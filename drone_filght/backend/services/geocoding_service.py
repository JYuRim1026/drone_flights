import requests
import re
from typing import Dict, Any, Tuple, Optional


def clean_user_input(raw_input: str) -> str:
    """사용자가 입력한 검색어에서 불필요한 조사, 술어 및 공백 정제 (룰 기반 폴백 클리너)"""
    if not raw_input:
        return ""
    q = raw_input.strip()
    # 1. '...에서', '...로', '...부근', '...근처' 패턴
    m = re.search(r'([가-힣0-9\s]+?)(?:에서|로|부근|근처|인근|앞에서|앞)(?:\s*(?:비행|드론|날리|촬영|가능|신청|가서|띄우))?', q)
    if m:
        cand = m.group(1).strip()
        if cand and len(cand) >= 2 and not any(cand == sw for sw in ["여기", "거기", "어디", "지금", "오늘", "내일"]):
            return cand
    # 2. 질문형 어미 제거
    cleaned = re.sub(r'(드론\s*|비행\s*|날리\s*|촬영\s*)*(가능해\??|돼\??|되나\??|어때\??|할래|할게|하고\s*싶어|신청해줘|신청\s*어떻게).*$', '', q).strip()
    if cleaned and len(cleaned) >= 2:
        for suffix in ["에서", " 부근", " 인근", " 근처", " 앞"]:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
        return cleaned
    return q


def interpret_place_with_gemini(raw_input: str) -> str:
    """
    [핵심 Step 2] Gemini AI 장소 해석 엔진
    사용자가 자연어로 입력한 문장(예: '한신대학교', '오창 호수공원에서 드론 날리고 싶어')의 의미를 분석하여,
    지도 API(VWorld / 도로명주소 / OpenStreetMap) 검색에 가장 최적화된 검색어 키워드를 구성합니다.
    ※ 주의: Gemini AI는 좌표나 가짜 주소를 생성하지 않으며, 오직 검색용 키워드만 정제합니다.
    """
    if not raw_input or not raw_input.strip():
        return ""

    raw_text = raw_input.strip()
    basic_cleaned = clean_user_input(raw_text)

    try:
        from backend.external.gemini_client import gemini_client
        prompt = (
            f"사용자 입력 문장: \"{raw_text}\"\n\n"
            f"[요청 작업]\n"
            f"위 문장에서 대한민국 지도 API(VWorld / 도로명주소 / OpenStreetMap)로 장소를 검색할 때 사용할 가장 최적화된 검색어 키워드 1개만 단일 행으로 추출하십시오.\n\n"
            f"[엄격 준수 규칙]\n"
            f"1. 다른 설명, 인사말, 따옴표, 마크다운 없이 오직 정제된 장소명 검색어만 단일 행으로 출력하십시오.\n"
            f"2. 위도, 경도, 가짜 주소를 절대 생성하거나 추측하지 마십시오.\n"
            f"3. '에서', '드론 날리고 싶어', '비행 가능해?', '부근' 등 불필요한 조사와 술어는 완전히 제거하십시오.\n"
            f"4. 예시:\n"
            f"   - '한신대학교' -> '한신대학교'\n"
            f"   - '경기도 화성시 동탄호수공원에서 드론 날리고 싶어' -> '경기도 화성시 동탄호수공원'\n"
            f"   - '강원도 춘천시 의암호 비행 가능해?' -> '춘천시 의암호'\n"
            f"   - '제주도 서귀포시 천지연폭포' -> '서귀포시 천지연폭포'\n"
            f"   - '여수 오동도 앞' -> '여수 오동도'\n"
            f"   - '강릉 경포해변 부근' -> '강릉시 경포해변'\n"
            f"   - '포항 영일대해수욕장' -> '포항시 영일대해수욕장'"
        )

        res, _ = gemini_client.generate_text(
            prompt=prompt,
            system_instruction="너는 한국 지리 정보 및 장소 검색 키워드 추출 AI 엔진이다. 좌표를 생성하지 말고 지도 검색 키워드만 단일 행으로 출력한다.",
            timeout=1.2
        )
        if res and res.strip():
            candidate = res.strip().split("\n")[0].strip().replace('"', '').replace("'", "")
            if len(candidate) >= 2 and not candidate.startswith("오류") and not candidate.startswith("Error"):
                return candidate
    except Exception:
        pass

    return basic_cleaned


