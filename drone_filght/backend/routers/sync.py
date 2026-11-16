from fastapi import APIRouter, Depends, Path, Query, Body, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, Union, Optional
from backend.database import get_db
from backend.config import settings
from backend.models.models import User
from backend.services.auth_service import get_optional_current_user
from backend.schemas.schemas import (
    SyncProjectCreate,
    SyncProjectResponse,
    SyncStatusUpdate,
    SyncAnalysisResultCreate,
    SyncAnalysisResultResponse
)
from backend.services.sync_service import sync_service

router = APIRouter(prefix="/sync", tags=["PC·모바일 실시간 데이터 연동 (PC-Mobile Data Sync)"])

@router.post(
    "/projects",
    response_model=SyncProjectResponse,
    summary="1. [PC] 신규 촬영 프로젝트 생성 & 고유 코드/QR코드 발급"
)
def create_project(
    project_in: SyncProjectCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    PC 웹에서 촬영 목적 및 장소를 저장하고,
    'DRONE_001'과 같은 고유 프로젝트 코드 및 모바일 즉시 접속용 QR코드를 생성합니다.
    로그인한 경우 해당 사용자의 프로젝트로 귀속됩니다.
    """
    user_obj = current_user if isinstance(current_user, User) else None
    return sync_service.create_pc_project(db=db, project_in=project_in, current_user=user_obj)


@router.get(
    "/projects/{identifier}",
    response_model=SyncProjectResponse,
    summary="2. [모바일/PC] 프로젝트 ID(DRONE_001)로 데이터 조회 및 분석 시작"
)
def get_project(
    identifier: str = Path(..., description="프로젝트 고유 ID(정수) 또는 코드(예: DRONE_001)"),
    for_mobile: bool = Query(True, description="모바일 스마트폰 현장 접속 여부 (True 시 상태를 ANALYZING으로 자동 전이)"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 암호화 서명 보안 토큰"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    스마트폰 카메라로 QR코드를 스캔하거나 DRONE_001 코드를 입력하여
    PC에서 수립된 비행/촬영 계획을 불러오고, 상태를 'ANALYZING(분석 중)'으로 전환합니다.
    소유권 또는 QR 보안 토큰을 검증하여 타인의 프로젝트 무단 열람을 차단합니다.
    """
    user_obj = current_user if isinstance(current_user, User) else None
    token_str = token if isinstance(token, str) else None
    is_mobile = for_mobile if isinstance(for_mobile, bool) else True
    return sync_service.get_project_sync(
        db=db,
        identifier=identifier,
        for_mobile=is_mobile,
        current_user=user_obj,
        project_token=token_str
    )


@router.post(
    "/projects/{identifier}/results",
    response_model=SyncAnalysisResultResponse,
    summary="3. [모바일] 촬영 구도 및 AI 분석 결과·영상 저장 (완료 전이)"
)
def save_analysis_result(
    identifier: str = Path(..., description="프로젝트 고유 ID 또는 코드(DRONE_001)"),
    result_in: SyncAnalysisResultCreate = Body(...),
    token: Optional[str] = Query(None, description="모바일 QR 접속 암호화 서명 보안 토큰"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    모바일 웹(camera.html)에서 추천 구도 일치 촬영을 마친 뒤,
    프레임 점수, 오프셋, 녹화 영상 URL을 저장하고 프로젝트 상태를 'COMPLETED(완료)'로 갱신합니다.
    """
    user_obj = current_user if isinstance(current_user, User) else None
    token_str = token if isinstance(token, str) else None
    return sync_service.save_mobile_analysis_result(
        db=db,
        identifier=identifier,
        result_in=result_in,
        current_user=user_obj,
        project_token=token_str
    )


@router.get(
    "/projects/{identifier}/results",
    summary="4. [PC] 모바일에서 저장한 분석 결과 및 녹화 영상 실시간 조회"
)
def get_project_results(
    identifier: str = Path(..., description="프로젝트 고유 ID 또는 코드(DRONE_001)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    PC 웹 대시보드에서 모바일 현장에서 방금 전송된
    구도 분석 결과, 프레임 일치 점수 및 녹화 영상 목록을 실시간으로 확인합니다.
    """
    user_obj = current_user if isinstance(current_user, User) else None
    return sync_service.get_pc_project_results(db=db, identifier=identifier, current_user=user_obj)


@router.patch(
    "/projects/{identifier}/status",
    summary="5. 데이터 상태 관리 (CREATED ➔ ANALYZING ➔ COMPLETED ➔ FAILED)"
)
def update_status(
    identifier: str = Path(..., description="프로젝트 고유 ID 또는 코드(DRONE_001)"),
    status_in: SyncStatusUpdate = Body(...),
    db: Session = Depends(get_db)
):
    """
    프로젝트의 생명주기 상태(생성, 분석 중, 완료, 실패)를 갱신합니다.
    """
    return sync_service.update_project_status(db=db, identifier=identifier, status=status_in.status)


@router.get(
    "/projects/{identifier}/qr",
    summary="6. [시연용] 프로젝트 접속용 QR코드 Base64 Data URI 조회"
)
def get_project_qr(
    identifier: str = Path(..., description="프로젝트 고유 ID 또는 코드(DRONE_001)"),
    db: Session = Depends(get_db)
):
    """
    PC 화면에 표시하여 스마트폰으로 바로 스캔할 수 있는 QR코드 이미지를 반환합니다.
    보안 토큰이 포함되어 있어 스캔 시 자동 인증됩니다.
    """
    proj = sync_service.find_project(db, identifier)
    token_param = f"&token={proj.project_token}" if proj.project_token else ""
    mobile_url = f"{settings.MOBILE_WEB_URL}/camera.html?project_code={proj.project_code}{token_param}"
    qr_b64 = sync_service.generate_qr_base64(mobile_url)
    return {
        "project_code": proj.project_code,
        "mobile_access_url": mobile_url,
        "qr_code_base64": qr_b64
    }
