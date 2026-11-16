from fastapi import APIRouter, Query, Body
from typing import Optional
from backend.schemas.schemas import (
    FlightSafetyEvaluationRequest,
    FlightSafetyEvaluationResponse
)
from backend.services.safety_engine import flight_safety_engine

router = APIRouter(prefix="/safety", tags=["드론 비행 안전 판단 로직 (Flight Safety Evaluation)"])

@router.post(
    "/evaluate",
    response_model=FlightSafetyEvaluationResponse,
    summary="드론 비행 안전 종합 사전 검토 및 3단계 판정 (적합 / 주의 필요 / 비행 불가)"
)
def evaluate_flight_safety(
    req: FlightSafetyEvaluationRequest
):
    """
    [6단계 드론 비행 안전 판단 엔진 핵심]
    위치, 공역(P-73/관제권), 예정 고도(150m 법정 한도), 기상(풍속/강수), 시간(일몰/야간비행),
    기체 제원(중량/카메라/자격증)을 6단계로 종합 분석하여:
    - 🟢 적합 (FIT)
    - 🟡 주의 필요 (CAUTION)
    - 🔴 비행 불가 (PROHIBITED)
    3단계 판정 및 안전 점수(0~100점), 필수 체크리스트를 도출합니다.
    (※ 법적 공식 승인 여부와 명확히 구분되는 '사전 안전 검토' 결과 고지 포함)
    """
    return flight_safety_engine.evaluate_flight_safety(req)


@router.get(
    "/quick-check",
    response_model=FlightSafetyEvaluationResponse,
    summary="빠른 URL 쿼리 파라미터 비행 안전 진단"
)
def quick_check_safety(
    location: str = Query(..., description="비행 예정 장소 (필수)"),
    altitude_m: Optional[float] = Query(default=120.0, description="예정 비행 고도 (미터)"),
    target_date: Optional[str] = Query(default=None, description="비행 희망 일자 (YYYY-MM-DD)"),
    target_time: Optional[str] = Query(default=None, description="비행 희망 시간대 (예: 16:00, 19:30)"),
    drone_weight_g: Optional[int] = Query(default=249, description="기체 중량 (그램, 250g 이하 4종 자격)"),
    has_camera: Optional[bool] = Query(default=True, description="카메라 탑재 여부")
):
    """
    간단한 GET 요청 쿼리로 비행 안전 사전 검토 결과를 빠르게 진단합니다.
    """
    date_val = target_date if isinstance(target_date, str) else None
    time_val = target_time if isinstance(target_time, str) else None
    req = FlightSafetyEvaluationRequest(
        location=location.strip() if isinstance(location, str) else "",
        altitude_m=float(altitude_m) if isinstance(altitude_m, (int, float)) else 120.0,
        target_date=date_val,
        target_time=time_val,
        drone_weight_g=int(drone_weight_g) if isinstance(drone_weight_g, (int, float)) else 249,
        has_camera=bool(has_camera)
    )
    return flight_safety_engine.evaluate_flight_safety(req)
