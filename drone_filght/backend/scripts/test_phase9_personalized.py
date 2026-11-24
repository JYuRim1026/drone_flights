"""
Phase 9 Personalized Shooting Path Variation Engine - Final Stabilization Test Suite
개인별 촬영 경로 변형 엔진 최종 보완 및 정밀 검증 스크립트

검증 시나리오 목록:
1. Scenario 1: Cold Start 신규 사용자 맞춤 경로 기본 생성 (STRAIGHT / 공통 경로 유지)
2. Scenario 2: 직선형 성향(STRAIGHT) 사용자 (저이탈도 0.85m, 선형 기법 선호) 자동 분석 및 생성
3. Scenario 3: 단순 GPS 오차/일회성 우회(WALKING_DETOUR, 2.3m) 사용자와 실제 지그재그 선호 사용자의 구분 검증
4. Scenario 4: 실제 지그재그(ZIGZAG) 선호 사용자 동선 생성, 시점/종점 보존, ±2m 교차 변위 및 안전성 한계 경고 메타데이터 검증
5. Scenario 5: 실제 좌표가 등록된 POI 에셋의 정상 경유 동선 생성 (실제 POI 좌표 사용: True)
6. Scenario 6: 좌표가 없는 POI 에셋 및 에셋 부재 시 가상 좌표 생성 차단 및 STRAIGHT 안전 Fallback 검증 (실제 POI 좌표 사용: False)
7. Scenario 7: 사용자별/프로젝트별 DB 분리 저장 및 데이터 격리성 검증
8. Scenario 8: 원본 ProjectCommonPath 불변성(Immutability) 보장 검증
9. Scenario 9: 공통 경로 v1 -> v2 갱신 시 오래된 개인화 경로(v1)의 차기 회차 승계 차단 및 최신 공통 경로(v2) Fallback 검증
10. Scenario 10: 개인화 경로 재생성 후 최신 v2 기반 정상 승계 및 이전 v1 기록의 보존(is_active=False) 검증
11. Scenario 11: 실제 PHONE_GPS 보행 경로와 개인 맞춤 동선 간 이탈도 분석(Cross-Track & Smoothing) 정상 연동
12. Scenario 12: 프로젝트 미인가 사용자(IDOR 공격) 403 Forbidden 권한 차단 검증
13. Scenario 13: 맞춤 동선 vs 공통 동선 기하학적 비교(compare_with_common_path) 지표 산출 검증
"""

import os
import sys
import json
import math
from datetime import datetime
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target Database: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from backend.database import SessionLocal
from backend.models.models import (
    User,
    ShootingProject,
    ShootingPath,
    ShootingAnalysis,
    ProjectCommonPath,
    LocationAsset,
    UserPreferenceScore,
    PersonalizedShootingPath
)
from backend.services.auth_service import auth_service
from backend.services.collaborative_path_service import collaborative_path_service
from backend.services.personalized_path_service import (
    personalized_path_service,
    haversine_distance
)
from backend.services.path_service import (
    path_service,
    generate_default_recommended_waypoints
)
from backend.routers.mobile import (
    get_next_round_path_recommendation
)
from backend.routers.common import (
    get_user_personalized_path,
    generate_user_personalized_path,
    compare_personalized_path
)


def log_test(title: str, ok: bool, details: str = ""):
    mark = "✅ PASS" if ok else "❌ FAIL"
    print(f"[{mark}] {title}")
    if details:
        for line in details.strip().split("\n"):
            print(f"       {line}")


