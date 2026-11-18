import os
import re
import html
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import jwt
import bcrypt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.models import User, ShootingProject

# HTTP Bearer scheme for Swagger UI & API headers
security_bearer = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.project_token_expire_hours = settings.PROJECT_TOKEN_EXPIRE_HOURS

    # ==========================================
    # 1. 비밀번호 단방향 해싱 & 검증 (Bcrypt)
    # ==========================================
    def hash_password(self, plain_password: str) -> str:
        """평문 비밀번호를 Bcrypt Salt + Hash로 안전하게 암호화합니다."""
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """입력된 평문 비밀번호와 저장된 Bcrypt 해시를 안전하게 대조합니다."""
        if not hashed_password:
            return False
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

    # ==========================================
    # 2. JWT 사용자 인증 토큰 발급 & 검증
    # ==========================================
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """RFC 7519 기반의 서명된 JWT Access Token을 발급합니다."""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta if expires_delta else timedelta(minutes=self.access_token_expire_minutes)
        )
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "token_type": "access_token"
        })
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_access_token(self, token: str) -> Dict[str, Any]:
        """JWT 토큰의 서명 및 만료 시간을 검증하고 페이로드를 복호화합니다."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("token_type") != "access_token":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="유효하지 않은 토큰 유형입니다. (Access Token 아님)"
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 토큰(JWT)이 만료되었습니다. 다시 로그인해 주세요."
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 토큰 서명이 위조되었거나 손상되었습니다."
            )

    # ==========================================
    # 3. 프로젝트별 서명된 접근 보안 토큰 (Project Access Token)
    #    "단순히 URL을 알아도 토큰 없이는 타인 프로젝트 접근 차단"
    # ==========================================
    def create_project_access_token(
        self,
        project_code: str,
        project_id: int,
        user_id: Optional[int] = None,
        expires_hours: Optional[int] = None
    ) -> str:
        """
        특정 프로젝트 전용의 서명된 암호화 접근 토큰을 발급합니다.
        스마트폰 QR코드 접속 시 URL 파라미터(?token=...)로 함께 전달되어
        타인이 프로젝트 코드(DRONE_001)만 유추하여 데이터를 훔쳐보는 행위를 완전 차단합니다.
        """
        hours = expires_hours if expires_hours else self.project_token_expire_hours
        expire = datetime.now(timezone.utc) + timedelta(hours=hours)
        payload = {
            "sub": "project_access",
            "project_code": project_code,
            "project_id": project_id,
            "owner_user_id": user_id,
            "scope": "mobile_access",
            "exp": expire,
            "iat": datetime.now(timezone.utc)
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_project_access_token(self, token: str, expected_project_code: str) -> Dict[str, Any]:
        """
        모바일 QR 스캔 시 전달된 프로젝트 보안 토큰을 검증합니다.
        위조된 토큰이거나 대상 프로젝트 코드가 일치하지 않으면 차단합니다.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("sub") != "project_access":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="해당 토큰은 프로젝트 전용 접근 토큰이 아닙니다."
                )
            if payload.get("project_code") != expected_project_code:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"보안 토큰의 프로젝트 코드 불일치 (기대값: {expected_project_code})"
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="프로젝트 접속 보안 토큰이 만료되었습니다. PC 웹에서 QR코드를 새로 발급받으세요."
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="위조되었거나 유효하지 않은 프로젝트 보안 토큰입니다. (접근 차단)"
            )

    # ==========================================
    # 4. 데모 사용자 시드 (초기 계정 자동 세팅)
    # ==========================================
    def init_default_users(self, db: Session):
        """
        초기 시연을 위한 역할별 기본 계정을 안전한 Bcrypt 해시로 생성합니다.
        - pilot (PC 조종사용): pilot / pilot1234
        - crew (모바일 현장팀용): crew / crew1234
        - admin (최고 관리자용): admin / admin1234
        """
        default_accounts = [
            {
                "username": "pilot",
                "email": "pilot_pc@skycommand.kr",
                "full_name": "스카이 조종사 (PC 관제)",
                "password": "pilot1234",
                "role": "pilot",
                "drone_model": "DJI Mavic 3 Pro",
                "drone_weight_g": 958
            },
            {
                "username": "crew",
                "email": "crew@skycommand.kr",
                "full_name": "현장 카메라 촬영팀 (모바일)",
                "password": "crew1234",
                "role": "crew",
                "drone_model": "DJI Mini 4 Pro",
                "drone_weight_g": 249
            },
            {
                "username": "admin",
                "email": "admin@skycommand.kr",
                "full_name": "통합 안전관리관 (Admin)",
                "password": "admin1234",
                "role": "admin",
                "drone_model": "DJI Inspire 3",
                "drone_weight_g": 3995
            }
        ]

        for acc in default_accounts:
            user = db.query(User).filter(User.username == acc["username"]).first()
            if not user:
                hashed = self.hash_password(acc["password"])
                new_user = User(
                    username=acc["username"],
                    email=acc["email"],
                    full_name=acc["full_name"],
                    hashed_password=hashed,
                    role=acc["role"],
                    drone_model=acc["drone_model"],
                    drone_weight_g=acc["drone_weight_g"],
                    is_active=True
                )
                db.add(new_user)
            else:
                # 기존 사용자의 해시 비밀번호 및 역할 보정
                if not user.hashed_password:
                    user.hashed_password = self.hash_password(acc["password"])
                if not user.role:
                    user.role = acc["role"]
                user.is_active = True

        # 기존 drone_pilot 계정도 보정
        legacy_pilot = db.query(User).filter(User.username == "drone_pilot").first()
        if legacy_pilot and not legacy_pilot.hashed_password:
            legacy_pilot.hashed_password = self.hash_password("drone1234")
            legacy_pilot.role = "pilot"
            legacy_pilot.is_active = True

        db.commit()

    # ==========================================
    # 5. 사용자 인증 및 로그인 처리
    # ==========================================
    def authenticate_user(self, db: Session, username: str, plain_password: str) -> Optional[User]:
        """사용자 아이디(또는 이메일)와 비밀번호를 검증하여 일치 시 User 객체를 반환합니다."""
        clean_target = (username or "").strip()
        user = db.query(User).filter(
            (User.username == clean_target) | (User.email == clean_target)
        ).first()
        if not user:
            return None
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="비활성화된 계정입니다. 관리자에게 문의하세요."
            )
        if not self.verify_password(plain_password, user.hashed_password):
            return None
        return user

    # ==========================================
    # 6. 화면별 기능 권한 제어 (PC vs 모바일 기능 분리)
    # ==========================================
    def check_screen_permission(self, role: str, required_screen: str) -> bool:
        """
        PC 기능과 모바일 기능의 화면별 접근 권한을 분리 검사합니다.
        - PC 기능 (flight, airspace, pc/projects): pilot, admin
        - 모바일 기능 (camera, analyze, recommendations): crew, pilot, admin
        - 관리자 기능: admin
        """
        role = role.lower() if role else ""
        if role == "admin":
            return True
        if required_screen == "pc":
            return role in ["pilot", "admin"]
        elif required_screen == "mobile":
            return role in ["crew", "pilot", "admin"]
        elif required_screen == "admin":
            return role == "admin"
        return False

    # ==========================================
    # 7. 사용자별 데이터 접근 제어 (IDOR 방어)
    #    "다른 사용자의 프로젝트 데이터 접근 완벽 차단"
    # ==========================================
    def verify_project_ownership(
        self,
        db: Session,
        project_identifier: str,
        current_user: Optional[User] = None,
        project_token: Optional[str] = None
    ) -> ShootingProject:
        """
        [데이터 보안 핵심]
        1. 모바일 QR코드로 전달된 암호화 서명 project_token이 유효한 경우: 현장 열람/저장 허용
        2. 로그인 사용자가 Admin인 경우: 전체 열람/저장 허용
        3. 로그인 사용자가 해당 프로젝트의 생성자(owner)인 경우: 열람/저장 허용
        4. 타인의 프로젝트를 임의의 ID/코드로 훔쳐보려는 경우: 403 Forbidden 즉각 차단!
        """
        # 프로젝트 검색 (ID 또는 코드)
        if project_identifier.isdigit():
            proj = db.query(ShootingProject).filter(ShootingProject.id == int(project_identifier)).first()
        else:
            proj = db.query(ShootingProject).filter(ShootingProject.project_code == project_identifier).first()

        if not proj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"대상 촬영 프로젝트({project_identifier})를 찾을 수 없습니다."
            )

        # 경로 1: 모바일 QR코드 보안 토큰 검증
        if project_token:
            self.verify_project_access_token(project_token, expected_project_code=proj.project_code)
            return proj

        # 경로 2: 로그인 사용자 소유권 검증
        if current_user:
            if current_user.role == "admin":
                return proj  # 관리자는 전수 열람 허용
            if proj.user_id is None or proj.user_id == current_user.id:
                return proj  # 본인 소유 프로젝트 허용
            
            # 타인 프로젝트 무단 접근 시도 차단!
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"해당 프로젝트(코드: {proj.project_code})에 대한 접근 권한이 없습니다. (타인 프로젝트 접근 차단)"
            )

        # 경로 3: 인증 수단 없음
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인 인증 토큰(JWT) 또는 프로젝트 전용 보안 토큰(?token=...)이 필요합니다."
        )

    # ==========================================
    # 8. 입력값 살균 및 보안 필터링 (XSS & Injection 방지)
    # ==========================================
    def sanitize_text(self, text: Optional[str]) -> str:
        """
        사용자 입력 문자열에서 위험한 HTML 태그 및 악성 스크립트를 살균합니다.
        """
        if not text:
            return ""
        # 1. HTML 엔티티 이스케이프
        clean = html.escape(text.strip())
        # 2. 자바스크립트 슈도 프로토콜 제거
        clean = re.sub(r"javascript:", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"on\w+\s*=", "", clean, flags=re.IGNORECASE)
        return clean

    # ==========================================
    # 9. 외부 API 키 은닉 및 상태 마스킹
    # ==========================================
    def get_masked_api_keys(self) -> Dict[str, Any]:
        """
        Gemini, VWorld, 기상청 API 키의 실서버 보관 상태를 확인하되,
        실제 비밀키는 마스킹 처리하여 프론트엔드 및 외부에 일절 노출하지 않습니다.
        """
        def mask_key(k: str) -> str:
            if not k:
                return "UNCONFIGURED"
            if len(k) <= 8:
                return "****"
            return f"{k[:4]}...{k[-4:]}"

        return {
            "gemini_api": {
                "configured": bool(settings.GEMINI_API_KEY),
                "masked": mask_key(settings.GEMINI_API_KEY)
            },
            "vworld_api": {
                "configured": bool(settings.VWORLD_API_KEY),
                "masked": mask_key(settings.VWORLD_API_KEY)
            },
            "kma_api": {
                "configured": bool(settings.KMA_API_KEY),
                "masked": mask_key(settings.KMA_API_KEY)
            },
            "storage_mode": "SERVER_ENCRYPTED_ENV",
            "frontend_exposed": False
        }


