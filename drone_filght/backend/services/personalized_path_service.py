"""
Phase 9: Personalized Shooting Path Variation Engine
사용자별 맞춤 촬영 경로 변형 서비스

핵심 원칙:
1. Phase 8의 ProjectCommonPath(공통 권장 경로) 원본은 불변(Immutability)으로 유지
2. 사용자의 과거 PHONE_GPS 보행 궤적, 이탈도, 선호 기법(Phase 5), 만족도(Phase 6/8)를 분석하여 맞춤 경로 생성
3. 3가지 변형 유형 지원:
   - A. STRAIGHT (직선형): 공통 권장 동선 최적 유지, 안정된 선형 페이싱
   - B. ZIGZAG (지그재그형): 시점/종점 유지, 중간 구간 직교 교차 보행(±2m) 반영
   - C. POI_WAYPOINT (주요 촬영 지점 경유형): 프로젝트 장소 자료(LocationAsset) 및 피사체 지향 경유 후 복귀
   - Cold Start: 이력이 부족한 신규 사용자는 공통 권장 경로를 기본 제공
4. 원본 공통 경로 버전(base_common_version) 연동 및 버전 갱신 감지(Staleness Check)
5. 단말기 지상 보행 경로(PHONE_GPS)만을 엄격히 다루며, 가상 드론 비행 데이터를 생성하지 않음
"""

import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.models.models import (
    ShootingProject,
    ShootingPath,
    ShootingAnalysis,
    ProjectCommonPath,
    LocationAsset,
    UserPreferenceScore,
    PersonalizedShootingPath,
    User
)
from backend.services.path_service import (
    path_service,
    haversine_distance,
    lat_lon_to_meters,
    meters_to_lat_lon,
    extract_wp_coordinate,
    generate_default_recommended_waypoints
)
from backend.services.collaborative_path_service import collaborative_path_service


