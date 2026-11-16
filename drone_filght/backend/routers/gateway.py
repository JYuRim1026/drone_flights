import re
import urllib.parse
from fastapi import APIRouter, Request, Query, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional

from backend.config import settings

router = APIRouter(tags=["스마트 단일 URL 기기 라우터 (Smart Device Gateway)"])

# 모바일 브라우저 식별 정규식 패턴
MOBILE_REGEX = re.compile(
    r"android|iphone|ipad|ipod|mobile|blackberry|iemobile|opera mini|webos|windows phone",
    re.IGNORECASE
)


def detect_is_mobile(user_agent: str) -> bool:
    """User-Agent 문자열을 정규식으로 분석하여 모바일/태블릿 여부를 판별합니다."""
    if not user_agent:
        return False
    return bool(MOBILE_REGEX.search(user_agent))


def build_redirect_url(
    base_url: str,
    project_code: Optional[str] = None,
    token: Optional[str] = None,
    extra_params: Optional[dict] = None
) -> str:
    """쿼리 파라미터(project_code, token 등)를 안전하게 인코딩하여 붙입니다."""
    params = {}
    if project_code:
        params["project_code"] = project_code
    if token:
        params["token"] = token
    if extra_params:
        params.update(extra_params)

    if not params:
        return base_url

    separator = "&" if "?" in base_url else "?"
    query_string = urllib.parse.urlencode(params)
    return f"{base_url}{separator}{query_string}"


@router.get(
    "/app",
    summary="1. [단일 대표 URL] 스마트 기기 자동 판별 리다이렉트 진입점"
)
@router.get(
    "/launch",
    summary="[별칭] 스마트 기기 자동 판별 리다이렉트"
)
def smart_app_gateway(
    request: Request,
    mode: Optional[str] = Query(None, description="강제 모드 지정 ('pc' 또는 'mobile')"),
    project_code: Optional[str] = Query(None, description="촬영 프로젝트 고유 코드 (예: DRONE_001)"),
    token: Optional[str] = Query(None, description="모바일 QR 접속 암호화 서명 보안 토큰"),
    page: Optional[str] = Query("camera", description="모바일 접속 대상 페이지 ('camera' 또는 'index')")
):
    """
    [핵심 기능: 하나의 URL로 PC와 모바일 화면 자동 분기]
    사용자가 단 하나의 URL(`http://서버주소/app`)로 접속하면,
    서버가 접속 기기(User-Agent)를 초고속으로 판별하여:
    - 📱 스마트폰/태블릿 ➔ 모바일 웹(Netlify camera.html / index.html)으로 자동 이동
    - 💻 PC/노트북 ➔ PC 관제 대시보드(Streamlit / :8501)로 자동 이동
    """
    user_agent = request.headers.get("user-agent", "")
    is_mobile = detect_is_mobile(user_agent)

    # 파라미터 정규화 (FastAPI Query 기본 객체 처리)
    mode_str = mode if isinstance(mode, str) else None
    code_str = project_code if isinstance(project_code, str) else None
    token_str = token if isinstance(token, str) else None
    page_str = page if isinstance(page, str) else "camera"

    # 강제 모드 파라미터(?mode=pc 또는 ?mode=mobile)가 있으면 우선 적용
    if mode_str == "mobile":
        is_mobile = True
    elif mode_str == "pc":
        is_mobile = False

    if is_mobile:
        target_path = "/camera.html" if page_str == "camera" else "/index.html"
        mobile_base = f"{settings.MOBILE_WEB_URL.rstrip('/')}{target_path}"
        final_url = build_redirect_url(mobile_base, project_code=code_str, token=token_str)
    else:
        pc_base = settings.PC_WEB_URL.rstrip("/")
        final_url = build_redirect_url(pc_base, project_code=code_str, token=token_str)

    return RedirectResponse(url=final_url, status_code=307)


