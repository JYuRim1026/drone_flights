from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.schemas import (
    AIChatbotGroundTruthRequest,
    AIChatbotGroundTruthResponse,
    SceneImageAnalysisRequest,
    CompositionRecommendation,
    MobilePostProcessedUIResponse,
    FlightApprovalChatRequest,
    FlightApprovalChatResponse
)
from backend.services.ai_service import ai_service
from backend.services.ai_assistant import chat_with_flight_approval_assistant

router = APIRouter(prefix="/ai", tags=["AI 서비스 연동 (AI Services Integration)"])

@router.post(
    "/chatbot/ground-truth",
    response_model=AIChatbotGroundTruthResponse,
    summary="A. PC 웹 AI 챗봇 (결정론적 비행 안전 판단 Ground Truth 주입)"
)
def chat_with_ground_truth(
    req: AIChatbotGroundTruthRequest,
    db: Session = Depends(get_db)
):
    """
    1. 사용자 질문을 수신하고 장소/일정 분석
    2. 공역 규제, 기상청 풍속/강수, 일몰 천문 데이터 조회
    3. [핵심] 실제 비행 가능 여부는 Gemini의 추론에 맡기지 않고 백엔드 안전 판단 로직에서 확정
    4. Gemini API에 질문과 확정된 Ground Truth를 전달하여 신뢰도 100% 답변 생성
    """
    return ai_service.chat_with_ground_truth(req=req, db=db)


@router.post(
    "/mobile/scene-analysis",
    summary="B. 모바일 촬영 장면 분석 (프레임 전처리 및 피사체/장면 특징 추출)"
)
def analyze_scene_image(
    req: SceneImageAnalysisRequest
):
    """
    모바일 카메라 캡처 영상 프레임의 크기를 정규화하고
    밝기, 수평선 위치(Horizon Y), 중심 피사체 위치, 광원 상태를 정밀 분석합니다.
    """
    _, features = ai_service.preprocess_image(req.image_base64)
    return {
        "status": "success",
        "scene_features": features,
        "input_intent": req.scene_intent
    }


@router.post(
    "/mobile/composition-recommendation",
    response_model=CompositionRecommendation,
    summary="C. AI 촬영 구도 추천 (삼분할/대각선 구도 & 검증된 신뢰도)"
)
def recommend_composition(
    req: SceneImageAnalysisRequest
):
    """
    촬영 목적과 피사체 위치에 따른 최적 구도와 조종 방향을 제안합니다:
    - 촬영 목적(건물, 일몰, 강변)에 따른 구도 추천
    - 피사체 위치에 따른 촬영 방향 제안
    - 추천 이유 생성
    - [원칙 준수] 임의 난수가 아닌 삼분할 황금비 기하학적 정렬 오차 기반 검증된 신뢰도 반환
    """
    _, features = ai_service.preprocess_image(req.image_base64)
    return ai_service.recommend_composition(
        image_features=features,
        scene_intent=req.scene_intent or "일몰 도시 풍경 시네마틱 촬영",
        current_pitch=req.current_pitch or -15.0
    )


@router.post(
    "/mobile/pipeline",
    response_model=MobilePostProcessedUIResponse,
    summary="D. 모바일 촬영 원스톱 AI 파이프라인 (분석 ➔ 추천 ➔ 필터링 ➔ DB저장 ➔ UI변환)"
)
def process_mobile_pipeline(
    req: SceneImageAnalysisRequest,
    db: Session = Depends(get_db)
):
    """
    모바일 카메라 화면(camera.html)을 위한 원스톱 종합 처리:
    1. 프레임 추출 및 특징 분석 (B)
    2. 피사체 맞춤 구도 및 조종 방향 추천 (C)
    3. 위험 조종 명령 화이트리스트 필터링 (D)
    4. 분석 결과 DB(shooting_analyses) 저장 (D)
    5. 모바일 화면에 즉시 렌더링 가능한 데이터 형식으로 변환 (D)
    """
    return ai_service.process_mobile_scene(req=req, db=db)


@router.post(
    "/flight-approval/chat",
    response_model=FlightApprovalChatResponse,
    summary="E. AI 드론 비행 신청 도우미 대화형 처리 및 신청 정보 상태 유지"
)
def flight_approval_chat(
    req: FlightApprovalChatRequest
):
    """
    사용자와의 자연스러운 멀티턴 대화에서 7가지 비행 신청 정보를 수집/정규화하고,
    일반 질문 처리 시에도 기존에 수집된 비행 신청 정보를 유지합니다.
    """
    res = chat_with_flight_approval_assistant(
        conversation_history=req.conversation_history,
        user_query=req.user_query,
        current_application_info=req.current_application_info,
        reference_date_str=req.reference_date_str
    )
    return res

