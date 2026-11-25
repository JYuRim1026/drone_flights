from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, UniqueConstraint, event
from sqlalchemy.orm import relationship, synonym
from datetime import datetime
from backend.database import Base

# ==========================================
# 1. users — 사용자 정보 (PC & 모바일 공통 계정)
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=True)
    username = Column(String(50), nullable=True)
    user_name = Column(String(50), nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 추가 편의/호환 컬럼
    full_name = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    drone_model = Column(String(50), default="DJI Mini 4 Pro")
    drone_weight_g = Column(Integer, default=249)
    role = Column(String(30), default="pilot")          # pilot, crew, admin
    is_active = Column(Boolean, default=True)

    def __init__(self, **kwargs):
        u = kwargs.get("username") or kwargs.get("user_name")
        if u:
            kwargs["username"] = u
            kwargs["user_name"] = u
        p = kwargs.get("hashed_password") or kwargs.get("password_hash")
        if p:
            kwargs["hashed_password"] = p
            kwargs["password_hash"] = p
        uid = kwargs.get("id") or kwargs.get("user_id")
        if uid is not None:
            kwargs["id"] = uid
            kwargs["user_id"] = uid
        super().__init__(**kwargs)

    # 관계 설정 (1:1 user_settings, 1:N flight_requests, 1:N shooting_projects, 1:N flight_guide_logs, 1:N registered_drones)
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan", foreign_keys="[UserSetting.user_id]")
    flight_requests = relationship("FlightRequest", back_populates="user", cascade="all, delete-orphan", foreign_keys="[FlightRequest.user_id]")
    shooting_projects = relationship("ShootingProject", back_populates="user", cascade="all, delete-orphan", foreign_keys="[ShootingProject.user_id]")
    flight_guide_logs = relationship("FlightGuideLog", back_populates="user", cascade="all, delete-orphan", foreign_keys="[FlightGuideLog.user_id]")
    registered_drones = relationship("RegisteredDrone", back_populates="user", cascade="all, delete-orphan", foreign_keys="[RegisteredDrone.user_id]")

    # 커뮤니티 선호도 및 상호작용 관계 (1:N survey_preferences, 1:N preference_scores, 1:N interactions)
    survey_preferences = relationship("SurveyPreference", back_populates="user", cascade="all, delete-orphan", foreign_keys="[SurveyPreference.user_id]")
    preference_scores = relationship("UserPreferenceScore", back_populates="user", cascade="all, delete-orphan", foreign_keys="[UserPreferenceScore.user_id]")
    interactions = relationship("Interaction", back_populates="user", cascade="all, delete-orphan", foreign_keys="[Interaction.user_id]")

    # 신규 관계 (1:N shooting_paths, 1:N location_assets, 1:N personalized_paths)
    shooting_paths = relationship("ShootingPath", back_populates="user", foreign_keys="[ShootingPath.user_id]")
    location_assets = relationship("LocationAsset", back_populates="user", foreign_keys="[LocationAsset.user_id]")
    personalized_paths = relationship("PersonalizedShootingPath", back_populates="user", cascade="all, delete-orphan", foreign_keys="[PersonalizedShootingPath.user_id]")


# ==========================================
# 2. user_settings — 사용자 환경 설정 (1:1 관계)
# ==========================================
class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    preferred_mode = Column(String(30), default="cinematic")
    preferred_camera_mode = Column(String(50), default="cinematic")
    notification = Column(Boolean, default=True)
    notification_enabled = Column(Boolean, default=True)
    settings_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    safety_margin_m = Column(Integer, default=30)
    weather_auto_refresh = Column(Boolean, default=True)

    def __init__(self, **kwargs):
        m = kwargs.get("preferred_mode") or kwargs.get("preferred_camera_mode") or "cinematic"
        kwargs["preferred_mode"] = m
        kwargs["preferred_camera_mode"] = m
        n = kwargs.get("notification") if kwargs.get("notification") is not None else kwargs.get("notification_enabled", True)
        kwargs["notification"] = n
        kwargs["notification_enabled"] = n
        super().__init__(**kwargs)

    # 관계 설정
    user = relationship("User", back_populates="settings")


# ==========================================
# 3. flight_requests — 비행 신청 정보 (PC 중심 비행 계획 & 모바일 요약 조회)
# ==========================================
class FlightRequest(Base):
    __tablename__ = "flight_requests"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, unique=True, index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    flight_date = Column(DateTime, default=datetime.utcnow)
    flight_location = Column(String(255), nullable=True)
    location = Column(String(200), nullable=True)
    flight_status = Column(String(30), default="APPROVED")   # READY, PENDING, APPROVED, REJECTED
    approval_status = Column(String(20), default="APPROVED")
    flight_plan = Column(JSON, nullable=True)               # 비행 계획 상세 (웨이포인트, 시간, 고도 등)

    latitude = Column(Float, nullable=True, default=37.5284)
    longitude = Column(Float, nullable=True, default=126.9328)
    start_date = Column(String(30), nullable=True, default="2026-10-24")
    end_date = Column(String(30), nullable=True, default="2026-10-24")
    flight_time = Column(String(50), nullable=True, default="14:00 ~ 16:00")
    drone_weight = Column(String(50), nullable=True, default="249g (초경량)")
    has_camera = Column(Boolean, default=True)
    purpose = Column(String(100), nullable=True, default="경관 사진 및 영상 촬영")
    altitude = Column(String(30), default="120m")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        loc = kwargs.get("location") or kwargs.get("flight_location") or "비행 예정 장소"
        kwargs["location"] = loc
        kwargs["flight_location"] = loc
        st = kwargs.get("approval_status") or kwargs.get("flight_status") or "APPROVED"
        kwargs["approval_status"] = st
        kwargs["flight_status"] = st
        fid = kwargs.get("id") or kwargs.get("flight_id")
        if fid is not None:
            kwargs["id"] = fid
            kwargs["flight_id"] = fid
        super().__init__(**kwargs)

    # 관계 설정
    user = relationship("User", back_populates="flight_requests")
    projects = relationship("ShootingProject", back_populates="flight_request")
    guide_logs = relationship("FlightGuideLog", back_populates="flight_request")


# ==========================================
# SQLAlchemy Synchronization Listeners
# ==========================================
@event.listens_for(User, "before_insert")
def _sync_user_before_insert(mapper, connection, target):
    u = target.username or target.user_name
    if u:
        target.username = u
        target.user_name = u
    p = target.hashed_password or target.password_hash
    if p:
        target.hashed_password = p
        target.password_hash = p
    if target.id is not None and target.user_id is None:
        target.user_id = target.id
    elif target.user_id is not None and target.id is None:
        target.id = target.user_id

@event.listens_for(User, "after_insert")
def _sync_user_after_insert(mapper, connection, target):
    if target.user_id is None or target.user_id != target.id:
        connection.execute(
            User.__table__.update().where(User.id == target.id).values(user_id=target.id)
        )

@event.listens_for(FlightRequest, "before_insert")
def _sync_flight_before_insert(mapper, connection, target):
    loc = target.location or target.flight_location or "비행 예정 장소"
    target.location = loc
    target.flight_location = loc
    st = target.approval_status or target.flight_status or "APPROVED"
    target.approval_status = st
    target.flight_status = st
    if target.id is not None and target.flight_id is None:
        target.flight_id = target.id
    elif target.flight_id is not None and target.id is None:
        target.id = target.flight_id

@event.listens_for(FlightRequest, "after_insert")
def _sync_flight_after_insert(mapper, connection, target):
    if target.flight_id is None or target.flight_id != target.id:
        connection.execute(
            FlightRequest.__table__.update().where(FlightRequest.id == target.id).values(flight_id=target.id)
        )


# ==========================================
# 4. airspace_zones — 공역 및 비행 제한 정보 (공공데이터 및 관제)
# ==========================================
class AirspaceZone(Base):
    __tablename__ = "airspace_zones"

    zone_id = Column(Integer, primary_key=True, index=True)
    zone_name = Column(String(100), index=True, nullable=False)
    zone_type = Column(String(30), nullable=False)          # CTR, PROHIBITED, RESTRICTED, UNCONTROLLED
    geometry = Column(JSON, nullable=True)                  # 공간 좌표 및 영역 폴리곤 / 버퍼
    altitude_limit = Column(Float, default=150.0)           # 고도 제한 (m) - DECIMAL(8,2)

    # 호환성 컬럼 & synonym
    id = synonym("zone_id")
    latitude = Column(Float, nullable=True, default=37.5284)
    longitude = Column(Float, nullable=True, default=126.9328)
    radius_meter = Column(Integer, default=1000)
    altitude_limit_m = synonym("altitude_limit")
    approval_required = Column(Boolean, default=True)
    contact_agency = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)


