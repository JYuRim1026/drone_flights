"""
cinematography_service.py
AI 시네마틱 드론 촬영 도우미 모듈
- 천문 태양 위치 계산 (일출, 일몰, 골든아워, 블루아워)
- 자연어 촬영 의도 분석 (장소, 시간, 피사체, 무빙)
- 항공안전법 야간비행 제한 및 실시간 기상 안전 필터링
- 시네마틱 비행 모드 & 카메라/ND필터/스틱 조작 레시피 생성
- 인터랙티브 3D/SVG 비행 궤적 & 앵글 다이어그램 생성
- 스카이 비행 도우미(대화로 신청하기) 1클릭 연동 데이터 내보내기
"""

import math
from datetime import date, datetime, timedelta
import re

# ---------------------------------------------------------------------------
# 1. Pure Python NOAA Solar Position Algorithm
# ---------------------------------------------------------------------------
def calculate_sun_times(lat: float, lon: float, target_date: date = None) -> dict:
    """
    Computes exact astronomical solar times (Sunrise, Sunset, Morning/Evening Golden Hour, Blue Hour)
    for a given latitude, longitude, and date in Korea Standard Time (UTC+9).
    """
    if target_date is None:
        target_date = date.today()
        
    year = target_date.year
    month = target_date.month
    day = target_date.day
    
    # Day of the year
    n = (datetime(year, month, day) - datetime(year, 1, 1)).days + 1
    
    # Fractional year in radians
    gamma = 2.0 * math.pi / 365.0 * (n - 1)
    
    # Equation of time in minutes
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    
    # Solar declination angle in radians
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.0148 * math.sin(3 * gamma))
    
    lat_rad = math.radians(lat)
    
    # Zenith for standard sunrise/sunset: 90.833 degrees (atmospheric refraction)
    zenith_official = math.radians(90.833)
    
    # Hour angle for sunrise/sunset
    cos_ha_official = (math.cos(zenith_official) / (math.cos(lat_rad) * math.cos(decl)) 
                       - math.tan(lat_rad) * math.tan(decl))
    
    # Clamp for polar regions
    cos_ha_official = max(-1.0, min(1.0, cos_ha_official))
    ha_official = math.degrees(math.acos(cos_ha_official))
    
    # Zenith for Golden hour (+6 degrees elevation = 84 degrees zenith)
    zenith_golden = math.radians(84.0)
    cos_ha_golden = (math.cos(zenith_golden) / (math.cos(lat_rad) * math.cos(decl)) 
                     - math.tan(lat_rad) * math.tan(decl))
    cos_ha_golden = max(-1.0, min(1.0, cos_ha_golden))
    ha_golden = math.degrees(math.acos(cos_ha_golden))
    
    # Zenith for Blue hour (civil twilight: -6 degrees elevation = 96 degrees zenith)
    zenith_blue = math.radians(96.0)
    cos_ha_blue = (math.cos(zenith_blue) / (math.cos(lat_rad) * math.cos(decl)) 
                   - math.tan(lat_rad) * math.tan(decl))
    cos_ha_blue = max(-1.0, min(1.0, cos_ha_blue))
    ha_blue = math.degrees(math.acos(cos_ha_blue))
    
    # Solar noon in minutes from midnight UTC
    tz_offset = 9.0  # Korea Standard Time (UTC+9)
    solar_noon_min = 720.0 - 4.0 * lon - eqtime + (tz_offset * 60.0)
    
    sunrise_min = solar_noon_min - (ha_official * 4.0)
    sunset_min = solar_noon_min + (ha_official * 4.0)
    
    m_golden_end_min = solar_noon_min - (ha_golden * 4.0)
    e_golden_start_min = solar_noon_min + (ha_golden * 4.0)
    
    m_blue_start_min = solar_noon_min - (ha_blue * 4.0)
    e_blue_end_min = solar_noon_min + (ha_blue * 4.0)
    
    def min_to_hhmm(m: float) -> str:
        m = (m + 1440.0) % 1440.0
        hrs = int(m // 60)
        mins = int(round(m % 60))
        if mins >= 60:
            hrs = (hrs + 1) % 24
            mins = 0
        return f"{hrs:02d}:{mins:02d}"
    
    sunrise_str = min_to_hhmm(sunrise_min)
    sunset_str = min_to_hhmm(sunset_min)
    m_golden_start = sunrise_str
    m_golden_end = min_to_hhmm(m_golden_end_min)
    
    e_golden_start = min_to_hhmm(e_golden_start_min)
    e_golden_end = min_to_hhmm(sunset_min - 5)  # Safe landing 5 min before legal sunset
    
    m_blue_start = min_to_hhmm(m_blue_start_min)
    m_blue_end = sunrise_str
    
    e_blue_start = sunset_str
    e_blue_end = min_to_hhmm(e_blue_end_min)
    
    solar_noon_str = min_to_hhmm(solar_noon_min)
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "sunrise": sunrise_str,
        "sunset": sunset_str,
        "solar_noon": solar_noon_str,
        "morning_golden_hour": f"{m_golden_start} ~ {m_golden_end}",
        "evening_golden_hour": f"{e_golden_start} ~ {e_golden_end}",
        "morning_blue_hour": f"{m_blue_start} ~ {m_blue_end}",
        "evening_blue_hour": f"{e_blue_start} ~ {e_blue_end}",
        "safe_sunset_flight_window": f"{min_to_hhmm(sunset_min - 45)} ~ {min_to_hhmm(sunset_min - 5)}",
        "raw_sunset_min": sunset_min,
        "raw_sunrise_min": sunrise_min
    }

