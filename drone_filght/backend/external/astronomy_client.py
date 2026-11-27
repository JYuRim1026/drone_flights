from datetime import date, datetime
from typing import Dict, Any, Optional
from backend.config import settings
from backend.external.cache import external_cache

class AstronomyClient:
    """
    한국천문연구원(KASI) 및 NOAA 표준 천문 태양 궤적 계산 클라이언트.
    일출, 일몰, 모닝/이브닝 골든아워, 블루아워, 야간비행 금지 타임윈도우 계산 및 캐싱(24시간 TTL).
    """

    @classmethod
    def get_solar_schedule(cls, lat: float, lon: float, target_date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        위경도 좌표(lat, lon) 및 날짜 기반 일출/일몰 및 골든아워 산출.
        """
        t_date = date.today()
        if target_date_str:
            try:
                # support YYYY-MM-DD or YYYY.MM.DD
                clean_d = target_date_str.replace(".", "-").replace("/", "-")
                t_date = datetime.strptime(clean_d[:10], "%Y-%m-%d").date()
            except Exception:
                t_date = date.today()

        cache_key = f"astro:{round(lat, 3)}:{round(lon, 3)}:{t_date.isoformat()}"
        cached = external_cache.get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

        from backend.services.cinematography_service import calculate_sun_times
        sun_data = calculate_sun_times(lat, lon, t_date)
        sunrise_str = sun_data.get("sunrise_str", "06:40")
        sunset_str = sun_data.get("sunset_str", "17:45")
        m_gh_start = sun_data.get("morning_golden_start_str", "06:30")
        m_gh_end = sun_data.get("morning_golden_end_str", "07:15")
        e_gh_start = sun_data.get("evening_golden_start_str", "17:05")
        e_gh_end = sun_data.get("evening_golden_end_str", "17:45")
        blue_start = sun_data.get("blue_hour_evening_start_str", "17:45")
        blue_end = sun_data.get("blue_hour_evening_end_str", "18:05")

        # 야간비행 금지 법령 경고 및 안전 타임윈도우 계산
        # 일몰 10분 전까지는 반드시 착륙 완료 권장
        legal_notice = (
            f"항공안전법 제129조(조종자 준수사항): 일몰 후({sunset_str})부터 일출 전({sunrise_str})까지의 "
            f"야간 비행은 원칙적으로 엄격히 금지됩니다. (특별승인 미취득 시 과태료 최대 300만원)"
        )
        safe_flight_window = f"{e_gh_start} ~ {sunset_str} (일몰 직전 착륙 필수)"

        result = {
            "source": "한국천문연구원(KASI) / NOAA 표준 태양 궤적 천문 엔진",
            "cached": False,
            "target_date": t_date.isoformat(),
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "morning_golden_hour": {
                "start": m_gh_start,
                "end": m_gh_end,
                "description": "은은하고 부드러운 아침 햇살과 긴 그림자 연출"
            },
            "evening_golden_hour": {
                "start": e_gh_start,
                "end": e_gh_end,
                "description": "붉은 석양과 따뜻한 색감의 시네마틱 골든타임"
            },
            "blue_hour": {
                "start": blue_start,
                "end": blue_end,
                "description": "하늘이 짙은 푸른빛으로 물드는 도심 야경 전환 시점"
            },
            "night_flight_restriction": {
                "sunset_cutoff": sunset_str,
                "legal_notice": legal_notice,
                "safe_flight_window": safe_flight_window,
                "is_night_flight_warning": True
            }
        }

        # 24시간 캐싱
        external_cache.set(cache_key, result, ttl=settings.CACHE_DEFAULT_TTL_ASTRONOMY)
        return result

astronomy_client = AstronomyClient()