def resolve_location(query: str, simulate_offline: bool = False) -> Dict[str, Any]:
    """
    [동적 장소 검색 및 지도 API 연동 파이프라인]
    1. 사용자가 비행 희망 장소 입력
    2. Gemini AI가 입력된 자연어를 분석하여 지도 API 최적 검색어 구성
    3. Python 백엔드가 VWorld 및 OpenStreetMap Nominatim 지도 API에 동적 검색 요청 전달
    4. 실제 지도 검색 결과에서 장소명, 실제 주소, 위도, 경도 확보
    5. 지도 검색 실패 시: 로컬 하드코딩 DB나 가짜 좌표를 일체 반환하지 않고,
       '주소를 불러올 수 없습니다. 다시 입력해주세요' 실패 응답을 반환
    """
    raw_query = str(query or "").strip()
    if not raw_query:
        return {
            "input_name": "",
            "name": "",
            "address": "주소를 불러올 수 없습니다. 비행 희망 장소를 입력해주세요.",
            "latitude": None,
            "longitude": None,
            "source": "검색어 없음",
            "verified": False,
            "message": "장소명이 입력되지 않았습니다."
        }

    # Step 2: Gemini AI 장소 해석 및 지도 API 검색어 구성
    ai_search_keyword = interpret_place_with_gemini(raw_query) if not simulate_offline else clean_user_input(raw_query)
    search_target = ai_search_keyword or clean_user_input(raw_query)

    # Step 3 & 4: 지도 API 검색 및 좌표/주소 확보
    # 3-A. VWorld 국가공간정보플랫폼 API 시도 (API 키 설정 시)
    if not simulate_offline:
        try:
            from backend.config import settings
            vworld_key = getattr(settings, "VWORLD_API_KEY", "") or ""
            if vworld_key:
                search_url = "https://api.vworld.kr/req/search"
                s_params = {
                    "service": "search",
                    "request": "search",
                    "version": "2.0",
                    "crs": "epsg:4326",
                    "size": 1,
                    "page": 1,
                    "query": search_target,
                    "type": "place",
                    "format": "json",
                    "key": vworld_key
                }
                res = requests.get(search_url, params=s_params, timeout=2.5)
                if res.status_code == 200:
                    d = res.json()
                    items = d.get("response", {}).get("result", {}).get("items", [])
                    if items:
                        item = items[0]
                        pt = item.get("point", {})
                        lat = float(pt.get("y"))
                        lon = float(pt.get("x"))
                        title = item.get("title", search_target)
                        addr = item.get("address", {}).get("road") or item.get("address", {}).get("parcel") or title
                        return {
                            "input_name": raw_query,
                            "name": title,
                            "address": addr,
                            "latitude": round(lat, 6),
                            "longitude": round(lon, 6),
                            "source": "VWorld 국가공간정보플랫폼 API",
                            "verified": True
                        }
        except Exception:
            pass

    # 3-B. OpenStreetMap Nominatim Geocoding API 시도 (전국 전역 동적 검색)
    if not simulate_offline:
        try:
            nom_url = "https://nominatim.openstreetmap.org/search"
            q_param = search_target if "대한민국" in search_target else f"대한민국 {search_target}"
            nom_params = {
                "q": q_param,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
                "accept-language": "ko"
            }
            nom_headers = {"User-Agent": "SkyCommandDroneApp/2.0 (contact: pilot@skycommand.kr)"}
            res = requests.get(nom_url, params=nom_params, headers=nom_headers, timeout=3.5)
            if res.status_code == 200:
                list_data = res.json()
                if list_data and isinstance(list_data, list) and len(list_data) > 0:
                    item = list_data[0]
                    lat = float(item["lat"])
                    lon = float(item["lon"])
                    display_name = item.get("display_name", search_target)
                    real_name = item.get("name") or search_target
                    return {
                        "input_name": raw_query,
                        "name": real_name,
                        "address": display_name,
                        "latitude": round(lat, 6),
                        "longitude": round(lon, 6),
                        "source": "OpenStreetMap Nominatim 검색 결과",
                        "verified": True
                    }
        except Exception:
            pass

    # 4. 지도 검색 실패 시: 임의 좌표나 로컬 DB 없이 명확한 실패 및 재입력 안내 반환
    return {
        "input_name": raw_query,
        "name": raw_query,
        "address": "주소를 불러올 수 없습니다. 상세 주소나 주변 랜드마크를 포함하여 다시 입력해주세요.",
        "latitude": None,
        "longitude": None,
        "source": "위치 검색 실패",
        "verified": False,
        "message": "입력하신 장소의 위치를 확인할 수 없습니다. 구체적인 도로명 주소나 인근 건물명으로 다시 입력해 주세요."
    }


def geocode_address(address_text: str) -> Tuple[Optional[float], Optional[float], str]:
    """
    기존 호출 호환성을 위한 튜플 반환 래퍼: (latitude, longitude, formatted_address)
    검색 실패 시 위경도는 None을 반환합니다.
    """
    res = resolve_location(address_text)
    return res["latitude"], res["longitude"], res["address"]
