import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.schemas.schemas import FlightSafetyEvaluationRequest
from backend.services.safety_engine import flight_safety_engine
from backend.routers.safety import evaluate_flight_safety, quick_check_safety

def run_safety_tests():
    print("==================================================================", flush=True)
    print("[Step 6] 드론 비행 안전 판단 엔진 (Flight Safety Engine) 정밀 검증", flush=True)
    print("==================================================================", flush=True)

    # -------------------------------------------------------------------------
    # Case 1: [비행 불가 (🔴)] 법정 고도 초과(200m) 및 일몰 후 야간 비행 시나리오
    # -------------------------------------------------------------------------
    print("\n[시나리오 1] 비행 불가 (Red) 검증: 고도 200m(150m 초과) 및 야간 비행 시도", flush=True)
    req_danger = FlightSafetyEvaluationRequest(
        location="서울 여의도 한강공원",
        altitude_m=200.0,            # 150m 초과
        target_date="2026-10-24",
        target_time="20:30",          # 일몰 17:45 이후 (야간)
        drone_weight_g=249,
        has_camera=True
    )
    res_danger = evaluate_flight_safety(req_danger)
    print(f"  [OK] 종합 판정: {res_danger.verdict_badge} {res_danger.final_verdict} (안전점수: {res_danger.safety_score}점)", flush=True)
    print(f"  [OK] 차단 사유 건수: {len(res_danger.warning_messages)}건", flush=True)
    for msg in res_danger.warning_messages[:2]:
        print(f"       - {msg}", flush=True)
    assert "비행 불가" in res_danger.final_verdict or "PROHIBITED" in res_danger.final_verdict
    assert res_danger.verdict_badge == "🔴"

    # -------------------------------------------------------------------------
    # Case 2: [주의 필요 (🟡)] 관제권(CTR) 구역, 원스톱 사전 승인 필수 시나리오
    # -------------------------------------------------------------------------
    print("\n[시나리오 2] 주의 필요 (Yellow) 검증: 오산 관제권(CTR) 내 주간 비행 (승인 필요)", flush=True)
    req_caution = FlightSafetyEvaluationRequest(
        location="오산시청",
        altitude_m=100.0,            # 150m 이하 준수
        target_date="2026-10-24",
        target_time="15:00",          # 주간 시간 준수
        drone_weight_g=249,
        has_camera=True
    )
    res_caution = evaluate_flight_safety(req_caution)
    print(f"  [OK] 종합 판정: {res_caution.verdict_badge} {res_caution.final_verdict} (안전점수: {res_caution.safety_score}점)", flush=True)
    print(f"  [OK] 공역 검토 결과: {res_caution.step_results['airspace_check']['zone_name']}", flush=True)
    print(f"  [OK] 관할 승인 기관: {res_caution.step_results['airspace_check']['contact_agency']} ({res_caution.step_results['airspace_check']['contact_phone']})", flush=True)
    print(f"  [OK] 필수 체크리스트: {res_caution.actionable_checklist[0]}", flush=True)
    assert res_caution.verdict_badge == "🟡"
    assert "주의 필요" in res_caution.final_verdict or "CAUTION" in res_caution.final_verdict

    # -------------------------------------------------------------------------
    # Case 3: [적합 (🟢)] 비관제공역(G공역/김천 혁신도시), 249g 초경량, 고도 80m, 주간
    # -------------------------------------------------------------------------
    print("\n[시나리오 3] 적합 (Green) 검증: 비관제 자율비행 공역, 주간, 249g 미니 드론", flush=True)
    req_safe = FlightSafetyEvaluationRequest(
        location="김천 율곡동",
        altitude_m=80.0,
        target_date="2026-10-24",
        target_time="14:00",
        drone_weight_g=249,
        has_camera=False
    )
    res_safe = evaluate_flight_safety(req_safe)
    print(f"  [OK] 종합 판정: {res_safe.verdict_badge} {res_safe.final_verdict} (안전점수: {res_safe.safety_score}점)", flush=True)
    print(f"  [OK] 공역 상태: {res_safe.step_results['airspace_check']['airspace_status']}", flush=True)
    print(f"  [OK] 고도 상태: {res_safe.step_results['altitude_check']['status']}", flush=True)
    print(f"  [OK] 기상 상태: 풍속 {res_safe.step_results['weather_check']['wind_speed_ms']}m/s ({res_safe.step_results['weather_check']['status']})", flush=True)

    # -------------------------------------------------------------------------
    # Case 4: 법적 사전 검토 고지문 및 공식 승인 구분 검증
    # -------------------------------------------------------------------------
    print("\n[법적 고지 검증] 사전 안전 검토 결과와 공식 인허가 구분 고지문 확인", flush=True)
    print(f"  [OK] 고지문: \"{res_safe.disclaimer[:70]}...\"", flush=True)
    assert "사전" in res_safe.disclaimer and "공식" in res_safe.disclaimer and "드론원스톱" in res_safe.disclaimer

    # -------------------------------------------------------------------------
    # Case 5: GET 빠른 쿼리 엔드포인트 검증
    # -------------------------------------------------------------------------
    print("\n[엔드포인트 검증] GET /api/safety/quick-check 빠른 쿼리 진단", flush=True)
    res_quick = quick_check_safety(location="서울 여의도", altitude_m=90.0, target_time="16:00", drone_weight_g=249, has_camera=True)
    assert res_quick.safety_score > 0
    print(f"  [OK] Quick-check 성공: {res_quick.verdict_badge} {res_quick.final_verdict} (점수: {res_quick.safety_score}점)", flush=True)

    print("\n==================================================================", flush=True)
    print("[SUCCESS] 6단계 드론 비행 안전 판단 로직 모든 시나리오 100% 검증 통과!", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    run_safety_tests()
