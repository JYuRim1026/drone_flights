LEGAL_PENALTIES = [
    {
        "regulation": "항공안전법 제161조 / 제166조 (미승인 비행)",
        "violation": "비행금지구역 / 관제권 내 사전 비행 승인 없이 드론을 비행한 경우",
        "fine_details": "1차 150만원 / 2차 225만원 / 3차 300만원 과태료 부과",
        "severity": "HIGH"
    },
    {
        "regulation": "군사기지 및 군사시설 보호법 제19조 (미승인 촬영)",
        "violation": "국방부 사전 촬영 허가 없이 군사시설, 보안 구역을 항공 촬영한 경우",
        "fine_details": "3년 이하의 징역 또는 3,000만원 이하의 벌금 (형사 처벌)",
        "severity": "CRITICAL"
    },
    {
        "regulation": "항공안전법 시행규칙 제310조 (안전준수사항 위반)",
        "violation": "야간 비행(일몰 후), 비시계 비행(눈으로 안 보이는 거리), 고도 150m 초과 비행",
        "fine_details": "1차 100만원 / 2차 150만원 / 3차 200만원 과태료 부과",
        "severity": "MEDIUM"
    },
    {
        "regulation": "항공안전법 제161조의2 (음주/약물 비행)",
        "violation": "주류(혈중알코올농도 0.02% 이상) 또는 약물 상태에서 드론을 조종한 경우",
        "fine_details": "3년 이하의 징역 또는 3,000만원 이하의 벌금",
        "severity": "CRITICAL"
    }
]

def evaluate_flight_suitability(drone_info, airspace_info, weather_info, location_name="선택 지역"):
    reasons = []
    required_docs = []
    recommendations = []
    score = 100
    
    status_code = "FLYABLE"
    clean_loc = location_name.strip()
    
    # 1. Airspace Check
    if airspace_info.get("is_prohibited"):
        status_code = "PROHIBITED"
        score -= 50
        reasons.append(f"⛔ **비행금지구역(P)**: {airspace_info.get('zone_name')} - 승인 없는 비행 시 엄격히 금지됩니다.")
        required_docs.append({
            "name": "초경량비행장치 비행 승인 신청서",
            "authority": "수도방위사령부 / 서울지방항공청",
            "mandatory": True,
            "desc": "비행금지구역 사전 민원 승인 필수 서류"
        })
    elif airspace_info.get("is_controlled"):
        if status_code != "PROHIBITED":
            status_code = "CAUTION"
        score -= 25
        reasons.append(f"⚠️ **관제권/제한구역(CTR/R)**: {airspace_info.get('zone_name')} - 공항 주변 및 수도권 제한구역으로 비행 승인이 필요합니다.")
        required_docs.append({
            "name": "초경량비행장치 비행 승인 신청서",
            "authority": "지방항공청 / 공군 비행단",
            "mandatory": True,
            "desc": "공항 반경 9.3km 이내 사전 승인 신청서"
        })

    # 2. Camera & Aerial Photography Check
    has_camera = drone_info.get("has_camera", True)
    if has_camera:
        if status_code == "FLYABLE":
            status_code = "CAUTION"
        reasons.append("📷 **항공촬영 여부 확인 필요**: 촬영 목적·지역 등에 따라 드론원스톱을 통한 항공촬영 사전 신청이 필요할 수 있습니다.")
        required_docs.append({
            "name": "항공촬영 허가 신청서",
            "authority": "국방부 / 관할 군부대 (드론원스톱 신청)",
            "mandatory": False,
            "desc": "촬영 목적 및 지역 보안 요건에 따른 항공촬영 사전 신청 안내"
        })
    
    # 3. Weather Check
    wind_speed = weather_info.get("wind_speed", 0.0)
    rain = weather_info.get("rain", 0.0)
    
    if rain >= 1.0:
        status_code = "PROHIBITED"
        score -= 40
        reasons.append(f"🌧️ **보통 이상 강수 ({rain}mm/h)**: 기체 전자부품 침수 고장 및 시계 확보 곤란으로 비행 위험")
    elif rain > 0.0:
        if status_code != "PROHIBITED":
            status_code = "CAUTION"
        score -= 15
        reasons.append(f"🌦️ **약한 이슬비/미세 강수 ({rain}mm/h)**: 미세 강수 감지 (기체 비방수 유의 및 기체 정비 조심)")
    
    if wind_speed >= 9.0:
        status_code = "PROHIBITED"
        score -= 35
        reasons.append(f"💨 **강풍 위험 ({wind_speed}m/s)**: 풍속 9.0m/s 이상으로 기체 제어 불가능")
    elif wind_speed >= 6.0:
        if status_code != "PROHIBITED":
            status_code = "CAUTION"
        score -= 15
        reasons.append(f"🌬️ **풍속 주의 ({wind_speed}m/s)**: 풍속 6.0~8.9m/s 범위로 자세 제어 주의 필요")

    score = max(0, min(100, score))
    
    if status_code == "FLYABLE":
        status_label = "🟢 비행 적합 (자유 비행 가능)"
        summary = f"🎉 {clean_loc}은(는) 기본 비행 승인 제외 공역에 해당하며, 안전수칙 준수 시 비행이 가능합니다!"
    elif status_code == "CAUTION":
        status_label = "🟡 비행 승인 필요 (사전 민원 제출)"
        summary = f"⚠️ {clean_loc}은(는) 공항 관제권/제한구역 또는 미세 강수/풍속 주의 영향권으로 사전 비행/촬영 승인 및 안전 주의가 필요합니다."
    else:
        status_label = "🔴 비행 금지 (안전/보안 위험)"
        summary = f"⛔ {clean_loc}은(는) 비행금지구역(P) 또는 위험 기상(보통 이상 강수/강풍) 규정에 따라 비행이 절대 불허됩니다."

    return {
        "score": score,
        "status_code": status_code,
        "status_label": status_label,
        "summary": summary,
        "detailed_explanation": airspace_info.get("detailed_explanation", summary),
        "reasons": reasons,
        "required_documents": required_docs,
        "legal_penalties": LEGAL_PENALTIES,
        "recommendations": recommendations
    }
