import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, ShootingPath, LocationAsset
from backend.routers.mobile import resolve_mobile_project, get_project_shooting_summary
from backend.services.auth_service import auth_service

def test_phase3():
    db = SessionLocal()
    print("======================================================================")
    print("Phase 3 Verification: Smartphone Camera & Sensor Integration")
    print("======================================================================")

    # 1. Check frontend camera.html file existence and size
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend"))
    camera_path = os.path.join(frontend_dir, "camera.html")
    assert os.path.exists(camera_path), f"camera.html not found at {camera_path}"
    with open(camera_path, "r", encoding="utf-8") as f:
        camera_html = f.read()

    print(f"1. [프론트엔드 확인] camera.html 크기: {len(camera_html)} bytes")
    assert "getUserMedia" in camera_html, "getUserMedia not found in camera.html"
    assert "PHONE_GPS" in camera_html, "PHONE_GPS not found in camera.html"
    assert "watchPosition" in camera_html, "watchPosition not found in camera.html"
    assert "drawCroppedFrame" in camera_html, "drawCroppedFrame not found in camera.html"
    assert "deviceorientation" in camera_html, "deviceorientation not found in camera.html"
    assert "/api/mobile/projects/" in camera_html, "mobile projects API not found"
    print("   -> 후면 카메라, GPS(PHONE_GPS), 디바이스 방향 센서, 크롭 렌더러, 백엔드 API 연동 스크립트 정상 탑재 확인")

    # 2. Test resolve_mobile_project endpoint
    proj1 = db.query(ShootingProject).filter(ShootingProject.id == 1).first()
    assert proj1 is not None, "Project 1 must exist"

    # Resolve by ID string
    res_by_id = resolve_mobile_project(identifier=str(proj1.project_id), db=db)
    assert res_by_id["project_id"] == proj1.project_id
    print(f"2. [API 검증] ID({proj1.project_id}) 기준 프로젝트 식별 성공: '{res_by_id['title']}'")

    # Resolve by project_code string if present
    if proj1.project_code:
        res_by_code = resolve_mobile_project(identifier=proj1.project_code, db=db)
        assert res_by_code["project_id"] == proj1.project_id
        print(f"   -> 코드('{proj1.project_code}') 기준 프로젝트 식별 성공: '{res_by_code['title']}'")

    # 3. Test shooting summary with owner user
    owner = db.query(User).filter(User.id == proj1.user_id).first() if proj1.user_id else None
    if not owner:
        owner = db.query(User).filter(User.username == "pilot").first()
    summary = get_project_shooting_summary(project_id=proj1.project_id, current_user=owner, db=db)
    print(f"3. [회차 연동 확인 (로그인 사용자)] 프로젝트 {proj1.project_id} 누적 촬영: {summary['total_attempts']}회 (최신 회차: {summary['latest_shooting_number']}회)")

    # Test shooting summary with QR token
    qr_token = auth_service.create_project_access_token(project_code=proj1.project_code, project_id=proj1.id)
    summary_qr = get_project_shooting_summary(project_id=proj1.project_id, token=qr_token, db=db)
    assert summary_qr["total_attempts"] == summary["total_attempts"]
    print(f"   -> [회차 연동 확인 (QR 토큰 크루)] 동선 요약 일치 확인 (총 {summary_qr['total_attempts']}회 시도)")

    # 4. Check that auth_service and JWT are intact
    assert hasattr(auth_service, "verify_project_ownership")
    assert hasattr(auth_service, "create_access_token")
    print("4. [보안 및 인증 검증] auth_service 함수 정상 보존 확인 (create_access_token, verify_project_ownership)")

    print("======================================================================")
    print("Phase 3 스마트폰 카메라 및 센서 연동 사전/통합 검증 100% 완료!")
    print("======================================================================")
    db.close()

if __name__ == "__main__":
    test_phase3()
