from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship, synonym
from datetime import datetime
from backend.database import Base

# ==========================================
# 1. users — 사용자 정보 (PC & 모바일 공통 계정)
# ==========================================
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 추가 편의/호환 컬럼
    full_name = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    drone_model = Column(String(50), default="DJI Mini 4 Pro")
    drone_weight_g = Column(Integer, default=249)
    role = Column(String(30), default="pilot")          # pilot, crew, admin
    is_active = Column(Boolean, default=True)

    # 기존 코드 호환용 synonym
    id = synonym("user_id")
    username = synonym("user_name")
    hashed_password = synonym("password_hash")

    # 관계 설정 (1:1 user_settings, 1:N flight_requests, 1:N shooting_projects, 1:N flight_guide_logs)
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")
    flight_requests = relationship("FlightRequest", back_populates="user", cascade="all, delete-orphan")
    shooting_projects = relationship("ShootingProject", back_populates="user", cascade="all, delete-orphan")
    flight_guide_logs = relationship("FlightGuideLog", back_populates="user", cascade="all, delete-orphan")


# ==========================================
# 2. user_settings — 사용자 환경 설정 (1:1 관계)
# ==========================================
class UserSetting(Base):
    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    preferred_mode = Column(String(30), default="cinematic")
    notification = Column(Boolean, default=True)
    settings_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 호환성 컬럼 & synonym
    id = synonym("user_id")
    notification_enabled = synonym("notification")
    preferred_camera_mode = synonym("preferred_mode")
    updated_at = synonym("settings_updated_at")
    safety_margin_m = Column(Integer, default=30)
    weather_auto_refresh = Column(Boolean, default=True)

    # 관계 설정
    user = relationship("User", back_populates="settings")


# ==========================================
# 3. flight_requests — 비행 신청 정보 (PC 중심 비행 계획 & 모바일 요약 조회)
# ==========================================
class FlightRequest(Base):
    __tablename__ = "flight_requests"

    flight_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    flight_date = Column(DateTime, default=datetime.utcnow)
    flight_location = Column(String(255), nullable=False)
    flight_status = Column(String(30), default="PENDING")   # READY, PENDING, APPROVED, REJECTED
    flight_plan = Column(JSON, nullable=True)               # 비행 계획 상세 (웨이포인트, 시간, 고도 등)

    # 호환성 컬럼 & synonym
    id = synonym("flight_id")
    location = synonym("flight_location")
    approval_status = synonym("flight_status")
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

    # 관계 설정
    user = relationship("User", back_populates="flight_requests")
    projects = relationship("ShootingProject", back_populates="flight_request")
    guide_logs = relationship("FlightGuideLog", back_populates="flight_request")


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

    project_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    flight_id = Column(Integer, ForeignKey("flight_requests.flight_id"), nullable=True)

    project_name = Column(String(100), nullable=False)
    shooting_purpose = Column(String(100), nullable=True)
    shooting_location = Column(String(255), nullable=True)
    planned_time = Column(DateTime, nullable=True, default=datetime.utcnow)
    composition_type = Column(String(50), nullable=True)

    analysis_result = Column(JSON, nullable=True)           # 최종 AI 분석 결과 상세
    detected_scene = Column(String(100), nullable=True)     # 인식한 촬영 장면
    recommended_composition = Column(String(100), nullable=True) # AI 추천 구도
    achieved_rate = Column(Float, nullable=True)            # 최종 구도 이행률 (%) - DECIMAL(5,2)
    shooting_duration = Column(Integer, nullable=True)      # 실제 촬영 시간(초)
    result_file_url = Column(String(500), nullable=True)    # 촬영 결과물 저장 경로

    created_at = Column(DateTime, default=datetime.utcnow)
    analysis_completed_at = Column(DateTime, nullable=True) # 분석 완료 일시

    # 호환성 컬럼 & synonym
    id = synonym("project_id")
    flight_request_id = synonym("flight_id")
    title = synonym("project_name")
    place_name = synonym("shooting_location")
    scene_intent = synonym("shooting_purpose")
    recommended_mode = synonym("recommended_composition")
    status = Column(String(30), default="CREATED")          # CREATED, ANALYZING, COMPLETED, FAILED
    project_code = Column(String(50), unique=True, index=True, nullable=True)
    project_token = Column(String(512), nullable=True)
    latitude = Column(Float, default=37.5284)
    longitude = Column(Float, default=126.9328)
    target_date = Column(String(30), nullable=True, default="2026-10-24")
    target_time = Column(String(50), nullable=True, default="14:00 ~ 16:00")
    recommended_shutter = Column(String(50), default="1/50s")
    recommended_nd_filter = Column(String(50), default="ND16")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계 설정
    user = relationship("User", back_populates="shooting_projects")
    flight_request = relationship("FlightRequest", back_populates="projects")


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
# 기존 shooting_analyses 통합에 따른 호환용 별칭
# ==========================================
ShootingAnalysis = ShootingProject
