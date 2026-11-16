# -*- coding: utf-8 -*-
"""
스카이 커맨드 & 날려드려 - 로컬 통합 웹 서버 실행 스크립트
실행 방법: python run_web.py [--port 5500] [--with-backend]
"""
import os
import sys

# Ensure immediate unbuffered output
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

import argparse
import json
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import socketserver

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "drone_filght" / "frontend"
BACKEND_BASE_URL = "http://127.0.0.1:8000"


class SPAHandler(SimpleHTTPRequestHandler):
    """
    정적 프론트엔드 서빙, 클린 URL 라우팅 및 /api/* 백엔드 리버스 프록시 핸들러
    /pc -> /pc.html
    /mobile -> /mobile.html
    /camera -> /camera.html
    /api/* -> http://127.0.0.1:8000/api/*
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _is_backend_path(self) -> bool:
        path_only = self.path.split("?", 1)[0]
        return path_only.startswith("/api/") or path_only == "/health"

    def _proxy_to_backend(self, method: str) -> None:
        target_url = f"{BACKEND_BASE_URL}{self.path}"
        content_len = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_len) if content_len > 0 else None

        forward_headers = {}
        for hdr in ("Content-Type", "Authorization", "Accept"):
            val = self.headers.get(hdr)
            if val:
                forward_headers[hdr] = val

        req = urllib.request.Request(
            target_url,
            data=body,
            headers=forward_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json; charset=utf-8"))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as err:
            err_body = err.read()
            self.send_response(err.code)
            self.send_header("Content-Type", err.headers.get("Content-Type", "application/json; charset=utf-8"))
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as exc:
            msg = json.dumps({"detail": f"백엔드 API 서버(8000) 프록시 오류: {exc}"}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self._is_backend_path():
            self._proxy_to_backend("GET")
            return
        # Clean URL mapping
        clean_path = self.path.split('?')[0].rstrip('/')
        if clean_path == "/pc":
            self.path = "/pc.html" + self.path[len(clean_path):]
        elif clean_path == "/mobile":
            self.path = "/mobile.html" + self.path[len(clean_path):]
        elif clean_path == "/camera":
            self.path = "/camera.html" + self.path[len(clean_path):]
        return super().do_GET()

    def do_POST(self):
        if self._is_backend_path():
            self._proxy_to_backend("POST")
            return
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        if self._is_backend_path():
            self._proxy_to_backend("PUT")
            return
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self._is_backend_path():
            self._proxy_to_backend("DELETE")
            return
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        if self._is_backend_path():
            self._proxy_to_backend("OPTIONS")
            return
        self.send_response(204)
        self.end_headers()

def start_backend_process():
    import subprocess
    backend_script = ROOT_DIR / "drone_filght" / "backend" / "run_backend.py"
    if backend_script.exists():
        print(">> FastAPI 백엔드 프로세스를 함께 실행합니다 (http://localhost:8000)...")
        python_bin = sys.executable
        venv_python = ROOT_DIR / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_bin = str(venv_python)
        subprocess.Popen([python_bin, str(backend_script)], cwd=str(ROOT_DIR / "drone_filght"))

def main():
    parser = argparse.ArgumentParser(description="SkyCommand Local Web Server")
    parser.add_argument("--port", type=int, default=5500, help="Web server port (default: 5500)")
    parser.add_argument("--with-backend", action="store_true", help="Launch FastAPI backend together")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    if not FRONTEND_DIR.exists():
        print(f"[ERROR] Frontend directory not found: {FRONTEND_DIR}")
        sys.exit(1)

    if args.with_backend:
        start_backend_process()

    port = args.port
    httpd = None
    # Find free port starting at requested port
    for p in range(port, port + 10):
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", p), SPAHandler)
            port = p
            break
        except OSError:
            try:
                httpd = ThreadingHTTPServer(("127.0.0.1", p), SPAHandler)
                port = p
                break
            except OSError:
                continue

    if httpd is None:
        print(f"[ERROR] 포트 {port}~{port+10}를 바인딩할 수 없습니다.", flush=True)
        sys.exit(1)

    print("=" * 65, flush=True)
    print("🛸 SkyCommand & 날려드려 통합 프론트엔드 웹 서버가 시작되었습니다!", flush=True)
    print(f"👉 통합 포털 (자동 기기 감지) : http://localhost:{port}/", flush=True)
    print(f"👉 💻 PC 웹 관제 모드        : http://localhost:{port}/pc.html", flush=True)
    print(f"👉 📱 모바일 촬영 도우미 모드  : http://localhost:{port}/mobile.html", flush=True)
    print(f"👉 📸 카메라 시네마틱 가이드  : http://localhost:{port}/camera.html", flush=True)
    print(f"👉 📂 서빙 디렉토리           : {FRONTEND_DIR}", flush=True)
    print("=" * 65, flush=True)
    print("서버를 중지하려면 Ctrl+C를 누르세요.\n", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n웹 서버를 안전하게 종료했습니다.")
        httpd.server_close()

if __name__ == "__main__":
    main()