# ==========================================
# 5. shooting_projects — 촬영 프로젝트 통합 (가장 중요한 테이블)
# (기존 shooting_analyses 는 삭제하고 shooting_projects 에 통합)
# ==========================================
class ShootingProject(Base):
    __tablename__ = "shooting_projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    flight_request_id = Column(Integer, ForeignKey("flight_requests.flight_id"), nullable=True)

    title = Column(String(150), nullable=False)
    place_name = Column(String(150), nullable=False)
    latitude = Column(Float, default=37.5284)
    longitude = Column(Float, default=126.9328)
    target_date = Column(String(30), nullable=True, default="2026-10-24")
    target_time = Column(String(50), nullable=True, default="14:00 ~ 16:00")
    scene_intent = Column(Text, nullable=True)
    recommended_mode = Column(String(100), default="패럴랙스 리빌 & 선셋 아크")
    recommended_shutter = Column(String(50), default="1/50s")
    recommended_nd_filter = Column(String(50), default="ND16")
    status = Column(String(30), default="READY")
    created_at = Column(DateTime, default=datetime.utcnow)
    project_code = Column(String(50), unique=True, index=True, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project_token = Column(String(512), nullable=True)

    # 호환용 컬럼들 (모바일 및 통합 API)
    project_id = Column(Integer, nullable=True)
    flight_id = Column(Integer, nullable=True)
    project_name = Column(String(100), nullable=True)
    shooting_purpose = Column(String(100), nullable=True)
    shooting_location = Column(String(255), nullable=True)
    planned_time = Column(DateTime, nullable=True, default=datetime.utcnow)
    composition_type = Column(String(50), nullable=True)
    analysis_result = Column(JSON, nullable=True)
    detected_scene = Column(String(100), nullable=True)
    recommended_composition = Column(String(100), nullable=True)
    achieved_rate = Column(Float, nullable=True)
    shooting_duration = Column(Integer, nullable=True)
    result_file_url = Column(String(500), nullable=True)
    analysis_completed_at = Column(DateTime, nullable=True)

    # 신규 다중 기법 태그 컬럼 (사용자 희망 기법 & AI 추천 기법)
    desired_techniques = Column(JSON, nullable=True, default=list)
    recommended_techniques = Column(JSON, nullable=True, default=list)

    def __init__(self, **kwargs):
        # 양방향 필드 동기화 (title <-> project_name, place_name <-> shooting_location 등)
        t = kwargs.get("title") or kwargs.get("project_name")
        kwargs["title"] = t or "촬영 프로젝트"
        kwargs["project_name"] = t or "촬영 프로젝트"

        p = kwargs.get("place_name") or kwargs.get("shooting_location")
        kwargs["place_name"] = p or "서울 한강공원"
        kwargs["shooting_location"] = p or "서울 한강공원"

        purpose = kwargs.get("shooting_purpose")
        intent = kwargs.get("scene_intent")
        if purpose and not intent:
            kwargs["scene_intent"] = purpose
        elif intent and not purpose:
            kwargs["shooting_purpose"] = intent

        m = kwargs.get("recommended_mode") or kwargs.get("recommended_composition")
        if m:
            kwargs["recommended_mode"] = m
            kwargs["recommended_composition"] = m

        super().__init__(**kwargs)

    # 관계 설정
    user = relationship("User", back_populates="shooting_projects")
    flight_request = relationship("FlightRequest", back_populates="projects")
    analyses = relationship("ShootingAnalysis", back_populates="project", cascade="all, delete-orphan", foreign_keys="[ShootingAnalysis.project_id]")
    paths = relationship("ShootingPath", back_populates="project", cascade="all, delete-orphan", foreign_keys="[ShootingPath.project_id]")
    assets = relationship("LocationAsset", back_populates="project", cascade="all, delete-orphan", foreign_keys="[LocationAsset.project_id]")
    common_paths = relationship("ProjectCommonPath", back_populates="project", cascade="all, delete-orphan", foreign_keys="[ProjectCommonPath.project_id]")
    personalized_paths = relationship("PersonalizedShootingPath", back_populates="project", cascade="all, delete-orphan", foreign_keys="[PersonalizedShootingPath.project_id]")


@event.listens_for(ShootingProject, "after_insert")
def _sync_project_after_insert(mapper, connection, target):
    if target.project_id is None or target.project_id != target.id:
        connection.execute(
            ShootingProject.__table__.update().where(ShootingProject.id == target.id).values(project_id=target.id)
        )


# ==========================================
# 6. flight_guide_logs — 비행 가이드 기록
# (비행 가이드 제공 횟수와 안전/구도 이행률 분석 관리용)
# ==========================================
class FlightGuideLog(Base):
    __tablename__ = "flight_guide_logs"

    guide_log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    flight_id = Column(Integer, ForeignKey("flight_requests.flight_id"), nullable=False)
    guide_type = Column(String(50), nullable=False)         # e.g. "SAFETY_AIRSPACE", "CINEMA_COMPOSITION", "WEATHER_ALERT"
    provided_at = Column(DateTime, default=datetime.utcnow) # 가이드 제공 시점
    compliance_status = Column(String(30), default="COMPLIANT") # 이행 여부 (COMPLIANT, NON_COMPLIANT, PENDING)

    # 호환성 컬럼 & synonym
    id = synonym("guide_log_id")

    # 관계 설정
    user = relationship("User", back_populates="flight_guide_logs")
    flight_request = relationship("FlightRequest", back_populates="guide_logs")


# ==========================================
# 7. registered_drones — 등록된 드론 관리 (1:N with users)
# ==========================================
class RegisteredDrone(Base):
    __tablename__ = "registered_drones"

    drone_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)

    drone_type = Column(String(50), default="무인멀티콥터")     # 무인비행기, 무인헬리콥터, 무인멀티콥터, 기타
    report_number = Column(String(100), nullable=True)         # 신고번호
    model_name = Column(String(100), nullable=False)           # 모델명 (필수)
    purpose = Column(String(50), default="비영리")              # 용도 (비영리 / 영리)
    manufacturer = Column(String(100), nullable=True)          # 제작자
    operation_type = Column(String(50), default="비연구용")     # 운용유형 (비연구용 / 연구용)
    specifications = Column(String(100), nullable=True)        # 규격
    takeoff_weight = Column(String(50), default="249g")        # 자체중량
    owner_name = Column(String(100), nullable=True)            # 소유자
    phone_number = Column(String(50), nullable=True)           # 전화번호
    safety_cert_number = Column(String(100), nullable=True)    # 안전성인증증번호
    cert_expiry_date = Column(String(50), nullable=True)       # 인증 유효기간
    insurance_status = Column(String(50), default="가입")      # 보험가입유무 (미가입 / 가입)
    description = Column(Text, nullable=True)                  # 상세설명
    serial_number = Column(String(100), nullable=True)         # 제작번호

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 호환성 synonym
    id = synonym("drone_id")

    # 관계 설정 (N:1 with User)
    user = relationship("User", back_populates="registered_drones")


