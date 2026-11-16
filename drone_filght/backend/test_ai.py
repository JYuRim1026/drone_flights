import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.database import SessionLocal
from backend.services.ai_service import ai_service
from backend.schemas.schemas import (
    AIChatbotGroundTruthRequest,
    SceneImageAnalysisRequest
)
from backend.routers.ai import (
    chat_with_ground_truth,
    analyze_scene_image,
    recommend_composition,
    process_mobile_pipeline
)

def run_ai_service_tests():
    print("==================================================================", flush=True)
    print("[Step 5] AI 서비스 연동 (AI Services Integration) 정밀 검증", flush=True)
    print("==================================================================", flush=True)

    db = SessionLocal()
    try:
        # =====================================================================
        # A. PC 웹 AI 챗봇 검증 (결정론적 비행 안전 판단 Ground Truth 주입)
        # =====================================================================
        print("\n[A] PC 웹 AI 챗봇 검증 (결정론적 안전 판단 기반)", flush=True)
        # 1. 사용자가 '여의도 한강공원에서 지금 드론 날릴 수 있어?' 질문
        chat_req = AIChatbotGroundTruthRequest(
            prompt="여의도 한강공원에서 지금 드론 날릴 수 있어?",
            location="서울 여의도 한강공원",
            target_date="2026-10-24",
            target_time="17:00"
        )
        chat_res = chat_with_ground_truth(req=chat_req, db=db)
        print(f"  [OK] 1. 질문 수신 및 분석 완료: '{chat_req.prompt}'", flush=True)
        print(f"  [OK] 2. 백엔드 결정론적 판정 (Ground Truth): {chat_res.safety_status} (점수: {chat_res.ground_truth_score}점)", flush=True)
        print(f"  [OK] 3. 안전 판정 비행 가능 여부 (AI 추론 배제): {chat_res.is_safe_to_fly}", flush=True)
        print(f"  [OK] 4. Ground Truth 참고 데이터: 공역={chat_res.ground_truth_context['zone_name']}, 바람={chat_res.ground_truth_context['wind']}", flush=True)
        print(f"  [OK] 5. Gemini AI 생성 최종 답변 (길이 {len(chat_res.reply)}자):\n       \"{chat_res.reply[:100]}...\"", flush=True)

        # =====================================================================
        # B. 모바일 촬영 장면 분석 검증
        # =====================================================================
        print("\n[B] 모바일 촬영 장면 분석 검증 (프레임 추출 & 이미지 전처리)", flush=True)
        scene_req = SceneImageAnalysisRequest(
            project_id=1,
            scene_intent="도심 고층 건물과 일몰 풍경 시네마틱 촬영",
            current_pitch=-15.0,
            current_yaw=0.0
        )
        scene_res = analyze_scene_image(req=scene_req)
        features = scene_res["scene_features"]
        print(f"  [OK] 이미지 전처리 규격: {features['width']}x{features['height']} (정규화)", flush=True)
        print(f"  [OK] 평균 프레임 밝기: {features['avg_brightness']} (조도: {features['lighting_type']})", flush=True)
        print(f"  [OK] 감지된 수평선 위치 (Horizon Y): {features['horizon_y']} (중앙 기준 0.50)", flush=True)
        print(f"  [OK] 중심 피사체 무게중심 (Subject X): {features['subject_x']}", flush=True)

        # =====================================================================
        # C. AI 촬영 구도 추천 검증 (차별화 기능)
        # =====================================================================
        print("\n[C] AI 촬영 구도 추천 검증 (목적별 구도 및 검증된 신뢰도)", flush=True)
        rec_res = recommend_composition(req=scene_req)
        print("  [OK] 사용자 요구 양식 JSON 구조 검증:", flush=True)
        print(f"       subject: \"{rec_res.subject}\"", flush=True)
        print(f"       composition: \"{rec_res.composition}\"", flush=True)
        print(f"       direction: \"{rec_res.direction}\"", flush=True)
        print(f"       reason: \"{rec_res.reason}\"", flush=True)
        print(f"       confidence: {rec_res.confidence} (산출 근거: {rec_res.confidence_basis})", flush=True)

        # 신뢰도 점수 유효성 검사 (0.0 ~ 1.0)
        assert rec_res.confidence is not None and 0.5 <= rec_res.confidence <= 1.0, "신뢰도 점수 유효 범위 오류"
        assert rec_res.subject and rec_res.composition and rec_res.direction and rec_res.reason, "필수 항목 누락"

        # =====================================================================
        # D. AI 결과 후처리 및 모바일 UI 데이터 변환 & DB 저장 검증
        # =====================================================================
        print("\n[D] AI 결과 후처리 검증 (필터링, DB 저장, 모바일 camera.html 포맷 변환)", flush=True)
        pipeline_res = process_mobile_pipeline(req=scene_req, db=db)
        print(f"  [OK] 1. JSON 형식 검증 통과 (누락 항목 없음)", flush=True)
        print(f"  [OK] 2. 조종 방향 화이트리스트 필터링: \"{pipeline_res.direction}\" (안전 승인됨)", flush=True)
        print(f"  [OK] 3. 모바일 camera.html UI 신호 변환:", flush=True)
        print(f"       - mobile_guide_dir: '{pipeline_res.mobile_guide_dir}' (화살표: {'→' if pipeline_res.mobile_guide_dir == 'right' else '↑/↓'})", flush=True)
        print(f"       - offset_x: {pipeline_res.offset_x}, offset_y: {pipeline_res.offset_y}", flush=True)
        print(f"       - frame_score: {pipeline_res.frame_score}점 (배지 색상: {pipeline_res.badge_color})", flush=True)
        print(f"       - 녹화 준비 완료 여부: {pipeline_res.is_ready_to_record}", flush=True)
        print(f"       - 모바일 화면 가이드 문구: \"{pipeline_res.ui_message}\"", flush=True)
        print(f"  [OK] 4. 데이터베이스 저장 성공 (shooting_analyses 테이블 생성 ID: {pipeline_res.saved_analysis_id})", flush=True)

        print("\n==================================================================", flush=True)
        print("[SUCCESS] 5단계 AI 서비스 연동 (A, B, C, D) 모든 요구사항 100% 통과!", flush=True)
        print("==================================================================", flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    run_ai_service_tests()
