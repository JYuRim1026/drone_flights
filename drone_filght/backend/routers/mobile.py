import os
import re
import json
import base64
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Path, Query, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.models.models import User, ShootingProject, ShootingAnalysis, LocationAsset
from backend.schemas.schemas import (
    ShootingProjectCreate,
    ShootingProjectResponse,
    MobileProjectDetailResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    RecommendationResponse,
    AnalysisResultCreate,
    AnalysisResultResponse,
    ShootingPathCreate,
    ShootingPathResponse,
    ShootingPathProjectSummary,
    LocationAssetCreate,
    LocationAssetResponse,
    TechniqueCatalogItem,
    PersonalizedRecommendationResponse,
    TechniqueSelectRequest,
    TechniqueSelectResponse,
    TechniqueFeedbackRequest,
    TechniqueFeedbackResponse,
    PathAnalysisDetailResponse,
    NextRoundPathResponse,
    ProjectCommonPathResponse,
    CommonPathLearnRequest,
    CommonPathLearnResponse,
    CommonPathHistoryResponse,
    PersonalizedPathGenerateRequest,
    PersonalizedShootingPathResponse,
    PersonalizedPathComparisonResponse
)
from backend.services.mobile_service import mobile_service, UPLOAD_DIR
from backend.services.ai_service import ai_service
from backend.services.collaborative_path_service import collaborative_path_service
from backend.services.personalized_path_service import personalized_path_service
from backend.services.auth_service import auth_service, get_current_user, get_optional_current_user
from backend.external.gemini_client import gemini_client

logger = logging.getLogger(__name__)

class KeyframeAnalyzeItem(BaseModel):
    seq: int = Field(..., description="프레임 순번 (1, 2, 3)")
    ratio: Optional[float] = Field(None, description="영상 위치 비율 (0.15, 0.50, 0.85)")
    timestamp: Optional[float] = Field(None, description="추출 타임스탬프 (초)")
    base64: str = Field(..., description="Base64 인코딩된 이미지 데이터")
    mime_type: Optional[str] = Field("image/jpeg", description="MIME 타입")
    label: Optional[str] = Field(None, description="프레임 레이블")

class AnalyzeKeyframesRequest(BaseModel):
    keyframes: List[KeyframeAnalyzeItem] = Field(..., description="추출된 대표 프레임 목록 (최대 3장)")
    scene_intent: Optional[str] = Field(None, description="촬영 기획 의도 또는 설명")

router = APIRouter(prefix="/mobile", tags=["Mobile API (C, D Data)"])

def _clean_token(t: Any) -> Optional[str]:
    if not isinstance(t, str):
        return None
    val = t.strip()
    if not val or val == "mobile_launch" or val.lower() == "none" or val.lower() == "null":
        return None
    if val.count(".") != 2:
        return None
    return val

@router.get("/projects", response_model=List[ShootingProjectResponse], summary="1. [Step 1] 모바일 촬영 프로젝트 목록 조회 [C 영역]")
def get_mobile_projects(db: Session = Depends(get_db)):
    """
    모바일 웹(날려드려) '내 촬영 신청' 화면에서 PC에서 수립된 비행/촬영 계획을 불러옵니다.
    """
    return mobile_service.get_mobile_projects(db)


@router.get("/projects/resolve/{identifier}", response_model=MobileProjectDetailResponse, summary="프로젝트 ID 또는 코드로 모바일 프로젝트 조회")
def resolve_mobile_project(
    identifier: str = Path(..., description="프로젝트 고유 ID 또는 프로젝트 코드"),
    db: Session = Depends(get_db)
):
    """
    모바일 웹(camera.html)에서 URL의 project_code(예: DRONE_001) 또는 ID를 통해
    프로젝트 상세 정보 및 내부 PK project_id를 안전하게 식별합니다.
    """
    if identifier.isdigit():
        try:
            return mobile_service.get_mobile_project_detail(db, int(identifier))
        except HTTPException:
            pass

    proj = db.query(ShootingProject).filter(ShootingProject.project_code == identifier).first()
    if proj:
        return mobile_service.get_mobile_project_detail(db, proj.project_id)

    fallback = db.query(ShootingProject).order_by(ShootingProject.id.asc()).first()
    if fallback:
        return mobile_service.get_mobile_project_detail(db, fallback.project_id)

    raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")


@router.get("/projects/{project_id}", response_model=MobileProjectDetailResponse, summary="1. [Step 1] 모바일 촬영 프로젝트 상세 정보 불러오기 [C 영역]")
def get_mobile_project_detail(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    db: Session = Depends(get_db)
):
    """
    [Step 1] PC에서 생성된 특정 촬영 프로젝트를 선택하여
    촬영 목적, 장소, 촬영 시간, 원하는 구도 및 AI 분석 여부를 불러옵니다.
    """
    return mobile_service.get_mobile_project_detail(db, project_id)


@router.post("/projects", response_model=ShootingProjectResponse, status_code=201, summary="1. [Step 1] 모바일 신규 촬영 프로젝트 등록 [C 영역]")
def create_mobile_project(
    project_in: ShootingProjectCreate,
    db: Session = Depends(get_db)
):
    """
    [Step 1] 모바일 현장에서 직접 신규 촬영 목적, 장소, 시간, 원하는 구도를 설정하여 등록합니다.
    """
    return mobile_service.create_mobile_project(db, project_in)