# ==========================================
# 8. videos — 커뮤니티 영상 정보
# ==========================================
class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    background = Column(Text, nullable=True)     # 배경 (도시/수변, 자연/산악, 바다/해안 등)
    time_slot = Column(Text, nullable=True)      # 촬영 시간대 (주간, 골든아워, 일몰, 야간 등)
    composition = Column(Text, nullable=True)    # 구도 (와이드 트래킹, 오빗, 버드아이 등)
    content_techniques = Column(JSON, nullable=True, default=list) # 신규 다중 기법 태그 (["ground_orbit", "tracking_walk"] 등)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계 설정 (1:N with interactions)
    interactions = relationship("Interaction", back_populates="video", cascade="all, delete-orphan")


# ==========================================
# 9. survey_preferences — 최초 설문 응답 (카테고리별 선호도)
# ==========================================
class SurveyPreference(Base):
    __tablename__ = "survey_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "value", name="uq_survey_user_cat_val"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    category = Column(Text, nullable=False)      # category (background, time_slot, composition 등)
    value = Column(Text, nullable=False)         # value (바다, 골든아워, 오빗 등)
    strength = Column(Float, default=1.0)        # strength (선호 강도)

    # 관계 설정 (N:1 with users)
    user = relationship("User", back_populates="survey_preferences")


