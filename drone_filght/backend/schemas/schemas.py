import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==========================================
# E. 사용자 & 설정 스키마
# ==========================================
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    drone_model: Optional[str] = "DJI Mini 4 Pro"
    drone_weight_g: Optional[int] = 249

class UserResponse(UserBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

class UserSettingBase(BaseModel):
    safety_margin_m: Optional[int] = 30
    notification_enabled: Optional[bool] = True
    weather_auto_refresh: Optional[bool] = True
    preferred_camera_mode: Optional[str] = "cinematic"

class UserSettingUpdate(UserSettingBase):
    pass

class UserSettingResponse(UserSettingBase):
    id: int
    user_id: int
    updated_at: datetime
    class Config:
        from_attributes = True


# ==========================================
# A. 비행 신청 스키마 (PC 전용)
# ==========================================
class FlightRequestCreate(BaseModel):
    location: str = Field(..., description="비행 희망 장소 또는 도로명 주소", example="서울 여의도 한강공원")
    start_date: str = Field(..., description="비행 시작 일자 (YYYY-MM-DD)", example="2026-10-24")
    end_date: str = Field(..., description="비행 종료 일자 (YYYY-MM-DD)", example="2026-10-24")
    flight_time: str = Field(..., description="비행 시간대", example="14:00 ~ 16:00")
    drone_weight: str = Field(default="249g (초경량)", description="드론 기체 중량")
    has_camera: bool = Field(default=True, description="카메라 탑재 여부")
    purpose: str = Field(default="경관 사진 및 영상 촬영", description="비행 목적")
    altitude: str = Field(default="120m", description="예정 비행 고도")
    notes: Optional[str] = None

    @field_validator("location", "purpose", "notes", mode="before")
    def sanitize_strings(cls, v):
        if isinstance(v, str):
            v = re.sub(r"<script.*?>.*?</script>", "", v, flags=re.IGNORECASE | re.DOTALL)
            v = re.sub(r"javascript:", "", v, flags=re.IGNORECASE)
            v = re.sub(r"on\w+\s*=", "", v, flags=re.IGNORECASE)
            return v.strip()
        return v

class FlightRequestResponse(FlightRequestCreate):
    id: int
    approval_status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime
    class Config:
        from_attributes = True


# ==========================================
# B. 공역 정보 스키마 (PC 전용)
# ==========================================
class AirspaceZoneResponse(BaseModel):
    zone_name: str
    zone_type: str
    latitude: float
    longitude: float
    radius_meter: int
    approval_required: bool
    safety_score: int = 85
    status_label: str = "비행승인 필요"
    badge_color: str = "#ea580c"
    official_contacts: Dict[str, str] = {}
    description: Optional[str] = None


# ==========================================
# C. 촬영 프로젝트 스키마 (PC ↔ 모바일 공통)
# ==========================================
class ShootingProjectCreate(BaseModel):
    title: str = Field(..., example="한강 도시 풍경 촬영")
    place_name: str = Field(..., example="서울 한강공원")
    target_date: str = Field(..., example="2026-10-24")
    target_time: str = Field(..., example="오후 14:00 ~ 16:00")
    scene_intent: Optional[str] = Field(None, example="한강을 따라 이동하며 도시의 넓은 풍경과 석양 분위기를 시네마틱하게 담고 싶어요.")
    latitude: Optional[float] = 37.5284
    longitude: Optional[float] = 126.9328

    @field_validator("title", "place_name", "scene_intent", mode="before")
    def sanitize_sync_strings(cls, v):
        if isinstance(v, str):
            v = re.sub(r"<script.*?>.*?</script>", "", v, flags=re.IGNORECASE | re.DOTALL)
            v = re.sub(r"javascript:", "", v, flags=re.IGNORECASE)
            v = re.sub(r"on\w+\s*=", "", v, flags=re.IGNORECASE)
            return v.strip()
        return v

    @field_validator("latitude")
    def validate_lat(cls, v):
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("위도는 -90.0에서 90.0 범위 내여야 합니다.")
        return v

    @field_validator("longitude")
    def validate_lon(cls, v):
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("경도는 -180.0에서 180.0 범위 내여야 합니다.")
        return v
    recommended_mode: Optional[str] = "패럴랙스 리빌 & 선셋 아크"
    recommended_shutter: Optional[str] = "1/50s"
    recommended_nd_filter: Optional[str] = "ND16"
    desired_techniques: Optional[List[str]] = Field(default_factory=list, description="사용자 희망 촬영 기법 목록")
    recommended_techniques: Optional[List[str]] = Field(default_factory=list, description="AI 추천 촬영 기법 목록")

class ShootingProjectResponse(ShootingProjectCreate):
    id: int
    user_id: Optional[int] = None
    flight_request_id: Optional[int] = None
    status: str
    created_at: datetime
    project_code: Optional[str] = None
    class Config:
        from_attributes = True


class MobileProjectDetailResponse(BaseModel):
    id: int
    project_id: int
    title: str
    place_name: str
    target_date: str
    target_time: str
    scene_intent: Optional[str] = None
    recommended_mode: Optional[str] = None
    recommended_shutter: Optional[str] = None
    recommended_nd_filter: Optional[str] = None
    desired_techniques: Optional[List[str]] = None
    recommended_techniques: Optional[List[str]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    created_at: Optional[datetime] = None
    project_code: Optional[str] = None
    has_analysis: bool = False
    latest_analysis_id: Optional[int] = None
    analysis_score: Optional[float] = None

    class Config:
        from_attributes = True


# ==========================================
# D. 촬영 분석 및 실시간 가이드 스키마 (모바일 전용)
# ==========================================
class AnalyzeRequest(BaseModel):
    project_id: int = 1
    image_base64: Optional[str] = Field(None, description="모바일 카메라 캡처 이미지 (Base64 인코딩)")
    current_pitch: Optional[float] = -15.0
    current_roll: Optional[float] = 0.0
    current_yaw: Optional[float] = 0.0
    current_heading: Optional[float] = None
    purpose: Optional[str] = Field("orbit", description="촬영 목적 (orbit, dronie, thirds, landscape)")
    scene_intent: Optional[str] = Field(None, description="희망 촬영 콘셉트/의도")
    shooting_number: Optional[int] = Field(None, description="현재 촬영 회차")
    sensor_width: Optional[int] = 1280
    sensor_height: Optional[int] = 720
    detected_horizon_y: Optional[float] = 0.5
    save_result: Optional[bool] = Field(True, description="분석 결과 DB(shooting_analyses) 자동 저장 여부")

class AnalyzeResponse(BaseModel):
    project_id: int
    frame_score: int
    is_ready: bool
    guide_direction: str  # up, down, left, right, none, level_left, level_right, step_back
    offset_x: float
    offset_y: float
    guide_message: str

    # Extended Phase 4 Fields
    subject: Optional[str] = None
    subject_details: Optional[Dict[str, Any]] = None
    environment_details: Optional[Dict[str, Any]] = None
    recommended_composition: Optional[str] = None
    recommendation_reason: Optional[str] = None
    target_position: Optional[Dict[str, float]] = None
    is_aligned: Optional[bool] = None
    analysis_id: Optional[int] = None
    shooting_number: Optional[int] = None
    user_id: Optional[int] = None
    source: Optional[str] = None

class RecommendationResponse(BaseModel):
    project_id: int
    recommended_mode: str
    concept_summary: str
    camera_recipe: Dict[str, str]
    stick_combo_steps: List[Dict[str, str]]
    shooting_waypoints: List[Dict[str, Any]]

class AnalysisResultCreate(BaseModel):
    project_id: int
    frame_score: int
    guide_direction: str
    offset_x: float
    offset_y: float
    guide_message: Optional[str] = None
    recorded_video_url: Optional[str] = None
    shooting_number: Optional[int] = None
    subject: Optional[str] = None
    recommended_composition: Optional[str] = None
    target_summary: Optional[str] = None
    environment_summary: Optional[str] = None

class AnalysisResultResponse(AnalysisResultCreate):
    id: int
    analysis_id: Optional[int] = None
    created_at: datetime
    user_id: Optional[int] = None
    target_coordinates: Optional[Dict[str, Any]] = None
    class Config:
        from_attributes = True


# ==========================================
# 챗봇 & 날씨 스키마
# ==========================================
class ChatbotRequest(BaseModel):
    prompt: str = Field(..., example="비행 승인 신청서 작성 어떻게 해?")
    location: Optional[str] = "서울 여의도 한강공원"

class ChatbotResponse(BaseModel):
    reply: str
    matched_data: Dict[str, Any] = {}

class WeatherResponse(BaseModel):
    location_name: str
    latitude: float
    longitude: float
    weather_desc: str
    temp_c: float
    wind_speed: float
    wind_gust: float
    visibility_km: float
    rain_probability: int
    is_safe_to_fly: bool
    evaluation: str
    humidity_percent: Optional[int] = None
    wind_direction_text: Optional[str] = None
    precipitation_mm_h: Optional[float] = 0.0
    source: Optional[str] = None
    observed_at: Optional[str] = None
    kma_grid: Optional[Dict[str, Any]] = None
    risk_factors: List[str] = []
    hourly_forecast: List[Dict[str, Any]] = []


# ==========================================
# 5단계 AI 서비스 연동 전용 스키마 (AI Service Schemas)
# ==========================================
class AIChatbotGroundTruthRequest(BaseModel):
    prompt: str = Field(..., example="이 장소에서 드론 날릴 수 있어?")
    location: Optional[str] = Field("서울 여의도 한강공원", description="비행 예정 장소")
    target_date: Optional[str] = Field(None, description="비행 희망 일자 (YYYY-MM-DD)")
    target_time: Optional[str] = Field(None, description="비행 희망 시간 (예: 17:00)")

class AIChatbotGroundTruthResponse(BaseModel):
    reply: str
    is_safe_to_fly: bool
    safety_status: str
    ground_truth_score: Optional[int] = None
    reasons: List[str]
    ground_truth_context: Dict[str, Any]

class SceneImageAnalysisRequest(BaseModel):
    project_id: Optional[int] = 1
    image_base64: Optional[str] = Field(None, description="모바일 카메라 캡처 이미지 (Base64 인코딩)")
    scene_intent: Optional[str] = Field("일몰 도시 풍경 시네마틱 촬영", description="촬영 목적/의도")
    current_pitch: Optional[float] = Field(-15.0, description="현재 카메라 짐벌 틸트 각도")
    current_yaw: Optional[float] = Field(0.0, description="현재 기체 방위각")

class CompositionRecommendation(BaseModel):
    subject: str = Field(..., description="분석된 피사체 (예: 건물, 수면, 인물)", example="건물")
    composition: str = Field(..., description="추천 촬영 구도 (대각선 구도, 삼분할 구도 등)", example="대각선 구도")
    direction: str = Field(..., description="조종 방향 제안 (오른쪽으로 이동, 상승 등)", example="오른쪽으로 이동")
    reason: str = Field(..., description="구도 및 방향 추천 이유", example="건물의 측면과 전면을 함께 보여주기 적합")
    confidence: Optional[float] = Field(None, description="검증된 기하학적 정렬 신뢰도 점수 (임의 난수 배제)", example=0.87)
    confidence_basis: Optional[str] = Field(None, description="신뢰도 산출 근거 (예: geometric_alignment_metric)")

class MobilePostProcessedUIResponse(BaseModel):
    project_id: int
    subject: str
    composition: str
    direction: str
    reason: str
    confidence: Optional[float] = None
    confidence_basis: Optional[str] = None
    mobile_guide_dir: str  # 'up', 'down', 'left', 'right', 'none'
    offset_x: float
    offset_y: float
    frame_score: int
    is_ready_to_record: bool
    ui_message: str
    badge_color: str
    saved_analysis_id: Optional[int] = None


# ==========================================
# 6단계 드론 비행 안전 판단 로직 스키마 (Flight Safety Evaluation Schemas)
# ==========================================
class FlightSafetyEvaluationRequest(BaseModel):
    location: str = Field(..., description="비행 희망 장소 (주소 또는 랜드마크명)", example="서울 여의도 한강공원")
    altitude_m: Optional[float] = Field(default=120.0, description="예정 비행 고도 (m, 법정 한도 150m)", example=120.0)
    target_date: Optional[str] = Field(default=None, description="비행 희망 일자 (YYYY-MM-DD)", example="2026-10-24")
    target_time: Optional[str] = Field(default=None, description="비행 희망 시간 (예: 16:30, 19:00)", example="16:30")
    drone_weight_g: Optional[int] = Field(default=249, description="기체 중량 (g, 250g 이하 4종 자격)", example=249)
    has_camera: Optional[bool] = Field(default=True, description="촬영용 카메라 탑재 여부", example=True)
    flight_purpose: Optional[str] = Field(default="취미/레저 사진 및 영상 촬영", description="비행 목적", example="취미/레저 사진 및 영상 촬영")
    pilot_license_level: Optional[str] = Field(default="4종 (온라인 교육 이수)", description="보유 조종자 자격", example="4종 (온라인 교육 이수)")

class FlightSafetyEvaluationResponse(BaseModel):
    final_verdict: str = Field(..., description="종합 판정 결과: '적합 (FIT)', '주의 필요 (CAUTION)', '비행 불가 (PROHIBITED)', '위치 확인 필요 (UNVERIFIED)'", example="주의 필요 (CAUTION)")
    verdict_badge: str = Field(..., description="신호등 배지 아이콘 (🟢, 🟡, 🔴, ⚪)", example="🟡")
    safety_score: Optional[int] = Field(None, description="종합 안전 지수 (0~100점 또는 미확인 시 null)", example=75)
    is_preliminary_review: bool = Field(default=True, description="사전 안전 검토 여부 (공식 승인 여부와 구분)", example=True)
    disclaimer: str = Field(..., description="법적 공식 승인 구분 고지문")
    step_results: Dict[str, Any] = Field(default_factory=dict, description="6단계 세부 검토 결과 (위치, 공역, 고도, 기상, 시간, 기체제원)")
    actionable_checklist: List[str] = Field(default_factory=list, description="비행 전 필수 조치 체크리스트")
    warning_messages: List[str] = Field(default_factory=list, description="안전 위반 및 위험 요인 안내 목록")

    # [요구사항 4] 통일된 JSON 데이터 구조
    flight_location: Dict[str, Any] = Field(default_factory=dict, description="표준 위치 정보 블록")
    flight_conditions: Dict[str, Any] = Field(default_factory=dict, description="비행 조건 블록")
    flight_analysis: Dict[str, Any] = Field(default_factory=dict, description="비행 적합성 분석 결과 블록")


# ==========================================
# 7단계 PC·모바일 실시간 데이터 연동 스키마 (PC-Mobile Sync Schemas)
# ==========================================
class SyncProjectCreate(BaseModel):
    title: str = Field(default="한강 도시 풍경 촬영", example="한강 도시 풍경 촬영")
    place_name: str = Field(default="서울 여의도 한강공원", example="서울 여의도 한강공원")
    scene_intent: Optional[str] = Field(default="일몰과 함께 강변 풍경을 시네마틱하게 담고 싶어요.", example="일몰 강변 풍경")
    target_date: str = Field(default="2026-10-24", example="2026-10-24")
    target_time: str = Field(default="15:00 ~ 17:00", example="15:00 ~ 17:00")
    recommended_mode: Optional[str] = "패럴랙스 리빌 & 선셋 아크"
    recommended_shutter: Optional[str] = "1/50s"
    recommended_nd_filter: Optional[str] = "ND16"
    latitude: Optional[float] = 37.5284
    longitude: Optional[float] = 126.9328

    @field_validator("title", "place_name", "scene_intent", mode="before")
    def sanitize_sync_strings(cls, v):
        if isinstance(v, str):
            v = re.sub(r"<script.*?>.*?</script>", "", v, flags=re.IGNORECASE | re.DOTALL)
            v = re.sub(r"javascript:", "", v, flags=re.IGNORECASE)
            v = re.sub(r"on\w+\s*=", "", v, flags=re.IGNORECASE)
            return v.strip()
        return v

    @field_validator("latitude")
    def validate_lat(cls, v):
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("위도는 -90.0에서 90.0 범위 내여야 합니다.")
        return v

    @field_validator("longitude")
    def validate_lon(cls, v):
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("경도는 -180.0에서 180.0 범위 내여야 합니다.")
        return v

class SyncProjectResponse(SyncProjectCreate):
    id: int
    project_code: str = Field(..., example="DRONE_001", description="사람이 읽기 쉬운 고유 프로젝트 코드")
    status: str = Field(..., example="CREATED", description="생명주기 상태: CREATED, ANALYZING, COMPLETED, FAILED")
    project_token: Optional[str] = Field(None, description="모바일 접근용 암호화 서명 보안 토큰")
    mobile_access_url: str = Field(..., description="모바일 스마트폰 직접 접속 URL (camera.html)")
    qr_code_base64: Optional[str] = Field(None, description="PC 화면 렌더링용 QR코드 Base64 Data URI")
    created_at: datetime
    updated_at: Optional[datetime] = None
    analysis_count: int = 0
    class Config:
        from_attributes = True

class SyncStatusUpdate(BaseModel):
    status: str = Field(..., example="ANALYZING", description="변경할 상태: CREATED, ANALYZING, COMPLETED, FAILED")

class SyncAnalysisResultCreate(BaseModel):
    frame_score: int = Field(default=85, ge=0, le=100, example=85)
    offset_x: float = Field(default=0.0, example=0.0)
    offset_y: float = Field(default=0.0, example=0.0)
    guide_direction: str = Field(default="none", example="none")
    guide_message: Optional[str] = "AI 추천 구도 일치 촬영 완료"
    recorded_video_url: Optional[str] = "https://storage.skycommand.kr/videos/shot_001.mp4"

class SyncAnalysisResultResponse(SyncAnalysisResultCreate):
    id: int
    project_id: int
    created_at: datetime
    class Config:
        from_attributes = True


# ==========================================
# 8단계 사용자 인증 및 보안 스키마 (Auth & Security Schemas)
# ==========================================
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, example="new_pilot", description="사용자 아이디")
    password: str = Field(..., min_length=4, max_length=100, example="securePass123!", description="비밀번호")
    full_name: Optional[str] = Field("신규 조종사", example="홍길동", description="이름")
    email: Optional[str] = Field(None, example="new_pilot@skycommand.kr", description="이메일")
    role: Optional[str] = Field(default="pilot", example="pilot", description="역할: pilot (PC 조종사), crew (모바일 현장팀), admin (관리자)")
    drone_model: Optional[str] = Field(default="DJI Mini 4 Pro", description="보유 드론 기종")
    drone_weight_g: Optional[int] = Field(default=249, ge=0, le=50000, description="기체 중량(g)")

class UserLogin(BaseModel):
    username: str = Field(..., example="pilot", description="사용자 아이디")
    password: str = Field(..., example="pilot1234", description="비밀번호")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT Access Token")
    token_type: str = Field(default="bearer", description="토큰 유형 (Bearer)")
    expires_in_seconds: int = Field(default=86400, description="토큰 만료 시간 (초)")
    user_id: int = Field(..., description="사용자 DB 식별 번호")
    username: str = Field(..., description="사용자 아이디")
    role: str = Field(..., description="사용자 역할 (pilot / crew / admin)")
    allowed_screens: List[str] = Field(..., description="접근 가능한 화면 목록 (['pc', 'mobile'])")
    user: Optional[Dict[str, Any]] = Field(default=None, description="사용자 프로필 정보 딕셔너리")

class UserSecureProfile(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool
    drone_model: Optional[str] = None
    drone_weight_g: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True

class ProjectTokenResponse(BaseModel):
    project_code: str
    project_token: str
    expires_in_hours: int
    mobile_access_url: str

class ApiKeySecurityStatus(BaseModel):
    gemini_api: Dict[str, Any]
    vworld_api: Dict[str, Any]
    kma_api: Dict[str, Any]
    storage_mode: str
    frontend_exposed: bool


# ==========================================
# AI 비행 신청 도우미 대화 스키마
# ==========================================
class FlightApprovalChatRequest(BaseModel):
    user_query: str = Field(..., description="사용자 입력 메시지")
    conversation_history: Optional[List[Dict[str, str]]] = Field(default=None, description="대화 히스토리")
    current_application_info: Optional[Dict[str, Any]] = Field(default=None, description="현재까지 누적된 신청 정보")
    reference_date_str: Optional[str] = Field(default=None, description="기준 일자 (YYYY-MM-DD)")

class FlightApprovalChatResponse(BaseModel):
    intent: str
    assistant_message: str
    application_info: Dict[str, Any]
    missing_fields: List[str]
    completion_rate: int
    needs_location_confirmation: bool = False
    needs_date_confirmation: bool = False


# ==========================================
# 등록된 드론 (Registered Drone) 스키마
# ==========================================
class RegisteredDroneBase(BaseModel):
    drone_type: Optional[str] = Field("무인멀티콥터", description="기체 종류 (무인비행기, 무인헬리콥터, 무인멀티콥터, 기타)")
    report_number: Optional[str] = Field(None, description="신고번호")
    model_name: str = Field(..., description="모델명 (필수)")
    purpose: Optional[str] = Field("비영리", description="용도 (비영리 / 영리)")
    manufacturer: Optional[str] = Field(None, description="제작자")
    operation_type: Optional[str] = Field("비연구용", description="운용유형 (비연구용 / 연구용)")
    specifications: Optional[str] = Field(None, description="규격")
    takeoff_weight: Optional[str] = Field("249g", description="자체중량")
    owner_name: Optional[str] = Field(None, description="소유자")
    phone_number: Optional[str] = Field(None, description="전화번호")
    safety_cert_number: Optional[str] = Field(None, description="안전성인증증번호")
    cert_expiry_date: Optional[str] = Field(None, description="인증 유효기간")
    insurance_status: Optional[str] = Field("가입", description="보험가입유무 (미가입 / 가입)")
    description: Optional[str] = Field(None, description="상세설명")
    serial_number: Optional[str] = Field(None, description="제작번호")

class RegisteredDroneCreate(RegisteredDroneBase):
    pass

class RegisteredDroneUpdate(BaseModel):
    drone_type: Optional[str] = None
    report_number: Optional[str] = None
    model_name: Optional[str] = None
    purpose: Optional[str] = None
    manufacturer: Optional[str] = None
    operation_type: Optional[str] = None
    specifications: Optional[str] = None
    takeoff_weight: Optional[str] = None
    owner_name: Optional[str] = None
    phone_number: Optional[str] = None
    safety_cert_number: Optional[str] = None
    cert_expiry_date: Optional[str] = None
    insurance_status: Optional[str] = None
    description: Optional[str] = None
    serial_number: Optional[str] = None

class RegisteredDroneResponse(RegisteredDroneBase):
    drone_id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==========================================
# 스마트폰 센서 & 촬영 동선 (ShootingPath) 스키마
# ==========================================
class RawSensorData(BaseModel):
    alpha: Optional[float] = Field(None, description="기기 Z축 회전각 (0~360도, 미수집시 null)")
    beta: Optional[float] = Field(None, description="기기 X축 기울기 (-180~180도, 미수집시 null)")
    gamma: Optional[float] = Field(None, description="기기 Y축 회전각 (-90~90도, 미수집시 null)")
    screen_orientation_deg: Optional[int] = Field(0, description="화면 회전 각도 (0, 90, 180, 270)")
    is_absolute: Optional[bool] = Field(False, description="지자기 기준 절대각 여부")

class ConvertedCameraOrientation(BaseModel):
    camera_heading_deg: Optional[float] = Field(None, description="화면 방향 보정된 카메라 렌즈 방위각 (0~360도, 미수집시 null)")
    camera_pitch_deg: Optional[float] = Field(None, description="화면 방향 보정된 카메라 상하 틸트각 (-90~90도, 미수집시 null)")
    camera_roll_deg: Optional[float] = Field(None, description="카메라 좌우 롤 각도 (미수집시 null)")
    frame_aspect: Optional[str] = Field("PORTRAIT", description="촬영 화면 비율 (PORTRAIT/LANDSCAPE)")

class PhonePositionData(BaseModel):
    lat: float = Field(..., description="위도")
    lng: float = Field(..., description="경도")
    accuracy_m: Optional[float] = Field(None, description="스마트폰 GPS 오차 반경 (미터)")
    altitude_m: Optional[float] = Field(None, description="스마트폰 보고 고도 (미수집시 null, 임의 드론 고도 생성 금지)")

class PhoneWaypointItem(BaseModel):
    seq: int = Field(..., description="시퀀스 번호")
    timestamp: Optional[str] = Field(None, description="수집 시각 (ISO 8601)")
    raw_gps: Optional[PhonePositionData] = Field(None, description="스마트폰 GPS 수집 원본")
    filtered_gps: Optional[PhonePositionData] = Field(None, description="노이즈 필터링된 보행 좌표")
    raw_sensor: Optional[RawSensorData] = Field(None, description="단말기 방향 센서 원본")
    camera_orientation: Optional[ConvertedCameraOrientation] = Field(None, description="변환된 카메라 렌즈 방향")
    composition_state: Optional[Dict[str, Any]] = Field(None, description="실시간 화면 구도 분석 상태")

class ShootingPathCreate(BaseModel):
    project_id: int = Field(..., description="촬영 프로젝트 ID")
    shooting_number: Optional[int] = Field(None, description="동일 프로젝트 내 촬영 회차 (생략 시 자동 산출)")
    tracking_source: str = Field("PHONE_GPS", description="위치 수집 출처: PHONE_GPS, SIMULATION (확장: DRONE_GPS)")
    recommended_waypoints: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="권장 보행 촬영 동선")
    actual_waypoints: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="스마트폰 수집 실제 보행 동선 및 센서 데이터")
    corrected_waypoints: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="보정된 동선 가이드")
    alpha_weight: Optional[float] = Field(0.3, description="보정 가중치 (0.0~1.0)")
    deviation_score: Optional[float] = Field(None, description="권장 동선 대비 이탈도")
    deviation_reason: Optional[str] = Field(None, description="이탈 사유 (NORMAL, WALKING_DETOUR, PHONE_SHAKE 등)")
    is_valid: Optional[bool] = Field(True, description="차기 추천 반영 유효성 여부")

