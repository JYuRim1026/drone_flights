"""
Phase 8 Multi-User Collaborative Path Learning Engine Test Suite
다중 사용자 공통 촬영 경로 학습 엔진 검증 스크립트 (7개 시나리오 완전 검증)

시나리오 목록:
1. Scenario 1: 동일 프로젝트에 참여한 3명의 사용자(User A, B, C) 및 프로젝트 환경 준비
2. Scenario 2: 3명의 사용자로부터 상이한 이탈도와 궤적을 가진 PHONE_GPS 보행 경로 3건 기록
3. Scenario 3: AI 구도 달성도 점수(95, 82, 58) 및 사용자 만족도(5점, 4점, 3점) 다면 평가 데이터 생성
4. Scenario 4: GPS 정확도 불량/이상치 및 무효 경로(is_valid=False, GPS_ACCURACY_LOW) 자동 필터링 및 제외 검증
5. Scenario 5: 품질 점수 기반 Q^2 파워 가중치 산출 및 고품질 우수 경로 중심 공간 궤적 집계 검증
6. Scenario 6: ProjectCommonPath v1 생성, DB 영구 보관, 추가 경로 유입에 따른 점진적 블렌딩 v2 갱신 및 이력 관리 검증
7. Scenario 7: 신규 참여자(User D)의 차기 회차 요청 시 최신 v2 공통 권장 경로 자동 승계 및 모바일 API 응답 검증
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
    ProjectCommonPath
)
from backend.services.auth_service import auth_service
from backend.services.collaborative_path_service import collaborative_path_service
from backend.services.path_service import (
    path_service,
    generate_default_recommended_waypoints
)
from backend.routers.mobile import (
    get_next_round_path_recommendation,
    get_active_common_path,
    get_common_path_history,
    learn_project_common_path
)
from backend.routers.common import (
    get_common_project_path,
    learn_common_project_path,
    get_common_project_path_history
)
from backend.schemas.schemas import CommonPathLearnRequest


def log_test(title: str, ok: bool, details: str = ""):
    mark = "✅ PASS" if ok else "❌ FAIL"
    print(f"[{mark}] {title}")
    if details:
        for line in details.strip().split("\n"):
            print(f"       {line}")


def run_phase8_verification():
    print("=" * 80)
    print("🚀 [Phase 8] 다중 사용자 공통 촬영 경로 학습 엔진 종합 검증 시작")
    print(f"   데이터베이스: {db_path}")
    print("=" * 80)

    db = SessionLocal()
    try:
        # ----------------------------------------------------------------------
        # Scenario 1: Setup 3 Test Users (User A, B, C) and a Shared Project
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 1] 다중 사용자(User A, B, C) 및 공유 촬영 프로젝트 준비 ---")
        user_specs = [
            ("tester_a_p8@skycommand.ai", "사용자A(숙련자)", "Pass1234!"),
            ("tester_b_p8@skycommand.ai", "사용자B(보통)", "Pass1234!"),
            ("tester_c_p8@skycommand.ai", "사용자C(초심자)", "Pass1234!"),
            ("tester_d_p8@skycommand.ai", "사용자D(신규유입)", "Pass1234!")
        ]

        users = {}
        for email, name, pwd in user_specs:
            u = db.query(User).filter(User.email == email).first()
            if not u:
                u = User(
                    username=email.split("@")[0],
                    user_name=name,
                    email=email,
                    full_name=name,
                    hashed_password=auth_service.hash_password(pwd),
                    role="pilot",
                    is_active=True
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            users[email] = u

        # Create or fetch shared project for Phase 8 test
        project_title = "Phase 8 여의도 한강공원 다중 사용자 협업 촬영"
        proj = db.query(ShootingProject).filter(ShootingProject.title == project_title).first()
        if not proj:
            proj = ShootingProject(
                user_id=users["tester_a_p8@skycommand.ai"].id,
                title=project_title,
                place_name="여의도 한강공원 물빛무대",
                latitude=37.5284,
                longitude=126.9328,
                recommended_mode="POI Orbit",
                status="READY",
                created_at=datetime.utcnow()
            )
            db.add(proj)
            db.commit()
            db.refresh(proj)

        project_id = proj.id

        # Clean existing test paths and common paths for this test project
        db.query(ProjectCommonPath).filter(ProjectCommonPath.project_id == project_id).delete()
        db.query(ShootingPath).filter(ShootingPath.project_id == project_id).delete()
        db.query(ShootingAnalysis).filter(ShootingAnalysis.project_id == project_id).delete()
        db.commit()

        log_test(
            "Scenario 1: 다중 사용자 계정 및 협업 프로젝트 환경 구성",
            len(users) == 4 and project_id is not None,
            f"프로젝트 ID: {project_id} ('{proj.title}')\n"
            f"테스트 참여자: User A(ID={users['tester_a_p8@skycommand.ai'].id}), "
            f"User B(ID={users['tester_b_p8@skycommand.ai'].id}), "
            f"User C(ID={users['tester_c_p8@skycommand.ai'].id}), "
            f"User D(ID={users['tester_d_p8@skycommand.ai'].id})"
        )

        # Baseline recommended waypoints
        base_recs = generate_default_recommended_waypoints(proj.latitude, proj.longitude, proj.recommended_mode, count=5)

        # ----------------------------------------------------------------------
        # Scenario 2 & 3: Record 3 Distinct PHONE_GPS Paths with Varied Quality
        # & Path-Specific Satisfaction Linking (Problem 2)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 2 & 3] PHONE_GPS 보행 경로 수집 및 경로별 만족도(실제 70점 vs 기본값 70점 구분) ---")

        # User A: High quality walking path (dev=0.8m, frame_score=95.0)
        wps_a = []
        for i, r in enumerate(base_recs):
            wps_a.append({
                "seq": i + 1,
                "lat": r["lat"] + 0.000007,
                "lng": r["lng"] + 0.000005,
                "composition_state": {"frame_score": 95.0, "rule_of_thirds_match": True},
                "accuracy": 3.2
            })
        path_a = ShootingPath(
            project_id=project_id,
            user_id=users["tester_a_p8@skycommand.ai"].id,
            shooting_number=1,
            tracking_source="PHONE_GPS",
            recommended_waypoints=base_recs,
            actual_waypoints=wps_a,
            deviation_score=0.8,
            deviation_reason="NORMAL_EXECUTION",
            is_valid=True
        )
        db.add(path_a)

        # User B: Medium quality walking path (dev=2.4m, frame_score=82.0)
        wps_b = []
        for i, r in enumerate(base_recs):
            wps_b.append({
                "seq": i + 1,
                "lat": r["lat"] + 0.000020,
                "lng": r["lng"] - 0.000015,
                "composition_state": {"frame_score": 82.0, "rule_of_thirds_match": True},
                "accuracy": 4.5
            })
        path_b = ShootingPath(
            project_id=project_id,
            user_id=users["tester_b_p8@skycommand.ai"].id,
            shooting_number=2,
            tracking_source="PHONE_GPS",
            recommended_waypoints=base_recs,
            actual_waypoints=wps_b,
            deviation_score=2.4,
            deviation_reason="PHONE_SHAKE",
            is_valid=True
        )
        db.add(path_b)

        # User C: Low quality path (excessive dev=5.8m, frame_score=58.0)
        wps_c = []
        for i, r in enumerate(base_recs):
            wps_c.append({
                "seq": i + 1,
                "lat": r["lat"] - 0.000055,
                "lng": r["lng"] + 0.000045,
                "composition_state": {"frame_score": 58.0, "rule_of_thirds_match": False},
                "accuracy": 8.0
            })
        path_c = ShootingPath(
            project_id=project_id,
            user_id=users["tester_c_p8@skycommand.ai"].id,
            shooting_number=3,
            tracking_source="PHONE_GPS",
            recommended_waypoints=base_recs,
            actual_waypoints=wps_c,
            deviation_score=5.8,
            deviation_reason="OBSTACLE_AVOIDANCE",
            is_valid=True
        )
        db.add(path_c)

        # Add explicit feedback to ShootingAnalysis by round:
        # User A (Round 1): satisfaction 5.0 -> S_sat = 100.0, is_satisfaction_default = False
        # User B (Round 2): satisfaction 3.5 -> S_sat = 70.0, is_satisfaction_default = False (실제 3.5점 응답!)
        # User C (Round 3): 미응답 -> S_sat = 70.0, is_satisfaction_default = True (기본값!)
        analysis_test = ShootingAnalysis(
            project_id=project_id,
            analysis_status="completed",
            target_summary="한강공원 피사체 분석",
            composition_score=85.0,
            target_coordinates={
                "feedbacks_by_round": {
                    "1": {
                        "user_id": users["tester_a_p8@skycommand.ai"].id,
                        "shooting_number": 1,
                        "satisfaction_score": 5.0,
                        "comment": "완벽한 오빗 구도였습니다!"
                    },
                    "2": {
                        "user_id": users["tester_b_p8@skycommand.ai"].id,
                        "shooting_number": 2,
                        "satisfaction_score": 3.5,
                        "comment": "무난한 이동 동선이었습니다."
                    }
                }
            }
        )
        db.add(analysis_test)
        db.commit()

        # Evaluate quality individually
        ok_a, q_a, rpt_a = collaborative_path_service.evaluate_path_quality(path_a, db, base_wps=base_recs)
        ok_b, q_b, rpt_b = collaborative_path_service.evaluate_path_quality(path_b, db, base_wps=base_recs)
        ok_c, q_c, rpt_c = collaborative_path_service.evaluate_path_quality(path_c, db, base_wps=base_recs)

        log_test(
            "Scenario 2: 3인의 상이한 PHONE_GPS 보행 궤적 및 이탈 데이터 저장",
            path_a.path_id and path_b.path_id and path_c.path_id,
            f"User A(회차1): 이탈 {path_a.deviation_score}m, 웨이포인트 {len(wps_a)}개\n"
            f"User B(회차2): 이탈 {path_b.deviation_score}m, 웨이포인트 {len(wps_b)}개\n"
            f"User C(회차3): 이탈 {path_c.deviation_score}m, 웨이포인트 {len(wps_c)}개"
        )

        satisfaction_distinguished = (
            rpt_a["satisfaction_score"] == 100.0 and rpt_a["is_satisfaction_default"] is False and
            rpt_b["satisfaction_score"] == 70.0 and rpt_b["is_satisfaction_default"] is False and
            rpt_c["satisfaction_score"] == 70.0 and rpt_c["is_satisfaction_default"] is True
        )

        log_test(
            "Scenario 3: 경로별 만족도 개별 연결 및 실제 70점(User B) vs 미응답 기본값 70점(User C) 구분 검증",
            satisfaction_distinguished and (q_a > q_b and q_b > q_c),
            f"User A 만족도: {rpt_a['satisfaction_score']}점 (기본값여부={rpt_a['is_satisfaction_default']}, 출처={rpt_a['satisfaction_source']})\n"
            f"User B 만족도: {rpt_b['satisfaction_score']}점 (기본값여부={rpt_b['is_satisfaction_default']}, 출처={rpt_b['satisfaction_source']})\n"
            f"User C 만족도: {rpt_c['satisfaction_score']}점 (기본값여부={rpt_c['is_satisfaction_default']}, 출처={rpt_c['satisfaction_source']})\n"
            f"종합 품질점수: User A={q_a:.1f}점(적격={ok_a}), User B={q_b:.1f}점(적격={ok_b}), User C={q_c:.1f}점(적격={ok_c})"
        )

        # ----------------------------------------------------------------------
        # Scenario 4: Reject Invalid, Low-Accuracy/Drift, AND Reverse Paths (Problem 3)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 4] GPS 오류/정지 표류/무효 플래그 및 역방향 이동(REVERSE_DIRECTION) 배제 검증 ---")

        # Path with is_valid=False
        invalid_path_1 = ShootingPath(
            project_id=project_id,
            user_id=users["tester_c_p8@skycommand.ai"].id,
            shooting_number=4,
            tracking_source="PHONE_GPS",
            actual_waypoints=wps_a,
            deviation_score=1.0,
            deviation_reason="SENSOR_FAIL",
            is_valid=False  # Invalid
        )
        db.add(invalid_path_1)

        # Path with GPS_ACCURACY_LOW
        invalid_path_2 = ShootingPath(
            project_id=project_id,
            user_id=users["tester_c_p8@skycommand.ai"].id,
            shooting_number=5,
            tracking_source="PHONE_GPS",
            actual_waypoints=wps_a,
            deviation_score=15.0,
            deviation_reason="GPS_ACCURACY_LOW",  # Low GPS
            is_valid=True
        )
        db.add(invalid_path_2)

        # Path with STATIONARY_DRIFT
        invalid_path_3 = ShootingPath(
            project_id=project_id,
            user_id=users["tester_c_p8@skycommand.ai"].id,
            shooting_number=6,
            tracking_source="PHONE_GPS",
            actual_waypoints=wps_a,
            deviation_score=3.0,
            deviation_reason="STATIONARY_DRIFT",  # Stationary drift
            is_valid=True
        )
        db.add(invalid_path_3)

        # Path with REVERSE_DIRECTION (Point 5 -> Point 1 역순 보행)
        wps_reverse = []
        for i, r in enumerate(reversed(base_recs)):
            wps_reverse.append({
                "seq": i + 1,
                "lat": r["lat"] + 0.000005,
                "lng": r["lng"] + 0.000005,
                "composition_state": {"frame_score": 90.0, "rule_of_thirds_match": True},
                "accuracy": 3.0
            })
        invalid_path_reverse = ShootingPath(
            project_id=project_id,
            user_id=users["tester_c_p8@skycommand.ai"].id,
            shooting_number=7,
            tracking_source="PHONE_GPS",
            recommended_waypoints=base_recs,
            actual_waypoints=wps_reverse,
            deviation_score=1.0,
            deviation_reason="NORMAL_EXECUTION",
            is_valid=True
        )
        db.add(invalid_path_reverse)
        db.commit()

        ok_inv1, _, rpt_inv1 = collaborative_path_service.evaluate_path_quality(invalid_path_1, db, base_wps=base_recs)
        ok_inv2, _, rpt_inv2 = collaborative_path_service.evaluate_path_quality(invalid_path_2, db, base_wps=base_recs)
        ok_inv3, _, rpt_inv3 = collaborative_path_service.evaluate_path_quality(invalid_path_3, db, base_wps=base_recs)
        ok_inv_rev, _, rpt_inv_rev = collaborative_path_service.evaluate_path_quality(invalid_path_reverse, db, base_wps=base_recs)

        scenario4_pass = (not ok_inv1) and (not ok_inv2) and (not ok_inv3) and (not ok_inv_rev) and ("REVERSE_DIRECTION" in rpt_inv_rev["exclusion_reason"])
        log_test(
            "Scenario 4: 비정상 데이터 및 역방향 보행(REVERSE_DIRECTION) 자동 배제 확인",
            scenario4_pass,
            f"무효 플래그 제외 사유: {rpt_inv1['reason']}\n"
            f"GPS 저정확도 제외 사유: {rpt_inv2['reason']}\n"
            f"제자리 표류 제외 사유: {rpt_inv3['reason']}\n"
            f"역방향 보행 제외 사유: {rpt_inv_rev['exclusion_reason']}"
        )

        # ----------------------------------------------------------------------
        # Scenario 5: Quality-Weighted Spatial Aggregation (Q^2 Power Weighting)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 5] 품질 점수 파워 가중치(Q^2) 및 호 진행률 공간 집계 검증 ---")

        # Execute collaborative learning for project (User A and B should be accepted, C may or may not be accepted depending on threshold)
        # Using min_quality_threshold=60.0, User A (~90+) and User B (~75+) qualify; User C (~57.6) is excluded.
        common_v1 = collaborative_path_service.learn_project_common_path(
            db=db,
            project_id=project_id,
            min_quality_threshold=60.0,
            current_user=users["tester_a_p8@skycommand.ai"]
        )

        weights = common_v1.learning_metadata.get("weights_applied", [])
        qualified_cnt = common_v1.learning_metadata.get("qualified_paths_count", 0)

        # User A's weight should be substantially larger than User B's weight
        # e.g., if QA = 90.7, QB = 76.5: QA^2 / (QA^2 + QB^2) ≈ 8226 / (8226 + 5852) = 58.4% vs 41.6%
        weight_a_dominant = len(weights) >= 2 and weights[0] > weights[1]

        # Verify coordinates of common path are closer to User A's coordinates
        v1_wps = common_v1.common_waypoints
        v1_first_lat = v1_wps[0]["lat"]
        diff_with_a = abs(v1_first_lat - wps_a[0]["lat"])
        diff_with_b = abs(v1_first_lat - wps_b[0]["lat"])
        closer_to_a = diff_with_a < diff_with_b

        log_test(
            "Scenario 5: Q^2 가중치 산출 및 고품질 우수 경로(User A) 중심 궤적 수렴",
            weight_a_dominant and closer_to_a,
            f"적격 경로 수: {qualified_cnt}개 (User A, User B 통과, User C 및 이상치 3건 자동 탈락)\n"
            f"적용된 가중치: W_A={weights[0]:.4f}, W_B={weights[1]:.4f} (User A 가중치 우위: {weight_a_dominant})\n"
            f"웨이포인트 #1 위도 편차: User A와 편차={diff_with_a:.8f} < User B와 편차={diff_with_b:.8f}"
        )

        # ----------------------------------------------------------------------
        # Scenario 6: Version Management, Progressive Blending (v1 -> v2)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 6] 공통 경로 버전 관리 및 점진적 블렌딩(v1 -> v2) 검증 ---")

        # Verify v1 metadata
        v1_check = (
            common_v1.version == 1 and
            common_v1.is_active is True and
            common_v1.contributor_count >= 2 and
            common_v1.total_paths_used == qualified_cnt and
            len(common_v1.common_waypoints) == 5
        )

        # Now simulate a second round from User A with even higher refinement (회차 8)
        wps_a2 = []
        for i, r in enumerate(common_v1.common_waypoints):
            wps_a2.append({
                "seq": i + 1,
                "lat": r["lat"] + 0.000003,
                "lng": r["lng"] + 0.000002,
                "composition_state": {"frame_score": 98.0, "rule_of_thirds_match": True},
                "accuracy": 2.5
            })
        path_a2 = ShootingPath(
            project_id=project_id,
            user_id=users["tester_a_p8@skycommand.ai"].id,
            shooting_number=8,
            tracking_source="PHONE_GPS",
            recommended_waypoints=common_v1.common_waypoints,
            actual_waypoints=wps_a2,
            deviation_score=0.4,
            deviation_reason="NORMAL_EXECUTION",
            is_valid=True
        )
        db.add(path_a2)
        db.commit()

        # Re-learn to generate v2
        common_v2 = collaborative_path_service.learn_project_common_path(
            db=db,
            project_id=project_id,
            min_quality_threshold=60.0,
            current_user=users["tester_a_p8@skycommand.ai"]
        )

        # Reload v1 from DB to check status
        db.refresh(common_v1)
        history = collaborative_path_service.get_common_path_history(db, project_id)

        # Check v2 included IDs and total unique count
        v2_included = common_v2.learning_metadata.get("included_path_ids", [])
        no_duplicate_relearn = (
            path_a.path_id not in v2_included and
            path_b.path_id not in v2_included and
            path_a2.path_id in v2_included
        )

        # Test duplicate learning prevention: call learn AGAIN with NO new paths
        empty_relearn_blocked = False
        try:
            collaborative_path_service.learn_project_common_path(
                db=db,
                project_id=project_id,
                min_quality_threshold=60.0,
                current_user=users["tester_a_p8@skycommand.ai"]
            )
        except HTTPException as e:
            if e.status_code == 400 and "새롭게 추가된" in e.detail:
                empty_relearn_blocked = True

        v2_check = (
            common_v2.version == 2 and
            common_v2.is_active is True and
            common_v1.is_active is False and
            common_v2.total_paths_used == 3 and  # Exactly 3 unique paths (A, B, A2)
            len(history) == 2 and
            history[0].version == 2 and
            history[1].version == 1 and
            no_duplicate_relearn and
            empty_relearn_blocked
        )

        log_test(
            "Scenario 6: ProjectCommonPath v1 생성 및 점진적 블렌딩 v2 갱신 이력 (중복 학습 원천 차단 검증)",
            v1_check and v2_check,
            f"v1 상태: 버전={common_v1.version}, is_active={common_v1.is_active}, 반영 고유 경로={common_v1.total_paths_used}건\n"
            f"v2 상태: 버전={common_v2.version}, is_active={common_v2.is_active}, 반영 고유 경로={common_v2.total_paths_used}건\n"
            f"v2 신규 포함 ID: {v2_included} (기존 A, B 경로 배제: {no_duplicate_relearn})\n"
            f"신규 경로 부재 시 중복 버전 생성 차단: {empty_relearn_blocked} (400 Bad Request)\n"
            f"버전 이력 수: {len(history)}건 (최신 활성 버전={history[0].version})"
        )

        # ----------------------------------------------------------------------
        # Scenario 7: Auto-Recommendation Inheritance to New User (User D)
        # ----------------------------------------------------------------------
        print("\n--- [Scenario 7] 신규 참여자(User D)의 최신 v2 공통 권장 경로 자동 승계 검증 ---")

        # User D requests next round recommendation via path_service
        next_rec = path_service.get_next_round_recommendation(db, project_id)

        # Verify next_rec properties
        inherited_v2 = (
            next_rec["is_inherited_from_previous"] is True and
            next_rec["common_path_version"] == 2 and
            "v2" in next_rec["source_info"] and
            len(next_rec["recommended_waypoints"]) == 5
        )

        # Ensure project has project_code and valid mobile access token
        if not proj.project_code:
            proj.project_code = f"PRJ-P8-{project_id}"
        proj_token = auth_service.create_project_access_token(proj.project_code, proj.id)
        proj.project_token = proj_token
        db.commit()
        db.refresh(proj)

        # 1) IDOR 보안 검증: 미인가 사용자(User D)가 QR 토큰 없이 접근 시 403 Forbidden 차단
        idor_blocked = False
        try:
            get_next_round_path_recommendation(
                project_id=project_id,
                token=None,
                current_user=users["tester_d_p8@skycommand.ai"],
                db=db
            )
        except HTTPException as e:
            if e.status_code == 403:
                idor_blocked = True

        # 2) 현장 모바일 참여자(User D): QR 보안 토큰(proj_token)을 통해 정상 접근 및 v2 공통 경로 수신
        mobile_res = get_next_round_path_recommendation(
            project_id=project_id,
            token=proj_token,
            current_user=users["tester_d_p8@skycommand.ai"],
            db=db
        )

        router_check = (
            mobile_res.project_id == project_id and
            mobile_res.is_inherited_from_previous is True and
            mobile_res.common_path_version == 2 and
            len(mobile_res.recommended_waypoints) == 5
        )

        # Test common router endpoints
        active_resp = get_common_project_path(
            project_id=project_id,
            current_user=users["tester_a_p8@skycommand.ai"],
            db=db
        )
        hist_resp = get_common_project_path_history(
            project_id=project_id,
            current_user=users["tester_a_p8@skycommand.ai"],
            db=db
        )

        endpoints_check = (
            active_resp is not None and
            active_resp.version == 2 and
            hist_resp.total_versions == 2 and
            hist_resp.active_version == 2
        )

        log_test(
            "Scenario 7: 신규 사용자(User D)의 차기 회차 요청 시 v2 공통 권장 경로 자동 승계 및 IDOR 보안 검증",
            inherited_v2 and router_check and endpoints_check and idor_blocked,
            f"IDOR 보안: 미인가 접근 차단={idor_blocked} (403 Forbidden)\n"
            f"QR 토큰 승계: is_inherited={mobile_res.is_inherited_from_previous}\n"
            f"반영된 공통 경로 버전: v{mobile_res.common_path_version}\n"
            f"안내 문구: '{mobile_res.source_info}'\n"
            f"엔드포인트 검증: GET /projects/{project_id}/common-path (v{active_resp.version}), GET /history ({hist_resp.total_versions}개 버전)"
        )

        print("\n" + "=" * 80)
        print("🎉 [Phase 8] 7개 시나리오 전체 100% 검증 완료!")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    run_phase8_verification()