# ==========================================
# 10. user_preference_scores — 계산된 사용자별 선호도 점수
# ==========================================
class UserPreferenceScore(Base):
    __tablename__ = "user_preference_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "preference_value", name="uq_pref_user_cat_val"),
    )

    preference_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    category = Column(Text, nullable=False)             # category
    preference_value = Column(Text, nullable=False)     # preference_value
    preference_score = Column(Float, default=0.0)       # preference_score
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 호환성 synonym
    id = synonym("preference_id")

    # 관계 설정 (N:1 with users)
    user = relationship("User", back_populates="preference_scores")


# ==========================================
# 11. interactions — 영상 조회·좋아요·저장 이력
# ==========================================
class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, index=True)
    event_type = Column(Text, nullable=False)           # 'view', 'like', 'save', 'share'
    active = Column(Integer, default=1)                 # 1: 활성, 0: 취소/비활성
    occurred_at = Column(DateTime, default=datetime.utcnow)

    # 관계 설정 (N:1 with users, N:1 with videos)
    user = relationship("User", back_populates="interactions")
    video = relationship("Video", back_populates="interactions")


# ==========================================
# 11. shooting_analyses — 모바일 카메라 실시간 영상 최종 분석 결과 저장
# ==========================================
class ShootingAnalysis(Base):
    __tablename__ = "shooting_analyses"

    analysis_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_status = Column(String(50), default="completed", nullable=False)
    target_summary = Column(Text, nullable=True)
    environment_summary = Column(Text, nullable=True)
    recommended_composition = Column(String(100), nullable=True)
    target_coordinates = Column(JSON, nullable=True)
    composition_score = Column(Float, nullable=True)
    guide_message = Column(Text, nullable=True)
    representative_image_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    id = synonym("analysis_id")
    frame_score = synonym("composition_score")
    recorded_video_url = synonym("representative_image_path")

    # 관계 설정 (N:1 with ShootingProject)
    project = relationship("ShootingProject", back_populates="analyses")


