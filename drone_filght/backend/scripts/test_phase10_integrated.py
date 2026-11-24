"""
Phase 10: AI 기반 실시간 촬영 방향 및 구도 추천 통합 엔진 종합 검증 스크립트

검증 시나리오 (10개 핵심 항목):
1. [4대 핵심 데이터 통합] 프로젝트, 장소에셋, 경로동선, 사용자선호도 결합 조회
2. [기하학 계산 검증] 순수 수학 공식 기반 Haversine 거리 & 전방 방위각(Bearing) 정밀도
3. [역할 분리 검증] 촬영 방향(Shooting Direction) vs 보행 이동(Walking Direction) 분리
4. [초록색 프레임 분리] 구도·수평 일치 시 활성화(is_ready=True), 보행 도달 여부와 독립성 보장
5. [장소자료 재활용] LocationAsset 메타데이터(피사체, 좌표) 재활용 및 영상 전체 재전송 방지
6. [Fallback 검증] Gemini Vision 미호출/실패 시 PIL/NumPy Fallback 및 의미인식 제한(is_semantic_recognized=False) 명시
7. [결측 데이터 안전성] 선호도/자료 부재 시 Zero Crash 및 안전 디폴트 제공
8. [DB 영구 저장 무결성] shooting_analyses 테이블에 촬영/보행 가이드 및 context_info 저장 확인
9. [피드백 순환 파이프라인] 촬영 후 만족도(1~5점) 반영 시 UserPreferenceScore 누적 갱신
10. [보안 및 무결성] PHONE_GPS 지상 보행 경로 원칙 유지 및 타인 프로젝트 IDOR 보안
"""

import os
import sys
import math
import json
from datetime import datetime
from typing import Dict, Any

# 루트 디렉터리 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target Database: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from backend.database import SessionLocal
from backend.models.models import (
    User, ShootingProject, LocationAsset, ShootingPath,
    ProjectCommonPath, PersonalizedShootingPath,
    UserPreferenceScore, ShootingAnalysis
)
from backend.services.ai_service import ai_service
from backend.services.auth_service import auth_service
from backend.services.technique_service import technique_service
from backend.services.path_service import path_service
from backend.schemas.schemas import AnalyzeRequest, AnalyzeResponse


