from fastapi import APIRouter, Depends, Query, Path, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from backend.database import get_db
from backend.models.models import User
from backend.services.auth_service import get_optional_current_user
from backend.services.case_study_service import case_study_service
from backend.schemas.schemas import (
    ShootingCaseStudyCreate,
    ShootingCaseStudyResponse,
    ShootingCaseStudyVerifyRequest,
    CaseStudyFrameCreate,
    CaseStudyFrameResponse,
    YouTubeAnalyzeRequest,
    YouTubeApproveRequest,
    YouTubeRejectRequest
)

router = APIRouter(prefix="/case-studies", tags=["Shooting Case Studies"])


@router.post(
    "",
    response_model=ShootingCaseStudyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="신규 촬영 사례 등록"
)
def create_case_study(
    req: ShootingCaseStudyCreate,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    자체 촬영(SELF_FILMED), 외부 레퍼런스(YOUTUBE_REF), 커뮤니티(COMMUNITY_FEED) 촬영 사례를 등록합니다.
    - YOUTUBE_REF인 경우 Ground Truth 원칙에 따라 path_id=None, has_actual_gps=False가 강제됩니다.
    - 유효한 ShootingPath(PHONE_GPS/DRONE_GPS)가 연결된 경우에만 has_actual_gps=True가 확정됩니다.
    """
    return case_study_service.create_case_study(db=db, req=req, current_user=current_user)


@router.get(
    "",
    response_model=List[ShootingCaseStudyResponse],
    summary="촬영 사례 목록 조회"
)
def list_case_studies(
    source_type: Optional[str] = Query(None, description="출처 유형 필터 (SELF_FILMED, YOUTUBE_REF, COMMUNITY_FEED)"),
    has_actual_gps: Optional[bool] = Query(None, description="실제 GPS 궤적 보유 여부 필터"),
    verification_status: Optional[str] = Query(None, description="검증 상태 필터 (UNVERIFIED, HUMAN_VERIFIED, REJECTED)"),
    gps_quality_status: Optional[str] = Query(None, description="GPS 품질 상태 필터 (EXCELLENT, ACCEPTABLE, POOR, UNUSABLE)"),
    is_path_usable: Optional[bool] = Query(None, description="경로 생성 투입 가능 여부 필터"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    조건에 맞는 촬영 사례 목록을 조회합니다.
    """
    return case_study_service.get_case_studies(
        db=db,
        source_type=source_type,
        has_actual_gps=has_actual_gps,
        verification_status=verification_status,
        gps_quality_status=gps_quality_status,
        is_path_usable=is_path_usable,
        limit=limit,
        offset=offset
    )


@router.get(
    "/{case_id}",
    response_model=ShootingCaseStudyResponse,
    summary="촬영 사례 단건 상세 조회"
)
def get_case_study_detail(
    case_id: int = Path(..., description="사례 ID"),
    db: Session = Depends(get_db)
):
    """
    촬영 사례 상세 정보 및 연결된 모든 키프레임 분석 결과를 반환합니다.
    """
    return case_study_service.get_case_study_by_id(db=db, case_id=case_id)


@router.post(
    "/{case_id}/frames",
    response_model=List[CaseStudyFrameResponse],
    status_code=status.HTTP_201_CREATED,
    summary="촬영 사례 키프레임 및 AI 분석 일괄 등록"
)
def add_case_study_frames(
    case_id: int = Path(..., description="사례 ID"),
    frames: List[CaseStudyFrameCreate] = ...,
    db: Session = Depends(get_db)
):
    """
    영상에서 추출된 키프레임(BBox, 깊이 레이어, 구도, 추정 기법, 라벨 기법)을 일괄 등록합니다.
    """
    return case_study_service.add_frames_to_case_study(db=db, case_id=case_id, frames_data=frames)


@router.patch(
    "/{case_id}/verify",
    response_model=ShootingCaseStudyResponse,
    summary="촬영 사례 사람 육안 검증 및 확정"
)
def verify_case_study(
    case_id: int = Path(..., description="사례 ID"),
    req: ShootingCaseStudyVerifyRequest = ...,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    사람(조종사/관리자)이 AI 추정 결과와 영상을 비교 검증하여 대표 기법(verified_technique)을 확정하고,
    verification_audit에 트랜잭션 단위로 이력을 누적합니다. (declared_technique는 보존)
    """
    return case_study_service.verify_case_study(db=db, case_id=case_id, req=req, current_user=current_user)


@router.post(
    "/{case_id}/sync-gps",
    summary="촬영 사례 영상-GPS 다차원 품질 평가 및 시간 동기화 판정"
)
def evaluate_gps_time_sync(
    case_id: int = Path(..., description="사례 ID"),
    gps_points: Optional[List[Dict[str, Any]]] = None,
    tolerance_sec: float = Query(1.5, description="동기화 허용 오차(초)"),
    db: Session = Depends(get_db)
):
    """
    연결된 ShootingPath 또는 전달된 GPS 시계열 로그를 분석하여,
    유효 정확도 비율, P75, 최대 오차, 시간 동기화율을 종합 평가하고
    gps_quality_status(EXCELLENT/ACCEPTABLE/POOR/UNUSABLE) 및 is_path_usable을 갱신합니다.
    """
    return case_study_service.evaluate_gps_quality_and_sync(
        db=db,
        case_id=case_id,
        gps_points=gps_points,
        tolerance_sec=tolerance_sec
    )


# =========================================================================
# Phase A-3: YouTube 기반 촬영 사례 분석 및 사용자 검증·DB 적재 엔드포인트
# =========================================================================

@router.post(
    "/youtube/analyze",
    summary="YouTube 영상 URL 기반 Gemini Vision 분석 및 임시 초안 생성",
    status_code=status.HTTP_200_OK
)
def analyze_youtube_case(
    req: YouTubeAnalyzeRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    1. YouTube URL 검증 및 메타데이터 확보
    2. 프레임 확보 가능 여부 확인 (프레임 미제공 시 ANALYSIS_UNAVAILABLE 반환)
    3. 15%, 50%, 85% 프레임 Aspect Fit 640x360 압축 및 저장
    4. GeminiClient.generate_multi_vision() 다중 프레임 비전 분석
    5. 사용자 검증 전 임시 초안(REVIEW_PENDING) 상태로 저장 및 미리보기 DTO 반환
    """
    return case_study_service.analyze_youtube_case(db=db, req=req, current_user=current_user)


@router.post(
    "/youtube/{case_id}/approve",
    response_model=ShootingCaseStudyResponse,
    summary="사용자 검증 결과 승인 및 확정 DB 저장",
    status_code=status.HTTP_200_OK
)
def approve_youtube_case(
    case_id: int = Path(..., description="임시 초안 사례 ID"),
    req: YouTubeApproveRequest = ...,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    사용자가 AI 분석 결과를 확인하고 수정한 최종 기법과 구도를 확정하여
    verification_status='HUMAN_VERIFIED'로 저장하고 검증 감사 이력을 누적합니다.
    - Ground Truth 보장: has_actual_gps=False, path_id=None, is_path_usable=False 유지
    """
    return case_study_service.approve_youtube_case(db=db, case_id=case_id, req=req, current_user=current_user)


@router.post(
    "/youtube/{case_id}/reject",
    response_model=ShootingCaseStudyResponse,
    summary="사용자 사례 저장 거부 (Reject)",
    status_code=status.HTTP_200_OK
)
def reject_youtube_case(
    case_id: int = Path(..., description="임시 초안 사례 ID"),
    req: YouTubeRejectRequest = ...,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    사용자가 AI 분석 결과의 저장을 거부할 경우 verification_status='REJECTED'로 처리하며,
    확정된 촬영 사례로 승격되지 않습니다.
    """
    return case_study_service.reject_youtube_case(db=db, case_id=case_id, req=req, current_user=current_user)


@router.get(
    "/compositions/search",
    summary="향후 실시간 AI 구도 추천을 위한 검증 완료 사례 검색",
    status_code=status.HTTP_200_OK
)
def search_compositions(
    scene_type: Optional[str] = Query(None, description="장면 유형 필터 (자연, 도시, 수변, 해변 등)"),
    composition_type: Optional[str] = Query(None, description="구도 유형 필터 (삼분할, 중앙 집중 등)"),
    technique: Optional[str] = Query(None, description="촬영 기법 필터 (FORWARD, LATERAL, DIAGONAL_REVEAL, ORBIT, PANORAMA, UNKNOWN)"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="최소 AI 신뢰도"),
    limit: int = Query(20, ge=1, le=100, description="최대 조회 개수"),
    db: Session = Depends(get_db)
):
    """
    인간 검증이 완료된 고품질 시각적 촬영 프레임(BBox, 깊이 레이어, 구도, 기법)을 검색하여
    향후 실시간 카메라 뷰파인더 구도 추천의 레퍼런스로 활용합니다.
    """
    return case_study_service.search_compositions(
        db=db,
        scene_type=scene_type,
        composition_type=composition_type,
        technique=technique,
        min_confidence=min_confidence,
        limit=limit
    )

