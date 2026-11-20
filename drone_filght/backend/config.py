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
    _ORIGINAL_LOCAL_DB = os.path.join(_BASE_DIR, "sky_command.db")
    _DEMO_DB = os.path.join(_BASE_DIR, "sky_command_demo.db")
    
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

    @staticmethod
    def _resolve_sqlite_db(is_serverless: bool, demo_db: str, original_db: str) -> str:
        # If an external DATABASE_URL (e.g. postgresql:// or mysql://) is explicitly specified, use it
        env_url = os.getenv("DATABASE_URL")
        if env_url and not env_url.startswith("sqlite"):
            return ""

        import sqlite3
        import shutil
        import tempfile

        # Select source DB template:
        # In Serverless (Vercel): sky_command_demo.db is committed and preferred
        # In Local: sky_command.db (original) is preferred if present, falling back to sky_command_demo.db
        source_template = None
        if is_serverless:
            if os.path.exists(demo_db):
                source_template = demo_db
            elif os.path.exists(original_db):
                source_template = original_db
        else:
            if os.path.exists(original_db):
                source_template = original_db
            elif os.path.exists(demo_db):
                source_template = demo_db

        if not source_template:
            raise RuntimeError(
                f"[DB INIT ERROR] 데이터베이스 템플릿 파일이 존재하지 않습니다. "
                f"({demo_db} 및 {original_db} 모두 없음). "
                f"빈 DB가 비정상 생성되어 서버가 오류 상태로 실행되는 것을 방지하기 위해 중단합니다."
            )

        # Validate template integrity & required tables before copying
        try:
            with sqlite3.connect(source_template) as _conn:
                _integ = _conn.execute("PRAGMA integrity_check;").fetchone()
                if not _integ or _integ[0] != "ok":
                    raise RuntimeError(f"DB 템플릿 무결성 검사 실패: {_integ}")
                _u_tbl = _conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';"
                ).fetchone()[0]
                if _u_tbl == 0:
                    raise RuntimeError(f"DB 템플릿 내 필수 users 테이블이 없습니다: {source_template}")
        except Exception as _e:
            raise RuntimeError(f"데이터베이스 무결성 검증 실패 ({source_template}): {_e}")

        if is_serverless:
            tmp_db = os.path.join(tempfile.gettempdir(), "sky_command.db").replace("\\", "/")
            needs_copy = True
            if os.path.exists(tmp_db) and os.path.getsize(tmp_db) > 0:
                try:
                    with sqlite3.connect(tmp_db) as _chk:
                        if _chk.execute("PRAGMA integrity_check;").fetchone()[0] == "ok":
                            _u_cnt = _chk.execute(
                                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';"
                            ).fetchone()[0]
                            if _u_cnt > 0:
                                needs_copy = False
                except Exception:
                    needs_copy = True

            if needs_copy:
                try:
                    shutil.copy2(source_template, tmp_db)
                    print(f"[DB INIT] Serverless: Copied template {source_template} -> {tmp_db}")
                except Exception as _copy_err:
                    raise RuntimeError(f"Serverless /tmp DB 복사 실패: {_copy_err}")
            return tmp_db
        else:
            return source_template.replace("\\", "/")

    _DEFAULT_DB: str = _resolve_sqlite_db.__func__(IS_SERVERLESS, _DEMO_DB, _ORIGINAL_LOCAL_DB)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}" if _DEFAULT_DB else "")
    
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