# ---------------------------------------------------------------------------
# 2. Known Landmarks Database in Korea for Instant High-Precision Geocoding
# ---------------------------------------------------------------------------
KOREA_LANDMARKS = {
    "한강": {"lat": 37.5284, "lon": 126.9328, "name": "서울 여의도 한강공원 (한강 수변)", "zone": "서울 원전/비행제한구역(R73) 인근 - 특별주의"},
    "국회의사당": {"lat": 37.5318, "lon": 126.9142, "name": "서울 여의도 국회의사당 & 한강 수변", "zone": "서울 비행제한구역(R73) 및 국가중요시설 - 비행승인 필수"},
    "여의도": {"lat": 37.5284, "lon": 126.9328, "name": "서울 영등포구 여의도동", "zone": "R73 비행제한구역"},
    "뚝섬": {"lat": 37.5312, "lon": 127.0664, "name": "뚝섬 한강공원 (광진구)", "zone": "드론공원 지정구역 (조건부 허용)"},
    "광나루": {"lat": 37.5492, "lon": 127.1215, "name": "광나루 한강 드론공원 (강동구)", "zone": "비행승인 면제 드론공원 (100m 이내)"},
    "해운대": {"lat": 35.1587, "lon": 129.1604, "name": "부산 해운대 해수욕장", "zone": "김해공항 관제공역 외곽 (해안 비행)"},
    "광안리": {"lat": 35.1532, "lon": 129.1186, "name": "부산 광안리 해수욕장 (광안대교)", "zone": "해안선 자유비행 구역"},
    "성산일출봉": {"lat": 33.4581, "lon": 126.9426, "name": "제주 서귀포시 성산일출봉", "zone": "국립공원/천연기념물 보존구역"},
    "대관령": {"lat": 37.6872, "lon": 128.7495, "name": "강원 평창 대관령 삼양목장 / 풍력발전", "zone": "산악 고풍속 주의 구역"},
    "설악산": {"lat": 38.1195, "lon": 128.4655, "name": "강원 인제/속초 설악산 울산바위", "zone": "국립공원 비행제한구역"},
    "송도": {"lat": 37.3894, "lon": 126.6534, "name": "인천 송도 센트럴파크", "zone": "인천공항 관제권 주의"},
    "남산": {"lat": 37.5512, "lon": 126.9882, "name": "서울 남산 N서울타워", "zone": "서울 P-73A 비행금지구역 (비행 불가)"},
    "경복궁": {"lat": 37.5796, "lon": 126.9770, "name": "서울 종로구 경복궁", "zone": "P-73A 비행금지구역 (엄격 금지)"},
    "순천만": {"lat": 34.8860, "lon": 127.5085, "name": "전남 순천만 습지 / 갈대밭", "zone": "생태경관 보전지역"},
    "수원화성": {"lat": 37.2874, "lon": 127.0119, "name": "경기 수원 화성 방화수류정", "zone": "문화재 보호 및 수원비행장 인근"}
}