def run_phase9_final_verification():
    print("=" * 80)
    print("🎯 [Phase 9 최종 보완] 개인별 촬영 경로 변형 엔진 정밀 검증 시작")
    print(f"   데이터베이스: {db_path}")
    print("=" * 80)

    db = SessionLocal()
    try:
        # ----------------------------------------------------------------------
        # Setup: Project and Test Users
        # ----------------------------------------------------------------------
        print("\n--- [환경 준비] Phase 9 전용 테스트 프로젝트 및 사용자 구성 ---")
        user_specs = [
            ("user_cold_p9@skycommand.ai", "조종사A(신규)", "cold"),
            ("user_straight_p9@skycommand.ai", "조종사B(직선형)", "straight"),
            ("user_detour_p9@skycommand.ai", "조종사C(일회성우회)", "detour"),
            ("user_zigzag_p9@skycommand.ai", "조종사D(지그재그)", "zigzag"),
            ("user_poi_p9@skycommand.ai", "조종사E(랜드마크경유)", "poi"),
            ("user_unauthorized_p9@skycommand.ai", "외부인F(미인가)", "unauthorized")
        ]

        users = {}
        for email, name, role_key in user_specs:
            u = db.query(User).filter(User.email == email).first()
            if not u:
                u = User(
                    username=email.split("@")[0],
                    user_name=name,
                    email=email,
                    full_name=name,
                    hashed_password=auth_service.hash_password("Pass1234!"),
                    role="pilot",
                    is_active=True
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            if not u.user_id:
                u.user_id = u.id
                db.commit()
                db.refresh(u)
            users[role_key] = u

        # Project Setup
        proj_code = "PRJ-P9-PERSPATH"
        proj = db.query(ShootingProject).filter(ShootingProject.project_code == proj_code).first()
        if not proj:
            proj = ShootingProject(
                user_id=users["cold"].id,
                title="Phase 9 개인별 맞춤 동선 학습 프로젝트",
                project_code=proj_code,
                place_name="서울 광화문 광장",
                latitude=37.5759,
                longitude=126.9768,
                target_date="2026-10-25",
                target_time="오후 15:30 ~ 17:30",
                status="READY",
                created_at=datetime.utcnow()
            )
            db.add(proj)
            db.commit()
            db.refresh(proj)
        else:
            proj.project_token = auth_service.create_project_access_token(proj.project_code, proj.id)
            db.commit()
            db.refresh(proj)

        print(f"   테스트 프로젝트 준비 완료: ID={proj.id}, Code={proj.project_code}")

        # Clean existing test data for reproducible run
        db.query(PersonalizedShootingPath).filter(PersonalizedShootingPath.project_id == proj.id).delete()
        db.query(ProjectCommonPath).filter(ProjectCommonPath.project_id == proj.id).delete()
        db.query(ShootingPath).filter(ShootingPath.project_id == proj.id).delete()
        db.query(ShootingAnalysis).filter(ShootingAnalysis.project_id == proj.id).delete()
        db.query(LocationAsset).filter(LocationAsset.project_id == proj.id).delete()
        db.query(UserPreferenceScore).filter(UserPreferenceScore.user_id.in_([u.id for u in users.values()])).delete()
        db.commit()

        # Seed initial Base Common Path v1
        base_waypoints = [
            {"seq": 1, "lat": 37.575900, "lng": 126.976800, "action": "START_LINE", "description": "광화문 광장 초입 시작"},
            {"seq": 2, "lat": 37.576050, "lng": 126.976820, "action": "FORWARD_SLOW", "description": "중앙 통로 직선 전진"},
            {"seq": 3, "lat": 37.576200, "lng": 126.976840, "action": "MID_FOCUS", "description": "광장 중앙부 전진"},
            {"seq": 4, "lat": 37.576350, "lng": 126.976860, "action": "ACCEL_PAN", "description": "북악산 방면 조준 전진"},
            {"seq": 5, "lat": 37.576500, "lng": 126.976880, "action": "END_FINISH", "description": "광화문 정문 앞 도착"}
        ]
        common_v1 = ProjectCommonPath(
            project_id=proj.id,
            version=1,
            common_waypoints=base_waypoints,
            quality_score=88.5,
            contributor_count=3,
            total_paths_used=3,
            is_active=True,
            learning_metadata={"desc": "Initial base common path v1 for Phase 9"}
        )
        db.add(common_v1)
        db.commit()
        db.refresh(common_v1)
        print(f"   공통 기준 경로 v1 시드 완료: ID={common_v1.id}, Version={common_v1.version}")

        # Seed LocationAsset 1: With Valid Coordinates (이순신 장군 동상)
        poi_asset_valid = LocationAsset(
            project_id=proj.id,
            user_id=users["cold"].id,
            is_common=True,
            asset_type="MONUMENT",
            file_url="/assets/monument_statue.jpg",
            detected_features={
                "title": "이순신 장군 동상",
                "lat": 37.576180,
                "lng": 126.976950,
                "importance": 0.95
            }
        )
        # Seed LocationAsset 2: Without Coordinates (일반 전경 사진)
        poi_asset_no_coord = LocationAsset(
            project_id=proj.id,
            user_id=users["cold"].id,
            is_common=True,
            asset_type="PANORAMA",
            file_url="/assets/panorama_view.jpg",
            detected_features={
                "title": "광장 전체 전경",
                "importance": 0.50
            }
        )
        db.add(poi_asset_valid)
        db.add(poi_asset_no_coord)
        db.commit()
        print("   LocationAsset 2종 시드 완료 (실좌표 보유 에셋 1건 + 좌표 미보유 에셋 1건)")

        # ----------------------------------------------------------------------
        # Scenario 1: Cold Start User Personalization
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 1] Cold Start 신규 사용자 맞춤 경로 생성 ---")
        cold_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["cold"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        sc1_ok = (
            cold_res is not None and
            cold_res.variation_type in ["STRAIGHT", "COLD_START"] and
            cold_res.base_common_version == 1 and
            cold_res.is_active is True and
            len(cold_res.personalized_waypoints) == len(base_waypoints)
        )
        log_test(
            "Scenario 1: Cold Start 사용자 공통 경로 기반 STRAIGHT 맞춤 동선 기본 생성",
            sc1_ok,
            f"유형: {cold_res.variation_type}\n"
            f"사유: {cold_res.generation_reason}\n"
            f"기반 공통 버전: v{cold_res.base_common_version}, 활성 여부: {cold_res.is_active}\n"
            f"웨이포인트 개수: {len(cold_res.personalized_waypoints)}개"
        )

        # ----------------------------------------------------------------------
        # Scenario 2: Straight-type User Personalization
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 2] 직선형(STRAIGHT) 사용자 성향 분석 및 맞춤 경로 생성 ---")
        path_straight = ShootingPath(
            project_id=proj.id,
            user_id=users["straight"].id,
            shooting_number=1,
            is_valid=True,
            tracking_source="PHONE_GPS",
            deviation_score=0.85,
            deviation_reason="NORMAL",
            recommended_waypoints=base_waypoints,
            actual_waypoints=base_waypoints,
            corrected_waypoints=base_waypoints
        )
        db.add(path_straight)
        db.add(UserPreferenceScore(
            user_id=users["straight"].id,
            category="technique",
            preference_value="reveal_flyover",
            preference_score=92.0
        ))
        db.commit()

        straight_profile = personalized_path_service.analyze_user_shooting_profile(db, users["straight"].id, proj.id)
        straight_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["straight"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        sc2_ok = (
            straight_profile["variation_type"] == "STRAIGHT" and
            straight_res.variation_type == "STRAIGHT" and
            straight_res.user_id == users["straight"].id and
            len(straight_res.personalized_waypoints) == len(base_waypoints)
        )
        log_test(
            "Scenario 2: 직선형 성향(저이탈도 0.85m, 선형기법 선호) 자동 분석 및 STRAIGHT 경로 생성",
            sc2_ok,
            f"분석 유형: {straight_profile['variation_type']} (이탈도: {straight_profile['avg_deviation']}m)\n"
            f"생성 결과: {straight_res.variation_type}, 사유: {straight_res.generation_reason}"
        )

        # ----------------------------------------------------------------------
        # Scenario 3: High GPS Deviation Only (One-off Detour) vs Real Zigzag Preference
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 3] 일시적 우회/GPS 오차(2.3m) 사용자와 지그재그 선호 사용자의 구분 검증 ---")
        # User Detour: Had high deviation (2.3m) with reason "WALKING_DETOUR", but NO dynamic preference
        path_detour = ShootingPath(
            project_id=proj.id,
            user_id=users["detour"].id,
            shooting_number=2,
            is_valid=True,
            tracking_source="PHONE_GPS",
            deviation_score=2.30,
            deviation_reason="WALKING_DETOUR",
            recommended_waypoints=base_waypoints,
            actual_waypoints=base_waypoints,
            corrected_waypoints=base_waypoints
        )
        db.add(path_detour)
        db.commit()

        detour_profile = personalized_path_service.analyze_user_shooting_profile(db, users["detour"].id, proj.id)
        detour_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["detour"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        # Must fall back to STRAIGHT, not ZIGZAG!
        sc3_ok = (
            detour_profile["variation_type"] == "STRAIGHT" and
            detour_res.variation_type == "STRAIGHT" and
            "일시적 우회" in detour_profile["reason"]
        )
        log_test(
            "Scenario 3: 단순 GPS 오차/일회성 우회(2.3m) 사용자의 ZIGZAG 오판 방지 및 STRAIGHT 유지 검증",
            sc3_ok,
            f"이탈도: {detour_profile['avg_deviation']}m, 이탈 사유: WALKING_DETOUR\n"
            f"분석 결과: {detour_profile['variation_type']} (오판 방지 성공)\n"
            f"판정 사유: {detour_profile['reason']}"
        )

        # ----------------------------------------------------------------------
        # Scenario 4: Real Zigzag User Personalization & Safety Notice
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 4] 실제 지그재그(ZIGZAG) 선호 사용자 동선 생성 및 안전성 한계 경고 검증 ---")
        path_zigzag = ShootingPath(
            project_id=proj.id,
            user_id=users["zigzag"].id,
            shooting_number=3,
            is_valid=True,
            tracking_source="PHONE_GPS",
            deviation_score=2.25,
            deviation_reason="DYNAMIC_EXPLORE",
            recommended_waypoints=base_waypoints,
            actual_waypoints=base_waypoints,
            corrected_waypoints=base_waypoints
        )
        db.add(path_zigzag)
        db.add(UserPreferenceScore(
            user_id=users["zigzag"].id,
            category="technique",
            preference_value="weaving",
            preference_score=89.0
        ))
        db.commit()

        zigzag_profile = personalized_path_service.analyze_user_shooting_profile(db, users["zigzag"].id, proj.id)
        zigzag_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["zigzag"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        wps_base = base_waypoints
        wps_zig = zigzag_res.personalized_waypoints

        start_match = (
            abs(wps_zig[0]["lat"] - wps_base[0]["lat"]) < 1e-6 and
            abs(wps_zig[0]["lng"] - wps_base[0]["lng"]) < 1e-6
        )
        end_match = (
            abs(wps_zig[-1]["lat"] - wps_base[-1]["lat"]) < 1e-6 and
            abs(wps_zig[-1]["lng"] - wps_base[-1]["lng"]) < 1e-6
        )
        mid_diff = haversine_distance(
            wps_zig[1]["lat"], wps_zig[1]["lng"],
            wps_base[1]["lat"], wps_base[1]["lng"]
        )

        has_safety_notice = "safety_notice" in zigzag_res.style_metadata
        is_safety_unverified = zigzag_res.style_metadata.get("is_safety_verified") is False

        sc4_ok = (
            zigzag_profile["variation_type"] == "ZIGZAG" and
            zigzag_res.variation_type == "ZIGZAG" and
            start_match and end_match and
            (1.5 <= mid_diff <= 2.5) and
            has_safety_notice and is_safety_unverified
        )
        log_test(
            "Scenario 4: ZIGZAG 정규 생성, 시점/종점 보존(±2m) 및 보행 안전성 한계 고지 검증",
            sc4_ok,
            f"분석 유형: {zigzag_profile['variation_type']}\n"
            f"시작/종점 보존: {start_match and end_match}, 중간 변위: {mid_diff:.2f}m\n"
            f"안전성 안내문 포함: {has_safety_notice}\n"
            f"안전 미검증 플래그: is_safety_verified={zigzag_res.style_metadata.get('is_safety_verified')}\n"
            f"고지 내용: {zigzag_res.style_metadata.get('safety_notice', '')[:60]}..."
        )

        # ----------------------------------------------------------------------
        # Scenario 5: POI Waypoint with Valid Coordinates
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 5] 실제 좌표가 등록된 POI 에셋의 정상 경유 동선 생성 ---")
        path_poi = ShootingPath(
            project_id=proj.id,
            user_id=users["poi"].id,
            shooting_number=4,
            is_valid=True,
            tracking_source="PHONE_GPS",
            deviation_score=1.2,
            deviation_reason="COMPOSITION_OPTIMIZED",
            recommended_waypoints=base_waypoints,
            actual_waypoints=base_waypoints,
            corrected_waypoints=base_waypoints
        )
        db.add(path_poi)
        db.add(UserPreferenceScore(
            user_id=users["poi"].id,
            category="technique",
            preference_value="orbit_poi",
            preference_score=96.0
        ))
        db.commit()

        poi_profile = personalized_path_service.analyze_user_shooting_profile(db, users["poi"].id, proj.id)
        poi_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["poi"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        wps_poi = poi_res.personalized_waypoints
        mid_idx = len(wps_poi) // 2
        dist_to_poi_common = haversine_distance(wps_base[mid_idx]["lat"], wps_base[mid_idx]["lng"], 37.576180, 126.976950)
        dist_to_poi_pers = haversine_distance(wps_poi[mid_idx]["lat"], wps_poi[mid_idx]["lng"], 37.576180, 126.976950)

        sc5_ok = (
            poi_profile["variation_type"] == "POI_WAYPOINT" and
            poi_res.variation_type == "POI_WAYPOINT" and
            dist_to_poi_pers < dist_to_poi_common and
            poi_res.style_metadata.get("poi_coord_verified") is True and
            "실제 POI 좌표 사용 여부: True" in poi_res.generation_reason
        )
        log_test(
            "Scenario 5: 등록된 실제 좌표(이순신 장군 동상) 기반 POI_WAYPOINT 유인 및 좌표 검증 플래그",
            sc5_ok,
            f"POI 대상: {poi_res.style_metadata.get('poi_info', {}).get('name')}\n"
            f"피사체 접근 거리: {dist_to_poi_common:.2f}m -> {dist_to_poi_pers:.2f}m (접근 단축: {dist_to_poi_common - dist_to_poi_pers:.2f}m)\n"
            f"poi_coord_verified: {poi_res.style_metadata.get('poi_coord_verified')}\n"
            f"생성 사유: {poi_res.generation_reason}"
        )

        # ----------------------------------------------------------------------
        # Scenario 6: No Coordinates in POI Asset -> Blocked & Fallback to STRAIGHT
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 6] 좌표 미등록 POI 에셋의 가상 좌표 생성 차단 및 STRAIGHT Fallback ---")
        # Create temporary project with NO valid POI coordinates
        proj_no_poi = ShootingProject(
            user_id=users["poi"].id,
            title="POI 좌표 부재 테스트 프로젝트",
            project_code="PRJ-P9-NOPOI",
            place_name="미확인 야외 공터",
            latitude=37.5500,
            longitude=126.9200,
            status="READY",
            created_at=datetime.utcnow()
        )
        db.add(proj_no_poi)
        db.commit()
        db.refresh(proj_no_poi)

        # Seed LocationAsset with NO lat/lng
        asset_empty = LocationAsset(
            project_id=proj_no_poi.id,
            user_id=users["poi"].id,
            is_common=True,
            asset_type="LANDMARK",
            file_url="/assets/unknown.jpg",
            detected_features={"note": "좌표 없는 사진"}
        )
        db.add(asset_empty)
        db.commit()

        # Seed Common Path for this project
        common_no_poi = ProjectCommonPath(
            project_id=proj_no_poi.id,
            version=1,
            common_waypoints=base_waypoints,
            quality_score=80.0,
            contributor_count=1,
            total_paths_used=1,
            is_active=True
        )
        db.add(common_no_poi)
        db.commit()

        # Request POI_WAYPOINT explicitly
        fallback_res = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj_no_poi.id,
            user_id=users["poi"].id,
            preferred_variation_type="POI_WAYPOINT",
            force_regenerate=True
        )

        sc6_ok = (
            fallback_res.variation_type == "STRAIGHT" and  # Fallback to STRAIGHT
            fallback_res.style_metadata.get("poi_coord_verified") is False and
            "실제 POI 좌표 사용 여부: False" in fallback_res.generation_reason and
            "중심 조형물" not in fallback_res.generation_reason  # No fake monument created!
        )
        log_test(
            "Scenario 6: 좌표 미등록 에셋 시 가상 좌표(+4.5m) 생성 차단 및 STRAIGHT 안전 대체 검증",
            sc6_ok,
            f"요청 유형: POI_WAYPOINT -> 최종 생성 유형: {fallback_res.variation_type}\n"
            f"poi_coord_verified: {fallback_res.style_metadata.get('poi_coord_verified')}\n"
            f"대체 사유: {fallback_res.generation_reason}"
        )

        # ----------------------------------------------------------------------
        # Scenario 7: Separation of Storage Between Users & Projects
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 7] 사용자별/프로젝트별 DB 분리 저장 및 데이터 격리성 검증 ---")
        paths_in_db = db.query(PersonalizedShootingPath).filter(
            PersonalizedShootingPath.project_id == proj.id
        ).all()
        user_ids_saved = {p.user_id: p.variation_type for p in paths_in_db}

        sc7_ok = (
            len(paths_in_db) == 5 and  # cold, straight, detour, zigzag, poi
            users["cold"].id in user_ids_saved and
            users["straight"].id in user_ids_saved and
            users["detour"].id in user_ids_saved and
            users["zigzag"].id in user_ids_saved and
            users["poi"].id in user_ids_saved and
            user_ids_saved[users["detour"].id] == "STRAIGHT" and
            user_ids_saved[users["zigzag"].id] == "ZIGZAG" and
            user_ids_saved[users["poi"].id] == "POI_WAYPOINT"
        )
        log_test(
            "Scenario 7: PersonalizedShootingPath 독립 저장 및 사용자별 격리 검증",
            sc7_ok,
            f"저장된 맞춤 동선 레코드 수: {len(paths_in_db)}개\n"
            f"사용자별 맵핑: {user_ids_saved}"
        )

        # ----------------------------------------------------------------------
        # Scenario 8: Immutability of Original Common Path
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 8] 원본 ProjectCommonPath 불변성(Immutability) 보장 검증 ---")
        current_common = db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == proj.id,
            ProjectCommonPath.version == 1
        ).first()

        wps_now = current_common.common_waypoints
        common_unchanged = (
            len(wps_now) == len(base_waypoints) and
            all(
                abs(wps_now[i]["lat"] - base_waypoints[i]["lat"]) < 1e-9 and
                abs(wps_now[i]["lng"] - base_waypoints[i]["lng"]) < 1e-9
                for i in range(len(base_waypoints))
            ) and
            current_common.quality_score == 88.5 and
            current_common.total_paths_used == 3
        )
        log_test(
            "Scenario 8: 개인 맞춤 경로 다량 생성 후에도 원본 ProjectCommonPath 데이터 완전 불변",
            common_unchanged,
            f"공통 경로 ID: {current_common.id}, 버전: v{current_common.version}\n"
            f"품질 점수: {current_common.quality_score}점 유지, 웨이포인트 {len(wps_now)}개 불변"
        )

        # ----------------------------------------------------------------------
        # Scenario 9: Common Path Upgrade (v1 -> v2) -> Stale Personalized Path Blocked & Common v2 Fallback
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 9] 공통 경로 v2 갱신 시 노후화된 맞춤 동선 승계 차단 및 최신 공통 경로 Fallback 검증 ---")
        proj_token = auth_service.create_project_access_token(proj.project_code, proj.id)

        # Prior to upgrade: Zigzag user gets personalized path
        recom_before = get_next_round_path_recommendation(
            project_id=proj.id,
            token=proj_token,
            current_user=users["zigzag"],
            db=db
        )
        assert recom_before.is_personalized is True, "v1 시절에는 맞춤 동선 승계되어야 함"

        # Upgrade project common path to v2 with shifted waypoints
        v2_waypoints = [
            {"seq": 1, "lat": 37.575910, "lng": 126.976810, "action": "START_LINE", "description": "v2 개선 시점"},
            {"seq": 2, "lat": 37.576060, "lng": 126.976830, "action": "FORWARD_SLOW", "description": "v2 개선 전진 1"},
            {"seq": 3, "lat": 37.576210, "lng": 126.976850, "action": "MID_FOCUS", "description": "v2 개선 중앙"},
            {"seq": 4, "lat": 37.576360, "lng": 126.976870, "action": "ACCEL_PAN", "description": "v2 개선 전진 2"},
            {"seq": 5, "lat": 37.576510, "lng": 126.976890, "action": "END_FINISH", "description": "v2 개선 종점"}
        ]
        common_v2 = ProjectCommonPath(
            project_id=proj.id,
            version=2,
            common_waypoints=v2_waypoints,
            quality_score=94.0,
            contributor_count=4,
            total_paths_used=5,
            is_active=True,
            learning_metadata={"desc": "Upgraded common path v2"}
        )
        current_common.is_active = False
        db.add(common_v2)
        db.commit()

        # Now: User Zigzag has NOT regenerated their path yet (base_common_version = 1, latest = 2)
        # Calling next recommendation must BLOCK stale personalized path and FALLBACK to common v2!
        recom_stale = get_next_round_path_recommendation(
            project_id=proj.id,
            token=proj_token,
            current_user=users["zigzag"],
            db=db
        )

        sc9_ok = (
            recom_stale.is_personalized is False and  # Stale personalized path blocked!
            recom_stale.common_path_version == 2 and   # Delivered common path v2!
            recom_stale.recommended_waypoints[0]["description"] == "v2 개선 시점" and
            "노후화되어 최신 v2 공통 권장 동선으로 대체 제공" in recom_stale.source_info
        )
        log_test(
            "Scenario 9: 공통 경로 v2 갱신 시 노후화(v1 기반) 맞춤 동선 승계 차단 및 최신 공통 v2 안전 Fallback 검증",
            sc9_ok,
            f"맞춤 승계 차단: is_personalized={recom_stale.is_personalized}\n"
            f"대체된 공통 버전: v{recom_stale.common_path_version}\n"
            f"안내 메시지: {recom_stale.source_info}\n"
            f"전달된 1번 웨이포인트: {recom_stale.recommended_waypoints[0]['description']}"
        )

        # ----------------------------------------------------------------------
        # Scenario 10: Regenerate Personalized Path -> Latest v2 Inheritance & Historical Preservation
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 10] 개인화 경로 재생성 후 최신 v2 승계 및 과거 v1 기록 보존 검증 ---")
        pers_zig_v1 = db.query(PersonalizedShootingPath).filter(
            PersonalizedShootingPath.project_id == proj.id,
            PersonalizedShootingPath.user_id == users["zigzag"].id,
            PersonalizedShootingPath.base_common_version == 1
        ).first()

        # User clicks regenerate
        pers_zig_v2 = personalized_path_service.generate_personalized_path(
            db=db,
            project_id=proj.id,
            user_id=users["zigzag"].id,
            preferred_variation_type="AUTO",
            force_regenerate=True
        )

        # Re-query v1 record
        db.refresh(pers_zig_v1)

        # Request next recommendation again -> now should receive newly generated v2 personalized path!
        recom_active_v2 = get_next_round_path_recommendation(
            project_id=proj.id,
            token=proj_token,
            current_user=users["zigzag"],
            db=db
        )

        sc10_ok = (
            pers_zig_v1.is_active is False and           # Past v1 record preserved with is_active=False
            pers_zig_v2.base_common_version == 2 and     # New record based on v2
            pers_zig_v2.is_active is True and            # New record active
            pers_zig_v1.id != pers_zig_v2.id and         # Separate records!
            recom_active_v2.is_personalized is True and  # Successfully inherited!
            recom_active_v2.personalized_variation_type == "ZIGZAG"
        )
        log_test(
            "Scenario 10: 맞춤 동선 재단장 시 v1 기록 보존(is_active=False) 및 신규 v2 맞춤 동선 정상 승계 검증",
            sc10_ok,
            f"과거 v1 레코드 ID={pers_zig_v1.id}, 활성여부={pers_zig_v1.is_active}\n"
            f"신규 v2 레코드 ID={pers_zig_v2.id}, 활성여부={pers_zig_v2.is_active}, 기준버전=v{pers_zig_v2.base_common_version}\n"
            f"차기 회차 추천: is_personalized={recom_active_v2.is_personalized}, type={recom_active_v2.personalized_variation_type}"
        )

        # ----------------------------------------------------------------------
        # Scenario 11: Deviation Analysis Integration (Cross-Track & Smoothing)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 11] 실제 PHONE_GPS 보행 경로와 개인 맞춤 동선 간 이탈도 분석 연동 ---")
        pers_wps = pers_zig_v2.personalized_waypoints
        actual_walking_gps = [
            {"lat": p["lat"] + 0.00001, "lng": p["lng"] + 0.00001, "accuracy": 3.0}
            for p in pers_wps
        ]
        analysis_res = path_service.analyze_and_correct_path(
            recommended_waypoints=pers_wps,
            actual_waypoints=actual_walking_gps,
            project=proj
        )

        sc11_ok = (
            analysis_res is not None and
            analysis_res.get("is_valid") is True and
            analysis_res.get("deviation_score") is not None and
            analysis_res.get("deviation_reason") in ["NORMAL", "PHONE_SHAKE", "DYNAMIC_EXPLORE", "WALKING_DETOUR"]
        )
        log_test(
            "Scenario 11: 맞춤 동선 기반 Phase 6 이탈도 분석(Cross-Track & Smoothing) 정상 연동",
            sc11_ok,
            f"분석 유효성: {analysis_res.get('is_valid')}, 이탈 거리: {analysis_res.get('deviation_score', 0):.2f}m\n"
            f"판정 사유: {analysis_res.get('deviation_reason')}, 권장 가중치 alpha={analysis_res.get('alpha_weight')}"
        )

        # ----------------------------------------------------------------------
        # Scenario 12: Access Control & IDOR Security Check
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 12] IDOR 방지 및 프로젝트 미인가 사용자 403 Forbidden 검증 ---")
        idor_blocked = False
        try:
            auth_service.verify_project_ownership(
                db=db,
                project_identifier=str(proj.id),
                current_user=users["unauthorized"],
                project_token=None
            )
        except HTTPException as he:
            if he.status_code == 403:
                idor_blocked = True

        log_test(
            "Scenario 12: 타인의 프로젝트에 대한 맞춤 동선 무단 접근/생성 403 차단",
            idor_blocked,
            f"미인가 사용자: {users['unauthorized'].email} -> 403 Forbidden 정상 발생"
        )

        # ----------------------------------------------------------------------
        # Scenario 13: Geometric Comparison Endpoint Verification
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 13] 맞춤 동선 vs 공통 동선 기하학적 비교 엔드포인트 검증 ---")
        comp = personalized_path_service.compare_with_common_path(db, pers_zig_v2)

        sc13_ok = (
            comp["variation_type"] == "ZIGZAG" and
            comp["common_path_version"] == 2 and
            comp["is_stale"] is False and
            comp["max_offset_from_common_m"] > 1.0 and
            comp["distance_diff_m"] > 0
        )
        log_test(
            "Scenario 13: compare_with_common_path 변위/거리차/요약 지표 정밀 산출 검증",
            sc13_ok,
            f"공통 거리: {comp['total_common_distance_m']:.2f}m -> 맞춤 거리: {comp['total_personalized_distance_m']:.2f}m (+{comp['distance_diff_m']:.2f}m)\n"
            f"최대 변위: {comp['max_offset_from_common_m']:.2f}m, 평균 변위: {comp['avg_offset_from_common_m']:.2f}m\n"
            f"비교 요약: {comp['comparison_summary']}"
        )

        # Summary
        all_passed = (
            sc1_ok and sc2_ok and sc3_ok and sc4_ok and sc5_ok and
            sc6_ok and sc7_ok and common_unchanged and sc9_ok and
            sc10_ok and sc11_ok and idor_blocked and sc13_ok
        )
        print("\n" + "=" * 80)
        if all_passed:
            print("🎉 [Phase 9 최종 보완] 13개 세부 검증 시나리오 100% 통과 (ALL PASS)!")
        else:
            print("⚠️ [Phase 9 최종 보완] 일부 시나리오 검증 실패. 상세 로그를 확인하세요.")
        print("=" * 80)
        return all_passed

    finally:
        db.close()


if __name__ == "__main__":
    success = run_phase9_final_verification()
    sys.exit(0 if success else 1)
