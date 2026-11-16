from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.database import get_db
from backend.models.models import User, UserSetting, ShootingProject
from backend.services.auth_service import (
    auth_service,
    get_current_user,
    require_role
)
from backend.schemas.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserSecureProfile,
    ProjectTokenResponse,
    ApiKeySecurityStatus
)

router = APIRouter(prefix="/auth", tags=["사용자 인증 및 보안 (Authentication & Security)"])


@router.post(
    "/register",
    response_model=UserSecureProfile,
    status_code=status.HTTP_201_CREATED,
    summary="1. 신규 사용자 등록 (회원가입)"
)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """
    신규 사용자를 등록하고 비밀번호를 Bcrypt로 안전하게 단방향 암호화합니다.
    - 역할(Role): pilot (PC 조종사), crew (모바일 현장팀), admin (관리자)
    """
    clean_username = auth_service.sanitize_text(user_in.username)
    clean_name = auth_service.sanitize_text(user_in.full_name)

    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"이미 등록된 사용자 아이디입니다: '{clean_username}'"
        )

    # 유효한 역할 검증
    valid_roles = ["pilot", "crew", "admin"]
    role = user_in.role.lower() if user_in.role else "pilot"
    if role not in valid_roles:
        role = "pilot"

    hashed_pw = auth_service.hash_password(user_in.password)
    new_user = User(
        username=clean_username,
        email=user_in.email,
        full_name=clean_name,
        hashed_password=hashed_pw,
        role=role,
        drone_model=user_in.drone_model,
        drone_weight_g=user_in.drone_weight_g,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 기본 사용자 환경설정(user_settings) 자동 생성
    new_setting = UserSetting(
        user_id=new_user.id,
        safety_margin_m=30,
        notification_enabled=True,
        weather_auto_refresh=True,
        preferred_camera_mode="cinematic"
    )
    db.add(new_setting)
    db.commit()

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="2. 사용자 로그인 & JWT Access Token 발급"
)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    """
    아이디와 비밀번호를 검증하고 RFC 7519 규격의 JWT 토큰을 발급합니다.
    PC와 모바일 화면 접근 권한(allowed_screens)을 함께 반환합니다.
    """
    user = auth_service.authenticate_user(db, login_in.username, login_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 일치하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 접근 가능 화면 목록 산출
    allowed_screens = []
    if user.role in ["pilot", "admin"]:
        allowed_screens.append("pc")
    if user.role in ["crew", "pilot", "admin"]:
        allowed_screens.append("mobile")
    if user.role == "admin":
        allowed_screens.append("admin")

    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role
    }
    access_token = auth_service.create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=auth_service.access_token_expire_minutes * 60,
        user_id=user.id,
        username=user.username,
        role=user.role,
        allowed_screens=allowed_screens
    )


@router.get(
    "/me",
    response_model=UserSecureProfile,
    summary="3. 현재 로그인 사용자 프로필 및 권한 조회 (토큰 검증)"
)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    HTTP Bearer JWT 토큰을 검증하여 현재 인증된 사용자의 프로필 정보를 반환합니다.
    """
    return current_user


@router.get(
    "/check-screen-access",
    summary="4. 화면별 접근 권한 검사 (PC 전용 vs 모바일 전용)"
)
def check_screen_access(
    screen: str = Query(..., description="검사할 화면 유형 ('pc', 'mobile', 'admin')"),
    current_user: User = Depends(get_current_user)
):
    """
    [화면별 기능 접근 제어]
    - PC 기능: pilot, admin만 접근 가능
    - 모바일 기능: crew, pilot, admin 접근 가능
    """
    has_access = auth_service.check_screen_permission(current_user.role, screen)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"사용자 '{current_user.username}'(역할: {current_user.role})은 '{screen}' 화면 기능에 접근할 수 없습니다."
        )

    return {
        "allowed": True,
        "username": current_user.username,
        "role": current_user.role,
        "screen": screen,
        "message": f"'{screen}' 화면 접근 승인됨"
    }


@router.post(
    "/projects/{project_code}/token",
    response_model=ProjectTokenResponse,
    summary="5. 프로젝트별 서명된 일회성/세션 접근 보안 토큰 발급"
)
def generate_project_token(
    project_code: str = Path(..., description="프로젝트 고유 코드 (예: DRONE_001)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [데이터 접근 제어 & 모바일 보안]
    단순히 프로젝트 코드(DRONE_001)만 유추해서 남의 촬영 계획을 훔쳐보지 못하도록,
    소유자(owner) 또는 관리자가 모바일 접속용 암호화 서명 보안 토큰을 발급합니다.
    """
    proj = db.query(ShootingProject).filter(ShootingProject.project_code == project_code).first()
    if not proj:
        raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")

    # 소유권 검사
    if current_user.role != "admin" and proj.user_id is not None and proj.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인이 소유한 프로젝트에 대해서만 모바일 접근 토큰을 발급할 수 있습니다."
        )

    token = auth_service.create_project_access_token(
        project_code=proj.project_code,
        project_id=proj.id,
        user_id=current_user.id
    )

    # 프로젝트 테이블에 토큰 기록
    proj.project_token = token
    db.commit()

    from backend.config import settings
    mobile_url = f"{settings.MOBILE_WEB_URL}/camera.html?project_code={proj.project_code}&token={token}"

    return ProjectTokenResponse(
        project_code=proj.project_code,
        project_token=token,
        expires_in_hours=auth_service.project_token_expire_hours,
        mobile_access_url=mobile_url
    )


@router.get(
    "/projects/verify-token",
    summary="6. 프로젝트 접근 보안 토큰 유효성 검증"
)
def verify_project_token(
    project_code: str = Query(..., description="프로젝트 코드 (DRONE_001)"),
    token: str = Query(..., description="보안 서명 토큰")
):
    """
    모바일 웹 앱이 로드될 때 전달된 토큰의 유효성을 실시간 검증합니다.
    """
    payload = auth_service.verify_project_access_token(token, expected_project_code=project_code)
    return {
        "valid": True,
        "project_code": project_code,
        "scope": payload.get("scope"),
        "expires_at": payload.get("exp")
    }


@router.get(
    "/api-keys-status",
    response_model=ApiKeySecurityStatus,
    summary="7. 서버 보관 외부 API 키 보안 마스킹 상태 확인"
)
def check_api_keys_security():
    """
    [API 키 보호]
    Gemini, VWorld, KMA 등 핵심 외부 API 키가 프론트엔드에 일절 노출되지 않고
    서버 백엔드 환경변수 내에서 안전하게 관리되고 있는지 마스킹 상태로 점검합니다.
    """
    return auth_service.get_masked_api_keys()
