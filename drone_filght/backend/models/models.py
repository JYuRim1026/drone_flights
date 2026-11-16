from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

# ==========================================
# E. 공통 정보 (Users, User Settings)
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    full_name = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    drone_model = Column(String(50), default="DJI Mini 4 Pro")
    drone_weight_g = Column(Integer, default=249)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(30), default="pilot")          # pilot, crew, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    settings = relationship("UserSetting", back_populates="user", uselist=False)
    flight_requests = relationship("FlightRequest", back_populates="user")
    shooting_projects = relationship("ShootingProject", back_populates="user")


class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    safety_margin_m = Column(Integer, default=30)
    notification_enabled = Column(Boolean, default=True)
    weather_auto_refresh = Column(Boolean, default=True)
    preferred_camera_mode = Column(String(50), default="cinematic")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="settings")


# ==========================================
# A. 비행 정보 (Flight Requests - PC 중심)
# ==========================================
class FlightRequest(Base):
    __tablename__ = "flight_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    location = Column(String(200), nullable=False)        # 비행 장소/주소
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    start_date = Column(String(30), nullable=False)       # 2026-10-24
    end_date = Column(String(30), nullable=False)
    flight_time = Column(String(50), nullable=False)      # 14:00 ~ 16:00
    drone_weight = Column(String(50), nullable=False)     # 249g (초경량)
    has_camera = Column(Boolean, default=True)            # 카메라 탑재
    purpose = Column(String(100), nullable=False)         # 경관 촬영, 프로젝트 등
    altitude = Column(String(30), default="120m")         # 예정 고도
    approval_status = Column(String(20), default="READY") # READY, PENDING, APPROVED
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="flight_requests")
    projects = relationship("ShootingProject", back_populates="flight_request")


# ==========================================
# B. 공역 정보 (Airspace Zones - PC 중심)
# ==========================================
class AirspaceZone(Base):
    __tablename__ = "airspace_zones"

    id = Column(Integer, primary_key=True, index=True)
    zone_name = Column(String(100), index=True, nullable=False) # 서울 관제권 (CTR), P-73 등
    zone_type = Column(String(50), nullable=False)              # CTR, PROHIBITED, RESTRICTED, UNCONTROLLED
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_meter = Column(Integer, default=1000)
    altitude_limit_m = Column(Integer, default=150)
    approval_required = Column(Boolean, default=True)           # 비행승인 필수 여부
    contact_agency = Column(String(100), nullable=True)         # 관할 지방항공청 / 군부대
    contact_phone = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)


# ==========================================
# C. 촬영 프로젝트 (Shooting Projects - PC ↔ 모바일 핵심 공유)
# ==========================================
class ShootingProject(Base):
    __tablename__ = "shooting_projects"

    id = Column(Integer, primary_key=True, index=True)
    project_code = Column(String(50), unique=True, index=True, nullable=True) # e.g. DRONE_001
    project_token = Column(String(512), nullable=True)                         # 암호화 서명된 모바일 접속 보안 토큰
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    flight_request_id = Column(Integer, ForeignKey("flight_requests.id"), nullable=True)
    
    title = Column(String(150), nullable=False)           # 한강 도시 풍경 촬영
    place_name = Column(String(150), nullable=False)      # 서울 한강공원
    latitude = Column(Float, default=37.5284)
    longitude = Column(Float, default=126.9328)
    target_date = Column(String(30), nullable=False)      # 2026-10-24
    target_time = Column(String(50), nullable=False)      # 14:00 ~ 16:00
    scene_intent = Column(Text, nullable=True)            # 일몰과 함께 강변 풍경을 담고 싶어
    recommended_mode = Column(String(100), default="패럴랙스 리빌 & 선셋 아크")
    recommended_shutter = Column(String(50), default="1/50s")
    recommended_nd_filter = Column(String(50), default="ND16")
    status = Column(String(30), default="CREATED")        # CREATED, ANALYZING, COMPLETED, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="shooting_projects")
    flight_request = relationship("FlightRequest", back_populates="projects")
    analyses = relationship("ShootingAnalysis", back_populates="project", cascade="all, delete-orphan")


# ==========================================
# D. 촬영 분석 (Shooting Analyses - 모바일 중심)
# ==========================================
class ShootingAnalysis(Base):
    __tablename__ = "shooting_analyses"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("shooting_projects.id"), nullable=False)
    
    frame_score = Column(Integer, default=80)             # 구도 일치도 (0~100)
    offset_x = Column(Float, default=0.0)                 # 미세 화면 보정 X (-1.0 ~ 1.0)
    offset_y = Column(Float, default=0.0)                 # 미세 화면 보정 Y (-1.0 ~ 1.0)
    guide_direction = Column(String(20), default="none")  # up, down, left, right, none
    guide_message = Column(String(255), nullable=True)    # AI 안내 멘트
    stick_throttle = Column(String(50), nullable=True)    # 스로틀 스틱 값
    stick_yaw = Column(String(50), nullable=True)
    stick_pitch = Column(String(50), nullable=True)
    stick_roll = Column(String(50), nullable=True)
    recorded_video_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    project = relationship("ShootingProject", back_populates="analyses")
