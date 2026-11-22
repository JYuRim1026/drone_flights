"""
Phase 6 Comprehensive Verification Test Suite
스마트폰 촬영 경로 분석 및 개인화 보정 시스템 검증

검증 항목:
1. 수학적 좌표 변환 및 하버사인(Haversine) / 국소 평면 미터 투영 정합성 검증
2. 저신뢰도 GPS 노이즈 필터링 (accuracy_m > 20m) 및 정지 상태 미세 드리프트(Hovering Drift) 판정 검증
3. Phase 4 실시간 구도 달성도(Sweet Spot 유지율) 기반 적응형 보정(Adaptive Alpha Weighting) 검증
   - 구도 최적화 우회 (Score >= 80): alpha = 0.60, COMPOSITION_OPTIMIZED
   - 단순 보행 우회 (Score < 80, Dev > 3m): alpha = 0.20, WALKING_DETOUR
   - 정상 경로 유지 (Dev <= 2m): alpha = 0.35, NORMAL
4. 선형 보간(Linear Interpolation) 및 차기 보정 경로(corrected_waypoints) 산출 검증
5. 차기 회차(N -> N+1) AI 보정 동선 승계(Inheritance) 기능 검증
6. 백엔드 REST API (POST /paths/analyze, GET /paths/next-recommendation) 및 소유권 보안(IDOR) 검증
7. tracking_source의 PHONE_GPS 보존 및 드론 센서 위조 방지 검증
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

import math
from fastapi import HTTPException
from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, ShootingPath
from backend.services.path_service import path_service
from backend.services.mobile_service import mobile_service
from backend.services.auth_service import auth_service
from backend.schemas.schemas import ShootingPathCreate
from backend.routers.mobile import (
    analyze_shooting_path,
    get_next_round_path_recommendation,
    save_shooting_path
)


def test_phase6():
    db = SessionLocal()
    print("======================================================================")
    print("Phase 6 Verification: AI Shooting Path Analysis & Personalized Correction")
    print("======================================================================")

    # -----------------------------------------------------------------------
    # 0. 테스트용 사용자 및 프로젝트 픽스처 준비
    # -----------------------------------------------------------------------
    test_user_pilot = db.query(User).filter(User.username == "phase6_pilot").first()
    if not test_user_pilot:
        test_user_pilot = User(
            username="phase6_pilot",
            email="phase6_pilot@example.com",
            hashed_password="hashed_pw_test",
            role="PILOT"
        )
        db.add(test_user_pilot)
        db.commit()
        db.refresh(test_user_pilot)

    test_user_other = db.query(User).filter(User.username == "phase6_other").first()
    if not test_user_other:
        test_user_other = User(
            username="phase6_other",
            email="phase6_other@example.com",
            hashed_password="hashed_pw_test",
            role="CLIENT"
        )
        db.add(test_user_other)
        db.commit()
        db.refresh(test_user_other)

    project = db.query(ShootingProject).filter(
        ShootingProject.user_id == test_user_pilot.id,
        ShootingProject.title == "Phase6 테스트 보행 프로젝트"
    ).first()

    if not project:
        project = ShootingProject(
            user_id=test_user_pilot.id,
            title="Phase6 테스트 보행 프로젝트",
            place_name="여의도 한강공원 물빛무대",
            latitude=37.5284,
            longitude=126.9328,
            recommended_mode="POI Orbit",
            status="READY"
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    project_id = project.project_id if hasattr(project, "project_id") and project.project_id else project.id

    # 기존 테스트 잔여 경로 정리
    db.query(ShootingPath).filter(ShootingPath.project_id == project_id).delete()
    db.commit()

    try:
        # -----------------------------------------------------------------------
        # 1. 수학적 좌표 변환 및 하버사인 / 국소 평면 미터 투영 정합성 검증
        # -----------------------------------------------------------------------
        print("\n1. [좌표 변환 수학 검증] Haversine 거리 & 평면 미터 투영 역변환 오차 검증")
        base_lat, base_lng = 37.5284, 126.9328
        dist_zero = path_service.haversine_distance(base_lat, base_lng, base_lat, base_lng)
        assert dist_zero == 0.0, "동일 좌표 간 하버사인 거리는 0.0이어야 합니다."

        # 북쪽으로 약 11.1m (약 0.0001도 위도 차이)
        target_lat = base_lat + 0.0001
        h_dist = path_service.haversine_distance(base_lat, base_lng, target_lat, base_lng)
        print(f"   -> 위도 0.0001도 차이 하버사인 거리: {h_dist:.2f}m")
        assert 10.0 <= h_dist <= 12.0, "위도 0.0001도 이동 시 거리는 약 11.1m이어야 합니다."

        # 국소 평면 미터 변환 및 역변환 정합성 검사 (Round-trip)
        dx, dy = 25.5, -18.2 # 동쪽 25.5m, 남쪽 18.2m
        calc_lat, calc_lng = path_service.meters_to_lat_lon(dx, dy, base_lat, base_lng)
        ret_dx, ret_dy = path_service.lat_lon_to_meters(calc_lat, calc_lng, base_lat, base_lng)
        print(f"   -> 미터 변환 Round-trip 오차: dx오차={abs(dx - ret_dx):.6f}m, dy오차={abs(dy - ret_dy):.6f}m")
        assert abs(dx - ret_dx) < 1e-4, "국소 미터 좌표 변환 오차가 0.1mm 미만이어야 합니다."
        assert abs(dy - ret_dy) < 1e-4, "국소 미터 좌표 변환 오차가 0.1mm 미만이어야 합니다."

        # -----------------------------------------------------------------------
        # 2. 저신뢰도 GPS 노이즈 필터링 (accuracy_m > 20m) 및 정지 드리프트 감지
        # -----------------------------------------------------------------------
        print("\n2. [GPS 노이즈 및 정지 감지] 저신뢰도 GPS(>20m) 제외 및 정지 드리프트 판정")
        noisy_waypoints = [
            {"raw_gps": {"lat": 37.5284, "lng": 126.9328, "accuracy_m": 35.0, "speed_mps": 0.0}},
            {"raw_gps": {"lat": 37.5285, "lng": 126.9329, "accuracy_m": 28.0, "speed_mps": 0.0}},
            {"raw_gps": {"lat": 37.5286, "lng": 126.9330, "accuracy_m": 42.0, "speed_mps": 0.0}},
        ]
        res_noisy = path_service.analyze_and_correct_path(
            recommended_waypoints=[],
            actual_waypoints=noisy_waypoints,
            project=project
        )
        print(f"   -> 저신뢰도 GPS 처리 결과: is_valid={res_noisy['is_valid']}, reason={res_noisy['deviation_reason']}")
        assert res_noisy["is_valid"] is False, "accuracy > 20m 데이터만 있는 경우 is_valid는 False여야 합니다."
        assert res_noisy["deviation_reason"] == "GPS_ACCURACY_LOW", "저신뢰 GPS 원인이 GPS_ACCURACY_LOW여야 합니다."

        # 정지 상태 미세 오차(총 변위 < 2.5m, 이동 속도 없음)
        stationary_waypoints = [
            {"raw_gps": {"lat": 37.528400, "lng": 126.932800, "accuracy_m": 3.0, "speed_mps": 0.0}},
            {"raw_gps": {"lat": 37.528405, "lng": 126.932805, "accuracy_m": 3.2, "speed_mps": 0.0}},
            {"raw_gps": {"lat": 37.528402, "lng": 126.932803, "accuracy_m": 3.1, "speed_mps": 0.0}},
        ]
        res_stat = path_service.analyze_and_correct_path(
            recommended_waypoints=[],
            actual_waypoints=stationary_waypoints,
            project=project
        )
        print(f"   -> 정지 상태 판정 결과: is_valid={res_stat['is_valid']}, reason={res_stat['deviation_reason']}")
        assert res_stat["is_valid"] is False, "정지 상태 미세 드리프트는 is_valid가 False여야 합니다."
        assert res_stat["deviation_reason"] == "STATIONARY_DRIFT", "원인이 STATIONARY_DRIFT여야 합니다."

        # -----------------------------------------------------------------------
        # 3. Phase 4 구도 달성도(Sweet Spot 유지율) 기반 적응형 보정(Alpha Weight) 검증
        # -----------------------------------------------------------------------
        print("\n3. [적응형 가중치 검증] 구도 만족도(Score >= 80) vs 단순 우회 가중치 차등 반영")
        rec_waypoints = [
            {"seq": 1, "lat": 37.52840, "lng": 126.93280},
            {"seq": 2, "lat": 37.52850, "lng": 126.93280},
            {"seq": 3, "lat": 37.52860, "lng": 126.93280},
            {"seq": 4, "lat": 37.52870, "lng": 126.93280},
        ]

        # Case A: 동선은 권장 경로에서 횡으로 5m 벗어났으나, 구도 점수가 88점(Sweet Spot)으로 최적화된 경우
        # -> alpha = 0.60, deviation_reason = COMPOSITION_OPTIMIZED
        actual_comp_opt = [
            {"raw_gps": {"lat": 37.52840, "lng": 126.93286, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 90}},
            {"raw_gps": {"lat": 37.52850, "lng": 126.93286, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 88}},
            {"raw_gps": {"lat": 37.52860, "lng": 126.93286, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 85}},
            {"raw_gps": {"lat": 37.52870, "lng": 126.93286, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 92}},
        ]
        res_comp_opt = path_service.analyze_and_correct_path(
            recommended_waypoints=rec_waypoints,
            actual_waypoints=actual_comp_opt,
            project=project
        )
        print(f"   -> [Case A] 구도 최적화 우회: alpha={res_comp_opt['alpha_weight']}, reason={res_comp_opt['deviation_reason']}, score={res_comp_opt['match_score']}")
        assert res_comp_opt["alpha_weight"] == 0.60, "구도 최적화 우회 시 alpha는 0.60이어야 합니다."
        assert res_comp_opt["deviation_reason"] == "COMPOSITION_OPTIMIZED", "deviation_reason이 COMPOSITION_OPTIMIZED여야 합니다."
        assert res_comp_opt["is_valid"] is True, "구도 최적화 우회는 유효한 동선이어야 합니다."

        # Case B: 권장 경로에서 횡으로 6m 벗어났고 구도 점수도 55점으로 불량한 단순 보행 우회
        # -> alpha = 0.20, deviation_reason = WALKING_DETOUR
        actual_detour = [
            {"raw_gps": {"lat": 37.52840, "lng": 126.93288, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": False, "frame_score": 50}},
            {"raw_gps": {"lat": 37.52850, "lng": 126.93288, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": False, "frame_score": 55}},
            {"raw_gps": {"lat": 37.52860, "lng": 126.93288, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": False, "frame_score": 60}},
            {"raw_gps": {"lat": 37.52870, "lng": 126.93288, "accuracy_m": 3.0}, "composition_state": {"is_sweet_spot": False, "frame_score": 52}},
        ]
        res_detour = path_service.analyze_and_correct_path(
            recommended_waypoints=rec_waypoints,
            actual_waypoints=actual_detour,
            project=project
        )
        print(f"   -> [Case B] 단순 보행 우회: alpha={res_detour['alpha_weight']}, reason={res_detour['deviation_reason']}, score={res_detour['match_score']}")
        assert res_detour["alpha_weight"] == 0.20, "단순 보행 우회 시 alpha는 0.20이어야 합니다."
        assert res_detour["deviation_reason"] == "WALKING_DETOUR", "deviation_reason이 WALKING_DETOUR여야 합니다."

        # Case C: 권장 경로를 1m 이내로 충실히 따른 정상 보행
        # -> alpha = 0.35, deviation_reason = NORMAL
        actual_normal = [
            {"raw_gps": {"lat": 37.52840, "lng": 126.93281, "accuracy_m": 2.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 85}},
            {"raw_gps": {"lat": 37.52850, "lng": 126.93281, "accuracy_m": 2.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 85}},
            {"raw_gps": {"lat": 37.52860, "lng": 126.93281, "accuracy_m": 2.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 85}},
            {"raw_gps": {"lat": 37.52870, "lng": 126.93281, "accuracy_m": 2.0}, "composition_state": {"is_sweet_spot": True, "frame_score": 85}},
        ]
        res_normal = path_service.analyze_and_correct_path(
            recommended_waypoints=rec_waypoints,
            actual_waypoints=actual_normal,
            project=project
        )
        print(f"   -> [Case C] 정상 경로 유지: alpha={res_normal['alpha_weight']}, reason={res_normal['deviation_reason']}, score={res_normal['match_score']}")
        assert res_normal["alpha_weight"] == 0.35, "정상 경로 유지 시 alpha는 0.35여야 합니다."
        assert res_normal["deviation_reason"] == "NORMAL", "deviation_reason이 NORMAL이어야 합니다."

        # -----------------------------------------------------------------------
        # 4. 선형 보간 및 차기 보정 경로(corrected_waypoints) 산출 정밀도 검증
        # -----------------------------------------------------------------------
        print("\n4. [보정 동선 보간 검증] corrected_waypoints 산출 및 보간점 개수 정합성")
        corr_wps = res_comp_opt["corrected_waypoints"]
        assert len(corr_wps) == len(rec_waypoints), "보정 경로는 권장 경로의 웨이포인트 개수와 동일하게 리샘플링되어야 합니다."
        # Case A에서 권장 경로 lng는 126.93280, 실제 lng는 126.93286, alpha=0.60
        # 보정된 lng는 (1-0.6)*126.93280 + 0.6*126.93286 = 126.932836 근방이어야 함
        corr_lng_mid = corr_wps[1]["lng"]
        print(f"   -> 보정 경로 중간점 경도: {corr_lng_mid:.6f} (권장: 126.932800, 실제: 126.932860, 보정: 약 126.932836)")
        assert 126.932830 <= corr_lng_mid <= 126.932845, "보정 경도가 alpha=0.6 가중 보간 범위 내에 있어야 합니다."

        # -----------------------------------------------------------------------
        # 5. 차기 회차(N -> N+1) 보정 동선 승계(Inheritance) 기능 검증
        # -----------------------------------------------------------------------
        print("\n5. [차기 회차 승계 검증] 1회차 보정 동선 저장 후 2회차 권장 동선 승계 확인")
        # 1회차 저장 (Case A 보정 데이터)
        path_create_round1 = ShootingPathCreate(
            project_id=project_id,
            shooting_number=1,
            tracking_source="PHONE_GPS",
            recommended_waypoints=rec_waypoints,
            actual_waypoints=actual_comp_opt,
            corrected_waypoints=[], # 비워두면 자동 분석
            alpha_weight=None,
            deviation_score=None,
            deviation_reason=None,
            is_valid=True
        )
        saved_round1 = mobile_service.save_shooting_path(db, path_create_round1, current_user=test_user_pilot)
        assert saved_round1.shooting_number == 1
        assert saved_round1.is_valid is True
        assert saved_round1.deviation_reason == "COMPOSITION_OPTIMIZED"
        assert len(saved_round1.corrected_waypoints) > 0

        # 2회차 추천 경로 조회 (next-recommendation)
        next_rec = mobile_service.get_next_round_path_recommendation(db, project_id)
        print(f"   -> 2회차 추천 조회: target_shooting_number={next_rec['target_shooting_number']}, is_inherited={next_rec['is_inherited_from_previous']}")
        assert next_rec["target_shooting_number"] == 2, "차기 회차 번호는 2여야 합니다."
        assert next_rec["is_inherited_from_previous"] is True, "1회차가 유효하므로 이전 보정 경로가 승계되어야 합니다."
        assert next_rec["source_shooting_number"] == 1, "승계 소스는 1회차여야 합니다."
        assert len(next_rec["recommended_waypoints"]) == len(saved_round1.corrected_waypoints)
        assert next_rec["recommended_waypoints"][0]["lat"] == saved_round1.corrected_waypoints[0]["lat"]

        # -----------------------------------------------------------------------
        # 6. 백엔드 REST API 및 소유권 보안(IDOR) 검증
        # -----------------------------------------------------------------------
        print("\n6. [REST API & IDOR 검증] 라우터 엔드포인트 및 타인 프로젝트 접근 차단 검증")
        # A. POST /paths/analyze 라우터 함수 직접 호출 (정상 파일럿)
        api_analyze_res = analyze_shooting_path(
            project_id=project_id,
            path_in=path_create_round1,
            token=None,
            current_user=test_user_pilot,
            db=db
        )
        assert api_analyze_res.match_score > 0
        assert api_analyze_res.actionable_advice is not None
        print(f"   -> API 분석 완료: score={api_analyze_res.match_score:.1f}, advice='{api_analyze_res.actionable_advice[:30]}...'")

        # B. GET /paths/next-recommendation 라우터 함수 직접 호출 (정상 파일럿)
        api_next_res = get_next_round_path_recommendation(
            project_id=project_id,
            token=None,
            current_user=test_user_pilot,
            db=db
        )
        assert api_next_res.is_inherited_from_previous is True
        assert api_next_res.target_shooting_number == 2

        # C. IDOR 차단 검증: 타인(test_user_other)이 pilot의 프로젝트 경로 분석 요청 시 403 Forbidden 발생
        print("   -> IDOR 보안 검사: 타 사용자 권한으로 경로 분석 및 승계 조회 시도")
        try:
            analyze_shooting_path(
                project_id=project_id,
                path_in=path_create_round1,
                token=None,
                current_user=test_user_other,
                db=db
            )
            assert False, "타 사용자의 경로 분석 접근은 403 차단되어야 합니다."
        except HTTPException as e:
            assert e.status_code == 403
            print(f"   -> [보안 통과] 타 사용자 경로 분석 차단 확인 (403: {e.detail})")

        try:
            get_next_round_path_recommendation(
                project_id=project_id,
                token=None,
                current_user=test_user_other,
                db=db
            )
            assert False, "타 사용자의 차기 경로 승계 접근은 403 차단되어야 합니다."
        except HTTPException as e:
            assert e.status_code == 403
            print(f"   -> [보안 통과] 타 사용자 차기 경로 승계 차단 확인 (403: {e.detail})")

        # -----------------------------------------------------------------------
        # 7. tracking_source의 PHONE_GPS 보존 및 드론 위조 방지 검증
        # -----------------------------------------------------------------------
        print("\n7. [데이터 무결성 검증] tracking_source='PHONE_GPS' 유지 확인")
        db_path_rec = db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id,
            ShootingPath.shooting_number == 1
        ).first()
        assert db_path_rec is not None
        assert db_path_rec.tracking_source == "PHONE_GPS", "스마트폰 보행 데이터의 tracking_source는 반드시 PHONE_GPS여야 합니다."
        print(f"   -> 저장된 tracking_source: {db_path_rec.tracking_source} (정상 확인)")

        print("\n======================================================================")
        print("Phase 6 All 7 Verification Categories PASSED Successfully!")
        print("======================================================================")

    finally:
        # 정리: 테스트 데이터 롤백 또는 유지
        db.query(ShootingPath).filter(ShootingPath.project_id == project_id).delete()
        db.query(ShootingProject).filter(ShootingProject.id == project_id).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_phase6()
