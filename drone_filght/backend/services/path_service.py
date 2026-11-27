"""
Shooting Path Analysis & Adaptive Correction Engine (Phase 6)
스마트폰 지상 보행 촬영 경로 분석 및 개인화 AI 경로 보정 서비스

핵심 기능:
1. 미터 좌표계 변환 및 누적 이동 거리 기반 선형 보간 (Linear Interpolation)
2. GPS 정확도 필터링 & 정지 상태 미세 오차(Hovering/Drift) 감지
3. AI 권장 동선 vs 스마트폰 실제 보행 동선 비교 (시작점, 종료점, 이탈도, 횡방향 오차)
4. Phase 4 구도 완성도(Sweet Spot 유지율)를 반영한 적응형 보정(Adaptive Alpha Weighting)
5. 차기 회차(N+1) 보정 경로 자동 승계 및 모바일 개선 가이드 문장 생성
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session
from backend.models.models import ShootingProject, ShootingPath, ShootingAnalysis


# ===========================================================================
# 1. 지리 좌표계 <-> 국지 미터(Meter) 평면 좌표계 변환 유틸리티
# ===========================================================================
EARTH_RADIUS_M = 6371000.0  # 지구 평균 반지름 (m)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 위경도 좌표 간의 구면 대원 거리(미터) 계산"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def lat_lon_to_meters(lat: float, lon: float, ref_lat: float, ref_lon: float) -> Tuple[float, float]:
    """기준점을 (0, 0)으로 하는 로컬 평면 직교 좌표 (x: 동서, y: 남북, 단위: m) 변환"""
    rad_ref = math.radians(ref_lat)
    x = math.radians(lon - ref_lon) * EARTH_RADIUS_M * math.cos(rad_ref)
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return x, y


def meters_to_lat_lon(x: float, y: float, ref_lat: float, ref_lon: float) -> Tuple[float, float]:
    """로컬 평면 직교 좌표 (x, y)를 다시 위경도(lat, lon)로 역변환"""
    rad_ref = math.radians(ref_lat)
    lat = ref_lat + math.degrees(y / EARTH_RADIUS_M)
    lon = ref_lon + math.degrees(x / (EARTH_RADIUS_M * math.cos(rad_ref)))
    return lat, lon


def point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """점 (px, py)에서 선분 (x1, y1)-(x2, y2)까지의 최단 수직/끝점 거리(m) 계산"""
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-6:
        return math.hypot(px - x1, py - y1)

    # 투영 비율 t 계산 및 [0, 1] 클램핑
    t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def extract_wp_coordinate(wp: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], float]:
    """다양한 형식의 웨이포인트 딕셔너리에서 (lat, lon, accuracy) 추출"""
    lat = None
    lon = None
    acc = 5.0

    if "raw_gps" in wp and isinstance(wp["raw_gps"], dict):
        g = wp["raw_gps"]
        lat = g.get("latitude") or g.get("lat")
        lon = g.get("longitude") or g.get("lng") or g.get("lon")
        acc = float(g.get("accuracy_m") or g.get("accuracy") or 5.0)
    elif "filtered_gps" in wp and isinstance(wp["filtered_gps"], dict):
        g = wp["filtered_gps"]
        lat = g.get("latitude") or g.get("lat")
        lon = g.get("longitude") or g.get("lng") or g.get("lon")
        acc = float(g.get("accuracy_m") or g.get("accuracy") or 5.0)
    else:
        lat = wp.get("lat") or wp.get("latitude")
        lon = wp.get("lng") or wp.get("longitude") or wp.get("lon")
        acc = float(wp.get("accuracy_m") or wp.get("accuracy") or 5.0)

    return (float(lat) if lat is not None else None, float(lon) if lon is not None else None, acc)


# ===========================================================================
# 2. 신규 5대 기법별 독립 지상 이동 경로 생성 엔진 (Phase 12 Step 2)
# ===========================================================================
def validate_gps_coordinate(lat: Any, lon: Any, accuracy: Optional[float] = None) -> Tuple[bool, str]:
    """위경도 좌표 및 GPS 정확도 유효성 검증"""
    if lat is None or lon is None:
        return False, "GPS 좌표가 누락되었습니다."
    try:
        f_lat = float(lat)
        f_lon = float(lon)
    except (TypeError, ValueError):
        return False, "GPS 좌표가 유효한 숫자 형식이 아닙니다."

    if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0):
        return False, f"GPS 좌표 범위 초과 (lat={f_lat}, lon={f_lon})"

    if f_lat == 0.0 and f_lon == 0.0:
        return False, "Null Island (0, 0) 비정상 GPS 좌표입니다."

    if accuracy is not None:
        try:
            f_acc = float(accuracy)
            if f_acc > 20.0:
                return False, f"GPS 수신 오차 과다 (±{int(f_acc)}m > 20m)"
        except (TypeError, ValueError):
            pass

    return True, "VALID"


def generate_forward_path(
    start_lat: float,
    start_lon: float,
    heading_deg: float = 0.0,
    distance_m: float = 10.0,
    count: int = 5,
    subject_lat: Optional[float] = None,
    subject_lon: Optional[float] = None,
    gps_accuracy: Optional[float] = None
) -> Dict[str, Any]:
    """
    [기법 1] FORWARD (전진 촬영)
    피사체 방향으로 시선을 고정하고 천천히 직선으로 접근하는 지상 보행 경로 생성
    """
    is_valid, err_msg = validate_gps_coordinate(start_lat, start_lon, gps_accuracy)
    if not is_valid:
        return {
            "technique": "FORWARD",
            "name": "전진 촬영 (Forward Approach)",
            "is_executable": False,
            "reason": f"유효하지 않은 스마트폰 GPS 좌표입니다: {err_msg}",
            "waypoints": []
        }

    count = max(3, min(10, int(count)))
    dist_m = max(2.0, min(50.0, float(distance_m)))

    # 피사체 실측 좌표가 제공된 경우 피사체 방향 방위각 산출
    if subject_lat is not None and subject_lon is not None:
        s_valid, _ = validate_gps_coordinate(subject_lat, subject_lon)
        if s_valid:
            sx, sy = lat_lon_to_meters(float(subject_lat), float(subject_lon), float(start_lat), float(start_lon))
            bearing_rad = math.atan2(sx, sy)
            eff_heading = (math.degrees(bearing_rad) + 360.0) % 360.0
        else:
            eff_heading = float(heading_deg) % 360.0
            bearing_rad = math.radians(eff_heading)
    else:
        eff_heading = float(heading_deg) % 360.0
        bearing_rad = math.radians(eff_heading)

    dx = math.sin(bearing_rad)
    dy = math.cos(bearing_rad)

    wps = []
    for i in range(count):
        s = i / max(1, count - 1)
        cur_d = dist_m * s
        x = cur_d * dx
        y = cur_d * dy
        w_lat, w_lon = meters_to_lat_lon(x, y, float(start_lat), float(start_lon))
        wps.append({
            "seq": i + 1,
            "lat": round(w_lat, 7),
            "lng": round(w_lon, 7),
            "target_heading": round(eff_heading, 1),
            "target_pitch": -10.0,
            "distance_from_start_m": round(cur_d, 2),
            "action": "FORWARD_APPROACH",
            "guide_msg": f"전진 접근 {i+1}단계: 피사체를 바라보며 천천히 앞으로 이동하세요 ({cur_d:.1f}m/{dist_m:.1f}m)"
        })

    return {
        "technique": "FORWARD",
        "name": "전진 촬영 (Forward Approach)",
        "is_executable": True,
        "total_distance_m": round(dist_m, 1),
        "target_heading_deg": round(eff_heading, 1),
        "requires_walking": True,
        "waypoints": wps,
        "safety_notice": "⚠️ [보행 안전 주의] 본 경로는 보행 가능 여부가 사전 검증된 도로가 아니므로, 이동 시 전방 및 주변 장애물을 반드시 육안으로 확인하세요."
    }


def generate_lateral_path(
    start_lat: float,
    start_lon: float,
    heading_deg: float = 0.0,
    lateral_dir: str = "right",
    distance_m: float = 10.0,
    count: int = 5,
    subject_lat: Optional[float] = None,
    subject_lon: Optional[float] = None,
    gps_accuracy: Optional[float] = None
) -> Dict[str, Any]:
    """
    [기법 2] LATERAL (측면 이동 촬영)
    피사체를 화면에 유지하면서 시선 방향에 수직인 좌우 평행 지상 보행 경로 생성
    """
    is_valid, err_msg = validate_gps_coordinate(start_lat, start_lon, gps_accuracy)
    if not is_valid:
        return {
            "technique": "LATERAL",
            "name": "측면 이동 촬영 (Lateral Tracking)",
            "is_executable": False,
            "reason": f"유효하지 않은 스마트폰 GPS 좌표입니다: {err_msg}",
            "waypoints": []
        }

    count = max(3, min(10, int(count)))
    dist_m = max(2.0, min(50.0, float(distance_m)))
    is_right = str(lateral_dir).lower() in ["right", "우측", "오른쪽"]
    dir_name = "right" if is_right else "left"
    dir_kor = "오른쪽" if is_right else "왼쪽"

    # 전방 시선 방향 (facing subject)
    eff_facing_heading = float(heading_deg) % 360.0
    # 횡이동 각도 (수직 90도)
    lat_angle_deg = (eff_facing_heading + (90.0 if is_right else -90.0) + 360.0) % 360.0
    lat_angle_rad = math.radians(lat_angle_deg)

    dx = math.sin(lat_angle_rad)
    dy = math.cos(lat_angle_rad)

    wps = []
    for i in range(count):
        s = i / max(1, count - 1)
        cur_d = dist_m * s
        x = cur_d * dx
        y = cur_d * dy
        w_lat, w_lon = meters_to_lat_lon(x, y, float(start_lat), float(start_lon))

        # 피사체 실측 좌표가 있으면 피사체를 계속 바라보도록 target_heading 동적 계산
        if subject_lat is not None and subject_lon is not None:
            sx, sy = lat_lon_to_meters(float(subject_lat), float(subject_lon), w_lat, w_lon)
            target_h = (math.degrees(math.atan2(sx, sy)) + 360.0) % 360.0
        else:
            target_h = eff_facing_heading

        wps.append({
            "seq": i + 1,
            "lat": round(w_lat, 7),
            "lng": round(w_lon, 7),
            "target_heading": round(target_h, 1),
            "target_pitch": -10.0,
            "distance_from_start_m": round(cur_d, 2),
            "action": "LATERAL_TRACK",
            "guide_msg": f"측면 이동 {i+1}단계: 피사체를 화면에 유지하면서 {dir_kor}으로 이동하세요 ({cur_d:.1f}m/{dist_m:.1f}m)"
        })

    return {
        "technique": "LATERAL",
        "name": "측면 이동 촬영 (Lateral Tracking)",
        "is_executable": True,
        "lateral_direction": dir_name,
        "total_distance_m": round(dist_m, 1),
        "requires_walking": True,
        "waypoints": wps,
        "safety_notice": "⚠️ [보행 안전 주의] 측면으로 걷는 동안 발밑과 측면 장애물에 걸려 넘어지지 않도록 주변 환경을 수시로 육안 확인하세요."
    }


def generate_diagonal_reveal_path(
    start_lat: float,
    start_lon: float,
    heading_deg: float = 0.0,
    diagonal_side: str = "left",
    forward_dist_m: float = 8.0,
    lateral_dist_m: float = 6.0,
    count: int = 5,
    gps_accuracy: Optional[float] = None
) -> Dict[str, Any]:
    """
    [기법 3] DIAGONAL_REVEAL (사선 리빌 촬영)
    전경 요소를 벗어나며 배경을 드러내는 대각선 지상 보행 경로 생성 (촬영 연출 패턴)
    """
    is_valid, err_msg = validate_gps_coordinate(start_lat, start_lon, gps_accuracy)
    if not is_valid:
        return {
            "technique": "DIAGONAL_REVEAL",
            "name": "사선 리빌 촬영 (Diagonal Reveal)",
            "is_executable": False,
            "reason": f"유효하지 않은 스마트폰 GPS 좌표입니다: {err_msg}",
            "waypoints": []
        }

    count = max(3, min(10, int(count)))
    f_dist = max(1.0, min(30.0, float(forward_dist_m)))
    l_dist = max(1.0, min(30.0, float(lateral_dist_m)))

    is_left = str(diagonal_side).lower() in ["left", "좌측", "왼쪽"]
    side_name = "left" if is_left else "right"
    side_kor = "왼쪽" if is_left else "오른쪽"

    f_rad = math.radians(float(heading_deg) % 360.0)
    lat_angle = (float(heading_deg) + (-90.0 if is_left else 90.0) + 360.0) % 360.0
    l_rad = math.radians(lat_angle)

    fx = math.sin(f_rad)
    fy = math.cos(f_rad)
    lx = math.sin(l_rad)
    ly = math.cos(l_rad)

    total_hypot = math.hypot(f_dist, l_dist)

    wps = []
    for i in range(count):
        s = i / max(1, count - 1)
        cur_f = f_dist * s
        cur_l = l_dist * s
        x = (cur_f * fx) + (cur_l * lx)
        y = (cur_f * fy) + (cur_l * ly)
        w_lat, w_lon = meters_to_lat_lon(x, y, float(start_lat), float(start_lon))
        cur_d = math.hypot(cur_f, cur_l)

        wps.append({
            "seq": i + 1,
            "lat": round(w_lat, 7),
            "lng": round(w_lon, 7),
            "target_heading": round(float(heading_deg) % 360.0, 1),
            "target_pitch": -10.0,
            "distance_from_start_m": round(cur_d, 2),
            "action": "DIAGONAL_REVEAL_WALK",
            "guide_msg": f"사선 리빌 {i+1}단계: 전경을 벗어나도록 {side_kor} 앞 방향으로 이동하세요 ({cur_d:.1f}m/{total_hypot:.1f}m)"
        })

    return {
        "technique": "DIAGONAL_REVEAL",
        "name": "사선 리빌 촬영 (Diagonal Reveal)",
        "is_executable": True,
        "diagonal_side": side_name,
        "total_distance_m": round(total_hypot, 1),
        "requires_walking": True,
        "waypoints": wps,
        "safety_notice": "⚠️ [보행 안전 주의] 본 경로는 사선 이동을 이용한 촬영 연출 패턴이며, 실제 현장의 장애물 회피나 안전 통과를 보장하지 않습니다. 반드시 주변 장애물을 육안으로 확인하세요."
    }


def generate_orbit_path(
    start_lat: float,
    start_lon: float,
    subject_lat: Optional[float] = None,
    subject_lon: Optional[float] = None,
    orbit_direction: str = "clockwise",
    arc_angle_deg: float = 180.0,
    count: int = 5,
    space_confirmed: bool = True,
    gps_accuracy: Optional[float] = None
) -> Dict[str, Any]:
    """
    [기법 4] ORBIT (반원 회전 촬영)
    피사체 실측 GPS 좌표 중심 반원(180도) 선회 지상 보행 경로 생성
    조건 미충족 시(피사체 GPS 누락, 공간 미확인, GPS 오차 과다) 경로 생성을 엄격히 거부
    """
    is_valid, err_msg = validate_gps_coordinate(start_lat, start_lon, gps_accuracy)
    if not is_valid:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": f"유효하지 않은 스마트폰 GPS 좌표입니다: {err_msg}",
            "waypoints": []
        }

    # [핵심 검증 1] 피사체 실측 GPS 누락 시 임의 좌표 생성 금지 및 즉각 거부
    if subject_lat is None or subject_lon is None:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": "피사체의 실제 GPS 실측 좌표가 확인되지 않아 반원 회전 경로 생성이 비활성화되었습니다. (임의 좌표 생성 금지)",
            "waypoints": []
        }

    s_valid, s_err = validate_gps_coordinate(subject_lat, subject_lon)
    if not s_valid:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": f"피사체 실측 GPS 좌표 오류: {s_err}",
            "waypoints": []
        }

    # [핵심 검증 2] 주변 보행 공간 미확인 시 경로 생성 거부
    if not space_confirmed:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": "피사체 주변의 안전한 반원 보행 공간이 확인되지 않아 경로 생성을 거부합니다.",
            "waypoints": []
        }

    # [핵심 검증 3] 스마트폰 GPS 오차 20m 초과 시 경로 생성 거부
    if gps_accuracy is not None and float(gps_accuracy) > 20.0:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": f"스마트폰 GPS 오차(±{int(gps_accuracy)}m > 20m)가 커서 정밀한 반원 궤적을 산출할 수 없습니다.",
            "waypoints": []
        }

    # 피사체와 시작점 간 거리(반경) 계산
    radius = haversine_distance(float(start_lat), float(start_lon), float(subject_lat), float(subject_lon))
    if radius < 2.0 or radius > 50.0:
        return {
            "technique": "ORBIT",
            "name": "반원 회전 촬영 (Orbit Arc)",
            "is_executable": False,
            "reason": f"피사체와의 거리({radius:.1f}m)가 반원 보행 권장 범위(2~50m)를 벗어났습니다.",
            "waypoints": []
        }

    count = max(3, min(10, int(count)))
    arc_deg = max(45.0, min(180.0, float(arc_angle_deg)))
    is_cw = str(orbit_direction).lower() in ["clockwise", "시계", "cw"]
    dir_name = "clockwise" if is_cw else "counter_clockwise"

    # 피사체 중심 국지 평면 좌표계 (원점: subject_lat, subject_lon)
    x0, y0 = lat_lon_to_meters(float(start_lat), float(start_lon), float(subject_lat), float(subject_lon))
    theta0 = math.atan2(y0, x0)
    delta_theta = math.radians(arc_deg)

    wps = []
    for i in range(count):
        s = i / max(1, count - 1)
        theta_i = theta0 - (delta_theta * s) if is_cw else theta0 + (delta_theta * s)
        xi = radius * math.cos(theta_i)
        yi = radius * math.sin(theta_i)
        w_lat, w_lon = meters_to_lat_lon(xi, yi, float(subject_lat), float(subject_lon))

        # 웨이포인트에서 피사체 중심(0, 0)을 향하는 방위각 (dx: -xi, dy: -yi)
        t_heading = (math.degrees(math.atan2(-xi, -yi)) + 360.0) % 360.0

        wps.append({
            "seq": i + 1,
            "lat": round(w_lat, 7),
            "lng": round(w_lon, 7),
            "target_heading": round(t_heading, 1),
            "target_pitch": -12.0,
            "angle_step_deg": round(s * arc_deg, 1),
            "action": "ORBIT_ARC_WALK",
            "guide_msg": f"반원 선회 {i+1}단계: 피사체를 바라보며 반원 방향으로 이동하세요 ({int(s * arc_deg)}°)"
        })

    return {
        "technique": "ORBIT",
        "name": "반원 회전 촬영 (Orbit Arc)",
        "is_executable": True,
        "radius_m": round(radius, 1),
        "arc_angle_deg": round(arc_deg, 1),
        "orbit_direction": dir_name,
        "requires_walking": True,
        "waypoints": wps,
        "safety_notice": "⚠️ [보행 안전 주의] 피사체를 주시하며 걷는 동안 발밑과 측면 장애물에 걸리지 않도록 주변 환경을 육안으로 확인하세요."
    }


def generate_panorama_guide(
    current_lat: Optional[float] = None,
    current_lon: Optional[float] = None,
    current_heading: float = 0.0,
    sweep_angle_deg: float = 120.0,
    rotation_direction: str = "right",
    steps: int = 4
) -> Dict[str, Any]:
    """
    [기법 5] PANORAMA (고정 파노라마 촬영)
    보행 waypoint를 일절 생성하지 않고(0개), 스마트폰 방향 센서 기준으로 회전 각도를 안내
    """
    steps = max(2, min(8, int(steps)))
    sweep_deg = max(30.0, min(360.0, float(sweep_angle_deg)))
    is_right = str(rotation_direction).lower() in ["right", "우측", "오른쪽"]
    dir_name = "right" if is_right else "left"
    dir_kor = "오른쪽" if is_right else "왼쪽"

    start_h = float(current_heading) % 360.0

    checkpoints = []
    for k in range(steps):
        s = k / max(1, steps - 1)
        delta = sweep_deg * s
        t_heading = (start_h + (delta if is_right else -delta) + 360.0) % 360.0
        checkpoints.append({
            "step": k + 1,
            "target_heading": round(t_heading, 1),
            "angle_delta_deg": round(delta, 1),
            "guide_msg": f"파노라마 {k+1}단계: 현재 위치를 유지하고 천천히 {dir_kor}으로 회전하세요 (목표 각도 {int(t_heading)}°)"
        })

    return {
        "technique": "PANORAMA",
        "name": "고정 파노라마 촬영 (Stationary Panorama)",
        "is_executable": True,
        "requires_walking": False,
        "requires_heading_sensor": True,
        "is_stationary": True,
        "rotation_direction": dir_name,
        "sweep_angle_deg": round(sweep_deg, 1),
        "waypoints": [],  # [엄격 준수] 보행 waypoint 0개
        "rotation_checkpoints": checkpoints,
        "guide_message": f"현재 위치를 유지하고 천천히 {dir_kor}으로 회전하세요.",
        "safety_notice": "📱 [고정 파노라마 안내] 본 기법은 보행 이동 없이 제자리에서 기기를 수평으로 잡고 회전하는 촬영입니다."
    }


# ===========================================================================
# 3. 촬영 기법별 기본 권장 보행 경로 템플릿 생성 (하위 호환 100% 보존)
# ===========================================================================
def generate_default_recommended_waypoints(
    ref_lat: float = 37.5284,
    ref_lon: float = 126.9328,
    mode_name: str = "POI Orbit",
    count: int = 5
) -> List[Dict[str, Any]]:
    """프로젝트 기준 좌표 주변으로 촬영 기법에 부합하는 다점 보행 궤적 템플릿 생성"""
    mode_lower = mode_name.lower()
    wps = []

    # 1) 오빗 / 원형 회전 촬영 (반경 5m 원형 호)
    if any(k in mode_lower for k in ["orbit", "오빗", "회전", "선셋 아크"]):
        radius = 5.0
        for i in range(count):
            angle = (math.pi / 2.0) * (i / max(1, count - 1))  # 0 to 90 degrees
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            lat, lon = meters_to_lat_lon(x, y, ref_lat, ref_lon)
            wps.append({
                "seq": i + 1,
                "lat": round(lat, 7),
                "lng": round(lon, 7),
                "target_heading": round((angle * 180.0 / math.pi + 180.0) % 360.0, 1),
                "target_pitch": -12.0,
                "guide_msg": f"오빗 선회 {i+1}단계: 피사체 중심을 조준하며 원호 이동",
                "action": "ORBIT_WALK"
            })
    # 2) 직선 드로니 / 후진 촬영 (남쪽 방향 -10m 직선 후진)
    elif any(k in mode_lower for k in ["dronie", "드로니", "후진", "fly-through"]):
        total_dist = 10.0
        for i in range(count):
            dist = (total_dist * (i / max(1, count - 1)))
            x = 0.0
            y = -dist
            lat, lon = meters_to_lat_lon(x, y, ref_lat, ref_lon)
            wps.append({
                "seq": i + 1,
                "lat": round(lat, 7),
                "lng": round(lon, 7),
                "target_heading": 0.0,  # 북쪽 피사체 응시
                "target_pitch": -10.0,
                "guide_msg": f"드로니 {i+1}단계: 피사체를 정면에 두고 서서히 뒤로 후진",
                "action": "BACKWARD_WALK"
            })
    # 3) 삼분할 추적 / 횡이동 촬영 (동쪽으로 +12m 평행 전진)
    elif any(k in mode_lower for k in ["track", "트래킹", "삼분할", "추적"]):
        total_dist = 12.0
        for i in range(count):
            dist = (total_dist * (i / max(1, count - 1)))
            x = dist
            y = 2.0
            lat, lon = meters_to_lat_lon(x, y, ref_lat, ref_lon)
            wps.append({
                "seq": i + 1,
                "lat": round(lat, 7),
                "lng": round(lon, 7),
                "target_heading": 90.0,
                "target_pitch": -10.0,
                "guide_msg": f"삼분할 추적 {i+1}단계: 우측 분할선에 피사체를 고정하고 등속 전진",
                "action": "TRACK_WALK"
            })
    # 4) 기본 직선 전진
    else:
        total_dist = 10.0
        for i in range(count):
            dist = (total_dist * (i / max(1, count - 1)))
            x = 0.0
            y = dist
            lat, lon = meters_to_lat_lon(x, y, ref_lat, ref_lon)
            wps.append({
                "seq": i + 1,
                "lat": round(lat, 7),
                "lng": round(lon, 7),
                "target_heading": 0.0,
                "target_pitch": -10.0,
                "guide_msg": f"권장 동선 {i+1}구간: 수평을 유지하며 전진",
                "action": "FORWARD_WALK"
            })

    return wps


# ===========================================================================
# 3. AI 촬영 경로 분석 & 보정 핵심 엔진 (ShootingPathService)
# ===========================================================================
class ShootingPathService:
    """스마트폰 지상 보행 경로 분석 및 적응형 보정 서비스"""

    haversine_distance = staticmethod(haversine_distance)
    lat_lon_to_meters = staticmethod(lat_lon_to_meters)
    meters_to_lat_lon = staticmethod(meters_to_lat_lon)
    point_to_segment_distance = staticmethod(point_to_segment_distance)
    generate_default_recommended_waypoints = staticmethod(generate_default_recommended_waypoints)
    validate_gps_coordinate = staticmethod(validate_gps_coordinate)
    generate_forward_path = staticmethod(generate_forward_path)
    generate_lateral_path = staticmethod(generate_lateral_path)
    generate_diagonal_reveal_path = staticmethod(generate_diagonal_reveal_path)
    generate_orbit_path = staticmethod(generate_orbit_path)
    generate_panorama_guide = staticmethod(generate_panorama_guide)

    def generate_technique_path(
        self,
        technique_id: str,
        start_lat: float,
        start_lon: float,
        heading_deg: float = 0.0,
        subject_lat: Optional[float] = None,
        subject_lon: Optional[float] = None,
        gps_accuracy: Optional[float] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """신규 5대 기법 ID에 따른 독립 경로 생성기 분기"""
        tid = str(technique_id).upper().strip()
        if tid == "FORWARD":
            return generate_forward_path(
                start_lat=start_lat, start_lon=start_lon,
                heading_deg=heading_deg,
                distance_m=kwargs.get("distance_m", 10.0),
                count=kwargs.get("count", 5),
                subject_lat=subject_lat, subject_lon=subject_lon,
                gps_accuracy=gps_accuracy
            )
        elif tid == "LATERAL":
            return generate_lateral_path(
                start_lat=start_lat, start_lon=start_lon,
                heading_deg=heading_deg,
                lateral_dir=kwargs.get("lateral_dir", "right"),
                distance_m=kwargs.get("distance_m", 10.0),
                count=kwargs.get("count", 5),
                subject_lat=subject_lat, subject_lon=subject_lon,
                gps_accuracy=gps_accuracy
            )
        elif tid == "DIAGONAL_REVEAL":
            return generate_diagonal_reveal_path(
                start_lat=start_lat, start_lon=start_lon,
                heading_deg=heading_deg,
                diagonal_side=kwargs.get("diagonal_side", "left"),
                forward_dist_m=kwargs.get("forward_dist_m", 8.0),
                lateral_dist_m=kwargs.get("lateral_dist_m", 6.0),
                count=kwargs.get("count", 5),
                gps_accuracy=gps_accuracy
            )
        elif tid == "ORBIT":
            return generate_orbit_path(
                start_lat=start_lat, start_lon=start_lon,
                subject_lat=subject_lat, subject_lon=subject_lon,
                orbit_direction=kwargs.get("orbit_direction", "clockwise"),
                arc_angle_deg=kwargs.get("arc_angle_deg", 180.0),
                count=kwargs.get("count", 5),
                space_confirmed=kwargs.get("space_confirmed", True),
                gps_accuracy=gps_accuracy
            )
        elif tid == "PANORAMA":
            return generate_panorama_guide(
                current_lat=start_lat, current_lon=start_lon,
                current_heading=heading_deg,
                sweep_angle_deg=kwargs.get("sweep_angle_deg", 120.0),
                rotation_direction=kwargs.get("rotation_direction", "right"),
                steps=kwargs.get("steps", 4)
            )
        else:
            return generate_forward_path(
                start_lat=start_lat, start_lon=start_lon,
                heading_deg=heading_deg,
                distance_m=kwargs.get("distance_m", 10.0),
                count=kwargs.get("count", 5),
                subject_lat=subject_lat, subject_lon=subject_lon,
                gps_accuracy=gps_accuracy
            )

    def analyze_and_correct_path(
        self,
        recommended_waypoints: Optional[List[Dict[str, Any]]],
        actual_waypoints: Optional[List[Dict[str, Any]]],
        project: Optional[ShootingProject] = None
    ) -> Dict[str, Any]:
        """
        AI 권장 경로와 실제 스마트폰 GPS 수집 경로를 비교·분석하여
        이탈도 산출 및 다음 촬영용 보정 경로(corrected_waypoints)를 생성합니다.
        """
        # 기준 좌표 식별
        ref_lat = project.latitude if (project and project.latitude) else 37.5284
        ref_lon = project.longitude if (project and project.longitude) else 126.9328
        mode_name = project.recommended_mode if (project and project.recommended_mode) else "POI Orbit"

        # 1. 권장 경로 보강 (비어있거나 단일 좌표인 경우 템플릿 생성)
        rec_wps = list(recommended_waypoints or [])
        if len(rec_wps) < 2:
            if len(rec_wps) == 1:
                p_lat, p_lon, _ = extract_wp_coordinate(rec_wps[0])
                if p_lat and p_lon:
                    ref_lat, ref_lon = p_lat, p_lon
            rec_wps = generate_default_recommended_waypoints(ref_lat, ref_lon, mode_name, count=5)

        # 2. 실제 스마트폰 GPS 좌표 정제 및 신뢰도 검증
        act_raw = list(actual_waypoints or [])
        valid_act_points = []
        accuracies = []

        for wp in act_raw:
            lat, lon, acc = extract_wp_coordinate(wp)
            if lat is not None and lon is not None:
                # GPS 정확도가 20m 초과인 저신뢰 데이터 필터링
                if acc <= 20.0:
                    valid_act_points.append({
                        "lat": lat,
                        "lon": lon,
                        "acc": acc,
                        "wp_ref": wp
                    })
                accuracies.append(acc)

        avg_acc = (sum(accuracies) / len(accuracies)) if accuracies else 99.0

        # 데이터 부족 또는 GPS 수신 불량 (오차 15m 초과 또는 유효점 2개 미만)
        if len(valid_act_points) < 2 or (len(accuracies) > 0 and avg_acc > 15.0):
            return {
                "is_valid": False,
                "deviation_score": None,
                "match_score": 30.0,
                "max_deviation_m": None,
                "avg_deviation_m": None,
                "average_deviation_m": None,
                "start_point_error_m": None,
                "end_point_error_m": None,
                "path_length_rec_m": 0.0,
                "path_length_act_m": 0.0,
                "alpha_weight": 0.3,
                "deviation_reason": "GPS_ACCURACY_LOW",
                "advice_message": "스마트폰 GPS 신호 오차가 커서 경로를 정확히 분석하지 못했습니다. 하늘이 트인 야외에서 Wi-Fi/위성 신호를 확보한 뒤 다시 시도해 주세요.",
                "actionable_advice": "스마트폰 GPS 신호 오차가 커서 경로를 정확히 분석하지 못했습니다. 하늘이 트인 야외에서 Wi-Fi/위성 신호를 확보한 뒤 다시 시도해 주세요.",
                "recommended_waypoints": rec_wps,
                "actual_waypoints": act_raw,
                "corrected_waypoints": rec_wps  # 기존 권장 경로 유지
            }

        # 3. 로컬 평면 미터 좌표 변환
        # 기준 좌표는 권장 경로의 첫 점으로 설정
        first_r_lat, first_r_lon, _ = extract_wp_coordinate(rec_wps[0])
        origin_lat = first_r_lat or ref_lat
        origin_lon = first_r_lon or ref_lon

        rec_meters = []
        for r in rec_wps:
            r_lat, r_lon, _ = extract_wp_coordinate(r)
            if r_lat is not None and r_lon is not None:
                mx, my = lat_lon_to_meters(r_lat, r_lon, origin_lat, origin_lon)
                rec_meters.append((mx, my, r))

        act_meters = []
        for a in valid_act_points:
            mx, my = lat_lon_to_meters(a["lat"], a["lon"], origin_lat, origin_lon)
            act_meters.append((mx, my, a))

        # 4. 정지 상태 미세 오차 (Hovering / Stationary Drift) 감지
        # 전체 이동 변위가 2.5m 미만인 경우 제자리 촬영으로 판단
        start_act = act_meters[0]
        end_act = act_meters[-1]
        total_displacement = math.hypot(end_act[0] - start_act[0], end_act[1] - start_act[1])

        act_total_len = 0.0
        for i in range(len(act_meters) - 1):
            act_total_len += math.hypot(act_meters[i+1][0] - act_meters[i][0], act_meters[i+1][1] - act_meters[i][1])

        if total_displacement < 2.5 and act_total_len < 5.0:
            return {
                "is_valid": False,
                "deviation_score": round(total_displacement, 2),
                "match_score": 75.0,
                "max_deviation_m": round(total_displacement, 2),
                "avg_deviation_m": round(total_displacement, 2),
                "average_deviation_m": round(total_displacement, 2),
                "start_point_error_m": round(math.hypot(start_act[0] - rec_meters[0][0], start_act[1] - rec_meters[0][1]), 2),
                "end_point_error_m": None,
                "path_length_rec_m": 0.0,
                "path_length_act_m": round(act_total_len, 2),
                "alpha_weight": 0.3,
                "deviation_reason": "STATIONARY_DRIFT",
                "advice_message": "정지 상태에서 스마트폰 센서 및 GPS 미세 오차가 발생했습니다. 이동 보행 동선이 감지되지 않아 기존 권장 경로를 유지합니다.",
                "actionable_advice": "정지 상태에서 스마트폰 센서 및 GPS 미세 오차가 발생했습니다. 이동 보행 동선이 감지되지 않아 기존 권장 경로를 유지합니다.",
                "recommended_waypoints": rec_wps,
                "actual_waypoints": act_raw,
                "corrected_waypoints": rec_wps
            }

        # 5. 권장 경로와 실제 이동 경로 비교 (횡방향 최단 오차 계산)
        deviations = []
        for ax, ay, _ in act_meters:
            min_dist = float("inf")
            for j in range(len(rec_meters) - 1):
                r1 = rec_meters[j]
                r2 = rec_meters[j+1]
                d = point_to_segment_distance(ax, ay, r1[0], r1[1], r2[0], r2[1])
                if d < min_dist:
                    min_dist = d
            deviations.append(min_dist)

        avg_dev = sum(deviations) / len(deviations) if deviations else 0.0
        max_dev = max(deviations) if deviations else 0.0

        # 시작점 및 종료점 오차
        start_error = math.hypot(act_meters[0][0] - rec_meters[0][0], act_meters[0][1] - rec_meters[0][1])
        end_error = math.hypot(act_meters[-1][0] - rec_meters[-1][0], act_meters[-1][1] - rec_meters[-1][1])

        # 권장 경로 총 길이
        rec_total_len = 0.0
        for i in range(len(rec_meters) - 1):
            rec_total_len += math.hypot(rec_meters[i+1][0] - rec_meters[i][0], rec_meters[i+1][1] - rec_meters[i][1])

        # 6. 실시간 구도 달성도 (Phase 4 Sweet Spot) 평가
        sweet_spot_count = 0
        comp_scores = []
        for p in valid_act_points:
            orig_wp = p.get("wp_ref", {})
            c_state = orig_wp.get("composition_state", {})
            if c_state.get("is_sweet_spot") is True:
                sweet_spot_count += 1
            if "frame_score" in c_state:
                comp_scores.append(float(c_state["frame_score"]))

        comp_ratio = (sweet_spot_count / len(valid_act_points)) if valid_act_points else 0.5
        avg_comp_score = (sum(comp_scores) / len(comp_scores)) if comp_scores else (comp_ratio * 100.0)

        # 7. 적응형 보정 가중치(alpha_weight) 및 이탈 원인(deviation_reason) 결정
        # - 정상 경로 유지 (avg_dev <= 2.0m): 권장 동선 준수 (alpha=0.35, reason=NORMAL)
        # - 구도 최적화 우회 (avg_dev > 2.0m & avg_comp_score >= 80.0): 사용자가 피사체에 맞게 동선을 훌륭하게 보정한 것이므로 실제 경로 대폭 반영 (alpha=0.60, reason=COMPOSITION_OPTIMIZED)
        # - 단순 보행 우회 (avg_dev > 3.0m & avg_comp_score < 80.0): 보행 길 잃음 또는 불필요 우회 (alpha=0.20, reason=WALKING_DETOUR)
        # - 통상적 미세 흔들림 (2.0m < avg_dev <= 3.0m): (alpha=0.25, reason=PHONE_SHAKE)
        if avg_dev <= 2.0:
            alpha = 0.35
            reason = "NORMAL"
            advice = (
                f"권장 동선을 매우 훌륭하게 이행하셨습니다 (경로 일치도 {max(0, 100 - avg_dev*10):.0f}%). "
                f"안정적인 보행 흐름을 반영하여 차기 회차 가이드를 미세 보정했습니다."
            )
        elif avg_comp_score >= 80.0:
            alpha = 0.60
            reason = "COMPOSITION_OPTIMIZED"
            advice = (
                f"경로가 평균 {avg_dev:.1f}m 이탈했으나 피사체 구도 일치도({avg_comp_score:.0f}점)가 매우 우수했습니다! "
                f"사용자님의 실제 보행 동선 장점을 {int(alpha*100)}% 승계하여 다음 권장 경로로 보정했습니다."
            )
        elif avg_dev > 3.0:
            alpha = 0.20
            reason = "WALKING_DETOUR"
            advice = (
                f"권장 경로 대비 평균 {avg_dev:.1f}m(최대 {max_dev:.1f}m) 벗어났습니다. "
                f"다음 촬영에서는 화면의 방향 화살표를 주시하며 권장 가이드선 안쪽으로 걸어주세요."
            )
        else:
            alpha = 0.25
            reason = "PHONE_SHAKE"
            advice = (
                f"일부 구간에서 급격한 이탈(최대 {max_dev:.1f}m)이 감지되었습니다. "
                f"발걸음을 11자로 유지하는 닌자 워킹으로 상하좌우 흔들림을 완화해 보세요."
            )

        # 8. 누적 이동 거리 기반 선형 보간 보정 경로(corrected_waypoints) 생성
        # K개 지점 (권장 웨이포인트 수와 일치, 최소 2개)
        K = max(2, len(rec_meters))
        corrected_wps = []

        for k in range(K):
            s = k / max(1, K - 1)  # 0.0 ~ 1.0 진행률

            # (1) 권장 경로 위의 위치 r_pos(s)
            r_pos = self._sample_polyline(rec_meters, s)
            # (2) 실제 경로 위의 위치 a_pos(s)
            a_pos = self._sample_polyline(act_meters, s)

            # (3) 가중 선형 결합: C = (1 - alpha) * R + alpha * A
            cx = (1.0 - alpha) * r_pos[0] + alpha * a_pos[0]
            cy = (1.0 - alpha) * r_pos[1] + alpha * a_pos[1]

            c_lat, c_lon = meters_to_lat_lon(cx, cy, origin_lat, origin_lon)

            # 각도 및 조준 방향 가이드
            guide_r = rec_wps[min(k, len(rec_wps) - 1)]
            target_heading = guide_r.get("target_heading", 0.0)
            target_pitch = guide_r.get("target_pitch", -10.0)

            corrected_wps.append({
                "seq": k + 1,
                "lat": round(c_lat, 7),
                "lng": round(c_lon, 7),
                "target_heading": target_heading,
                "target_pitch": target_pitch,
                "guide_msg": f"보정 가이드 {k+1}구간: {advice.split('.')[0]}",
                "action": guide_r.get("action", "SMOOTH_WALK")
            })

        # 9. 경로 일치도(match_score, 0~100) 및 이탈 점수 산출
        match_score = max(10.0, min(100.0, 100.0 - (avg_dev * 8.0) - (start_error * 1.5)))

        return {
            "is_valid": True,
            "deviation_score": round(avg_dev, 2),
            "match_score": round(match_score, 1),
            "max_deviation_m": round(max_dev, 2),
            "avg_deviation_m": round(avg_dev, 2),
            "average_deviation_m": round(avg_dev, 2),
            "start_point_error_m": round(start_error, 2),
            "end_point_error_m": round(end_error, 2),
            "path_length_rec_m": round(rec_total_len, 2),
            "path_length_act_m": round(act_total_len, 2),
            "alpha_weight": round(alpha, 2),
            "deviation_reason": reason,
            "composition_score": round(avg_comp_score, 1),
            "advice_message": advice,
            "actionable_advice": advice,
            "recommended_waypoints": rec_wps,
            "actual_waypoints": act_raw,
            "corrected_waypoints": corrected_wps
        }

    def _sample_polyline(self, points_meters: List[Tuple[float, float, Any]], progress: float) -> Tuple[float, float]:
        """누적 거리 진행률 progress(0.0~1.0)에 해당하는 꺾은선 상의 (x, y) 보간 계산"""
        if not points_meters:
            return 0.0, 0.0
        if len(points_meters) == 1:
            return points_meters[0][0], points_meters[0][1]

        # 세그먼트별 거리 계산
        seg_lens = []
        total_len = 0.0
        for i in range(len(points_meters) - 1):
            p1 = points_meters[i]
            p2 = points_meters[i+1]
            l = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            seg_lens.append(l)
            total_len += l

        if total_len < 1e-6:
            return points_meters[0][0], points_meters[0][1]

        target_dist = total_len * max(0.0, min(1.0, progress))
        accum = 0.0

        for i, l in enumerate(seg_lens):
            if accum + l >= target_dist or i == len(seg_lens) - 1:
                t = (target_dist - accum) / max(1e-6, l)
                t = max(0.0, min(1.0, t))
                p1 = points_meters[i]
                p2 = points_meters[i+1]
                return p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])
            accum += l

        return points_meters[-1][0], points_meters[-1][1]

    # =======================================================================
    # 4. 차기 회차(N+1) 추천 경로 승계 및 조회
    # =======================================================================
    def get_next_round_recommendation(
        self,
        db: Session,
        project_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        동일 프로젝트의 이전 유효 촬영 기록(ShootingPath)을 조회하여
        이전 보정 경로(corrected_waypoints)를 다음 회차의 권장 경로로 승계 반환
        Phase 8: 프로젝트 공통 학습 경로(ProjectCommonPath) 반영
        Phase 9: 사용자별 맞춤 변형 경로(PersonalizedShootingPath) 최우선 승계
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise ValueError(f"프로젝트(ID={project_id})를 찾을 수 없습니다.")

        # 가장 최근 유효 촬영 경로 검색
        latest_valid_path = db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id,
            ShootingPath.is_valid == True
        ).order_by(ShootingPath.shooting_number.desc()).first()

        latest_any_path = db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id
        ).order_by(ShootingPath.shooting_number.desc()).first()

        next_number = (latest_any_path.shooting_number + 1) if latest_any_path else 1

        # Phase 8: 프로젝트에 학습된 활성 공통 경로(ProjectCommonPath)가 있는지 확인
        from backend.models.models import ProjectCommonPath, PersonalizedShootingPath
        active_common = db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == project_id,
            ProjectCommonPath.is_active == True
        ).order_by(ProjectCommonPath.version.desc()).first()

        # Phase 9: 사용자의 활성 개인화 맞춤 변형 경로가 있는지 확인
        pers_path = None
        if user_id:
            pers_path = db.query(PersonalizedShootingPath).filter(
                PersonalizedShootingPath.project_id == project_id,
                PersonalizedShootingPath.user_id == user_id,
                PersonalizedShootingPath.is_active == True
            ).order_by(PersonalizedShootingPath.created_at.desc()).first()

        # Staleness 판정: 공통 경로 최신 버전과 개인화 경로의 base_common_version 비교
        is_pers_stale = False
        if pers_path and active_common:
            if pers_path.base_common_version < active_common.version:
                is_pers_stale = True

        pers_var_type = None
        is_personalized = False

        # 1) Phase 9: 사용자 개인별 맞춤 변형 경로가 존재하고 최신 공통 버전과 일치하는 경우 최우선 제공
        if pers_path and pers_path.personalized_waypoints and not is_pers_stale:
            recs = pers_path.personalized_waypoints
            is_inherited = True
            is_personalized = True
            pers_var_type = pers_path.variation_type
            source_info = f"사용자 맞춤형 [{pers_path.variation_type}] 변형 동선(공통 v{pers_path.base_common_version} 기반)이 적용되었습니다."
            prev_deviation = None
            prev_reason = f"PERSONALIZED_{pers_path.variation_type}"
        # 2) Phase 8: 다중 사용자 공통 학습 경로가 존재하는 경우 (개인화 경로가 없거나 노후화되어 최신 공통 경로로 Fallback하는 경우)
        elif active_common and active_common.common_waypoints:
            recs = active_common.common_waypoints
            is_inherited = True
            is_personalized = False
            pers_var_type = None
            if is_pers_stale:
                source_info = f"기존 개인 맞춤 동선(v{pers_path.base_common_version} 기반)이 노후화되어 최신 v{active_common.version} 공통 권장 동선으로 대체 제공합니다. 맞춤 동선을 재단장해 주세요."
            else:
                source_info = f"프로젝트 참여자 {active_common.contributor_count}명의 우수 경로({active_common.total_paths_used}건)를 학습한 최신 v{active_common.version} 공통 권장 동선입니다."
            prev_deviation = active_common.average_deviation_m
            prev_reason = f"COLLABORATIVE_V{active_common.version}"
        # 3) Phase 6: 이전 개인 유효 보정 경로가 존재하는 경우 승계
        elif latest_valid_path and latest_valid_path.corrected_waypoints:
            recs = latest_valid_path.corrected_waypoints
            is_inherited = True
            source_info = f"이전 {latest_valid_path.shooting_number}회차의 AI 보정 동선을 차기 {next_number}회차 권장 경로로 승계했습니다."
            prev_deviation = latest_valid_path.deviation_score
            prev_reason = latest_valid_path.deviation_reason
        else:
            # 4) 초기 신규 사용자이거나 유효 기록이 없는 경우: 기본 프로젝트 템플릿 유지
            ref_lat = project.latitude or 37.5284
            ref_lon = project.longitude or 126.9328
            mode_name = project.recommended_mode or "POI Orbit"
            recs = generate_default_recommended_waypoints(ref_lat, ref_lon, mode_name, count=5)
            is_inherited = False
            source_info = f"초기 {next_number}회차 기본 권장 경로(프로젝트 기획 기반)를 제공합니다."
            prev_deviation = None
            prev_reason = None

        return {
            "project_id": project_id,
            "next_shooting_number": next_number,
            "target_shooting_number": next_number,
            "is_inherited_from_previous": is_inherited,
            "source_info": source_info,
            "previous_shooting_number": latest_valid_path.shooting_number if latest_valid_path else None,
            "source_shooting_number": latest_valid_path.shooting_number if latest_valid_path else None,
            "previous_deviation_score": prev_deviation,
            "previous_deviation_reason": prev_reason,
            "common_path_version": active_common.version if active_common else None,
            "personalized_variation_type": pers_var_type,
            "is_personalized": is_personalized,
            "recommended_waypoints": recs
        }


# 싱글톤 인스턴스
path_service = ShootingPathService()
