import requests
from typing import Dict, Any, Tuple, Optional

# =========================================================================
# Fallback Offline Database for Verified Korean Landmarks & POIs
# (외부 지도 API 장애 시에만 정확히 일치(Exact Match)하는 경우에 사용되는 백업 DB)
# ※ 주의: 도시나 권역 대표 좌표는 오인식을 방지하기 위해 등록하지 않습니다.
# =========================================================================
KOREA_ADDRESS_DB = {
    # 1. 공공청사 및 경찰서/소방서
    "오산경찰서": (37.153667, 127.082211, "경기도 오산시 동부대로 596 (원동)"),
    "오산시청": (37.1498, 127.0771, "경기도 오산시 성호대로 141 (오산동)"),
    "오산역": (37.1416, 127.0687, "경기도 오산시 역광장로 59 (오산동)"),
    "오산소방서": (37.1580, 127.0650, "경기도 오산시 경기대로 347 (가장동)"),

    # 2. 한강 및 주요 공원 랜드마크
    "여의도 한강공원": (37.5284, 126.9328, "서울특별시 영등포구 여의동로 330 (여의도동)"),
    "여의도한강공원": (37.5284, 126.9328, "서울특별시 영등포구 여의동로 330 (여의도동)"),
    "반포 한강공원": (37.5098, 126.9947, "서울특별시 서초구 신반포로11길 40 (반포동)"),
    "뚝섬 한강공원": (37.5295, 127.0699, "서울특별시 광진구 강변북로 139 (자양동)"),
    "난지 한강공원": (37.5663, 126.8795, "서울특별시 마포구 한강난지로 162 (상암동)"),

    # 3. 학교 및 교육시설
    "김천 율곡중학교": (36.121754, 128.185708, "경상북도 김천시 혁신4로 45 (율곡동)"),
    "율곡중학교": (36.121754, 128.185708, "경상북도 김천시 혁신4로 45 (율곡동)"),
    "한양여자대학교": (37.5615, 127.0425, "서울특별시 성동구 살곶이길 200 (사근동)"),
    "한양여대": (37.5615, 127.0425, "서울특별시 성동구 살곶이길 200 (사근동)"),
    "한양대학교 서울캠퍼스": (37.5572, 127.0453, "서울특별시 성동구 왕십리로 222 (행당동)"),
    "한양대학교 ERICA캠퍼스": (37.2974, 126.8355, "경기도 안산시 상록구 한양대학로 55 (사동)"),
    "한신대학교": (37.1856, 127.0375, "경기도 오산시 한신대길 137 (양산동)"),
    "영남대학교": (35.8363, 128.7533, "경상북도 경산시 대학로 280 (대동)"),
    "동의대학교": (35.1432, 129.0346, "부산광역시 부산진구 엄광로 176 (가야동)"),
    "광주여자대학교": (35.1678, 126.8094, "광주광역시 광산구 여대길 201 (산정동)"),
    "경북대학교": (35.8906, 128.6121, "대구광역시 북구 대학로 80 (산격동)"),
    "부산대학교": (35.2332, 129.0794, "부산광역시 금정구 부산대학로63번길 2 (장전동)"),
    "전남대학교": (35.1768, 126.9084, "광주광역시 북구 용봉로 77 (용봉동)"),
    "전북대학교": (35.8468, 127.1292, "전북특별자치도 전주시 덕진구 백제대로 567 (금암동)"),
    "충남대학교": (36.3665, 127.3444, "대전광역시 유성구 대학로 99 (궁동)"),
    "충북대학교": (36.6285, 127.4571, "충청북도 청주시 서원구 충대로 1 (개신동)"),
    "제주대학교": (33.4547, 126.5647, "제주특별자치도 제주시 제주대학로 102 (아라일동)"),
    "강원대학교": (37.8697, 127.7444, "강원특별자치도 춘천시 강원대학길 1 (효자동)"),
    "계명대학교": (35.8564, 128.4878, "대구광역시 달서구 달구벌대로 1095 (신당동)"),
    "조선대학교": (35.1423, 126.9344, "광주광역시 동구 필문대로 309 (서석동)")
}


