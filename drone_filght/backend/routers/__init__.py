from backend.routers.pc import router as pc_router
from backend.routers.mobile import router as mobile_router
from backend.routers.common import router as common_router
from backend.routers.external import router as external_router
from backend.routers.ai import router as ai_router
from backend.routers.safety import router as safety_router
from backend.routers.auth import router as auth_router
from backend.routers.gateway import router as gateway_router
from backend.routers.drones import router as drones_router
from backend.routers.community import router as community_router
from backend.routers.case_study import router as case_study_router

__all__ = [
    "pc_router",
    "mobile_router",
    "common_router",
    "external_router",
    "ai_router",
    "safety_router",
    "auth_router",
    "gateway_router",
    "drones_router",
    "community_router",
    "case_study_router"
]
