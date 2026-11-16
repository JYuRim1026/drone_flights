import math

# Official Drone One-Stop (드론원스톱) Legend Data & Color Codes
OFFICIAL_LEGENDS = {
    "P": {"name": "비행금지구역 (Prohibited Area)", "color": "#DC2626", "badge": "🔴", "desc": "안보 및 보안상 사전 승인 없이 비행이 절대 금지되는 구역"},
    "R": {"name": "비행제한구역 (Restricted Area)", "color": "#EA580C", "badge": "🟠", "desc": "수도권 대공방어 및 안보 목적으로 비행 승인이 필요한 구역"},
    "CTR": {"name": "공항 관제권 (Control Zone)", "color": "#D97706", "badge": "🟡", "desc": "공항/비행장 반경 9.3km 이내 항공기 안전 관제 구역"},
    "MOA": {"name": "군작전구역 (Military Operations Area)", "color": "#9333EA", "badge": "🟣", "desc": "군용 항공기 훈련 및 작전을 위한 구역"},
    "UA": {"name": "드론전용공역 (Ultralight Flight Area)", "color": "#059669", "badge": "🟢", "desc": "드론 시험 및 자유 비행을 위해 지정된 전용 공역 (승인 면제)"},
    "G": {"name": "비관제공역 (Uncontrolled Airspace)", "color": "#0284C7", "badge": "🔵", "desc": "기본 안전수칙 준수 시 자유롭게 비행 가능한 일반 공역"}
}

