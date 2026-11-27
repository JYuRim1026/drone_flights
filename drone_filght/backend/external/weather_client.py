import math
import time
import urllib.parse
import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests

from backend.config import settings
from backend.external.cache import external_cache


KST = timezone(timedelta(hours=9))


class WeatherAPIError(RuntimeError):
    """기상청 실시간 API 호출 또는 응답 파싱 실패 시 발생하는 예외."""


class WeatherClient:
    """
    기상청 단기예보 조회서비스 2.0 (VilageFcstInfoService_2.0) 실시간 연동 클라이언트.
    - getUltraSrtNcst (초단기실황): 현재 기온(T1H), 풍속(WSD), 풍향(VEC), 습도(REH), 1시간 강수량(RN1), 강수형태(PTY)
    - getUltraSrtFcst (초단기예보): 하늘상태(SKY), 낙뢰(LGT), 향후 5시간 시간대별 실측 예보
    - getVilageFcst (단기예보): 강수확률(POP)
    시뮬레이션 폴백 없이 실제 기상청 관측/예보 데이터만 사용합니다.
    """

    DIRECTION_LABELS_16 = [
        "북풍 (N)", "북북동풍 (NNE)", "북동풍 (NE)", "동북동풍 (ENE)",
        "동풍 (E)", "동남동풍 (ESE)", "남동풍 (SE)", "남남동풍 (SSE)",
        "남풍 (S)", "남남서풍 (SSW)", "남서풍 (SW)", "서남서풍 (WSW)",
        "서풍 (W)", "서북서풍 (WNW)", "북서풍 (NW)", "북북서풍 (NNW)",
    ]

    PTY_LABELS = {
        0: None,
        1: "비",
        2: "비/눈",
        3: "눈",
        4: "소나기",
        5: "빗방울",
        6: "빗방울/눈날림",
        7: "눈날림",
    }

    SKY_MAP = {
        1: ("맑음", 10),
        3: ("구름 많음", 55),
        4: ("흐림", 90),
    }

    @classmethod
    def deg_to_16_direction(cls, deg: float) -> str:
        """각도(0~360도)를 16방위 한국어 명칭으로 변환."""
        idx = int((deg + 11.25) / 22.5) % 16
        return cls.DIRECTION_LABELS_16[idx]

    @staticmethod
    def _resolve_service_key(raw_key: str) -> str:
        cleaned = (raw_key or "").strip()
        if not cleaned:
            cleaned = (getattr(settings, "KMA_API_KEY", "") or os.getenv("KMA_API_KEY", "")).strip()
        if not cleaned:
            raise WeatherAPIError("KMA_API_KEY가 .env에 설정되어 있지 않습니다.")
        if "%" in cleaned:
            return urllib.parse.unquote(cleaned)
        return cleaned

    @staticmethod
    def latlon_to_grid(lat: float, lon: float) -> Tuple[int, int]:
        """위경도(WGS84)를 기상청 LCC DFS 5km 격자 좌표(nx, ny)로 변환."""
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            raise WeatherAPIError("유효하지 않은 위도/경도 좌표입니다.")
        if not (31.0 <= lat <= 44.0 and 123.0 <= lon <= 133.0):
            raise WeatherAPIError(
                f"대한민국 기상청 격자 서비스 범위를 벗어난 좌표입니다 (lat={lat}, lon={lon})."
            )

        RE = 6371.00877
        GRID = 5.0
        SLAT1 = 30.0
        SLAT2 = 60.0
        OLON = 126.0
        OLAT = 38.0
        XO = 43.0
        YO = 136.0
        DEGRAD = math.pi / 180.0

        re = RE / GRID
        slat1 = SLAT1 * DEGRAD
        slat2 = SLAT2 * DEGRAD
        olon = OLON * DEGRAD
        olat = OLAT * DEGRAD

        sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
        sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
        sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
        sf = math.pow(sf, sn) * math.cos(slat1) / sn
        ro = math.tan(math.pi * 0.25 + olat * 0.5)
        ro = re * sf / math.pow(ro, sn)

        ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
        ra = re * sf / math.pow(ra, sn)
        theta = lon * DEGRAD - olon
        if theta > math.pi:
            theta -= 2.0 * math.pi
        if theta < -math.pi:
            theta += 2.0 * math.pi
        theta *= sn

        nx = int(math.floor(ra * math.sin(theta) + XO + 0.5))
        ny = int(math.floor(ro - ra * math.cos(theta) + YO + 0.5))
        return nx, ny

    @staticmethod
    def _parse_float(raw: Any, default: Optional[float] = None) -> Optional[float]:
        if raw is None:
            return default
        text = str(raw).strip()
        if not text:
            return default
        try:
            val = float(text)
            if val <= -900.0 or val >= 900.0:
                return default
            return val
        except ValueError:
            return default

    @staticmethod
    def _parse_rain_mm(raw: Any) -> float:
        """기상청 강수량 문자열(강수없음, 1.0mm 미만, 수치)을 mm/h 실수로 변환."""
        if raw is None:
            return 0.0
        text = str(raw).strip()
        if not text or "없음" in text or text == "-":
            return 0.0
        if "미만" in text:
            return 0.5
        if "~" in text:
            text = text.split("~")[0]
        if "이상" in text:
            text = text.replace("이상", "")
        text = text.replace("mm", "").strip()
        try:
            val = float(text)
            return max(0.0, round(val, 1)) if val < 900.0 else 0.0
        except ValueError:
            return 0.0

    @classmethod
    def _derive_visibility_km(cls, pty: int, rain_mm: float, humidity: int, sky: int) -> float:
        """실측 강수·강수형태·상대습도·운량을 기반으로 법정 시계거리(km) 산출."""
        if rain_mm >= 5.0 or pty in (2, 3, 6, 7):
            return 3.5
        if rain_mm > 0.0 or pty in (1, 4, 5):
            return 4.8
        if humidity >= 95:
            return 4.5
        if humidity >= 85:
            return 8.0
        if sky == 4:
            return 12.0
        if sky == 3:
            return 15.0
        return 20.0

    @classmethod
    def _describe_weather(cls, pty: int, sky: int, lgt: float, hour_kst: int) -> Tuple[str, str, int]:
        sky_label, cloudiness = cls.SKY_MAP.get(sky, ("맑음", 10))
        pty_label = cls.PTY_LABELS.get(pty)

        if lgt > 0:
            desc = f"{pty_label or sky_label} (낙뢰 주의)"
            icon = "⛈️"
        elif pty_label:
            desc = f"{pty_label} ({sky_label})"
            if pty in (3, 7):
                icon = "❄️"
            elif pty in (2, 6):
                icon = "🌨️"
            elif pty == 5:
                icon = "🌦️"
            else:
                icon = "🌧️"
        else:
            desc = sky_label
            if sky == 4:
                icon = "☁️"
            elif sky == 3:
                icon = "⛅"
            elif hour_kst >= 19 or hour_kst < 6:
                icon = "🌙"
            elif 17 <= hour_kst < 19:
                icon = "🌇"
            else:
                icon = "☀️"
        return desc, icon, cloudiness

    @classmethod
    def evaluate_flight_safety(
        cls,
        wind_speed: float,
        wind_gust: float,
        rain: float,
        visibility_km: float,
        lightning: float = 0.0,
    ) -> Tuple[bool, str, List[str]]:
        """드론 비행 안전 규정 기반 적합도 종합 진단."""
        risks: List[str] = []
        is_safe = True

        if lightning > 0:
            is_safe = False
            risks.append("낙뢰 관측/예보: 비행 중 기체 피뢰 및 통신 두절 위험 (즉시 비행 중지)")

        if wind_speed >= 10.0 or wind_gust >= 13.0:
            is_safe = False
            risks.append(
                f"강풍 경보: 실시간 풍속 {wind_speed}m/s (추정 돌풍 {wind_gust}m/s)로 기체 제어 불능 및 추락 위험"
            )
        elif wind_speed >= 7.0:
            risks.append(f"풍속 주의: 풍속 {wind_speed}m/s (초경량 기체 흔들림 발생 가능)")

        if rain > 0.0:
            is_safe = False
            risks.append(f"강우/강설 감지: 시간당 {rain}mm 강수로 방수 미지원 기체 쇼트 위험 (비행 금지)")

        if visibility_km < 5.0:
            is_safe = False
            risks.append(f"시정 불량: 가시거리 {visibility_km}km (법정 시계비행 기준 5km 미달)")

        if is_safe and not risks:
            status_text = "비행 최적 (Safe to Fly)"
        elif is_safe and risks:
            status_text = "주의 비행 (Caution)"
        else:
            status_text = "비행 불가 (Danger - No Flight)"

        return is_safe, status_text, risks

    @classmethod
    def _request_kma(
        cls,
        operation: str,
        service_key: str,
        base_date: str,
        base_time: str,
        nx: int,
        ny: int,
        num_of_rows: int = 100,
    ) -> Dict[str, Any]:
        endpoint = settings.KMA_API_ENDPOINT
        url = f"{endpoint}/{operation}"
        params = {
            "serviceKey": service_key,
            "pageNo": 1,
            "numOfRows": num_of_rows,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        }
        try:
            res = requests.get(url, params=params, timeout=settings.KMA_API_TIMEOUT)
        except requests.RequestException as exc:
            safe_err = str(exc).replace(service_key, "***")
            raise WeatherAPIError(f"기상청 {operation} 네트워크 요청 실패: {safe_err}") from exc

        if res.status_code != 200:
            raise WeatherAPIError(f"기상청 {operation} HTTP 오류 ({res.status_code}): {res.text[:200]}")

        try:
            payload = res.json()
            header = payload["response"]["header"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WeatherAPIError(f"기상청 {operation} 응답 JSON 파싱 실패: {res.text[:200]}") from exc

        code = header.get("resultCode")
        msg = header.get("resultMsg", "")
        if code != "00":
            return {"_kma_error_code": code, "_kma_error_msg": msg, "items": []}

        items = (
            payload.get("response", {})
            .get("body", {})
            .get("items", {})
            .get("item", [])
        )
        if isinstance(items, dict):
            items = [items]
        return {"_kma_error_code": "00", "_kma_error_msg": msg, "items": items or []}

    @classmethod
    def _fetch_ultra_srt_ncst(cls, service_key: str, nx: int, ny: int, now_kst: datetime) -> Tuple[List[Dict[str, Any]], str, str]:
        anchor = now_kst.replace(minute=0, second=0, microsecond=0)
        if now_kst.minute < 15:
            anchor -= timedelta(hours=1)

        last_err = "NO_DATA"
        for step in range(3):
            dt = anchor - timedelta(hours=step)
            bdate = dt.strftime("%Y%m%d")
            btime = dt.strftime("%H00")
            resp = cls._request_kma("getUltraSrtNcst", service_key, bdate, btime, nx, ny, num_of_rows=20)
            if resp["_kma_error_code"] == "00" and resp["items"]:
                return resp["items"], bdate, btime
            last_err = f"{resp['_kma_error_code']}: {resp['_kma_error_msg']}"
            if resp["_kma_error_code"] not in ("03",):
                break
        raise WeatherAPIError(f"기상청 초단기실황(getUltraSrtNcst) 조회 실패 ({last_err})")

    @classmethod
    def _fetch_ultra_srt_fcst(cls, service_key: str, nx: int, ny: int, now_kst: datetime) -> List[Dict[str, Any]]:
        anchor = now_kst.replace(minute=30, second=0, microsecond=0)
        if now_kst.minute < 45:
            anchor -= timedelta(hours=1)

        for step in range(3):
            dt = anchor - timedelta(hours=step)
            resp = cls._request_kma(
                "getUltraSrtFcst",
                service_key,
                dt.strftime("%Y%m%d"),
                dt.strftime("%H30"),
                nx,
                ny,
                num_of_rows=80,
            )
            if resp["_kma_error_code"] == "00" and resp["items"]:
                return resp["items"]
            if resp["_kma_error_code"] != "03":
                break
        return []

    @classmethod
    def _fetch_vilage_pop(cls, service_key: str, nx: int, ny: int, now_kst: datetime) -> Optional[int]:
        """단기예보(getVilageFcst)에서 가장 가까운 시각의 강수확률(POP) 조회."""
        slots = [2, 5, 8, 11, 14, 17, 20, 23]
        candidates: List[Tuple[str, str]] = []
        check_dt = now_kst - timedelta(minutes=20)
        for day_offset in (0, 1):
            target_day = (check_dt - timedelta(days=day_offset)).date()
            for hr in reversed(slots):
                if day_offset == 0 and hr > check_dt.hour:
                    continue
                candidates.append((target_day.strftime("%Y%m%d"), f"{hr:02d}00"))
                if len(candidates) >= 2:
                    break
            if len(candidates) >= 2:
                break

        for bdate, btime in candidates:
            resp = cls._request_kma("getVilageFcst", service_key, bdate, btime, nx, ny, num_of_rows=36)
            if resp["_kma_error_code"] == "00" and resp["items"]:
                for item in resp["items"]:
                    if item.get("category") == "POP":
                        pop_val = cls._parse_float(item.get("fcstValue"))
                        if pop_val is not None:
                            return int(round(pop_val))
        return None

    @classmethod
    def _build_hourly_forecast(cls, fcst_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in fcst_items:
            key = (item.get("fcstDate", ""), item.get("fcstTime", ""))
            if not key[0] or not key[1]:
                continue
            grouped.setdefault(key, {})[item.get("category", "")] = item.get("fcstValue")

        hourly: List[Dict[str, Any]] = []
        for idx, ((fdate, ftime), cats) in enumerate(sorted(grouped.items())[:5]):
            hour_int = int(ftime[:2]) if len(ftime) >= 2 else 12
            temp_c = cls._parse_float(cats.get("T1H"), 0.0)
            wind_ms = cls._parse_float(cats.get("WSD"), 0.0)
            wind_gust = round(wind_ms * 1.35, 1)
            hum = int(round(cls._parse_float(cats.get("REH"), 50.0)))
            pty = int(round(cls._parse_float(cats.get("PTY"), 0.0)))
            sky = int(round(cls._parse_float(cats.get("SKY"), 1.0)))
            lgt = cls._parse_float(cats.get("LGT"), 0.0)
            rain_mm = cls._parse_rain_mm(cats.get("RN1"))
            vis_km = cls._derive_visibility_km(pty, rain_mm, hum, sky)
            desc, icon, _ = cls._describe_weather(pty, sky, lgt, hour_int)
            nd_filter = "Clear" if (hour_int >= 18 or hour_int < 6) else ("ND32" if sky == 1 and 10 <= hour_int <= 15 else ("ND16" if sky <= 3 else "ND8"))

            hourly.append({
                "date": fdate,
                "time": f"{ftime[:2]}:{ftime[2:4]}",
                "icon": icon,
                "temp_c": round(temp_c, 1),
                "temp": f"{round(temp_c, 1)}°C",
                "desc": desc,
                "wind_speed_ms": round(wind_ms, 1),
                "wind": f"{round(wind_ms, 1)} m/s",
                "wind_gust_ms": wind_gust,
                "gust": f"추정 돌풍 {wind_gust} m/s",
                "vis_km": vis_km,
                "vis": f"{vis_km} km",
                "humidity_percent": hum,
                "humid": f"{hum}%",
                "rain_mm_h": rain_mm,
                "nd": nd_filter,
                "current": idx == 0,
            })
        return hourly

    @classmethod
    def get_weather(cls, lat: float, lon: float, location_name: str = "서울 여의도 한강공원") -> Dict[str, Any]:
        """
        좌표(lat, lon) 기반 기상청 단기예보 조회서비스 2.0 실시간 날씨 및 비행 적합도 조회.
        """
        service_key = cls._resolve_service_key(settings.KMA_API_KEY)
        nx, ny = cls.latlon_to_grid(lat, lon)

        cache_key = f"kma:{nx}:{ny}"
        cached_data = external_cache.get(cache_key)
        if cached_data:
            result = dict(cached_data)
            result["cached"] = True
            result["query_location"] = location_name
            result["latitude"] = round(lat, 5)
            result["longitude"] = round(lon, 5)
            return result

        now_kst = datetime.now(KST)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            ncst_future = executor.submit(cls._fetch_ultra_srt_ncst, service_key, nx, ny, now_kst)
            fcst_future = executor.submit(cls._fetch_ultra_srt_fcst, service_key, nx, ny, now_kst)
            pop_future = executor.submit(cls._fetch_vilage_pop, service_key, nx, ny, now_kst)

            ncst_items, obs_date, obs_time = ncst_future.result()
            try:
                fcst_items = fcst_future.result()
            except Exception:
                fcst_items = []
            try:
                vilage_pop = pop_future.result()
            except Exception:
                vilage_pop = None

        ncst_map = {item.get("category"): item.get("obsrValue") for item in ncst_items}

        temp = cls._parse_float(ncst_map.get("T1H"))
        wind_speed = cls._parse_float(ncst_map.get("WSD"))
        wind_deg = cls._parse_float(ncst_map.get("VEC"), 0.0)
        humidity_raw = cls._parse_float(ncst_map.get("REH"), 50.0)
        pty = int(round(cls._parse_float(ncst_map.get("PTY"), 0.0)))
        rain = cls._parse_rain_mm(ncst_map.get("RN1"))

        if temp is None or wind_speed is None:
            raise WeatherAPIError(
                f"기상청 실황 필수 항목(T1H/WSD) 누락 (nx={nx}, ny={ny}, date={obs_date}, time={obs_time})."
            )

        temp = round(temp, 1)
        wind_speed = max(0.0, round(wind_speed, 1))
        wind_gust = round(wind_speed * 1.35, 1)
        humidity = int(max(0, min(100, round(humidity_raw))))

        hourly_forecast = cls._build_hourly_forecast(fcst_items) if fcst_items else []

        # 초단기예보 첫 시각에서 하늘상태(SKY) 및 낙뢰(LGT) 보강
        sky = 1
        lightning = 0.0
        if fcst_items:
            first_date = fcst_items[0].get("fcstDate")
            first_time = fcst_items[0].get("fcstTime")
            for item in fcst_items:
                if item.get("fcstDate") == first_date and item.get("fcstTime") == first_time:
                    if item.get("category") == "SKY":
                        sky = int(round(cls._parse_float(item.get("fcstValue"), 1.0)))
                    elif item.get("category") == "LGT":
                        lightning = cls._parse_float(item.get("fcstValue"), 0.0) or 0.0

        weather_desc, weather_icon, cloudiness = cls._describe_weather(pty, sky, lightning, now_kst.hour)
        visibility = cls._derive_visibility_km(pty, rain, humidity, sky)
        wind_direction_text = cls.deg_to_16_direction(wind_deg)

        if rain > 0.0 or pty > 0:
            rain_probability = max(vilage_pop or 0, 80)
        elif vilage_pop is not None:
            rain_probability = vilage_pop
        else:
            rain_probability = 30 if sky == 4 else (15 if sky == 3 else 0)

        is_safe, safety_status, risks = cls.evaluate_flight_safety(
            wind_speed, wind_gust, rain, visibility, lightning=lightning
        )

        observed_at = f"{obs_date[:4]}-{obs_date[4:6]}-{obs_date[6:8]} {obs_time[:2]}:{obs_time[2:4]} KST"

        result = {
            "source": "기상청 단기예보 API (VilageFcstInfoService_2.0 실시간 실황·초단기예보)",
            "cached": False,
            "query_location": location_name,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "temperature_c": temp,
            "wind_speed_ms": wind_speed,
            "wind_gust_ms": wind_gust,
            "wind_direction_deg": int(round(wind_deg)),
            "wind_direction_text": wind_direction_text,
            "precipitation_mm_h": rain,
            "rain_probability": rain_probability,
            "humidity_percent": humidity,
            "visibility_km": visibility,
            "cloudiness_percent": cloudiness,
            "weather_condition": weather_desc,
            "weather_icon": weather_icon,
            "is_safe_to_fly": is_safe,
            "safety_status": safety_status,
            "risk_factors": risks,
            "observed_at": observed_at,
            "kma_grid": {
                "nx": nx,
                "ny": ny,
                "base_date": obs_date,
                "base_time": obs_time,
            },
            "hourly_forecast": hourly_forecast,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        external_cache.set(cache_key, result, ttl=settings.CACHE_DEFAULT_TTL_WEATHER)
        return result


weather_client = WeatherClient()
