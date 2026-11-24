"""
Phase 8: Multi-User Collaborative Path Learning Engine
다중 사용자 공통 촬영 경로 학습 엔진

핵심 기능:
1. 동일 프로젝트에 참여한 다중 사용자(PHONE_GPS)의 보행 촬영 경로 및 결과 집계
2. 데이터 품질(GPS 정확도, AI 구도 점수, 사용자 만족도, 이탈 오차) 다면 평가
3. 저품질/이상치 경로 제외 및 고품질 우수 경로 가중치(Q^2) 부여
4. 호 진행률(Arc-length Progress) 기반 공간적 대응 결합
5. 기존 공통 경로가 있을 경우 점진적 버전 갱신 (Progressive Blending)
6. 신규 사용자에게 최신 공통 권장 경로 자동 제공
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


class CollaborativePathLearningService:
    """다중 사용자 공통 경로 학습 서비스"""

    @staticmethod
    def evaluate_path_quality(
        path: ShootingPath,
        db: Session,
        min_quality_threshold: float = 60.0,
        base_wps: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """
        단일 보행 경로의 종합 품질 점수 산출 및 공통 경로 반영 적격성 판정:
        1. 필수 유효성 검사 (is_valid, tracking_source, 포인트 수)
        2. GPS 이상치 및 제자리 떨림 제외 (GPS_ACCURACY_LOW, STATIONARY_DRIFT)
        3. 역방향 이동 감지 및 제외 (REVERSE_DIRECTION)
        4. 경로별 사용자 만족도 연결 (미응답 기본값 70점 vs 실제 응답 구분)
        5. 구도 점수(45%) + 사용자 만족도(35%) + 경로 안정성(20%) 결합
        """
        def fail_metric(msg: str) -> Dict[str, Any]:
            return {
                "path_id": path.path_id,
                "shooting_number": path.shooting_number,
                "user_id": path.user_id,
                "quality_score": 0.0,
                "composition_score": 0.0,
                "satisfaction_score": 0.0,
                "is_satisfaction_default": True,
                "satisfaction_source": "NONE",
                "deviation_score": float(path.deviation_score or 0.0),
                "is_qualified": False,
                "exclusion_reason": msg,
                "reason": msg
            }

        # 1. 기본 유효성 검사
        if not path.is_valid:
            return False, 0.0, fail_metric("경로 유효성 플래그가 False(무효)입니다.")

        if (path.tracking_source or "").upper() != "PHONE_GPS":
            return False, 0.0, fail_metric(f"출처({path.tracking_source})가 PHONE_GPS가 아닙니다.")

        raw_wps = path.actual_waypoints or []
        if len(raw_wps) < 2:
            return False, 0.0, fail_metric("실제 보행 웨이포인트가 2개 미만입니다.")

        # 유효 위경도 유효성 검사
        valid_coords = []
        for wp in raw_wps:
            lat, lon, _ = extract_wp_coordinate(wp)
            if lat is not None and lon is not None:
                valid_coords.append((lat, lon))
        if len(valid_coords) < 2:
            return False, 0.0, fail_metric("유효한 위경도 좌표를 가진 웨이포인트가 2개 미만입니다.")

        reason_code = (path.deviation_reason or "").upper()
        if reason_code in ["GPS_ACCURACY_LOW", "STATIONARY_DRIFT"]:
            return False, 0.0, fail_metric(f"GPS 오류 또는 제자리 떨림({reason_code}) 데이터입니다.")

        # 2. 역방향 보행 검증 (Reverse Direction Detection)
        ref_wps = base_wps or path.recommended_waypoints or []
        if ref_wps and len(ref_wps) >= 2 and len(valid_coords) >= 2:
            base_s_lat, base_s_lon, _ = extract_wp_coordinate(ref_wps[0])
            base_e_lat, base_e_lon, _ = extract_wp_coordinate(ref_wps[-1])
            act_s_lat, act_s_lon = valid_coords[0]
            act_e_lat, act_e_lon = valid_coords[-1]

            if all(v is not None for v in (base_s_lat, base_s_lon, base_e_lat, base_e_lon)):
                d_base_endpoints = haversine_distance(base_s_lat, base_s_lon, base_e_lat, base_e_lon)
                d_fwd_start = haversine_distance(act_s_lat, act_s_lon, base_s_lat, base_s_lon)
                d_fwd_end = haversine_distance(act_e_lat, act_e_lon, base_e_lat, base_e_lon)
                d_rev_start = haversine_distance(act_s_lat, act_s_lon, base_e_lat, base_e_lon)
                d_rev_end = haversine_distance(act_e_lat, act_e_lon, base_s_lat, base_s_lon)

                if d_base_endpoints >= 3.0:
                    # 개방형 직선/곡선 경로: 역방향 출발/도착 지점 합이 순방향보다 더 가까울 경우
                    if (d_rev_start + d_rev_end) < (d_fwd_start + d_fwd_end) and d_rev_start < d_fwd_start:
                        return False, 0.0, fail_metric("권장 동선의 역방향으로 이동한 경로(REVERSE_DIRECTION)이므로 공통 학습 대상에서 제외되었습니다.")
                else:
                    # 원형 궤적(Orbit 등)의 경우: 1/4 시점의 횡방향 진행 방향 비교
                    idx_q_base = max(1, len(ref_wps) // 4)
                    idx_3q_base = max(idx_q_base + 1, (3 * len(ref_wps)) // 4)
                    q_b_lat, q_b_lon, _ = extract_wp_coordinate(ref_wps[idx_q_base])
                    tq_b_lat, tq_b_lon, _ = extract_wp_coordinate(ref_wps[idx_3q_base])
                    idx_q_act = max(1, len(valid_coords) // 4)
                    act_q_lat, act_q_lon = valid_coords[idx_q_act]

                    if all(v is not None for v in (q_b_lat, q_b_lon, tq_b_lat, tq_b_lon)):
                        dist_fwd_quarter = haversine_distance(act_q_lat, act_q_lon, q_b_lat, q_b_lon)
                        dist_rev_quarter = haversine_distance(act_q_lat, act_q_lon, tq_b_lat, tq_b_lon)
                        if dist_rev_quarter < dist_fwd_quarter and (dist_fwd_quarter - dist_rev_quarter) > 3.0:
                            return False, 0.0, fail_metric("원형 궤적을 반대 방향으로 회전한 경로(REVERSE_DIRECTION)이므로 공통 학습 대상에서 제외되었습니다.")

        # 3. 구도 달성도 점수 (S_comp, 0~100)
        comp_scores = []
        for wp in raw_wps:
            c_state = wp.get("composition_state", {}) if isinstance(wp, dict) else {}
            if "frame_score" in c_state and c_state["frame_score"] is not None:
                comp_scores.append(float(c_state["frame_score"]))

        if comp_scores:
            s_comp = sum(comp_scores) / len(comp_scores)
        else:
            # ShootingAnalysis에서 보충 조회
            analysis = db.query(ShootingAnalysis).filter(
                ShootingAnalysis.project_id == path.project_id,
                ShootingAnalysis.analysis_status == "completed"
            ).order_by(ShootingAnalysis.created_at.desc()).first()
            s_comp = float(analysis.composition_score) if (analysis and analysis.composition_score) else 75.0

        # 4. 사용자 만족도 점수 (S_sat, 20~100) 및 경로별 정밀 연결
        s_sat = 70.0  # 기본 만족도 (3.5점 상당)
        is_sat_default = True
        sat_source = "DEFAULT_BASELINE"

        if path.project_id:
            # 해당 path의 shooting_number 및 user_id와 일치하는 피드백 검색
            analyses = db.query(ShootingAnalysis).filter(
                ShootingAnalysis.project_id == path.project_id
            ).order_by(ShootingAnalysis.created_at.desc()).all()

            matched_fb = None
            for an in analyses:
                coords = an.target_coordinates if isinstance(an.target_coordinates, dict) else {}
                # 1) feedbacks_by_round 맵에서 검색
                by_round = coords.get("feedbacks_by_round", {})
                if str(path.shooting_number) in by_round:
                    rfb = by_round[str(path.shooting_number)]
                    if path.user_id is None or rfb.get("user_id") is None or rfb.get("user_id") == path.user_id:
                        matched_fb = rfb
                        break
                # 2) 단일 user_feedback 객체에서 검색 (기존 데이터 호환)
                ufb = coords.get("user_feedback", {})
                if isinstance(ufb, dict) and ufb.get("shooting_number") == path.shooting_number:
                    if path.user_id is None or ufb.get("user_id") is None or ufb.get("user_id") == path.user_id:
                        matched_fb = ufb
                        break

            if matched_fb and "satisfaction_score" in matched_fb:
                raw_score = float(matched_fb["satisfaction_score"])
                s_sat = max(20.0, min(100.0, raw_score * 20.0))
                is_sat_default = False
                sat_source = f"USER_FEEDBACK(round={path.shooting_number}, score={raw_score})"

        # 5. 경로 완성도 및 안정성 (S_dev, 0~100)
        # 이탈도가 작을수록 높은 점수 부여 (1m 이탈 당 10점 감점)
        dev = float(path.deviation_score) if path.deviation_score is not None else 2.5
        s_dev = max(0.0, min(100.0, 100.0 - (dev * 10.0)))

        # 6. 종합 품질 점수 계산 (Quality Score)
        quality_score = round((0.45 * s_comp) + (0.35 * s_sat) + (0.20 * s_dev), 1)

        is_qualified = quality_score >= min_quality_threshold
        metrics = {
            "path_id": path.path_id,
            "shooting_number": path.shooting_number,
            "user_id": path.user_id,
            "quality_score": quality_score,
            "composition_score": round(s_comp, 1),
            "satisfaction_score": round(s_sat, 1),
            "is_satisfaction_default": is_sat_default,
            "satisfaction_source": sat_source,
            "deviation_score": round(dev, 2),
            "is_qualified": is_qualified,
            "exclusion_reason": None if is_qualified else f"품질 점수({quality_score}점)가 기준({min_quality_threshold}점) 미만입니다."
        }
        return is_qualified, quality_score, metrics

    def learn_project_common_path(
        self,
        db: Session,
        project_id: int,
        min_quality_threshold: float = 60.0,
        max_paths: int = 50,
        current_user: Optional[User] = None
    ) -> ProjectCommonPath:
        """
        동일 프로젝트에 참여한 다중 사용자의 PHONE_GPS 경로를 수집·학습하여
        버전이 관리되는 최신 공통 권장 경로(ProjectCommonPath)를 생성 및 갱신합니다.
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")

        # 1. 기준 투영 좌표계 및 기존 공통 경로 이력 조회
        ref_lat = project.latitude or 37.5284
        ref_lon = project.longitude or 126.9328
        mode_name = project.recommended_mode or "POI Orbit"

        active_common = db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == project_id,
            ProjectCommonPath.is_active == True
        ).order_by(ProjectCommonPath.version.desc()).first()

        all_prev_common = db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == project_id
        ).all()

        prev_evaluated_path_ids = set()
        prev_used_path_ids = set()
        prev_contributor_ids = set()
        for pc in all_prev_common:
            meta = pc.learning_metadata or {}
            prev_evaluated_path_ids.update(meta.get("evaluated_path_ids", []))
            prev_used_path_ids.update(meta.get("included_path_ids", []))
            prev_used_path_ids.update(meta.get("all_used_path_ids", []))
            prev_contributor_ids.update(meta.get("contributor_user_ids", []))

        if active_common and active_common.common_waypoints:
            base_wps = active_common.common_waypoints
            base_version = active_common.version
            prev_total_used = len(prev_used_path_ids) if prev_used_path_ids else active_common.total_paths_used
            prev_contributors = len(prev_contributor_ids) if prev_contributor_ids else active_common.contributor_count
        else:
            base_wps = generate_default_recommended_waypoints(ref_lat, ref_lon, mode_name, count=5)
            base_version = 0
            prev_total_used = 0
            prev_contributors = 0

        # 2. 신규 보행 경로 조회 (이전 학습에서 이미 처리/평가된 ShootingPath 제외)
        candidate_query = db.query(ShootingPath).filter(ShootingPath.project_id == project_id)
        if prev_evaluated_path_ids:
            candidate_query = candidate_query.filter(~ShootingPath.path_id.in_(prev_evaluated_path_ids))
        elif prev_used_path_ids:
            candidate_query = candidate_query.filter(~ShootingPath.path_id.in_(prev_used_path_ids))
        elif active_common and active_common.created_at:
            candidate_query = candidate_query.filter(ShootingPath.created_at > active_common.created_at)

        candidate_paths = candidate_query.order_by(ShootingPath.created_at.asc()).limit(max_paths).all()

        if not candidate_paths:
            if active_common:
                raise HTTPException(
                    status_code=400,
                    detail=f"기존 v{active_common.version} 공통 경로 이후 새롭게 추가된 촬영 동선 데이터가 없습니다."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="학습할 수 있는 촬영 동선 데이터가 프로젝트에 존재하지 않습니다."
                )

        # 3. 각 신규 경로 품질 평가 및 필터링 (역방향 감지 및 피드백 연결)
        qualified_paths: List[ShootingPath] = []
        path_qualities: List[float] = []
        eval_reports: List[Dict[str, Any]] = []

        for p in candidate_paths:
            ok, q_score, rpt = self.evaluate_path_quality(p, db, min_quality_threshold, base_wps=base_wps)
            eval_reports.append(rpt)
            if ok:
                qualified_paths.append(p)
                path_qualities.append(q_score)

        if not qualified_paths:
            raise HTTPException(
                status_code=422,
                detail=f"제출된 {len(candidate_paths)}개 신규 경로 중 최소 품질 기준({min_quality_threshold}점)을 충족하는 유효 경로가 없습니다."
            )

        # 4. 신규 배치 품질 점수 기반 가중치 정규화 (Q^2 파워 가중치)
        q_squared_sum = sum(q ** 2 for q in path_qualities)
        weights = [(q ** 2) / q_squared_sum for q in path_qualities]

        # 첫 번째 기준점 (투영 원점)
        first_r_lat, first_r_lon, _ = extract_wp_coordinate(base_wps[0])
        origin_lat = first_r_lat or ref_lat
        origin_lon = first_r_lon or ref_lon

        # 5. 각 유효 경로를 로컬 평면 직교 좌표 (mx, my)로 변환
        all_act_meters: List[List[Tuple[float, float, Any]]] = []
        contributor_user_ids = set()

        for p in qualified_paths:
            if p.user_id:
                contributor_user_ids.add(p.user_id)
            meters_list = []
            for wp in (p.actual_waypoints or []):
                lat, lon, _ = extract_wp_coordinate(wp)
                if lat is not None and lon is not None:
                    mx, my = lat_lon_to_meters(lat, lon, origin_lat, origin_lon)
                    meters_list.append((mx, my, wp))
            if len(meters_list) >= 2:
                all_act_meters.append(meters_list)

        if not all_act_meters:
            raise HTTPException(status_code=422, detail="유효한 좌표를 가진 보행 경로가 부족합니다.")

        # 기준 템플릿 미터 변환
        base_meters = []
        for bw in base_wps:
            blat, blon, _ = extract_wp_coordinate(bw)
            if blat is not None and blon is not None:
                bmx, bmy = lat_lon_to_meters(blat, blon, origin_lat, origin_lon)
                base_meters.append((bmx, bmy, bw))

        K = max(5, len(base_meters))
        learned_meters: List[Tuple[float, float]] = []

        # 6. 호 진행률(Arc-length Progress s in [0, 1]) 기준 가중 공간 집계
        for k in range(K):
            s = k / max(1, K - 1)  # 진행률 0.0 ~ 1.0

            # 이번 배치에서 학습된 가중 평균 위치 산출
            batch_x = 0.0
            batch_y = 0.0
            for i, p_meters in enumerate(all_act_meters):
                sample_pos = path_service._sample_polyline(p_meters, s)
                w = weights[i]
                batch_x += w * sample_pos[0]
                batch_y += w * sample_pos[1]

            # 7. 기존 공통 경로가 있을 경우 점진적 지수 블렌딩 (Progressive Update)
            if active_common and base_meters:
                prev_pos = path_service._sample_polyline(base_meters, s)
                # 새로운 배치 기여 가중치 (이전 누적 고유 경로 수 N_prev와 현재 신규 배치 경로 수 M의 조화)
                m_count = len(qualified_paths)
                beta = min(0.65, max(0.25, m_count / float(prev_total_used + m_count)))
                final_x = (1.0 - beta) * prev_pos[0] + beta * batch_x
                final_y = (1.0 - beta) * prev_pos[1] + beta * batch_y
            else:
                # 초기 버전: 기획 기준선(35%)과 다중 사용자 보행 집계(65%) 블렌딩
                base_pos = path_service._sample_polyline(base_meters, s)
                final_x = 0.35 * base_pos[0] + 0.65 * batch_x
                final_y = 0.35 * base_pos[1] + 0.65 * batch_y

            learned_meters.append((final_x, final_y))

        # 8. 최종 평면 좌표를 다시 위경도로 역투영하여 common_waypoints 빌드
        new_version = base_version + 1
        common_wps: List[Dict[str, Any]] = []

        for k, (lx, ly) in enumerate(learned_meters):
            c_lat, c_lon = meters_to_lat_lon(lx, ly, origin_lat, origin_lon)
            guide_r = base_wps[min(k, len(base_wps) - 1)]
            target_heading = guide_r.get("target_heading", 0.0)
            target_pitch = guide_r.get("target_pitch", -10.0)

            common_wps.append({
                "seq": k + 1,
                "lat": round(c_lat, 7),
                "lng": round(c_lon, 7),
                "target_heading": target_heading,
                "target_pitch": target_pitch,
                "action": guide_r.get("action", "SMOOTH_WALK"),
                "guide_msg": f"공통 학습 {k+1}구간: 참여자 {len(contributor_user_ids)}명의 우수 동선이 집약된 v{new_version} 권장 경로"
            })

        # 9. 평균 통계 지표 산출
        avg_q = sum(path_qualities) / len(path_qualities)
        avg_comp = sum(r["composition_score"] for r in eval_reports if r["is_qualified"]) / len(qualified_paths)
        avg_sat = sum(r["satisfaction_score"] for r in eval_reports if r["is_qualified"]) / len(qualified_paths)
        avg_dev = sum(r["deviation_score"] for r in eval_reports if r["is_qualified"]) / len(qualified_paths)

        # 10. 기존 활성 버전 비활성화
        if active_common:
            active_common.is_active = False

        # 11. 고유 경로 ID 및 참여자 ID 누적 (중복 카운트 방지)
        new_evaluated_ids = [p.path_id for p in candidate_paths]
        cumulative_evaluated_ids = list(prev_evaluated_path_ids.union(new_evaluated_ids))
        new_included_ids = [p.path_id for p in qualified_paths]
        cumulative_path_ids = list(prev_used_path_ids.union(new_included_ids))
        cumulative_contributors = list(prev_contributor_ids.union(contributor_user_ids))

        total_used_count = len(cumulative_path_ids)
        total_contributors = len(cumulative_contributors) if cumulative_contributors else max(len(contributor_user_ids), prev_contributors)

        new_common_path = ProjectCommonPath(
            project_id=project_id,
            version=new_version,
            common_waypoints=common_wps,
            contributor_count=total_contributors,
            total_paths_used=total_used_count,
            quality_score=round(avg_q, 1),
            average_deviation_m=round(avg_dev, 2),
            average_composition_score=round(avg_comp, 1),
            average_satisfaction_score=round(avg_sat, 1),
            learning_metadata={
                "evaluated_paths_count": len(candidate_paths),
                "qualified_paths_count": len(qualified_paths),
                "evaluated_path_ids": cumulative_evaluated_ids,
                "included_path_ids": new_included_ids,
                "all_used_path_ids": cumulative_path_ids,
                "contributor_user_ids": cumulative_contributors,
                "weights_applied": [round(w, 4) for w in weights],
                "evaluated_reports": eval_reports,
                "learned_at": datetime.utcnow().isoformat()
            },
            is_active=True
        )
        db.add(new_common_path)
        db.commit()
        db.refresh(new_common_path)

        return new_common_path

    @staticmethod
    def get_active_common_path(db: Session, project_id: int) -> Optional[ProjectCommonPath]:
        """프로젝트의 최신 활성 공통 권장 경로 조회"""
        return db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == project_id,
            ProjectCommonPath.is_active == True
        ).order_by(ProjectCommonPath.version.desc()).first()

    @staticmethod
    def get_common_path_history(db: Session, project_id: int) -> List[ProjectCommonPath]:
        """프로젝트의 버전별 공통 권장 경로 업데이트 이력 조회"""
        return db.query(ProjectCommonPath).filter(
            ProjectCommonPath.project_id == project_id
        ).order_by(ProjectCommonPath.version.desc()).all()


collaborative_path_service = CollaborativePathLearningService()
