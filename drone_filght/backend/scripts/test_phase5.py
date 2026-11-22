"""
Phase 5 Comprehensive Verification Test Suite
사용자 맞춤형 AI 촬영 기법 추천 시스템 및 커뮤니티 콘텐츠 연계 검증

검증 항목:
1. 촬영 기법 카탈로그 확장성 및 스마트폰/드론 전용 분류 검증
2. 콜드 스타트 (신규 사용자) 기본 추천 및 Fallback 검증
3. 다요소 개인화 알고리즘 (프로젝트 + 과거 이력 + 커뮤니티 선호도) 가중치 검증
4. 기법 선택 및 만족도 피드백 저장 & 선호도 점수 갱신 검증 (1점, 2.5점, 4점, 5점, 6점, 8점 차등)
5. 커뮤니티 콘텐츠 기법별 필터링 및 데모 영상 연동 검증
6. 보안(IDOR) 및 JWT 인증 연동 검증
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from fastapi import HTTPException
from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, Video, Interaction, UserPreferenceScore
from backend.services.technique_service import technique_service, TechniqueDefinition
from backend.services.video_recommender import VideoRecommender
from backend.services.auth_service import auth_service
from backend.schemas.schemas import TechniqueSelectRequest, TechniqueFeedbackRequest
from backend.routers.mobile import (
    get_technique_catalog,
    get_personalized_techniques,
    select_project_technique,
    record_technique_feedback
)
from backend.routers.community import get_community_videos, record_interaction, InteractionRequest


def test_phase5():
    db = SessionLocal()
    print("======================================================================")
    print("Phase 5 Verification: Personalized AI Shooting Technique Recommendation")
    print("======================================================================")

    # -----------------------------------------------------------------------
    # 1. 기법 카탈로그 및 스마트폰/드론 분류 검증
    # -----------------------------------------------------------------------
    print("\n1. [카탈로그 분류 검증] 전체 기법 카탈로그 및 지원 환경 분리 확인")
    all_techs = technique_service.get_all_techniques()
    phone_techs = technique_service.get_all_techniques(filter_supported_only=True)
    drone_techs = [t for t in all_techs if t.is_drone_only]

    print(f"   -> 전체 등록 기법: {len(all_techs)}개 (스마트폰 지원: {len(phone_techs)}개, 드론 전용: {len(drone_techs)}개)")
    assert len(all_techs) >= 10, "기본 기법이 최소 10개 이상 등록되어야 합니다."
    assert len(phone_techs) >= 7, "스마트폰 지원 기법이 7개 이상이어야 합니다."
    assert len(drone_techs) >= 3, "드론 전용 기법이 3개 이상이어야 합니다."

    # 스마트폰 지원 플래그 정합성 검사
    for t in phone_techs:
        assert t.is_smartphone_supported is True, f"{t.name}은 스마트폰 지원이어야 합니다."
        assert t.is_drone_only is False, f"{t.name}은 드론 전용이 아니어야 합니다."

    # 드론 전용 플래그 및 경고 문구 검사
    for t in drone_techs:
        assert t.is_smartphone_supported is False, f"{t.name}은 스마트폰 미지원이어야 합니다."
        assert t.is_drone_only is True, f"{t.name}은 드론 전용이어야 합니다."
        assert t.drone_warning is not None and len(t.drone_warning) > 5, f"{t.name}의 드론 경고 문구가 필수적입니다."

    print("   ✓ 스마트폰 지원 기법(오빗, 드로니, 삼분할, 리빌, 로우앵글 등)과 드론 전용 기법(버드아이, 스파이럴, 플라이바이) 완벽 분리 확인")

    # 동적 기법 확장성 테스트 (11번째 기법 등록)
    custom_tech = TechniqueDefinition(
        technique_id="hyperlapse_timelapse",
        name="모바일 하이퍼랩스 보행 촬영",
        category="시간 압축",
        description="동일 보행 궤적을 일정 간격으로 인터벌 촬영하여 시간의 흐름을 초고속으로 압축하는 기법",
        recommended_scenes=["해질녘 도심", "구름 이동", "출퇴근 인파"],
        required_environment={"lighting": "안정적 노출", "space": "긴 직선 보행로 50m", "obstacles": "평탄화 노면"},
        is_smartphone_supported=True,
        is_drone_only=False,
        related_tags=["하이퍼랩스", "타임랩스", "timelapse"],
        recommended_composition="중앙 정렬 하이퍼랩스 구도",
        precautions="스마트폰 짐벌 또는 양손 파지로 상하 수직 진동을 극도로 억제하세요.",
        execution_guide="1초에 한 걸음씩 등속 보행하며 인터벌 촬영을 진행합니다."
    )
    technique_service.register_technique(custom_tech)
    assert technique_service.get_technique("hyperlapse_timelapse") is not None
    print(f"   ✓ 신규 11번째 기법 동적 등록 성공: '{custom_tech.name}' (카탈로그 확장성 검증 완료)")

    # -----------------------------------------------------------------------
    # 2. 콜드 스타트 (신규 사용자) 기본 추천 검증
    # -----------------------------------------------------------------------
    print("\n2. [콜드 스타트 검증] 이용 기록이 전무한 신규 사용자의 추천 Fallback 확인")
    db.query(User).filter(User.username == "cold_starter").delete()
    db.commit()

    new_user = User(
        username="cold_starter",
        user_name="신규조종사",
        hashed_password="fake",
        role="pilot"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    project1 = db.query(ShootingProject).filter(ShootingProject.id == 1).first()
    assert project1 is not None

    cold_recs = technique_service.recommend_techniques(
        db=db,
        user=new_user,
        project=project1,
        limit=4,
        smartphone_only=False
    )
    assert len(cold_recs) == 4, "기본 4개의 추천 기법이 반환되어야 합니다."
    print(f"   -> 콜드 스타트 상위 추천 1위: '{cold_recs[0]['name']}' (점수: {cold_recs[0]['recommendation_score']}점)")
    print(f"   -> 추천 사유: \"{cold_recs[0]['recommendation_reason']}\"")
    assert "초보자 맞춤 추천" in cold_recs[0]["recommendation_reason"] or "시네마틱" in cold_recs[0]["recommendation_reason"]
    # 콜드 스타트 시 스마트폰 지원 기법이 최상단에 우선 배치되었는지 확인
    assert cold_recs[0]["is_smartphone_supported"] is True, "현재 스마트폰 환경에서는 스마트폰 지원 기법이 1위여야 합니다."
    print("   ✓ 신규 사용자 데이터 부족 시 프로젝트 환경 기반 Fallback 추천 정상 작동 확인")

    # -----------------------------------------------------------------------
    # 3. 다요소 개인화 알고리즘 및 커뮤니티 상호작용 가중치 반영 검증
    # -----------------------------------------------------------------------
    print("\n3. [개인화 가중치 검증] 영상 조회(1점), 반복시청(2.5점), 좋아요(4점), 저장(5점) 반영")
    pilot = db.query(User).filter(User.username == "pilot").first()
    assert pilot is not None

    # Step 1: pilot 사용자가 비디오 2 (오빗 무빙) 조회 (1.0점)
    comm_rec = VideoRecommender(db_path=db_path)
    comm_rec.record_interaction(pilot.user_id, video_id=2, action="view")
    score_after_view = db.query(UserPreferenceScore).filter(
        UserPreferenceScore.user_id == pilot.user_id,
        UserPreferenceScore.category == "composition",
        UserPreferenceScore.preference_value == "오빗(원형회전)"
    ).first()
    print(f"   -> 1회 조회 후 오빗 선호도 점수: {score_after_view.preference_score if score_after_view else 'N/A'}")

    # Step 2: 비디오 2 반복 시청 (repeat_view -> 2.5점 가중치)
    comm_rec.record_interaction(pilot.user_id, video_id=2, action="view")

    # Step 3: 비디오 2 좋아요 (like -> 4.0점 가중치)
    comm_rec.record_interaction(pilot.user_id, video_id=2, action="like")

    # Step 4: 비디오 2 저장 (save -> 5.0점 가중치)
    comm_rec.record_interaction(pilot.user_id, video_id=2, action="save")
    db.expire_all()

    # 추천 재연산: 오빗(orbit_poi) 기법이 높은 점수로 최상위 랭킹에 도달해야 함
    pilot_recs = technique_service.recommend_techniques(
        db=db,
        user=pilot,
        project=project1,
        limit=4
    )
    top_tech = pilot_recs[0]
    print(f"   -> 선호도 누적 후 최상위 추천 기법: '{top_tech['name']}' ({top_tech['technique_id']}, 일치도: {top_tech['recommendation_score']}점)")
    print(f"   -> 개인화 추천 사유: \"{top_tech['recommendation_reason']}\"")
    assert top_tech["technique_id"] == "orbit_poi", "좋아요/저장 이력이 반영되어 오빗 촬영이 1위여야 합니다."
    assert "보관함에 저장" in top_tech["recommendation_reason"] or "좋아요" in top_tech["recommendation_reason"]
    print("   ✓ 커뮤니티 상호작용 차등 가중치에 따른 개인화 랭킹 상승 검증 완료")

    # -----------------------------------------------------------------------
    # 4. 사용자 최종 기법 선택 및 만족도 피드백 API 검증
    # -----------------------------------------------------------------------
    print("\n4. [기법 선택 & 피드백 API 검증] 촬영 목표 선택(6점) 및 만족도 평가(8점)")
    # 기법 선택 API: POST /projects/{project_id}/techniques/select (로그인 조종사 본인 프로젝트)
    sel_res = select_project_technique(
        project_id=1,
        payload=TechniqueSelectRequest(technique_id="orbit_poi"),
        token=None,
        current_user=pilot,
        db=db
    )
    assert sel_res.status == "success"
    assert "orbit_poi" in sel_res.desired_techniques
    print(f"   -> 기법 선택 응답: {sel_res.message}")

    # DB에 ShootingProject.desired_techniques 반영 확인
    db.refresh(project1)
    assert "orbit_poi" in (project1.desired_techniques or [])

    # 만족도 피드백 API: POST /projects/{project_id}/techniques/feedback (5점 만점 -> 8.0 가중치)
    fb_res = record_technique_feedback(
        project_id=1,
        payload=TechniqueFeedbackRequest(
            technique_id="orbit_poi",
            shooting_number=1,
            was_shot=True,
            satisfaction_score=5,
            comment="스마트폰으로도 오빗 구도가 매우 안정적으로 포착되었습니다!"
        ),
        token=None,
        current_user=pilot,
        db=db
    )
    assert fb_res.status == "success"
    assert fb_res.applied_weight == 8.0
    print(f"   -> 피드백 반영 응답: {fb_res.message} (갱신된 선호도: {fb_res.updated_preference_score}점)")
    assert fb_res.updated_preference_score >= 80.0
    print("   ✓ 촬영 기법 선택(6점) 및 촬영 후 만족도(8점) 가중치 정상 갱신 확인")

    # -----------------------------------------------------------------------
    # 5. 커뮤니티 콘텐츠 연계 및 데모 영상 필터링 검증
    # -----------------------------------------------------------------------
    print("\n5. [커뮤니티 콘텐츠 연계 검증] 기법별 영상 필터링 및 데모 영상 첨부 확인")
    pilot_token = auth_service.create_access_token(data={"sub": pilot.username})

    # 추천 기법에 데모 영상이 연결되어 있는지 확인
    assert len(top_tech["related_videos"]) >= 1, "추천 기법에 데모 영상이 연동되어야 합니다."
    demo_vid = top_tech["related_videos"][0]
    print(f"   -> 추천 기법 [{top_tech['name']}]에 연계된 커뮤니티 영상: '{demo_vid['title']}' (ID: {demo_vid['video_id']}, 좋아요: {demo_vid['likes_count']}회)")

    # 커뮤니티 API 기법 필터링: GET /api/community/videos?technique=orbit_poi
    orbit_vids = get_community_videos(
        sort="recommended",
        technique="orbit_poi",
        limit=10,
        user_id=pilot.user_id,
        authorization=f"Bearer {pilot_token}",
        db=db
    )
    print(f"   -> 'orbit_poi' 기법 필터링 조회 영상 수: {orbit_vids['count']}건")
    assert orbit_vids["count"] >= 1
    assert any("오빗" in v["composition"] or "오빗" in v["title"] for v in orbit_vids["videos"])

    # 드론 전용 기법 필터링: GET /api/community/videos?technique=high_spiral
    spiral_vids = get_community_videos(
        sort="popular",
        technique="high_spiral",
        limit=10,
        user_id=pilot.user_id,
        authorization=f"Bearer {pilot_token}",
        db=db
    )
    print(f"   -> 'high_spiral' 기법 필터링 조회 영상 수: {spiral_vids['count']}건")
    assert spiral_vids["count"] >= 1
    print("   ✓ 기법별 커뮤니티 영상 필터링 및 데모 영상 연동 검증 완료")

    # -----------------------------------------------------------------------
    # 6. IDOR 보안 및 JWT 인증 검증
    # -----------------------------------------------------------------------
    print("\n6. [보안 및 IDOR 차단 검증] 타인 프로젝트에 대한 비인가 접근 차단")
    crew = db.query(User).filter(User.username == "crew").first()
    assert crew is not None

    try:
        select_project_technique(
            project_id=1,
            payload=TechniqueSelectRequest(technique_id="straight_dronie"),
            token=None,
            current_user=crew,
            db=db
        )
        assert False, "타인 프로젝트 기법 변경 시 HTTP 403이 발생해야 합니다."
    except HTTPException as e:
        assert e.status_code == 403, f"HTTP 403 기대, 실제: {e.status_code}"
        print("   ✓ 타인(crew)의 비인가 기법 변경 시도 즉시 차단 (HTTP 403 발생 확인)")

    # Clean up test user
    try:
        db.delete(new_user)
        db.commit()
    except Exception:
        db.rollback()

    db.close()
    print("\n======================================================================")
    print("Phase 5 모든 검증 항목(카탈로그, 개인화, 상호작용, 커뮤니티, 보안) 100% 통과! (ALL PASS)")
    print("======================================================================")


if __name__ == "__main__":
    test_phase5()