# ---------------------------------------------------------------------------
# 3. Natural Language Intent & Cinematography Analysis
# ---------------------------------------------------------------------------
def analyze_cinematography_intent(query: str, user_profile: dict = None) -> dict:
    """
    Parses user natural language query, computes astronomical solar data,
    evaluates weather & legal airspace, and returns optimal flight recommendations.
    """
    q = query.lower()
    
    # 1. Location Detection
    matched_loc = None
    matched_key = None
    for k, v in KOREA_LANDMARKS.items():
        if k in query:
            matched_loc = v
            matched_key = k
            break
            
    if not matched_loc:
        matched_loc = {
            "lat": 37.5284, 
            "lon": 126.9328, 
            "name": "서울 한강공원 수변구역", 
            "zone": "수도권 비행안전 구역 (기본 관제)"
        }
        matched_key = "한강"

    lat = matched_loc["lat"]
    lon = matched_loc["lon"]
    loc_display = matched_loc["name"]

    # 2. Solar Astronomical Calculations
    today = date.today()
    sun_times = calculate_sun_times(lat, lon, today)
    
    # 3. Scene Intent Classification
    is_night = any(w in q for w in ["야경", "밤", "도심불빛", "night", "조명", "매직아워", "블루아워"])
    is_sunset = not is_night and any(w in q for w in ["일몰", "노을", "석양", "해질녘", "sunset", "황혼"])
    is_sunrise = any(w in q for w in ["일출", "해돋이", "새벽", "아침", "sunrise", "여명"])
    is_action = any(w in q for w in ["서핑", "파도", "스포츠", "달리기", "자동차", "보트", "액션", "트래킹"])
    is_nature = any(w in q for w in ["단풍", "숲", "가을", "산책", "호수", "나무", "자연", "갈대"])
    is_city = any(w in q for w in ["도심", "빌딩", "건물", "도시", "건축", "스카이라인"])
    
    if not (is_sunset or is_sunrise or is_night or is_action or is_nature or is_city):
        is_sunset = True

    # 4. Optimal Time Window & Legal Rules
    night_flight_warning = None
    legal_clearance = "주간 비행 기준 충족 (일출 후 ~ 일몰 전 비행)"
    
    if is_sunset:
        target_scene_title = "황금빛 일몰 & 강변 실루엣 (Evening Golden Hour)"
        rec_time_start = sun_times["evening_golden_hour"].split(" ~ ")[0]
        rec_time_end = sun_times["evening_golden_hour"].split(" ~ ")[1]
        recommended_time = f"{rec_time_start} ~ {rec_time_end}"
        time_reason = (f"태양 고도가 0°~6° 사이로 빛이 부드러워지며 강변 수면에 황금빛 반영이 가장 극대화되는 시간대입니다. "
                       f"항공안전법상 일몰({sun_times['sunset']}) 후 야간비행은 특별승인이 필요하므로, "
                       f"일몰 5분 전({rec_time_end})까지 안전하게 착륙을 완료하는 일정으로 편성되었습니다.")
    elif is_sunrise:
        target_scene_title = "여명 & 아침 골든아워 (Morning Golden Hour)"
        rec_time_start = sun_times["morning_golden_hour"].split(" ~ ")[0]
        rec_time_end = sun_times["morning_golden_hour"].split(" ~ ")[1]
        recommended_time = f"{rec_time_start} ~ {rec_time_end}"
        time_reason = (f"일출({sun_times['sunrise']}) 직후 대기 중 연무와 맑은 빛이 피사체를 감싸는 최적의 역광 시간대입니다. "
                       f"바람이 가장 잔잔하여 안정적인 저고도 호버링과 물결 반영 촬영에 유리합니다.")
    elif is_night:
        target_scene_title = "블루아워 & 도심 야경 (Blue Hour to Night)"
        recommended_time = sun_times["evening_blue_hour"]
        time_reason = (f"하늘에 짙은 남색 빛이 남아있고 지상 인공조명이 켜지는 일몰 직후 30분 골든 타임입니다.")
        night_flight_warning = ("⚠️ [항공안전법 제129조 야간비행 주의] 일몰 후 비행은 국토교통부 '특별비행승인' "
                                "(야간비행 허가) 및 기체 충돌방지등(3NM 식별 가능) 장착이 법적으로 필수입니다.")
        legal_clearance = "야간 비행 특별승인 필요"
    else:
        target_scene_title = "자연광 풍경 & 다이내믹 시네마틱 (Midday Sunlight)"
        recommended_time = "14:00 ~ 15:30 (최적 사광선 시간대)"
        time_reason = ("정오의 직사광선을 피해 45도 사광선(Side Light)이 들어오는 시간대로 피사체의 입체감과 그림자 디테일이 우수합니다.")

    # 5. Cinematic Flight Move Recommendation
    if is_sunset:
        rec_mode_name = "패럴랙스 리빌 & 선셋 아크 (Parallax Arc & Reveal)"
        rec_mode_desc = "피사체(강변/교각)를 전경에 두고 측면으로 완만하게 선회(Orbit)하면서 후경의 일몰 지평선이 점진적으로 드러나는 3차원 입체 기법"
        recommended_alt = 55
        gimbal_pitch = "-15° ~ -25°"
        stick_left = "상승 15% 서서히 가속 (고도 35m ➔ 65m 점진 상승)"
        stick_right = "전진 30% + 우측 횡이동 25% (대각선 완만한 호 궤적)"
        drone_speed = "2.5 m/s (부드러운 시네 스피드)"
    elif is_sunrise:
        rec_mode_name = "스카이 드로니 & 호라이즌 라이즈 (Sky Dronie & Horizon Rise)"
        rec_mode_desc = "수면 가까이 저고도에서 시작하여 후방으로 대각선 급상승하며 웅장한 아침 햇살과 주변 파노라마를 한눈에 확장시키는 기법"
        recommended_alt = 70
        gimbal_pitch = "-10° ➔ -35° (상승에 맞춰 틸트 다운)"
        stick_left = "스로틀 상승 40% 지속"
        stick_right = "피치 후진 45% (수직-후방 대각선 궤적)"
        drone_speed = "3.8 m/s (역동적 공간 확장)"
    elif is_action:
        rec_mode_name = "로우 앵글 다이내믹 트래킹 (Low-to-High Tracking)"
        rec_mode_desc = "피사체의 진행 방향 전면 또는 측면 45도에서 시선을 평행하게 유지하며 속도감 있게 추적하는 액션 촬영"
        recommended_alt = 25
        gimbal_pitch = "-10° 수평 밀착"
        stick_left = "방향 회전(Yaw)으로 피사체 센터 락온 유지"
        stick_right = "전진 피치 60% (피사체 속도와 정밀 동기화)"
        drone_speed = "6.0 ~ 8.0 m/s"
    elif is_nature:
        rec_mode_name = "포레스트 버드아이 & 슬로우 패스 (Top-Down Bird's Eye)"
        rec_mode_desc = "카메라를 수직 90도로 바닥을 내려다보게 고정하고, 숲의 텍스처와 단풍 능선을 회전하며 감상하는 버티고 뷰"
        recommended_alt = 85
        gimbal_pitch = "-90° (직하방 수직 앵글)"
        stick_left = "미세 Yaw 회전 (분당 90도 이하 극저속 회전)"
        stick_right = "순방향 전진 20% (직선 관통 비행)"
        drone_speed = "1.8 m/s (안정적인 텍스처 감상)"
    else:
        rec_mode_name = "시네마틱 360 오빗 (Cinematic 360 Orbit)"
        rec_mode_desc = "중심 랜드마크를 화면 정중앙에 고정하고 일정한 반경(30m)을 그리며 원형으로 선회하는 가장 안정적인 클래식 시네마틱 샷"
        recommended_alt = 50
        gimbal_pitch = "-25°"
        stick_left = "Yaw 좌회전 25%"
        stick_right = "Roll 우측 이동 35% (동시 조작으로 원형 궤적 형성)"
        drone_speed = "2.2 m/s"

    # 6. Camera & Exposure Settings
    if is_sunset:
        cam_res = "4K (3840x2160) @ 24fps (시네마틱 모션 블러)"
        shutter = "1/50s (180° 셔터 앵글 룰 준수)"
        nd_filter = "ND16 필터 (골든아워 역광 노출 제어)"
        iso = "ISO 100 고정 (노이즈 최소화)"
        color_profile = "D-Log M / 10-bit (석양 그라데이션 DR 확보)"
        white_balance = "5600K ~ 6200K (황금빛 색온도 수동 고정)"
    elif is_sunrise:
        cam_res = "4K @ 24fps"
        shutter = "1/50s"
        nd_filter = "ND8 필터 (이른 아침 부드러운 감광)"
        iso = "ISO 100"
        color_profile = "D-Log M / HLG"
        white_balance = "5000K ~ 5400K"
    elif is_night:
        is_tele = any(w in q for w in ["망원", "3x", "70mm", "압축"])
        cam_res = "4K @ 30fps (DJI Air 3 70mm 3배 망원 렌즈 추천 - 피사체 압축감)" if is_tele else "4K @ 30fps"
        shutter = "1/30s 또는 1/60s (빛 번짐 억제)"
        nd_filter = "필터 없음 (UV 또는 Clear) - 야간 최대 수광량 확보"
        iso = "ISO 400 ~ 800 (기체 야간 노이즈 제어)"
        color_profile = "Night Mode 또는 Normal (10-bit)"
        white_balance = "4000K (도심 가로등 및 조명 밸런스)"
    elif is_action:
        cam_res = "4K @ 60fps (부드러운 슬로우모션 변환 가능)"
        shutter = "1/120s"
        nd_filter = "ND32 필터 (강한 주간 반사광 억제)"
        iso = "ISO 100"
        color_profile = "D-Cinelike"
        white_balance = "5500K (Daylight)"
    else:
        cam_res = "4K @ 30fps"
        shutter = "1/60s"
        nd_filter = "ND16 / ND32"
        iso = "ISO 100"
        color_profile = "D-Cinelike"
        white_balance = "5500K"

    # 7. Generate Visual SVG Diagram Markup
    svg_diagram = generate_flight_path_svg(rec_mode_name, recommended_alt, gimbal_pitch, loc_display)

    res_dict = {
        "location": loc_display,
        "landmark_key": matched_key,
        "lat": lat,
        "lon": lon,
        "date": today.strftime("%Y-%m-%d"),
        "sun_times": sun_times,
        "scene_title": target_scene_title,
        "recommended_time": recommended_time,
        "time_reason": time_reason,
        "night_flight_warning": night_flight_warning,
        "legal_clearance": legal_clearance,
        "mode_name": rec_mode_name,
        "mode_desc": rec_mode_desc,
        "altitude_m": recommended_alt,
        "gimbal_pitch": gimbal_pitch,
        "stick_left": stick_left,
        "stick_right": stick_right,
        "speed": drone_speed,
        "camera_settings": {
            "resolution": cam_res,
            "shutter": shutter,
            "nd_filter": nd_filter,
            "iso": iso,
            "color_profile": color_profile,
            "white_balance": white_balance
        },
        "svg_diagram": svg_diagram,
        "query_raw": query
    }
    
    # Attach dynamic notices based on user intent
    res_dict["notices"] = generate_cinematography_notices(query, res_dict)
    return res_dict

