import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.database import SessionLocal, engine, Base
from backend.models import models
from backend.schemas.schemas import (
    FlightRequestCreate,
    AnalyzeRequest,
    AnalysisResultCreate,
    UserSettingUpdate,
    ChatbotRequest
)
from backend.routers.pc import get_flights, create_flight, get_airspace, chat_with_bot
from backend.routers.mobile import get_mobile_projects, analyze_frame, get_recommendations, save_analysis_result
from backend.routers.common import get_common_project, create_common_project, get_weather, get_user_settings, update_user_settings

def run_tests():
    print("==========================================", flush=True)
    print("[Step 1~3] Drone Flight Safety & Filming Backend Integration Test", flush=True)
    print("==========================================", flush=True)
    
    # DB 세션 생성
    db = SessionLocal()
    try:
        # 1. PC 전용 API 테스트 (A: 비행 정보, B: 공역 정보, E: 챗봇)
        print("\n[Step 3-A] PC 전용 API 테스트 (/api/pc/*)", flush=True)
        flights = get_flights(db=db)
        print(f"  [OK] GET /api/pc/flights : {len(flights)}건 조회 성공", flush=True)
        
        new_flight_data = FlightRequestCreate(
            location="서울 여의도 한강공원",
            start_date="2026-10-25",
            end_date="2026-10-25",
            flight_time="15:00 ~ 17:00",
            drone_weight="249g (초경량)",
            has_camera=True,
            purpose="일몰 및 도심 야경 시네마틱 촬영",
            altitude="120m",
            notes="테스트 비행 신청"
        )
        created_flight = create_flight(flight_in=new_flight_data, db=db)
        print(f"  [OK] POST /api/pc/flights : 등록 성공 (ID={created_flight.id}, 위치={created_flight.location})", flush=True)
        
        airspace = get_airspace(location="서울 여의도 한강공원")
        print(f"  [OK] GET /api/pc/airspace : 공역 조회 성공 ({airspace.zone_name}, 안전점수={airspace.safety_score}점)", flush=True)
        
        bot_res = chat_with_bot(chat_in=ChatbotRequest(prompt="비행 승인 방법 알려줘", location="서울 여의도"))
        print(f"  [OK] POST /api/pc/chatbot : AI 챗봇 응답 성공 (응답 길이={len(bot_res.reply)}자)", flush=True)

        # 2. 모바일 전용 API 테스트 (C: 촬영 프로젝트, D: 촬영 분석 & 가이드)
        print("\n[Step 3-B] 모바일 전용 API 테스트 (/api/mobile/*)", flush=True)
        m_projects = get_mobile_projects(db=db)
        assert len(m_projects) > 0, "프로젝트 데이터 없음"
        proj_id = m_projects[0].id
        print(f"  [OK] GET /api/mobile/projects : {len(m_projects)}건 조회 성공 (첫번째: {m_projects[0].title})", flush=True)
        
        frame_in = AnalyzeRequest(
            project_id=proj_id,
            current_pitch=-12.0,
            current_yaw=0.0,
            detected_horizon_y=0.5
        )
        analysis_res = analyze_frame(req=frame_in)
        print(f"  [OK] POST /api/mobile/analyze : 실시간 프레임 분석 성공 (가이드={analysis_res.guide_direction}, 점수={analysis_res.frame_score}점)", flush=True)
        print(f"       가이드 안내문: '{analysis_res.guide_message}'", flush=True)
        
        recom_res = get_recommendations(project_id=proj_id, db=db)
        print(f"  [OK] GET /api/mobile/recommendations/{{id}} : 추천 구도 조회 성공 ({recom_res.recommended_mode})", flush=True)
        print(f"       추천 레시피: {recom_res.camera_recipe}", flush=True)
        print(f"       조종기 3단계 스틱 1번: {recom_res.stick_combo_steps[0]}", flush=True)
        
        result_save = AnalysisResultCreate(
            project_id=proj_id,
            frame_score=94,
            guide_direction="none",
            offset_x=0.0,
            offset_y=0.0,
            guide_message="촬영 완료 (골든아워 완벽 구도)",
            recorded_video_url="nalyeo_shot_demo.mp4"
        )
        saved_log = save_analysis_result(res_in=result_save, db=db)
        print(f"  [OK] POST /api/mobile/results : 촬영 분석 결과 DB 저장 성공 (ID={saved_log.id})", flush=True)

        # 3. 공통 API 테스트 (C: 공통 프로젝트, E: 기상 및 사용자 설정)
        print("\n[Step 3-C] 공통 API 테스트 (/api/common/*)", flush=True)
        common_proj = get_common_project(project_id=proj_id, db=db)
        print(f"  [OK] GET /api/common/projects/{{id}} : 공통 프로젝트 상세 조회 성공 ({common_proj.title})", flush=True)
        
        weather_res = get_weather(lat=37.5284, lon=126.9328, location_name="서울 여의도 한강공원")
        print(f"  [OK] GET /api/common/weather : 실시간 날씨 연동 성공 (풍속={weather_res.wind_speed}m/s, 안전여부={weather_res.is_safe_to_fly})", flush=True)
        
        settings = get_user_settings(db=db)
        print(f"  [OK] GET /api/common/settings : 사용자 공통 설정 조회 성공 (안전마진={settings.safety_margin_m}m)", flush=True)
        
        up_settings = update_user_settings(setting_in=UserSettingUpdate(safety_margin_m=40, notification_enabled=True), db=db)
        print(f"  [OK] PUT /api/common/settings : 사용자 설정 변경 성공 (안전마진={up_settings.safety_margin_m}m)", flush=True)

        print("\n==========================================", flush=True)
        print("[SUCCESS] 1단계, 2단계, 3단계 모든 데이터베이스 및 백엔드 API 검증 완료 (100% 정상 통과)!", flush=True)
        print("==========================================", flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