class PersonalizedPathService:
    """Phase 9 개인별 맞춤 촬영 경로 변형 엔진"""

    def analyze_user_shooting_profile(
        self,
        db: Session,
        user_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """
        사용자의 과거 촬영 이력, 이탈도, 선호 기법을 다각도로 분석하여 변형 유형을 판별
        """
        # 1. 과거 유효 보행 촬영 이력 조회
        past_paths = db.query(ShootingPath).filter(
            ShootingPath.user_id == user_id,
            ShootingPath.is_valid == True
        ).order_by(ShootingPath.created_at.desc()).all()

        # 2. 누적 기법 선호도 점수 조회 (Phase 5)
        pref_scores = db.query(UserPreferenceScore).filter(
            UserPreferenceScore.user_id == user_id,
            UserPreferenceScore.category == "technique"
        ).order_by(UserPreferenceScore.preference_score.desc()).all()

        # 3. 프로젝트 등록 장소 자료(LocationAsset) 중 실제 유효 좌표(lat, lng) 보유 여부 확인
        location_assets = db.query(LocationAsset).filter(
            LocationAsset.project_id == project_id
        ).all()

        valid_poi_assets = []
        for a in location_assets:
            feat = a.detected_features or {}
            if isinstance(feat, dict) and "lat" in feat and "lng" in feat:
                try:
                    plat = float(feat["lat"])
                    plon = float(feat["lng"])
                    if -90.0 <= plat <= 90.0 and -180.0 <= plon <= 180.0:
                        valid_poi_assets.append(a)
                except (ValueError, TypeError):
                    continue
        has_valid_poi = len(valid_poi_assets) > 0

        # Cold Start 판정: 과거 경로와 선호도 데이터가 모두 없는 경우
        if len(past_paths) == 0 and len(pref_scores) == 0:
            return {
                "variation_type": "COLD_START",
                "is_cold_start": True,
                "reason": "신규 사용자이므로 과거 촬영 이력 및 선호도가 없어 최신 공통 권장 경로를 기본 제공합니다.",
                "avg_deviation": 0.0,
                "top_technique": None,
                "has_location_assets": has_valid_poi,
                "has_valid_poi": has_valid_poi,
                "actual_poi_used": False
            }

        # 평균 횡방향 이탈도 산출 (보조 지표로 활용)
        dev_scores = [float(p.deviation_score) for p in past_paths if p.deviation_score is not None]
        avg_dev = round(sum(dev_scores) / len(dev_scores), 2) if dev_scores else 0.0

        # 이탈 원인 및 패턴 분석 (반복 관찰 패턴 vs 일회성 우회/GPS 오차 구분)
        reasons = [p.deviation_reason for p in past_paths if p.deviation_reason]
        dynamic_count = sum(1 for r in reasons if r == "DYNAMIC_EXPLORE")
        shake_count = sum(1 for r in reasons if r == "PHONE_SHAKE")
        detour_count = sum(1 for r in reasons if r in ["WALKING_DETOUR", "GPS_ACCURACY_LOW"])
        composition_count = sum(1 for r in reasons if r in ["COMPOSITION_OPTIMIZED", "OBSTACLE_AVOIDANCE"])

        # 최상위 선호 기법 식별 (Phase 5)
        top_tech = pref_scores[0].preference_value if pref_scores else None
        top_score = pref_scores[0].preference_score if pref_scores else 0.0
        is_poi_technique = top_tech in ["orbit_poi", "poi_orbit", "statue_focus"]
        is_dynamic_technique = top_tech in ["spiral_rise", "weaving", "dolly_zoom"]

        actual_poi_used = False

        # 성향 분류 로직
        # 1) 피사체 조준 및 랜드마크 경유 성향 (POI_WAYPOINT):
        #    선호 기법이 orbit/poi 이거나 구도 최적화 이탈 경험이 있고, 프로젝트에 '실제 유효 좌표가 등록된' 장소 자료가 존재하는 경우
        if (is_poi_technique or composition_count >= 1) and has_valid_poi:
            var_type = "POI_WAYPOINT"
            poi_title = valid_poi_assets[0].detected_features.get("title") or valid_poi_assets[0].asset_type
            reason = f"실제 등록된 피사체([{poi_title}]) 및 기법 선호도({top_tech or 'POI Focus'}, {top_score:.1f}점)를 반영하여 랜드마크 집중 경유 동선을 구성했습니다. (실제 POI 좌표 사용 여부: True)"
            actual_poi_used = True

        # 2) 지그재그 다각도 앵글 성향 (ZIGZAG):
        #    - Phase 5 동적/지그재그 기법(spiral_rise, weaving, dolly_zoom) 선호가 명확하거나
        #    - 과거 촬영에서 동적 탐색 패턴(DYNAMIC_EXPLORE)이 반복 관찰된 경우 (2회 이상 또는 1회 이상 + 보조지표 avg_dev >= 1.8m)
        #    - 단순 일회성 우회(detour_count)나 미세 흔들림/GPS 오차만으로는 ZIGZAG 성향을 확정하지 않음
        elif (is_dynamic_technique and top_score >= 70.0) or (dynamic_count >= 2) or (dynamic_count >= 1 and avg_dev >= 1.8):
            var_type = "ZIGZAG"
            reason = f"다각도 입체 앵글 기법({top_tech or '탐색적 보행'}) 선호 및 검증된 동적 보행 패턴(보조지표 평균이탈 {avg_dev}m)을 반영한 지그재그(±2m) 권장 가이드입니다. (⚠️ 보행 안전 육안 확인 필수)"

        # 3) 직선형 최적화 성향 (STRAIGHT): 기본값 및 안전 유지
        #    - 낮은 이탈도(< 1.8m)
        #    - 직진 패스 기법(reveal_flyover, tracking_shot 등) 선호
        #    - 일시적 우회나 GPS 오차 등으로 성향을 확실히 단정할 수 없는 경우 기본 공통 경로(STRAIGHT) 유지
        else:
            var_type = "STRAIGHT"
            if detour_count >= 1 and avg_dev >= 1.8:
                reason = f"일시적 우회 또는 환경적 이탈(보조지표 평균이탈 {avg_dev}m)이 감지되었으나 지그재그 촬영 성향이 지속 확인되지 않아 안정적인 직선형(STRAIGHT) 공통 권장 동선을 유지합니다."
            elif is_poi_technique and not has_valid_poi:
                reason = f"피사체 조준 기법({top_tech})을 선호하나 실제 좌표가 등록된 POI 에셋이 없어 안전한 직선형(STRAIGHT) 공통 권장 동선으로 대체 유지합니다. (실제 POI 좌표 사용 여부: False)"
            else:
                reason = f"평균 이탈도가 {avg_dev}m로 안정적이며 선형 패스 기법을 선호하여 공통 권장 동선의 부드러운 직진 페이싱(STRAIGHT)을 유지합니다."

        return {
            "variation_type": var_type,
            "is_cold_start": False,
            "reason": reason,
            "avg_deviation": avg_dev,
            "top_technique": top_tech,
            "has_location_assets": len(location_assets) > 0,
            "has_valid_poi": has_valid_poi,
            "actual_poi_used": actual_poi_used
        }

    def generate_personalized_path(
        self,
        db: Session,
        project_id: int,
        user_id: int,
        preferred_variation_type: Optional[str] = "AUTO",
        force_regenerate: bool = False
    ) -> PersonalizedShootingPath:
        """
        프로젝트의 최신 공통 경로(ProjectCommonPath)를 기준으로 사용자의 성향에 맞춘 변형 경로를 생성하고 DB에 영구 저장
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")

        # 1. 기준 공통 경로(ProjectCommonPath) 확인 (불변 원본)
        active_common = collaborative_path_service.get_active_common_path(db, project_id)
        if active_common and active_common.common_waypoints:
            base_wps = [dict(wp) for wp in active_common.common_waypoints]
            base_version = active_common.version
            common_path_id = active_common.id
        else:
            # 공통 학습 경로가 아직 없는 경우 기본 프로젝트 기획 웨이포인트 5개 생성
            ref_lat = project.latitude or 37.5284
            ref_lon = project.longitude or 126.9328
            mode_name = project.recommended_mode or "POI Orbit"
            base_wps = generate_default_recommended_waypoints(ref_lat, ref_lon, mode_name, count=5)
            base_version = 1
            common_path_id = None

        # 2. 기존 사용자 활성 개인화 경로 확인
        existing_pers = db.query(PersonalizedShootingPath).filter(
            PersonalizedShootingPath.project_id == project_id,
            PersonalizedShootingPath.user_id == user_id,
            PersonalizedShootingPath.is_active == True
        ).order_by(PersonalizedShootingPath.created_at.desc()).first()

        # 만약 기존 경로가 있고, 기준 공통 버전과 일치하며 강제 재생성이 아닌 경우 그대로 반환
        if existing_pers and not force_regenerate:
            if existing_pers.base_common_version == base_version:
                # 사용자가 명시적 변형 유형 변경을 요청하지 않은 경우 기존 유지
                if not preferred_variation_type or preferred_variation_type.upper() in ["AUTO", existing_pers.variation_type]:
                    return existing_pers

        # 3. 사용자 성향 분석
        profile = self.analyze_user_shooting_profile(db, user_id, project_id)

        target_type = (preferred_variation_type or "AUTO").upper()
        if target_type not in ["STRAIGHT", "ZIGZAG", "POI_WAYPOINT", "COLD_START"]:
            target_type = profile["variation_type"]

        reason = profile["reason"]
        if preferred_variation_type and preferred_variation_type.upper() in ["STRAIGHT", "ZIGZAG", "POI_WAYPOINT"]:
            target_type = preferred_variation_type.upper()
            reason = f"사용자 직접 선택 모드: [{target_type}] 맞춤 촬영 동선을 생성했습니다."

        # 4. 평면 직교 좌표계 투영 (원점: 공통 경로 1번 웨이포인트)
        first_lat, first_lon, _ = extract_wp_coordinate(base_wps[0])
        origin_lat = first_lat or project.latitude or 37.5284
        origin_lon = first_lon or project.longitude or 126.9328

        base_meters = []
        for bw in base_wps:
            lat, lon, _ = extract_wp_coordinate(bw)
            mx, my = lat_lon_to_meters(lat, lon, origin_lat, origin_lon)
            base_meters.append((mx, my, bw))

        K = len(base_meters)
        personalized_wps: List[Dict[str, Any]] = []
        style_meta: Dict[str, Any] = {
            "origin_lat": origin_lat,
            "origin_lon": origin_lon,
            "profile_analysis": profile
        }

        # ======================================================================
        # 변형 유형 A: STRAIGHT (직선형) & COLD_START
        # ======================================================================
        if target_type in ["STRAIGHT", "COLD_START"]:
            for k, (mx, my, raw_wp) in enumerate(base_meters):
                c_lat, c_lon = meters_to_lat_lon(mx, my, origin_lat, origin_lon)
                personalized_wps.append({
                    "seq": k + 1,
                    "lat": round(c_lat, 7),
                    "lng": round(c_lon, 7),
                    "target_heading": raw_wp.get("target_heading", 0.0),
                    "target_pitch": raw_wp.get("target_pitch", -10.0),
                    "action": "SMOOTH_LINEAR_WALK",
                    "guide_msg": f"직선형 맞춤 {k+1}구간: 흔들림을 최소화하며 일정한 선형 보행 페이스 유지"
                })
            style_meta["description"] = "공통 기준 궤적을 100% 보존한 선형 최적화 경로"

        # ======================================================================
        # 변형 유형 B: ZIGZAG (지그재그형)
        # ======================================================================
        elif target_type == "ZIGZAG":
            # 시작점(0)과 종료점(K-1)은 공통 경로에 견고하게 고정, 중간 구간에만 직교 교차 오프셋 부여
            lateral_offset_m = 2.0
            style_meta["lateral_offset_m"] = lateral_offset_m
            style_meta["safety_notice"] = "⚠️ [보행 안전 주의] 본 지그재그 동선은 시네마틱 화각 제안을 위한 촬영 가이드용 권장 동선입니다. 실제 보행 가능 구역(인도/차도 구분) 및 지형 장애물(난간/화단/가로수 등)이 자동 검증되지 않았으므로 보행 전 주변 환경을 반드시 육안 확인하세요."
            style_meta["is_safety_verified"] = False

            for k in range(K):
                mx, my, raw_wp = base_meters[k]

                if k == 0 or k == K - 1:
                    # 시작점과 종료점은 불변
                    off_x, off_y = mx, my
                    guide_act = "ANCHORED_START" if k == 0 else "ANCHORED_END"
                    guide_msg = f"지그재그 권장 {k+1}구간: 공통 경로 기준 위치 안착"
                else:
                    # 이전 점과 다음 점 사이의 진행 벡터 산출
                    prev_x, prev_y, _ = base_meters[k - 1]
                    next_x, next_y, _ = base_meters[k + 1]
                    vx = next_x - prev_x
                    vy = next_y - prev_y
                    v_len = math.hypot(vx, vy) or 1.0

                    # 진행 방향에 수직인 법선 벡터 (nx, ny)
                    nx = -vy / v_len
                    ny = vx / v_len

                    # 좌우 번갈아 가며 ±2.0m 오프셋 적용
                    sign = 1.0 if (k % 2 == 1) else -1.0
                    off_x = mx + (sign * lateral_offset_m * nx)
                    off_y = my + (sign * lateral_offset_m * ny)
                    guide_act = "ZIGZAG_WEAVE"
                    guide_msg = f"지그재그 권장 {k+1}구간: 좌/우 교차 보행({sign * lateral_offset_m:+.1f}m) 가이드 (주변 장애물 및 보행 안전 필수 확인)"

                c_lat, c_lon = meters_to_lat_lon(off_x, off_y, origin_lat, origin_lon)
                personalized_wps.append({
                    "seq": k + 1,
                    "lat": round(c_lat, 7),
                    "lng": round(c_lon, 7),
                    "target_heading": raw_wp.get("target_heading", 0.0),
                    "target_pitch": raw_wp.get("target_pitch", -10.0),
                    "action": guide_act,
                    "guide_msg": guide_msg
                })
            style_meta["description"] = "중간 구간에 좌우 ±2m 교차 변형을 가미한 촬영 가이드용 동선 (실제 보행 안전성 미검증, 현장 육안 확인 필수)"

        # ======================================================================
        # 변형 유형 C: POI_WAYPOINT (주요 촬영 지점 경유형)
        # ======================================================================
        elif target_type == "POI_WAYPOINT":
            # 프로젝트 등록 LocationAsset 중 실제 유효 위·경도 좌표가 등록된 피사체만 검색
            assets = db.query(LocationAsset).filter(
                LocationAsset.project_id == project_id
            ).all()

            found_asset = False
            poi_name = None
            p_lat, p_lon = None, None
            poi_mx, poi_my = 0.0, 0.0

            for a in assets:
                feat = a.detected_features or {}
                if isinstance(feat, dict) and "lat" in feat and "lng" in feat:
                    try:
                        plat = float(feat["lat"])
                        plon = float(feat["lng"])
                        if -90.0 <= plat <= 90.0 and -180.0 <= plon <= 180.0:
                            p_lat, p_lon = plat, plon
                            poi_mx, poi_my = lat_lon_to_meters(plat, plon, origin_lat, origin_lon)
                            poi_name = feat.get("title") or feat.get("name") or a.asset_type or "등록 장소 피사체"
                            found_asset = True
                            break
                    except (ValueError, TypeError):
                        continue

            # 실제 위·경도 좌표가 없는 경우 임의 가상 좌표(+4.5m)를 절대 생성하지 않고, 즉시 STRAIGHT로 안전 Fallback!
            if not found_asset:
                target_type = "STRAIGHT"
                reason = "유효한 위·경도 좌표가 등록된 장소 자료(LocationAsset)가 확인되지 않아 POI_WAYPOINT 생성을 중단하고 공통 권장 동선(STRAIGHT)으로 안전하게 대체 제공합니다. (실제 POI 좌표 사용 여부: False)"
                style_meta["poi_coord_verified"] = False
                style_meta["fallback_from"] = "POI_WAYPOINT"

                for k, (mx, my, raw_wp) in enumerate(base_meters):
                    c_lat, c_lon = meters_to_lat_lon(mx, my, origin_lat, origin_lon)
                    personalized_wps.append({
                        "seq": k + 1,
                        "lat": round(c_lat, 7),
                        "lng": round(c_lon, 7),
                        "target_heading": raw_wp.get("target_heading", 0.0),
                        "target_pitch": raw_wp.get("target_pitch", -10.0),
                        "action": "SMOOTH_LINEAR_WALK",
                        "guide_msg": f"직선형 대체 {k+1}구간: POI 좌표 부재로 공통 권장 동선 유지"
                    })
                style_meta["description"] = "등록된 POI 실제 좌표가 없어 공통 권장 동선으로 대체된 직선형 경로"
            else:
                style_meta["poi_coord_verified"] = True
                style_meta["poi_info"] = {
                    "name": poi_name,
                    "lat": p_lat,
                    "lng": p_lon,
                    "poi_meter_x": round(poi_mx, 2),
                    "poi_meter_y": round(poi_my, 2),
                    "is_verified": True
                }
                reason = f"실제 등록된 피사체 [{poi_name}] 좌표(위도 {p_lat:.6f}, 경도 {p_lon:.6f})를 바탕으로 집중 경유 동선을 생성했습니다. (실제 POI 좌표 사용 여부: True)"

                # 중간 구간을 실제 POI 지향점으로 60% 유인 후 자연스럽게 복귀
                mid_idx = K // 2
                for k in range(K):
                    mx, my, raw_wp = base_meters[k]

                    if k == mid_idx:
                        # 중간 지점을 POI 방향으로 60% 유인
                        detour_x = 0.40 * mx + 0.60 * poi_mx
                        detour_y = 0.40 * my + 0.60 * poi_my
                        c_lat, c_lon = meters_to_lat_lon(detour_x, detour_y, origin_lat, origin_lon)
                        act = "POI_DETOUR_FOCUS"
                        msg = f"주요 지점 경유 맞춤 {k+1}구간: [{poi_name}] 피사체로 근접 우회하여 집중 촬영"
                    elif k == mid_idx - 1:
                        # 진입 완충 구간 (25% 유인)
                        detour_x = 0.75 * mx + 0.25 * poi_mx
                        detour_y = 0.75 * my + 0.25 * poi_my
                        c_lat, c_lon = meters_to_lat_lon(detour_x, detour_y, origin_lat, origin_lon)
                        act = "POI_APPROACH"
                        msg = f"주요 지점 접근 {k+1}구간: [{poi_name}] 조준 진입"
                    elif k == mid_idx + 1:
                        # 복귀 완충 구간 (25% 유인)
                        detour_x = 0.75 * mx + 0.25 * poi_mx
                        detour_y = 0.75 * my + 0.25 * poi_my
                        c_lat, c_lon = meters_to_lat_lon(detour_x, detour_y, origin_lat, origin_lon)
                        act = "POI_RETURN"
                        msg = f"주요 지점 이탈 {k+1}구간: 피사체 촬영 완료 후 공통 권장 동선으로 부드럽게 복귀"
                    else:
                        c_lat, c_lon = meters_to_lat_lon(mx, my, origin_lat, origin_lon)
                        act = "SMOOTH_LINEAR_WALK"
                        msg = f"경유 연계 {k+1}구간: 공통 메인 동선 유지"

                    personalized_wps.append({
                        "seq": k + 1,
                        "lat": round(c_lat, 7),
                        "lng": round(c_lon, 7),
                        "target_heading": raw_wp.get("target_heading", 0.0),
                        "target_pitch": raw_wp.get("target_pitch", -10.0),
                        "action": act,
                        "guide_msg": msg
                    })
                style_meta["description"] = f"실제 좌표가 검증된 핵심 피사체([{poi_name}])를 정밀 경유 후 공통 권장 궤적으로 안전하게 복귀하는 동선"

        # 5. 기존 동일 사용자의 해당 프로젝트 활성 개인화 경로 비활성화
        if existing_pers:
            existing_pers.is_active = False

        # 6. 신규 PersonalizedShootingPath 레코드 저장
        new_pers_path = PersonalizedShootingPath(
            project_id=project_id,
            user_id=user_id,
            common_path_id=common_path_id,
            base_common_version=base_version,
            variation_type=target_type,
            personalized_waypoints=personalized_wps,
            generation_reason=reason,
            style_metadata=style_meta,
            is_active=True
        )
        db.add(new_pers_path)
        db.commit()
        db.refresh(new_pers_path)

        return new_pers_path

    def get_user_personalized_path(
        self,
        db: Session,
        project_id: int,
        user_id: int
    ) -> Optional[PersonalizedShootingPath]:
        """
        사용자의 최신 활성 개인화 경로를 조회 (없으면 None)
        """
        return db.query(PersonalizedShootingPath).filter(
            PersonalizedShootingPath.project_id == project_id,
            PersonalizedShootingPath.user_id == user_id,
            PersonalizedShootingPath.is_active == True
        ).order_by(PersonalizedShootingPath.created_at.desc()).first()

    def check_staleness(
        self,
        db: Session,
        pers_path: PersonalizedShootingPath
    ) -> Tuple[bool, Optional[int]]:
        """
        개인화 경로가 참조한 공통 경로 버전이 최신 공통 경로보다 구버전인지 판별
        """
        active_common = collaborative_path_service.get_active_common_path(db, pers_path.project_id)
        if not active_common:
            return False, pers_path.base_common_version

        is_stale = (pers_path.base_common_version < active_common.version)
        return is_stale, active_common.version

    def compare_with_common_path(
        self,
        db: Session,
        pers_path: PersonalizedShootingPath
    ) -> Dict[str, Any]:
        """
        공통 권장 경로 원본과 개인화 변형 경로 간의 차이 비교 분석
        """
        active_common = collaborative_path_service.get_active_common_path(db, pers_path.project_id)
        project = db.query(ShootingProject).filter(ShootingProject.id == pers_path.project_id).first()

        if active_common and active_common.common_waypoints:
            common_wps = active_common.common_waypoints
            c_ver = active_common.version
        else:
            ref_lat = project.latitude or 37.5284
            ref_lon = project.longitude or 126.9328
            common_wps = generate_default_recommended_waypoints(ref_lat, ref_lon, "POI Orbit", count=5)
            c_ver = 1

        is_stale, latest_ver = self.check_staleness(db, pers_path)

        # 웨이포인트별 거리 편차 요약 및 기하학적 비교 통계
        diff_msgs = []
        offsets = []
        for i in range(min(len(common_wps), len(pers_path.personalized_waypoints))):
            cw = common_wps[i]
            pw = pers_path.personalized_waypoints[i]
            dist = haversine_distance(cw["lat"], cw["lng"], pw["lat"], pw["lng"])
            offsets.append(dist)
            if dist > 0.05:
                diff_msgs.append(f"구간 {i+1}: {dist:.1f}m 편차 ({pw.get('action', 'WALK')})")

        total_common_dist = sum(
            haversine_distance(common_wps[i]["lat"], common_wps[i]["lng"], common_wps[i+1]["lat"], common_wps[i+1]["lng"])
            for i in range(len(common_wps) - 1)
        )
        pwps = pers_path.personalized_waypoints
        total_pers_dist = sum(
            haversine_distance(pwps[i]["lat"], pwps[i]["lng"], pwps[i+1]["lat"], pwps[i+1]["lng"])
            for i in range(len(pwps) - 1)
        )
        dist_diff = round(total_pers_dist - total_common_dist, 2)
        max_offset = round(max(offsets), 2) if offsets else 0.0
        avg_offset = round(sum(offsets) / len(offsets), 2) if offsets else 0.0

        poi_name = None
        if pers_path.style_metadata and isinstance(pers_path.style_metadata, dict):
            poi_info = pers_path.style_metadata.get("poi_info", {})
            if isinstance(poi_info, dict):
                poi_name = poi_info.get("name")

        diff_summary = f"변형 유형 [{pers_path.variation_type}] - 공통 v{c_ver} 대비 변형 구간 {len(diff_msgs)}곳 감지"
        if diff_msgs:
            diff_summary += " (" + ", ".join(diff_msgs[:3]) + ")"
        else:
            diff_summary += " (공통 경로와 좌표 100% 일치)"

        return {
            "project_id": pers_path.project_id,
            "user_id": pers_path.user_id,
            "common_path_version": c_ver,
            "variation_type": pers_path.variation_type,
            "generation_reason": pers_path.generation_reason,
            "is_stale": is_stale,
            "common_waypoints": common_wps,
            "personalized_waypoints": pers_path.personalized_waypoints,
            "waypoint_diff_summary": diff_summary,
            "total_common_distance_m": round(total_common_dist, 2),
            "total_personalized_distance_m": round(total_pers_dist, 2),
            "distance_diff_m": dist_diff,
            "max_offset_from_common_m": max_offset,
            "avg_offset_from_common_m": avg_offset,
            "poi_target_name": poi_name,
            "comparison_summary": diff_summary
        }


personalized_path_service = PersonalizedPathService()
