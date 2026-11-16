from typing import Dict, Any
from backend.config import settings
from backend.external.cache import external_cache
try:
    from backend.services.airspace_service import check_airspace
except ImportError:
    try:
        from services.airspace_service import check_airspace
    except ImportError:
        from airspace_service import check_airspace

class AirspaceClient:
    """
    국토교통부 드론원스톱 및 항공안전고시 공역 규제 통합 클라이언트.
    비행금지구역(P), 비행제한구역(R), 관제권(CTR), 고도 제한, 인허가 기관 정보 표준화 및 캐싱(1시간 TTL).
    """

    @classmethod
    def query_airspace(cls, lat: float, lon: float, location_name: str = "서울 여의도 한강공원") -> Dict[str, Any]:
        """
        위경도 좌표(lat, lon) 기반 공역 진단 및 원스톱 승인 필요 요부 판정.
        """
        cache_key = f"airspace:{round(lat, 3)}:{round(lon, 3)}"
        cached = external_cache.get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

        # 공식 공역 데이터베이스 진단
        raw_info = check_airspace(lat, lon, location_name)
        zone_name = raw_info.get("zone_name", "비관제 일반공역 (G공역)")
        approval_required = raw_info.get("approval_required", False)
        matched_zones = raw_info.get("matched_zones", [])
        
        # 안전 점수 및 상태 계산
        safety_score = 95
        badge_color = "#059669"
        permission_state = "자유 비행 가능 (고도 150m 이하 승인 면제)"
        zone_type = "FREE"
        
        if "비관제" in zone_name or "면제" in zone_name:
            safety_score = 95
            badge_color = "#059669"
            permission_state = "자유 비행 가능 (고도 150m 이하 승인 면제)"
            approval_required = False
            zone_type = "FREE"
        elif "금지" in zone_name or "P-73" in zone_name or "P-61" in zone_name or "P-62" in zone_name:
            safety_score = 25
            badge_color = "#dc2626"
            permission_state = "비행 금지 구역 (원칙적 비행 불가, 특별 인가 필요)"
            approval_required = True
            zone_type = "PROHIBITED"
        elif "관제" in zone_name or "CTR" in zone_name:
            safety_score = 75
            badge_color = "#d97706"
            permission_state = "공항 관제권 (지방항공청 사전 비행승인 필수)"
            approval_required = True
            zone_type = "CTR"
        elif "제한" in zone_name or "R-75" in zone_name or "R" in zone_name:
            safety_score = 50
            badge_color = "#ea580c"
            permission_state = "비행 제한 구역 (비행승인 필수)"
            approval_required = True
            zone_type = "RESTRICTED"

        # 기관 연락처 매핑
        primary_agency = "서울지방항공청 항공운항과"
        primary_phone = "032-740-2114"
        if matched_zones:
            primary_agency = matched_zones[0].get("authority", primary_agency)
            primary_phone = matched_zones[0].get("flight_contact", primary_phone)
        elif "부산" in str(raw_info.get("official_contacts", {})):
            primary_agency = "부산지방항공청 항공안전과"
            primary_phone = "051-974-2144"

        print(f"📡 [AirspaceClient] Location: {location_name}, Coords: ({lat}, {lon}), Zone: {zone_name}, Type: {zone_type}, ApprovalReq: {approval_required}, MaxAlt: 150m AGL, Source: 국토교통부 드론원스톱 공역 정보망")

        result = {
            "source": "국토교통부 드론원스톱 공역 정보망 (Aviation Safety Regulation)",
            "cached": False,
            "query_location": location_name,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "zone_name": zone_name,
            "zone_type": zone_type,
            "approval_required": approval_required,
            "max_altitude_limit_m": 150,
            "safety_score": safety_score,
            "badge_color": badge_color,
            "permission_state": permission_state,
            "contact_agency": primary_agency,
            "contact_phone": primary_phone,
            "flight_permission_guide": "드론원스톱 민원포털(drone.onestop.go.kr)에서 비행 예정일 최소 3~7일 전 신청 필요",
            "shooting_permission_guide": "국가 보안시설(군부대, 공항, 원전 등) 포함 시 국방부 촬영허가 별도 신청 필요",
            "matched_zones_count": len(matched_zones),
            "matched_zones": matched_zones
        }

        # 1시간 캐싱
        external_cache.set(cache_key, result, ttl=settings.CACHE_DEFAULT_TTL_AIRSPACE)
        return result

airspace_client = AirspaceClient()
