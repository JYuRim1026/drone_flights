from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from typing import Optional
from backend.database import get_db
from backend.models.models import User
from backend.external import WeatherAPIError
from backend.schemas.schemas import (
    ShootingProjectCreate,
    ShootingProjectResponse,
    WeatherResponse,
    UserSettingResponse,
    UserSettingUpdate,
    ProjectCommonPathResponse,
    CommonPathLearnRequest,
    CommonPathLearnResponse,
    CommonPathHistoryResponse,
    PersonalizedPathGenerateRequest,
    PersonalizedShootingPathResponse,
    PersonalizedPathComparisonResponse
)
from backend.services.common_service import common_service
from backend.services.collaborative_path_service import collaborative_path_service
from backend.services.personalized_path_service import personalized_path_service
from backend.services.auth_service import auth_service, get_optional_current_user

router = APIRouter(prefix="/common", tags=["Common API (C, E Data)"])

@router.get("/projects/{id}", response_model=ShootingProjectResponse, summary="공통 프로젝트 상세 조회 [C 영역]")
def get_common_project(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    db: Session = Depends(get_db)
):
    """
    PC와 모바일 양쪽에서 공통으로 참조하는 비행 및 시네마틱 촬영 프로젝트의 상세 정보를 조회합니다.
    """
    return common_service.get_project_by_id(db, project_id)


@router.post("/projects", response_model=ShootingProjectResponse, summary="신규 촬영 프로젝트 생성 [C 영역]")
@router.post("/project", response_model=ShootingProjectResponse, summary="신규 촬영 프로젝트 생성 (단수형 별칭) [C 영역]")
def create_common_project(
    project_in: ShootingProjectCreate,
    db: Session = Depends(get_db)
):
    """
    PC 웹에서 AI 분석을 거친 촬영 프로젝트를 생성하거나, 모바일에서 새로운 미션을 등록합니다.
    """
    return common_service.create_project(db, project_in)


@router.get("/weather", response_model=WeatherResponse, summary="실시간 날씨 및 비행 적합도 조회 [E 영역]")
def get_weather(
    lat: float = Query(37.5284, description="위도"),
    lon: float = Query(126.9328, description="경도"),
    location_name: str = Query("서울 여의도 한강공원", description="지역명")
):
    """
    기상청 단기예보 조회서비스 2.0(실황·초단기예보)을 바탕으로 실시간 풍속(m/s), 추정 돌풍, 강수 확률, 비행 안전 적합도를 제공합니다.
    """
    try:
        return common_service.get_current_weather(lat, lon, location_name)
    except WeatherAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/settings", response_model=UserSettingResponse, summary="사용자 환경 설정 조회 [E 영역]")
@router.get("/user", response_model=UserSettingResponse, summary="사용자 환경 설정 조회 (별칭) [E 영역]")
def get_user_settings(db: Session = Depends(get_db)):
    """
    드론 안전 마진 고도, 알림 설정, 날씨 자동 갱신 등 공통 사용자 설정을 조회합니다.
    """
    return common_service.get_user_settings(db)


@router.put("/settings", response_model=UserSettingResponse, summary="사용자 환경 설정 변경 [E 영역]")
@router.put("/user", response_model=UserSettingResponse, summary="사용자 환경 설정 변경 (별칭) [E 영역]")
def update_user_settings(
    setting_in: UserSettingUpdate,
    db: Session = Depends(get_db)
):
    """
    공통 사용자 환경 설정을 업데이트합니다.
    """
    return common_service.update_user_settings(db, setting_in)


# ==========================================
# 다중 사용자 공통 경로 학습 API (Phase 8 - PC/공통)
# ==========================================
@router.get(
    "/projects/{project_id}/common-path",
    response_model=Optional[ProjectCommonPathResponse],
    summary="프로젝트별 최신 공통 권장 경로 조회 [PC/공통]"
)
def get_common_project_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """PC 웹 및 공통 클라이언트를 위한 최신 활성 공통 권장 경로 조회"""
    auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    return collaborative_path_service.get_active_common_path(db, project_id)


@router.post(
    "/projects/{project_id}/common-path/learn",
    response_model=CommonPathLearnResponse,
    summary="프로젝트별 다중 사용자 공통 경로 학습 실행 [PC/공통]"
)
def learn_common_project_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: Optional[CommonPathLearnRequest] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """PC 웹에서 참여자들의 누적 보행 경로를 AI 학습하여 최신 공통 권장 경로를 생성/갱신"""
    auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    min_q = payload.min_quality_threshold if payload and payload.min_quality_threshold is not None else 60.0
    max_p = payload.max_paths_to_evaluate if payload and payload.max_paths_to_evaluate is not None else 50

    new_path = collaborative_path_service.learn_project_common_path(
        db=db,
        project_id=project_id,
        min_quality_threshold=min_q,
        max_paths=max_p,
        current_user=current_user
    )

    return CommonPathLearnResponse(
        status="success",
        project_id=project_id,
        version=new_path.version,
        message=f"다중 사용자({new_path.contributor_count}명)의 우수 경로({new_path.total_paths_used}건)를 반영한 v{new_path.version} 공통 권장 경로가 성공적으로 학습되었습니다.",
        contributor_count=new_path.contributor_count,
        total_paths_used=new_path.total_paths_used,
        quality_score=new_path.quality_score,
        common_path=new_path
    )


