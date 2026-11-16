from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.external import WeatherAPIError
from backend.schemas.schemas import (
    ShootingProjectCreate,
    ShootingProjectResponse,
    WeatherResponse,
    UserSettingResponse,
    UserSettingUpdate
)
from backend.services.common_service import common_service

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
