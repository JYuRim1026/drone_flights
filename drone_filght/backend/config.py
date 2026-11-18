import os
from typing import List
from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH, override=True)
load_dotenv()

class Settings:
    PROJECT_NAME: str = "SkyCommand & Nalyeo-Deuryeo Integrated Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Database: SQLite for local out-of-the-box demo, PostgreSQL ready
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DEFAULT_DB = os.path.join(_BASE_DIR, "sky_command.db").replace("\\", "/")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
    
    # JWT & Security Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "skycommand_super_secret_jwt_key_2026_!@#$%^&*")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) # 24시간
    PROJECT_TOKEN_EXPIRE_HOURS: int = int(os.getenv("PROJECT_TOKEN_EXPIRE_HOURS", "48"))     # 48시간
    
    # External API Keys & Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_ENDPOINT: str = os.getenv(
        "GEMINI_API_ENDPOINT",
        "https://generativelanguage.googleapis.com/v1beta/models",
    ).rstrip("/")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_FALLBACK_MODELS = (
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    )
    KMA_API_ENDPOINT: str = os.getenv(
        "KMA_API_ENDPOINT",
        "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0",
    ).rstrip("/")
    KMA_API_KEY: str = os.getenv("KMA_API_KEY", "")
    VWORLD_API_KEY: str = os.getenv("VWORLD_API_KEY", "")
    
    # External API Timeout & Cache Policies
    EXTERNAL_API_TIMEOUT: float = 2.5
    KMA_API_TIMEOUT: float = 6.0
    GEMINI_API_TIMEOUT: float = 10.0
    CACHE_DEFAULT_TTL_WEATHER: int = 600      # 10분
    CACHE_DEFAULT_TTL_GEOCODING: int = 86400  # 24시간
    CACHE_DEFAULT_TTL_ASTRONOMY: int = 86400  # 24시간
    CACHE_DEFAULT_TTL_AIRSPACE: int = 3600    # 1시간
    
    # Frontend Web App URLs for Smart Routing & QR Deep Linking
    MOBILE_WEB_URL: str = os.getenv("MOBILE_WEB_URL", "https://chimerical-trifle-7e9011.netlify.app")
    PC_WEB_URL: str = os.getenv("PC_WEB_URL", "https://chimerical-trifle-7e9011.netlify.app/pc.html")
    
    # CORS Origins (PC Web localhost, Mobile Web Netlify, etc.)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",       # Local Web Client
        "http://localhost:5500",       # Local Web Server
        "http://localhost:8000",       # Backend Swagger
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8000",
        "https://chimerical-trifle-7e9011.netlify.app", # Netlify Mobile Web
        "*"
    ]

settings = Settings()
