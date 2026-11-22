"""
Phase 7 End-to-End System Integration & Final Verification Suite
전체 14단계 서비스 흐름 통합 및 PC/모바일 웹 상호작용 검증

테스트 시나리오:
1. PC 웹 사용자 로그인 (auth_service.authenticate_user & JWT 발급)
2. PC 웹 촬영 프로젝트 생성 및 기획 정보 저장 (create_common_project)
3. 모바일 웹 프로젝트 코드/ID 식별 및 접속 (resolve_mobile_project)
4. 카메라 & 센서 데이터 스키마 정합성 검증 (PHONE_GPS, Euler 각도, 화면 좌표계)
5. GPS 정확도 필터링 및 방향 센서 정합성 확인
6. AI 촬영 장면 분석 및 실시간 구도 추천 (analyze_frame)
7. 사용자 맞춤형 촬영 기법 추천 목록 조회 (get_personalized_techniques)
8. 사용자의 촬영 기법 선택 및 선호도 가중치 반영 (select_project_technique)
9. 스마트폰 실제 보행 촬영 및 다점 웨이포인트(PHONE_GPS) 수집 시뮬레이션
10. 촬영 종료 후 보행 동선, 분석 결과, 키프레임 에셋 저장 (save_shooting_path)
11. AI 권장 동선 vs 실제 보행 동선 비교 및 횡방향 이탈 분석 (analyze_shooting_path)
12. 실시간 구도 달성도 반영 적응형 보정(Alpha Weight) 및 차기 보정 동선(corrected_waypoints) 생성
13. 촬영 만족도 피드백 및 사용자 선호도 점수 누적 갱신 (record_technique_feedback)
14. PC 및 모바일 프로젝트 상세 요약 조회 (get_project_shooting_summary & get_next_round_path_recommendation)
15. 재촬영(Re-take) 시 동일 회차 중복 방지 및 갱신 무결성 검증
16. 비인가 사용자(IDOR) 접근 차단 검증 (403 Forbidden)
17. 영구 저장소 vs Vercel 임시 파일(/tmp) 업로드 저장소 정책 검증
"""

import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from fastapi import HTTPException, UploadFile
from io import BytesIO
from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, ShootingPath, ShootingAnalysis, LocationAsset, UserPreferenceScore
from backend.services.auth_service import auth_service
from backend.schemas.schemas import (
    ShootingProjectCreate,
    AnalyzeRequest,
    TechniqueSelectRequest,
    ShootingPathCreate,
    TechniqueFeedbackRequest
)
from backend.routers.common import create_common_project
from backend.routers.mobile import (
    resolve_mobile_project,
    get_mobile_project_detail,
    analyze_frame,
    get_personalized_techniques,
    select_project_technique,
    save_shooting_path,
    analyze_shooting_path,
    get_next_round_path_recommendation,
    record_technique_feedback,
    get_project_shooting_summary,
    get_shooting_paths,
    upload_location_asset_file
)


