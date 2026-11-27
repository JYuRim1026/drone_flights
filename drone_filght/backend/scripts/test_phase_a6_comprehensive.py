"""
Phase A-6: 사용자 선호도 기반 촬영 추천 개인화 종합 검증 테스트
================================================================
검증 항목:
1. 사용자별 선호도 격리 검증 (User ID Isolation: User A vs User B 선호도 미혼양)
2. 피드백 누적 후 차기 추천 변경 검증 (Feedback -> Next Recommendation Dynamic Update)
3. 장면 적합성 및 안전 Fallback 검증 (선호 기법 실행 불가 시 기존 AI 추천 우선)
4. 신규 사용자 Cold Start 검증 (선호도 부재 시 기본 추천 엔진 무결성 유지)
5. 별점별 가중치(A-5) 의도 정합성 검증 (5/4점: +8.0, 3점: +4.0, 2/1점: +1.0)
6. 개인화 추천 필드 및 DB 저장 검증 (is_personalized, personalized_reason)
"""

import sys
import os
import unittest
from pathlib import Path

# Add drone_filght to sys.path
_PROJECT_DIR = os.path.abspath("drone_filght")
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from backend.database import SessionLocal
from backend.models.models import (
    User, ShootingProject as Project, ShootingPath, UserPreferenceScore, ShootingAnalysis
)
from backend.services.technique_service import technique_service
from backend.services.ai_service import ai_service