# Airspace Zones Database with Official Drone One-Stop Contacts & Categories
AIRSPACE_ZONES = [
    # 1. P (Prohibited Areas - 비행금지구역)
    {
        "name": "P-73A/B 비행금지구역 (서울 도심/용산)",
        "code": "P-73",
        "category_code": "P",
        "category": "P (비행금지구역)",
        "color": "#DC2626",
        "lat": 37.5326,
        "lon": 126.9810,
        "radius_km": 8.3,
        "authority": "수도방위사령부 / 서울지방항공청",
        "desc": "국가 보안 주요 시설 보호 구역",
        "flight_contact": "군 담당자 [ ☎ 02-524-3346 ]",
        "special_contact": "김포항공관리사무소(안전운항과) ☎ 02-2660-5733",
        "photo_contact": "군 담당자 [ ☎ 02-524-3346 ]"
    },
    {
        "name": "P-61 고리/새울 원전 비행금지구역",
        "code": "P-61",
        "category_code": "P",
        "category": "P (비행금지구역)",
        "color": "#DC2626",
        "lat": 35.3167,
        "lon": 129.2833,
        "radius_km": 18.6,
        "authority": "국방부 / 산업통상자원부",
        "desc": "원자력 발전소 핵심 안보 시설 구역",
        "flight_contact": "군 담당자 [ ☎ 051-720-3114 ]",
        "special_contact": "부산지방항공청 ☎ 051-974-2144",
        "photo_contact": "군 담당자 [ ☎ 051-720-3114 ]"
    },
    {
        "name": "P-62 월성 원전 비행금지구역",
        "code": "P-62",
        "category_code": "P",
        "category": "P (비행금지구역)",
        "color": "#DC2626",
        "lat": 35.7133,
        "lon": 129.4750,
        "radius_km": 18.6,
        "authority": "국방부 / 산업통상자원부",
        "desc": "원자력 발전소 핵심 안보 시설 구역",
        "flight_contact": "군 담당자 [ ☎ 054-770-3114 ]",
        "special_contact": "부산지방항공청 ☎ 051-974-2144",
        "photo_contact": "군 담당자 [ ☎ 054-770-3114 ]"
    },
    
    # 2. CTR (Control Zone - 관제권 / 공항 주변 9.3km)
    {
        "name": "오산 공군기지 관제권 (RKSO CTR)",
        "code": "RKSO CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.0906,
        "lon": 127.0304,
        "radius_km": 18.0,
        "authority": "공군 제51전투비행단 / 미공군",
        "desc": "군용 항공기 비행 이착륙 관제 공역 (오산시, 평택시, 화성시 양산동 등 포함)",
        "flight_contact": "군 담당자 [ ☎ 031-220-1224 ]",
        "special_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 031-290-9225 ]"
    },
    {
        "name": "수원 공군기지 관제권 (RKSW CTR)",
        "code": "RKSW CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.2386,
        "lon": 127.0078,
        "radius_km": 12.0,
        "authority": "공군 제10전투비행단",
        "desc": "군용 항공기 관제 공역 (수원시, 화성시, 오산 북부 일부)",
        "flight_contact": "군 담당자 [ ☎ 031-220-1224 ]",
        "special_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 031-290-9225 ]"
    },
    {
        "name": "김포국제공항 관제권 (CTR)",
        "code": "RKSS CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.5583,
        "lon": 126.7906,
        "radius_km": 9.3,
        "authority": "서울지방항공청",
        "desc": "항공기 이착륙 관제 공역 (서울 성동구, 강서구, 마포구, 은평구 등 해당)",
        "flight_contact": "군 담당자 [ ☎ 02-524-3346 ]",
        "special_contact": "김포항공관리사무소(안전운항과) ☎ 02-2660-5733",
        "photo_contact": "군 담당자 [ ☎ 02-524-3346 ]"
    },
    {
        "name": "인천국제공항 관제권 (CTR)",
        "code": "RKSI CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.4604,
        "lon": 126.4407,
        "radius_km": 9.3,
        "authority": "서울지방항공청",
        "desc": "공항 반경 9.3km 이내 민간 항공기 통행구역",
        "flight_contact": "인천공항출장소 ☎ 032-740-2351",
        "special_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 032-740-2351 ]"
    },
    {
        "name": "서울공항(K-16) 관제권 (CTR)",
        "code": "RKSM CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.4450,
        "lon": 127.1111,
        "radius_km": 9.3,
        "authority": "공군 제15특수임무비행단",
        "desc": "군용 항공기 관제 공역 (성남, 송파, 서초 일부)",
        "flight_contact": "군 담당자 [ ☎ 031-720-3114 ]",
        "special_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 031-720-3114 ]"
    },
    {
        "name": "김해국제공항 관제권 (CTR)",
        "code": "RKPK CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.1795,
        "lon": 128.9382,
        "radius_km": 9.3,
        "authority": "부산지방항공청",
        "desc": "공항 반경 9.3km 관제 구역",
        "flight_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
        "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 051-970-2114 ]"
    },
    {
        "name": "제주국제공항 관제권 (CTR)",
        "code": "RKPC CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 33.5113,
        "lon": 126.4930,
        "radius_km": 9.3,
        "authority": "제주지방항공청",
        "desc": "제주공항 반경 9.3km 관제 구역",
        "flight_contact": "제주지방항공청 ☎ 064-797-6800",
        "special_contact": "제주지방항공청 ☎ 064-797-6831",
        "photo_contact": "군 담당자 [ ☎ 064-797-6800 ]"
    },
    {
        "name": "대구국제공항(K-2 기지) 관제권 (CTR)",
        "code": "RKTN CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.8995,
        "lon": 128.6593,
        "radius_km": 9.3,
        "authority": "공군 제11전투비행단 / 부산지방항공청",
        "desc": "공항 반경 9.3km 이내 대구 도심 및 공군 관제구역",
        "flight_contact": "공군 제11전비 [ ☎ 053-989-3204 ] / 부산지방항공청 ☎ 051-974-2155",
        "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 053-320-6219 ]"
    },
    {
        "name": "광주공항(제1전투비행단) 관제권 (CTR)",
        "code": "RKJJ CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.1264,
        "lon": 126.8089,
        "radius_km": 9.3,
        "authority": "공군 제1전투비행단 / 부산지방항공청",
        "desc": "광주 도심 서부 및 공항 관제구역",
        "flight_contact": "공군 제1전비 [ ☎ 062-940-1313 ] / 부산지방항공청 ☎ 051-974-2155",
        "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 062-260-6211 ]"
    },
    {
        "name": "울산공항 관제권 (CTR)",
        "code": "RKPU CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.5936,
        "lon": 129.3519,
        "radius_km": 9.3,
        "authority": "부산지방항공청",
        "desc": "울산공항 반경 9.3km 민항 관제구역",
        "flight_contact": "부산지방항공청 ☎ 051-974-2155",
        "special_contact": "부산지방항공청 ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 051-730-6209 ]"
    },
    {
        "name": "청주국제공항(공군 제17전투비행단) 관제권 (CTR)",
        "code": "RKTU CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 36.7166,
        "lon": 127.4991,
        "radius_km": 9.3,
        "authority": "공군 제17전투비행단 / 서울지방항공청",
        "desc": "청주 도심 및 세종 북부 관제구역",
        "flight_contact": "서울지방항공청 ☎ 032-740-2351",
        "special_contact": "서울지방항공청 ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 043-210-2114 ]"
    },
    {
        "name": "포항공항(해군 제6항공전단) 관제권 (CTR)",
        "code": "RKTH CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.9877,
        "lon": 129.4203,
        "radius_km": 9.3,
        "authority": "해군 제6항공전단 / 부산지방항공청",
        "desc": "포항 남구 및 해군 비행장 관제구역",
        "flight_contact": "해군 제6항공전단 [ ☎ 054-290-3114 ] / 부산지방항공청",
        "special_contact": "부산지방항공청 ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 054-290-3114 ]"
    },
    {
        "name": "군산공항(미공군 제8전투비행단) 관제권 (CTR)",
        "code": "RKJK CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.9261,
        "lon": 126.6158,
        "radius_km": 9.3,
        "authority": "미공군 제8전비 / 서울지방항공청",
        "desc": "군산공항 반경 9.3km 한미연합 군사관제권",
        "flight_contact": "서울지방항공청 ☎ 032-740-2351",
        "special_contact": "서울지방항공청 ☎ 032-740-2351",
        "photo_contact": "국방부 [ ☎ 02-748-3114 ]"
    },
    {
        "name": "여수공항 관제권 (CTR)",
        "code": "RKJY CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 34.8423,
        "lon": 127.6166,
        "radius_km": 9.3,
        "authority": "부산지방항공청",
        "desc": "여수공항 반경 9.3km 관제구역",
        "flight_contact": "부산지방항공청 ☎ 051-974-2155",
        "special_contact": "부산지방항공청 ☎ 051-974-2155",
        "photo_contact": "국방부 [ ☎ 02-748-3114 ]"
    },
    {
        "name": "사천공항(공군 제3훈련비행단) 관제권 (CTR)",
        "code": "RKPS CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 35.0886,
        "lon": 128.0841,
        "radius_km": 9.3,
        "authority": "공군 제3훈련비행단 / 부산지방항공청",
        "desc": "사천 및 진주 일대 비행 훈련 관제구역",
        "flight_contact": "부산지방항공청 ☎ 051-974-2155",
        "special_contact": "부산지방항공청 ☎ 051-974-2155",
        "photo_contact": "군 담당자 [ ☎ 055-850-2114 ]"
    },
    {
        "name": "원주공항(공군 제8전투비행단) 관제권 (CTR)",
        "code": "RKNW CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 37.4382,
        "lon": 127.9605,
        "radius_km": 9.3,
        "authority": "공군 제8전비 / 서울지방항공청",
        "desc": "원주 및 횡성 일대 공군 작전 관제구역",
        "flight_contact": "서울지방항공청 ☎ 032-740-2351",
        "special_contact": "서울지방항공청 ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 033-740-2114 ]"
    },
    {
        "name": "양양국제공항 관제권 (CTR)",
        "code": "RKNY CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 38.0614,
        "lon": 128.6692,
        "radius_km": 9.3,
        "authority": "서울지방항공청",
        "desc": "양양공항 반경 9.3km 영동 관제구역",
        "flight_contact": "서울지방항공청 ☎ 032-740-2351",
        "special_contact": "서울지방항공청 ☎ 032-740-2351",
        "photo_contact": "국방부 [ ☎ 02-748-3114 ]"
    },
    {
        "name": "서산 해미비행장(공군 제20전투비행단) 관제권 (CTR)",
        "code": "RKTP CTR",
        "category_code": "CTR",
        "category": "CTR (관제권)",
        "color": "#D97706",
        "lat": 36.7027,
        "lon": 126.4950,
        "radius_km": 9.3,
        "authority": "공군 제20전투비행단",
        "desc": "서산 해미 일대 공군 작전 관제구역",
        "flight_contact": "서울지방항공청 ☎ 032-740-2351",
        "special_contact": "서울지방항공청 ☎ 032-740-2351",
        "photo_contact": "군 담당자 [ ☎ 041-689-2114 ]"
    },
    
    # 3. R / MOA (Restricted / Military Operations Area)
    {
        "name": "수도권 비행제한구역 (R-75)",
        "code": "R-75",
        "category_code": "R",
        "category": "R (비행제한구역)",
        "color": "#EA580C",
        "lat": 37.5665,
        "lon": 126.9780,
        "radius_km": 15.0,
        "authority": "수도방위사령부",
        "desc": "수도권 안보 및 대공 방어를 위한 비행 제한 구역",
        "flight_contact": "군 담당자 [ ☎ 02-524-3346 ]",
        "special_contact": "김포항공관리사무소(안전운항과) ☎ 02-2660-5733",
        "photo_contact": "군 담당자 [ ☎ 02-524-3346 ]"
    },
    {
        "name": "휴전선 접경 비행제한구역 (P-518)",
        "code": "P-518",
        "category_code": "R",
        "category": "R (비행제한구역)",
        "color": "#EA580C",
        "lat": 37.8500,
        "lon": 126.7800,
        "radius_km": 30.0,
        "authority": "합동참모본부 / 국방부",
        "desc": "DMZ 접경 안보 군사 작전 구역",
        "flight_contact": "합동참모본부 [☎ 02-748-3114]",
        "special_contact": "서울지방항공청 [☎ 032-740-2351]",
        "photo_contact": "국방부 [☎ 02-748-3114]"
    },
    
    # 4. UA / UAV (드론 전용 비행공역)
    {
        "name": "시흥 드론 전용 비행공역 (UA)",
        "code": "UA-SH",
        "category_code": "UA",
        "category": "UA (드론전용공역)",
        "color": "#059669",
        "lat": 37.3801,
        "lon": 126.8030,
        "radius_km": 2.5,
        "authority": "시흥시 / 한국교통안전공단",
        "desc": "드론 전용 비행공역 (비행승인 우대/자유 비행)",
        "flight_contact": "시흥시 드론사업과 [☎ 031-310-2114]",
        "special_contact": "서울지방항공청 [☎ 032-740-2351]",
        "photo_contact": "국방부 [☎ 02-748-3114]"
    },
    {
        "name": "보은 드론 전용 비행공역 (UA)",
        "code": "UA-BE",
        "category_code": "UA",
        "category": "UA (드론전용공역)",
        "color": "#059669",
        "lat": 36.4894,
        "lon": 127.7294,
        "radius_km": 3.0,
        "authority": "보은군 / 국토교통부",
        "desc": "드론 실증 전용 공역",
        "flight_contact": "보은군 드론사업팀 [☎ 043-540-3114]",
        "special_contact": "부산지방항공청 [☎ 051-974-2144]",
        "photo_contact": "국방부 [☎ 02-748-3114]"
    }
]

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def check_airspace(lat, lon, location_name="입력 위치"):
    matched_zones = []
    is_prohibited = False
    is_controlled = False
    is_restricted = False
    is_ua_zone = False

    for zone in AIRSPACE_ZONES:
        dist = haversine_distance(lat, lon, zone["lat"], zone["lon"])
        if dist <= zone["radius_km"]:
            matched_zones.append({
                "name": zone["name"],
                "code": zone["code"],
                "category_code": zone.get("category_code", "CTR"),
                "category": zone["category"],
                "color": zone.get("color", "#D97706"),
                "authority": zone["authority"],
                "distance_km": round(dist, 2),
                "desc": zone["desc"],
                "flight_contact": zone.get("flight_contact", "지방항공청"),
                "special_contact": zone.get("special_contact", "지방항공청"),
                "photo_contact": zone.get("photo_contact", "국방부 보안담당자")
            })
            cat_code = zone.get("category_code")
            if cat_code == "P":
                is_prohibited = True
            elif cat_code == "CTR":
                is_controlled = True
            elif cat_code == "R":
                is_restricted = True
            elif cat_code == "UA":
                is_ua_zone = True

    clean_name = location_name.strip()
    
    if is_prohibited:
        status = "PROHIBITED"
        detailed_explanation = (
            f"⛔ **[{clean_name}] 비행 진단 안내**\n\n"
            f"선택하신 **{clean_name}**은(는) 국가 핵심 보안 시설 보호를 위한 **🔴 비행금지구역(P)**에 해당합니다.\n\n"
            f"💡 **안전 가이드**:\n"
            f"- 사전 비행 승인 없이는 드론 비행이 **엄격히 금지**됩니다.\n"
            f"- 비행을 원하시는 경우, 비행 3~5일 전에 '드론원스톱'을 통해 관할 기관(수도방위사령부/지방항공청)의 승인을 꼭 먼저 받으셔야 합니다.\n"
            f"- 승인 없는 비행 시 최대 300만원의 과태료가 부과될 수 있습니다."
        )
    elif is_controlled or is_restricted:
        status = "CONTROLLED"
        zone_names = ", ".join([z["name"] for z in matched_zones])
        detailed_explanation = (
            f"⚠️ **[{clean_name}] 비행 진단 안내**\n\n"
            f"선택하신 **{clean_name}**은(는) 항공기 이착륙 안전을 위한 **🟡 공항 관제권(CTR)** 또는 **🟠 비행제한구역(R)** [{zone_names}] 영향권입니다.\n\n"
            f"💡 **안전 가이드**:\n"
            f"- 공항 주변 및 군기지 관제구역으로, **비행 전 사전 승인이 필요한 지역**입니다.\n"
            f"- 250g 이하 기체라도 관제권 및 비행제한구역 내에서는 비행승인을 신청하셔야 합니다.\n"
            f"- 3번째 탭 **'📄 드론원스톱 신청서 자동 생성'**에서 입력된 정보를 바탕으로 신청서를 쉽게 다운로드 받아 제출해보세요!"
        )
    elif is_ua_zone:
        status = "UA_FREE"
        detailed_explanation = (
            f"✨ **[{clean_name}] 비행 진단 안내**\n\n"
            f"축하합니다! **{clean_name}**은(는) 드론 이용자를 위해 특별히 지정된 **🟢 드론전용공역(UA)**입니다! 🎉\n\n"
            f"💡 **안전 가이드**:\n"
            f"- 기본 안전수칙 준수 시 자유롭게 비행을 즐기실 수 있습니다.\n"
            f"- 단, 육안 비행(시계비행), 최고 고도 150m 이하 준수 및 촬영 목적·지역에 따른 항공촬영 신청 여부를 확인해 주세요!"
        )
    else:
        status = "OPEN"
        # Determine region name for open Class G airspace
        if "김천" in clean_name or "경북" in clean_name:
            reg_label = "경상북도 김천시"
        elif "대구" in clean_name:
            reg_label = "대구광역시"
        elif "부산" in clean_name or "해운대" in clean_name:
            reg_label = "부산광역시"
        elif "제주" in clean_name or "서귀포" in clean_name:
            reg_label = "제주특별자치도"
        elif "강릉" in clean_name or "강원" in clean_name:
            reg_label = "강원특별자치도"
        elif "전주" in clean_name or "전북" in clean_name:
            reg_label = "전북특별자치도"
        elif "광주" in clean_name or "전남" in clean_name:
            reg_label = "전라남도/광주"
        elif "대전" in clean_name or "충남" in clean_name or "충북" in clean_name:
            reg_label = "충청권"
        else:
            reg_label = clean_name or "대한민국"

        open_zone_name = f"🟢 {reg_label} 비관제공역 (G공역, 자유 비행)"
        detailed_explanation = (
            f"🎉 **[{clean_name}] 비행 진단 안내**\n\n"
            f"선택하신 **{clean_name}** ({reg_label})은(는) 관제권 및 비행금지구역 외곽의 **🟢 비관제 일반 공역(Class G)**입니다!\n\n"
            f"💡 **안전 가이드**:\n"
            f"- 250g 이하 기체는 사전 비행승인이 면제되며, 250g 초과 기체도 고도 150m 이하 시계비행 준수 시 자유 비행이 가능합니다.\n"
            f"- 📷 **항공촬영 유의사항**: 군부대, 보안시설 등이 포함되지 않은 경우 드론원스톱을 통한 항공촬영 확인 후 비행하세요.\n"
            f"- ⚠️ **기본 안전수칙**: 눈에 보이는 거리 내 비행(시계비행), 최고 고도 150m 이하, 일몰 후 야간 비행 금지 수칙을 준수해 주세요!"
        )

    # Primary Contact Details for Drone One-Stop Table
    if matched_zones:
        primary_contacts = {
            "flight_contact": matched_zones[0]["flight_contact"],
            "special_contact": matched_zones[0]["special_contact"],
            "photo_contact": matched_zones[0]["photo_contact"]
        }
    else:
        # Check regional location for open airspace (G)
        if any(k in clean_name for k in ["영남", "경산", "대구", "경북", "김천", "구미", "포항", "안동"]) or (35.5 <= lat <= 36.6 and 128.0 <= lon <= 129.5):
            primary_contacts = {
                "flight_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "photo_contact": "군 담당자 [ ☎ 053-320-6219 ]"
            }
        elif any(k in clean_name for k in ["동의", "부산", "해운대", "부산진구", "울산", "창원", "진주"]) or (34.8 <= lat <= 35.4 and 128.8 <= lon <= 129.4):
            primary_contacts = {
                "flight_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "photo_contact": "군 담당자 [ ☎ 051-730-6209 ]"
            }
        elif any(k in clean_name for k in ["광주", "광산구", "전남", "전북", "목포", "여수", "순천"]) or (34.5 <= lat <= 35.8 and 126.3 <= lon <= 127.5):
            primary_contacts = {
                "flight_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "special_contact": "부산지방항공청(항공운항과) ☎ 051-974-2155",
                "photo_contact": "군 담당자 [ ☎ 062-260-6211 ]"
            }
        elif any(k in clean_name for k in ["제주"]):
            primary_contacts = {
                "flight_contact": "제주지방항공청 ☎ 064-797-6800",
                "special_contact": "제주지방항공청 ☎ 064-797-6831",
                "photo_contact": "군 담당자 [ ☎ 064-797-6800 ]"
            }
        else:
            primary_contacts = {
                "flight_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
                "special_contact": "서울지방항공청(항공운항과) ☎ 032-740-2351",
                "photo_contact": "군 담당자 [ ☎ 02-524-3346 ]"
            }

    return {
        "status": status,
        "zone_name": ", ".join([z["name"] for z in matched_zones]) if matched_zones else open_zone_name,
        "is_prohibited": is_prohibited,
        "is_controlled": is_controlled or is_restricted,
        "is_ua_zone": is_ua_zone,
        "matched_zones": matched_zones,
        "official_legends": OFFICIAL_LEGENDS,
        "official_contacts": primary_contacts,
        "approval_required": is_prohibited or is_controlled or is_restricted,
        "detailed_explanation": detailed_explanation
    }
