import os
from typing import List
from dotenv import load_dotenv

_CURR_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ENV_PATHS = [
    os.path.join(_CURR_DIR, ".env"),                                     # drone_filght/backend/.env
    os.path.join(os.path.dirname(_CURR_DIR), ".env"),                    # drone_filght/.env
    os.path.join(os.path.dirname(os.path.dirname(_CURR_DIR)), ".env"),   # project root .env
    os.path.join(os.getcwd(), ".env")                                    # current working directory .env
]

for _p in _CANDIDATE_ENV_PATHS:
    if os.path.isfile(_p):
        load_dotenv(_p, override=False)

# If KMA_API_KEY or GEMINI_API_KEY is empty, reload with override=True to avoid shadowing by empty parent env vars
if not (os.getenv("KMA_API_KEY") or "").strip() or not (os.getenv("GEMINI_API_KEY") or "").strip():
    for _p in _CANDIDATE_ENV_PATHS:
        if os.path.isfile(_p):
            load_dotenv(_p, override=True)
            if (os.getenv("KMA_API_KEY") or "").strip() and (os.getenv("GEMINI_API_KEY") or "").strip():
                break

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
            if os.path.exists(demo_db):
                source_template = demo_db
            elif os.path.exists(original_db):
                source_template = original_db

        # Validate template integrity & required tables before copying (if on disk)
        if source_template and os.path.exists(source_template):
            try:
                with sqlite3.connect(source_template) as _conn:
                    _integ = _conn.execute("PRAGMA integrity_check;").fetchone()
                    if not _integ or _integ[0] != "ok":
                        source_template = None
            except Exception:
                source_template = None

        if is_serverless:
            tmp_db = os.path.join(tempfile.gettempdir(), "sky_command.db").replace("\\", "/")
            needs_copy = True
            if os.path.exists(tmp_db) and os.path.getsize(tmp_db) > 0:
                try:
                    chk_conn = sqlite3.connect(tmp_db)
                    try:
                        if chk_conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok":
                            _u_cnt = chk_conn.execute(
                                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';"
                            ).fetchone()[0]
                            if _u_cnt > 0:
                                needs_copy = False
                    finally:
                        chk_conn.close()
                except Exception:
                    needs_copy = True

            if needs_copy:
                copied = False
                # 1. Try file copy if template exists on disk
                if source_template and os.path.exists(source_template):
                    try:
                        shutil.copy2(source_template, tmp_db)
                        copied = True
                        print(f"[DB INIT] Serverless: Copied template {source_template} -> {tmp_db}")
                    except Exception:
                        copied = False

                # 2. If disk template was omitted by Vercel packager, unpack from embedded Python blob
                if not copied:
                    try:
                        try:
                            from backend.demo_db_blob import restore_demo_db_to
                        except ImportError:
                            from demo_db_blob import restore_demo_db_to
                        if restore_demo_db_to(tmp_db):
                            print(f"[DB INIT] Serverless: Successfully restored DB from embedded Python blob -> {tmp_db}")
                            copied = True
                    except Exception as _blob_err:
                        print(f"[DB INIT WARNING] Blob restore failed: {_blob_err}")

                if not copied and not os.path.exists(tmp_db):
                    raise RuntimeError("Serverless /tmp DB 복제 및 복원에 실패했습니다.")
            return tmp_db
        else:
            if source_template:
                return source_template.replace("\\", "/")
            # Local fallback: restore demo_db from blob if missing
            try:
                try:
                    from backend.demo_db_blob import restore_demo_db_to
                except ImportError:
                    from demo_db_blob import restore_demo_db_to
                restore_demo_db_to(demo_db)
                return demo_db.replace("\\", "/")
            except Exception:
                return demo_db.replace("\\", "/")

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
    @property
    def KMA_API_KEY(self) -> str:
        key = (os.getenv("KMA_API_KEY") or "").strip()
        if not key:
            for p in _CANDIDATE_ENV_PATHS:
                if os.path.isfile(p):
                    load_dotenv(p, override=True)
                    key = (os.getenv("KMA_API_KEY") or "").strip()
                    if key:
                        break
        return key

    @KMA_API_KEY.setter
    def KMA_API_KEY(self, val: str):
        if val is not None:
            os.environ["KMA_API_KEY"] = str(val).strip()

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