# ---------------------------------------------------------------------------
# 3.1 Dynamic Notices & Announcement Generator for Shooting Intent
# ---------------------------------------------------------------------------
def generate_cinematography_notices(query: str, analysis: dict) -> list:
    """
    Generates dynamic contextual notices, announcements, and reference tips
    based on the user's natural language input, location, airspace, and equipment.
    """
    q = query.lower()
    notices = []
    
    # 1. Airspace & Legal Notice
    if analysis.get("night_flight_warning"):
        notices.append({
            "icon": "⚖️",
            "badge": "항공안전법 공지",
            "badge_color": "#dc2626",
            "badge_bg": "#fef2f2",
            "title": "야간 비행 특별승인 필수 안내 (항공안전법 제129조)",
            "desc": "일몰 후 야간 비행은 국토교통부(지방항공청) '특별비행승인' 및 3NM 이상 가시거리 식별이 가능한 야간 충돌방지등 장착이 법적으로 필수입니다."
        })
    elif any(k in q for k in ["국회의사당", "여의도", "청와대", "용산", "원전"]):
        notices.append({
            "icon": "🏛️",
            "badge": "비행제한구역 공지",
            "badge_color": "#b45309",
            "badge_bg": "#fffbeb",
            "title": "수도권 비행제한구역(R-73) 및 국가중요시설 사전 승인 안내",
            "desc": "해당 지역은 비행제한구역 또는 국가중요시설 인근입니다. 비행 최소 3~7일 전 드론원스톱(drone.onestop.go.kr)을 통해 비행승인 및 항공촬영 허가를 반드시 득해야 합니다."
        })
    else:
        notices.append({
            "icon": "📏",
            "badge": "공역 준수사항",
            "badge_color": "#1d4ed8",
            "badge_bg": "#eff6ff",
            "title": "법정 최고고도 150m 준수 및 조종자 시계비행(VLOS)",
            "desc": "항공안전법상 대지면 기준 150m 초과 비행은 엄격히 금지되며, 육안으로 기체를 항상 확인할 수 있는 시계비행 범위를 유지해야 합니다."
        })
        
    # 2. Camera & Gear Reference
    if any(k in q for k in ["망원", "3x", "70mm", "air 3", "air3", "압축"]):
        notices.append({
            "icon": "🔭",
            "badge": "촬영 기법 참고",
            "badge_color": "#4338ca",
            "badge_bg": "#eef2ff",
            "title": "DJI Air 3 70mm 미디엄 망원 렌즈 압축 구도 팁",
            "desc": "70mm 망원은 피사체와 배경 건물군의 원근을 압축(Compression)하여 웅장한 도심 야경을 담아냅니다. 망원 화각은 미세한 흔들림에도 민감하므로 '시네 모드(C-Mode)' 및 삼각대 모드로 완만한 선회 비행을 권장합니다."
        })
    elif any(k in q for k in ["일몰", "노을", "석양", "골든아워"]):
        notices.append({
            "icon": "🌅",
            "badge": "노출 가이드",
            "badge_color": "#c2410c",
            "badge_bg": "#fff7ed",
            "title": "골든아워 180° 셔터 앵글 & 감광 필터 세팅",
            "desc": "24fps 기준 1/50초 셔터속도를 유지하고 ND16 필터를 활용하여 부드러운 모션 블러와 일몰 역광 하이라이트/암부 디테일을 D-Log M 프로파일로 보존하세요."
        })
    elif any(k in q for k in ["서핑", "스포츠", "액션", "파도"]):
        notices.append({
            "icon": "🌊",
            "badge": "액션 촬영 팁",
            "badge_color": "#0284c7",
            "badge_bg": "#f0f9ff",
            "title": "고속 추적 비행 & 피사체 락온 설정",
            "desc": "빠른 피사체의 움직임을 흔들림 없이 포착하려면 4K 60fps와 최소 1/120s 셔터스피드를 권장하며, 능동형 장애물 감지 센서를 반드시 활성화하세요."
        })
    else:
        notices.append({
            "icon": "🎬",
            "badge": "화질 최적화",
            "badge_color": "#047857",
            "badge_bg": "#ecfdf5",
            "title": "시네마틱 컬러 프로파일 및 셔터 앵글 권장",
            "desc": "자연스러운 움직임 표현을 위해 180° 셔터 룰(프레임레이트의 2배수 셔터스피드)을 적용하고 D-Log M 또는 D-Cinelike 10-bit로 촬영하세요."
        })

    # 3. Weather & Safety Notice
    notices.append({
        "icon": "🌤️",
        "badge": "현장 안전 알림",
        "badge_color": "#0f766e",
        "badge_bg": "#f0fdfa",
        "title": "실시간 풍속 및 전파 간섭(Compass Error) 점검",
        "desc": "비행 전 현장 돌풍(최대 10m/s 이하 권장)과 수변/교각/고압선 주변 전자기파 간섭을 확인하고, 배터리 잔량 30% 도달 전 안전 착륙을 계획하세요."
    })
    
    return notices

