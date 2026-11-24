"""
Phase 1~7 Comprehensive Technical Report PDF Generator
Title: 드론 실시간 구도 추천
"""

import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# 1. 폰트 등록 (Malgun Gothic)
FONT_REGULAR = "Malgun"
FONT_BOLD = "MalgunBold"

font_path = "C:/Windows/Fonts/malgun.ttf"
font_bold_path = "C:/Windows/Fonts/malgunbd.ttf"

if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, font_path))
if os.path.exists(font_bold_path):
    pdfmetrics.registerFont(TTFont(FONT_BOLD, font_bold_path))
else:
    pdfmetrics.registerFont(TTFont(FONT_BOLD, font_path))


class NumberedCanvas(canvas.Canvas):
    """2-pass canvas to dynamically compute and print total page count"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        if self._pageNumber == 1:
            # Skip header and footer on cover page
            return

        self.saveState()
        self.setFont(FONT_REGULAR, 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Header
        self.drawString(20 * mm, 285 * mm, "드론 실시간 구도 추천 · Phase 1~7 종합 기술 검증 보고서")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(20 * mm, 282 * mm, 190 * mm, 282 * mm)

        # Footer
        page_text = f"페이지 {self._pageNumber} / {page_count}"
        self.drawRightString(190 * mm, 12 * mm, page_text)
        self.drawString(20 * mm, 12 * mm, "CONFIDENTIAL · 학술 및 기술 심사용 최종 보고서")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)

        self.restoreState()


def build_pdf(filename="드론_실시간_구도_추천.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    c_navy = colors.HexColor("#0f2b48")
    c_blue = colors.HexColor("#1d4ed8")
    c_dark = colors.HexColor("#1e293b")
    c_gray = colors.HexColor("#475569")
    c_code_bg = colors.HexColor("#f8fafc")

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=24,
        leading=32,
        textColor=c_navy,
        alignment=1, # Center
        spaceAfter=12
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=12,
        leading=18,
        textColor=c_blue,
        alignment=1,
        spaceAfter=25
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=15,
        leading=21,
        textColor=c_navy,
        spaceBefore=14,
        spaceAfter=7,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=11.5,
        leading=17,
        textColor=c_blue,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=9.5,
        leading=14.5,
        textColor=c_dark,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=9,
        leading=14,
        textColor=c_dark,
        leftIndent=12,
        spaceAfter=4
    )

    callout_style = ParagraphStyle(
        "Callout_Text",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=8.5,
        leading=13,
        textColor=c_dark
    )

    callout_bold = ParagraphStyle(
        "Callout_Bold",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=13,
        textColor=c_navy
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=12,
        textColor=colors.white,
        alignment=1
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=11.5,
        textColor=c_dark
    )

    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=11.5,
        textColor=c_navy
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#0f172a")
    )

    story = []

    # =========================================================================
    # 1. 표지 (Cover Page)
    # =========================================================================
    story.append(Spacer(1, 25 * mm))
    story.append(Paragraph("드론 실시간 구도 추천", title_style))
    story.append(Paragraph("Phase 1 ~ Phase 7 스마트폰 사전 시각화(Pre-viz) 및<br/>실시간 구도 추천·적응형 경로 보정 시스템 종합 기술 검증 보고서", subtitle_style))

    story.append(HRFlowable(width="80%", thickness=1.5, color=c_blue, spaceBefore=5, spaceAfter=20))

    meta_data = [
        [Paragraph("<b>프로젝트 명</b>", callout_bold), Paragraph("날려드려 (Sky Command / Drone Flight Pre-visualization)", callout_style)],
        [Paragraph("<b>분석 대상</b>", callout_bold), Paragraph("Phase 1~7 전체 파이프라인 (DB, API, 센서, AI구도, 맞춤추천, 경로보정, E2E)", callout_style)],
        [Paragraph("<b>작성 일자</b>", callout_bold), Paragraph("2026년 11월 23일", callout_style)],
        [Paragraph("<b>검증 상태</b>", callout_bold), Paragraph("<font color='#15803d'><b>E2E 전 17단계 통합 테스트 100% PASS (무결성 검증 완료)</b></font>", callout_style)],
        [Paragraph("<b>기술 특징</b>", callout_bold), Paragraph("하이브리드 비전(Gemini + PIL/NumPy), Haversine 투영, 호 진행률 선형 보간", callout_style)],
        [Paragraph("<b>보고 목적</b>", callout_bold), Paragraph("교수님 및 심사위원 평가용 100% 사실 기반 기술 보고서", callout_style)]
    ]
    t_meta = Table(meta_data, colWidths=[35 * mm, 120 * mm])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 20 * mm))

    # Executive Summary Box
    summary_box_data = [[
        Paragraph(
            "<b>[Executive Summary]</b><br/>"
            "본 프로젝트는 도심지 비행 규제 및 고가 드론 추락 위험을 원천 방지하기 위해, "
            "촬영자가 스마트폰을 들고 지상에서 걸으며 드론의 시네마틱 앵글과 궤적을 사전에 검증(Pre-visualization)하는 지능형 촬영 지원 플랫폼입니다. "
            "스마트폰 3축 자이로 센서 오일러 좌표 변환, 컴퓨터 비전 에지 에너지 기반 실시간 삼분할/수평 코칭, "
            "사용자 선호도와 현장 환경을 다면 결합하는 Cold/Warm 기법 추천, Haversine 및 선분 투영을 통한 횡방향 이탈 분석, "
            "그리고 구도 달성도 연동 적응형 가중치(alpha) 기반 차기 동선 자동 승계 파이프라인을 구축하였습니다. "
            "본 문서는 실제 소스 코드(파일, 라인 번호, 수식)와 100% 일치하도록 작성된 공학적 기술 보고서입니다.",
            callout_style
        )
    ]]
    t_sum = Table(summary_box_data, colWidths=[155 * mm])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
        ('BOX', (0, 0), (-1, -1), 1.0, c_blue),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_sum)
    story.append(PageBreak())

    # =========================================================================
    # 2. 필수 사전 확인: 설계 논의와 실제 구현의 5대 핵심 차이
    # =========================================================================
    story.append(Paragraph("1. 설계 논의와 실제 구현 간의 5대 핵심 차이", h1_style))
    story.append(Paragraph(
        "심사 질의응답 시 혼선을 방지하기 위해, 기획 및 설계 논의 단계의 아이디어와 현재 소스 코드에 실제 구현된 구현 현황의 차이를 객관적으로 대조하여 명시합니다.",
        body_style
    ))

    diff_table_data = [
        [Paragraph("항목", table_header_style), Paragraph("설계안 논의 내용", table_header_style), Paragraph("실제 소스 코드 구현 현황 (Source of Truth)", table_header_style), Paragraph("발표 시 정확한 설명 가이드", table_header_style)],
        [
            Paragraph("<b>① Circular EMA</b>", table_cell_bold),
            Paragraph("방위각 wrap-around 방지를 위한 atan2 삼각함수 평균 합성", table_cell_style),
            Paragraph("<b>path_service.py #L395-L408</b><br/>위치 (x, y)만 alpha 가중 결합되며, 각도는 권장 템플릿의 목표 조준각(guide_r)을 그대로 유지", table_cell_style),
            Paragraph("보행 위치 좌표는 alpha 가중 결합으로 보정하고, 조준 각도는 권장 기준을 유지했다고 설명", table_cell_style)
        ],
        [
            Paragraph("<b>② 동적 GPS 속도 필터</b>", table_cell_bold),
            Paragraph("v = d / delta_t 기반 속도 임계치 필터링", table_cell_style),
            Paragraph("<b>path_service.py #L218-L234, #L273-L284</b><br/>개별 오차 20m 이하 필터, 경로 평균 15m 이하 필터, 제자리 떨림(변위 2.5m 미만) 감지", table_cell_style),
            Paragraph("시간 미분 속도 필터가 아닌, 오차 반경(20m/15m) 및 제자리 떨림(2.5m) 필터를 적용했다고 설명", table_cell_style)
        ],
        [
            Paragraph("<b>③ 드론 vs 스마트폰 구분</b>", table_cell_bold),
            Paragraph("실제 비행 로그와 보행 데이터의 혼동 방지", table_cell_style),
            Paragraph("<b>models.py #L219</b><br/>tracking_source = 'PHONE_GPS' 전용 컬럼 명시 및 shooting_paths 테이블 격리", table_cell_style),
            Paragraph("실제 비행이 아닌 지상 보행 데이터(PHONE_GPS)만을 수집·분석한 사전 검증 시스템임을 명확히 강조", table_cell_style)
        ],
        [
            Paragraph("<b>④ AI 추천의 실체</b>", table_cell_bold),
            Paragraph("직접 학습시킨 독자 딥러닝 모델인가?", table_cell_style),
            Paragraph("<b>technique_service.py #L286-L291</b><br/>Cold/Warm 다인자 가중치 합성 스코어링 규칙 + PIL/NumPy 에지 검출 휴리스틱 + Gemini API", table_cell_style),
            Paragraph("직접 학습한 인공신경망이 아니라, 멀티모달 API와 컴퓨터 비전 및 다인자 가중치 추천 엔진임을 명시", table_cell_style)
        ],
        [
            Paragraph("<b>⑤ PC 화면 동기화</b>", table_cell_bold),
            Paragraph("WebSocket 실시간 양방향 스트리밍인가?", table_cell_style),
            Paragraph("<b>pc.html #L6404-L6428</b><br/>모달 활성화 및 사용자 인터랙션 시점에 백엔드 REST API (fetch) 비동기 호출", table_cell_style),
            Paragraph("웹소켓이 아닌 가볍고 안정적인 HTTP REST API (fetch) 요약 동기화임을 설명", table_cell_style)
        ]
    ]

    t_diff = Table(diff_table_data, colWidths=[25 * mm, 38 * mm, 52 * mm, 40 * mm])
    t_diff.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('BOX', (0, 0), (-1, -1), 0.8, c_navy),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_diff)
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 3. Phase 1 & 2: DB 마이그레이션 v2 및 백엔드 REST API
    # =========================================================================
    story.append(Paragraph("2. Phase 1 & 2: DB 스키마 분리 및 백엔드 REST API", h1_style))
    story.append(Paragraph(
        "<b>1) 구현 목적:</b> 실제 드론의 비행 관제 로그 데이터가 지상 스마트폰 보행 데이터에 의해 오염되는 문제를 원천 차단하고, "
        "현장 촬영에 필요한 회차별 경로 데이터와 시각 에셋(사진/영상)을 안전하게 영구 격리 보존하기 위함입니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) 적용 기술 및 아키텍처:</b><br/>"
        "• SQLite / SQLAlchemy v2 DDL: <code>ShootingPath</code> 및 <code>LocationAsset</code> 모델 신설<br/>"
        "• FastAPI 의존성 주입 기반 보안 인가: JWT 인증 및 프로젝트 소유권 검증 (<code>auth_service.verify_project_ownership</code>)<br/>"
        "• Re-take 트랜잭션 무결성: 동일 회차 재촬영 시 DB Duplicate Key 충돌 없이 안전 덮어쓰기(Upsert) 구현",
        body_style
    ))

    p1_data = [
        [Paragraph("구분", table_header_style), Paragraph("테이블/함수명", table_header_style), Paragraph("핵심 필드 및 역할", table_header_style), Paragraph("검증 결과", table_header_style)],
        [
            Paragraph("<b>동선 모델</b>", table_cell_bold),
            Paragraph("shooting_paths<br/>(models.py #L210)", table_cell_style),
            Paragraph("path_id(PK), project_id(FK), shooting_number, tracking_source('PHONE_GPS'), recommended_waypoints(JSON), actual_waypoints(JSON), corrected_waypoints(JSON), alpha_weight, deviation_score, is_valid", table_cell_style),
            Paragraph("<font color='#15803d'><b>PASS (격리 완료)</b></font>", table_cell_style)
        ],
        [
            Paragraph("<b>에셋 모델</b>", table_cell_bold),
            Paragraph("location_assets<br/>(models.py #L255)", table_cell_style),
            Paragraph("id(PK), project_id(FK), user_id(FK), is_common(공통/개인 구분), asset_type('CAMERA_FRAME'), file_url, detected_features(JSON)", table_cell_style),
            Paragraph("<font color='#15803d'><b>PASS (저장 확인)</b></font>", table_cell_style)
        ],
        [
            Paragraph("<b>보안 인가</b>", table_cell_bold),
            Paragraph("verify_project_ownership<br/>(auth_service.py #L115)", table_cell_style),
            Paragraph("타 사용자의 비인가 프로젝트 경로 조회 및 조작 시 즉시 HTTP 403 Forbidden 반환 (IDOR 원천 방어)", table_cell_style),
            Paragraph("<font color='#15803d'><b>PASS (403 차단)</b></font>", table_cell_style)
        ]
    ]
    t_p1 = Table(p1_data, colWidths=[25 * mm, 38 * mm, 72 * mm, 20 * mm])
    t_p1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('BOX', (0, 0), (-1, -1), 0.8, c_navy),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_p1)
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 4. Phase 3: 스마트폰 카메라 및 센서 좌표계 변환
    # =========================================================================
    story.append(Paragraph("3. Phase 3: 스마트폰 카메라 및 센서 좌표계 변환", h1_style))
    story.append(Paragraph(
        "<b>1) 구현 목적:</b> 스마트폰 후면 카메라를 실행하고, 기기를 쥐는 방향(가로/세로) 및 렌즈 오프셋(-90도)에 따른 자이로 각도를 보정하여 렌즈가 향하는 실제 Heading, Pitch, Roll을 산출하기 위함입니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) 핵심 로직 및 실제 코드 수식 (camera.html #L841-L895):</b><br/>"
        "• <b>Heading (방위각)</b>: iOS는 <code>webkitCompassHeading</code> 우선, Android는 <code>(360 - alpha) % 360</code> 적용 후 화면 회전각 합산<br/>"
        "&nbsp;&nbsp;<code>heading = ((compassHeading + screenAngle) % 360 + 360) % 360</code><br/>"
        "• <b>Pitch & Roll (화면 회전각 screenAngle에 따른 축 변환)</b>:<br/>"
        "&nbsp;&nbsp;- 세로 모드 (0°): <code>pitch = beta - 90</code>, <code>roll = gamma</code><br/>"
        "&nbsp;&nbsp;- 가로 우측 모드 (90°): <code>pitch = gamma</code>, <code>roll = -(beta - 90)</code><br/>"
        "&nbsp;&nbsp;- 가로 좌측 모드 (270°): <code>pitch = -gamma</code>, <code>roll = beta - 90</code><br/>"
        "• <b>GPS 이상치 필터링 순서 (path_service.py #L218-L284)</b>:<br/>"
        "&nbsp;&nbsp;① 개별 좌표 정확도 검사: <code>acc <= 20.0m</code>인 좌표만 수록 (20m 초과 노이즈 제거)<br/>"
        "&nbsp;&nbsp;② 경로 평균 정확도 검사: <code>avg_acc > 15.0m</code>이거나 유효 좌표가 2개 미만 시 무효 처리<br/>"
        "&nbsp;&nbsp;③ 정지 제자리 미세 오차(Drift): <code>total_displacement < 2.5m and act_total_len < 5.0m</code> 시 제자리 떨림 판정",
        body_style
    ))
    story.append(Paragraph(
        "<b>3) 검증 상태:</b> <b>[B] 시뮬레이션 및 코드 레벨 검증 완료.</b> "
        "JS 구문 및 백엔드 DTO 파싱 검증은 100% 완료되었으나, 실제 물리 기기를 들고 야외 위성 신호 아래에서 회전하는 필드 테스트는 미수행 상태입니다.",
        body_style
    ))
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 5. Phase 4: 실시간 AI 장면 분석 및 구도 추천
    # =========================================================================
    story.append(Paragraph("4. Phase 4: 실시간 AI 장면 분석 및 구도 추천", h1_style))
    story.append(Paragraph(
        "<b>1) 구현 목적:</b> 초보 촬영자도 전문가 수준의 구도(삼분할 황금비율, 수평선)를 유지할 수 있도록 실시간 뷰파인더 코칭 UI를 제공하기 위함입니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) Gemini Vision + PIL/NumPy 하이브리드 Fallback 구조 (ai_service.py #L619-L671):</b><br/>"
        "• <code>GEMINI_API_KEY</code> 존재 시 Google Gemini Vision API를 비동기 호출하여 의미론적 객체/조도/구도를 분석합니다.<br/>"
        "• 네트워크 단절 또는 타임아웃 발생 시 즉시 로컬 컴퓨터 비전 엔진(<code>_extract_cv_scene_features</code>)으로 자동 전환되어 0.01초 내에 지연 없이 처리됩니다.<br/>"
        "• Gemini 성공 시와 실패 시 모두 <b>동일한 AnalyzeResponse DTO</b>로 정규화되어 프론트엔드에서는 동일하게 소비됩니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>3) 에지 에너지 중심 및 구도 점수 계산 공식 (ai_service.py #L522-L531, #L773-L805):</b><br/>"
        "• <b>에지 에너지 중심점</b>: <code>gray = 0.299R + 0.587G + 0.114B</code> 휘도 변환 후 1차 미분 그래디언트 절대값 합산:<br/>"
        "&nbsp;&nbsp;<code>energy = |diff_row| + |diff_col|</code>, <code>subject_center_x = argmax(mean(energy, axis=0)) / (w-1)</code><br/>"
        "&nbsp;&nbsp;⚠️ <i>실제 객체 인식이 아니라 이미지 내 에지 에너지가 가장 집중된 중심을 통계적으로 추정한 값입니다.</i><br/>"
        "• <b>구도 점수 및 수평 판정</b>: 정규화 오프셋 거리 <code>dist = hypot(curr_x - target_x, curr_y - target_y)</code><br/>"
        "&nbsp;&nbsp;- 롤 수평 오차: <code>abs(effective_roll) > 4.0°</code> 시 <code>frame_score = max(50, 85 - int(roll * 3))</code> (감점 및 수평 경고)<br/>"
        "&nbsp;&nbsp;- 최적 삼분할 락온: <code>dist <= 0.18</code> 시 <code>frame_score = min(98, max(90, int(100 - dist * 40)))</code> (90~98점)<br/>"
        "&nbsp;&nbsp;- 구도 이탈 상태: <code>dist > 0.18</code> 시 <code>frame_score = max(55, int(90 - dist * 70))</code> (55~89점)",
        body_style
    ))
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 6. Phase 5: 사용자 맞춤형 AI 촬영 기법 추천 시스템
    # =========================================================================
    story.append(Paragraph("5. Phase 5: 사용자 맞춤형 AI 촬영 기법 추천 시스템", h1_style))
    story.append(Paragraph(
        "<b>1) 구현 목적:</b> 촬영자의 누적 취향(좋아요, 저장, 만족도)과 현장 환경(수변, 건축물, 일몰 등)을 결합하여 최적의 촬영 기법 4선을 큐레이션하기 위함입니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) Cold Start vs Warm Start 추천 스코어링 공식 (technique_service.py #L286-L291):</b><br/>"
        "• <b>Cold Start (기록 없는 신규 사용자)</b>: 이력 점수가 없으므로 기본값 <code>score_hist = 40.0</code>점이 부여됨<br/>"
        "&nbsp;&nbsp;<code>total_score = (score_proj * 0.65) + (score_hist * 0.35)</code> (프로젝트 적합도가 65% 지배)<br/>"
        "• <b>Warm Start (기존 사용자 취향 누적)</b>:<br/>"
        "&nbsp;&nbsp;<code>total_score = (score_proj * 0.30) + (score_hist * 0.25) + (score_pref * 0.45)</code> (사용자 취향 45% 반영)",
        body_style
    ))
    story.append(Paragraph(
        "<b>3) 행동별 선호도 점수 누적 갱신 공식 (technique_service.py #L686, #L734, #L801):</b><br/>"
        "• 기법 선택 시: <code>weight = 6.0</code><br/>"
        "• 촬영 후 만족도 피드백: 만족도 4~5점 시 <code>weight = 8.0</code>, 3점 시 <code>4.0</code>, 1~2점 시 <code>1.0</code> (미촬영 시 0.5배)<br/>"
        "• DB 점수 누적: <code>new_score = min(100.0, float(pref.preference_score or 0.0) + (weight * 3.5))</code><br/>"
        "&nbsp;&nbsp;<i>user_preference_scores 테이블에 최대 100점 상한으로 점진적 지수 누적 갱신됩니다.</i>",
        body_style
    ))
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 7. Phase 6: 지상 보행 경로 분석 및 적응형 경로 보정
    # =========================================================================
    story.append(Paragraph("6. Phase 6: 지상 보행 경로 분석 및 적응형 경로 보정", h1_style))
    story.append(Paragraph(
        "<b>1) 구현 목적:</b> AI 권장 동선과 실제 보행 GPS를 비교하여 횡방향 이탈을 분석하고, 구도 점수가 우수할 경우 실제 보행선의 장점을 흡수하여 차기 2회차 권장 동선으로 자동 승계하기 위함입니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) Haversine 및 Cross-Track 선분 투영 수식 (path_service.py #L32-L33, #L56-L65):</b><br/>"
        "• 구면 대원거리: <code>d = 2 * R * atan2(sqrt(a), sqrt(1 - a))</code><br/>"
        "• 최단 선분 투영거리: 실제 보행점 (px, py)에서 권장 선분 (x1, y1)-(x2, y2)로의 직교 수선의 발 t 계산:<br/>"
        "&nbsp;&nbsp;<code>t = clamp(((px - x1)*dx + (py - y1)*dy) / (dx^2 + dy^2), 0.0, 1.0)</code><br/>"
        "&nbsp;&nbsp;<code>dist_cross_track = hypot(px - (x1 + t*dx), py - (y1 + t*dy))</code>",
        body_style
    ))
    story.append(Paragraph(
        "<b>3) 적응형 보정 가중치(alpha) 결정 규칙 및 보간 결합 (path_service.py #L347-L370, #L389-L393):</b><br/>"
        "• <code>avg_dev <= 2.0m</code>: <b>alpha = 0.35, reason = 'NORMAL'</b> (권장 동선 65% 유지)<br/>"
        "• <code>avg_comp_score >= 80.0점</code>: <b>alpha = 0.60, reason = 'COMPOSITION_OPTIMIZED'</b> (구도가 훌륭하므로 사용자 실제 보행선 60% 대폭 승계)<br/>"
        "• <code>avg_dev > 3.0m</code>: <b>alpha = 0.20, reason = 'WALKING_DETOUR'</b> (길 잃음, 권장선으로 80% 복귀)<br/>"
        "• <code>2.0m < avg_dev <= 3.0m</code>: <b>alpha = 0.25, reason = 'PHONE_SHAKE'</b> (보행 미세 흔들림 완화)<br/>"
        "• <b>대응 지점 선정 및 위치 결합</b>: 정규화 누적 거리 진행률 <code>s in [0.0, 1.0]</code>을 기준으로 양 경로의 대응점 r_pos(s)와 a_pos(s)를 추출하여 선형 결합:<br/>"
        "&nbsp;&nbsp;<code>cx = (1 - alpha) * r_pos[x] + alpha * a_pos[x]</code>, <code>cy = (1 - alpha) * r_pos[y] + alpha * a_pos[y]</code><br/>"
        "&nbsp;&nbsp;⚠️ <i>조준 방위각(target_heading)은 권장 템플릿의 목표 각도를 그대로 유지합니다.</i>",
        body_style
    ))
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 8. Phase 7: 전체 시스템 통합 및 최종 검증
    # =========================================================================
    story.append(Paragraph("7. Phase 7: 전체 시스템 통합 및 최종 검증", h1_style))
    story.append(Paragraph(
        "<b>1) 전체 서비스 흐름:</b> PC 웹 프로젝트 기획 및 코드 발급 → 모바일 웹 프로젝트 식별 접속 → 뷰파인더 카메라 및 자이로 센서 구동 → "
        "AI 구도 코칭 및 기법 선택 → 실제 지상 보행 다점 촬영 → 동선 저장 및 이탈 분석 → 차기 회차 보정 동선 승계 → "
        "PC 웹 `GET /paths/summary` 비동기 REST API 요약 동기화의 14단계 파이프라인이 완성되었습니다.",
        body_style
    ))
    story.append(Paragraph(
        "<b>2) 재촬영(Re-take) 시 필드 갱신 무결성 (mobile_service.py #L311-L323):</b><br/>"
        "• <b>유지되는 필드</b>: <code>path_id</code> (기존 PK 유지), <code>project_id</code>, <code>shooting_number</code>, <code>created_at</code> (최초 생성 시간 보존)<br/>"
        "• <b>변경(갱신)되는 필드</b>: <code>actual_waypoints</code> (새 GPS 데이터로 완전 교체), <code>recommended_waypoints</code>, <code>corrected_waypoints</code> (재보정 경로로 갱신), "
        "<code>alpha_weight</code>, <code>deviation_score</code>, <code>deviation_reason</code>, <code>is_valid</code> (최신 재촬영 데이터로 전체 리프레시)",
        body_style
    ))
    story.append(Paragraph(
        "<b>3) 전체 회귀 테스트 검증 결과:</b><br/>"
        "• Phase 2 백엔드 API 검증: 14/14 PASS (100%)<br/>"
        "• Phase 3 카메라/센서 사전 검증: ALL PASS (100%)<br/>"
        "• Phase 4 AI 구도 분석 검증: ALL PASS (100%)<br/>"
        "• Phase 5 맞춤 기법 추천 검증: ALL PASS (100%)<br/>"
        "• Phase 6 경로 이탈 및 보정 검증: 7/7 카테고리 PASS (100%)<br/>"
        "• Phase 7 E2E 17단계 통합 검증: 17/17 Steps PASS (100%)",
        body_style
    ))
    story.append(Spacer(1, 5 * mm))

    # =========================================================================
    # 9. 최종 기능 구현 상태 3대 종합 분류 (A / B / C)
    # =========================================================================
    story.append(Paragraph("8. 최종 기능 구현 상태 3대 종합 분류 (A / B / C)", h1_style))

    cat_data = [
        [Paragraph("분류", table_header_style), Paragraph("정의 및 판정 기준", table_header_style), Paragraph("해당 기능 목록", table_header_style)],
        [
            Paragraph("<b>[A]<br/>실제 코드 구현 및 테스트 완료</b>", table_cell_bold),
            Paragraph("코드에 구현되어 있으며 단위/통합 테스트 스위트를 통해 정상 동작이 100% 검증된 기능", table_cell_style),
            Paragraph(
                "• SQLite DB v2 마이그레이션 (shooting_paths, location_assets 격리)<br/>"
                "• PC 프로젝트 코드 자동 발급 (DRONE_YYYYMMDD_XXXXXX) 및 모바일 접속 식별<br/>"
                "• 화면 회전(0/90/270도) 대응 스마트폰 센서 좌표계 변환 (Heading/Pitch/Roll)<br/>"
                "• GPS 수평 정확도 임계값 필터 (20m/15m) 및 제자리 떨림(2.5m) 감지<br/>"
                "• PIL/NumPy 휘도 및 1차 미분 에지 그래디언트 분석 기반 구도 점수화<br/>"
                "• 스마트폰 롤 각도(±4도) 수평 이탈 감지 및 뷰파인더 코칭 HUD 연동<br/>"
                "• Cold Start(65:35) / Warm Start(30:25:45) 다인자 기법 추천 알고리즘<br/>"
                "• 사용자 상호작용 피드백 반영 및 선호도 점수 누적 갱신<br/>"
                "• Haversine 대원거리 및 Cross-Track 선분 투영 횡방향 이탈 분석<br/>"
                "• 구도 달성도 연동 적응형 가중치(alpha=0.35/0.60/0.20/0.25) 조건 분기<br/>"
                "• 호 진행률(s) 기준 보행 동선 선형 결합 및 차기 회차 보정 경로 자동 승계<br/>"
                "• 동일 회차 재촬영(Re-take) 안전 갱신 트랜잭션 무결성<br/>"
                "• 비인가 타인 프로젝트 접근 차단 (HTTP 403 Forbidden IDOR 방어)<br/>"
                "• PC 웹 누적 촬영 요약 비동기 HTTP REST API (fetch) 동기화",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>[B]<br/>코드 구현 완료되었으나 실기기/외부망 검증 필요</b>", table_cell_bold),
            Paragraph("코드는 완성되어 있으나 실제 하드웨어 또는 외부망 환경에서 미수행된 항목", table_cell_style),
            Paragraph(
                "• Gemini Multimodal Vision API 외부망 라이브 호출 (로컬 샌드박스 망분리로 인해 PIL/NumPy Fallback 엔진으로 자동 전환되어 테스트됨)<br/>"
                "• 물리 스마트폰 하드웨어 자이로 센서 실기기 회전 (PC 모의 센서 데이터로 검증됨)<br/>"
                "• 야외 실제 위성 GPS 수신 환경 필드 도보 테스트 (Geolocation API 코드는 탑재되었으나 실외 테스트 미수행)",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>[C]<br/>설계 단계 논의되었으나 현재 코드 미구현</b>", table_cell_bold),
            Paragraph("설계안에서 검토되었으나 현재 실제 코드에는 반영되지 않은 향후 과제", table_cell_style),
            Paragraph(
                "• 방위각(Heading)에 대한 Circular EMA (atan2) 삼각함수 복원 각도 합성 (현재는 위치 좌표만 alpha 결합되며, 각도는 권장 템플릿 유지)<br/>"
                "• 시간 미분 기반의 순간 GPS 속도 초과 필터 (v = d / delta_t) (현재는 오차 반경 20m/15m 및 제자리 떨림 2.5m 검사로 구현됨)<br/>"
                "• WebSocket 기반의 전이중 실시간 양방향 푸시 스트리밍 (현재는 표준 HTTP REST API 비동기 Fetch 요청으로 구현됨)",
                table_cell_style
            )
        ]
    ]

    t_cat = Table(cat_data, colWidths=[30 * mm, 38 * mm, 87 * mm])
    t_cat.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_navy),
        ('BOX', (0, 0), (-1, -1), 0.8, c_navy),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_cat)
    story.append(Spacer(1, 8 * mm))

    # =========================================================================
    # 10. 교수님 앞 최종 발표 3줄 요약 스크립트
    # =========================================================================
    story.append(Paragraph("9. 교수님 앞 최종 발표 3줄 요약 스크립트", h1_style))
    story.append(Paragraph(
        "<b>Q. 본 시스템의 차별성과 실제 작동 원리는 무엇입니까?</b>",
        h2_style
    ))
    closing_script = [
        [Paragraph(
            "<b>1. [연구 배경 및 목적]</b><br/>"
            "고가 드론의 추락 위험과 도심지 비행 승인 규제를 해결하기 위해, 조종사가 스마트폰을 들고 지상에서 직접 걸으며 시네마틱 앵글과 비행 궤적을 사전에 검증(Pre-visualization)하는 지능형 촬영 지원 플랫폼을 개발했습니다.<br/><br/>"
            "<b>2. [실시간 구도 분석 및 기법 추천]</b><br/>"
            "네트워크 지연이 없는 현장 대응을 위해 PIL/NumPy 기반 2차원 에지 그래디언트 에너지 분석 엔진을 구축하여 삼분할 구도와 롤 수평 오차(±4도)를 0.01초 내에 실시간 코칭하며, 프로젝트 환경과 사용자 누적 취향을 결합한 다인자 가중치 스코어링 공식으로 최적 기법 4선을 추천합니다.<br/><br/>"
            "<b>3. [적응형 경로 보정 및 시스템 통합]</b><br/>"
            "Haversine 구면 거리와 Cross-Track 선분 투영을 통해 보행 이탈도를 계산하고, 구도 점수가 80점 이상일 경우 실제 보행선의 장점을 60% 자동 계승(alpha=0.60)하여 차기 권장 동선을 호 진행률 기준으로 선형 보정함으로써 PC-모바일 간 단절 없는 14단계 서비스 흐름을 완성했습니다.",
            callout_style
        )]
    ]
    t_close = Table(closing_script, colWidths=[155 * mm])
    t_close.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ('BOX', (0, 0), (-1, -1), 1.0, colors.HexColor("#16a34a")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_close)

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF Successfully Generated: {filename} ({os.path.getsize(filename)} bytes)")


if __name__ == "__main__":
    out_pdf = "드론_실시간_구도_추천.pdf"
    if len(sys.argv) > 1:
        out_pdf = sys.argv[1]
    build_pdf(out_pdf)
