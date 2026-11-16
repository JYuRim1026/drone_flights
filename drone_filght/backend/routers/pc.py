from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.database import get_db
from backend.schemas.schemas import (
    FlightRequestCreate,
    FlightRequestResponse,
    AirspaceZoneResponse,
    ChatbotRequest,
    ChatbotResponse
)
from backend.services.pc_service import pc_service

router = APIRouter(prefix="/pc", tags=["PC API (A, B, E Data)"])

@router.get("/flights", response_model=List[FlightRequestResponse], summary="비행 신청 정보 목록 조회 [A 영역]")
@router.get("/flight", response_model=List[FlightRequestResponse], summary="비행 신청 정보 목록 조회 (단수형 별칭) [A 영역]")
def get_flights(db: Session = Depends(get_db)):
    """
    PC 웹에서 작성된 비행 승인 신청 정보 목록을 조회합니다.
    """
    return pc_service.get_all_flights(db)


@router.post("/flights", response_model=FlightRequestResponse, summary="비행 신청 정보 등록 [A 영역]")
@router.post("/flight", response_model=FlightRequestResponse, summary="비행 신청 정보 등록 (단수형 별칭) [A 영역]")
def create_flight(flight_in: FlightRequestCreate, db: Session = Depends(get_db)):
    """
    드론원스톱 7가지 필수 정보(장소, 일정, 시간, 중량, 카메라, 목적, 고도)를 기반으로 비행 신청서를 등록합니다.
    """
    return pc_service.create_flight(db, flight_in)


@router.get("/airspace", response_model=AirspaceZoneResponse, summary="공역 정보 조회 [B 영역]")
def get_airspace(
    location: str = Query("서울 여의도 한강공원", description="비행 예정 장소"),
    lat: Optional[float] = Query(None, description="위도"),
    lon: Optional[float] = Query(None, description="경도")
):
    """
    좌표 및 장소를 기반으로 P-73 비행금지구역, 관제권(CTR), 비행제한구역 및 승인 요부를 진단합니다.
    """
    return pc_service.query_airspace(location, lat, lon)


@router.post("/chatbot", response_model=ChatbotResponse, summary="비행 관련 AI 챗봇 질문 [A, B, E 영역]")
def chat_with_bot(chat_in: ChatbotRequest):
    """
    Google Gemini AI 및 비행 법률/안전 규칙 엔진을 통해 사용자의 자연어 비행 질의에 실시간 답변합니다.
    """
    reply = pc_service.chat_with_ai(chat_in.prompt, chat_in.location or "서울 여의도 한강공원")
    return ChatbotResponse(reply=reply, matched_data={"location": chat_in.location})
