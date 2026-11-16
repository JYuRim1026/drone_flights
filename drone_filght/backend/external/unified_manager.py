from typing import Dict, Any, Optional, List
from backend.external.weather_client import weather_client
from backend.external.vworld_client import vworld_client
from backend.external.airspace_client import airspace_client
from backend.external.astronomy_client import astronomy_client
from backend.external.gemini_client import gemini_client
from backend.external.cache import external_cache

class ExternalDataManager:
    """
    외부 데이터 API 통합 관리자 (Facade Pattern).
    기상청, VWorld, 공역 데이터, 일출·일몰, Gemini AI 등 모든 외부 데이터의 단일 진입점.
    - 요청 및 응답 처리
    - 응답 데이터 전처리 및 단위 통일
    - 예외 처리 및 폴백 보호
    - 캐싱 관리 (TTL)
    - 종합 비행 적합도 원스톱 리포트 생성
    """

    def __init__(self):
        self.weather = weather_client
        self.vworld = vworld_client
        self.airspace = airspace_client
        self.astronomy = astronomy_client
        self.gemini = gemini_client
        self.cache = external_cache

    def get_weather(self, lat: float, lon: float, location_name: str = "서울 여의도 한강공원") -> Dict[str, Any]:
        """실시간 기상 데이터 조회 및 단위 통일 (℃, m/s, mm/h, 16방위)"""
        return self.weather.get_weather(lat, lon, location_name)

    def search_location(self, query: str) -> Dict[str, Any]:
        """VWorld 기반 공간정보/주소 검색 및 위경도 좌표 변환"""
        return self.vworld.search_location(query)

    def check_airspace(self, lat: float, lon: float, location_name: str = "서울 여의도 한강공원") -> Dict[str, Any]:
        """국토부 드론원스톱 공역 규제 및 인허가 관할 기관 조회"""
        return self.airspace.query_airspace(lat, lon, location_name)

    def get_solar_times(self, lat: float, lon: float, target_date_str: Optional[str] = None) -> Dict[str, Any]:
        """한국천문연구원 및 NOAA 표준 일출·일몰, 골든아워, 야간비행 제한 산출"""
        return self.astronomy.get_solar_schedule(lat, lon, target_date_str)

    def ask_ai_assistant(self, user_prompt: str, location_context: str = "서울 여의도 한강공원", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Gemini API 및 비행 안전 지식 엔진 기반 질의응답"""
        return self.gemini.ask_ai(user_prompt, location_context, history)

    def get_one_stop_flight_safety_report(
        self,
        location: str,
        target_date: Optional[str] = None,
        target_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [PC & 모바일 공통 핵심 모듈]
        장소, 일자, 비행 희망 시간을 바탕으로 4대 외부 데이터(위치 + 기상 + 공역 + 천문)를
        동시 통합 분석하여 단 하나의 원스톱 종합 비행 안전 진단 리포트를 생성합니다.
        (※ 좌표 미확인 시 임의 분석을 수행하지 않고 '위치 확인 필요'를 즉시 반환합니다.)
        """
        # 1. 위치 지오코딩 (VWorld / Nominatim / 로컬 백업 DB)
        loc_data = self.search_location(location)
        lat = loc_data.get("latitude")
        lon = loc_data.get("longitude")
        formatted_address = loc_data.get("formatted_address") or loc_data.get("address") or location

        # [원칙 준수] 좌표가 없으면 분석을 일체 진행하지 않는다.
        if not loc_data.get("verified") or lat is None or lon is None:
            return {
                "integrated_status": "위치 확인 필요 (UNVERIFIED)",
                "badge": "⚪",
                "overall_safety_score": None,
                "location_summary": loc_data,
                "weather_summary": {
                    "temperature": "-",
                    "wind": "-",
                    "wind_gust": "-",
                    "rain": "-",
                    "condition": "확인 필요",
                    "is_safe": False
                },
                "airspace_summary": {
                    "zone_name": "확인 필요",
                    "approval_required": None,
                    "contact_agency": "-",
                    "contact_phone": "-"
                },
                "astronomy_summary": {
                    "date": target_date or "-",
                    "sunrise": "-",
                    "sunset": "-",
                    "golden_hour_evening": "-",
                    "is_night_risk": False
                },
                "risk_violations": ["입력하신 장소의 실제 좌표를 지도에서 확인하지 못했습니다. 검증되지 않은 좌표로는 비행 적합성을 분석하지 않습니다."],
                "action_recommendations": ["정확한 도로명 주소 또는 정식 건물·공원 명칭을 입력해 주세요."],
                "cache_stats": self.cache.get_stats(),
                "flight_location": loc_data,
                "flight_analysis": {
                    "status": "위치 확인 필요 (UNVERIFIED)",
                    "score": None,
                    "summary": f"'{location}'의 실제 좌표를 확인하지 못하여 비행 적합성(공역·기상) 분석을 진행할 수 없습니다.",
                    "airspace": {"status": "좌표 미확인으로 공역 조회 불가"},
                    "weather": {"status": "좌표 미확인으로 기상청 조회 불가"},
                    "restrictions": ["정확한 좌표 없이는 비행 승인 필요 여부를 판정할 수 없습니다."],
                    "required_documents": [],
                    "recommendations": ["상세 주소나 주변 랜드마크를 추가로 입력해 주세요."]
                }
            }

        # 2. 실시간/예보 기상 분석 (기상청)
        weather_data = self.get_weather(lat, lon, location)

        # 3. 공역 규제 진단 (국토교통부 공역망)
        airspace_data = self.check_airspace(lat, lon, location)

        # 4. 태양 천문 일정 및 골든아워 (천문우주지식정보)
        solar_data = self.get_solar_times(lat, lon, target_date)

        # 5. 종합 비행 안전 종합 판정 및 점수 계산 (0~100점)
        total_score = 100
        violations = []
        recommendations = []

        # (1) 공역 평가
        if airspace_data["approval_required"]:
            total_score -= 25
            violations.append(f"공역 규제: {airspace_data['zone_name']} 구역으로 사전 비행승인이 필수적입니다.")
            recommendations.append(f"비행 전 {airspace_data['contact_agency']} ({airspace_data['contact_phone']}) 승인을 취득하세요.")
        else:
            recommendations.append("비관제 자율비행 가능 공역입니다. (고도 150m 이하)")

        # (2) 기상 평가
        if not weather_data["is_safe_to_fly"]:
            total_score -= 40
            violations.extend(weather_data["risk_factors"])
        else:
            if weather_data["risk_factors"]:
                total_score -= 15
                violations.extend(weather_data["risk_factors"])
            recommendations.append(f"풍속 {weather_data['wind_speed_ms']}m/s ({weather_data['wind_direction_text']})로 안정적인 비행이 가능합니다.")

        # (3) 시간대 야간비행 평가 (타겟 시간이 일몰 이후인지 검사)
        sunset_str = solar_data["sunset"]
        is_night = False
        if target_time:
            # e.g., "19:00", "20:00", "오후 8시"
            import re
            hour_match = re.search(r"(\d{1,2}):?(\d{2})?", target_time)
            if hour_match:
                hr = int(hour_match.group(1))
                if "오후" in target_time and hr < 12:
                    hr += 12
                # parse sunset hour
                sunset_hr = int(sunset_str.split(":")[0])
                if hr >= sunset_hr:
                    is_night = True
                    total_score -= 35
                    violations.append(f"야간비행 위반: 희망 시간({target_time})은 일몰 시각({sunset_str}) 이후입니다. (항공안전법 위반 과태료 대상)")
                    recommendations.append(f"일몰 전 골든아워 타임윈도우({solar_data['evening_golden_hour']['start']} ~ {sunset_str})로 비행 일정을 조정하십시오.")

        # 최종 등급 결정
        total_score = max(10, min(100, total_score))
        if total_score >= 80:
            final_verdict = "비행 승인 및 비행 가능 (Green)"
            verdict_badge = "🟢"
        elif total_score >= 50:
            final_verdict = "조건부 비행 승인 필요 (Yellow)"
            verdict_badge = "🟡"
        else:
            final_verdict = "비행 불가 및 일정 재조정 권고 (Red)"
            verdict_badge = "🔴"

        return {
            "integrated_status": final_verdict,
            "badge": verdict_badge,
            "overall_safety_score": total_score,
            "location_summary": {
                "input_location": location,
                "resolved_address": formatted_address,
                "latitude": lat,
                "longitude": lon,
                "geocoding_source": loc_data["source"]
            },
            "weather_summary": {
                "temperature": f"{weather_data['temperature_c']}℃",
                "wind": f"{weather_data['wind_speed_ms']}m/s ({weather_data['wind_direction_text']})",
                "wind_gust": f"{weather_data['wind_gust_ms']}m/s",
                "rain": f"{weather_data['precipitation_mm_h']}mm/h",
                "condition": weather_data["weather_condition"],
                "is_safe": weather_data["is_safe_to_fly"]
            },
            "airspace_summary": {
                "zone_name": airspace_data["zone_name"],
                "approval_required": airspace_data["approval_required"],
                "contact_agency": airspace_data["contact_agency"],
                "contact_phone": airspace_data["contact_phone"]
            },
            "astronomy_summary": {
                "date": solar_data["target_date"],
                "sunrise": solar_data["sunrise"],
                "sunset": solar_data["sunset"],
                "golden_hour_evening": f"{solar_data['evening_golden_hour']['start']} ~ {solar_data['evening_golden_hour']['end']}",
                "is_night_risk": is_night
            },
            "risk_violations": violations,
            "action_recommendations": recommendations,
            "cache_stats": self.cache.get_stats()
        }

external_manager = ExternalDataManager()