@router.get(
    "/app/select",
    response_class=HTMLResponse,
    summary="2. [시연용 브릿지 UI] PC/모바일 수동 선택 및 카운트다운 자동 이동 화면"
)
def device_selection_page(
    request: Request,
    project_code: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    발표나 시연 시 양쪽 화면을 직접 비교하거나 원하는 화면을 선택할 수 있는
    사이버펑크 드론 테마의 고급 브릿지 랜딩 페이지를 제공합니다.
    """
    user_agent = request.headers.get("user-agent", "")
    is_mobile = detect_is_mobile(user_agent)
    detected_device = "📱 스마트폰 / 모바일 기기" if is_mobile else "💻 PC / 데스크톱 브라우저"

    code_str = project_code if isinstance(project_code, str) else None
    token_str = token if isinstance(token, str) else None

    pc_url = build_redirect_url(f"{settings.PC_WEB_URL.rstrip('/')}", project_code=code_str, token=token_str)
    mob_url = build_redirect_url(f"{settings.MOBILE_WEB_URL.rstrip('/')}/camera.html", project_code=code_str, token=token_str)
    auto_url = mob_url if is_mobile else pc_url

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SkyCommand Gateway - 접속 기기 자동 감지</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{
            background: linear-gradient(135deg, #090e17 0%, #0d1b2a 50%, #1b263b 100%);
            color: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 40px;
            max-width: 520px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        }}
        .logo {{ font-size: 48px; margin-bottom: 12px; }}
        h1 {{ font-size: 24px; font-weight: 700; color: #48cae4; margin-bottom: 8px; }}
        p.desc {{ font-size: 14px; color: #94a3b8; margin-bottom: 24px; }}
        .badge {{
            display: inline-block;
            background: rgba(72, 202, 228, 0.15);
            border: 1px solid #48cae4;
            color: #90e0ef;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 24px;
        }}
        .btn-group {{ display: flex; flex-direction: column; gap: 12px; }}
        .btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 16px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: all 0.2s ease;
        }}
        .btn-pc {{
            background: linear-gradient(90deg, #0077b6, #0096c7);
            color: #ffffff;
        }}
        .btn-pc:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0, 119, 182, 0.4); }}
        .btn-mob {{
            background: linear-gradient(90deg, #059669, #10b981);
            color: #ffffff;
        }}
        .btn-mob:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(16, 185, 129, 0.4); }}
        .countdown {{
            margin-top: 24px;
            font-size: 13px;
            color: #64748b;
        }}
        .countdown span {{ color: #48cae4; font-weight: 700; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🛸</div>
        <h1>SkyCommand 스마트 라우터</h1>
        <p class="desc">하나의 대표 URL로 PC 웹과 모바일 웹을 기기에 맞게 분기합니다.</p>
        
        <div class="badge">감지된 기기: {detected_device}</div>

        <div class="btn-group">
            <a href="{pc_url}" class="btn btn-pc">
                <span>💻</span> PC 관제 및 비행승인 대시보드
            </a>
            <a href="{mob_url}" class="btn btn-mob">
                <span>📱</span> 모바일 현장 카메라 촬영 웹
            </a>
        </div>

        <div class="countdown">
            <span id="timer">3</span>초 후 감지된 기기 최적화 화면으로 자동 이동합니다...
        </div>
    </div>

    <script>
        let timeLeft = 3;
        const targetUrl = "{auto_url}";
        const timerEl = document.getElementById("timer");

        const countdownInterval = setInterval(() => {{
            timeLeft--;
            if (timerEl) timerEl.textContent = timeLeft;
            if (timeLeft <= 0) {{
                clearInterval(countdownInterval);
                window.location.href = targetUrl;
            }}
        }}, 1000);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get(
    "/api/gateway/detect",
    summary="3. [진단 API] 접속 기기 및 리다이렉트 대상 진단"
)
def check_device_detection(
    request: Request,
    mode: Optional[str] = Query(None)
):
    """
    현재 접속한 클라이언트의 User-Agent를 분석한 기기 진단 결과를 JSON으로 반환합니다.
    """
    user_agent = request.headers.get("user-agent", "")
    is_mobile = detect_is_mobile(user_agent)
    if mode == "mobile":
        is_mobile = True
    elif mode == "pc":
        is_mobile = False

    return {
        "user_agent": user_agent,
        "is_mobile": is_mobile,
        "device_type": "mobile" if is_mobile else "pc",
        "redirect_target": settings.MOBILE_WEB_URL if is_mobile else settings.PC_WEB_URL,
        "pc_web_url": settings.PC_WEB_URL,
        "mobile_web_url": settings.MOBILE_WEB_URL
    }
