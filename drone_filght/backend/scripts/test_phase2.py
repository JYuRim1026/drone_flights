import sys
import os
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "drone_filght"))

# Target: sky_command_demo.db
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sky_command_demo.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from backend.database import SessionLocal
from backend.models.models import User, ShootingProject, ShootingPath, LocationAsset
from backend.schemas.schemas import (
    ShootingPathCreate, ShootingPathResponse,
    LocationAssetCreate, LocationAssetResponse,
    ShootingPathProjectSummary
)
from backend.services.auth_service import auth_service
from backend.services.mobile_service import mobile_service
from backend.routers.mobile import (
    save_shooting_path,
    get_shooting_paths,
    get_project_shooting_summary,
    get_shooting_path_by_number,
    get_shooting_path_detail,
    create_location_asset,
    upload_location_asset_file,
    get_project_location_assets,
    get_location_asset_detail,
    delete_location_asset
)
from fastapi import HTTPException, UploadFile
import io

def run_tests():
    print("=" * 70)
    print("Phase 2 Backend API Verification Test Suite (Direct Execution)")
    print("=" * 70)

    db = SessionLocal()

    try:
        # 1. Authenticate users
        pilot = auth_service.authenticate_user(db, "pilot", "pilot1234")
        assert pilot is not None, "Pilot authentication failed"
        crew = auth_service.authenticate_user(db, "crew", "crew1234")
        assert crew is not None, "Crew authentication failed"
        print(f"1. [인증 확인] pilot (ID: {pilot.id}), crew (ID: {crew.id}) 인증 성공")

        # 2. Project Ownership Setup
        project = db.query(ShootingProject).first()
        assert project is not None, "No project in DB"
        proj_id = project.id
        project.user_id = pilot.id
        db.commit()
        db.refresh(project)
        print(f"2. [프로젝트 확인] ID: {proj_id} ('{project.title}') 소유자 pilot({pilot.id}) 설정 완료")

        # 3. IDOR / Access Control Check
        # Pilot owns the project -> verify_project_ownership succeeds
        p_check = auth_service.verify_project_ownership(db, str(proj_id), current_user=pilot)
        assert p_check.id == proj_id

        # Crew does not own the project -> expect 403 Forbidden
        try:
            auth_service.verify_project_ownership(db, str(proj_id), current_user=crew)
            assert False, "Crew should not have access to pilot's project without token"
        except HTTPException as e:
            assert e.status_code == 403
            print("3. [IDOR 차단 확인] 타인(crew)의 비인가 접근 즉각 차단 (HTTP 403 정상 발생)")

        # 4. Save Shooting Path (1st Round)
        path_in_1 = ShootingPathCreate(
            project_id=proj_id,
            shooting_number=1,
            tracking_source="PHONE_GPS",
            recommended_waypoints=[{"seq": 1, "lat": 37.5284, "lng": 126.9328, "target_heading": 180.0}],
            actual_waypoints=[{
                "seq": 1,
                "timestamp": "2026-11-21T22:50:00Z",
                "raw_gps": {"lat": 37.52841, "lng": 126.93282, "accuracy_m": 4.0, "altitude_m": None},
                "camera_orientation": {"camera_heading_deg": 181.5, "camera_pitch_deg": -10.0, "camera_roll_deg": 0.0},
                "composition_state": {"score": 88}
            }],
            corrected_waypoints=[{"seq": 1, "lat": 37.5284, "lng": 126.9328}],
            alpha_weight=0.3,
            deviation_score=0.85,
            deviation_reason="NORMAL",
            is_valid=True
        )
        saved_1 = save_shooting_path(proj_id, path_in_1, current_user=pilot, db=db)
        assert saved_1.path_id is not None
        assert saved_1.shooting_number == 1
        print(f"4. [동선 저장 1회차] Path ID: {saved_1.path_id}, 회차: {saved_1.shooting_number}, 출처: {saved_1.tracking_source}")

        # 5. Save Shooting Path (2nd Round - Auto increment)
        path_in_2 = ShootingPathCreate(
            project_id=proj_id,
            shooting_number=None, # auto-increment
            tracking_source="PHONE_GPS",
            recommended_waypoints=[],
            actual_waypoints=[{"seq": 1, "raw_gps": {"lat": 37.5285, "lng": 126.9329}}],
            corrected_waypoints=[],
            alpha_weight=0.3,
            deviation_score=1.5,
            deviation_reason="WALKING_DETOUR",
            is_valid=True
        )
        saved_2 = save_shooting_path(proj_id, path_in_2, current_user=pilot, db=db)
        assert saved_2.shooting_number >= 2
        print(f"5. [동선 저장 차기 회차] Path ID: {saved_2.path_id}, 회차: {saved_2.shooting_number} (자동 증분 정상 동작)")

        # 6. List Shooting Paths for Project
        paths_list = get_shooting_paths(proj_id, current_user=pilot, db=db)
        assert len(paths_list) >= 2
        print(f"6. [동선 목록 조회] 프로젝트 {proj_id} 누적 촬영 동선: {len(paths_list)}건 확인")

        # 7. Shooting Path Summary
        summary = get_project_shooting_summary(proj_id, current_user=pilot, db=db)
        total_att = summary["total_attempts"] if isinstance(summary, dict) else summary.total_attempts
        latest_num = summary["latest_shooting_number"] if isinstance(summary, dict) else summary.latest_shooting_number
        valid_cnt = summary["valid_paths_count"] if isinstance(summary, dict) else summary.valid_paths_count
        assert total_att >= 2
        assert latest_num >= 2
        assert valid_cnt >= 2
        print(f"7. [동선 요약 조회] 총 시도: {total_att}회, 최신 회차: {latest_num}회, 유효 경로: {valid_cnt}건")

        # 8. Detail Views (by ID & by round number)
        detail_by_id = get_shooting_path_detail(saved_1.path_id, current_user=pilot, db=db)
        assert detail_by_id.path_id == saved_1.path_id
        detail_by_num = get_shooting_path_by_number(proj_id, 1, current_user=pilot, db=db)
        assert detail_by_num.shooting_number == 1
        print("8. [동선 상세 조회] path_id 및 shooting_number 기준 조회 일치 확인")

        # 9. Register Location Asset (JSON)
        asset_in = LocationAssetCreate(
            project_id=proj_id,
            is_common=True,
            asset_type="PANORAMA",
            file_url="https://storage.skycommand.kr/panorama/view_360.jpg",
            thumbnail_url="https://storage.skycommand.kr/panorama/thumb.jpg",
            detected_features={"horizon_y": 0.52, "landmarks": ["여의도 랜드마크"]},
            file_size_bytes=204800
        )
        asset_common = create_location_asset(proj_id, asset_in, current_user=pilot, db=db)
        assert asset_common.asset_id is not None
        assert asset_common.is_common == True
        print(f"9. [장소 자료 JSON 등록] Asset ID: {asset_common.asset_id}, 타입: {asset_common.asset_type}, 공통 여부: {asset_common.is_common}")

        # 10. Real Physical File Upload (Direct Service & Storage validation)
        dummy_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdbRealSmartphonePhoto"
        
        uploaded = mobile_service.save_uploaded_asset(
            db=db,
            project_id=proj_id,
            filename="phone_panorama.jpg",
            file_bytes=dummy_content,
            asset_type="CAMERA_FRAME",
            is_common=False,
            detected_features={"horizon": 0.5, "objects": ["river", "park"]},
            current_user=pilot
        )
        assert uploaded.asset_id is not None
        assert uploaded.file_size_bytes == len(dummy_content)
        print(f"10. [실제 물리 파일 저장] Asset ID: {uploaded.asset_id}, 파일 URL: {uploaded.file_url}, 크기: {uploaded.file_size_bytes} bytes")

        # 11. Verify Physical File on Disk
        url_parts = uploaded.file_url.split("/api/mobile/assets/files/")[-1].split("/")
        from backend.services.mobile_service import UPLOAD_DIR
        physical_file = os.path.join(UPLOAD_DIR, url_parts[0], url_parts[1])
        assert os.path.exists(physical_file), f"Physical file missing at {physical_file}"
        with open(physical_file, "rb") as pf:
            assert pf.read() == dummy_content
        print(f"11. [물리 파일 저장소 검증] 디스크 파일 실재 확인: {physical_file}")

        # 12. Asset Permission Isolation Check
        # Pilot (Owner) can see both common and personal assets
        pilot_assets = get_project_location_assets(proj_id, current_user=pilot, db=db)
        assert len(pilot_assets) >= 2
        print(f"12. [권한 격리 검증 - 소유자] pilot이 열람 가능한 자료: {len(pilot_assets)}건 (공통 + 개인 전체)")

        # Project token access (Field crew without personal ownership)
        proj_token = auth_service.create_project_access_token(project_code=project.project_code, project_id=project.id)
        project.project_token = proj_token
        db.commit()

        crew_assets = get_project_location_assets(proj_id, token=proj_token, current_user=None, db=db)
        for a in crew_assets:
            assert a.is_common == True, "Non-owner should not see private personal assets"
        print(f"13. [권한 격리 검증 - 현장 크루] QR 토큰 크루가 열람 가능한 자료: {len(crew_assets)}건 (오직 공통 자료만 노출, 개인 자료 완벽 격리)")

        # 13. Delete Asset
        del_res = delete_location_asset(uploaded.asset_id, current_user=pilot, db=db)
        assert del_res["success"] == True
        assert not os.path.exists(physical_file), "Physical file should be deleted on disk"
        print("14. [자료 삭제 및 물리 파일 정리] DB 레코드 및 디스크 파일 정상 삭제 완료")

        print("=" * 70)
        print("모든 Phase 2 백엔드 API 기능 테스트가 100% 성공적으로 통과했습니다! (14/14 PASS)")
        print("=" * 70)

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
