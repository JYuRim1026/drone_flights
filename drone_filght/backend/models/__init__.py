from backend.models.models import (
    User,
    UserSetting,
    FlightRequest,
    AirspaceZone,
    ShootingProject,
    FlightGuideLog,
    RegisteredDrone
)

# 기존 shooting_analyses 통합에 따른 호환용 별칭
ShootingAnalysis = ShootingProject

__all__ = [
    "User",
    "UserSetting",
    "FlightRequest",
    "AirspaceZone",
    "ShootingProject",
    "FlightGuideLog",
    "RegisteredDrone",
    "ShootingAnalysis"
]