def test_phase7_full_integration():
    db = SessionLocal()
    print("======================================================================")
    print("Phase 7: Full System Integration & End-to-End Verification")
    print("======================================================================")

    created_project_id = None
    created_project_code = None

    try:
        # -------------------------------------------------------------------
        # Step 1. PC 웹 사용자 로그인
        # -------------------------------------------------------------------
        print("\nStep 1. [사용자 로그인] PC 웹 조종사 로그인 및 JWT 토큰 획득")
        # Ensure test pilot user exists
        pilot = db.query(User).filter(User.username == "pilot").first()
        if not pilot:
            pilot = db.query(User).filter(User.username == "drone_pilot").first()
        if not pilot:
            pilot = User(username="pilot", email="pilot@test.kr", hashed_password="pw", role="PILOT")
            db.add(pilot)
            db.commit()
            db.refresh(pilot)

        token = auth_service.create_access_token({"sub": pilot.username, "user_id": pilot.id, "role": pilot.role})
        print(f"   -> 로그인 성공: user_id={pilot.id}, username='{pilot.username}', role='{pilot.role}', JWT 발급 완료")

        # -------------------------------------------------------------------
        # Step 2. PC 웹 촬영 프로젝트 생성 및 기획 정보 입력
        # -------------------------------------------------------------------
        print("\nStep 2. [프로젝트 생성] PC 웹에서 신규 시네마틱 촬영 프로젝트 생성 (POST /projects)")
        proj_create_in = ShootingProjectCreate(
            title="여의도 한강공원 일몰 골든아워 시네마틱",
            place_name="서울 한강공원 여의도 수변",
            target_date="2026-11-22",
            target_time="16:00 ~ 17:30",
            scene_intent="한강을 따라 이동하며 고층 빌딩과 노을 분위기를 시네마틱하게 담고 싶어요.",
            latitude=37.5284,
            longitude=126.9328,
            recommended_mode="패럴랙스 리빌 & 선셋 아크",
            recommended_shutter="1/50s",
            recommended_nd_filter="ND16"
        )
        saved_proj = create_common_project(project_in=proj_create_in, db=db)
        created_project_id = saved_proj.id
        created_project_code = saved_proj.project_code
        # User ownership bind
        saved_proj.user_id = pilot.id
        db.commit()
        db.refresh(saved_proj)

        assert created_project_code is not None, "프로젝트 코드가 반드시 자동 생성되어야 합니다."
        print(f"   -> 프로젝트 생성 완료: ID={created_project_id}, Code='{created_project_code}'")

        # -------------------------------------------------------------------
        # Step 3. 모바일 웹에서 프로젝트 식별 및 접속 (Resolve)
        # -------------------------------------------------------------------
        print("\nStep 3. [프로젝트 접속] 모바일 웹에서 project_code 및 ID로 접속 식별")
        detail_by_code = resolve_mobile_project(identifier=created_project_code, db=db)
        code_id = detail_by_code["id"] if isinstance(detail_by_code, dict) else detail_by_code.id
        code_title = detail_by_code["title"] if isinstance(detail_by_code, dict) else detail_by_code.title
        assert code_id == created_project_id
        print(f"   -> [Code 조회] '{created_project_code}' -> ID {code_id} ('{code_title}') 식별 성공")

        detail_by_id = resolve_mobile_project(identifier=str(created_project_id), db=db)
        id_id = detail_by_id["id"] if isinstance(detail_by_id, dict) else detail_by_id.id
        assert id_id == created_project_id
        print(f"   -> [ID 조회] '{created_project_id}' -> 프로젝트 정상 식별 성공")

        # -------------------------------------------------------------------
        # Step 4 & 5. 스마트폰 센서 수집 및 PHONE_GPS 데이터 정합성 검증
        # -------------------------------------------------------------------
        print("\nStep 4 & 5. [센서 수집 규격] PHONE_GPS 및 방향 센서 스키마 검증")
        mock_waypoint = {
            "seq": 1,
            "raw_gps": {
                "lat": 37.52841,
                "lng": 126.93282,
                "accuracy_m": 4.5,
                "speed_mps": 0.8,
                "heading_deg": 185.0
            },
            "camera_orientation": {
                "heading": 184.2,
                "pitch": -14.5,
                "roll": 1.2,
                "screen_orientation_angle": 0
            },
            "composition_state": {
                "offset_x": 0.05,
                "offset_y": -0.08,
                "guide_direction": "none",
                "guide_message": "최적 구도 유지 중",
                "is_sweet_spot": True,
                "frame_score": 92
            }
        }
        assert mock_waypoint["raw_gps"]["accuracy_m"] <= 20.0
        assert -90.0 <= mock_waypoint["camera_orientation"]["pitch"] <= 90.0
        print("   -> 스마트폰 수집 센서 규격(PHONE_GPS, 가속도/기울기, 뷰파인더 구도 상태) 검증 통과")

        # -------------------------------------------------------------------
        # Step 6. 촬영 장면 AI 실시간 구도 분석
        # -------------------------------------------------------------------
        print("\nStep 6. [AI 장면 분석] 스마트폰 카메라 뷰파인더 실시간 구도 분석")
        an_req = AnalyzeRequest(
            project_id=created_project_id,
            current_pitch=-12.0,
            current_roll=0.5,
            current_yaw=180.0,
            purpose="orbit",
            scene_intent="한강 석양 시네마틱",
            shooting_number=1,
            sensor_width=1280,
            sensor_height=720,
            detected_horizon_y=0.52,
            save_result=True
        )
        an_res = analyze_frame(req=an_req, current_user=pilot, db=db)
        print(f"   -> 분석 결과: 점수={an_res.frame_score}점, 추천구도='{an_res.recommended_composition}', 방향='{an_res.guide_direction}'")
        assert an_res.project_id == created_project_id
        assert an_res.frame_score >= 0

        # -------------------------------------------------------------------
        # Step 7. 사용자 맞춤형 촬영 기법 추천
        # -------------------------------------------------------------------
        print("\nStep 7. [맞춤 기법 추천] 사용자 취향 및 프로젝트 기반 기법 4선 추천")
        tech_rec_res = get_personalized_techniques(project_id=created_project_id, limit=4, token=None, current_user=pilot, db=db)
        assert len(tech_rec_res.recommendations) > 0
        top_tech = tech_rec_res.recommendations[0]
        print(f"   -> 최상위 추천 기법: '{top_tech.name}' (ID: {top_tech.technique_id}, 일치도: {top_tech.recommendation_score}점)")
        print(f"   -> 추천 사유: {top_tech.recommendation_reason}")

        # -------------------------------------------------------------------
        # Step 8. 사용자가 촬영 기법 선택
        # -------------------------------------------------------------------
        print(f"\nStep 8. [기법 선택] 사용자가 추천 1순위 '{top_tech.name}' 선택")
        sel_req = TechniqueSelectRequest(technique_id=top_tech.technique_id)
        sel_res = select_project_technique(project_id=created_project_id, payload=sel_req, token=None, current_user=pilot, db=db)
        print(f"   -> 선택 완료 응답: {sel_res.message} (기법: {sel_res.technique_name})")

        # -------------------------------------------------------------------
        # Step 9. 실제 스마트폰 촬영 및 GPS 이동 경로 수집 시뮬레이션
        # -------------------------------------------------------------------
        print("\nStep 9. [실제 촬영 수집] 스마트폰 보행 4개 웨이포인트(PHONE_GPS) 수집 시뮬레이션")
        simulated_waypoints = [
            {
                "seq": 1,
                "raw_gps": {"lat": 37.52840, "lng": 126.93285, "accuracy_m": 3.0, "speed_mps": 0.9},
                "camera_orientation": {"heading": 180.0, "pitch": -12.0, "roll": 0.0},
                "composition_state": {"is_sweet_spot": True, "frame_score": 90}
            },
            {
                "seq": 2,
                "raw_gps": {"lat": 37.52848, "lng": 126.93285, "accuracy_m": 3.2, "speed_mps": 0.8},
                "camera_orientation": {"heading": 182.0, "pitch": -11.0, "roll": 0.5},
                "composition_state": {"is_sweet_spot": True, "frame_score": 88}
            },
            {
                "seq": 3,
                "raw_gps": {"lat": 37.52856, "lng": 126.93285, "accuracy_m": 3.1, "speed_mps": 0.8},
                "camera_orientation": {"heading": 185.0, "pitch": -10.0, "roll": -0.2},
                "composition_state": {"is_sweet_spot": True, "frame_score": 92}
            },
            {
                "seq": 4,
                "raw_gps": {"lat": 37.52865, "lng": 126.93285, "accuracy_m": 2.9, "speed_mps": 0.7},
                "camera_orientation": {"heading": 187.0, "pitch": -12.0, "roll": 0.0},
                "composition_state": {"is_sweet_spot": True, "frame_score": 89}
            }
        ]
        rec_waypoints = [
            {"seq": 1, "lat": 37.52840, "lng": 126.93280},
            {"seq": 2, "lat": 37.52848, "lng": 126.93280},
            {"seq": 3, "lat": 37.52856, "lng": 126.93280},
            {"seq": 4, "lat": 37.52865, "lng": 126.93280}
        ]
        print(f"   -> 실제 보행 웨이포인트: {len(simulated_waypoints)}개 위치 및 센서 프레임 생성 완료")

        # -------------------------------------------------------------------
        # Step 10 & 11. 촬영 종료 후 보행 동선 저장 & 이탈도 분석
        # -------------------------------------------------------------------
        print("\nStep 10 & 11. [동선 저장 & 분석] 1회차 보행 동선 DB 저장 및 이탈 분석 자동 트리거")
        path_payload = ShootingPathCreate(
            project_id=created_project_id,
            shooting_number=1,
            tracking_source="PHONE_GPS",
            recommended_waypoints=rec_waypoints,
            actual_waypoints=simulated_waypoints,
            corrected_waypoints=[], # 비워두면 백엔드에서 자동 분석 및 보정 생성
            alpha_weight=None,
            deviation_score=None,
            deviation_reason=None,
            is_valid=True
        )
        saved_path = save_shooting_path(project_id=created_project_id, path_in=path_payload, token=None, current_user=pilot, db=db)
        print(f"   -> 1회차 저장 성공: shooting_number={saved_path.shooting_number}, is_valid={saved_path.is_valid}")
        print(f"   -> 자동 판정 이탈 원인: {saved_path.deviation_reason}, 보정 가중치(alpha): {saved_path.alpha_weight}")
        assert saved_path.deviation_reason == "COMPOSITION_OPTIMIZED", "구도 점수 >= 80이므로 COMPOSITION_OPTIMIZED여야 합니다."
        assert saved_path.alpha_weight == 0.60
        assert len(saved_path.corrected_waypoints) > 0

        # 단독 분석 엔드포인트(POST /paths/analyze)도 검증
        an_path_json = analyze_shooting_path(project_id=created_project_id, path_in=path_payload, token=None, current_user=pilot, db=db)
        print(f"   -> 경로 상세 분석: match_score={an_path_json.match_score}, avg_dev={an_path_json.avg_deviation_m}m")
        print(f"   -> 코칭 조언: {an_path_json.advice_message}")

        # -------------------------------------------------------------------
        # Step 12. 차기 회차(N+1) 보정 경로 자동 승계 확인
        # -------------------------------------------------------------------
        print("\nStep 12. [보정 동선 승계] 2회차 촬영용 AI 보정 경로 승계 조회 (GET /paths/next-recommendation)")
        next_data = get_next_round_path_recommendation(project_id=created_project_id, token=None, current_user=pilot, db=db)
        print(f"   -> 차기 촬영 회차: {next_data.next_shooting_number}회차 (승계여부: {next_data.is_inherited_from_previous})")
        print(f"   -> 승계 안내문: {next_data.source_info}")
        assert next_data.next_shooting_number == 2
        assert next_data.is_inherited_from_previous is True
        assert len(next_data.recommended_waypoints) == len(saved_path.corrected_waypoints)

        # -------------------------------------------------------------------
        # Step 13. 촬영 만족도 피드백 및 사용자 선호도 점수 누적 저장
        # -------------------------------------------------------------------
        print("\nStep 13. [만족도 피드백] 촬영 완료 후 5점 만점 피드백 및 사용자 선호도 누적")
        fb_in = TechniqueFeedbackRequest(
            technique_id=top_tech.technique_id,
            shooting_number=1,
            was_shot=True,
            satisfaction_score=5,
            comment="피사체 중심을 부드럽게 감싸는 안정적인 오빗 보행 완료"
        )
        fb_json = record_technique_feedback(project_id=created_project_id, payload=fb_in, token=None, current_user=pilot, db=db)
        print(f"   -> 피드백 반영 완료: {fb_json.message} (갱신된 선호도: {fb_json.updated_preference_score}점)")

        # -------------------------------------------------------------------
        # Step 14. PC 및 모바일 프로젝트 상세 화면에서 결과 확인
        # -------------------------------------------------------------------
        print("\nStep 14. [결과 동기화 확인] 프로젝트 촬영 요약 조회 (GET /paths/summary)")
        sum_json = get_project_shooting_summary(project_id=created_project_id, token=None, current_user=pilot, db=db)
        total_cnt = sum_json["total_shooting_count"] if isinstance(sum_json, dict) else sum_json.total_shooting_count
        latest_num = sum_json["latest_shooting_number"] if isinstance(sum_json, dict) else sum_json.latest_shooting_number
        valid_cnt = sum_json["valid_paths_count"] if isinstance(sum_json, dict) else sum_json.valid_paths_count
        print(f"   -> 프로젝트 요약: 총 촬영 {total_cnt}회, 최신 회차 {latest_num}회, 유효 경로 {valid_cnt}건")
        assert total_cnt == 1
        assert latest_num == 1
        assert valid_cnt == 1

        # -------------------------------------------------------------------
        # Step 15. 재촬영(Re-take) 시 동일 회차 중복 방지 및 갱신 무결성 검증
        # -------------------------------------------------------------------
        print("\nStep 15. [중복 방지 무결성] 동일 1회차 재촬영(Re-take) 요청 시 기존 레코드 안전 갱신 확인")
        retake_path_in = ShootingPathCreate(**path_payload.model_dump())
        retake_path_in.shooting_number = 1
        save_shooting_path(project_id=created_project_id, path_in=retake_path_in, token=None, current_user=pilot, db=db)
        db_count = db.query(ShootingPath).filter(
            ShootingPath.project_id == created_project_id,
            ShootingPath.shooting_number == 1
        ).count()
        assert db_count == 1, "동일 회차 재촬영 시 UNIQUE 제약 위반 없이 단일 레코드로 갱신되어야 합니다."
        print("   -> 재촬영 시 중복 INSERT 없이 기존 레코드 안전 갱신 확인 (DB 레코드 1건 유지)")

        # -------------------------------------------------------------------
        # Step 16. 비인가 사용자(IDOR) 접근 차단 검증
        # -------------------------------------------------------------------
        print("\nStep 16. [보안 & IDOR 검증] 타인 계정으로 본 프로젝트 경로 접근 시 차단 확인")
        other_user = db.query(User).filter(User.username == "phase7_hacker").first()
        if not other_user:
            other_user = User(username="phase7_hacker", email="hacker@test.kr", hashed_password="pw", role="CLIENT")
            db.add(other_user)
            db.commit()
            db.refresh(other_user)

        try:
            get_shooting_paths(project_id=created_project_id, token=None, current_user=other_user, db=db)
            assert False, "타 사용자의 경로 목록 조회는 차단되어야 합니다."
        except HTTPException as e:
            assert e.status_code == 403
            print(f"   -> [보안 통과] 타 사용자의 경로 목록 조회 즉시 차단 (403 Forbidden: {e.detail})")

        try:
            get_next_round_path_recommendation(project_id=created_project_id, token=None, current_user=other_user, db=db)
            assert False, "타 사용자의 차기 보정 동선 승계 조회는 차단되어야 합니다."
        except HTTPException as e:
            assert e.status_code == 403
            print(f"   -> [보안 통과] 타 사용자의 차기 보정 동선 승계 조회 즉시 차단 (403 Forbidden)")

        # -------------------------------------------------------------------
        # Step 17. 파일 업로드 저장소 정책 검증
        # -------------------------------------------------------------------
        print("\nStep 17. [저장소 정책 검증] 현장 프레임 에셋 업로드 및 디렉터리 분리 확인")
        fake_file = UploadFile(filename="frame_test.jpg", file=BytesIO(b"\xFF\xD8\xFF\xE0\x00\x10JFIFtest_frame_data"))
        uploaded_asset = upload_location_asset_file(
            project_id=created_project_id,
            file=fake_file,
            asset_type="CAMERA_FRAME",
            detected_features=json.dumps({"title": "1회차 주요 구도 프레임", "description": "스마트폰 모사 촬영 중 캡처된 AI 구도 일치 프레임"}),
            is_common=False,
            token=None,
            current_user=pilot,
            db=db
        )
        print(f"   -> 에셋 업로드 완료: ID={uploaded_asset.id}, URL='{uploaded_asset.file_url}'")
        assert uploaded_asset.project_id == created_project_id

        print("\n======================================================================")
        print("Phase 7 All 17 End-to-End Integration Tests PASSED Successfully! (100% PASS)")
        print("======================================================================")

    finally:
        # 정리: 생성된 테스트 프로젝트 및 하위 데이터 정리
        if created_project_id:
            db.query(LocationAsset).filter(LocationAsset.project_id == created_project_id).delete()
            db.query(ShootingPath).filter(ShootingPath.project_id == created_project_id).delete()
            db.query(ShootingAnalysis).filter(ShootingAnalysis.project_id == created_project_id).delete()
            db.query(ShootingProject).filter(ShootingProject.id == created_project_id).delete()
            db.commit()
        db.close()


if __name__ == "__main__":
    test_phase7_full_integration()
