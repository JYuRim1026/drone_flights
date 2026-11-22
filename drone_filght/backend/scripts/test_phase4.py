import os
import sys
import base64
import io
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, ShootingAnalysis
from backend.schemas.schemas import AnalyzeRequest
from backend.services.ai_service import ai_service
from backend.routers.mobile import analyze_frame, get_project_analyses, get_latest_project_analysis

def create_sample_image_base64() -> str:
    """Create a sample 300x300 image with a simulated building/subject on the right half."""
    img = Image.new("RGB", (300, 300), color=(135, 206, 235)) # Sky blue
    # Draw building on right
    for x in range(160, 260):
        for y in range(80, 290):
            img.putpixel((x, y), (70, 70, 80)) # Dark building
    # Draw ground on bottom
    for x in range(0, 300):
        for y in range(250, 300):
            img.putpixel((x, y), (34, 139, 34)) # Forest green ground

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

def test_phase4():
    db = SessionLocal()
    print("======================================================================")
    print("Phase 4 Verification: AI Scene Analysis & Composition Recommendation")
    print("======================================================================")

    # 1. Pilot user & Project 1 verification
    pilot = db.query(User).filter(User.username == "pilot").first()
    assert pilot is not None, "pilot user must exist"
    project = db.query(ShootingProject).filter(ShootingProject.id == 1).first()
    assert project is not None, "project 1 must exist"

    sample_b64 = create_sample_image_base64()
    print("1. [테스트 프레임 준비] 300x300 합성 시네마틱 프레임 생성 완료 (스카이라인 & 수평선 포함)")

    # 2. Test AIService.analyze_scene_and_recommend (Direct Service Call)
    # Test A: Purpose = orbit (Center Framing)
    res_orbit = ai_service.analyze_scene_and_recommend(
        image_base64=sample_b64,
        scene_intent="한강변 도심 빌딩 일몰 시네마틱",
        purpose="orbit",
        current_pitch=-10.0,
        current_roll=0.0,
        current_heading=145.0,
        project_id=project.id,
        shooting_number=1,
        current_user=pilot,
        save_to_db=True,
        db=db
    )
    assert res_orbit.project_id == project.id
    assert res_orbit.subject is not None
    assert res_orbit.recommended_composition is not None
    assert "중앙 배치" in res_orbit.recommended_composition
    assert res_orbit.target_position == {"target_x": 0.0, "target_y": 0.0}
    assert res_orbit.analysis_id is not None
    print(f"2. [서비스 분석 - POI Orbit] 추천 구도: '{res_orbit.recommended_composition}'")
    print(f"   -> 피사체: {res_orbit.subject}")
    print(f"   -> 보정 안내: {res_orbit.guide_direction} (오프셋: x={res_orbit.offset_x}, y={res_orbit.offset_y})")
    print(f"   -> DB 분석 ID: {res_orbit.analysis_id}, 점수: {res_orbit.frame_score}점")

    # Test B: Purpose = thirds (Rule of Thirds)
    res_thirds = ai_service.analyze_scene_and_recommend(
        image_base64=sample_b64,
        scene_intent="한강 인물 및 조형물 삼분할 촬영",
        purpose="thirds",
        current_pitch=-15.0,
        current_roll=0.0,
        project_id=project.id,
        shooting_number=2,
        current_user=pilot,
        save_to_db=True,
        db=db
    )
    assert "삼분할" in res_thirds.recommended_composition
    print(f"   -> [서비스 분석 - 삼분할 구도] 추천: '{res_thirds.recommended_composition}', 목표 X: {res_thirds.target_position['target_x']}")

    # Test C: Sensor Roll compensation check (Requirement 5)
    res_roll = ai_service.analyze_scene_and_recommend(
        image_base64=sample_b64,
        purpose="landscape",
        current_pitch=-5.0,
        current_roll=7.5, # Tilted right by 7.5 deg
        project_id=project.id,
        current_user=pilot,
        save_to_db=False,
        db=db
    )
    assert res_roll.guide_direction == "level_right"
    assert "기울어졌습니다" in res_roll.guide_message
    print(f"   -> [센서 연동 - 롤 각도 보정] 7.5° 기울어짐 감지: '{res_roll.guide_message}' (방향: {res_roll.guide_direction})")

    # 3. Test Router endpoint: POST /api/mobile/analyze
    req_payload = AnalyzeRequest(
        project_id=project.id,
        image_base64=sample_b64,
        purpose="dronie",
        scene_intent="골든아워 직선 플라이스루",
        current_pitch=-12.0,
        current_roll=0.0,
        shooting_number=3,
        save_result=True
    )
    router_res = analyze_frame(req=req_payload, current_user=pilot, db=db)
    assert router_res.project_id == project.id
    assert "리딩라인" in router_res.recommended_composition
    print(f"3. [Router POST /analyze 검증] 엔드포인트 응답 성공: '{router_res.recommended_composition}' (분석 ID: {router_res.analysis_id})")

    # 4. Test Router endpoint: GET /api/mobile/projects/{project_id}/analyses
    analyses_list = get_project_analyses(project_id=project.id, current_user=pilot, db=db)
    assert len(analyses_list) >= 3, f"Expected at least 3 analyses, got {len(analyses_list)}"
    print(f"4. [Router GET /analyses 검증] 프로젝트 {project.id} 분석 이력 총 {len(analyses_list)}건 조회 성공")

    # 5. Test Router endpoint: GET /api/mobile/projects/{project_id}/analyses/latest
    latest = get_latest_project_analysis(project_id=project.id, current_user=pilot, db=db)
    assert latest["analysis_id"] == router_res.analysis_id
    assert latest["target_coordinates"]["shooting_number"] == 3
    print(f"5. [Router GET /analyses/latest 검증] 최신 분석 ID {latest['analysis_id']} (회차: {latest['target_coordinates']['shooting_number']}, 구도: '{latest['recommended_composition']}')")

    # 6. Verify ShootingAnalysis DB record columns and integrity
    db_rec = db.query(ShootingAnalysis).filter(ShootingAnalysis.analysis_id == router_res.analysis_id).first()
    assert db_rec is not None
    assert db_rec.project_id == project.id
    assert db_rec.target_coordinates["user_id"] == pilot.id
    assert db_rec.composition_score is not None
    assert db_rec.guide_message is not None
    print(f"6. [DB 무결성 검증] shooting_analyses 레코드 저장 확인 (User ID: {db_rec.target_coordinates['user_id']}, 점수: {db_rec.composition_score})")

    print("======================================================================")
    print("Phase 4 AI 촬영 장면 분석 및 구도 추천 검증 100% 통과! (ALL PASS)")
    print("======================================================================")
    db.close()

if __name__ == "__main__":
    test_phase4()
