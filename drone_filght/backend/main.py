import sys
import os
from pathlib import Path

# Vercel Serverless 및 다중 환경 sys.path 및 backend 패키지 자동 보정
_CUR_DIR = Path(__file__).resolve().parent
_PARENT_DIR = _CUR_DIR.parent
for _p in [str(_PARENT_DIR), str(_CUR_DIR), str(_PARENT_DIR.parent)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "backend" not in sys.modules:
    try:
        import backend
    except ModuleNotFoundError:
        import types
        _pkg = types.ModuleType("backend")
        _pkg.__path__ = [str(_CUR_DIR)]
        sys.modules["backend"] = _pkg

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.config import settings
from backend.database import engine, Base, SessionLocal
from backend.models import models
from backend.routers import (
    pc_router,
    mobile_router,
    common_router,
    external_router,
    ai_router,
    safety_router,
    sync_router,
    auth_router,
    gateway_router,
    drones_router,
    community_router
)
from backend.services.auth_service import auth_service

def seed_initial_data():
    """Initial Seed Data for Demo & Report Testing"""
    db = SessionLocal()
    try:
        # 0. Seed Default Accounts (pilot, crew, admin, drone_pilot with bcrypt)
        auth_service.init_default_users(db)

        # 1. Seed User & Setting
        user = db.query(models.User).filter(models.User.username == "drone_pilot").first()
        if not user:
            user = models.User(
                username="drone_pilot",
                email="pilot@skycommand.kr",
                full_name="홍길동 조종사",
                phone="010-1234-5678",
                drone_model="DJI Mini 4 Pro",
                drone_weight_g=249
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            setting = models.UserSetting(
                user_id=user.id,
                safety_margin_m=30,
                notification_enabled=True,
                weather_auto_refresh=True,
                preferred_camera_mode="cinematic"
            )
            db.add(setting)

        # 2. Seed Flight Request (A: PC)
        flight = db.query(models.FlightRequest).first()
        if not flight:
            flight = models.FlightRequest(
                user_id=user.id,
                location="서울 여의도 한강공원",
                latitude=37.5284,
                longitude=126.9328,
                start_date="2026-10-24",
                end_date="2026-10-24",
                flight_time="14:00 ~ 16:00",
                drone_weight="249g (초경량)",
                has_camera=True,
                purpose="경관 사진 및 영상 촬영",
                altitude="120m",
                approval_status="APPROVED",
                notes="원스톱 비행승인 완료"
            )
            db.add(flight)
            db.commit()
            db.refresh(flight)

        # 3. Seed Shooting Project (C: Shared PC <-> Mobile)
        project = db.query(models.ShootingProject).first()
        if not project:
            project = models.ShootingProject(
                project_code="DRONE_001",
                user_id=user.id,
                flight_request_id=flight.id if flight else None,
                title="한강 도시 풍경 촬영",
                place_name="서울 한강공원",
                target_date="2026년 10월 24일",
                target_time="오후 14:00 ~ 16:00",
                scene_intent="한강을 따라 이동하며 도시의 넓은 풍경과 석양 분위기를 시네마틱하게 담고 싶어요.",
                latitude=37.5284,
                longitude=126.9328,
                recommended_mode="패럴랙스 리빌 & 선셋 아크",
                recommended_shutter="1/50s",
                recommended_nd_filter="ND16",
                status="CREATED"
            )
            db.add(project)
            db.commit()
        elif not project.project_code:
            project.project_code = "DRONE_001"
            db.commit()

        # 4. Seed Major Airspace Zones (B: PC)
        if db.query(models.AirspaceZone).count() == 0:
            zones = [
                models.AirspaceZone(
                    zone_name="서울 관제권 (CTR)",
                    zone_type="CTR",
                    latitude=37.5284,
                    longitude=126.9328,
                    radius_meter=1000,
                    altitude_limit_m=150,
                    approval_required=True,
                    contact_agency="서울지방항공청 항공운항과",
                    contact_phone="032-740-2114",
                    description="공항 관제구역 내 원스톱 비행 승인이 요구됩니다."
                ),
                models.AirspaceZone(
                    zone_name="P-73A 비행금지구역",
                    zone_type="PROHIBITED",
                    latitude=37.5326,
                    longitude=126.9810,
                    radius_meter=3700,
                    altitude_limit_m=150,
                    approval_required=True,
                    contact_agency="수도방위사령부 화력처",
                    contact_phone="02-524-3401",
                    description="국가중요시설 보호구역으로 사전 특별허가 없이 비행이 금지됩니다."
                ),
                models.AirspaceZone(
                    zone_name="비관제공역 (G공역)",
                    zone_type="UNCONTROLLED",
                    latitude=36.1268,
                    longitude=128.1852,
                    radius_meter=1000,
                    altitude_limit_m=150,
                    approval_required=False,
                    contact_agency="한국교통안전공단",
                    contact_phone="1577-0333",
                    description="250g 미만 기체의 경우 고도 150m 이하 자율 비행이 가능합니다."
                )
            ]
            db.add_all(zones)
            db.commit()

    except Exception as _seed_err:
        print(f"Notice: Seed initial data warning (deferred): {_seed_err}")
    finally:
        db.close()

# Initialize Database Tables & Seed data on module load (Ensures tables & users exist in serverless)
try:
    Base.metadata.create_all(bind=engine)
    seed_initial_data()
except Exception as _init_err:
    print(f"Notice: Immediate DB initialization warning: {_init_err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Seed Data
    seed_initial_data()
    yield
    # Shutdown

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
## 🛸 스카이 커맨드 (Sky Command) & 날려드려 통합 백엔드 API
하나의 중앙 백엔드와 데이터베이스를 바탕으로 **PC 웹(행정·공역진단)**과 **모바일 웹(현장 카메라·구도가이드)**을 분리 지원하는 **BFF(Backend For Frontend) 멀티 클라이언트 API**입니다.

### 📌 데이터 영역 매핑 구조
- **A 영역 (비행 행정 정보)**: `/api/pc/flights` (PC 전용)
- **B 영역 (공역 규제 정보)**: `/api/pc/airspace` (PC 전용)
- **C 영역 (촬영 프로젝트 정보)**: `/api/common/projects`, `/api/mobile/projects` (PC ↔ 모바일 공유 핵심 데이터)
- **D 영역 (실시간 카메라 분석)**: `/api/mobile/analyze`, `/api/mobile/recommendations` (모바일 전용)
- **E 영역 (공통 환경 및 날씨)**: `/api/common/weather`, `/api/common/settings` (공통)
    """,
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler (JSON fail-safe so frontend never sees raw HTML or broken JSON)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    err_type = type(exc).__name__
    err_msg = str(exc)
    print(f"[FASTAPI GLOBAL ERROR 500] {request.method} {request.url.path}: {err_type} - {err_msg}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"백엔드 서버 내부 오류 ({err_type}): {err_msg}",
            "type": err_type,
            "path": request.url.path
        }
    )

# Include Routers with multiple prefixes for maximum frontend & proxy compatibility
_api_routers = [
    pc_router,
    mobile_router,
    common_router,
    external_router,
    ai_router,
    safety_router,
    sync_router,
    auth_router,
    drones_router,
    community_router
]
for _r in _api_routers:
    app.include_router(_r, prefix="/api")       # Standard /api/auth/login
    app.include_router(_r, prefix="/api/v1")    # Mobile /api/v1/auth/login
    app.include_router(_r)                      # Fallback /auth/login (if proxy strips /api)

app.include_router(gateway_router)  # 단일 대표 URL: /app, /launch, /app/select

@app.get("/", tags=["System Health"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "smart_entry_url": "/app",
        "smart_select_url": "/app/select",
        "endpoints": {
            "auth_api": f"{settings.API_V1_STR}/auth",
            "pc_api": f"{settings.API_V1_STR}/pc",
            "mobile_api": f"{settings.API_V1_STR}/mobile",
            "common_api": f"{settings.API_V1_STR}/common",
            "external_api": f"{settings.API_V1_STR}/external",
            "ai_api": f"{settings.API_V1_STR}/ai",
            "safety_api": f"{settings.API_V1_STR}/safety",
            "sync_api": f"{settings.API_V1_STR}/sync"
        }
    }

@app.get("/health", tags=["System Health"])
def health():
    return {"status": "healthy"}