@router.get(
    "/projects/{project_id}/common-path/history",
    response_model=CommonPathHistoryResponse,
    summary="공통 권장 경로 버전별 업데이트 이력 조회 [PC/공통]"
)
def get_common_project_path_history(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """프로젝트의 버전별 공통 권장 경로 업데이트 이력 전체 조회"""
    auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    history = collaborative_path_service.get_common_path_history(db, project_id)
    active_ver = next((h.version for h in history if h.is_active), None)

    return CommonPathHistoryResponse(
        project_id=project_id,
        total_versions=len(history),
        active_version=active_ver,
        history=history
    )


# ==========================================
# Phase 9: 개인별 맞춤 촬영 경로 API [PC/공통]
# ==========================================
@router.get(
    "/projects/{project_id}/personalized-path",
    response_model=PersonalizedShootingPathResponse,
    summary="개인별 맞춤 촬영 권장 경로 조회 [PC/공통]"
)
def get_user_personalized_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    현재 로그인 사용자의 성향과 이력을 기반으로 한 맞춤 촬영 경로를 조회합니다.
    (기존 경로가 없으면 성향 분석을 통해 자동 생성)
    """
    proj = auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    target_user_id = current_user.id if current_user else proj.user_id or 1

    pers = personalized_path_service.get_user_personalized_path(db, project_id, target_user_id)
    if not pers:
        pers = personalized_path_service.generate_personalized_path(db, project_id, target_user_id, "AUTO")

    is_stale, latest_ver = personalized_path_service.check_staleness(db, pers)
    res_dict = {
        "id": pers.id,
        "project_id": pers.project_id,
        "user_id": pers.user_id,
        "common_path_id": pers.common_path_id,
        "base_common_version": pers.base_common_version,
        "active_common_version": latest_ver,
        "is_stale": is_stale,
        "variation_type": pers.variation_type,
        "personalized_waypoints": pers.personalized_waypoints,
        "generation_reason": pers.generation_reason,
        "style_metadata": pers.style_metadata,
        "is_active": pers.is_active,
        "created_at": pers.created_at,
        "updated_at": pers.updated_at
    }
    return PersonalizedShootingPathResponse(**res_dict)


@router.post(
    "/projects/{project_id}/personalized-path/generate",
    response_model=PersonalizedShootingPathResponse,
    summary="개인별 맞춤 촬영 경로 생성 및 재변형 [PC/공통]"
)
def generate_user_personalized_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: Optional[PersonalizedPathGenerateRequest] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    사용자의 요청에 따라 특정 변형 유형(STRAIGHT, ZIGZAG, POI_WAYPOINT, AUTO)으로
    맞춤 권장 동선을 생성하거나 최신 공통 경로를 기반으로 재갱신합니다.
    """
    proj = auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    target_user_id = current_user.id if current_user else proj.user_id or 1

    pref_type = payload.preferred_variation_type if payload else "AUTO"
    force_regen = payload.force_regenerate if payload else False

    pers = personalized_path_service.generate_personalized_path(
        db=db,
        project_id=project_id,
        user_id=target_user_id,
        preferred_variation_type=pref_type,
        force_regenerate=force_regen
    )

    is_stale, latest_ver = personalized_path_service.check_staleness(db, pers)
    res_dict = {
        "id": pers.id,
        "project_id": pers.project_id,
        "user_id": pers.user_id,
        "common_path_id": pers.common_path_id,
        "base_common_version": pers.base_common_version,
        "active_common_version": latest_ver,
        "is_stale": is_stale,
        "variation_type": pers.variation_type,
        "personalized_waypoints": pers.personalized_waypoints,
        "generation_reason": pers.generation_reason,
        "style_metadata": pers.style_metadata,
        "is_active": pers.is_active,
        "created_at": pers.created_at,
        "updated_at": pers.updated_at
    }
    return PersonalizedShootingPathResponse(**res_dict)


@router.get(
    "/projects/{project_id}/personalized-path/compare",
    response_model=PersonalizedPathComparisonResponse,
    summary="공통 권장 동선 vs 개인화 맞춤 동선 비교 분석 [PC/공통]"
)
def compare_personalized_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    프로젝트의 불변 공통 권장 동선과 사용자 맞춤형 변형 동선 간의 좌표 편차 및 세부 차이를 비교합니다.
    """
    proj = auth_service.verify_project_ownership(db, str(project_id), current_user, None)
    target_user_id = current_user.id if current_user else proj.user_id or 1

    pers = personalized_path_service.get_user_personalized_path(db, project_id, target_user_id)
    if not pers:
        pers = personalized_path_service.generate_personalized_path(db, project_id, target_user_id, "AUTO")

    cmp_data = personalized_path_service.compare_with_common_path(db, pers)
    return PersonalizedPathComparisonResponse(**cmp_data)