class ShootingPathResponse(BaseModel):
    path_id: int
    project_id: int
    user_id: Optional[int] = None
    shooting_number: int
    tracking_source: str
    recommended_waypoints: Optional[List[Dict[str, Any]]] = None
    actual_waypoints: Optional[List[Dict[str, Any]]] = None
    corrected_waypoints: Optional[List[Dict[str, Any]]] = None
    alpha_weight: float
    deviation_score: Optional[float] = None
    deviation_reason: Optional[str] = None
    is_valid: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ShootingPathSummaryItem(BaseModel):
    path_id: int
    project_id: int
    shooting_number: int
    tracking_source: str
    waypoint_count: int
    deviation_score: Optional[float] = None
    deviation_reason: Optional[str] = None
    is_valid: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ShootingPathProjectSummary(BaseModel):
    project_id: int
    total_attempts: int
    total_shooting_count: Optional[int] = None
    latest_shooting_number: int
    valid_paths_count: int
    latest_path: Optional[ShootingPathResponse] = None
    history: List[ShootingPathSummaryItem] = []


class PathAnalysisDetailResponse(BaseModel):
    is_valid: bool
    deviation_score: Optional[float] = None
    match_score: float
    max_deviation_m: Optional[float] = None
    avg_deviation_m: Optional[float] = None
    average_deviation_m: Optional[float] = None
    start_point_error_m: Optional[float] = None
    end_point_error_m: Optional[float] = None
    path_length_rec_m: float
    path_length_act_m: float
    alpha_weight: float
    deviation_reason: str
    composition_score: Optional[float] = None
    advice_message: str
    actionable_advice: Optional[str] = None
    recommended_waypoints: List[Dict[str, Any]]
    actual_waypoints: List[Dict[str, Any]]
    corrected_waypoints: List[Dict[str, Any]]


