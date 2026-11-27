from typing import Dict, Any, Optional
from backend.config import settings
from backend.external.cache import external_cache


class VWorldClient:
    """
    국가공간정보플랫폼(VWorld) 및 통합 지오코딩 클라이언트.
    1. VWorld API
    2. Nominatim API
    3. KOREA_ADDRESS_DB (오프라인 완전일치 백업)
    순서로 조회하며, 실패 시 임의 좌표 없이 verified=False를 반환합니다.
    """

    @classmethod
    def search_location(cls, query: str, simulate_offline: bool = False) -> Dict[str, Any]:
        """
        자연어 주소/장소명을 실제 위경도 좌표 및 표준 주소로 변환합니다.
        좌표 미확인 시 latitude=None, longitude=None, verified=False를 반환합니다.
        """
        clean_query = str(query or "").strip()
        if not clean_query:
            return {
                "input_name": "",
                "name": "",
                "address": "주소 미입력",
                "formatted_address": "주소 미입력",
                "road_address": "",
                "jibun_address": "",
                "latitude": None,
                "longitude": None,
                "source": "검색어 없음",
                "verified": False,
                "is_valid": False,
                "cached": False
            }

        cache_key = f"geo:{clean_query}"
        cached = external_cache.get(cache_key)
        if cached and not simulate_offline:
            cached_copy = dict(cached)
            cached_copy["cached"] = True
            return cached_copy

        # 정밀 위치 해석 파이프라인 호출
        from backend.services.geocoding_service import resolve_location
        res = resolve_location(clean_query, simulate_offline=simulate_offline)

        addr_str = res.get("address") or clean_query
        lat = res.get("latitude")
        lon = res.get("longitude")
        verified = bool(res.get("verified") and lat is not None and lon is not None)

        result = {
            "input_name": clean_query,
            "name": res.get("name") or clean_query,
            "address": addr_str,
            "formatted_address": addr_str,
            "road_address": addr_str,
            "jibun_address": addr_str,
            "latitude": lat,
            "longitude": lon,
            "source": res.get("source", "위치 검색"),
            "verified": verified,
            "is_valid": verified,
            "cached": False
        }

        # 유효한 좌표만 캐시에 저장
        if verified and not simulate_offline:
            external_cache.set(cache_key, result, ttl=settings.CACHE_DEFAULT_TTL_GEOCODING)

        return result


vworld_client = VWorldClient()
