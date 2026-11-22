import os
import json
from fastapi import APIRouter, Depends, Path, Query, UploadFile, File, Form, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from backend.database import get_db
from backend.models.models import User, ShootingProject, ShootingAnalysis
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
    NextRoundPathResponse
)
from backend.services.mobile_service import mobile_service, UPLOAD_DIR
from backend.services.ai_service import ai_service
from backend.services.auth_service import auth_service, get_current_user, get_optional_current_user

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
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    [Phase 4] 스마트폰 후면 카메라 및 센서 데이터 기반 AI 장면 분석 및 구도 추천:
    - Gemini API 멀티모달 분석 (키 미설정/실패 시 컴퓨터 비전 규칙 엔진 자동 전환)
    - 주요 피사체 탐지 (사람, 건물, 자연, 차량 등) 및 화면 내 위치/점유율
    - 배경 및 조도/수평선 특징 분석
    - 촬영 목적(orbit, dronie, thirds, landscape 등) 맞춤 구도 추천 및 보정 방향(↑↓←→, 수평) 안내
    - 분석 결과 DB(shooting_analyses) 저장 (사용자 ID 및 회차 연계)
    """
    if req.image_base64:
        return ai_service.analyze_scene_and_recommend(
            image_base64=req.image_base64,
            scene_intent=req.scene_intent,
            purpose=req.purpose or "orbit",
            current_pitch=req.current_pitch or -15.0,
            current_roll=req.current_roll or 0.0,
            current_heading=req.current_heading,
            project_id=req.project_id or 1,
            shooting_number=req.shooting_number or 1,
            current_user=current_user,
            save_to_db=req.save_result if req.save_result is not None else True,
            db=db
        )
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
    res = mobile_service.get_next_round_path_recommendation(db, project_id)
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
    db: Session = Depends(get_db)
):
    """
    백엔드에 안전하게 저장된 스마트폰 파노라마/영상 물리 파일을 브라우저로 스트리밍 반환합니다.
    """
    safe_name = os.path.basename(filename)
    if ".." in filename or safe_name != filename:
        raise HTTPException(status_code=400, detail="유효하지 않은 파일 경로입니다.")

    file_path = os.path.join(UPLOAD_DIR, str(project_id), safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="물리적 저장소에서 대상 파일을 찾을 수 없습니다.")

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