# ==========================================
# 12. shooting_paths — 휴대폰 촬영 동선(보행 궤적) 및 가이드 보정 관리
# ==========================================
class ShootingPath(Base):
    __tablename__ = "shooting_paths"
    __table_args__ = (
        UniqueConstraint("project_id", "shooting_number", name="uq_project_shooting_number"),
    )

    path_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # 동일 프로젝트 내 촬영 회차 (1회차, 2회차...)
    shooting_number = Column(Integer, default=1, nullable=False, index=True)

    # 위치 수집 출처 (현재: PHONE_GPS, SIMULATION 우선 지원 / 향후 확장: DRONE_GPS)
    tracking_source = Column(String(30), default="PHONE_GPS", nullable=False)

    # [권장 촬영 동선]: 사전 기획된 보행 동선 및 카메라 지향 목표
    # [{"seq": 1, "lat": ..., "lng": ..., "target_heading": 180.0, "target_pitch": -10.0, "guide_msg": "..."}, ...]
    recommended_waypoints = Column(JSON, nullable=True, default=list)

    # [실제 휴대폰 수집 동선]: 휴대폰 GPS + 방향 센서(heading, pitch, roll) + 실시간 구도 분석
    # 절대 드론 비행 경로로 취급하지 않으며, 단말기 수집 데이터만 온전히 보관
    # [{"seq": 1, "timestamp": "...", "raw_gps": {...}, "camera_orientation": {...}, ...}]
    actual_waypoints = Column(JSON, nullable=True, default=list)

    # [보정된 동선 가이드]: 보행 흔들림 및 카메라 조준 오차를 다듬은 개선 가이드라인
    corrected_waypoints = Column(JSON, nullable=True, default=list)

    # 보정 가중치 및 편차 분석
    alpha_weight = Column(Float, default=0.3, nullable=False)
    deviation_score = Column(Float, nullable=True)      # 권장 동선/방향 대비 평균 이탈 오차
    deviation_reason = Column(Text, nullable=True)     # NORMAL, WALKING_DETOUR, PHONE_SHAKE, GPS_ACCURACY_LOW 등
    is_valid = Column(Boolean, default=True, nullable=False)  # 보행 이탈이 심할 경우 차기 추천 반영 제외(False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 호환성 별칭
    id = synonym("path_id")

    # 관계 설정
    project = relationship("ShootingProject", back_populates="paths")
    user = relationship("User", back_populates="shooting_paths", foreign_keys=[user_id])


