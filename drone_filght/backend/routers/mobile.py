from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from typing import List
from backend.database import get_db
from backend.schemas.schemas import (
    ShootingProjectResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    RecommendationResponse,
    AnalysisResultCreate,
    AnalysisResultResponse
)
from backend.services.mobile_service import mobile_service

router = APIRouter(prefix="/mobile", tags=["Mobile API (C, D Data)"])

@router.get("/projects", response_model=List[ShootingProjectResponse], summary="촬영 프로젝트 목록 조회 [C 영역]")
def get_mobile_projects(db: Session = Depends(get_db)):
    """
    모바일 웹(날려드려) '내 촬영 신청' 화면에서 PC에서 수립된 비행/촬영 계획을 불러옵니다.
    """
    return mobile_service.get_mobile_projects(db)


@router.post("/analyze", response_model=AnalyzeResponse, summary="카메라 촬영 장면 실시간 분석 요청 [D 영역]")
def analyze_frame(req: AnalyzeRequest):
    """
    스마트폰 후면 카메라 및 드론 카메라 영상의 수평선, 피사체 위치를 실시간 분석하여
    오프셋 보정치 및 상하좌우 조종 화살표(↑↓←→) 가이드를 반환합니다.
    """
    return mobile_service.analyze_camera_frame(req)


@router.get("/recommendations/{id}", response_model=RecommendationResponse, summary="추천 구도 및 조종 가이드 조회 [D 영역]")
def get_recommendations(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    db: Session = Depends(get_db)
):
    """
    선택한 프로젝트의 최적 촬영 콘셉트, 180° 셔터 룰/ND필터 레시피, 조종기 3단계 스틱 콤보 가이드를 조회합니다.
    """
    return mobile_service.get_recommendation_details(db, project_id)


@router.post("/results", response_model=AnalysisResultResponse, summary="촬영 분석 결과 및 녹화 영상 저장 [C, D 영역]")
@router.post("/result", response_model=AnalysisResultResponse, summary="촬영 분석 결과 및 녹화 영상 저장 (단수형 별칭) [C, D 영역]")
def save_analysis_result(res_in: AnalysisResultCreate, db: Session = Depends(get_db)):
    """
    모바일에서 AI 추천 구도에 맞춰 보정 촬영을 마친 뒤, 분석 로그 및 녹화 영상 URL을 저장합니다.
    """
    return mobile_service.save_analysis_result(db, res_in)