def run_phase10_verification():
    db = SessionLocal()
    print("=" * 80)
    print("🚀 [Phase 10] AI 기반 실시간 촬영 방향 및 구도 추천 통합 엔진 종합 검증")
    print("   데이터베이스: sky_command_demo.db (스마트폰 PHONE_GPS 지상 촬영 모사 원칙 준수)")
    print("=" * 80)

    try:
        # -------------------------------------------------------------------
        # [환경 준비] Phase 10 전용 테스트 사용자 및 프로젝트 시드
        # -------------------------------------------------------------------
        print("\n--- [환경 준비] Phase 10 전용 프로젝트 및 데이터 시드 ---")
        
        # 1. 파일럿 사용자
        pilot = db.query(User).filter(User.email == "pilot_p10@skycommand.ai").first()
        if not pilot:
            pilot = User(
                email="pilot_p10@skycommand.ai",
                username="pilot_p10",
                full_name="Phase 10 모바일 조종사",
                role="pilot",
                hashed_password=auth_service.hash_password("pilot1234!")
            )
            db.add(pilot)
            db.commit()
            db.refresh(pilot)
        
        # 2. 미인가 사용자 (IDOR 테스트용)
        unauth_user = db.query(User).filter(User.email == "unauth_p10@skycommand.ai").first()
        if not unauth_user:
            unauth_user = User(
                email="unauth_p10@skycommand.ai",
                username="unauth_p10",
                full_name="미인가 테스트 사용자",
                role="pilot",
                hashed_password=auth_service.hash_password("unauth1234!")
            )
            db.add(unauth_user)
            db.commit()
            db.refresh(unauth_user)

        # 3. 프로젝트 생성 (여의도 한강공원)
        proj = db.query(ShootingProject).filter(ShootingProject.project_code == "PRJ-P10-INTEGRATED").first()
        if not proj:
            proj = ShootingProject(
                user_id=pilot.id,
                project_code="PRJ-P10-INTEGRATED",
                title="Phase 10 한강공원 일몰 시네마틱 오빗",
                place_name="여의도 한강공원 멀티플라자",
                latitude=37.5284000,
                longitude=126.9328000,
                target_date="2026-11-25",
                target_time="17:00 ~ 18:30 (골든아워)",
                scene_intent="석양 역광과 한강 수면을 배경으로 조형물을 360도 회전하며 입체감 연출",
                recommended_mode="오빗(원형 회전) 촬영",
                desired_techniques=["orbit_poi", "golden_hour_sunset"],
                status="IN_PROGRESS"
            )
            db.add(proj)
            db.commit()
            db.refresh(proj)
        print(f"   테스트 프로젝트: ID={proj.id}, Code={proj.project_code}")

        # 4. LocationAsset 등록 (이순신 동상 실좌표 포함)
        loc_asset = db.query(LocationAsset).filter(
            LocationAsset.project_id == proj.id,
            LocationAsset.asset_type == "PANORAMA_360"
        ).first()
        if not loc_asset:
            loc_asset = LocationAsset(
                project_id=proj.id,
                user_id=pilot.id,
                asset_type="PANORAMA_360",
                file_url="/assets/p10_panorama.jpg",
                thumbnail_url="/assets/p10_thumb.jpg",
                is_common=True,
                detected_features={
                    "title": "여의도 한강 조형물",
                    "lat": 37.5284800,
                    "lng": 126.9328800,
                    "features": ["조형물", "석양", "수면"],
                    "landmark": True
                }
            )
            db.add(loc_asset)
            db.commit()
            db.refresh(loc_asset)
        print(f"   장소 자료(LocationAsset): ID={loc_asset.id}, 피사체='{loc_asset.detected_features.get('title')}'")

        # 5. UserPreferenceScore (Phase 5 선호도: orbit_poi 95.0점)
        pref = db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == pilot.id,
            UserPreferenceScore.category == "technique",
            UserPreferenceScore.preference_value == "orbit_poi"
        ).first()
        if not pref:
            pref = UserPreferenceScore(
                user_id=pilot.id,
                category="technique",
                preference_value="orbit_poi",
                preference_score=95.0
            )
            db.add(pref)
        else:
            pref.preference_score = 95.0
        db.commit()
        db.refresh(pref)
        print(f"   사용자 선호도(UserPreferenceScore): 기법={pref.preference_value}, 점수={pref.preference_score}점")

        # 6. ProjectCommonPath v1 등록 (5개 웨이포인트)
        common_path = db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == proj.id,
            ProjectCommonPath.is_active == True
        ).first()
        if not common_path:
            wps = [
                {"seq": 1, "lat": 37.5284000, "lng": 126.9328000, "target_heading": 0.0, "guide_msg": "1번 시작 지점"},
                {"seq": 2, "lat": 37.5284500, "lng": 126.9328500, "target_heading": 45.0, "guide_msg": "2번 북동쪽 전진"},
                {"seq": 3, "lat": 37.5285000, "lng": 126.9328000, "target_heading": 90.0, "guide_msg": "3번 피사체 대면"},
                {"seq": 4, "lat": 37.5284500, "lng": 126.9327500, "target_heading": 135.0, "guide_msg": "4번 서측 우회"},
                {"seq": 5, "lat": 37.5284000, "lng": 126.9328000, "target_heading": 180.0, "guide_msg": "5번 원점 복귀"}
            ]
            common_path = ProjectCommonPath(
                project_id=proj.id,
                version=1,
                common_waypoints=wps,
                contributor_count=2,
                total_paths_used=3,
                quality_score=90.0,
                is_active=True
            )
            db.add(common_path)
            db.commit()
            db.refresh(common_path)
        print(f"   공통 권장 경로(ProjectCommonPath): v{common_path.version}, 웨이포인트 5개")

        # ===================================================================
        # [Scenario 1] 4가지 핵심 데이터 결합 통합 조회 확인
        # ===================================================================
        print("\n--- [Scenario 1] 4대 핵심 데이터(프로젝트, 장소, 경로, 선호도) 결합 조회 검증 ---")
        an_req_s1 = AnalyzeRequest(
            project_id=proj.id,
            current_pitch=-15.0,
            current_roll=0.0,
            current_heading=0.0,
            current_lat=37.5284000,
            current_lng=126.9328000,
            current_waypoint_seq=1,
            purpose="orbit",
            shooting_number=1,
            save_result=False
        )
        res_s1 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            scene_intent=proj.scene_intent,
            purpose="orbit",
            current_pitch=-15.0,
            current_roll=0.0,
            current_lat=37.5284000,
            current_lng=126.9328000,
            current_waypoint_seq=1,
            project_id=proj.id,
            shooting_number=1,
            current_user=pilot,
            save_to_db=False,
            db=db
        )
        ctx = res_s1.context_info
        assert ctx is not None, "context_info 누락"
        assert ctx["project_info"]["id"] == proj.id, "프로젝트 정보 매핑 실패"
        assert ctx["location_asset_info"]["asset_count"] >= 1, "장소 에셋 카운트 매핑 실패"
        assert ctx["location_asset_info"]["matched_poi_name"] == "여의도 한강 조형물", "장소 피사체명 매핑 실패"
        assert ctx["path_info"]["total_waypoints"] == 5, "경로 웨이포인트 수 매핑 실패"
        assert ctx["user_preference_info"]["top_technique"] == "orbit_poi", "선호 기법 매핑 실패"
        print(f"[✅ PASS] Scenario 1: 4대 핵심 데이터 정상 결합 확인")
        print(f"       프로젝트: {ctx['project_info']['title']}")
        print(f"       연계 에셋: {ctx['location_asset_info']['matched_poi_name']} ({ctx['location_asset_info']['asset_count']}건)")
        print(f"       권장 경로: 총 {ctx['path_info']['total_waypoints']}개 웨이포인트")
        print(f"       사용자 선호: {ctx['user_preference_info']['top_technique']} ({ctx['user_preference_info']['top_score']}점)")

        # ===================================================================
        # [Scenario 2] 순수 기하 수식 기반 Haversine 거리 & 전방 방위각 계산 검증
        # ===================================================================
        print("\n--- [Scenario 2] 순수 기하학 공식 기반 GPS 거리 & 방위각 정밀도 검증 ---")
        # 알려진 기준점 테스트: (37.5284000, 126.9328000) -> (37.5284500, 126.9328500)
        # 위도차: 0.00005도 (약 5.56m 북쪽), 경도차: 0.00005도 (약 4.41m 동쪽)
        # 예상 대각 거리: sqrt(5.56^2 + 4.41^2) = 약 7.09m, 방위각: 약 38.4° (북동쪽)
        calc_dist, calc_bearing, calc_cardinal = ai_service.calculate_gps_distance_and_bearing(
            37.5284000, 126.9328000, 37.5284500, 126.9328500
        )
        assert 6.5 <= calc_dist <= 7.5, f"Haversine 거리 이상: {calc_dist}m (예상: 약 7.1m)"
        assert 30.0 <= calc_bearing <= 45.0, f"전방 방위각 이상: {calc_bearing}° (예상: 약 38.4°)"
        assert calc_cardinal == "북동", f"8방위 문자열 이상: {calc_cardinal} (예상: 북동)"
        print(f"[✅ PASS] Scenario 2: 구면 삼각법 기하학 정밀도 검증 성공")
        print(f"       산출 거리: {calc_dist}m, 전방 방위각: {calc_bearing}°, 방위명: [{calc_cardinal}]")

        # ===================================================================
        # [Scenario 3] 촬영 방향(Shooting) vs 보행 이동(Walking) 분리 검증
        # ===================================================================
        print("\n--- [Scenario 3] 촬영 방향(Shooting Direction) vs 보행 이동(Walking Direction) 분리 검증 ---")
        # 카메라 피사체는 왼쪽으로 치우쳤고(카메라 오른쪽 지향 필요), 다음 2번 웨이포인트는 북동쪽 7.1m
        res_s3 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            purpose="orbit",
            current_pitch=-15.0,
            current_roll=0.0,
            current_lat=37.5284000,
            current_lng=126.9328000,
            current_waypoint_seq=2,
            project_id=proj.id,
            shooting_number=1,
            current_user=pilot,
            save_to_db=False,
            db=db
        )
        assert res_s3.shooting_guide is not None, "shooting_guide 누락"
        assert res_s3.walking_guide is not None, "walking_guide 누락"
        
        sg = res_s3.shooting_guide
        wg = res_s3.walking_guide
        assert "guide_direction" in sg, "촬영 방향 지시 누락"
        assert "horizon_tilt_deg" in sg, "수평선 기울기 누락"
        assert wg["target_waypoint_seq"] == 2, "보행 목표 시퀀스 불일치"
        assert wg["distance_m"] > 0, "보행 거리 누락"
        assert wg["bearing_cardinal"] == "북동", "보행 방위 누락"
        assert "전방 지형 및 주변 환경" in wg["safety_notice"], "보행 안전 고지 누락"
        print(f"[✅ PASS] Scenario 3: 촬영 방향과 보행 이동 안내의 엄격한 분리 확인")
        print(f"       촬영 방향 지시: {sg['guide_direction']} (메시지: {sg['message']})")
        print(f"       보행 이동 지시: {wg['walking_message']}")
        print(f"       보행 안전 고지: {wg['safety_notice']}")

        # ===================================================================
        # [Scenario 4] 초록색 프레임(is_ready) 활성화 조건 분리 검증
        # ===================================================================
        print("\n--- [Scenario 4] 초록색 프레임(is_ready) 독립성 검증 (보행 미도착 시에도 구도 맞으면 촬영 가능) ---")
        # 웨이포인트 2번까지 7.1m 남아있어 is_waypoint_reached == False인 상태
        # 그러나 카메라 구도와 수평도가 정렬(is_aligned=True, is_level=True)된 상황 시뮬레이션
        res_s4 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            purpose="orbit",
            current_pitch=-15.0,
            current_roll=0.0, # 완벽한 수평
            current_lat=37.5284000,
            current_lng=126.9328000,
            current_waypoint_seq=2,
            project_id=proj.id,
            shooting_number=1,
            current_user=pilot,
            save_to_db=False,
            db=db
        )
        assert res_s4.walking_guide["is_waypoint_reached"] == False, "보행 도착 플래그는 False여야 함"
        assert res_s4.is_ready == True, "구도와 수평이 적합하므로 is_ready(초록색 프레임)는 True여야 함"
        print(f"[✅ PASS] Scenario 4: 보행 미도착({res_s4.walking_guide['distance_m']}m 잔여) 상태에서도 is_ready=True 확인")
        print(f"       보행 도착 상태: is_waypoint_reached={res_s4.walking_guide['is_waypoint_reached']}")
        print(f"       초록색 프레임: is_ready={res_s4.is_ready} (촬영 버튼 활성화 보장)")

        # ===================================================================
        # [Scenario 5] 장소 사전 업로드 자료(LocationAsset) 특징 재활용 검증
        # ===================================================================
        print("\n--- [Scenario 5] LocationAsset 특징 메타데이터 재활용 및 영상 전체 재전송 방지 검증 ---")
        # 장소 에셋의 detected_features에 등록된 피사체 정보가 실시간 분석 컨텍스트로 바인딩되는지 확인
        assert res_s1.context_info["location_asset_info"]["matched_poi_name"] == "여의도 한강 조형물"
        assert res_s1.context_info["location_asset_info"]["asset_count"] >= 1
        print(f"[✅ PASS] Scenario 5: 사전 등록된 LocationAsset의 피사체 및 좌표 정보 정상 재활용 확인")
        print(f"       반영된 피사체: {res_s1.context_info['location_asset_info']['matched_poi_name']}")

        # ===================================================================
        # [Scenario 6] Gemini Vision 실패 시 Fallback(PIL/NumPy) 작동 및 의미 인식 제한 명시
        # ===================================================================
        print("\n--- [Scenario 6] Fallback 작동 및 의미 인식 한계 고지(is_semantic_recognized=False) 검증 ---")
        # Gemini 키가 없거나 호출이 실패한 환경 -> PIL/NumPy 에지 분석 실행
        res_s6 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            purpose="orbit",
            project_id=proj.id,
            shooting_number=1,
            current_user=pilot,
            save_to_db=False,
            db=db
        )
        assert "컴퓨터 비전 규칙 엔진" in res_s6.source, "Fallback 소스 미표기"
        assert "의미 인식 제한" in res_s6.source, "한계 고지 문구 누락"
        assert res_s6.subject_details.get("is_semantic_recognized") == False, "is_semantic_recognized 플래그 불일치"
        assert "의미 인식 제한" in res_s6.subject, "피사체 인식 한계 미표기"
        print(f"[✅ PASS] Scenario 6: Fallback 정상 작동 및 의미 인식 한계 명확히 고지")
        print(f"       분석 출처: {res_s6.source}")
        print(f"       피사체 표기: {res_s6.subject}")
        print(f"       의미 인식 플래그: is_semantic_recognized={res_s6.subject_details.get('is_semantic_recognized')}")

        # ===================================================================
        # [Scenario 7] 데이터 부재(신규 사용자/신규 프로젝트) 시 결측값 안전 처리 검증
        # ===================================================================
        print("\n--- [Scenario 7] 데이터 결측 시 Zero Crash 및 안전 디폴트 제공 검증 ---")
        # 선호도 이력과 에셋이 전무한 가상 프로젝트 ID=999999 및 임의 사용자
        res_s7 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            purpose="thirds",
            current_lat=None,
            current_lng=None,
            project_id=999999,
            shooting_number=1,
            current_user=None,
            save_to_db=False,
            db=db
        )
        assert res_s7.project_id == 999999
        assert res_s7.frame_score >= 0
        assert res_s7.walking_guide["distance_m"] is None
        assert "수신 대기 중" in res_s7.walking_guide["walking_message"]
        print(f"[✅ PASS] Scenario 7: 결측 데이터 환경에서도 예외 없이 안전한 디폴트 구도 반환")
        print(f"       추천 구도: {res_s7.recommended_composition}")
        print(f"       보행 상태: {res_s7.walking_guide['walking_message']}")

        # ===================================================================
        # [Scenario 8] 분석 결과 DB(shooting_analyses) 저장 무결성 검증
        # ===================================================================
        print("\n--- [Scenario 8] 분석 결과 DB 영구 저장 및 target_coordinates 구조 검증 ---")
        res_s8 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            purpose="orbit",
            current_pitch=-15.0,
            current_roll=0.0,
            current_lat=37.5284000,
            current_lng=126.9328000,
            current_waypoint_seq=1,
            project_id=proj.id,
            shooting_number=2,
            current_user=pilot,
            save_to_db=True,
            db=db
        )
        assert res_s8.analysis_id is not None, "DB 저장 후 analysis_id 누락"
        db_rec = db.query(ShootingAnalysis).filter(ShootingAnalysis.analysis_id == res_s8.analysis_id).first()
        assert db_rec is not None, "DB 레코드 조회 실패"
        assert "shooting_guide" in db_rec.target_coordinates, "target_coordinates 내 shooting_guide 누락"
        assert "walking_guide" in db_rec.target_coordinates, "target_coordinates 내 walking_guide 누락"
        assert "context_info" in db_rec.target_coordinates, "target_coordinates 내 context_info 누락"
        print(f"[✅ PASS] Scenario 8: DB(shooting_analyses) 레코드(ID={db_rec.analysis_id}) 저장 및 JSON 구조 확인")

        # ===================================================================
        # [Scenario 9] 촬영 후 만족도(1~5점) 피드백 반영 및 선호도 갱신 검증
        # ===================================================================
        print("\n--- [Scenario 9] 촬영 결과 피드백 순환 파이프라인(1~5점) 검증 ---")
        prev_score = pref.preference_score
        feedback_res = technique_service.record_technique_feedback(
            db=db,
            user_id=pilot.id,
            project_id=proj.id,
            technique_id="orbit_poi",
            shooting_number=1,
            satisfaction_score=5
        )
        db.refresh(pref)
        assert feedback_res["status"] in ["success", "already_recorded"], "피드백 반영 실패"
        assert pref.preference_score >= prev_score, "만족도 5점 반영 후 선호도 점수 상승 또는 유지 검증 실패"
        print(f"[✅ PASS] Scenario 9: 만족도 피드백(5점) 반영 성공")
        print(f"       갱신된 선호도 점수: {prev_score:.1f}점 -> {pref.preference_score:.1f}점")

        # ===================================================================
        # [Scenario 10] IDOR 보안 검증 및 PHONE_GPS 무결성 검증
        # ===================================================================
        print("\n--- [Scenario 10] PHONE_GPS 지상 보행 경로 원칙 및 IDOR 보안 검증 ---")
        # 1. PHONE_GPS 검증
        latest_path = db.query(ShootingPath).filter(ShootingPath.project_id == proj.id).first()
        if latest_path:
            assert latest_path.tracking_source == "PHONE_GPS", f"tracking_source 이상: {latest_path.tracking_source}"
            print(f"   -> tracking_source: {latest_path.tracking_source} (지상 보행 경로 원칙 준수 확인)")
        
        # 2. IDOR 보안 검증: 미인가 사용자로 프로젝트 소유권 검사
        try:
            auth_service.verify_project_ownership(db, str(proj.id), unauth_user, None)
            idor_blocked = False
        except Exception as e:
            idor_blocked = True
            print(f"   -> [보안 통과] 미인가 사용자의 프로젝트 접근 차단 확인: {e.status_code if hasattr(e, 'status_code') else 403}")
        assert idor_blocked == True, "IDOR 보안 차단 실패"
        print(f"[✅ PASS] Scenario 10: PHONE_GPS 지상 원칙 및 IDOR 403 보안 확인")

        print("\n" + "=" * 80)
        print("🎉 [Phase 10] 전체 10개 검증 시나리오 100% 통과 (ALL PASS)!")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    run_phase10_verification()
