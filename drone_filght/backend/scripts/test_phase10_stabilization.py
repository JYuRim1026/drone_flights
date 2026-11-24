"""
Phase 10: 실시간 GPS 정확도·최신성 검증, 만족도 피드백 중복 방지, 웨이포인트 도착 판정 안정화 검증 스크립트

검증 시나리오 (8개 핵심 항목):
1. GPS accuracy 10m, 20m, 30m 환경에서 안내 결과 비교 (20m 이하 허용, 30m 초과 시 차단)
2. 오래된 GPS 좌표(>15초) 수신 시 이동 안내 차단 및 경고 확인
3. GPS 정상화 이후 이동 안내 즉시 복구 확인
4. 동일 별점 피드백 2회 이상 전송 시 선호도 점수(UserPreferenceScore) 중복 가산 방지(멱등성) 및 차분 반영 검증
5. 실제 촬영 회차와 피드백 저장 회차 일치 및 누락 시 최신 회차 자동 연계 확인
6. GPS가 한 번만 2.5m 이내로 튄 경우(순간 튐) 웨이포인트 순번 승계 차단 확인
7. 2회 연속 2.5m 이내 관측 시 정상적으로 다음 웨이포인트로 승계(Debounce) 확인
8. 기존 Phase 6~10 통합 기능 무결성 회귀 검증
"""

import os
import sys
import math
import json
from datetime import datetime, timezone, timedelta
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
from backend.services.technique_service import technique_service
from backend.services.mobile_service import mobile_service
from backend.schemas.schemas import AnalyzeRequest, AnalyzeResponse, TechniqueFeedbackRequest


