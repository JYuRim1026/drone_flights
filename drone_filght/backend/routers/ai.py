from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.schemas import (
    AIChatbotGroundTruthRequest,
    AIChatbotGroundTruthResponse,
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

