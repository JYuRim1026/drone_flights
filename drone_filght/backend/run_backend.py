"""
드론 비행 안전 & 시네마틱 촬영 계획 지원 시스템 - FastAPI 백엔드 실행 스크립트
실행 방법: python run_backend.py
Swagger 문서: http://localhost:8000/docs
"""
import sys
import os
from pathlib import Path

# Add backend directory and parent directory to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for p in [str(CURRENT_DIR), str(PARENT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("🛰️ 드론 비행 안전 & 촬영 지원 통합 백엔드 서버를 시작합니다.")
    print("👉 PC 웹 클라이언트 : http://localhost:5500/pc.html")
    print("👉 모바일 웹 배포 : https://chimerical-trifle-7e9011.netlify.app")
    print("👉 Swagger API 문서 : http://localhost:8000/docs")
    print("👉 대화형 Redoc 문서 : http://localhost:8000/redoc")
    print("=" * 60)
    # Check importable app module
    app_module = "main:app"
    try:
        import backend.main
        app_module = "backend.main:app"
    except ImportError:
        pass
    uvicorn.run(app_module, host="0.0.0.0", port=8000, reload=True)