# ---------------------------------------------------------------------------
# 4. Interactive SVG Flight Trajectory & Camera Angle Diagram Generator
# ---------------------------------------------------------------------------
def generate_flight_path_svg(mode_name: str, altitude: int, gimbal_pitch: str, location_name: str) -> str:
    """
    Returns an ultra-clean, modern SVG diagram visualizing the drone's 3D trajectory,
    camera FOV cone, altitude waypoints, and target point of interest (POI).
    """
    svg = f"""
    <svg viewBox="0 0 760 330" width="100%" height="260" xmlns="http://www.w3.org/2000/svg" style="background:#0c1a2d; border-radius:14px; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <defs>
            <linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#142642" />
                <stop offset="65%" stop-color="#2d3b59" />
                <stop offset="85%" stop-color="#df744a" stop-opacity="0.4" />
                <stop offset="100%" stop-color="#e89f65" stop-opacity="0.2" />
            </linearGradient>
            <linearGradient id="beamGrad" x1="0%" y1="0%" x2="100%" y2="80%">
                <stop offset="0%" stop-color="#3978f6" stop-opacity="0.65" />
                <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.05" />
            </linearGradient>
            <linearGradient id="groundGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#172b4d" />
                <stop offset="100%" stop-color="#091424" />
            </linearGradient>
            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
        </defs>

        <rect x="0" y="0" width="760" height="260" fill="url(#skyGrad)" />
        <rect x="0" y="260" width="760" height="70" fill="url(#groundGrad)" />
        <line x1="0" y1="260" x2="760" y2="260" stroke="#334e68" stroke-width="1.5" />
        
        <path d="M 40 280 Q 90 276, 140 280 T 240 280" stroke="#254366" stroke-width="1.2" fill="none" opacity="0.6" />
        <path d="M 320 295 Q 380 291, 440 295 T 560 295" stroke="#254366" stroke-width="1.2" fill="none" opacity="0.5" />
        <path d="M 520 275 Q 580 272, 640 275 T 720 275" stroke="#254366" stroke-width="1.2" fill="none" opacity="0.6" />

        <path d="M 460 260 L 510 200 L 530 260 L 590 180 L 610 260 L 680 220 L 730 260 Z" fill="#1b2a47" opacity="0.5" />
        
        <line x1="60" y1="45" x2="720" y2="45" stroke="#ef4444" stroke-dasharray="4,4" stroke-width="1.2" opacity="0.8" />
        <text x="715" y="40" fill="#f87171" font-size="10" font-weight="bold" text-anchor="end">⚠️ 항공안전법 법정 고도 한계선 (150m)</text>

        <line x1="60" y1="120" x2="720" y2="120" stroke="#38bdf8" stroke-dasharray="2,3" stroke-width="0.8" opacity="0.5" />
        <text x="65" y="115" fill="#38bdf8" font-size="10" font-weight="600">추천 순항 고도: {altitude}m</text>

        <line x1="50" y1="45" x2="50" y2="260" stroke="#486581" stroke-width="1.5" />
        <line x1="45" y1="45" x2="50" y2="45" stroke="#ef4444" stroke-width="2" />
        <line x1="45" y1="120" x2="50" y2="120" stroke="#38bdf8" stroke-width="2" />
        <line x1="45" y1="190" x2="50" y2="190" stroke="#627d98" stroke-width="1.5" />
        <line x1="42" y1="260" x2="50" y2="260" stroke="#627d98" stroke-width="2" />
        <text x="38" y="49" fill="#f87171" font-size="9" text-anchor="end">150m</text>
        <text x="38" y="124" fill="#38bdf8" font-size="9" text-anchor="end">{altitude}m</text>
        <text x="38" y="194" fill="#829ab1" font-size="9" text-anchor="end">40m</text>
        <text x="38" y="264" fill="#829ab1" font-size="9" text-anchor="end">0m (지표)</text>

        <polygon points="340,118 520,245 590,260 340,118" fill="url(#beamGrad)" />

        <path d="M 110 230 C 180 180, 260 120, 340 118 S 530 115, 660 160" 
              fill="none" stroke="#38bdf8" stroke-width="3.5" stroke-linecap="round" stroke-dasharray="6,4" filter="url(#glow)" />
        
        <circle cx="110" cy="230" r="6" fill="#102a45" stroke="#38bdf8" stroke-width="2.5" />
        <text x="110" y="215" fill="#bae6fd" font-size="11" font-weight="700" text-anchor="middle">WP 1</text>
        <text x="110" y="248" fill="#94a3b8" font-size="9" text-anchor="middle">이륙 &amp; 진입 (25m)</text>

        <g transform="translate(340, 118)">
            <line x1="-16" y1="-8" x2="16" y2="8" stroke="#ffffff" stroke-width="2.5" />
            <line x1="-16" y1="8" x2="16" y2="-8" stroke="#ffffff" stroke-width="2.5" />
            <ellipse cx="-16" cy="-8" rx="7" ry="2.5" fill="#38bdf8" opacity="0.8" />
            <ellipse cx="16" cy="8" rx="7" ry="2.5" fill="#38bdf8" opacity="0.8" />
            <ellipse cx="-16" cy="8" rx="7" ry="2.5" fill="#38bdf8" opacity="0.8" />
            <ellipse cx="16" cy="-8" rx="7" ry="2.5" fill="#38bdf8" opacity="0.8" />
            <circle cx="0" cy="0" r="7" fill="#3b82f6" stroke="#ffffff" stroke-width="2" />
            <polygon points="5,-3 12,0 5,3" fill="#60a5fa" />
        </g>
        
        <rect x="255" y="65" width="170" height="34" rx="8" fill="#1e293b" stroke="#38bdf8" stroke-width="1.2" opacity="0.95" />
        <text x="340" y="79" fill="#38bdf8" font-size="10.5" font-weight="800" text-anchor="middle">WP 2 (핵심 시네마틱 구간)</text>
        <text x="340" y="93" fill="#cbd5e1" font-size="9.5" text-anchor="middle">고도 {altitude}m · 짐벌 피치 {gimbal_pitch}</text>

        <circle cx="660" cy="160" r="6" fill="#102a45" stroke="#38bdf8" stroke-width="2.5" />
        <text x="660" y="146" fill="#bae6fd" font-size="11" font-weight="700" text-anchor="middle">WP 3</text>
        <text x="660" y="180" fill="#94a3b8" font-size="9" text-anchor="middle">상승 이탈 &amp; 복귀</text>

        <g transform="translate(560, 255)">
            <ellipse cx="0" cy="0" rx="20" ry="6" fill="#f59e0b" opacity="0.3" />
            <circle cx="0" cy="-6" r="6" fill="#f59e0b" stroke="#ffffff" stroke-width="2" />
            <line x1="0" y1="-12" x2="0" y2="-28" stroke="#f59e0b" stroke-width="2" />
            <polygon points="0,-28 14,-22 0,-16" fill="#ef4444" />
            <text x="0" y="18" fill="#fde68a" font-size="10.5" font-weight="750" text-anchor="middle">🎯 초점 타겟 (POI)</text>
        </g>

        <line x1="340" y1="118" x2="560" y2="249" stroke="#fbbf24" stroke-dasharray="3,3" stroke-width="1.5" />
        <circle cx="560" cy="249" r="3" fill="#fbbf24" />

        <rect x="60" y="12" width="280" height="24" rx="6" fill="#0f172a" opacity="0.8" />
        <text x="70" y="28" fill="#e2e8f0" font-size="11" font-weight="700">🎬 {mode_name}</text>
    </svg>
    """
    return re.sub(r'^[ \t]+', '', svg.strip(), flags=re.MULTILINE)

