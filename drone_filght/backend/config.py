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
    _SOURCE_DB = os.path.join(_BASE_DIR, "sky_command.db")
    
    # In Vercel serverless / Lambda environment, the app bundle is strictly read-only.
    # We dynamically test environment flags and directory writability.
    # When read-only or in serverless, we automatically use the system temp directory.
    @staticmethod
    def _is_serverless_env(base_dir: str) -> bool:
        # 1. Standard serverless environment flags
        serverless_flags = [
            "VERCEL", "VERCEL_ENV", "NOW_REGION",
            "AWS_LAMBDA_FUNCTION_NAME", "LAMBDA_TASK_ROOT"
        ]
        if any(os.getenv(k) for k in serverless_flags):
            return True
        # 2. Typical serverless execution path on AWS / Vercel
        if os.path.exists("/var/task"):
            return True
        # 3. Direct write permission test on current directory
        try:
            test_file = os.path.join(base_dir, ".fs_write_test_tmp")
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            return False
        except Exception:
            return True

    IS_SERVERLESS: bool = _is_serverless_env(_BASE_DIR)

    if IS_SERVERLESS:
        import tempfile
        import shutil
        _TMP_DIR = tempfile.gettempdir()
        _TMP_DB = os.path.join(_TMP_DIR, "sky_command.db").replace("\\", "/")
        try:
            if os.path.exists(_SOURCE_DB) and not os.path.exists(_TMP_DB):
                shutil.copy2(_SOURCE_DB, _TMP_DB)
        except Exception:
            pass
        _DEFAULT_DB = _TMP_DB
    else:
        _DEFAULT_DB = _SOURCE_DB.replace("\\", "/")

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
    MOBILE_WEB_URL: str = os.getenv("MOBILE_WEB_URL", "http://localhost:5500")
    PC_WEB_URL: str = os.getenv("PC_WEB_URL", "http://localhost:5500/pc.html")
    
    # CORS Origins (Local Web Server & Vercel Web Client)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",       # Local Web Client
        "http://localhost:5500",       # Local Web Server
        "http://localhost:8000",       # Backend Swagger
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8000",
        "*"
    ]

settings = Settings()