# ==========================================
# 13. location_assets — 촬영 장소 시각 자료 (스마트폰 촬영 파노라마/영상/캡처)
# ==========================================
class LocationAsset(Base):
    __tablename__ = "location_assets"

    asset_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # 사전 제공 기본 자료(True) vs 스마트폰 현장 업로드 개인 자료(False)
    is_common = Column(Boolean, default=False, nullable=False, index=True)

    # 자료 종류 (PANORAMA, SHORT_VIDEO, CAMERA_FRAME, KEY_FEATURE)
    asset_type = Column(String(50), nullable=False)
    file_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)

    # 스마트폰 프레임에서 감지된 피사체/특징점 메타데이터
    detected_features = Column(JSON, nullable=True, default=dict)
    file_size_bytes = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 호환성 별칭
    id = synonym("asset_id")

    # 관계 설정
    project = relationship("ShootingProject", back_populates="assets")
    user = relationship("User", back_populates="location_assets", foreign_keys=[user_id])


# ==========================================
# 14. project_common_paths — 다중 사용자 공통 학습 권장 경로 (Phase 8)
# ==========================================
class ProjectCommonPath(Base):
    __tablename__ = "project_common_paths"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False, index=True)

    # 공통 권장 웨이포인트 목록
    # [{"seq": 1, "lat": ..., "lng": ..., "target_heading": ..., "target_pitch": ..., "action": ...}, ...]
    common_waypoints = Column(JSON, nullable=False, default=list)

    # 반영 메타데이터
    contributor_count = Column(Integer, default=1, nullable=False)   # 학습에 기여한 순 사용자(조종사) 수
    total_paths_used = Column(Integer, default=1, nullable=False)    # 학습에 반영된 유효 보행 동선 수
    quality_score = Column(Float, default=80.0, nullable=False)      # 가중 평균 종합 품질 점수
    average_deviation_m = Column(Float, nullable=True)               # 참여 경로들의 평균 횡방향 이탈도
    average_composition_score = Column(Float, nullable=True)         # 참여 경로들의 평균 AI 구도 점수
    average_satisfaction_score = Column(Float, nullable=True)        # 참여자들의 평균 만족도 점수

    learning_metadata = Column(JSON, nullable=True, default=dict)    # 반영된 path_id 목록, 가중치 산출 내역 등
    is_active = Column(Boolean, default=True, nullable=False, index=True) # 최신 활성 버전 여부

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계 설정
    project = relationship("ShootingProject", back_populates="common_paths")


# ==========================================
# 14. personalized_shooting_paths — Phase 9 사용자별 맞춤 촬영 경로 변형 관리
# ==========================================
class PersonalizedShootingPath(Base):
    """
    Phase 9: 개인별 촬영 경로 변형 모델
    - 최신 활성 공통 경로(ProjectCommonPath)를 불변 기준선으로 참조
    - 사용자의 과거 촬영 이력, 이탈도, 선호 기법을 분석하여 맞춤 경로 생성
    - 변형 유형: STRAIGHT (직선형), ZIGZAG (지그재그형), POI_WAYPOINT (주요촬영지점경유형), COLD_START (신규기본)
    """
    __tablename__ = "personalized_shooting_paths"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    common_path_id = Column(Integer, ForeignKey("project_common_paths.id", ondelete="SET NULL"), nullable=True)

    # 생성 시점의 기준 공통 경로 버전 (Phase 8 연동)
    base_common_version = Column(Integer, default=1, nullable=False, index=True)

    # 개인별 변형 유형
    variation_type = Column(String(50), nullable=False, default="STRAIGHT", index=True)

    # 생성된 개인별 맞춤 권장 웨이포인트 목록
    # [{"seq": 1, "lat": ..., "lng": ..., "target_heading": ..., "target_pitch": ..., "action": ..., "guide_msg": ...}]
    personalized_waypoints = Column(JSON, nullable=False, default=list)

    # 개인화 생성 사유 및 성향 분석 요약문
    generation_reason = Column(Text, nullable=False)

    # 세부 메타데이터: {lateral_offset_m, added_poi_info: {...}, profile_summary: {...}}
    style_metadata = Column(JSON, nullable=True, default=dict)

    # 활성 상태 (사용자-프로젝트 쌍마다 최신 1건만 is_active=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 관계 설정
    project = relationship("ShootingProject", back_populates="personalized_paths")
    user = relationship("User", back_populates="personalized_paths")
    common_path = relationship("ProjectCommonPath")
