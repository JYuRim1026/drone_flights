from backend.external.cache import external_cache, TTLCache
from backend.external.weather_client import weather_client, WeatherClient, WeatherAPIError
from backend.external.vworld_client import vworld_client, VWorldClient
from backend.external.airspace_client import airspace_client, AirspaceClient
from backend.external.astronomy_client import astronomy_client, AstronomyClient
from backend.external.gemini_client import gemini_client, GeminiClient
from backend.external.unified_manager import external_manager, ExternalDataManager

__all__ = [
    "external_cache",
    "TTLCache",
    "weather_client",
    "WeatherClient",
    "WeatherAPIError",
    "vworld_client",
    "VWorldClient",
    "airspace_client",
    "AirspaceClient",
    "astronomy_client",
    "AstronomyClient",
    "gemini_client",
    "GeminiClient",
    "external_manager",
    "ExternalDataManager"
]
