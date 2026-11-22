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
# 2. 촬영 기법별 기본 권장 보행 경로 템플릿 생성
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
        project_id: int
    ) -> Dict[str, Any]:
        """
        동일 프로젝트의 이전 유효 촬영 기록(ShootingPath)을 조회하여
        이전 보정 경로(corrected_waypoints)를 다음 회차의 권장 경로로 승계 반환
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

        # 이전 유효 보정 경로가 존재하는 경우 승계
        if latest_valid_path and latest_valid_path.corrected_waypoints:
            recs = latest_valid_path.corrected_waypoints
            is_inherited = True
            source_info = f"이전 {latest_valid_path.shooting_number}회차의 AI 보정 동선을 차기 {next_number}회차 권장 경로로 승계했습니다."
            prev_deviation = latest_valid_path.deviation_score
            prev_reason = latest_valid_path.deviation_reason
        else:
            # 신규 사용자이거나 유효 보정 기록이 없는 경우: 기본 프로젝트 템플릿 유지
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
            "recommended_waypoints": recs
        }


# 싱글톤 인스턴스
path_service = ShootingPathService()
