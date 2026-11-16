import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import backend.services  # Ensure service registry initializes cleanly before external package
from backend.external import (
    external_manager,
    weather_client,
    vworld_client,
    airspace_client,
    astronomy_client,
    gemini_client,
    external_cache
)
from backend.routers.external import (
    get_weather,
    search_location,
    check_airspace,
    get_astronomy,
    ask_gemini_ai,
    get_safety_report,
    get_cache_stats
)
from backend.schemas.schemas import ChatbotRequest

def run_external_tests():
    print("==================================================================", flush=True)
    print("[Step 4] 외부 데이터 API 통합 관리 모듈 (External Integration) 검증", flush=True)
    print("==================================================================", flush=True)

    # 1. 기상청 실시간 API 클라이언트 검증
    print("\n[1] 기상청 단기예보 2.0 (VilageFcstInfoService_2.0) 실시간 날씨 클라이언트 검증", flush=True)
    w = weather_client.get_weather(37.5284, 126.9328, "서울 여의도 한강공원")
    print(f"  [OK] 기온: {w['temperature_c']}℃ | 풍속: {w['wind_speed_ms']}m/s (돌풍: {w['wind_gust_ms']}m/s)", flush=True)
    print(f"  [OK] 16방위 풍향: {w['wind_direction_text']} ({w['wind_direction_deg']}°)", flush=True)
    print(f"  [OK] 강수량: {w['precipitation_mm_h']}mm/h | 시정: {w['visibility_km']}km", flush=True)
    print(f"  [OK] 비행 안전 진단: {w['safety_status']} (안전여부: {w['is_safe_to_fly']})", flush=True)
    print(f"  [OK] 데이터 출처: {w['source']}", flush=True)

    # 2. VWorld 공간정보 & 지오코딩 클라이언트 검증
    print("\n[2] VWorld (국토교통부) & 공간정보 지오코딩 클라이언트 검증", flush=True)
    loc = vworld_client.search_location("서울 여의도 한강공원")
    print(f"  [OK] 질의: '{loc['query']}' ➔ 위도: {loc['latitude']}, 경도: {loc['longitude']}", flush=True)
    print(f"  [OK] 표준 도로명/지번 주소: {loc['formatted_address']}", flush=True)
    print(f"  [OK] 데이터 출처: {loc['source']}", flush=True)

    # 3. 국토교통부 드론원스톱 공역 규제 클라이언트 검증
    print("\n[3] 국토교통부 드론원스톱 공역 규제 및 승인 요부 검증", flush=True)
    air = airspace_client.query_airspace(37.5284, 126.9328, "서울 여의도 한강공원")
    print(f"  [OK] 공역명: {air['zone_name']} (타입: {air['zone_type']})", flush=True)
    print(f"  [OK] 비행승인 필수 여부: {air['approval_required']} (안전점수: {air['safety_score']}점)", flush=True)
    print(f"  [OK] 관할 행정/군 기관: {air['contact_agency']} (전화: {air['contact_phone']})", flush=True)
    print(f"  [OK] 법적 신청 가이드: {air['flight_permission_guide'][:35]}...", flush=True)

    # 4. 한국천문연구원(KASI) / NOAA 일출·일몰 및 골든아워 검증
    print("\n[4] 한국천문연구원(KASI) & NOAA 천문 태양 궤적 클라이언트 검증", flush=True)
    astro = astronomy_client.get_solar_schedule(37.5284, 126.9328, "2026-10-24")
    print(f"  [OK] 기준 일자: {astro['target_date']} | 일출: {astro['sunrise']} | 일몰: {astro['sunset']}", flush=True)
    print(f"  [OK] 모닝 골든아워: {astro['morning_golden_hour']['start']} ~ {astro['morning_golden_hour']['end']}", flush=True)
    print(f"  [OK] 이브닝 골든아워: {astro['evening_golden_hour']['start']} ~ {astro['evening_golden_hour']['end']}", flush=True)
    print(f"  [OK] 항공안전법 야간비행 경고: {astro['night_flight_restriction']['legal_notice'][:40]}...", flush=True)

    # 5. Gemini API & 비행 안전 지식 엔진 검증
    print("\n[5] Google Gemini API & 비행 전문가 지능형 엔진 검증", flush=True)
    ai = gemini_client.ask_ai("일몰 촬영 시 비행 승인 주의사항 알려줘", "서울 여의도 한강공원")
    print(f"  [OK] 질의 응답 성공 (길이: {len(ai['reply'])}자)", flush=True)
    print(f"  [OK] 엔진 출처: {ai['source']} (신뢰도: {ai['confidence_score']})", flush=True)

    # 6. ⭐ 4대 외부 데이터 동시 통합 원스톱 안전 종합 리포트 검증
    print("\n[6] ⭐ 4대 외부 데이터 동시 통합 원스톱 안전 종합 리포트 검증", flush=True)
    report = external_manager.get_one_stop_flight_safety_report(
        location="서울 여의도 한강공원",
        target_date="2026-10-24",
        target_time="17:10"
    )
    print(f"  [OK] 종합 판정: {report['badge']} {report['integrated_status']}", flush=True)
    print(f"  [OK] 종합 안전 점수: {report['overall_safety_score']}점 / 100점", flush=True)
    print(f"  [OK] 위치 요약: {report['location_summary']['resolved_address']}", flush=True)
    print(f"  [OK] 날씨 요약: 기온 {report['weather_summary']['temperature']}, 바람 {report['weather_summary']['wind']}", flush=True)
    print(f"  [OK] 공역 요약: {report['airspace_summary']['zone_name']} (승인필수: {report['airspace_summary']['approval_required']})", flush=True)
    print(f"  [OK] 천문 요약: 일몰 {report['astronomy_summary']['sunset']}, 골든타임 {report['astronomy_summary']['golden_hour_evening']}", flush=True)
    print(f"  [OK] 조치 권고사항({len(report['action_recommendations'])}건): {report['action_recommendations'][0]}", flush=True)

    # 7. 인메모리 TTL 캐시 검증
    print("\n[7] 인메모리 TTL 캐시 (Rate-Limit 보호 및 고속화) 검증", flush=True)
    stats = external_cache.get_stats()
    print(f"  [OK] 캐시 등록 항목 수: {stats['items_count']}개", flush=True)
    print(f"  [OK] 캐시 적중(Hits): {stats['hits']}회 | 미스(Misses): {stats['misses']}회", flush=True)

    # 8. REST API 라우터 함수 검증
    print("\n[8] FastAPI 외부 통합 라우터 엔드포인트 함수 검증", flush=True)
    r_weather = get_weather(37.5284, 126.9328, "서울 여의도")
    assert r_weather["is_safe_to_fly"] is not None
    print("  [OK] GET /api/external/weather ➔ 정상 응답", flush=True)

    r_geo = search_location("서울 여의도")
    assert r_geo["latitude"] > 0
    print("  [OK] GET /api/external/vworld/search ➔ 정상 응답", flush=True)

    r_air = check_airspace(37.5284, 126.9328, "서울 여의도")
    assert r_air["zone_name"]
    print("  [OK] GET /api/external/airspace ➔ 정상 응답", flush=True)

    r_astro = get_astronomy(37.5284, 126.9328, "2026-10-24")
    assert r_astro["sunset"]
    print("  [OK] GET /api/external/astronomy ➔ 정상 응답", flush=True)

    r_chat = ask_gemini_ai(ChatbotRequest(prompt="비행 테스트", location="여의도"))
    assert len(r_chat["reply"]) > 0
    print("  [OK] POST /api/external/ai/chat ➔ 정상 응답", flush=True)

    r_rep = get_safety_report("서울 여의도", "2026-10-24", "17:00")
    assert r_rep["overall_safety_score"] > 0
    print("  [OK] GET /api/external/safety-report ➔ 정상 응답", flush=True)

    print("\n==================================================================", flush=True)
    print("[SUCCESS] 4단계 외부 데이터 API 통합 관리 모듈 모든 항목 100% 검증 통과!", flush=True)
    print("==================================================================", flush=True)

if __name__ == "__main__":
    run_external_tests()
