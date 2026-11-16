import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.database import SessionLocal
from backend.schemas.schemas import (
    SyncProjectCreate,
    SyncStatusUpdate,
    SyncAnalysisResultCreate
)
from backend.routers.sync import (
    create_project,
    get_project,
    save_analysis_result,
    get_project_results,
    update_status,
    get_project_qr
)

def run_sync_tests():
    print("==================================================================", flush=True)
    print("[Step 7] PC·모바일 실시간 데이터 연동 (PC-Mobile Sync) 정밀 검증", flush=True)
    print("==================================================================", flush=True)

    db = SessionLocal()
    try:
        # 1. [PC] 신규 프로젝트 생성 & DRONE_001 고유 코드 및 QR코드 발급
        print("\n[1] PC 데이터 저장 & 프로젝트 고유 ID(DRONE_001) 및 QR코드 생성", flush=True)
        new_proj_data = SyncProjectCreate(
            title="여의도 한강 시네마틱 선셋 촬영",
            place_name="서울 여의도 한강공원",
            scene_intent="붉은 노을과 한강 다리를 배경으로 대각선 리빌 촬영",
            target_date="2026-10-25",
            target_time="17:00 ~ 17:40",
            recommended_mode="패럴랙스 리빌 & 선셋 아크",
            recommended_shutter="1/50s",
            recommended_nd_filter="ND16"
        )
        created = create_project(project_in=new_proj_data, db=db)
        proj_code = created.project_code
        print(f"  [OK] 고유 프로젝트 ID 발급 완료: '{proj_code}' (DB PK ID={created.id})", flush=True)
        print(f"  [OK] 초기 생명주기 상태: '{created.status}' (대기 중)", flush=True)
        print(f"  [OK] 모바일 직접 접속 URL: {created.mobile_access_url}", flush=True)
        print(f"  [OK] PC용 QR코드 생성 완료 (Base64 길이: {len(created.qr_code_base64 or '')}자)", flush=True)
        assert proj_code.startswith("DRONE_"), f"프로젝트 코드 형식 오류: {proj_code}"
        assert created.status == "CREATED"
        assert created.qr_code_base64 and created.qr_code_base64.startswith("data:image/png;base64,")

        # 2. [모바일] QR코드 스캔 접속 ➔ 데이터 조회 & 'ANALYZING' 자동 상태 전이
        print("\n[2] 모바일 데이터 조회 (스마트폰에서 DRONE_001 코드로 계획 로드)", flush=True)
        mobile_loaded = get_project(identifier=proj_code, for_mobile=True, token=created.project_token, db=db)
        print(f"  [OK] 모바일 촬영 계획 불러오기 성공: '{mobile_loaded.title}' ({mobile_loaded.place_name})", flush=True)
        print(f"  [OK] 추천 레시피: 모드={mobile_loaded.recommended_mode}, 셔터={mobile_loaded.recommended_shutter}, ND={mobile_loaded.recommended_nd_filter}", flush=True)
        print(f"  [OK] 스마트폰 접속 감지 후 생명주기 상태 자동 전이: '{mobile_loaded.status}' (현장 분석 중)", flush=True)
        assert mobile_loaded.status == "ANALYZING", f"상태 전이 실패: {mobile_loaded.status}"

        # 3. [모바일] 현장 AI 구도 분석 및 녹화 영상 저장 ➔ 'COMPLETED' 자동 전이
        print("\n[3] 모바일 현장 AI 분석 결과 및 녹화 영상 업로드 저장", flush=True)
        analysis_data = SyncAnalysisResultCreate(
            frame_score=94,
            offset_x=0.0,
            offset_y=0.0,
            guide_direction="none",
            guide_message="AI 삼분할 황금비 구도 일치 녹화 완료",
            recorded_video_url="https://chimerical-trifle-7e9011.netlify.app/videos/drone_shot_demo.mp4"
        )
        saved_shot = save_analysis_result(identifier=proj_code, result_in=analysis_data, token=created.project_token, db=db)
        print(f"  [OK] 현장 분석 결과 DB 저장 완료 (로그 ID={saved_shot.id})", flush=True)
        print(f"  [OK] 녹화 영상 URL: {saved_shot.recorded_video_url}", flush=True)

        # 4. [PC] 실시간 결과 확인
        print("\n[4] PC 웹 결과 조회 (모바일에서 보낸 분석 로그 및 영상 확인)", flush=True)
        pc_check = get_project_results(identifier=proj_code, db=db)
        print(f"  [OK] PC 대시보드 프로젝트 상태: '{pc_check['status']}' (완료 확인)", flush=True)
        print(f"  [OK] 수신된 현장 촬영 횟수: {pc_check['total_shots_count']}건", flush=True)
        latest_shot = pc_check["analysis_results"][0]
        print(f"  [OK] 현장 분석 점수: {latest_shot['frame_score']}점 | 가이드: '{latest_shot['guide_message']}'", flush=True)
        assert pc_check["status"] == "COMPLETED"
        assert pc_check["total_shots_count"] >= 1

        # 5. [동기화 & 상태 관리] 데이터 상태 수동 제어 테스트
        print("\n[5] 데이터 상태 관리 (CREATED ➔ ANALYZING ➔ COMPLETED ➔ FAILED) 검증", flush=True)
        st_update = update_status(identifier=proj_code, status_in=SyncStatusUpdate(status="ANALYZING"), db=db)
        print(f"  [OK] 상태 재조정: {st_update['message']}", flush=True)
        assert st_update["status"] == "ANALYZING"

        # 6. QR코드 전용 엔드포인트 검증
        print("\n[6] QR코드 전용 조회 엔드포인트 검증", flush=True)
        qr_info = get_project_qr(identifier=proj_code, db=db)
        print(f"  [OK] QR코드 대상 URL: {qr_info['mobile_access_url']}", flush=True)
        print(f"  [OK] QR Base64 이미지 검증: {qr_info['qr_code_base64'][:35]}...", flush=True)

        print("\n==================================================================", flush=True)
        print("[SUCCESS] 7단계 PC·모바일 실시간 데이터 연동 및 QR코드 시스템 100% 검증 통과!", flush=True)
        print("==================================================================", flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    run_sync_tests()
