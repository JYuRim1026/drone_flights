import re
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from backend.schemas.schemas import (
    FlightSafetyEvaluationRequest,
    FlightSafetyEvaluationResponse
)
from backend.external import external_manager

class FlightSafetyEngine:
    """
    드론 비행 안전 판단 자체 통합 엔진 (6단계)
    - 위치 확인 (VWorld/DB 지오코딩)
    - 공역 확인 (P-73, R-75, 관제권, 비관제 공역)
    - 고도 확인 (법정 150m 제한 및 구역별 고도 검토)
    - 기상 확인 (풍속, 돌풍, 강수량, 시정)
    - 시간 확인 (일출·일몰, 골든타임, 야간비행 제한)
    - 기체 제원 및 법규 확인 (기체 중량, 조종자 자격, 카메라 촬영허가)
    - 종합 판단 (적합 / 주의 필요 / 비행 불가 3단계 판정)
    - 법적 사전 검토 결과와 공식 승인 구분의 명확한 면책 안내
    """

    OFFICIAL_DISCLAIMER = (
        "※ [법적 사전 안전 검토 안내]: 본 진단 결과는 항공안전법, 국토교통부 공역고시 및 실시간 기상·천문 "
        "데이터를 바탕으로 조종자의 자율적인 안전 비행을 돕는 '사전 검토(Preliminary Review)' 결과입니다. "
        "본 결과가 지방항공청 및 국방부의 '공식 비행 승인 및 촬영 허가'를 대신하지 않으므로, 승인 대상 구역 및 "
        "조건에 해당하는 경우 비행 전 반드시 드론원스톱 민원서비스(drone.onestop.go.kr)를 통해 정식 인허가를 취득하십시오."
    )

    @classmethod
    def evaluate_flight_safety(
        cls,
        req: FlightSafetyEvaluationRequest,
        verified_location: Optional[Dict[str, Any]] = None
    ) -> FlightSafetyEvaluationResponse:
        location_str = (req.location or "").strip()

        if not location_str:
            raise ValueError("비행 희망 장소를 입력해 주세요.")

        altitude_m = float(req.altitude_m) if req.altitude_m is not None else None
        drone_weight_g = int(req.drone_weight_g) if req.drone_weight_g is not None else None
        has_camera = req.has_camera
        purpose = req.flight_purpose
        target_date_str = req.target_date
        target_time_str = req.target_time

        blockers: List[str] = []     # 비행 불가 (Red) 사유
        cautions: List[str] = []     # 주의 필요 (Yellow) 사유
        checklist: List[str] = []    # 비행 전 조치 체크리스트
        score = 100

        # =====================================================================
        # 1. 위치 확인 (VWorld & 공간정보 지오코딩)
        # =====================================================================
        loc_res = verified_location if verified_location is not None else external_manager.search_location(location_str)
        lat = loc_res.get("latitude")
        lon = loc_res.get("longitude")
        verified = bool(loc_res.get("verified") and lat is not None and lon is not None)
        resolved_addr = loc_res.get("formatted_address") or loc_res.get("address") or location_str

        # [핵심 원칙 철저 준수] 좌표가 없거나 검증되지 않으면 분석을 일체 진행하지 않는다.
        if not verified or lat is None or lon is None:
            return FlightSafetyEvaluationResponse(
                final_verdict="위치 확인 필요 (UNVERIFIED)",
                verdict_badge="⚪",
                safety_score=None,
                is_preliminary_review=True,
                disclaimer=cls.OFFICIAL_DISCLAIMER,
                step_results={
                    "location_check": {
                        "query": location_str,
                        "resolved_address": "주소 미확인",
                        "latitude": None,
                        "longitude": None,
                        "source": loc_res.get("source", "위치 확인 실패"),
                        "status": "위치 확인 실패 (좌표 없음)"
                    },
                    "airspace_check": {
                        "zone_name": "확인 필요",
                        "zone_type": "UNKNOWN",
                        "approval_required": None,
                        "airspace_status": "좌표 미확인으로 공역 분석 불가",
                        "contact_agency": "-",
                        "contact_phone": "-"
                    },
                    "altitude_check": {
                        "requested_altitude_m": altitude_m,
                        "legal_limit_altitude_m": 150.0,
                        "is_valid": (altitude_m <= 150.0) if altitude_m is not None else True,
                        "status": "고도 규제 기준 대기"
                    },
                    "weather_check": {
                        "temperature_c": None,
                        "wind_speed_ms": None,
                        "wind_gust_ms": None,
                        "wind_direction": "-",
                        "precipitation_mm_h": None,
                        "visibility_km": None,
                        "weather_condition": "확인 필요",
                        "status": "좌표 미확인으로 기상청 조회 불가"
                    },
                    "time_check": {
                        "target_date": target_date_str or "-",
                        "target_time": target_time_str or "-",
                        "sunrise": "-",
                        "sunset": "-",
                        "is_night_violation": False,
                        "status": "좌표 미확인으로 일출·일몰 계산 불가"
                    },
                    "regulatory_check": {
                        "drone_weight_g": drone_weight_g,
                        "has_camera": has_camera,
                        "purpose": purpose
                    }
                },
                actionable_checklist=["정확한 비행 장소(도로명 주소 또는 정식 건물·공원 명칭)를 다시 입력해 주세요."],
                warning_messages=["입력하신 장소의 실제 좌표를 지도에서 확인하지 못했습니다. 검증되지 않은 좌표로는 비행 적합성을 분석하지 않습니다."],
                flight_location={
                    "input_name": location_str,
                    "name": location_str,
                    "address": "",
                    "latitude": None,
                    "longitude": None,
                    "source": loc_res.get("source", "위치 검색 실패"),
                    "verified": False
                },
                flight_conditions={
                    "flight_altitude": altitude_m,
                    "drone_weight": drone_weight_g,
                    "camera_installed": has_camera,
                    "flight_purpose": purpose or "",
                    "flight_date": target_date_str or "",
                    "flight_time": target_time_str or ""
                },
                flight_analysis={
                    "status": "위치 확인 필요 (UNVERIFIED)",
                    "score": None,
                    "summary": f"'{location_str}'의 실제 위치 좌표를 확인하지 못하여 비행 적합성(공역·기상) 분석을 진행할 수 없습니다. 상세 주소나 주변 랜드마크를 추가로 입력해 주세요.",
                    "airspace": {"status": "좌표 미확인으로 공역 조회 불가"},
                    "weather": {"status": "좌표 미확인으로 기상청 조회 불가"},
                    "restrictions": ["정확한 좌표 없이는 비행 승인 필요 여부를 판정할 수 없습니다."],
                    "required_documents": [],
                    "recommendations": ["정확한 도로명 주소 또는 정식 시설명을 입력해 주세요."]
                }
            )

        location_step = {
            "query": location_str,
            "resolved_address": resolved_addr,
            "latitude": lat,
            "longitude": lon,
            "source": loc_res.get("source", "공간정보 지오코딩"),
            "status": "정상 확인 완료"
        }

        # =====================================================================
        # 2. 공역 확인 (국토교통부 드론원스톱 공역 규제)
        # =====================================================================
        air_res = external_manager.check_airspace(lat, lon, location_str)
        zone_name = air_res["zone_name"]
        zone_type = air_res["zone_type"]
        approval_req = air_res["approval_required"]
        contact_agency = air_res["contact_agency"]
        contact_phone = air_res["contact_phone"]

        airspace_status = "비행 가능 (자유 비행)"
        if "금지" in zone_name or "P-73" in zone_name or "P-61" in zone_name or "P-62" in zone_name:
            blockers.append(f"비행금지구역({zone_name}): 국가 핵심 안보/시설 구역으로 사전 특별허가 없이 비행이 절대 불가합니다.")
            score -= 50
            airspace_status = "비행 금지 (Prohibited)"
        elif approval_req:
            cautions.append(f"비행승인 필수({zone_name}): 관제권 또는 비행제한구역으로 지방항공청의 사전 승인이 필요합니다.")
            score -= 20
            airspace_status = "비행 승인 필요 (Restricted/CTR)"
            checklist.append(f"드론원스톱을 통해 {contact_agency} ({contact_phone}) 비행승인 신청 완료하기")
        else:
            checklist.append("비관제 자유비행 공역: 별도 비행승인 절차 없이 자율 비행 가능")

        airspace_step = {
            "zone_name": zone_name,
            "zone_type": zone_type,
            "approval_required": approval_req,
            "airspace_status": airspace_status,
            "contact_agency": contact_agency,
            "contact_phone": contact_phone,
            "guide": air_res.get("flight_permission_guide", "")
        }

        # =====================================================================
        # 3. 고도 확인 (법정 150m AGL 및 장애물 제한표면)
        # =====================================================================
        max_legal_alt = 150.0 # 항공안전법 제129조 기본 고도 한도 150m
        altitude_status = "법정 고도 준수 (양호)"
        
        if altitude_m > max_legal_alt:
            blockers.append(f"법정 고도 초과: 입력 고도({altitude_m}m)가 항공안전법상 상한선(150m)을 초과했습니다. (특별승인 없는 비행 시 과태료 최대 300만원)")
            score -= 30
            altitude_status = "법정 한도 초과 (비행 불가)"
        elif altitude_m > 120.0:
            cautions.append(f"고고도 비행 주의: {altitude_m}m 비행 시 돌풍 위험 증가 및 유인항공기 비행경로 근접 주의")
            score -= 5
            altitude_status = "주의 필요 고도"
            checklist.append("고고도(120m 이상) 비행 시 육안 가시권(VLOS) 상시 유지 및 유인기 회피 준비")
        else:
            checklist.append(f"예정 고도 {altitude_m}m: 150m 이하 안전 고도 기준 만족")

        altitude_step = {
            "requested_altitude_m": altitude_m,
            "legal_limit_altitude_m": max_legal_alt,
            "is_valid": (altitude_m <= max_legal_alt),
            "status": altitude_status
        }

        # =====================================================================
        # 4. 기상 조건 확인 (기상청 실시간/예보 데이터 또는 오프라인 안전 폴백)
        # =====================================================================
        try:
            weather_res = external_manager.get_weather(lat, lon, location_str)
        except Exception as w_err:
            weather_res = {
                "wind_speed_ms": 0.0,
                "wind_gust_ms": 0.0,
                "wind_direction_text": "정보 없음",
                "precipitation_mm_h": 0.0,
                "visibility_km": 10.0,
                "temperature_c": 18.0,
                "weather_condition": "기상 정보 미연동 (현장 확인 필요)",
                "is_safe_to_fly": True,
                "risk_factors": ["기상청 실황 미연동 (비행 전 현장 풍속/강수 직접 확인 필수)"]
            }
            cautions.append("기상청 API 실황 조회 불가 (오프라인 상태) - 비행 전 풍속 및 강수 현장 직접 확인 필수")
            checklist.append("현장 풍속계로 6.5m/s 이하 여부 직접 확인")

        wind_speed = weather_res.get("wind_speed_ms", 0.0)
        wind_gust = weather_res.get("wind_gust_ms", 0.0)
        wind_dir = weather_res.get("wind_direction_text", "북서풍")
        rain = weather_res.get("precipitation_mm_h", 0.0)
        vis_km = weather_res.get("visibility_km", 10.0)
        temp_c = weather_res.get("temperature_c", 18.0)
        w_desc = weather_res.get("weather_condition", "맑음")

        weather_status = "기상 양호 (Safe)"
        if wind_speed >= 10.0 or wind_gust >= 13.0:
            blockers.append(f"기상 악화(강풍): 실시간 풍속 {wind_speed}m/s (돌풍 {wind_gust}m/s)로 기체 조종 상실 위험이 매우 높습니다.")
            score -= 40
            weather_status = "강풍 위험 (비행 불가)"
        elif wind_speed >= 6.5:
            cautions.append(f"풍속 주의: 풍속 {wind_speed}m/s ({wind_dir}) - 초경량 기체 흔들림 및 배터리 소모 급증 주의")
            score -= 15
            weather_status = "풍속 주의 구간"
            checklist.append(f"바람 저항력이 낮은 소형 기체는 강풍 시 안전 착륙 대비")

        if rain > 0.0:
            blockers.append(f"강우/강설 감지: 시간당 {rain}mm 강수로 방수 미지원 드론 침수 및 모터 쇼트 위험")
            score -= 35
            weather_status = "강수 위험 (비행 불가)"

        if vis_km < 5.0:
            cautions.append(f"시정 불량: 가시거리 {vis_km}km로 항공안전법상 법정 시계비행(5km 이상) 기준 미달")
            score -= 10

        weather_step = {
            "temperature_c": temp_c,
            "wind_speed_ms": wind_speed,
            "wind_gust_ms": wind_gust,
            "wind_direction": wind_dir,
            "precipitation_mm_h": rain,
            "visibility_km": vis_km,
            "weather_condition": w_desc,
            "status": weather_status
        }

        # =====================================================================
        # 5. 비행 시간 및 천문 조건 확인 (일출·일몰, 야간비행 금지)
        # =====================================================================
        try:
            solar_res = external_manager.get_solar_times(lat, lon, target_date_str)
        except Exception:
            solar_res = {
                "sunrise": "07:00",
                "sunset": "17:30",
                "evening_golden_hour": {"start": "16:30", "end": "17:30"}
            }
        sunrise_str = solar_res["sunrise"]
        sunset_str = solar_res["sunset"]
        golden_evening = solar_res["evening_golden_hour"]["start"] + " ~ " + solar_res["evening_golden_hour"]["end"]
        time_status = "주간 비행 시간대 준수 (양호)"

        is_night = False
        if target_time_str:
            hour_match = re.search(r"(\d{1,2}):?(\d{2})?", target_time_str)
            if hour_match:
                hr = int(hour_match.group(1))
                if "오후" in target_time_str and hr < 12:
                    hr += 12
                # parse sunset hour
                sunset_parts = sunset_str.split(":")
                sunset_total_min = int(sunset_parts[0]) * 60 + int(sunset_parts[1])
                user_min = hr * 60 + (int(hour_match.group(2)) if hour_match.group(2) else 0)

                if user_min >= sunset_total_min:
                    is_night = True
                    blockers.append(f"야간비행 금지 위반: 희망 시간({target_time_str})은 일몰 시각({sunset_str}) 이후입니다. (항공안전법 제129조 위반, 특별승인 필수)")
                    score -= 40
                    time_status = "야간비행 금지 위반 (비행 불가)"
                elif user_min >= sunset_total_min - 30:
                    cautions.append(f"일몰 직전 비행 주의: 일몰 시각({sunset_str}) 30분 전으로, 일몰 전 안전 착륙 계획 필수")
                    score -= 10
                    time_status = "일몰 직전 주의 시간대"
                    checklist.append(f"일몰 10분 전({sunset_str} 이전)까지 반드시 기체 착륙 완료하기")
        
        if not is_night:
            checklist.append(f"일출({sunrise_str}) ~ 일몰({sunset_str}) 주간 비행 준수")

        time_step = {
            "target_date": solar_res["target_date"],
            "target_time": target_time_str or "주간 시간대",
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "golden_hour_evening": golden_evening,
            "is_night_violation": is_night,
            "status": time_status
        }

        # =====================================================================
        # 6. 기체 제원 및 조종자 자격·촬영 규제 확인
        # =====================================================================
        reg_notes: List[str] = []
        if drone_weight_g <= 250:
            weight_class = "4종 초경량 기체 (250g 이하 완구/소형)"
            required_license = "4종 온라인 교육 이수증"
            reg_notes.append("250g 이하 기체는 비관제 공역에서 고도 150m 이하 비행 시 비행승인이 면제됩니다.")
        elif 250 < drone_weight_g <= 2000:
            weight_class = "4종 무인동력비행장치 (250g 초과 ~ 2kg 이하)"
            required_license = "4종 온라인 교육 이수증 (한국교통안전공단 기체 등록 필수)"
            cautions.append(f"기체 중량 {drone_weight_g}g: 한국교통안전공단 배움터 4종 이수 및 기체 신고 필수")
            reg_notes.append("기체 일련번호를 한국교통안전공단 드론관리시스템(drone.kotsa.or.kr)에 등록해야 합니다.")
            score -= 5
        else:
            weight_class = f"중대형 기체 ({drone_weight_g}g)"
            required_license = "1~3종 국가공인 드론 조종자 자격증 필수"
            cautions.append(f"기체 중량 {drone_weight_g}g: 1~3종 조종자 자격증 및 안전성인증검사 대상")
            score -= 10

        # 카메라 촬영 허가 확인
        if has_camera:
            cautions.append("항공촬영허가 별도 요건: 비행승인과 별개로 국방부 항공촬영 허가 필요 (국가보안시설 미포함 시에도 확인 권고)")
            checklist.append("카메라 촬영 시 드론원스톱 '항공사진 촬영 허가' 별도 신청 여부 확인")
            reg_notes.append("비행 승인과 항공촬영 허가는 서로 다른 법률에 따른 별개 민원입니다.")

        regulatory_step = {
            "drone_weight_g": drone_weight_g,
            "weight_classification": weight_class,
            "required_license": required_license,
            "has_camera": has_camera,
            "purpose": purpose,
            "regulatory_notes": reg_notes
        }

        # =====================================================================
        # 7. 종합 판단 (Synthesis & 3-Tier Classification)
        # =====================================================================
        score = max(10, min(100, score))

        if len(blockers) > 0:
            final_verdict = "비행 불가 (PROHIBITED)"
            verdict_badge = "🔴"
            score = min(score, 45)
        elif len(cautions) > 0:
            final_verdict = "주의 필요 (CAUTION)"
            verdict_badge = "🟡"
            score = max(50, min(score, 79))
        else:
            final_verdict = "적합 (FIT)"
            verdict_badge = "🟢"
            score = max(80, score)

        all_warnings = blockers + cautions

        # 필요 민원 서류 도출
        required_docs: List[str] = []
        if "금지" in zone_name or "P-73" in zone_name:
            required_docs.append("초경량비행장치 비행승인 신청서 (국가보안 1급 비행금지구역 특별보안승인)")
            if has_camera:
                required_docs.append("항공사진 촬영 허가 신청서 (국방부 보안과)")
        elif approval_req or "제한" in zone_name or "CTR" in zone_name or "관제" in zone_name:
            required_docs.append(f"초경량비행장치 비행승인 신청서 ({contact_agency})")
            if has_camera:
                required_docs.append("항공사진 촬영 허가 신청서 (국방부/수도방위사령부)")
        else:
            required_docs.append("사전 비행승인 불필요 (비관제 Class G 공역 시계비행 준수)")
            if has_camera:
                required_docs.append("항공촬영 허가 신청서 (국가보안시설 미포함 시에도 확인 권고)")

        # [요구사항 4] 통합 데이터 구조
        flight_loc_block = {
            "input_name": location_str,
            "name": loc_res.get("name") or resolved_addr,
            "address": resolved_addr,
            "latitude": lat,
            "longitude": lon,
            "source": loc_res.get("source", "공간정보 지오코딩"),
            "verified": True
        }

        flight_cond_block = {
            "flight_altitude": altitude_m,
            "drone_weight": drone_weight_g,
            "camera_installed": has_camera,
            "flight_purpose": purpose or "",
            "flight_date": target_date_str or "",
            "flight_time": target_time_str or ""
        }

        flight_analysis_block = {
            "status": final_verdict,
            "score": score,
            "summary": f"{resolved_addr} 비행 적합성 진단: {final_verdict} (안전 점수: {score}점/100점)",
            "airspace": airspace_step,
            "weather": weather_step,
            "restrictions": all_warnings,
            "required_documents": required_docs,
            "recommendations": checklist
        }

        return FlightSafetyEvaluationResponse(
            final_verdict=final_verdict,
            verdict_badge=verdict_badge,
            safety_score=score,
            is_preliminary_review=True,
            disclaimer=cls.OFFICIAL_DISCLAIMER,
            step_results={
                "location_check": location_step,
                "airspace_check": airspace_step,
                "altitude_check": altitude_step,
                "weather_check": weather_step,
                "time_check": time_step,
                "regulatory_check": regulatory_step
            },
            actionable_checklist=checklist,
            warning_messages=all_warnings,
            flight_location=flight_loc_block,
            flight_conditions=flight_cond_block,
            flight_analysis=flight_analysis_block
        )

flight_safety_engine = FlightSafetyEngine()