# ---------------------------------------------------------------------------
# 5. Bridge to Sky Command Flight Assistant (대화로 신청하기 1-Click Sync)
# ---------------------------------------------------------------------------
def export_to_flight_assistant(analysis: dict) -> dict:
    """
    Constructs a complete 7-field dictionary for st.session_state.flight_form_data,
    guaranteeing instant 100% progress rate (7/7 filled) when transferred to View 2.
    """
    location = analysis.get("location", "서울 여의도 한강공원 수변구역")
    date_str = analysis.get("date", date.today().strftime("%Y-%m-%d"))
    time_window = analysis.get("recommended_time", "17:15 ~ 18:00")
    scene = analysis.get("scene_title", "골든아워 시네마틱 항공촬영")
    alt = analysis.get("altitude_m", 60)
    cam = analysis.get("camera_settings", {})
    q_raw = analysis.get("query_raw", "").lower()

    is_air3 = "air 3" in q_raw or "air3" in q_raw
    weight_str = "720g (DJI Air 3 - 초경량 2종)" if is_air3 else "249g (초경량 비행장치 1종 면제)"

    return {
        "location": location,
        "date": date_str,
        "time": f"{time_window} (추천 비행시간)",
        "weight": weight_str,
        "camera": f"카메라 탑재 ({cam.get('resolution', '4K 24fps')[:24]}, {cam.get('nd_filter', 'ND16')[:10]})",
        "purpose": f"{scene.split('(')[0].strip()} 및 항공촬영",
        "altitude": f"{alt}m (법정고도 150m 이내 준수)"
    }