class NextRoundPathResponse(BaseModel):
    project_id: int
    next_shooting_number: int
    target_shooting_number: Optional[int] = None
    is_inherited_from_previous: bool
    source_info: str
    previous_shooting_number: Optional[int] = None
    source_shooting_number: Optional[int] = None
    previous_deviation_score: Optional[float] = None
    previous_deviation_reason: Optional[str] = None
    recommended_waypoints: List[Dict[str, Any]]


# ==========================================
# 장소 시각 자료 (LocationAsset) 스키마
# ==========================================
class LocationAssetCreate(BaseModel):
    project_id: int = Field(..., description="촬영 프로젝트 ID")
    is_common: Optional[bool] = Field(False, description="프로젝트 공통 자료 여부 (False: 모바일 현장 업로드)")
    asset_type: str = Field(..., description="자료 유형: PANORAMA, SHORT_VIDEO, CAMERA_FRAME, KEY_FEATURE")
    file_url: str = Field(..., description="파일 URL 또는 로컬 경로")
    thumbnail_url: Optional[str] = Field(None, description="썸네일 URL")
    detected_features: Optional[Dict[str, Any]] = Field(default_factory=dict, description="AI 객체 및 구도 특징점 분석 결과")
    file_size_bytes: Optional[int] = Field(None, description="파일 크기 (바이트)")