def run_phase10_stabilization_verification():
    db = SessionLocal()
    print("=" * 80)
    print("🚀 [Phase 10 Stabilization] GPS 최신성/정확도, 피드백 멱등성, 웨이포인트 디바운스 정밀 검증")
    print("   대상 DB: sky_command_demo.db (스마트폰 PHONE_GPS 지상 촬영 모사 원칙)")
    print("=" * 80)

    try:
        # -------------------------------------------------------------------
        # [테스트 시드 준비]
        # -------------------------------------------------------------------
        user = db.query(User).filter(User.email == "pilot_stab_p10@skycommand.ai").first()
        if not user:
            from backend.services.auth_service import auth_service
            user = User(
                email="pilot_stab_p10@skycommand.ai",
                username="pilot_stab_p10",
                hashed_password=auth_service.hash_password("pilot1234!"),
                role="pilot"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        project = db.query(ShootingProject).filter(ShootingProject.id == 1).first()
        if not project:
            project = ShootingProject(
                id=1,
                title="여의도 한강공원 시네마틱 프로젝트",
                place_name="여의도 한강공원",
                latitude=37.5284,
                longitude=126.9328,
                recommended_mode="패럴랙스 리빌 & 선셋 아크"
            )
            db.add(project)
            db.commit()
            db.refresh(project)

        # 기준 좌표 (목표 웨이포인트 lat: 37.5284, lng: 126.9328 근방)
        target_lat = 37.528400
        target_lng = 126.932800

        # ===================================================================
        # [시나리오 1] GPS accuracy 10m vs 20m vs 30m 환경에서 안내 결과 비교
        # ===================================================================
        print("\n[시나리오 1] GPS accuracy 10m, 20m, 30m 안내 결과 비교 검증")
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1-A. accuracy 10m (우수): 정상 거리·방위각 계산
        res_10m = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=37.528300,
            current_lng=126.932700,
            current_accuracy=10.0,
            current_timestamp=now_iso,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_10m = res_10m.walking_guide
        assert wg_10m["distance_m"] is not None, "Accuracy 10m에서 distance_m이 계산되어야 함"
        assert wg_10m["bearing_deg"] is not None, "Accuracy 10m에서 bearing_deg가 계산되어야 함"
        assert wg_10m["is_gps_usable"] is True, "Accuracy 10m에서 GPS는 사용 가능해야 함"
        print(f"  ✓ 10m (우수): distance={wg_10m['distance_m']}m, bearing={wg_10m['bearing_deg']}°, usable=True")

        # 1-B. accuracy 20m (임계 허용치, Phase 6 기준 일치): 정상 거리·방위각 계산
        res_20m = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=37.528300,
            current_lng=126.932700,
            current_accuracy=20.0,
            current_timestamp=now_iso,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_20m = res_20m.walking_guide
        assert wg_20m["distance_m"] is not None, "Accuracy 20m(임계값)에서 distance_m이 계산되어야 함"
        assert wg_20m["is_gps_usable"] is True, "Accuracy 20m에서 GPS는 사용 가능해야 함"
        print(f"  ✓ 20m (임계치 허용): distance={wg_20m['distance_m']}m, usable=True (Phase 6 20m 기준과 일치)")

        # 1-C. accuracy 30m (초과): 계산 중단 및 경고 메시지 출력
        res_30m = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=37.528300,
            current_lng=126.932700,
            current_accuracy=30.0,
            current_timestamp=now_iso,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_30m = res_30m.walking_guide
        assert wg_30m["distance_m"] is None, "Accuracy 30m(초과) 시 distance_m은 None이어야 함"
        assert wg_30m["bearing_deg"] is None, "Accuracy 30m(초과) 시 bearing_deg는 None이어야 함"
        assert wg_30m["is_gps_usable"] is False, "Accuracy 30m에서 GPS는 불량이어야 함"
        assert "GPS 수신 정확도 저하" in wg_30m["walking_message"], "정확도 저하 경고 메시지가 포함되어야 함"
        print(f"  ✓ 30m (초과 차단): distance=None, bearing=None, msg='{wg_30m['walking_message']}'")

        # ===================================================================
        # [시나리오 2] 오래된 GPS 좌표 (>15초) 수신 시 이동 안내 차단 검증
        # ===================================================================
        print("\n[시나리오 2] 오래된 GPS 좌표 (>15초) 이동 안내 차단 검증")
        stale_time_iso = (datetime.now(timezone.utc) - timedelta(seconds=25)).isoformat()
        res_stale = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=37.528300,
            current_lng=126.932700,
            current_accuracy=5.0,
            current_timestamp=stale_time_iso,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_stale = res_stale.walking_guide
        assert wg_stale["distance_m"] is None, "25초 전 GPS는 distance_m이 None이어야 함"
        assert wg_stale["bearing_deg"] is None, "25초 전 GPS는 bearing_deg가 None이어야 함"
        assert wg_stale["is_gps_usable"] is False, "오래된 GPS는 unusable이어야 함"
        assert "GPS 위치 정보 지연" in wg_stale["walking_message"], "지연 경고 메시지가 포함되어야 함"
        print(f"  ✓ 지연 GPS (25초 전): distance=None, msg='{wg_stale['walking_message']}'")

        # ===================================================================
        # [시나리오 3] GPS 정상화 이후 이동 안내 즉시 복구 검증
        # ===================================================================
        print("\n[시나리오 3] GPS 정상화 이후 이동 안내 즉시 복구 검증")
        fresh_time_iso = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        res_recovered = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=37.528300,
            current_lng=126.932700,
            current_accuracy=8.0,
            current_timestamp=fresh_time_iso,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_rec = res_recovered.walking_guide
        assert wg_rec["distance_m"] is not None, "정상화 시 distance_m 복구되어야 함"
        assert wg_rec["bearing_deg"] is not None, "정상화 시 bearing_deg 복구되어야 함"
        assert wg_rec["is_gps_usable"] is True, "정상화 시 GPS는 사용 가능해야 함"
        print(f"  ✓ GPS 정상화 복구 성공: distance={wg_rec['distance_m']}m, bearing={wg_rec['bearing_deg']}°, msg='{wg_rec['walking_message'][:40]}...'")

        # ===================================================================
        # [시나리오 4] 동일 별점 요청 2회 이상 전송 시 선호도 점수 멱등성 검증
        # ===================================================================
        print("\n[시나리오 4] 동일 별점 피드백 중복 전송 시 선호도 점수(UserPreferenceScore) 멱등성 검증")
        import time
        tech_id = "orbit_poi"
        test_round = int(time.time()) % 90000 + 1000

        # 이전 테스트 기록 초기화
        db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == user.id,
            UserPreferenceScore.category == "technique",
            UserPreferenceScore.preference_value == tech_id
        ).delete()
        db.commit()

        # 4-A. 1회차 피드백 등록 (5점, 최초 등록)
        fb1 = technique_service.record_technique_feedback(
            db=db,
            user_id=user.id,
            project_id=project.id,
            technique_id=tech_id,
            shooting_number=test_round,
            was_shot=True,
            satisfaction_score=5,
            comment="1회차 최초 5점 피드백"
        )
        score_after_fb1 = fb1["updated_preference_score"]
        assert fb1["status"] == "success", "최초 피드백은 success이어야 함"
        assert fb1["applied_weight"] == 8.0, "5점 피드백의 가중치는 8.0이어야 함"
        print(f"  ✓ 1회 전송 (5점): status={fb1['status']}, applied_weight={fb1['applied_weight']}, score={score_after_fb1}")

        # 4-B. 동일 회차/기법 5점 재전송 (중복 요청) -> 추가 가산 완전 차단
        fb2 = technique_service.record_technique_feedback(
            db=db,
            user_id=user.id,
            project_id=project.id,
            technique_id=tech_id,
            shooting_number=test_round,
            was_shot=True,
            satisfaction_score=5,
            comment="1회차 중복 5점 피드백 재전송"
        )
        score_after_fb2 = fb2["updated_preference_score"]
        assert fb2["status"] == "already_recorded", "동일 피드백 재전송 시 already_recorded 반환"
        assert fb2["applied_weight"] == 0.0, "중복 피드백 시 가중치 추가는 0.0이어야 함"
        assert score_after_fb2 == score_after_fb1, f"중복 요청 시 점수 변동 없어야 함: {score_after_fb1} == {score_after_fb2}"
        print(f"  ✓ 2회 전송 (중복 5점): status={fb2['status']}, applied_weight={fb2['applied_weight']}, score={score_after_fb2} (가산 없음)")

        # 4-C. 동일 회차에서 점수를 3점으로 변경 -> 가중치 차분만 반영 (3점 가중치 4.0 - 이전 8.0 = -4.0)
        fb3 = technique_service.record_technique_feedback(
            db=db,
            user_id=user.id,
            project_id=project.id,
            technique_id=tech_id,
            shooting_number=test_round,
            was_shot=True,
            satisfaction_score=3,
            comment="1회차 3점으로 수정"
        )
        score_after_fb3 = fb3["updated_preference_score"]
        expected_diff = (4.0 - 8.0) * 3.5  # -14.0
        assert fb3["status"] == "success", "점수 수정 시 success 반환"
        assert fb3["applied_weight"] == -4.0, f"수정 시 가중치 차분은 -4.0이어야 함 (실제: {fb3['applied_weight']})"
        assert round(score_after_fb3 - score_after_fb1, 1) == round(expected_diff, 1), f"차분 점수 일치 확인: {score_after_fb3} - {score_after_fb1} == {expected_diff}"
        print(f"  ✓ 3회 전송 (점수 3점 수정): status={fb3['status']}, delta_weight={fb3['applied_weight']}, new_score={score_after_fb3}")

        # 4-D. 수정된 3점으로 다시 중복 전송 -> 다시 추가 가산 차단
        fb4 = technique_service.record_technique_feedback(
            db=db,
            user_id=user.id,
            project_id=project.id,
            technique_id=tech_id,
            shooting_number=test_round,
            was_shot=True,
            satisfaction_score=3,
            comment="1회차 중복 3점 재전송"
        )
        assert fb4["status"] == "already_recorded", "수정된 점수로도 중복 전송 시 already_recorded 반환"
        assert fb4["updated_preference_score"] == score_after_fb3, "수정 후 중복 요청도 점수 유지"
        print(f"  ✓ 4회 전송 (중복 3점): status={fb4['status']}, score={fb4['updated_preference_score']} (가산 없음)")

        # ===================================================================
        # [시나리오 5] 실제 촬영 회차와 피드백 저장 회차 일치 및 누락 시 최신 회차 자동 연계
        # ===================================================================
        print("\n[시나리오 5] 실제 촬영 회차 연계 및 누락 시 최신 회차 자동 조회 검증")

        # 5-A. 현재 존재하는 가장 큰 shooting_number 확인 후 +1 회차 생성
        latest_existing = db.query(ShootingPath).filter(
            ShootingPath.project_id == project.id
        ).order_by(ShootingPath.shooting_number.desc()).first()
        target_test_round = (latest_existing.shooting_number + 1) if latest_existing else 10

        test_path = ShootingPath(
            project_id=project.id,
            user_id=user.id,
            shooting_number=target_test_round,
            recommended_waypoints=[{"seq": 1, "lat": 37.5284, "lng": 126.9328}]
        )
        db.add(test_path)
        db.commit()

        # 5-B. mobile_service.record_technique_feedback 호출 시 shooting_number 누락 (None)
        req_missing_round = TechniqueFeedbackRequest(
            technique_id="straight_dronie",
            shooting_number=None,  # 누락!
            was_shot=True,
            satisfaction_score=4,
            comment="회차 번호 누락 피드백 테스트"
        )
        res_linked = mobile_service.record_technique_feedback(
            db=db,
            project_id=project.id,
            req=req_missing_round,
            current_user=user
        )
        # 최신 회차인 target_test_round로 자동 조회되어 피드백이 연계되었는지 확인
        latest_analysis = db.query(ShootingAnalysis).filter(
            ShootingAnalysis.project_id == project.id
        ).order_by(ShootingAnalysis.created_at.desc()).first()
        coords = latest_analysis.target_coordinates if latest_analysis else {}
        feedbacks_by_round = coords.get("feedbacks_by_round", {})
        feedbacks_by_key = coords.get("feedbacks_by_key", {})
        assert str(target_test_round) in feedbacks_by_round or f"{user.id}_{target_test_round}_straight_dronie" in feedbacks_by_key, f"누락 시 최신 회차인 {target_test_round}회차로 정확히 연계되어야 함"
        print(f"  ✓ 누락 시 최신 회차 자동 연계: shooting_number=None -> 실제 활성 회차({target_test_round}회차)로 피드백 연계 완료")

        # ===================================================================
        # [시나리오 6] GPS 1회 순간 튐 (<2.5m) 시 순번 승계 차단 검증
        # ===================================================================
        print("\n[시나리오 6] GPS 1회 순간 튐 (<2.5m) 시 웨이포인트 순번 승계 차단 검증")

        # 목표 웨이포인트(seq=1)의 실제 목표 좌표 확인
        t_lat = wg_10m["target_lat"]
        t_lng = wg_10m["target_lng"]

        # 목표 지점으로부터 약 1.1m 거리의 근접 좌표 (1도 위도 ~= 111,000m)
        near_lat = t_lat + 0.000010
        near_lng = t_lng

        # 1회차 관측 (consecutive_arrival_count = 0)
        res_spike = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=near_lat,
            current_lng=near_lng,
            current_accuracy=8.0,
            current_timestamp=datetime.now(timezone.utc).isoformat(),
            consecutive_arrival_count=0,  # 첫 번째 접근
            current_waypoint_seq=1,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_spike = res_spike.walking_guide
        assert wg_spike["distance_m"] <= 2.5, f"2.5m 이내 관측이어야 함: {wg_spike['distance_m']}"
        assert wg_spike["is_near_waypoint"] is True, "반경 2.5m 이내이므로 is_near_waypoint는 True"
        assert wg_spike["consecutive_arrival_count"] == 1, "연속 관측 카운트는 1이어야 함"
        assert wg_spike["is_waypoint_reached"] is False, "1회 관측만으로는 is_waypoint_reached가 False여야 함 (순번 건너뜀 방지)"
        print(f"  ✓ 1회 튐: distance={wg_spike['distance_m']}m, near=True, consecutive=1, is_reached=False (순번 유지)")

        # 직후 다음 프레임에서 GPS가 다시 6.6m 밖으로 이동
        far_lat = t_lat + 0.000060
        far_lng = t_lng
        res_after_spike = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=far_lat,
            current_lng=far_lng,
            current_accuracy=8.0,
            current_timestamp=datetime.now(timezone.utc).isoformat(),
            consecutive_arrival_count=1,  # 이전 1회 카운트 전달
            current_waypoint_seq=1,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_after_spike = res_after_spike.walking_guide
        assert wg_after_spike["is_near_waypoint"] is False, "5m 밖이므로 is_near_waypoint는 False"
        assert wg_after_spike["consecutive_arrival_count"] == 0, "도착 범위를 벗어났으므로 consecutive_arrival_count는 0으로 리셋"
        assert wg_after_spike["is_waypoint_reached"] is False, "is_waypoint_reached는 False 유지"
        print(f"  ✓ 튐 복귀: distance={wg_after_spike['distance_m']}m, consecutive 리셋=0, is_reached=False (순번 건너뛰어지지 않음)")

        # ===================================================================
        # [시나리오 7] 2회 연속 2.5m 이내 관측 시 정상적으로 다음 웨이포인트 승계 검증
        # ===================================================================
        print("\n[시나리오 7] 2회 연속 2.5m 이내 관측 시 정상 승계 (Debounce 성공) 검증")

        # 1회차 관측
        res_step1 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=near_lat,
            current_lng=near_lng,
            current_accuracy=8.0,
            current_timestamp=datetime.now(timezone.utc).isoformat(),
            consecutive_arrival_count=0,
            current_waypoint_seq=1,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        assert res_step1.walking_guide["consecutive_arrival_count"] == 1
        assert res_step1.walking_guide["is_waypoint_reached"] is False

        # 2회차 연속 관측 (동일하게 2.5m 이내, 이전 관측 카운트=1 전달)
        res_step2 = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=near_lat,
            current_lng=near_lng,
            current_accuracy=7.5,
            current_timestamp=datetime.now(timezone.utc).isoformat(),
            consecutive_arrival_count=1,  # 2번째 관측!
            current_waypoint_seq=1,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        wg_step2 = res_step2.walking_guide
        assert wg_step2["is_near_waypoint"] is True, "2.5m 이내"
        assert wg_step2["consecutive_arrival_count"] == 2, "연속 2회 관측 달성"
        assert wg_step2["is_waypoint_reached"] is True, "2회 연속 관측 완료로 is_waypoint_reached가 True로 확정되어야 함!"
        assert "도착 완료" in wg_step2["walking_message"], "도착 완료 안내 메시지 출력 확인"
        print(f"  ✓ 2회 연속 관측: distance={wg_step2['distance_m']}m, consecutive=2, is_reached=True! (도착 확정)")

        # 2-B. 만약 2회차라도 GPS 정확도가 25m(>20m)로 불량하다면 도착 확정 차단 검증
        res_step2_bad_acc = ai_service.analyze_scene_and_recommend(
            image_base64=None,
            current_lat=near_lat,
            current_lng=near_lng,
            current_accuracy=25.0,  # 20m 초과 불량
            current_timestamp=datetime.now(timezone.utc).isoformat(),
            consecutive_arrival_count=1,
            current_waypoint_seq=1,
            project_id=project.id,
            current_user=user,
            save_to_db=False,
            db=db
        )
        assert res_step2_bad_acc.walking_guide["is_waypoint_reached"] is False, "GPS 정확도가 20m를 초과하면 2회차라도 도착 판정에 사용 금지"
        assert res_step2_bad_acc.walking_guide["consecutive_arrival_count"] == 0, "정확도 저하 시 카운터 리셋"
        print(f"  ✓ 2회차 GPS 정확도 저하(25m) 시: is_reached=False, consecutive=0 (안전 차단 완료)")

        print("\n" + "=" * 80)
        print("🎉 [Phase 10 Stabilization] 7대 보완 항목 검증 전체 통과 (100% PASS)")
        print("=" * 80)
        return True

    except Exception as e:
        db.rollback()
        print(f"\n❌ [ERROR] 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = run_phase10_stabilization_verification()
    sys.exit(0 if success else 1)
