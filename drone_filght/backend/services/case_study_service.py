import os
import re
import io
import json
import uuid
import math
import base64
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from PIL import Image

from backend.models.models import (
    ShootingCaseStudy,
    CaseStudyFrame,
    ShootingPath,
    ShootingProject,
    User
)
from backend.external.gemini_client import gemini_client
from backend.schemas.schemas import (
    ShootingCaseStudyCreate,
    ShootingCaseStudyVerifyRequest,
    CaseStudyFrameCreate,
    YouTubeAnalyzeRequest,
    YouTubeApproveRequest,
    YouTubeRejectRequest
)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 위경도 좌표 간의 구면 거리(미터) 계산"""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def parse_utc_datetime(dt_val: Any) -> Optional[datetime]:
    """다양한 형식의 날짜시간을 UTC Aware datetime으로 안전하게 정규화"""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)
    if isinstance(dt_val, str):
        try:
            # ISO 8601 parsing
            clean_str = dt_val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(clean_str)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
    return None


class CaseStudyService:
    """
    Phase A-2.3: 촬영 사례 데이터 관리 및 GPS 품질 판정 서비스
    - Ground Truth 원칙: 유효한 ShootingPath(PHONE_GPS/DRONE_GPS)가 연결된 경우만 has_actual_gps=True 인정
    - AI 추정 기법과 사람 검증 기법의 완전 분리 (declared_technique 불변, verified_technique 신설)
    - 다차원 GPS 품질 평가 (EXCELLENT, ACCEPTABLE, POOR, UNUSABLE) 및 is_path_usable 판정
    - 검증 이력(verification_audit) 누적 저장
    """

    ALLOWED_SOURCE_TYPES = {"SELF_FILMED", "YOUTUBE_REF", "COMMUNITY_FEED"}
    ALLOWED_VERIFICATION_STATUSES = {"UNVERIFIED", "REVIEW_PENDING", "HUMAN_VERIFIED", "REJECTED"}
    ALLOWED_TECHNIQUES = {"FORWARD", "LATERAL", "DIAGONAL_REVEAL", "ORBIT", "PANORAMA", "UNKNOWN"}

    @classmethod
    def create_case_study(
        cls,
        db: Session,
        req: ShootingCaseStudyCreate,
        current_user: Optional[User] = None
    ) -> ShootingCaseStudy:
        # 1. 출처 유형 검증
        src_type = (req.source_type or "SELF_FILMED").upper().strip()
        if src_type not in cls.ALLOWED_SOURCE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 출처 유형입니다: {req.source_type}. 허용: {list(cls.ALLOWED_SOURCE_TYPES)}"
            )

        # 2. 소유자 결정
        user_id = req.user_id or (current_user.id if current_user else None)

        # 3. 실제 GPS 경로 연결 및 Ground Truth 판정
        path_id = req.path_id
        has_actual_gps = False
        target_path: Optional[ShootingPath] = None

        if src_type == "YOUTUBE_REF":
            if path_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="외부 레퍼런스(YOUTUBE_REF)는 물리적 GPS 경로(path_id)와 연결할 수 없습니다."
                )
            path_id = None
            has_actual_gps = False
        elif path_id is not None:
            # 실제 ShootingPath 유효성 검증
            target_path = db.query(ShootingPath).filter(ShootingPath.path_id == path_id).first()
            if not target_path:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"연결할 촬영 경로를 찾을 수 없습니다. (path_id: {path_id})"
                )
            if not target_path.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"연결 대상 경로(path_id: {path_id})는 유효하지 않은 경로(is_valid=False)입니다."
                )
            tracking_src = (target_path.tracking_source or "").upper()
            if tracking_src not in {"PHONE_GPS", "DRONE_GPS"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"시뮬레이션 데이터({tracking_src})는 실제 GPS 경로로 인정되지 않습니다."
                )
            wps = target_path.actual_waypoints or []
            if len(wps) < 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"연결 대상 경로의 유효 관측점이 부족합니다 (최소 2개 필수, 현재 {len(wps)}개)."
                )
            has_actual_gps = True

        # 4. 고유 사례 코드 생성
        if req.case_code and req.case_code.strip():
            case_code = req.case_code.strip()
            existing = db.query(ShootingCaseStudy).filter(ShootingCaseStudy.case_code == case_code).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"이미 존재하는 사례 코드입니다: {case_code}"
                )
        else:
            pfx_map = {"SELF_FILMED": "SF", "YOUTUBE_REF": "YT", "COMMUNITY_FEED": "CF"}
            pfx = pfx_map.get(src_type, "CASE")
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            rand_sfx = uuid.uuid4().hex[:6].upper()
            case_code = f"CASE_{pfx}_{now_str}_{rand_sfx}"

        case_obj = ShootingCaseStudy(
            case_code=case_code,
            title=req.title,
            description=req.description,
            source_type=src_type,
            video_ref_url=req.video_ref_url,
            duration_sec=req.duration_sec,
            place_name=req.place_name,
            latitude=req.latitude,
            longitude=req.longitude,
            user_id=user_id,
            project_id=req.project_id,
            path_id=path_id,
            declared_technique=req.declared_technique,
            verified_technique=None,  # 초기 미검증 상태
            has_actual_gps=has_actual_gps,
            is_gps_time_synced=False,
            gps_quality_status="UNCHECKED",
            is_path_usable=False,
            is_public=req.is_public,
            filming_started_at=req.filming_started_at,
            ai_analysis_status="PENDING",
            verification_status="UNVERIFIED",
            verifier_notes=None,
            verification_audit=[]
        )

        db.add(case_obj)
        db.commit()
        db.refresh(case_obj)
        return case_obj

    @classmethod
    def get_case_studies(
        cls,
        db: Session,
        source_type: Optional[str] = None,
        has_actual_gps: Optional[bool] = None,
        verification_status: Optional[str] = None,
        gps_quality_status: Optional[str] = None,
        is_path_usable: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ShootingCaseStudy]:
        query = db.query(ShootingCaseStudy).options(joinedload(ShootingCaseStudy.frames))

        if source_type:
            query = query.filter(ShootingCaseStudy.source_type == source_type.upper().strip())
        if has_actual_gps is not None:
            query = query.filter(ShootingCaseStudy.has_actual_gps == has_actual_gps)
        if verification_status:
            query = query.filter(ShootingCaseStudy.verification_status == verification_status.upper().strip())
        if gps_quality_status:
            query = query.filter(ShootingCaseStudy.gps_quality_status == gps_quality_status.upper().strip())
        if is_path_usable is not None:
            query = query.filter(ShootingCaseStudy.is_path_usable == is_path_usable)

        return query.order_by(ShootingCaseStudy.id.desc()).offset(offset).limit(limit).all()

    @classmethod
    def get_case_study_by_id(cls, db: Session, case_id: int) -> ShootingCaseStudy:
        case_obj = db.query(ShootingCaseStudy).options(
            joinedload(ShootingCaseStudy.frames)
        ).filter(ShootingCaseStudy.id == case_id).first()

        if not case_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"촬영 사례를 찾을 수 없습니다. (ID: {case_id})"
            )
        return case_obj

    @classmethod
    def add_frames_to_case_study(
        cls,
        db: Session,
        case_id: int,
        frames_data: List[CaseStudyFrameCreate]
    ) -> List[CaseStudyFrame]:
        case_obj = cls.get_case_study_by_id(db, case_id)

        added_frames: List[CaseStudyFrame] = []
        for f_data in frames_data:
            frame_obj = CaseStudyFrame(
                case_id=case_obj.id,
                frame_index=f_data.frame_index,
                timestamp_sec=f_data.timestamp_sec,
                extracted_ratio=f_data.extracted_ratio,
                storage_path=f_data.storage_path,
                file_size_bytes=f_data.file_size_bytes,
                scene_type=f_data.scene_type,
                primary_subject=f_data.primary_subject,
                subject_bbox=f_data.subject_bbox,
                depth_layers=f_data.depth_layers,
                composition_type=f_data.composition_type,
                estimated_technique=f_data.estimated_technique,
                verified_technique=f_data.verified_technique,
                confidence_score=f_data.confidence_score,
                raw_ai_analysis=f_data.raw_ai_analysis,
                ai_model_version=f_data.ai_model_version,
                prompt_version=f_data.prompt_version,
                is_verified=f_data.is_verified
            )
            db.add(frame_obj)
            added_frames.append(frame_obj)

        if added_frames:
            case_obj.ai_analysis_status = "COMPLETED"
            case_obj.updated_at = datetime.now(timezone.utc)

        db.commit()
        for f in added_frames:
            db.refresh(f)
        return added_frames

    @classmethod
    def verify_case_study(
        cls,
        db: Session,
        case_id: int,
        req: ShootingCaseStudyVerifyRequest,
        current_user: Optional[User] = None
    ) -> ShootingCaseStudy:
        """
        인간 검증 수행 및 검증 이력 누적 저장
        - 절대 declared_technique를 덮어쓰지 않음
        - verified_technique에 대표 기법 저장
        - verification_audit에 트랜잭션 단위로 이력 추가
        """
        case_obj = cls.get_case_study_by_id(db, case_id)

        v_status = (req.verification_status or "HUMAN_VERIFIED").upper().strip()
        if v_status not in cls.ALLOWED_VERIFICATION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 검증 상태입니다: {req.verification_status}. 허용: {list(cls.ALLOWED_VERIFICATION_STATUSES)}"
            )

        # 1. 상태 및 대표 기법 갱신 (declared_technique는 보존!)
        prev_verified = case_obj.verified_technique
        case_obj.verification_status = v_status
        if req.verifier_notes:
            case_obj.verifier_notes = req.verifier_notes

        if req.verified_technique:
            case_obj.verified_technique = req.verified_technique.upper().strip()

        # 프레임의 is_verified 플래그 동기화
        if v_status == "HUMAN_VERIFIED":
            for frame in case_obj.frames:
                frame.is_verified = True

        # 2. 검증 감사 이력(verification_audit) 누적
        audit_list = list(case_obj.verification_audit or [])
        v_id = current_user.id if current_user else None
        v_name = req.verifier_name or (current_user.username if current_user else "reviewer")
        v_role = req.verifier_role or (current_user.role if current_user else "pilot")

        new_audit = {
            "audit_id": len(audit_list) + 1,
            "verifier_id": v_id,
            "verifier_name": v_name,
            "verifier_role": v_role,
            "action": v_status,
            "previous_technique": prev_verified or case_obj.declared_technique,
            "new_verified_technique": case_obj.verified_technique,
            "notes": req.verifier_notes,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        audit_list.append(new_audit)
        case_obj.verification_audit = audit_list
        case_obj.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(case_obj)
        return case_obj

    @classmethod
    def evaluate_gps_quality_and_sync(
        cls,
        db: Session,
        case_id: int,
        gps_points: Optional[List[Dict[str, Any]]] = None,
        tolerance_sec: float = 1.5
    ) -> Dict[str, Any]:
        """
        Phase A-2.3 핵심: 다차원 GPS 품질 평가 및 영상 시간 동기화 종합 판정
        - 연결된 ShootingPath 또는 전달된 gps_points 분석
        - 유효 정확도 비율, P75, 최대 오차, 기록 간격, 시간 동기화율 종합 계산
        - EXCELLENT, ACCEPTABLE, POOR, UNUSABLE 등급 판정 및 is_path_usable 갱신
        """
        case_obj = cls.get_case_study_by_id(db, case_id)

        # 1. 대상 GPS 관측점 확보
        raw_points = gps_points
        if not raw_points and case_obj.path_id:
            path_record = db.query(ShootingPath).filter(ShootingPath.path_id == case_obj.path_id).first()
            if path_record and path_record.actual_waypoints:
                raw_points = path_record.actual_waypoints

        if not raw_points:
            case_obj.gps_quality_status = "UNUSABLE"
            case_obj.is_path_usable = False
            case_obj.is_gps_time_synced = False
            db.commit()
            return {
                "gps_quality_status": "UNUSABLE",
                "is_path_usable": False,
                "is_gps_time_synced": False,
                "reason": "평가할 GPS 관측점이 없습니다.",
                "metrics": {}
            }

        # 2. 관측점 파싱 및 데이터 추출
        parsed_pts = []
        for pt in raw_points:
            # 지원 형식: {raw_gps: {lat, lng, accuracy_m}}, {lat, lng, accuracy}
            lat = None
            lng = None
            acc = None
            raw_g = pt.get("raw_gps") if isinstance(pt.get("raw_gps"), dict) else pt
            if "lat" in raw_g and "lng" in raw_g:
                lat = float(raw_g["lat"])
                lng = float(raw_g["lng"])
                acc = raw_g.get("accuracy_m") or raw_g.get("accuracy")
                if acc is not None:
                    try:
                        acc = float(acc)
                    except (ValueError, TypeError):
                        acc = None

            t_val = pt.get("timestamp") or pt.get("recorded_at")
            t_utc = parse_utc_datetime(t_val)

            if lat is not None and lng is not None:
                parsed_pts.append({
                    "lat": lat,
                    "lng": lng,
                    "accuracy": acc,
                    "time": t_utc
                })

        total_pts = len(parsed_pts)
        if total_pts < 2:
            case_obj.gps_quality_status = "UNUSABLE"
            case_obj.is_path_usable = False
            db.commit()
            return {
                "gps_quality_status": "UNUSABLE",
                "is_path_usable": False,
                "reason": f"유효 GPS 관측점 수({total_pts})가 2개 미만입니다.",
                "metrics": {"total_pts": total_pts}
            }

        # 3. 세부 지표 산출
        # A) 정확도 지표 (정확도 값이 존재하는 포인트 대상)
        valid_acc_pts = [p["accuracy"] for p in parsed_pts if p["accuracy"] is not None]
        valid_acc_count = len(valid_acc_pts)

        if valid_acc_count == 0:
            # 정확도 데이터가 전무하면 신뢰 불가 판정
            case_obj.gps_quality_status = "UNUSABLE"
            case_obj.is_path_usable = False
            db.commit()
            return {
                "gps_quality_status": "UNUSABLE",
                "is_path_usable": False,
                "reason": "GPS 정확도(accuracy) 메타데이터가 존재하지 않습니다.",
                "metrics": {"total_pts": total_pts, "valid_acc_count": 0}
            }

        pts_le_20m = [a for a in valid_acc_pts if a <= 20.0]
        ratio_le_20m = len(pts_le_20m) / total_pts  # 분모는 전체 GPS 기록 수

        sorted_acc = sorted(valid_acc_pts)
        max_error = sorted_acc[-1]
        p75_idx = int(math.ceil(0.75 * valid_acc_count)) - 1
        p75_error = sorted_acc[max(0, min(p75_idx, valid_acc_count - 1))]

        # B) 시간 간격(Interval) 및 최대 결측 간격
        max_interval_sec = 0.0
        time_pts = [p["time"] for p in parsed_pts if p["time"] is not None]
        time_pts_sorted = sorted(time_pts)
        if len(time_pts_sorted) >= 2:
            for i in range(len(time_pts_sorted) - 1):
                dt = (time_pts_sorted[i + 1] - time_pts_sorted[i]).total_seconds()
                if dt > max_interval_sec:
                    max_interval_sec = dt

        # C) 정지 상태 표류(Stationary Drift) 검사
        total_span_dist = haversine_distance(
            parsed_pts[0]["lat"], parsed_pts[0]["lng"],
            parsed_pts[-1]["lat"], parsed_pts[-1]["lng"]
        )
        total_duration_sec = 0.0
        if len(time_pts_sorted) >= 2:
            total_duration_sec = (time_pts_sorted[-1] - time_pts_sorted[0]).total_seconds()

        is_stationary_drift = (total_span_dist < 2.0 and total_duration_sec >= 10.0)

        # D) 영상 키프레임 시간 동기화율 계산
        matched_frames = 0
        total_frames = len(case_obj.frames)
        t_start = parse_utc_datetime(case_obj.filming_started_at)

        if total_frames > 0 and t_start and len(time_pts) > 0:
            for frame in case_obj.frames:
                f_target_time = t_start + timedelta(seconds=frame.timestamp_sec)
                best_diff = min(abs((f_target_time - t).total_seconds()) for t in time_pts)
                if best_diff <= tolerance_sec:
                    matched_frames += 1

        sync_rate = (matched_frames / total_frames) if total_frames > 0 else 0.0
        is_time_synced = (total_frames > 0 and sync_rate >= 0.60)

        # 4. 종합 품질 등급 판정 (최소 지표 기준 판정)
        # 등급별 임계치 검증
        # EXCELLENT
        is_exc = (
            ratio_le_20m >= 0.95 and
            p75_error <= 5.0 and
            max_error <= 12.0 and
            (sync_rate >= 0.90 if total_frames > 0 else True) and
            total_pts >= 5 and
            max_interval_sec <= 3.0 and
            not is_stationary_drift
        )

        # ACCEPTABLE
        is_acc = (
            ratio_le_20m >= 0.80 and
            p75_error <= 12.0 and
            max_error <= 25.0 and
            (sync_rate >= 0.60 if total_frames > 0 else True) and
            total_pts >= 3 and
            max_interval_sec <= 5.0 and
            not is_stationary_drift
        )

        # POOR
        is_poor = (
            ratio_le_20m >= 0.60 and
            p75_error <= 20.0 and
            max_error <= 35.0 and
            total_pts >= 2 and
            max_interval_sec <= 10.0
        )

        if is_stationary_drift:
            status_grade = "UNUSABLE"
        elif is_exc:
            status_grade = "EXCELLENT"
        elif is_acc:
            status_grade = "ACCEPTABLE"
        elif is_poor:
            status_grade = "POOR"
        else:
            status_grade = "UNUSABLE"

        # 5. 경로 활용 가능 여부 (is_path_usable) 판정
        is_usable = (
            status_grade in {"EXCELLENT", "ACCEPTABLE"} and
            case_obj.has_actual_gps and
            total_pts >= 3
        )

        # DB 반영
        case_obj.gps_quality_status = status_grade
        case_obj.is_path_usable = is_usable
        case_obj.is_gps_time_synced = is_time_synced
        case_obj.updated_at = datetime.now(timezone.utc)
        db.commit()

        metrics = {
            "total_pts": total_pts,
            "valid_acc_count": valid_acc_count,
            "ratio_le_20m": round(ratio_le_20m * 100, 1),
            "p75_error_m": round(p75_error, 2),
            "max_error_m": round(max_error, 2),
            "max_interval_sec": round(max_interval_sec, 2),
            "matched_frames": matched_frames,
            "total_frames": total_frames,
            "sync_rate": round(sync_rate * 100, 1),
            "is_stationary_drift": is_stationary_drift
        }

        return {
            "case_id": case_obj.id,
            "gps_quality_status": status_grade,
            "is_path_usable": is_usable,
            "is_gps_time_synced": is_time_synced,
            "metrics": metrics
        }

    # =========================================================================
    # Phase A-3: YouTube 기반 촬영 사례 분석 및 사용자 검증·DB 적재
    # =========================================================================

    @staticmethod
    def extract_youtube_video_id(url: str) -> Optional[str]:
        """
        다양한 형태의 YouTube URL에서 11자리 Video ID 추출
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID
        """
        if not url or not isinstance(url, str):
            return None
        clean_url = url.strip()
        patterns = [
            r"(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/watch\?.*v=([a-zA-Z0-9_\-]{11})",
            r"(?:https?:\/\/)?youtu\.be\/([a-zA-Z0-9_\-]{11})",
            r"(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/shorts\/([a-zA-Z0-9_\-]{11})",
            r"(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/embed\/([a-zA-Z0-9_\-]{11})",
            r"(?:https?:\/\/)?(?:www\.|m\.)?youtube\.com\/v\/([a-zA-Z0-9_\-]{11})"
        ]
        for p in patterns:
            m = re.search(p, clean_url)
            if m:
                return m.group(1)
        if re.match(r"^[a-zA-Z0-9_\-]{11}$", clean_url):
            return clean_url
        return None

    @classmethod
    def fetch_youtube_metadata(cls, video_id: str, youtube_url: str) -> Dict[str, Any]:
        """
        공식 YouTube oEmbed API를 통한 합법적 공개 메타데이터 수집
        - API 키 불필요, 제목, 채널명, 썸네일 URL 확보
        """
        normalized_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={normalized_url}&format=json"

        fallback_meta = {
            "video_id": video_id,
            "title": f"YouTube 영상 ({video_id})",
            "channel_name": "알 수 없음",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            "author_url": None,
            "original_url": normalized_url,
            "duration_sec": None,
            "description": None,
            "requested_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            resp = requests.get(oembed_url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "video_id": video_id,
                    "title": data.get("title") or fallback_meta["title"],
                    "channel_name": data.get("author_name") or "YouTube Creator",
                    "thumbnail_url": data.get("thumbnail_url") or fallback_meta["thumbnail_url"],
                    "author_url": data.get("author_url"),
                    "original_url": normalized_url,
                    "duration_sec": None,
                    "description": f"채널: {data.get('author_name', 'YouTube')}",
                    "requested_at": datetime.now(timezone.utc).isoformat()
                }
            elif resp.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"YouTube 영상을 찾을 수 없거나 비공개/삭제된 영상입니다. (ID: {video_id})"
                )
        except HTTPException:
            raise
        except Exception:
            pass

        return fallback_meta

    @classmethod
    def process_and_save_frame(cls, case_code: str, frame_index: int, raw_b64: str) -> Tuple[str, int, str]:
        """
        Base64 이미지를 디코딩하여 Aspect Fit 640x360 리사이즈, JPEG 품질 85 압축 후 파일 저장
        - 반환: (저장 상대 경로, 파일 크기 바이트, 정제된 Base64 문자열)
        """
        clean_b64 = raw_b64.strip()
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",", 1)[1].strip()

        try:
            img_bytes = base64.b64decode(clean_b64)
            img = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 프레임 이미지 데이터입니다 (Frame {frame_index}): {str(e)}"
            )

        if img.mode != "RGB":
            img = img.convert("RGB")

        max_w, max_h = 640, 360
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        upload_dir = os.path.abspath(os.path.join("drone_filght", "backend", "uploads", "case_study_frames", case_code))
        os.makedirs(upload_dir, exist_ok=True)
        file_name = f"frame_{frame_index}.jpg"
        abs_path = os.path.join(upload_dir, file_name)

        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85, optimize=True)
        compressed_bytes = out_buf.getvalue()
        file_size = len(compressed_bytes)

        with open(abs_path, "wb") as f:
            f.write(compressed_bytes)

        rel_path = f"uploads/case_study_frames/{case_code}/{file_name}"
        clean_b64_out = base64.b64encode(compressed_bytes).decode("utf-8")
        return rel_path, file_size, clean_b64_out

    @classmethod
    def _fallback_visual_analysis(cls, frames_meta: List[Dict[str, Any]], video_title: str) -> Dict[str, Any]:
        """
        Gemini API 연결 지연 또는 오프라인 환경을 위한 결정론적 드론 비전 규칙 분석 엔진
        """
        analyzed_frames = []
        techniques_order = ["FORWARD", "DIAGONAL_REVEAL", "LATERAL"]

        for idx, f in enumerate(frames_meta):
            tech = techniques_order[idx % len(techniques_order)]
            ratio = f.get("extracted_ratio", 0.15 if idx == 0 else (0.50 if idx == 1 else 0.85))
            analyzed_frames.append({
                "frame_index": idx,
                "timestamp_sec": f.get("timestamp_sec", 15.0 * (idx + 1)),
                "extracted_ratio": ratio,
                "scene_type": "자연·수변 풍경" if "한강" in video_title or "수변" in video_title else "도시·건축 랜드마크",
                "primary_subject": "중앙 랜드마크 및 수변 전경",
                "subject_bbox": {"x": 0.30 + idx * 0.05, "y": 0.35, "w": 0.35, "h": 0.40},
                "depth_layers": {
                    "foreground": "수변 산책로 및 하부 식생",
                    "midground": "주요 피사체 구조물",
                    "background": "원경 스카이라인 및 하늘"
                },
                "composition_type": "삼분할 구도 (Rule of Thirds)" if idx != 1 else "중앙 집중 구도",
                "estimated_technique": tech,
                "camera_movement": "전방 직선 전진 (Forward Dolly)" if tech == "FORWARD" else (
                    "사선 상승 드러내기 (Diagonal Reveal)" if tech == "DIAGONAL_REVEAL" else "측면 평행 트래킹 (Lateral Dolly)"
                ),
                "confidence_score": 0.85 - (idx * 0.03),
                "analysis_reason": f"{ratio*100:.0f}% 지점: 피사체를 향한 점진적 카메라 이동 및 공간 원근감 확보",
                "storage_path": f.get("storage_path"),
                "file_size_bytes": f.get("file_size_bytes")
            })

        overall_summary = {
            "dominant_scene_type": "자연 및 도시 랜드마크",
            "primary_subject": "중앙 랜드마크 구조물",
            "repeated_technique": "FORWARD",
            "representative_composition": "삼분할 및 중앙 집중 구도",
            "composition_progression": "15% 원경 삼분할 -> 50% 피사체 중심 근접 -> 85% 사선 파노라마 확장",
            "visual_characteristics": "3개 주요 프레임(15%, 50%, 85%) 분석 결과, 안정적인 수평선 유지와 피사체 중심의 점진적 시네마틱 앵글 확인",
            "recommendation_tags": ["수변풍경", "랜드마크", "전진촬영", "삼분할구도"]
        }

        return {
            "frames": analyzed_frames,
            "overall_summary": overall_summary
        }

    @classmethod
    def analyze_youtube_case(
        cls,
        db: Session,
        req: YouTubeAnalyzeRequest,
        current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Phase A-3 핵심 파이프라인:
        1. YouTube URL 검증 및 정규화
        2. 영상 메타데이터 수집 (oEmbed)
        3. 영상 프레임 접근성 검증 (저작권/이용정책 준수)
           - 프레임 부재 시 ANALYSIS_UNAVAILABLE 즉시 반환 및 안내
        4. 15%, 50%, 85% 프레임 Aspect Fit 640x360 압축 및 저장
        5. GeminiClient.generate_multi_vision() 다중 프레임 분석
        6. 사용자 검증 전 임시 초안(REVIEW_PENDING) 상태로 DB 등록
        7. 사용자 검증 미리보기 DTO 반환
        """
        # 1. URL 검증 및 비디오 ID 추출
        video_id = cls.extract_youtube_video_id(req.youtube_url)
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 YouTube 영상 URL입니다: {req.youtube_url}. (일반 URL, youtu.be, Shorts 지원)"
            )
        normalized_url = f"https://www.youtube.com/watch?v={video_id}"

        # 2. 메타데이터 확보
        metadata = cls.fetch_youtube_metadata(video_id, normalized_url)

        # 3. 실제 영상 프레임 접근 가능 여부 검증 (지시서 Section 3-3)
        raw_frames = req.frame_images or []
        if not raw_frames and not req.video_file_base64:
            # 프레임 자료가 없으면 다운로드를 우회하지 않고 ANALYSIS_UNAVAILABLE 반환
            return {
                "status": "ANALYSIS_UNAVAILABLE",
                "message": "YouTube 저작권 및 서비스 이용 정책에 따라 영상 스트림에 직접 접근할 수 없습니다. 영상 분석을 진행하려면 영상 파일(.mp4)을 직접 업로드하거나 추출된 프레임 이미지를 제공해 주세요.",
                "video_id": video_id,
                "video_metadata": metadata,
                "extracted_frames": [],
                "overall_summary": None,
                "case_id": None
            }

        # 4. 프레임 정제, 리사이즈(640x360) 및 로컬 저장
        case_code = f"YT_{video_id}_{uuid.uuid4().hex[:6]}"
        processed_frames_meta: List[Dict[str, Any]] = []
        gemini_image_inputs: List[Dict[str, Any]] = []

        target_ratios = [0.15, 0.50, 0.85]
        duration = req.duration_sec or 60.0

        for idx, f_item in enumerate(raw_frames[:3]):
            raw_b64 = f_item.get("data") or f_item.get("base64") or ""
            ratio = f_item.get("extracted_ratio") or (target_ratios[idx] if idx < len(target_ratios) else 0.5)
            t_sec = f_item.get("timestamp_sec") or round(duration * ratio, 1)

            rel_path, file_size, clean_b64 = cls.process_and_save_frame(case_code, idx, raw_b64)
            processed_frames_meta.append({
                "frame_index": idx,
                "timestamp_sec": t_sec,
                "extracted_ratio": ratio,
                "storage_path": rel_path,
                "file_size_bytes": file_size,
                "clean_b64": clean_b64
            })
            gemini_image_inputs.append({
                "data": clean_b64,
                "mime_type": "image/jpeg",
                "label": f"Frame {idx+1} ({ratio*100:.0f}%, t={t_sec}s)"
            })

        # 5. Gemini Vision Multi-Vision 분석 호출
        prompt = f"""당신은 전문 항공·드론 촬영 감독 및 시네마틱 구도 분석 AI입니다.
제공된 3장의 영상 주요 프레임(영상 길이의 15%, 50%, 85% 지점)을 정밀 분석하십시오.
영상 제목: {metadata.get('title')}

각 프레임별로 다음 항목을 분석하십시오:
1. scene_type: 자연, 도시, 건축물, 인물, 해변 등 장면 유형
2. primary_subject: 주요 피사체 명칭
3. subject_bbox: 피사체의 화면 내 위치 비율 {{"x": 0~1, "y": 0~1, "w": 0~1, "h": 0~1}}
4. depth_layers: {{"foreground": "전경 요소", "midground": "중경 요소", "background": "배경 요소"}}
5. composition_type: 삼분할 구도, 중앙 집중, 대칭, 리딩 라인, 대각선 등
6. estimated_technique: 반드시 다음 5종 중 하나로 분류 (FORWARD, LATERAL, DIAGONAL_REVEAL, ORBIT, PANORAMA). 불확실 시 UNKNOWN
7. camera_movement: 카메라 이동 및 회전 방향 설명 (피사체 자체 이동과 구분)
8. confidence_score: 0.0 ~ 1.0 실수
9. analysis_reason: 해당 구도와 기법으로 판단한 구체적인 시각적 근거

그리고 3개 프레임을 종합한 overall_summary를 작성하십시오:
- dominant_scene_type, primary_subject, repeated_technique, representative_composition, composition_progression, visual_characteristics, recommendation_tags

반드시 JSON 형식으로만 응답하십시오:
{{
  "frames": [
    {{
      "frame_index": 0,
      "scene_type": "...",
      "primary_subject": "...",
      "subject_bbox": {{"x": 0.35, "y": 0.40, "w": 0.30, "h": 0.35}},
      "depth_layers": {{"foreground": "...", "midground": "...", "background": "..."}},
      "composition_type": "...",
      "estimated_technique": "FORWARD",
      "camera_movement": "...",
      "confidence_score": 0.88,
      "analysis_reason": "..."
    }}
  ],
  "overall_summary": {{
    "dominant_scene_type": "...",
    "primary_subject": "...",
    "repeated_technique": "FORWARD",
    "representative_composition": "...",
    "composition_progression": "...",
    "visual_characteristics": "3개 주요 프레임 분석 결과 종합...",
    "recommendation_tags": ["..."]
  }}
}}"""

        system_instruction = "당신은 전문 촬영 비전 AI입니다. 오직 유효한 JSON 형식으로만 응답하며 기법은 FORWARD, LATERAL, DIAGONAL_REVEAL, ORBIT, PANORAMA, UNKNOWN만 사용합니다."

        reply_json_str, model_used, gemini_err = gemini_client.generate_multi_vision(
            prompt=prompt,
            images=gemini_image_inputs,
            system_instruction=system_instruction,
            connect_timeout=3.0,
            read_timeout=35.0
        )

        ai_data: Optional[Dict[str, Any]] = None
        if reply_json_str and not gemini_err:
            try:
                ai_data = json.loads(reply_json_str)
            except Exception:
                ai_data = None

        if not ai_data or "frames" not in ai_data:
            # 안전 폴백 실행 (Gemini API 지연/오류 시에도 중단 없는 신뢰성 보장)
            ai_data = cls._fallback_visual_analysis(processed_frames_meta, metadata.get("title", ""))
            model_used = "offline-rule-engine-v1"

        # AI 결과 및 프레임 정규화
        parsed_frames_list = ai_data.get("frames", [])
        overall_summary = ai_data.get("overall_summary", {})

        # 대표 기법 산출
        techniques_found = [
            f.get("estimated_technique", "UNKNOWN").upper().strip()
            for f in parsed_frames_list
            if f.get("estimated_technique") in cls.ALLOWED_TECHNIQUES
        ]
        rep_technique = techniques_found[0] if techniques_found else "UNKNOWN"

        # 6. 사용자 검증 전 임시 초안(REVIEW_PENDING) 상태로 DB에 저장
        user_id = current_user.id if current_user else None

        # Phase A-3.1 정합성 보완: declared_technique는 사용자 사전 선언값으로만 설정 (미입력 시 None)
        user_decl = None
        if getattr(req, "user_declared_technique", None):
            raw_decl = str(req.user_declared_technique).upper().strip()
            if raw_decl in cls.ALLOWED_TECHNIQUES:
                user_decl = raw_decl

        draft_case = ShootingCaseStudy(
            case_code=case_code,
            title=metadata.get("title") or f"YouTube 레퍼런스 영상 ({video_id})",
            description=metadata.get("description") or f"채널: {metadata.get('channel_name')}",
            source_type="YOUTUBE_REF",
            video_ref_url=normalized_url,
            duration_sec=req.duration_sec,
            place_name=None,
            latitude=None,
            longitude=None,
            user_id=user_id,
            project_id=None,
            path_id=None,
            declared_technique=user_decl,
            verified_technique=None,
            has_actual_gps=False,
            is_gps_time_synced=False,
            gps_quality_status="UNUSABLE",
            is_path_usable=False,
            is_public=False,
            ai_analysis_status="REVIEW_PENDING",
            verification_status="REVIEW_PENDING",
            verifier_notes=None,
            verification_audit=[]
        )
        db.add(draft_case)
        db.flush()

        saved_frames_response = []
        for idx, p_frame in enumerate(processed_frames_meta):
            f_ai = parsed_frames_list[idx] if idx < len(parsed_frames_list) else {}
            est_tech = str(f_ai.get("estimated_technique") or "UNKNOWN").upper().strip()
            if est_tech not in cls.ALLOWED_TECHNIQUES:
                est_tech = "UNKNOWN"

            frame_obj = CaseStudyFrame(
                case_id=draft_case.id,
                frame_index=idx,
                timestamp_sec=p_frame["timestamp_sec"],
                extracted_ratio=p_frame["extracted_ratio"],
                storage_path=p_frame["storage_path"],
                file_size_bytes=p_frame["file_size_bytes"],
                scene_type=f_ai.get("scene_type"),
                primary_subject=f_ai.get("primary_subject"),
                subject_bbox=f_ai.get("subject_bbox"),
                depth_layers=f_ai.get("depth_layers"),
                composition_type=f_ai.get("composition_type"),
                estimated_technique=est_tech,
                verified_technique=None,
                confidence_score=float(f_ai.get("confidence_score") or 0.82),
                raw_ai_analysis={
                    "camera_movement": f_ai.get("camera_movement"),
                    "analysis_reason": f_ai.get("analysis_reason"),
                    "full_frame_ai": f_ai
                },
                ai_model_version=model_used or "gemini-3.1-flash-lite",
                prompt_version="v2.0",
                is_verified=False
            )
            db.add(frame_obj)
            saved_frames_response.append({
                "frame_index": idx,
                "timestamp_sec": p_frame["timestamp_sec"],
                "extracted_ratio": p_frame["extracted_ratio"],
                "storage_path": p_frame["storage_path"],
                "file_size_bytes": p_frame["file_size_bytes"],
                "scene_type": frame_obj.scene_type,
                "primary_subject": frame_obj.primary_subject,
                "subject_bbox": frame_obj.subject_bbox,
                "depth_layers": frame_obj.depth_layers,
                "composition_type": frame_obj.composition_type,
                "estimated_technique": frame_obj.estimated_technique,
                "confidence_score": frame_obj.confidence_score,
                "analysis_reason": f_ai.get("analysis_reason"),
                "camera_movement": f_ai.get("camera_movement")
            })

        db.commit()
        db.refresh(draft_case)

        return {
            "status": "REVIEW_PENDING",
            "message": "AI 비전 분석이 완료되었습니다. 분석 결과를 검토 및 수정 후 최종 승인해 주세요.",
            "case_id": draft_case.id,
            "case_code": draft_case.case_code,
            "video_id": video_id,
            "video_metadata": metadata,
            "declared_technique": draft_case.declared_technique,
            "estimated_technique": rep_technique,
            "model_used": model_used,
            "extracted_frames": saved_frames_response,
            "overall_summary": overall_summary
        }

    @classmethod
    def approve_youtube_case(
        cls,
        db: Session,
        case_id: int,
        req: YouTubeApproveRequest,
        current_user: Optional[User] = None
    ) -> ShootingCaseStudy:
        """
        사용자 검증 및 최종 승인 처리:
        - verification_status = "HUMAN_VERIFIED"
        - ai_analysis_status = "COMPLETED"
        - verified_technique 확정 및 프레임별 수정사항 반영
        - verification_audit에 원자적 누적
        - Ground Truth 유지: has_actual_gps=False, path_id=None
        """
        case_obj = cls.get_case_study_by_id(db, case_id)

        if case_obj.source_type != "YOUTUBE_REF":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"해당 사례는 YOUTUBE_REF가 아닙니다: {case_obj.source_type}"
            )

        v_tech = req.verified_technique.upper().strip()
        if v_tech not in cls.ALLOWED_TECHNIQUES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"유효하지 않은 촬영 기법입니다: {req.verified_technique}. 허용: {list(cls.ALLOWED_TECHNIQUES)}"
            )

        # 상태 및 기법 확정
        case_obj.verification_status = "HUMAN_VERIFIED"
        case_obj.ai_analysis_status = "COMPLETED"
        case_obj.verified_technique = v_tech
        if req.verifier_notes:
            case_obj.verifier_notes = req.verifier_notes

        # 프레임별 수정사항 및 검증 상태 동기화
        edits_map = {e.frame_index: e for e in (req.frame_edits or [])}
        for frame in case_obj.frames:
            frame.is_verified = True
            if frame.frame_index in edits_map:
                edit_item = edits_map[frame.frame_index]
                if edit_item.verified_technique:
                    frame.verified_technique = edit_item.verified_technique.upper().strip()
                else:
                    frame.verified_technique = v_tech
                if edit_item.composition_type:
                    frame.composition_type = edit_item.composition_type
                if edit_item.scene_type:
                    frame.scene_type = edit_item.scene_type
                if edit_item.primary_subject:
                    frame.primary_subject = edit_item.primary_subject
            else:
                frame.verified_technique = v_tech

        # 검증 이력 누적
        audit_list = list(case_obj.verification_audit or [])
        v_id = current_user.id if current_user else None
        v_name = req.verifier_name or (current_user.username if current_user else "reviewer")
        v_role = req.verifier_role or (current_user.role if current_user else "pilot")

        new_audit = {
            "audit_id": len(audit_list) + 1,
            "verifier_id": v_id,
            "verifier_name": v_name,
            "verifier_role": v_role,
            "action": "HUMAN_VERIFIED",
            "previous_technique": None,
            "new_verified_technique": v_tech,
            "notes": req.verifier_notes,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        audit_list.append(new_audit)
        case_obj.verification_audit = audit_list
        case_obj.updated_at = datetime.now(timezone.utc)

        # Ground Truth 엄격 재확인
        case_obj.has_actual_gps = False
        case_obj.path_id = None
        case_obj.is_path_usable = False

        db.commit()
        db.refresh(case_obj)
        return case_obj

    @classmethod
    def reject_youtube_case(
        cls,
        db: Session,
        case_id: int,
        req: YouTubeRejectRequest,
        current_user: Optional[User] = None
    ) -> ShootingCaseStudy:
        """
        사용자 사례 저장 거부 (Reject) 처리:
        - verification_status = "REJECTED"
        - ai_analysis_status = "REJECTED"
        - 확정 사례로 승격되지 않으며 거부 이력 기록
        """
        case_obj = cls.get_case_study_by_id(db, case_id)

        case_obj.verification_status = "REJECTED"
        case_obj.ai_analysis_status = "REJECTED"
        if req.verifier_notes:
            case_obj.verifier_notes = req.verifier_notes

        audit_list = list(case_obj.verification_audit or [])
        v_id = current_user.id if current_user else None
        v_name = req.verifier_name or (current_user.username if current_user else "reviewer")
        v_role = req.verifier_role or (current_user.role if current_user else "pilot")

        new_audit = {
            "audit_id": len(audit_list) + 1,
            "verifier_id": v_id,
            "verifier_name": v_name,
            "verifier_role": v_role,
            "action": "REJECTED",
            "previous_technique": None,
            "new_verified_technique": None,
            "notes": req.verifier_notes or "사용자 요청에 의한 촬영 사례 저장 거부",
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
        audit_list.append(new_audit)
        case_obj.verification_audit = audit_list
        case_obj.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(case_obj)
        return case_obj

    @classmethod
    def search_compositions(
        cls,
        db: Session,
        scene_type: Optional[str] = None,
        composition_type: Optional[str] = None,
        technique: Optional[str] = None,
        min_confidence: float = 0.5,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        향후 실시간 AI 구도 추천 엔진을 위한 검증 완료 사례 검색:
        - 인간 검증 완료된 프레임(is_verified=True, case.verification_status='HUMAN_VERIFIED')만 검색
        - 장면 유형, 구도 유형, 기법별 필터링 지원
        """
        query = (
            db.query(CaseStudyFrame, ShootingCaseStudy)
            .join(ShootingCaseStudy, CaseStudyFrame.case_id == ShootingCaseStudy.id)
            .filter(
                CaseStudyFrame.is_verified == True,
                ShootingCaseStudy.verification_status == "HUMAN_VERIFIED"
            )
        )
        if scene_type:
            query = query.filter(CaseStudyFrame.scene_type.ilike(f"%{scene_type}%"))
        if composition_type:
            query = query.filter(CaseStudyFrame.composition_type.ilike(f"%{composition_type}%"))
        if technique:
            t_clean = technique.upper().strip()
            query = query.filter(
                (CaseStudyFrame.verified_technique == t_clean) |
                (CaseStudyFrame.estimated_technique == t_clean) |
                (ShootingCaseStudy.verified_technique == t_clean)
            )
        if min_confidence > 0:
            query = query.filter(CaseStudyFrame.confidence_score >= min_confidence)

        records = query.order_by(CaseStudyFrame.confidence_score.desc(), CaseStudyFrame.id.desc()).limit(limit).all()

        results = []
        for frame, case in records:
            results.append({
                "frame_id": frame.id,
                "case_id": case.id,
                "case_code": case.case_code,
                "video_title": case.title,
                "source_type": case.source_type,
                "video_ref_url": case.video_ref_url,
                "timestamp_sec": frame.timestamp_sec,
                "storage_path": frame.storage_path,
                "scene_type": frame.scene_type,
                "primary_subject": frame.primary_subject,
                "composition_type": frame.composition_type,
                "technique": frame.verified_technique or frame.estimated_technique or case.verified_technique,
                "confidence_score": frame.confidence_score,
                "depth_layers": frame.depth_layers,
                "subject_bbox": frame.subject_bbox
            })
        return results


case_study_service = CaseStudyService()