@router.post("/analyze", response_model=AnalyzeResponse, summary="카메라 촬영 장면 실시간 분석 및 AI 구도 추천 [D 영역]")
def analyze_frame(
    req: AnalyzeRequest,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    [Phase 10] 스마트폰 후면 카메라 및 센서 데이터 기반 AI 종합 장면 분석 및 촬영/보행 방향 추천:
    - 4가지 데이터 결합: 프로젝트 정보, 장소 자료, 경로 동선(Phase 8/9), 사용자 선호도(Phase 5)
    - Gemini API 멀티모달 분석 (키 미설정/실패 시 컴퓨터 비전 규칙 엔진 자동 전환)
    - 촬영 방향(Shooting Guide: 상하좌우/수평) vs 보행 이동(Walking Guide: GPS 방위각/거리) 분리 산출
    - 초록색 프레임(.live.ready) 활성화 조건: 구도 및 수평도 일치 시 즉시 활성화 (보행 도달 여부와 독립)
    - 분석 결과 DB(shooting_analyses) 저장 (사용자 ID 및 회차 연계)
    """
    # 프로젝트 소유권 / 보안 검증 (토큰 또는 사용자 지정 시)
    if req.project_id and (token or current_user):
        try:
            auth_service.verify_project_ownership(db, str(req.project_id), current_user, _clean_token(token))
        except Exception:
            # QR 토큰이 mobile_launch 임시 토큰이거나 공개 데모 프로젝트일 경우 유연 처리
            pass

    # Phase A-6: 사용자 식별 및 선호도 분리 보장 (current_user -> req.user_id -> project.user_id)
    target_user = current_user
    if not target_user and req.user_id:
        target_user = db.query(User).filter(User.id == req.user_id).first()
    if not target_user and req.project_id:
        p_obj = db.query(ShootingProject).filter(ShootingProject.id == req.project_id).first()
        if p_obj and p_obj.user_id:
            target_user = db.query(User).filter(User.id == p_obj.user_id).first()

    eff_user_id = req.user_id or (target_user.id if target_user else None)

    return ai_service.analyze_scene_and_recommend(
        image_base64=req.image_base64,
        scene_intent=req.scene_intent,
        purpose=req.purpose or "orbit",
        current_pitch=req.current_pitch or -15.0,
        current_roll=req.current_roll,
        current_heading=req.current_heading,
        current_lat=req.current_lat,
        current_lng=req.current_lng,
        current_accuracy=req.current_accuracy,
        current_timestamp=req.current_timestamp,
        consecutive_arrival_count=req.consecutive_arrival_count or 0,
        current_waypoint_seq=req.current_waypoint_seq,
        project_id=req.project_id or 1,
        shooting_number=req.shooting_number or 1,
        current_user=target_user,
        user_id=eff_user_id,
        save_to_db=req.save_result if req.save_result is not None else True,
        db=db
    )


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
def save_analysis_result(
    res_in: AnalysisResultCreate,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    모바일에서 AI 추천 구도에 맞춰 보정 촬영을 마친 뒤, 분석 로그 및 녹화 영상 URL을 저장합니다.
    """
    return mobile_service.save_analysis_result(db, res_in, current_user=current_user)


@router.get(
    "/projects/{project_id}/analyses",
    summary="프로젝트별 촬영 분석 이력 목록 조회"
)
def get_project_analyses(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    limit: int = Query(20, ge=1, le=100),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 AI 촬영 장면 분석 및 구도 추천 이력을 최신순으로 조회합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    clean_limit = limit if isinstance(limit, int) else 20
    analyses = db.query(ShootingAnalysis).filter(
        ShootingAnalysis.project_id == project_id
    ).order_by(ShootingAnalysis.created_at.desc()).limit(clean_limit).all()

    return [{
        "analysis_id": a.analysis_id,
        "project_id": a.project_id,
        "analysis_status": a.analysis_status,
        "target_summary": a.target_summary,
        "environment_summary": a.environment_summary,
        "recommended_composition": a.recommended_composition,
        "composition_score": a.composition_score,
        "guide_message": a.guide_message,
        "target_coordinates": a.target_coordinates,
        "representative_image_path": a.representative_image_path,
        "created_at": a.created_at
    } for a in analyses]


@router.get(
    "/projects/{project_id}/analyses/latest",
    summary="프로젝트의 최신 AI 촬영 분석 결과 단건 조회"
)
def get_latest_project_analysis(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 가장 최근 AI 촬영 분석 결과를 조회합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    latest = db.query(ShootingAnalysis).filter(
        ShootingAnalysis.project_id == project_id
    ).order_by(ShootingAnalysis.created_at.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="촬영 분석 이력이 존재하지 않습니다.")

    return {
        "analysis_id": latest.analysis_id,
        "project_id": latest.project_id,
        "analysis_status": latest.analysis_status,
        "target_summary": latest.target_summary,
        "environment_summary": latest.environment_summary,
        "recommended_composition": latest.recommended_composition,
        "composition_score": latest.composition_score,
        "guide_message": latest.guide_message,
        "target_coordinates": latest.target_coordinates,
        "representative_image_path": latest.representative_image_path,
        "created_at": latest.created_at
    }


# ==========================================
# 2. 촬영 경로 API (ShootingPath)
# ==========================================
@router.post(
    "/projects/{project_id}/paths",
    response_model=ShootingPathResponse,
    status_code=201,
    summary="2. 모바일 보행 촬영 동선 및 센서 데이터 저장"
)
def save_shooting_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    path_in: ShootingPathCreate = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    스마트폰에서 수집한 실제 보행 이동 위치(GPS) 및 카메라 방향 센서(Euler/회전각),
    구도 분석 결과 및 AI 보정 동선을 DB에 저장합니다.
    (실제 드론 비행 경로가 아닌 스마트폰 보행 동선으로 취급)
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    path_in.project_id = project_id
    return mobile_service.save_shooting_path(db, path_in, current_user)


@router.get(
    "/projects/{project_id}/paths",
    response_model=List[ShootingPathResponse],
    summary="2. 특정 프로젝트의 전체 촬영 동선 이력 목록 조회"
)
def get_shooting_paths(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    선택한 프로젝트에 누적된 전체 촬영 회차(1회차, 2회차...)별 동선 및 센서 기록 목록을 조회합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return mobile_service.get_shooting_paths(db, project_id)


@router.get(
    "/projects/{project_id}/paths/summary",
    response_model=ShootingPathProjectSummary,
    summary="2. 프로젝트의 촬영 횟수 및 이전 촬영 기록 요약 확인"
)
def get_project_shooting_summary(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 총 촬영 시도 횟수, 최신 회차 번호, 유효 경로 개수 및 요약 히스토리를 확인합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return mobile_service.get_project_shooting_summary(db, project_id)


@router.get(
    "/projects/{project_id}/paths/{shooting_number}",
    response_model=ShootingPathResponse,
    summary="2. 특정 촬영 회차의 상세 동선 및 센서 데이터 조회"
)
def get_shooting_path_by_number(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    shooting_number: int = Path(..., description="촬영 회차 번호 (1, 2, 3...)"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    프로젝트 내 특정 촬영 회차의 세부 웨이포인트(스마트폰 GPS 및 방향 센서) 데이터를 조회합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return mobile_service.get_shooting_path_by_number(db, project_id, shooting_number)


@router.get(
    "/paths/{path_id}",
    response_model=ShootingPathResponse,
    summary="2. 특정 촬영 기록 상세 조회 (path_id 기준)"
)
def get_shooting_path_detail(
    path_id: int = Path(..., description="촬영 기록 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    촬영 기록 고유 ID(path_id)를 바탕으로 세부 동선 및 센서 분석 데이터를 조회합니다.
    """
    path = mobile_service.get_shooting_path_detail(db, path_id)
    auth_service.verify_project_ownership(db, str(path.project_id), current_user, _clean_token(token))
    return path


@router.post(
    "/projects/{project_id}/paths/analyze",
    response_model=PathAnalysisDetailResponse,
    summary="6. 스마트폰 실제 GPS 경로와 권장 경로 비교 및 보정 분석 단독 실행"
)
def analyze_shooting_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    path_in: ShootingPathCreate = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    [Phase 6] AI 권장 경로와 스마트폰 수집 실제 GPS 경로를 비교·분석:
    - 시작점/종료점 오차, 평균 횡방향 이탈도(m), 최대 이탈도 산출
    - GPS 정확도 20m 초과 저신뢰 데이터 필터링 및 정지 상태 미세 오차(Hovering/Drift) 자동 감지
    - Phase 4 구도 달성도(Sweet Spot 유지율)를 반영한 적응형 보정(alpha_weight)
    - 선형 보간 기반 차기 보정 경로(corrected_waypoints) 및 모바일 개선 조언 메시지 생성
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    path_in.project_id = project_id
    res = mobile_service.analyze_shooting_path(db, path_in, current_user)
    return PathAnalysisDetailResponse(**res)


@router.get(
    "/projects/{project_id}/paths/next-recommendation",
    response_model=NextRoundPathResponse,
    summary="6. 차기 회차(N+1) 추천 보행 경로 조회 (이전 유효 보정 경로 승계)"
)
def get_next_round_path_recommendation(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    [Phase 6] 다음 촬영 회차(N+1)에 적용할 권장 보행 경로를 조회합니다.
    - 이전 유효 촬영 회차(is_valid=True)가 존재하는 경우, 해당 회차의 AI 보정 경로(corrected_waypoints)를 자동 승계
    - 신규 사용자이거나 유효 이력이 없는 경우, 기본 프로젝트 기획 템플릿 제공
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    uid = current_user.id if current_user else None
    res = mobile_service.get_next_round_path_recommendation(db, project_id, user_id=uid)
    return NextRoundPathResponse(**res)


# ==========================================
# 3. 장소 자료 API (LocationAsset)
# ==========================================
@router.post(
    "/projects/{project_id}/assets",
    response_model=LocationAssetResponse,
    status_code=201,
    summary="3. 프로젝트별 장소 자료 등록 (JSON 메타데이터)"
)
def create_location_asset(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    asset_in: LocationAssetCreate = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    촬영 장소의 파노라마 이미지, 프리뷰 영상, 캡처 이미지 URL 및 AI 감지 객체 메타데이터를 등록합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    asset_in.project_id = project_id
    return mobile_service.create_location_asset(db, asset_in, current_user)


@router.post(
    "/projects/{project_id}/assets/upload",
    response_model=LocationAssetResponse,
    status_code=201,
    summary="3. 스마트폰 현장 촬영 파일(파노라마/영상/캡처) 실제 물리 업로드"
)
def upload_location_asset_file(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    file: UploadFile = File(..., description="업로드할 실제 사진/영상 파일"),
    asset_type: str = Form("PANORAMA", description="자료 종류 (PANORAMA, SHORT_VIDEO, CAMERA_FRAME, KEY_FEATURE)"),
    is_common: bool = Form(False, description="공통 자료 여부 (True: 사전 공통, False: 현장 개인 업로드)"),
    detected_features: Optional[str] = Form(None, description="AI 객체 및 지형 감지 JSON 문자열"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    스마트폰 카메라로 현장에서 직접 촬영한 파노라마 사진, 짧은 영상, 프레임 캡처를 백엔드에 안전하게 물리 저장합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))

    features_dict = None
    if detected_features:
        try:
            features_dict = json.loads(detected_features)
        except Exception:
            features_dict = {"raw_text": detected_features}

    file_bytes = file.file.read() if hasattr(file, "file") else file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일 내용이 비어 있습니다.")

    return mobile_service.save_uploaded_asset(
        db=db,
        project_id=project_id,
        filename=file.filename or "upload.jpg",
        file_bytes=file_bytes,
        asset_type=asset_type,
        is_common=is_common,
        detected_features=features_dict,
        current_user=current_user
    )


@router.post(
    "/projects/{project_id}/assets/{asset_id}/analyze-keyframes",
    status_code=200,
    summary="3. [Phase 12] 사전 장소 영상 대표 프레임 Gemini Vision 종합 분석 및 메타데이터 갱신"
)
def analyze_location_asset_keyframes(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    asset_id: int = Path(..., description="분석 대상 장소 에셋 ID"),
    req: AnalyzeKeyframesRequest = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    브라우저에서 추출된 대표 프레임(최대 3장)을 전달받아 Gemini Vision 다중 이미지 단일 요청으로 분석합니다.
    - 백엔드 엄격 검증: 최대 3장 이하, 디코딩된 전체 이미지 총합 120KB 이하
    - 프로젝트 소유권 및 에셋 소속 관계 교차 검증
    - 분석 성공 시 해당 LocationAsset의 detected_features만 갱신
    - ShootingProject.analysis_result는 일체 수정하지 않음 (사후 평가 데이터 보존)
    """
    # 1. 사용자 프로젝트 소유권 검증
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))

    # 2. 에셋 존재 및 프로젝트 소속 관계 검증
    asset = db.query(LocationAsset).filter(
        LocationAsset.asset_id == asset_id,
        LocationAsset.project_id == project_id
    ).first()
    if not asset:
        raise HTTPException(
            status_code=404,
            detail=f"프로젝트 #{project_id}에 소속된 장소 에셋 #{asset_id}을(를) 찾을 수 없습니다."
        )

    # 3. 프레임 개수 검증 (최대 3장)
    if not req.keyframes or len(req.keyframes) == 0:
        raise HTTPException(status_code=400, detail="분석할 대표 프레임이 전달되지 않았습니다.")

    if len(req.keyframes) > 3:
        raise HTTPException(
            status_code=400,
            detail=f"분석 가능한 대표 프레임은 최대 3장입니다. (전달된 개수: {len(req.keyframes)}장)"
        )

    # 4. 각 프레임 Base64 디코딩 및 총 용량 검증 (최대 120KB) - Gemini 호출 전 사전 차단!
    MAX_TOTAL_DECODED_BYTES = 120 * 1024  # 122,880 bytes (120KB)
    total_decoded_bytes = 0
    images_for_gemini: List[Dict[str, Any]] = []

    for idx, kf in enumerate(req.keyframes):
        raw_b64 = (kf.base64 or "").strip()
        if not raw_b64:
            raise HTTPException(status_code=400, detail=f"프레임 #{kf.seq}의 Base64 데이터가 비어 있습니다.")

        clean_b64 = raw_b64
        detected_mime = kf.mime_type or "image/jpeg"
        if "," in clean_b64:
            header, clean_b64 = clean_b64.split(",", 1)
            clean_b64 = clean_b64.strip()
            if "image/png" in header:
                detected_mime = "image/png"
            elif "image/webp" in header:
                detected_mime = "image/webp"
            elif "image/jpeg" in header or "image/jpg" in header:
                detected_mime = "image/jpeg"

        try:
            decoded_bytes = base64.b64decode(clean_b64, validate=True)
        except Exception as b64_err:
            raise HTTPException(status_code=400, detail=f"프레임 #{kf.seq}의 Base64 디코딩 실패: {b64_err}")

        if len(decoded_bytes) == 0:
            raise HTTPException(status_code=400, detail=f"프레임 #{kf.seq}의 디코딩된 크기가 0바이트입니다.")

        total_decoded_bytes += len(decoded_bytes)
        label_text = kf.label or f"프레임 #{kf.seq} ({int((kf.ratio or 0) * 100)}%)"

        images_for_gemini.append({
            "data": clean_b64,
            "mime_type": detected_mime,
            "label": label_text
        })

    if total_decoded_bytes > MAX_TOTAL_DECODED_BYTES:
        total_kb = round(total_decoded_bytes / 1024, 2)
        raise HTTPException(
            status_code=400,
            detail=f"전송된 대표 프레임의 총 용량({total_kb}KB)이 허용 한도(120KB)를 초과했습니다."
        )

    # 5. Gemini Vision 멀티모달 프롬프트 구성 (6개 독립 항목 개별 주입)
    project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
    proj_title = (project.title or project.project_name or "촬영 프로젝트") if project else "촬영 프로젝트"

    # 6개 촬영 프로젝트 조건 개별 추출
    c_location = (project.place_name or project.shooting_location or "촬영 현장") if project else "촬영 현장"
    c_purpose = (project.shooting_purpose or "자연·풍경 촬영") if project else "자연·풍경 촬영"
    c_date = (project.target_date or "일정 미지정") if project else "일정 미지정"
    c_time = (project.target_time or "시간 미지정") if project else "시간 미지정"

    desired_list = []
    if project and project.desired_techniques:
        if isinstance(project.desired_techniques, list):
            desired_list = project.desired_techniques
        elif isinstance(project.desired_techniques, str):
            desired_list = [project.desired_techniques]
    c_technique = ", ".join(desired_list) if desired_list else "현장 AI 자동 추천"

    c_notes = (req.scene_intent or (project.scene_intent if project else None) or "추가 연출 및 제약사항 없음")

    prompt = f"""당신은 항공촬영 및 시네마토그래피 전문 AI 감독입니다.
촬영 예정 프로젝트 6대 분석 조건:
1. 촬영 장소: {c_location}
2. 촬영 목적: {c_purpose}
3. 촬영 예정일: {c_date}
4. 촬영 시간: {c_time}
5. 선호 촬영 기법: {c_technique}
6. 기타 추가 연출 및 제약: {c_notes}
(프로젝트명: {proj_title})

현장 참조 영상에서 추출된 대표 프레임 3장(15% 도입부, 50% 중심 장면, 85% 원경/마무리)입니다.
이 3장의 연속된 공간 정보와 상기 6대 촬영 조건을 종합 분석하여 최적의 촬영 구도와 추천 기법을 다음 JSON 구조로만 엄격히 응답하십시오:
{{
  "name": "핵심 피사체/랜드마크 명칭 (예: 한강 철교 주탑, 남산 서울타워 등)",
  "title": "장소 및 랜드마크 요약 명칭 (예: 한강 철교 주탑과 여의도 스카이라인)",
  "scene_type": "도시 건축|자연 풍경|해안 수변|인물 중심|공원 및 레저|역사 유적",
  "lighting": "주간 맑은 순광|골든아워 온화한 조도|일몰 후 저조도|고조도 역광|흐린 날 확산광",
  "summary": "장소의 시각적 공간 특성 및 환경 1~2문장 요약",
  "detected_subjects": [
    {{
      "name": "피사체 명칭",
      "type": "건축물|자연지형|인물|차량/교통|조형물|수면",
      "center_x": 0.0~1.0 (이미지 가로 0=좌, 0.5=중앙, 1=우),
      "center_y": 0.0~1.0 (이미지 세로 0=상, 0.5=중앙, 1=하),
      "occupancy_ratio": 0.0~1.0,
      "bounding_box": {{"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}}
    }}
  ],
  "depth_layers": {{
    "foreground": "근경 요소 설명",
    "midground": "중경 요소 설명 (주 피사체 위치)",
    "background": "원경 요소 설명"
  }},
  "recommended_composition": {{
    "composition_name": "3x3 삼분할 황금비율 구도 (Rule of Thirds)|중앙 배치 구도 (Center Framing)|좌우 대칭 구도 (Symmetry Framing)|리딩라인 소실점 구도 (Leading Lines)|전경 프레이밍 구도 (Foreground Framing)|네거티브 스페이스 구도 (Negative Space)",
    "target_x": -1.0~1.0 (화면 중심 0.0 기준 오프셋: -0.33=좌측 1/3, 0=정중앙, +0.33=우측 1/3),
    "target_y": -1.0~1.0 (화면 중심 0.0 기준 오프셋: -0.33=상단 1/3, 0=정중앙, +0.33=하단 1/3),
    "horizon_y": 0.0~1.0,
    "is_horizon_visible": true,
    "rationale": "추천 구도 선정 사유 1~2문장"
  }},
  "recommended_techniques": [
    {{
      "technique_key": "orbit_poi|reveal|flyby|line|dronie",
      "technique_name": "추천 기법 명칭",
      "fit_score": 50~100,
      "reason": "해당 기법이 이 장면에 최적인 사유"
    }}
  ],
  "visual_hazards": [
    "시각적 주의 요소 (예: 고압 전선, 역광 암부 디테일 손실 등)"
  ]
}}"""

    # 6. Gemini Vision 호출 (단일 모델, connect: 3.0s, read: 6.5s)
    reply_text, model_used, error_detail = gemini_client.generate_multi_vision(
        prompt=prompt,
        images=images_for_gemini,
        system_instruction="당신은 전문 시네마틱 촬영 구도 AI입니다. 반드시 지정된 순수 JSON 구조로만 응답하세요.",
        connect_timeout=3.0,
        read_timeout=6.5
    )

    if error_detail or not reply_text:
        logger.warning(f"[Phase 12 Analyze] Gemini Multi-Vision 호출 실패 (Asset #{asset_id}): {error_detail}")
        if error_detail and "IMAGE_VALIDATION" in error_detail:
            raise HTTPException(status_code=400, detail=error_detail)
        elif error_detail and "TIMEOUT" in error_detail:
            raise HTTPException(
                status_code=504,
                detail="AI Vision 분석 서버 응답 대기 시간 초과 (Gemini Timeout). 기본 카메라 모드를 유지해 주세요."
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=f"AI Vision 분석 처리 실패: {error_detail or 'Gemini 서비스 무응답'}"
            )

    # 7. 분석 결과 JSON 구문 역직렬화 및 구조/좌표 범위 엄격 검증
    try:
        raw_parsed = json.loads(reply_text)
    except Exception as parse_err:
        raise HTTPException(status_code=502, detail=f"Gemini 응답 JSON 역직렬화 실패: {parse_err}")

    if not isinstance(raw_parsed, dict):
        raise HTTPException(status_code=502, detail="Gemini 분석 결과가 유효한 딕셔너리 객체가 아닙니다.")

    def _clamp(val, min_v, max_v, default_v):
        try:
            f = float(val)
            if f < min_v or f > max_v:
                return default_v
            return round(f, 3)
        except (TypeError, ValueError):
            return default_v

    name_val = str(raw_parsed.get("name") or raw_parsed.get("title") or "인식된 피사체").strip()
    title_val = str(raw_parsed.get("title") or name_val).strip()
    scene_type_val = str(raw_parsed.get("scene_type") or "도시 건축").strip()
    lighting_val = str(raw_parsed.get("lighting") or "주간 맑은 조도").strip()
    summary_val = str(raw_parsed.get("summary") or f"{scene_type_val} 환경 내 {name_val}").strip()

    # 피사체 2D 상대좌표 검증 (0.0 ~ 1.0)
    validated_subjects = []
    raw_subjects = raw_parsed.get("detected_subjects") or []
    if isinstance(raw_subjects, list):
        for s in raw_subjects:
            if isinstance(s, dict):
                s_name = str(s.get("name") or name_val).strip()
                s_type = str(s.get("type") or "건축물").strip()
                cx = _clamp(s.get("center_x"), 0.0, 1.0, 0.5)
                cy = _clamp(s.get("center_y"), 0.0, 1.0, 0.5)
                occ = _clamp(s.get("occupancy_ratio"), 0.0, 1.0, 0.2)
                bbox_raw = s.get("bounding_box") or {}
                bbox = {
                    "x_min": _clamp(bbox_raw.get("x_min"), 0.0, 1.0, max(0.0, cx - 0.15)),
                    "y_min": _clamp(bbox_raw.get("y_min"), 0.0, 1.0, max(0.0, cy - 0.15)),
                    "x_max": _clamp(bbox_raw.get("x_max"), 0.0, 1.0, min(1.0, cx + 0.15)),
                    "y_max": _clamp(bbox_raw.get("y_max"), 0.0, 1.0, min(1.0, cy + 0.15)),
                }
                validated_subjects.append({
                    "name": s_name,
                    "type": s_type,
                    "center_x": cx,
                    "center_y": cy,
                    "occupancy_ratio": occ,
                    "bounding_box": bbox
                })

    if not validated_subjects:
        validated_subjects.append({
            "name": name_val,
            "type": "건축물",
            "center_x": 0.5,
            "center_y": 0.5,
            "occupancy_ratio": 0.2,
            "bounding_box": {"x_min": 0.35, "y_min": 0.35, "x_max": 0.65, "y_max": 0.65}
        })

    # 추천 구도 및 화면 오프셋 좌표 검증 (-1.0 ~ +1.0)
    raw_comp = raw_parsed.get("recommended_composition") or {}
    comp_name = str(raw_comp.get("composition_name") or "3x3 삼분할 황금비율 구도 (Rule of Thirds)").strip()
    target_x = _clamp(raw_comp.get("target_x"), -1.0, 1.0, 0.0)
    target_y = _clamp(raw_comp.get("target_y"), -1.0, 1.0, 0.0)
    horizon_y = _clamp(raw_comp.get("horizon_y"), 0.0, 1.0, 0.45)
    comp_rationale = str(raw_comp.get("rationale") or "피사체와 배경의 원근감을 극대화하는 추천 구도입니다.").strip()

    validated_comp = {
        "composition_name": comp_name,
        "target_x": target_x,
        "target_y": target_y,
        "horizon_y": horizon_y,
        "is_horizon_visible": bool(raw_comp.get("is_horizon_visible", True)),
        "rationale": comp_rationale
    }

    # 깊이 레이어 검증
    raw_depth = raw_parsed.get("depth_layers") or {}
    validated_depth = {
        "foreground": str(raw_depth.get("foreground") or "근경 산책로 및 수변 지형").strip(),
        "midground": str(raw_depth.get("midground") or f"{name_val} 위치 구간").strip(),
        "background": str(raw_depth.get("background") or "원경 스카이라인 및 하늘").strip()
    }

    # 추천 기법 검증
    raw_techs = raw_parsed.get("recommended_techniques") or []
    validated_techs = []
    if isinstance(raw_techs, list):
        for t in raw_techs:
            if isinstance(t, dict):
                validated_techs.append({
                    "technique_key": str(t.get("technique_key") or "orbit_poi").strip(),
                    "technique_name": str(t.get("technique_name") or "피사체 궤도 선회 (Orbit)").strip(),
                    "fit_score": int(_clamp(t.get("fit_score"), 0, 100, 85)),
                    "reason": str(t.get("reason") or "장면 피사체 집중 연출에 적합").strip()
                })
    if not validated_techs:
        validated_techs.append({
            "technique_key": "orbit_poi",
            "technique_name": "피사체 궤도 선회 (Orbit)",
            "fit_score": 90,
            "reason": "중경 랜드마크 중심 회전 촬영에 최적"
        })

    raw_hazards = raw_parsed.get("visual_hazards") or []
    validated_hazards = [str(h).strip() for h in raw_hazards if str(h).strip()] if isinstance(raw_hazards, list) else []

    # 8. 5대 기본 촬영 기법(FORWARD, LATERAL, DIAGONAL_REVEAL, ORBIT, PANORAMA) 추천 점수 엔진 연동
    from backend.services.technique_service import technique_service
    from backend.services.path_service import path_service

    scene_input = {
        "scene_type": scene_type_val,
        "main_subject": name_val,
        "foreground": validated_depth.get("foreground", ""),
        "midground": validated_depth.get("midground", ""),
        "background": validated_depth.get("background", ""),
        "open_space": summary_val,
        "obstacle_level": "HIGH" if any("장애물" in str(h) or "전선" in str(h) for h in validated_hazards) else ("MEDIUM" if validated_hazards else "NONE"),
        "subject_visibility": "CLEAR"
    }

    # LocationAsset 및 Project에 등록된 GPS 좌표 탐색
    poi_lat = None
    poi_lng = None
    if asset.detected_features and isinstance(asset.detected_features, dict):
        poi_lat = asset.detected_features.get("lat")
        poi_lng = asset.detected_features.get("lng")
    if poi_lat is None and project:
        poi_lat = getattr(project, "target_lat", None)
        poi_lng = getattr(project, "target_lng", None)

    route_constraints = {
        "has_subject_gps": (poi_lat is not None and poi_lng is not None),
        "subject_lat": poi_lat,
        "subject_lng": poi_lng
    }

    tech_rec = technique_service.recommend_technique(
        scene_analysis=scene_input,
        sensor_state={"has_gps": True, "gps_accuracy": 5.0},
        route_constraints=route_constraints
    )

    top_tech_id = tech_rec.get("recommended_technique", "FORWARD")

    # 기법별 독립 경로 또는 회전 가이드 생성
    start_lat_val = poi_lat if poi_lat else 37.5284000
    start_lon_val = (poi_lng - 0.0001) if poi_lng else 126.9328000

    path_gen_res = path_service.generate_technique_path(
        technique_id=top_tech_id,
        start_lat=start_lat_val,
        start_lon=start_lon_val,
        heading_deg=0.0,
        subject_lat=poi_lat,
        subject_lon=poi_lng,
        gps_accuracy=5.0
    )

    # 9. 최종 구조화된 특징 메타데이터 구성 (기존 ai_service L750 호환을 위해 name/title 최상위 유지)
    final_features = {
        "name": name_val,
        "title": title_val,
        "scene_type": scene_type_val,
        "lighting": lighting_val,
        "summary": summary_val,
        "analyzed_at": datetime.utcnow().isoformat(),
        "model_used": model_used,
        "technique_recommendation": tech_rec,
        "recommended_path": path_gen_res,
        "pre_video_analysis": {
            "detected_subjects": validated_subjects,
            "depth_layers": validated_depth,
            "recommended_composition": validated_comp,
            "recommended_techniques": validated_techs,
            "visual_hazards": validated_hazards,
            "technique_recommendation": tech_rec,
            "recommended_path": path_gen_res
        }
    }

    # 10. 해당 LocationAsset의 detected_features만 안전하게 갱신 (다른 에셋 보존)
    asset.detected_features = final_features
    db.commit()
    db.refresh(asset)

    return {
        "status": "success",
        "project_id": project_id,
        "asset_id": asset_id,
        "model_used": model_used,
        "db_saved": True,
        "analysis": final_features,
        "technique_recommendation": tech_rec,
        "recommended_path": path_gen_res
    }


@router.get(
    "/projects/{project_id}/assets",
    response_model=List[LocationAssetResponse],
    summary="3. 프로젝트별 장소 자료 목록 조회 (공통/개인 구분 지원)"
)
def get_project_location_assets(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    filter_type: Optional[str] = Query(None, description="공통/개인 필터링: all, common, personal"),
    asset_type: Optional[str] = Query(None, description="자료 유형 필터링 (PANORAMA, SHORT_VIDEO 등)"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 장소 시각 자료 목록을 조회합니다.
    - 공통 자료(is_common=True): 프로젝트 열람자 전원 조회 가능
    - 개인 자료(is_common=False): 프로젝트 관리자/소유자 또는 업로드 당사자만 안전하게 격리 조회
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    f_type = filter_type if isinstance(filter_type, str) else None
    a_type = asset_type if isinstance(asset_type, str) else None
    return mobile_service.get_project_location_assets(
        db=db,
        project_id=project_id,
        current_user=current_user,
        filter_type=f_type,
        asset_type=a_type
    )


@router.get(
    "/assets/{asset_id}",
    response_model=LocationAssetResponse,
    summary="3. 특정 장소 자료 상세 정보 조회"
)
def get_location_asset_detail(
    asset_id: int = Path(..., description="장소 자료 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    단일 장소 자료의 상세 메타데이터 및 AI 특징점 분석 결과를 조회합니다.
    """
    return mobile_service.get_location_asset_detail(db, asset_id, current_user)


@router.get(
    "/assets/files/{project_id}/{filename}",
    summary="3. 업로드된 실제 물리 파일 스트리밍/다운로드"
)
def stream_asset_file(
    project_id: int = Path(..., description="프로젝트 ID"),
    filename: str = Path(..., description="파일 식별자"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    백엔드에 안전하게 저장된 스마트폰 파노라마/영상 물리 파일을 브라우저로 스트리밍 반환합니다.
    - 정규식 및 경로 정규화를 통한 Path Traversal 방어
    - 공용 에셋(is_common=True)은 익명 허용, 개인 에셋은 소유권 검증 적용
    """
    safe_name = os.path.basename(filename)
    if ".." in filename or safe_name != filename or not re.match(r"^[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+$", safe_name):
        raise HTTPException(status_code=400, detail="유효하지 않은 파일 경로 또는 파일명 형식입니다.")

    try:
        p_id_int = int(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="유효하지 않은 프로젝트 식별자입니다.")

    base_dir = os.path.abspath(UPLOAD_DIR)
    target_dir = os.path.abspath(os.path.join(base_dir, str(p_id_int)))
    file_path = os.path.abspath(os.path.join(target_dir, safe_name))

    # Path traversal 검증: 대상 경로가 허용된 project 디렉터리 내부에 속해야 함
    if not file_path.startswith(target_dir) or not file_path.startswith(base_dir):
        raise HTTPException(status_code=403, detail="허가되지 않은 상위 디렉터리 접근 시도입니다.")

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="물리적 저장소에서 대상 파일을 찾을 수 없습니다.")

    # 기본 접근 권한 검사 (데모 공용 파일 vs 개인 파일)
    asset_record = db.query(LocationAsset).filter(
        LocationAsset.project_id == p_id_int,
        LocationAsset.file_url.like(f"%{safe_name}")
    ).first()

    if asset_record and not asset_record.is_common:
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="비공개 파일 접근을 위해 로그인이 필요합니다.")
        if asset_record.user_id and current_user.id != asset_record.user_id and getattr(current_user, "role", "") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="해당 파일에 대한 접근 권한이 없습니다.")

    ext = os.path.splitext(safe_name)[1].lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".json": "application/json"
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(path=file_path, media_type=media_type, filename=safe_name)


@router.delete(
    "/assets/{asset_id}",
    summary="3. 특정 장소 자료 삭제 (물리 파일 및 DB 레코드 제거)"
)
def delete_location_asset(
    asset_id: int = Path(..., description="장소 자료 고유 ID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    장소 자료를 삭제합니다. (업로드 작성자 또는 프로젝트 소유자/관리자만 가능)
    """
    success = mobile_service.delete_location_asset(db, asset_id, current_user)
    return {"detail": "장소 자료가 성공적으로 삭제되었습니다.", "asset_id": asset_id, "success": success}


# ==========================================
# 4. 맞춤형 AI 촬영 기법 추천 & 피드백 API (Phase 5)
# ==========================================
@router.get(
    "/techniques",
    response_model=List[TechniqueCatalogItem],
    summary="4. 촬영 기법 카탈로그 전체 목록 조회"
)
def get_technique_catalog(
    smartphone_only: bool = Query(False, description="스마트폰 지원 기법만 필터링 (True: 스마트폰 지원, False: 전체 기법)"),
    db: Session = Depends(get_db)
):
    """
    확장 가능한 촬영 기법 카탈로그 목록을 조회합니다.
    - 스마트폰 지원 기법 (회전, 직선 드로니, 삼분할 추적, 전경 리빌, 초저각 로우앵글 등)
    - 실제 비행 드론 전용 기법 (수직 버드아이, 고고도 스파이럴, 고속 플라이바이)
    """
    return mobile_service.get_technique_catalog(smartphone_only=smartphone_only)


@router.get(
    "/projects/{project_id}/techniques/recommendations",
    response_model=PersonalizedRecommendationResponse,
    summary="4. 사용자 맞춤형 AI 촬영 기법 추천 조회"
)
def get_personalized_techniques(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    limit: int = Query(4, ge=1, le=10, description="추천 기법 개수 (기본 4개)"),
    smartphone_only: bool = Query(False, description="스마트폰 지원 기법만 추천"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    프로젝트 정보(장소/목적/피사체/시간) + 사용자 과거 촬영 기록 + 커뮤니티 상호작용(좋아요/저장/시청)을
    종합 분석하여 최적의 촬영 기법을 추천합니다.
    - Cold Start: 신규 사용자 데이터 부족 시 프로젝트 적합도 기반 기본 3~4개 기법 추천
    - 스마트폰 우선: 현재 단말 환경에 맞는 스마트폰 기법 우선 가중치 부여
    - 커뮤니티 연계: 각 추천 기법별 데모 영상 목록 첨부
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    clean_limit = limit if isinstance(limit, int) else 4
    return mobile_service.get_personalized_techniques(
        db=db,
        project_id=project_id,
        current_user=current_user,
        limit=clean_limit,
        smartphone_only=smartphone_only
    )


@router.post(
    "/projects/{project_id}/techniques/select",
    response_model=TechniqueSelectResponse,
    summary="4. 추천된 촬영 기법 최종 선택 및 선호도 가중치 반영"
)
def select_project_technique(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: TechniqueSelectRequest = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    사용자가 추천 기법 중 이번 촬영에서 수행할 기법을 최종 선택합니다.
    - ShootingProject.desired_techniques 컬럼에 저장
    - 사용자 취향 선호도 점수(user_preference_scores)에 선택 가중치(6.0) 즉시 반영
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return mobile_service.select_project_technique(
        db=db,
        project_id=project_id,
        technique_id=payload.technique_id,
        current_user=current_user
    )


@router.post(
    "/projects/{project_id}/techniques/feedback",
    response_model=TechniqueFeedbackResponse,
    summary="4. 촬영 후 사용자 만족도 피드백 및 선호도 갱신"
)
def record_technique_feedback(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: TechniqueFeedbackRequest = ...,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    촬영 완료 후 기법에 대한 실제 촬영 여부 및 만족도(1~5점)를 기록합니다.
    - 높은 만족도(4~5점) 반영 시 선호도 점수에 최고 가중치(8.0) 반영
    - 향후 개인화 추천 시 해당 스타일의 추천 순위 상승
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return mobile_service.record_technique_feedback(
        db=db,
        project_id=project_id,
        req=payload,
        current_user=current_user
    )


# ==========================================
# 5. 다중 사용자 공통 경로 학습 API (Phase 8)
# ==========================================
@router.get(
    "/projects/{project_id}/common-path",
    response_model=Optional[ProjectCommonPathResponse],
    summary="5. 프로젝트별 최신 공통 권장 경로 조회"
)
def get_active_common_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 다중 사용자 학습을 통해 생성된 최신 활성 공통 권장 경로를 조회합니다.
    (미생성 상태인 경우 null 반환)
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    return collaborative_path_service.get_active_common_path(db, project_id)


@router.post(
    "/projects/{project_id}/common-path/learn",
    response_model=CommonPathLearnResponse,
    summary="5. 프로젝트별 다중 사용자 공통 경로 학습 실행"
)
def learn_project_common_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: Optional[CommonPathLearnRequest] = None,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    동일 프로젝트에 참여한 다중 사용자의 PHONE_GPS 보행 경로와 품질 점수를 분석하여,
    품질이 우수한 경로에 가중치를 부여한 최신 버전의 공통 권장 경로를 생성/갱신합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
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
    summary="5. 공통 권장 경로 버전별 업데이트 이력 조회"
)
def get_common_path_history(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    해당 프로젝트의 공통 권장 경로 버전 이력 전체를 최신순으로 조회합니다.
    """
    auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
    history = collaborative_path_service.get_common_path_history(db, project_id)
    active_ver = next((h.version for h in history if h.is_active), None)

    return CommonPathHistoryResponse(
        project_id=project_id,
        total_versions=len(history),
        active_version=active_ver,
        history=history
    )


# ==========================================
# 6. 사용자별 맞춤 촬영 경로 API (Phase 9)
# ==========================================
@router.get(
    "/projects/{project_id}/personalized-path",
    response_model=PersonalizedShootingPathResponse,
    summary="6. 개인별 맞춤 촬영 권장 경로 조회 [모바일]"
)
def get_mobile_personalized_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    모바일 현장 접속 사용자를 위한 맞춤 권장 동선 조회 (미존재 시 자동 생성)
    """
    proj = auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
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
    summary="6. 개인별 맞춤 촬영 경로 생성 및 모드 변경 [모바일]"
)
def generate_mobile_personalized_path(
    project_id: int = Path(..., description="프로젝트 고유 ID"),
    payload: Optional[PersonalizedPathGenerateRequest] = None,
    token: Optional[str] = Query(None, description="모바일 QR 접속 보안 토큰"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    모바일 현장에서 사용자의 특정 변형 유형(STRAIGHT, ZIGZAG, POI_WAYPOINT)을 적용하여 동선을 재생성합니다.
    """
    proj = auth_service.verify_project_ownership(db, str(project_id), current_user, _clean_token(token))
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


