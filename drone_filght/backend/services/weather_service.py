import sys
from pathlib import Path

_DRONE_FILGHT_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _DRONE_FILGHT_DIR not in sys.path:
    sys.path.insert(0, _DRONE_FILGHT_DIR)

from backend.external.weather_client import weather_client


def get_weather(lat, lon, date_str=None, time_str=None):
    """
    기상청 단기예보 조회서비스 2.0(VilageFcstInfoService_2.0)을 호출하여
    지정된 위도·경도의 실시간 관측 기상 데이터를 반환합니다. (시뮬레이션 폴백 없음)
    """
    data = weather_client.get_weather(float(lat), float(lon), location_name="조회 위치")
    return {
        "source": data["source"],
        "temp": data["temperature_c"],
        "wind_speed": data["wind_speed_ms"],
        "wind_gust": data["wind_gust_ms"],
        "wind_direction": data["wind_direction_text"],
        "weather_desc": data["weather_condition"],
        "weather_icon": data["weather_icon"],
        "rain": data["precipitation_mm_h"],
        "humidity": data["humidity_percent"],
        "visibility_km": data["visibility_km"],
        "cloudiness": data["cloudiness_percent"],
        "observed_at": data["observed_at"],
        "hourly_forecast": data.get("hourly_forecast", []),
    }
