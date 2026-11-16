from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.external import external_manager, WeatherAPIError
from backend.schemas.schemas import ChatbotRequest

router = APIRouter(prefix="/external", tags=["외부 데이터 통합 API (External Integration)"])

@router.get("/weather", summary="1. 기상청(KMA) VilageFcstInfoService_2.0 실시간 날씨 및 단위 통일 조회")
def get_weather(
    lat: float = Query(37.5284, description="위도"),
    lon: float = Query(126.9328, description="경도"),
    location: str = Query("서울 여의도 한강공원", description="비행 장소명")
):
    """
    기상청 단기예보 조회서비스 2.0(초단기실황·초단기예보·단기예보)을 바탕으로
    기온(℃), 풍속(m/s), 16방위 풍향, 강수량(mm/h), 습도(%), 시정(km), 비행 안전 적합도를 반환합니다.
    """
    try:
        return external_manager.get_weather(lat, lon, location)
    except WeatherAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/vworld/search", summary="2. VWorld 공간정보 & 주소-좌표 변환 (지오코딩)")
def search_location(
    query: str = Query(..., description="검색할 주소 또는 장소명 (필수)")
):
    """
    국토교통부 VWorld 공간정보 플랫폼 및 한국 정밀 랜드마크 DB를 통해
    자연어 주소를 위경도(EPSG:4326) 좌표와 표준 도로명/지번 주소로 변환합니다.
    """
    return external_manager.search_location(query)


@router.get("/airspace", summary="3. 국토교통부 드론원스톱 공역 규제 및 안전 진단")
def check_airspace(
    lat: float = Query(37.5284, description="위도"),
    lon: float = Query(126.9328, description="경도"),
    location: str = Query("서울 여의도 한강공원", description="비행 장소명")
):
    """
    비행금지구역(P-73 등), 공항 관제권(CTR), 비행제한구역(R), 고도 제한(150m)을 판정하고
    관할 지방항공청 및 군부대 인허가 연락처와 안전 점수를 반환합니다.
    """
    return external_manager.check_airspace(lat, lon, location)


@router.get("/astronomy", summary="4. 천문우주지식정보(KASI) / NOAA 일출·일몰 & 골든아워")
def get_astronomy(
    lat: float = Query(37.5284, description="위도"),
    lon: float = Query(126.9328, description="경도"),
    target_date: Optional[str] = Query(None, description="비행 예정 일자 (YYYY-MM-DD)")
):
    """
    일출·일몰 시각, 시네마틱 모닝/이브닝 골든아워 타임윈도우 및
    항공안전법상 일몰 후 야간비행 금지 규정 준수 여부를 산출합니다.
    """
    return external_manager.get_solar_times(lat, lon, target_date)


@router.post("/ai/chat", summary="5. Google Gemini AI & 비행 안전 지식 질의응답")
def ask_gemini_ai(
    chat_in: ChatbotRequest
):
    """
    자연어로 질문한 드론 항공법규, 비행 신청 방법, 기종별 조종 팁에 대해
    Google Gemini REST API 및 전문가 규칙 엔진을 통해 안전 가이드를 제공합니다.
    """
    return external_manager.ask_ai_assistant(
        user_prompt=chat_in.prompt,
        location_context=chat_in.location or "서울 여의도 한강공원"
    )


@router.get("/safety-report", summary="⭐ 4대 외부 데이터 통합 원스톱 비행 안전 종합 리포트")
def get_safety_report(
    location: str = Query(..., description="비행 예정 장소 (필수)"),
    target_date: Optional[str] = Query(None, description="비행 희망 일자 (YYYY-MM-DD)"),
    target_time: Optional[str] = Query(None, description="비행 희망 시간 (예: 17:00, 19:30)")
):
    """
    [PC 웹 & 모바일 웹 공통 연동 핵심]
    위치(VWorld) + 기상(기상청) + 공역(드론원스톱) + 태양(천문정보) 4대 외부 데이터를
    단일 호출로 동시 통합 분석하여 비행 가능 여부, 안전 점수(0~100점), 위반 사항 및
    조치 가이드를 담은 종합 리포트를 즉시 반환합니다.
    """
    try:
        return external_manager.get_one_stop_flight_safety_report(location, target_date, target_time)
    except WeatherAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/cache/stats", summary="외부 API 인메모리 캐시 적중률 및 성능 통계")
def get_cache_stats():
    """
    외부 API 호출 최적화를 위한 인메모리 TTL 캐시의 저장 항목 수,
    캐시 적중 수(Hits), 실패 수(Misses), 적중률(%)을 조회합니다.
    """
    return external_manager.cache.get_stats()