class TestPhaseA6Comprehensive(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.technique_service = technique_service
        cls.ai_service = ai_service

        # 1. Setup User A (prefers FORWARD + 삼분할 구도)
        cls.user_a = cls.db.query(User).filter(User.username == "test_a6_user_a").first()
        if not cls.user_a:
            cls.user_a = User(
                username="test_a6_user_a",
                email="test_a6_a@example.com",
                hashed_password="pwd"
            )
            cls.db.add(cls.user_a)
            cls.db.commit()
            cls.db.refresh(cls.user_a)

        # 2. Setup User B (prefers LATERAL + 중앙 배치 구도)
        cls.user_b = cls.db.query(User).filter(User.username == "test_a6_user_b").first()
        if not cls.user_b:
            cls.user_b = User(
                username="test_a6_user_b",
                email="test_a6_b@example.com",
                hashed_password="pwd"
            )
            cls.db.add(cls.user_b)
            cls.db.commit()
            cls.db.refresh(cls.user_b)

        # 3. Setup User C (prefers ORBIT, for suitability test)
        cls.user_c = cls.db.query(User).filter(User.username == "test_a6_user_c").first()
        if not cls.user_c:
            cls.user_c = User(
                username="test_a6_user_c",
                email="test_a6_c@example.com",
                hashed_password="pwd"
            )
            cls.db.add(cls.user_c)
            cls.db.commit()
            cls.db.refresh(cls.user_c)

        # 4. Setup User D (Cold Start, 0 preference)
        cls.user_d = cls.db.query(User).filter(User.username == "test_a6_user_d").first()
        if not cls.user_d:
            cls.user_d = User(
                username="test_a6_user_d",
                email="test_a6_d@example.com",
                hashed_password="pwd"
            )
            cls.db.add(cls.user_d)
            cls.db.commit()
            cls.db.refresh(cls.user_d)

        # Common test project (no POI coordinates, to test ORBIT unexecutable)
        cls.test_project = cls.db.query(Project).filter(Project.project_name == "Phase A-6 Test Project").first()
        if not cls.test_project:
            cls.test_project = Project(
                user_id=cls.user_a.id,
                project_name="Phase A-6 Test Project",
                project_code="PROJ_A6_TEST",
                place_name="서울 여의도 한강공원",
                latitude=37.5284,
                longitude=126.9328,
                recommended_mode="직선 전진 드로니"
            )
            cls.db.add(cls.test_project)
            cls.db.commit()
            cls.db.refresh(cls.test_project)

    @classmethod
    def tearDownClass(cls):
        try:
            test_user_ids = [cls.user_a.id, cls.user_b.id, cls.user_c.id, cls.user_d.id]
            cls.db.query(UserPreferenceScore).filter(
                UserPreferenceScore.user_id.in_(test_user_ids)
            ).delete(synchronize_session=False)

            cls.db.query(ShootingAnalysis).filter(
                ShootingAnalysis.project_id == cls.test_project.id
            ).delete(synchronize_session=False)

            cls.db.delete(cls.test_project)
            for u in [cls.user_a, cls.user_b, cls.user_c, cls.user_d]:
                cls.db.delete(u)
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        finally:
            cls.db.close()

    def test_01_user_preference_isolation(self):
        """1. 사용자별 선호도 격리 검증: User A(FORWARD)와 User B(LATERAL)가 섞이지 않음"""
        # User A gives 5 stars to FORWARD + 삼분할 구도
        self.technique_service.record_technique_feedback(
            db=self.db,
            user_id=self.user_a.id,
            project_id=self.test_project.id,
            shooting_number=1,
            technique_id="FORWARD",
            was_shot=True,
            satisfaction_score=5,
            composition_type="삼분할 구도",
            is_liked=True
        )

        # User B gives 5 stars to LATERAL + 중앙 배치 구도
        self.technique_service.record_technique_feedback(
            db=self.db,
            user_id=self.user_b.id,
            project_id=self.test_project.id,
            shooting_number=1,
            technique_id="LATERAL",
            was_shot=True,
            satisfaction_score=5,
            composition_type="중앙 배치 구도",
            is_liked=True
        )

        # User A recommendation
        res_a = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_a,
            db=self.db
        )

        # User B recommendation
        res_b = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_b,
            db=self.db
        )

        # Verify User A got FORWARD and is_personalized=True
        self.assertEqual(res_a.recommended_technique, "FORWARD")
        self.assertTrue(res_a.is_personalized)
        self.assertIn("삼분할", res_a.recommended_composition)

        # Verify User B got LATERAL and is_personalized=True
        self.assertEqual(res_b.recommended_technique, "LATERAL")
        self.assertTrue(res_b.is_personalized)
        self.assertIn("중앙", res_b.recommended_composition)

        # Strict isolation check: User A must NOT have LATERAL, User B must NOT have FORWARD
        user_a_scores = {
            s.preference_value: float(s.preference_score)
            for s in self.db.query(UserPreferenceScore).filter(UserPreferenceScore.user_id == self.user_a.id).all()
        }
        user_b_scores = {
            s.preference_value: float(s.preference_score)
            for s in self.db.query(UserPreferenceScore).filter(UserPreferenceScore.user_id == self.user_b.id).all()
        }
        self.assertIn("FORWARD", user_a_scores)
        self.assertNotIn("LATERAL", user_a_scores)
        self.assertIn("LATERAL", user_b_scores)
        self.assertNotIn("FORWARD", user_b_scores)

        print(f"  ✓ [Test 1] 사용자별 선호도 격리 완벽 보장: User A({res_a.recommended_technique}), User B({res_b.recommended_technique})")

    def test_02_feedback_dynamic_recommendation_update(self):
        """2. 피드백 입력 후 차기 추천 변화 반영 검증: User A가 PANORAMA 피드백 후 추천 기법이 PANORAMA로 변경"""
        # User A gives 5 stars to PANORAMA (2 rounds of high satisfaction to exceed FORWARD)
        self.technique_service.record_technique_feedback(
            db=self.db,
            user_id=self.user_a.id,
            project_id=self.test_project.id,
            shooting_number=2,
            technique_id="PANORAMA",
            was_shot=True,
            satisfaction_score=5,
            composition_type="수평선 0도 랜드스케이프 구도",
            is_liked=True
        )
        self.technique_service.record_technique_feedback(
            db=self.db,
            user_id=self.user_a.id,
            project_id=self.test_project.id,
            shooting_number=3,
            technique_id="PANORAMA",
            was_shot=True,
            satisfaction_score=5,
            composition_type="수평선 0도 랜드스케이프 구도",
            is_liked=True
        )

        # Call recommendation for User A
        res_updated = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_a,
            db=self.db
        )

        self.assertEqual(res_updated.recommended_technique, "PANORAMA")
        self.assertTrue(res_updated.is_personalized)
        self.assertIn("수평선", res_updated.recommended_composition)
        print(f"  ✓ [Test 2] 피드백 누적 후 차기 추천 변경 확인: FORWARD -> {res_updated.recommended_technique}")

    def test_03_scene_suitability_fallback(self):
        """3. 장면 적합성 판정 및 Fallback 검증: ORBIT 선호 사용자가 POI GPS 없는 장면에 접근 시 기본 기법 우선"""
        # User C gives 5 stars to ORBIT
        self.technique_service.record_technique_feedback(
            db=self.db,
            user_id=self.user_c.id,
            project_id=self.test_project.id,
            shooting_number=1,
            technique_id="ORBIT",
            was_shot=True,
            satisfaction_score=5,
            is_liked=True
        )

        # Recommend for User C in a scene without POI (rec_waypoints=[], no POI assets)
        res_c = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_c,
            rec_waypoints=[],
            db=self.db
        )

        # Must NOT force ORBIT when scene is unexecutable
        self.assertNotEqual(res_c.recommended_technique, "ORBIT")
        self.assertEqual(res_c.recommended_technique, "FORWARD")
        self.assertFalse(res_c.is_personalized)
        self.assertIn("미등록", res_c.personalized_reason)
        print(f"  ✓ [Test 3] 장면 적합성 Fallback 정상 작동: 선호(ORBIT) 불가 시 장면 최적({res_c.recommended_technique}) 우선 반영")

    def test_04_cold_start_new_user(self):
        """4. 선호도 데이터가 없는 신규 사용자(Cold Start) 기본 추천 엔진 무결성 검증"""
        res_d = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_d,
            db=self.db
        )

        self.assertFalse(res_d.is_personalized)
        self.assertIn("기본 AI 추천", res_d.personalized_reason)
        self.assertIsNotNone(res_d.recommended_composition)
        self.assertIsNotNone(res_d.recommended_technique)
        print(f"  ✓ [Test 4] 신규 사용자 Cold Start 정상 가동: is_personalized={res_d.is_personalized}, 추천={res_d.recommended_technique}")

    def test_05_star_rating_weight_semantics(self):
        """5. A-5 별점별 점수 반영 기준 및 가중치 의미 정합성 검증"""
        weights = {}
        tech_map = {
            5: "FORWARD",
            4: "LATERAL",
            3: "DIAGONAL_REVEAL",
            2: "ORBIT",
            1: "PANORAMA"
        }
        for score, tech_name in tech_map.items():
            res = self.technique_service.record_technique_feedback(
                db=self.db,
                user_id=self.user_d.id,
                project_id=self.test_project.id,
                shooting_number=score + 10,  # distinct rounds
                technique_id=tech_name,
                was_shot=True,
                satisfaction_score=score,
                is_liked=(score >= 4)
            )
            weights[score] = res["applied_weight"]

        self.assertEqual(weights[5], 8.0)
        self.assertEqual(weights[4], 8.0)
        self.assertEqual(weights[3], 4.0)
        self.assertEqual(weights[2], 1.0)
        self.assertEqual(weights[1], 1.0)
        print(f"  ✓ [Test 5] 별점별 가중치 의미 정합성 검증 완료: 5/4점({weights[5]}), 3점({weights[3]}), 2/1점({weights[2]})")

    def test_06_personalization_fields_persisted(self):
        """6. 개인화 추천 필드(is_personalized, personalized_reason) 반환 및 DB 저장 검증"""
        res = self.ai_service.analyze_scene_and_recommend(
            project_id=self.test_project.id,
            purpose="dronie",
            current_user=self.user_a,
            db=self.db
        )

        self.assertIn("is_personalized", res.model_dump())
        self.assertIn("personalized_reason", res.model_dump())
        self.assertTrue(res.is_personalized)

        # Check in DB shooting_analyses table
        analysis_db = self.db.query(ShootingAnalysis).filter(
            ShootingAnalysis.analysis_id == res.analysis_id
        ).first()

        self.assertIsNotNone(analysis_db)
        coords = analysis_db.target_coordinates or {}
        self.assertEqual(coords.get("is_personalized"), True)
        self.assertIn("선호", coords.get("personalized_reason"))
        print(f"  ✓ [Test 6] 개인화 필드 DB(shooting_analyses) 영구 저장 및 반환 검증 완료")


if __name__ == "__main__":
    unittest.main()