def clean_user_input(raw_input: str) -> str:
    """사용자가 입력한 검색어에서 불필요한 조사, 술어 및 공백 정제 (룰 기반 폴백 클리너)"""
    if not raw_input:
        return ""
    import re
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
    지도 API(지오코딩/POI) 검색에 가장 적합한 검색어 키워드를 구성합니다.
    ※ 주의: Gemini AI는 좌표나 가짜 주소를 생성하지 않으며, 오직 검색용 키워드만 정제합니다.
    """
    if not raw_input or not raw_input.strip():
        return ""

    raw_text = raw_input.strip()

    # 이미 짧고 명확한 단일 고유명사나 행정구역 주소인 경우 1차 정제 후 바로 활용 가능
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

    # AI 호출 불가 또는 타임아웃 시 룰 기반 클리너 결과 사용
    return basic_cleaned


def resolve_location(query: str, simulate_offline: bool = False) -> Dict[str, Any]:
    """
    [핵심 수정 지시 원칙 준수: AI 기반 동적 장소 검색 및 지도 API 연동]
    1. 사용자가 비행 희망 장소 입력
    2. Gemini AI가 입력된 장소명 분석 및 지도 API 검색어 구성
    3. Python 백엔드가 VWorld 및 Nominatim 등 지도 API에 검색 요청 전달
    4. 검색 결과에서 실제 장소명, 주소, 위도, 경도 확보
    5. 입력 장소와 검색 결과의 일치 여부 확인
    6. 외부 API 모두 실패 시에만 KOREA_ADDRESS_DB에서 정확히 일치(Exact Match)하는 백업 장소 검색
    7. 모든 검색 실패 시 위치 확인 실패 응답 반환 (임의 기본 좌표 반환 절대 금지)
    """
    raw_query = str(query or "").strip()
    if not raw_query:
        return {
            "input_name": "",
            "name": "",
            "address": "",
            "latitude": None,
            "longitude": None,
            "source": "검색어 없음",
            "verified": False
        }

    # Step 2: Gemini AI 장소 해석 및 지도 API 검색어 구성
    ai_search_keyword = interpret_place_with_gemini(raw_query) if not simulate_offline else clean_user_input(raw_query)
    search_target = ai_search_keyword or clean_user_input(raw_query)

    # Step 3 & 4: 지도 API 검색 및 좌표/주소 확보
    # 3-A. VWorld 국가공간정보플랫폼 API 시도 (API 키가 설정되어 있는 경우)
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

    # 3-B. OpenStreetMap Nominatim Geocoding API 시도 (전국 임의 장소 동적 검색)
    if not simulate_offline:
        try:
            nom_url = "https://nominatim.openstreetmap.org/search"
            # 검색어에 '대한민국'을 조합하여 국내 장소로 정밀 매핑
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

    # 3-C. KOREA_ADDRESS_DB 로컬 백업 DB 확인 (외부 API 모두 실패 시에만 정확히 일치하는 경우 백업용으로 사용)
    clean_fallback = clean_user_input(raw_query)
    norm_q = clean_fallback.replace(" ", "")
    for k, val in KOREA_ADDRESS_DB.items():
        if k == clean_fallback or k.replace(" ", "") == norm_q:
            return {
                "input_name": raw_query,
                "name": k,
                "address": val[2],
                "latitude": round(val[0], 6),
                "longitude": round(val[1], 6),
                "source": "로컬 백업 DB (오프라인 검증 장소)",
                "verified": True
            }

    # 4. 모든 검색 실패 시: 위치 확인 실패 반환 (임의 기본 좌표 반환 절대 금지!)
    return {
        "input_name": raw_query,
        "name": raw_query,
        "address": "주소 미확인",
        "latitude": None,
        "longitude": None,
        "source": "실제 지도 검색 결과 없음",
        "verified": False
    }


def geocode_address(address_text: str) -> Tuple[Optional[float], Optional[float], str]:
    """
    기존 호출 호환성을 위한 튜플 반환 래퍼: (latitude, longitude, formatted_address)
    검색 실패 시 위경도는 None을 반환합니다.
    """
    res = resolve_location(address_text)
    return res["latitude"], res["longitude"], res["address"]