class LocationAssetResponse(LocationAssetCreate):
    asset_id: int
    user_id: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True


# ==========================================
# 촬영 기법 카탈로그 (ShootingTechnique) 및 맞춤 추천 스키마
# ==========================================
class ShootingTechniqueItem(BaseModel):
    technique_id: str
    name_ko: str
    category: str
    support_phone: bool
    support_drone: bool
    required_sensors: List[str] = Field(default_factory=list)
    guide_instruction: str


class TechniqueCatalogItem(BaseModel):
    technique_id: str
    name: str
    category: str
    description: str
    recommended_scenes: List[str]
    required_environment: Dict[str, Any]
    is_smartphone_supported: bool
    is_drone_only: bool
    drone_warning: Optional[str] = None
    related_tags: List[str]
    recommended_composition: str
    precautions: str
    execution_guide: str


class TechniqueRecommendationItem(BaseModel):
    technique_id: str
    name: str
    category: str
    description: str
    recommendation_score: float
    recommendation_reason: str
    related_composition: str
    precautions: str
    execution_guide: str
    is_smartphone_supported: bool
    is_drone_only: bool
    drone_warning: Optional[str] = None
    recommended_scenes: List[str] = Field(default_factory=list)
    required_environment: Dict[str, Any] = Field(default_factory=dict)
    related_tags: List[str] = Field(default_factory=list)
    related_videos: List[Dict[str, Any]] = Field(default_factory=list)


class PersonalizedRecommendationResponse(BaseModel):
    project_id: Optional[int] = None
    user_id: Optional[int] = None
    user_context: str
    count: int
    recommendations: List[TechniqueRecommendationItem]


class TechniqueSelectRequest(BaseModel):
    technique_id: str = Field(..., description="선택할 촬영 기법 ID")


class TechniqueSelectResponse(BaseModel):
    status: str
    project_id: int
    selected_technique_id: str
    technique_name: str
    desired_techniques: List[str]
    message: str


class TechniqueFeedbackRequest(BaseModel):
    technique_id: str = Field(..., description="피드백 대상 촬영 기법 ID")
    shooting_number: Optional[int] = Field(1, description="촬영 회차 번호")
    was_shot: bool = Field(True, description="실제 촬영 진행 여부")
    satisfaction_score: int = Field(5, ge=1, le=5, description="만족도 점수 (1~5점)")
    comment: Optional[str] = Field(None, description="사용자 피드백 코멘트")


class TechniqueFeedbackResponse(BaseModel):
    status: str
    project_id: int
    technique_id: str
    satisfaction_score: int
    was_shot: bool
    applied_weight: float
    updated_preference_score: float
    message: str







