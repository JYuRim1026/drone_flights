"""
Step 8: 사용자 인증 및 보안 (User Authentication & Security) 종합 검증 스위트
1. 사용자 등록 (Bcrypt 단방향 암호화, XSS 살균, 중복 방어)
2. 로그인 및 JWT Access Token 발급/만료/위조 방어
3. 토큰 검증 및 프로필 조회 (/api/auth/me)
4. 화면별 기능 권한 제어 (PC vs 모바일 화면 분리)
5. 프로젝트별 서명된 보안 토큰 & 타인 데이터 접근 차단 (IDOR 방어)
6. 외부 API 키 은닉 및 상태 마스킹 (Frontend Zero-Exposure)
7. 악의적 입력값 유효성 검증 및 살균
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import jwt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from pydantic import ValidationError

from backend.database import SessionLocal
from backend.models.models import User, ShootingProject
from backend.config import settings
from backend.services.auth_service import auth_service
from backend.routers.auth import (
    register,
    login,
    get_my_profile,
    check_screen_access,
    generate_project_token,
    verify_project_token,
    check_api_keys_security
)
from backend.routers.sync import (
    create_project as sync_create_project,
    get_project as sync_get_project,
    save_analysis_result as sync_save_result,
    get_project_results as sync_get_results
)
from backend.schemas.schemas import (
    UserRegister,
    UserLogin,
    SyncProjectCreate,
    SyncAnalysisResultCreate
)


def run_auth_security_tests():
    db = SessionLocal()
    print("=" * 66)
    print("[Step 8] 사용자 인증 및 보안 (Authentication & Security) 정밀 검증")
    print("=" * 66)

    try:
        # ---------------------------------------------------------
        # [0] 기본 계정 시드 초기화
        # ---------------------------------------------------------
        auth_service.init_default_users(db)
        print("\n[0] 기본 역할별 계정 시드 점검 (Bcrypt 암호화 저장)")
        pilot_user = db.query(User).filter(User.username == "pilot").first()
        crew_user = db.query(User).filter(User.username == "crew").first()
        admin_user = db.query(User).filter(User.username == "admin").first()
        
        assert pilot_user and pilot_user.hashed_password.startswith("$2b$")
        assert crew_user and crew_user.role == "crew"
        assert admin_user and admin_user.role == "admin"
        print(f"  [OK] pilot 계정 확인: ID={pilot_user.id}, role={pilot_user.role}, Bcrypt 해시={pilot_user.hashed_password[:15]}...")
        print(f"  [OK] crew 계정 확인 : ID={crew_user.id}, role={crew_user.role}")
        print(f"  [OK] admin 계정 확인: ID={admin_user.id}, role={admin_user.role}")

        # ---------------------------------------------------------
        # [1] 사용자 등록 (회원가입 & XSS 살균)
        # ---------------------------------------------------------
        print("\n[1] 신규 사용자 등록 & XSS 입력 살균 검증")
        test_username = f"sky_pilot_{int(datetime.now().timestamp())}"
        xss_name = "<script>alert('XSS')</script>보안조종사"
        reg_in = UserRegister(
            username=test_username,
            password="securePassword2026!",
            full_name=xss_name,
            email=f"{test_username}@skycommand.kr",
            role="pilot",
            drone_model="DJI Mavic 3 Pro",
            drone_weight_g=958
        )
        reg_res = register(user_in=reg_in, db=db)
        assert reg_res.username == test_username
        assert "<script>" not in reg_res.full_name, "XSS script 태그가 정제되지 않았습니다."
        assert reg_res.role == "pilot"
        print(f"  [OK] 신규 사용자 등록 성공: {reg_res.username} (역할: {reg_res.role})")
        print(f"  [OK] XSS 태그 자동 살균 완료: '{xss_name}' ➔ '{reg_res.full_name}'")

        # 중복 아이디 등록 차단 검증
        try:
            register(user_in=reg_in, db=db)
            assert False, "중복 아이디 등록이 허용되었습니다."
        except HTTPException as e:
            assert e.status_code == 400
            print(f"  [OK] 중복 아이디 차단 검증 통과 (400 Bad Request: {e.detail})")

        # ---------------------------------------------------------
        # [2] 사용자 로그인 & JWT 토큰 발급
        # ---------------------------------------------------------
        print("\n[2] 사용자 로그인 & RFC 7519 규격 JWT Access Token 발급")
        # 2-1) 틀린 비밀번호 차단
        bad_login = UserLogin(username=test_username, password="wrong_password_123")
        try:
            login(login_in=bad_login, db=db)
            assert False, "틀린 비밀번호 로그인이 통과되었습니다."
        except HTTPException as e:
            assert e.status_code == 401
            print("  [OK] 잘못된 비밀번호 로그인 즉시 차단 (401 Unauthorized)")

        # 2-2) 정상 로그인 & JWT 수신
        good_login = UserLogin(username=test_username, password="securePassword2026!")
        token_res = login(login_in=good_login, db=db)
        assert token_res.access_token is not None
        assert token_res.token_type == "bearer"
        assert token_res.role == "pilot"
        assert "pc" in token_res.allowed_screens
        print(f"  [OK] 로그인 성공 & JWT 발급: {token_res.access_token[:25]}... (길이: {len(token_res.access_token)}자)")
        print(f"  [OK] 사용자 역할 및 허용 화면: role={token_res.role}, allowed_screens={token_res.allowed_screens}")

        # ---------------------------------------------------------
        # [3] JWT 토큰 검증 & 프로필 조회 (/api/auth/me)
        # ---------------------------------------------------------
        print("\n[3] JWT 토큰 서명/만료 검증 및 위조 방어")
        # 정상 토큰 복호화
        decoded = auth_service.decode_access_token(token_res.access_token)
        assert decoded["sub"] == test_username
        print(f"  [OK] 토큰 서명 검증 성공: sub={decoded['sub']}, token_type={decoded['token_type']}")

        # 위조된 토큰(Tampered Token) 차단
        tampered_token = token_res.access_token[:-5] + "XXXXX"
        try:
            auth_service.decode_access_token(tampered_token)
            assert False, "위조된 토큰이 통과되었습니다."
        except HTTPException as e:
            assert e.status_code == 401
            print("  [OK] 위조된 서명 토큰 감지 및 차단 (401 Unauthorized)")

        # 만료된 토큰(Expired Token) 차단
        expired_token = auth_service.create_access_token(
            data={"sub": test_username, "role": "pilot"},
            expires_delta=timedelta(seconds=-10)
        )
        try:
            auth_service.decode_access_token(expired_token)
            assert False, "만료된 토큰이 통과되었습니다."
        except HTTPException as e:
            assert e.status_code == 401
            print("  [OK] 만료된 토큰 감지 및 거부 (401 ExpiredSignature)")

        # ---------------------------------------------------------
        # [4] 화면별 기능 권한 제어 (PC vs 모바일 권한 분리)
        # ---------------------------------------------------------
        print("\n[4] 화면별 기능 권한 제어 (PC 화면 vs 모바일 화면)")
        created_user_obj = db.query(User).filter(User.username == test_username).first()

        # PC 조종사(pilot)의 PC 화면 접근 ➔ 허용
        pc_check = check_screen_access(screen="pc", current_user=created_user_obj)
        assert pc_check["allowed"] is True
        print(f"  [OK] pilot 사용자 ➔ PC 기능 접근: 허용됨 ({pc_check['message']})")

        # 현장 촬영팀(crew)의 PC 화면 접근 ➔ 403 차단!
        try:
            check_screen_access(screen="pc", current_user=crew_user)
            assert False, "crew 사용자의 PC 기능 접근이 허용되었습니다."
        except HTTPException as e:
            assert e.status_code == 403
            print("  [OK] crew 사용자 ➔ PC 전용 기능 접근 시도: 차단 성공 (403 Forbidden)")

        # 현장 촬영팀(crew)의 모바일 화면 접근 ➔ 허용
        mob_check = check_screen_access(screen="mobile", current_user=crew_user)
        assert mob_check["allowed"] is True
        print(f"  [OK] crew 사용자 ➔ 모바일 기능 접근: 허용됨 ({mob_check['message']})")

        # 최고 관리자(admin)는 PC, 모바일 모두 허용
        admin_pc = check_screen_access(screen="pc", current_user=admin_user)
        admin_mob = check_screen_access(screen="mobile", current_user=admin_user)
        assert admin_pc["allowed"] and admin_mob["allowed"]
        print("  [OK] admin 사용자 ➔ 전 화면(PC/모바일/관리자) 접근 전체 승인")

        # ---------------------------------------------------------
        # [5] 프로젝트별 보안 토큰 & 타인 데이터 접근 차단 (IDOR 방어)
        # ---------------------------------------------------------
        print("\n[5] 프로젝트별 서명된 보안 토큰 & 타인 데이터 접근 차단 (IDOR 방어)")
        # 5-1) pilot 사용자가 본인 프로젝트 생성
        sec_proj_in = SyncProjectCreate(
            title="보안 통제 구역 시네마틱 촬영",
            place_name="서울 여의도 한강공원",
            scene_intent="보안 토큰 기반 모바일 페어링 검증",
            target_date="2026-10-24",
            target_time="16:00 ~ 17:30"
        )
        sec_proj = sync_create_project(project_in=sec_proj_in, db=db, current_user=created_user_obj)
        assert sec_proj.project_token is not None
        assert f"&token={sec_proj.project_token}" in sec_proj.mobile_access_url
        print(f"  [OK] 사용자 '{test_username}' 소유 프로젝트 생성: 코드={sec_proj.project_code} (DB ID={sec_proj.id})")
        print(f"  [OK] 자동 발급된 모바일 전용 보안 토큰: {sec_proj.project_token[:25]}...")
        print(f"  [OK] 보안 토큰 탑재 QR 딥링크: {sec_proj.mobile_access_url[:75]}...")

        # 5-2) QR코드를 스캔하여 정당한 토큰(?token=...)으로 모바일 조회 ➔ 성공
        mob_access = sync_get_project(
            identifier=sec_proj.project_code,
            for_mobile=True,
            token=sec_proj.project_token,
            db=db,
            current_user=None
        )
        assert mob_access.status == "ANALYZING"
        print("  [OK] 모바일 정당 토큰 스캔 접속: 정상 승인 및 상태 'ANALYZING' 전이")

        # 5-3) 타인이 모바일 주소만 알고 토큰 없이 무단 접속 시도 ➔ 403 차단!
        try:
            sync_get_project(
                identifier=sec_proj.project_code,
                for_mobile=True,
                token=None,  # 토큰 없음!
                db=db,
                current_user=None
            )
            assert False, "토큰 없는 모바일 무단 조회가 통과되었습니다."
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  [OK] 토큰 없는 무단 조회 차단 통과 (403 Forbidden: {e.detail})")

        # 5-4) 위조된 가짜 토큰으로 접속 시도 ➔ 403 차단!
        fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.signature"
        try:
            sync_get_project(
                identifier=sec_proj.project_code,
                for_mobile=True,
                token=fake_token,
                db=db,
                current_user=None
            )
            assert False, "가짜 토큰이 통과되었습니다."
        except HTTPException as e:
            assert e.status_code == 403
            print("  [OK] 위조된 가짜 프로젝트 토큰 차단 통과 (403 Forbidden)")

        # 5-5) 다른 로그인 사용자가 타인의 프로젝트 결과를 무단 열람 시도 ➔ 403 차단!
        try:
            sync_get_results(
                identifier=sec_proj.project_code,
                db=db,
                current_user=crew_user  # 소유자가 아닌 crew 사용자
            )
            assert False, "타인 프로젝트 결과 조회가 허용되었습니다."
        except HTTPException as e:
            assert e.status_code == 403
            print("  [OK] 타인 계정의 프로젝트 결과 무단 조회 차단 통과 (403 Forbidden: IDOR 방어)")

        # 5-6) 정당한 토큰으로 현장 결과 업로드 ➔ 성공
        shot_in = SyncAnalysisResultCreate(
            frame_score=96,
            offset_x=0.0,
            offset_y=0.0,
            guide_direction="none",
            guide_message="보안 인증 페어링 촬영 정상 완료",
            recorded_video_url="https://storage.skycommand.kr/videos/secure_shot.mp4"
        )
        shot_res = sync_save_result(
            identifier=sec_proj.project_code,
            result_in=shot_in,
            token=sec_proj.project_token,
            db=db,
            current_user=None
        )
        assert shot_res.frame_score == 96
        print("  [OK] 보안 토큰 인증 후 현장 촬영 결과 정상 업로드 및 COMPLETED 전이 완료")

        # ---------------------------------------------------------
        # [6] 외부 API 키 은닉 및 상태 마스킹 (Frontend Zero-Exposure)
        # ---------------------------------------------------------
        print("\n[6] 외부 API 키 은닉 및 마스킹 상태 검증")
        key_status = check_api_keys_security()
        assert key_status["storage_mode"] == "SERVER_ENCRYPTED_ENV"
        assert key_status["frontend_exposed"] is False
        assert "..." in key_status["gemini_api"]["masked"] or key_status["gemini_api"]["masked"] == "UNCONFIGURED"
        print(f"  [OK] Gemini API 키 보관 상태: configured={key_status['gemini_api']['configured']}, masked={key_status['gemini_api']['masked']}")
        print(f"  [OK] VWorld API 키 보관 상태: configured={key_status['vworld_api']['configured']}, masked={key_status['vworld_api']['masked']}")
        print(f"  [OK] 기상청 API 키 보관 상태: configured={key_status['kma_api']['configured']}, masked={key_status['kma_api']['masked']}")
        print(f"  [OK] 프론트엔드 직접 노출 여부: {key_status['frontend_exposed']} (서버 환경변수 완전 은닉)")

        # ---------------------------------------------------------
        # [7] 악의적 입력값 유효성 검증
        # ---------------------------------------------------------
        print("\n[7] Pydantic v2 비정상/악의적 입력값 차단 검증")
        # 위도 초과(999.0) 검증
        try:
            SyncProjectCreate(
                title="비정상 위도 테스트",
                place_name="서울",
                latitude=999.0  # 비정상 위도
            )
            assert False, "비정상 위도가 통과되었습니다."
        except ValidationError:
            print("  [OK] 허용 범위 초과 위도(latitude=999.0) 차단 통과 (Pydantic ValidationError)")

        # 스크립트 인젝션 살균 검증
        safe_proj = SyncProjectCreate(
            title="<script>evil()</script>안전 비행 프로젝트",
            place_name="여의도",
            latitude=37.5284,
            longitude=126.9328
        )
        assert "<script>" not in safe_proj.title
        print(f"  [OK] 프로젝트 생성 입력 XSS 살균 검증: '{safe_proj.title}'")

        print("\n" + "=" * 66)
        print("[SUCCESS] 8단계 사용자 인증 및 보안 (Authentication & Security) 100% 검증 통과!")
        print("=" * 66)

    finally:
        db.close()


if __name__ == "__main__":
    run_auth_security_tests()