auth_service = AuthService()


# ==========================================
# FastAPI 의존성 함수들 (Dependencies)
# ==========================================
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> User:
    """
    Authorization: Bearer <token> 헤더를 파싱하여 현재 로그인 사용자를 반환합니다.
    토큰이 없거나 유효하지 않으면 401 Unauthorized를 발생시킵니다.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요한 서비스입니다. Authorization 헤더에 Bearer 토큰을 포함하세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = auth_service.decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰 페이로드에 사용자 식별 정보(sub)가 없습니다."
        )
        
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="토큰에 해당하는 사용자가 데이터베이스에 존재하지 않습니다."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다."
        )
    return user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    선택적 로그인 사용자 의존성:
    로그인한 상태면 User 반환, 비로그인 상태면 None 반환.
    """
    if not credentials:
        return None
    try:
        payload = auth_service.decode_access_token(credentials.credentials)
        username = payload.get("sub")
        if not username:
            return None
        return db.query(User).filter(User.username == username).first()
    except Exception:
        return None


def require_role(allowed_roles: List[str]):
    """
    특정 역할(Role)만 접근을 허용하는 권한 제어 가드 의존성을 생성합니다.
    예: Depends(require_role(["pilot", "admin"]))
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"접근 권한이 없습니다. (요구 권한: {', '.join(allowed_roles)}, 본인 권한: {current_user.role})"
            )
        return current_user
    return role_checker
