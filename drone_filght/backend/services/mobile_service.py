import os
import time
import uuid
import tempfile
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from backend.models.models import ShootingProject, ShootingAnalysis, ShootingPath, LocationAsset, User
from backend.schemas.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    RecommendationResponse,
    AnalysisResultCreate,
    ShootingProjectCreate,
    MobileProjectDetailResponse,
    ShootingPathCreate,
    ShootingPathResponse,
    ShootingPathProjectSummary,
    LocationAssetCreate,
    LocationAssetResponse,
    TechniqueCatalogItem,
    TechniqueRecommendationItem,
    PersonalizedRecommendationResponse,
    TechniqueSelectResponse,
    TechniqueFeedbackRequest,
    TechniqueFeedbackResponse,
    PathAnalysisDetailResponse,
    NextRoundPathResponse
)
from fastapi import HTTPException, status, UploadFile

# 파일 저장 디렉터리 (로컬 개발 및 Vercel /tmp 자동 호환)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_UPLOAD = os.path.join(_BACKEND_DIR, "uploads", "location_assets")
try:
    os.makedirs(_LOCAL_UPLOAD, exist_ok=True)
    UPLOAD_DIR = _LOCAL_UPLOAD
except Exception:
    UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "skycommand_uploads", "location_assets")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

class MobileService:
    @staticmethod
    def get_mobile_projects(db: Session) -> List[ShootingProject]:
        # 모바일 '내 촬영 신청 목록' 4대 기본 프로젝트(한강 수변, 용산, 졸업식 캠퍼스, 제주 성산일출봉)만 반환
        allowed_keywords = ["한강 수변", "용산", "졸업식 캠퍼스", "성산일출봉"]
        all_projects = db.query(ShootingProject).order_by(ShootingProject.id.asc()).all()
        filtered = [
            p for p in all_projects
            if any(k in (p.title or "") or k in (p.place_name or "") for k in allowed_keywords)
        ]
        return filtered

    @staticmethod
    def get_mobile_project_detail(db: Session, project_id: int) -> Dict[str, Any]:
        """
        [Step 1] 모바일 촬영 도우미: PC에서 생성된 특정 촬영 프로젝트를 선택하여
        촬영 목적, 장소, 촬영 시간, 원하는 구도 및 이전 AI 분석 여부를 불러옵니다.
        """
        project = db.query(ShootingProject).filter(
            (ShootingProject.id == project_id) | (ShootingProject.project_id == project_id)
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="해당 촬영 프로젝트를 찾을 수 없습니다.")

        # 해당 프로젝트의 최신 AI 실시간 영상 분석 결과(shooting_analyses) 존재 여부 확인
        latest_analysis = db.query(ShootingAnalysis).filter(
            ShootingAnalysis.project_id == project.project_id
        ).order_by(ShootingAnalysis.created_at.desc()).first()

        return {
            "id": project.project_id,
            "project_id": project.project_id,
            "title": project.project_name or project.title or "촬영 프로젝트",
            "place_name": project.shooting_location or project.place_name or "촬영 장소 미정",
            "target_date": project.target_date or "2026-10-24",
            "target_time": project.target_time or "14:00 ~ 16:00",
            "scene_intent": project.shooting_purpose or project.scene_intent or "기본 시네마틱 촬영",
            "recommended_mode": project.recommended_composition or project.recommended_mode or "삼등분의 법칙 (Rule of Thirds)",
            "recommended_shutter": project.recommended_shutter or "1/50s",
            "recommended_nd_filter": project.recommended_nd_filter or "ND16",
            "latitude": project.latitude or 37.5284,
            "longitude": project.longitude or 126.9328,
            "status": project.status or "READY",
            "created_at": project.created_at,
            "project_code": project.project_code,
            "desired_techniques": project.desired_techniques or [],
            "recommended_techniques": project.recommended_techniques or [],
            "has_analysis": latest_analysis is not None,
            "latest_analysis_id": latest_analysis.analysis_id if latest_analysis else None,
            "analysis_score": latest_analysis.composition_score if latest_analysis else None
        }

    @staticmethod
    def create_mobile_project(db: Session, project_in: ShootingProjectCreate) -> ShootingProject:
        """
        [Step 1] 모바일 현장에서 직접 신규 촬영 프로젝트(목적, 장소, 시간, 희망 구도)를 생성합니다.
        """
        d_str = datetime.now().strftime("%Y%m%d")
        r_str = uuid.uuid4().hex[:6].upper()
        p_code = getattr(project_in, "project_code", None) or f"DRONE_{d_str}_{r_str}"

        new_project = ShootingProject(
            title=project_in.title,
            project_name=project_in.title,
            project_code=p_code,
            place_name=project_in.place_name,
            shooting_location=project_in.place_name,
            target_date=project_in.target_date,
            target_time=project_in.target_time,
            scene_intent=project_in.scene_intent,
            shooting_purpose=project_in.scene_intent,
            recommended_mode=project_in.recommended_mode,
            recommended_composition=project_in.recommended_mode,
            recommended_shutter=project_in.recommended_shutter,
            recommended_nd_filter=project_in.recommended_nd_filter,
            latitude=project_in.latitude,
            longitude=project_in.longitude,
            status="READY"
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        return new_project

    @staticmethod
    def analyze_camera_frame(req: AnalyzeRequest) -> AnalyzeResponse:
        """
        Mobile camera frame real-time analyzer (matches camera.html AI logic).
        Calculates horizon misalignment and offset shift.
        """
        pitch_diff = req.current_pitch - (-20.0) # Target pitch is -20 degrees
        horizon_diff = req.detected_horizon_y - 0.5

        offset_x = 0.0
        offset_y = 0.0
        direction = "none"
        score = 88
        ready = True
        msg = "추천 구도 일치! AI가 외곽 여백을 활용해 미세 흔들림을 보정 중입니다."

        if abs(pitch_diff) > 5.0:
            ready = False
            score = 65
            if pitch_diff > 0:
                direction = "down"
                offset_y = -0.4
                msg = "카메라를 아래쪽(↓)으로 조정하세요. 수평선 피사체가 상단에 치우쳐 있습니다."
            else:
                direction = "up"
                offset_y = 0.5
                msg = "고도를 살짝 높이거나 카메라를 위쪽(↑)으로 조정하세요."
        elif abs(horizon_diff) > 0.1:
            ready = False
            score = 72
            if horizon_diff > 0:
                direction = "right"
                offset_x = -0.6
                msg = "피사체가 우측에 치우쳐 있습니다. 오른쪽(→)으로 이동하세요."
            else:
                direction = "left"
                offset_x = 0.6
                msg = "피사체가 좌측에 치우쳐 있습니다. 왼쪽(←)으로 이동하세요."

        return AnalyzeResponse(
            project_id=req.project_id,
            frame_score=score,
            is_ready=ready,
            guide_direction=direction,
            offset_x=offset_x,
            offset_y=offset_y,
            guide_message=msg
        )

    @staticmethod
    def get_recommendation_details(db: Session, project_id: int) -> RecommendationResponse:
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        return RecommendationResponse(
            project_id=project.id,
            recommended_mode=project.recommended_mode,
            concept_summary="한강 와이드 establishing shot + 저고도 슬로우 트래킹",
            camera_recipe={
                "resolution": "4K @ 24fps",
                "shutter": project.recommended_shutter or "1/50s",
                "nd_filter": project.recommended_nd_filter or "ND16",
                "color_profile": "D-Log M 10-bit",
                "iso": "ISO 100",
                "white_balance": "5600K"
            },
            stick_combo_steps=[
                {"step": "1단계", "name": "전진 슬로우 가속", "stick": "왼쪽 스틱 ↑ 30% 지속"},
                {"step": "2단계", "name": "우측 완만 선회(Orbit)", "stick": "오른쪽 스틱 → 20%"},
                {"step": "3단계", "name": "고도 유지 정지촬영", "stick": "왼쪽 스틱 중앙 (3초 호버링)"}
            ],
            shooting_waypoints=[
                {"seq": 1, "name": "시작 지점 (진입)", "altitude_m": 30, "direction": "북동쪽"},
                {"seq": 2, "name": "메인 포인트 (피사체 대면)", "altitude_m": 45, "direction": "대상 정면"},
                {"seq": 3, "name": "마무리 포인트 (상승 이탈)", "altitude_m": 35, "direction": "남서쪽"}
            ]
        )

    @staticmethod
    def save_analysis_result(
        db: Session,
        res_in: AnalysisResultCreate,
        current_user: Optional[User] = None
    ) -> ShootingAnalysis:
        coords = {
            "offset_x": res_in.offset_x,
            "offset_y": res_in.offset_y,
            "guide_direction": res_in.guide_direction,
            "shooting_number": res_in.shooting_number or 1,
            "user_id": current_user.id if current_user else None
        }
        analysis = ShootingAnalysis(
            project_id=res_in.project_id,
            analysis_status="completed",
            target_summary=res_in.target_summary or (res_in.subject or res_in.guide_direction or "피사체 인식"),
            environment_summary=res_in.environment_summary or res_in.guide_message,
            recommended_composition=res_in.recommended_composition or "AI 맞춤 추천 구도",
            target_coordinates=coords,
            composition_score=float(res_in.frame_score or 0),
            guide_message=res_in.guide_message,
            representative_image_path=res_in.recorded_video_url
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    # ==========================================
    # 2. 촬영 경로 & 센서 데이터 (ShootingPath)
    # ==========================================
    @staticmethod
    def save_shooting_path(
        db: Session,
        path_in: ShootingPathCreate,
        current_user: Optional[User] = None
    ) -> ShootingPath:
        """
        스마트폰에서 수집한 실제 보행 이동 경로(actual_waypoints)와 센서 정보,
        권장 동선 및 AI 보정 동선을 DB에 저장합니다.
        (실제 드론 비행 경로가 아닌 스마트폰 보행 동선으로 취급)
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == path_in.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        # shooting_number 자동 산출 (미지정 또는 <= 0 시 다음 회차 자동 계산)
        target_number = path_in.shooting_number
        if not target_number or target_number <= 0:
            latest = db.query(ShootingPath).filter(
                ShootingPath.project_id == path_in.project_id
            ).order_by(ShootingPath.shooting_number.desc()).first()
            target_number = (latest.shooting_number + 1) if latest else 1

        # 사용자 바인딩 (인증 사용자 우선)
        user_id = current_user.id if current_user else project.user_id

        # tracking_source는 기본 PHONE_GPS
        tracking_src = (path_in.tracking_source or "PHONE_GPS").upper()
        if tracking_src not in ["PHONE_GPS", "SIMULATION", "DRONE_GPS"]:
            tracking_src = "PHONE_GPS"

        # Phase 6: actual_waypoints가 제공되었을 때 AI 경로 분석 및 보정 자동 실행
        rec_wps = path_in.recommended_waypoints or []
        act_wps = path_in.actual_waypoints or []
        corr_wps = path_in.corrected_waypoints or []
        alpha_val = path_in.alpha_weight
        dev_score = path_in.deviation_score
        dev_reason = path_in.deviation_reason
        is_valid_flag = path_in.is_valid

        # 보정 경로가 없거나 이탈도 미산출 상태인 경우 자동 분석 수행
        if act_wps and (not corr_wps or dev_score is None or alpha_val is None):
            from backend.services.path_service import path_service
            analysis_res = path_service.analyze_and_correct_path(
                recommended_waypoints=rec_wps,
                actual_waypoints=act_wps,
                project=project
            )
            rec_wps = analysis_res["recommended_waypoints"]
            corr_wps = analysis_res["corrected_waypoints"]
            dev_score = analysis_res["deviation_score"]
            dev_reason = analysis_res["deviation_reason"]
            alpha_val = analysis_res["alpha_weight"]
            is_valid_flag = analysis_res["is_valid"]

        # 기존 회차 존재 시 재촬영(Re-take) 갱신, 미존재 시 신규 생성 (UNIQUE 충돌 방지)
        existing = db.query(ShootingPath).filter(
            ShootingPath.project_id == path_in.project_id,
            ShootingPath.shooting_number == target_number
        ).first()

        if existing:
            existing.user_id = user_id
            existing.tracking_source = tracking_src
            existing.recommended_waypoints = rec_wps
            existing.actual_waypoints = act_wps
            existing.corrected_waypoints = corr_wps
            existing.alpha_weight = alpha_val if alpha_val is not None else 0.3
            existing.deviation_score = dev_score
            existing.deviation_reason = dev_reason or "NORMAL"
            existing.is_valid = is_valid_flag if is_valid_flag is not None else True
            db.commit()
            db.refresh(existing)
            return existing

        new_path = ShootingPath(
            project_id=path_in.project_id,
            user_id=user_id,
            shooting_number=target_number,
            tracking_source=tracking_src,
            recommended_waypoints=rec_wps,
            actual_waypoints=act_wps,
            corrected_waypoints=corr_wps,
            alpha_weight=alpha_val if alpha_val is not None else 0.3,
            deviation_score=dev_score,
            deviation_reason=dev_reason or "NORMAL",
            is_valid=is_valid_flag if is_valid_flag is not None else True
        )
        db.add(new_path)
        db.commit()
        db.refresh(new_path)
        return new_path

    @staticmethod
    def analyze_shooting_path(
        db: Session,
        path_in: ShootingPathCreate,
        current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        """촬영 경로 이탈 및 보정 분석 단독 실행 (저장 전 미리보기 또는 상세 분석용)"""
        project = db.query(ShootingProject).filter(ShootingProject.id == path_in.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        from backend.services.path_service import path_service
        return path_service.analyze_and_correct_path(
            recommended_waypoints=path_in.recommended_waypoints,
            actual_waypoints=path_in.actual_waypoints,
            project=project
        )

    @staticmethod
    def get_next_round_path_recommendation(
        db: Session,
        project_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """차기 회차 추천 경로 조회 (Phase 9 사용자 맞춤형 변형 경로 우선 승계)"""
        from backend.services.path_service import path_service
        return path_service.get_next_round_recommendation(db, project_id, user_id=user_id)

    @staticmethod
    def get_shooting_paths(db: Session, project_id: int) -> List[ShootingPath]:
        """프로젝트별 전체 촬영 기록 목록 조회 (회차 순 정렬)"""
        return db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id
        ).order_by(ShootingPath.shooting_number.asc()).all()

    @staticmethod
    def get_shooting_path_detail(db: Session, path_id: int) -> ShootingPath:
        """특정 촬영 기록 상세 조회 (path_id 기준)"""
        path = db.query(ShootingPath).filter(ShootingPath.path_id == path_id).first()
        if not path:
            raise HTTPException(status_code=404, detail="해당 촬영 기록을 찾을 수 없습니다.")
        return path

    @staticmethod
    def get_shooting_path_by_number(db: Session, project_id: int, shooting_number: int) -> ShootingPath:
        """프로젝트 내 특정 촬영 회차 상세 조회"""
        path = db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id,
            ShootingPath.shooting_number == shooting_number
        ).first()
        if not path:
            raise HTTPException(status_code=404, detail=f"프로젝트 {project_id}의 {shooting_number}회차 촬영 기록을 찾을 수 없습니다.")
        return path

    @staticmethod
    def get_project_shooting_summary(db: Session, project_id: int) -> Dict[str, Any]:
        """프로젝트의 총 촬영 횟수, 회차 목록 및 최신 촬영 기록 요약 확인"""
        paths = db.query(ShootingPath).filter(
            ShootingPath.project_id == project_id
        ).order_by(ShootingPath.shooting_number.asc()).all()

        total = len(paths)
        valid_count = sum(1 for p in paths if p.is_valid)
        latest_num = paths[-1].shooting_number if paths else 0
        latest_path = paths[-1] if paths else None

        history = [
            {
                "path_id": p.path_id,
                "project_id": p.project_id,
                "shooting_number": p.shooting_number,
                "tracking_source": p.tracking_source,
                "waypoint_count": len(p.actual_waypoints or []),
                "deviation_score": p.deviation_score,
                "deviation_reason": p.deviation_reason,
                "is_valid": p.is_valid,
                "created_at": p.created_at
            }
            for p in paths
        ]

        return {
            "project_id": project_id,
            "total_attempts": total,
            "total_shooting_count": total,
            "latest_shooting_number": latest_num,
            "valid_paths_count": valid_count,
            "latest_path": latest_path,
            "history": history
        }

    # ==========================================
    # 3. 장소 자료 관리 (LocationAsset)
    # ==========================================
    @staticmethod
    def create_location_asset(
        db: Session,
        asset_in: LocationAssetCreate,
        current_user: Optional[User] = None
    ) -> LocationAsset:
        """프로젝트별 장소 자료 등록 (JSON 메타데이터 기반)"""
        project = db.query(ShootingProject).filter(ShootingProject.id == asset_in.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        user_id = current_user.id if current_user else None

        new_asset = LocationAsset(
            project_id=asset_in.project_id,
            user_id=user_id,
            is_common=asset_in.is_common if asset_in.is_common is not None else False,
            asset_type=asset_in.asset_type.upper(),
            file_url=asset_in.file_url,
            thumbnail_url=asset_in.thumbnail_url,
            detected_features=asset_in.detected_features or {},
            file_size_bytes=asset_in.file_size_bytes
        )
        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)
        return new_asset

    @staticmethod
    def save_uploaded_asset(
        db: Session,
        project_id: int,
        filename: str,
        file_bytes: bytes,
        asset_type: str,
        is_common: bool = False,
        detected_features: Optional[Dict[str, Any]] = None,
        current_user: Optional[User] = None
    ) -> LocationAsset:
        """
        현장 스마트폰 카메라/파노라마/영상 실제 물리 파일 저장 및 LocationAsset 등록
        (로컬 uploads 디렉터리 및 Vercel /tmp 자동 호환)
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        ext = os.path.splitext(filename)[1].lower()
        allowed = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".mov", ".json"}
        if ext not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 형식입니다 ({ext}). 지원 형식: {', '.join(allowed)}"
            )

        proj_dir = os.path.join(UPLOAD_DIR, str(project_id))
        os.makedirs(proj_dir, exist_ok=True)
        unique_name = f"{asset_type.lower()}_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
        physical_path = os.path.join(proj_dir, unique_name)

        with open(physical_path, "wb") as f:
            f.write(file_bytes)

        file_size = len(file_bytes)
        download_url = f"/api/mobile/assets/files/{project_id}/{unique_name}"
        user_id = current_user.id if current_user else None

        new_asset = LocationAsset(
            project_id=project_id,
            user_id=user_id,
            is_common=is_common,
            asset_type=asset_type.upper(),
            file_url=download_url,
            thumbnail_url=download_url if ext in {".jpg", ".jpeg", ".png", ".webp"} else None,
            detected_features=detected_features or {},
            file_size_bytes=file_size
        )
        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)
        return new_asset

    @staticmethod
    def get_project_location_assets(
        db: Session,
        project_id: int,
        current_user: Optional[User] = None,
        filter_type: Optional[str] = None,
        asset_type: Optional[str] = None
    ) -> List[LocationAsset]:
        """
        프로젝트별 장소 자료 목록 조회 (공통 자료와 개인 자료 권한 분리)
        - is_common == True (공통 자료): 프로젝트 접근 권한자 전원 조회 가능
        - is_common == False (개인 자료): 프로젝트 소유자/관리자 또는 업로드 당사자만 조회 가능
        """
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="촬영 프로젝트를 찾을 수 없습니다.")

        query = db.query(LocationAsset).filter(LocationAsset.project_id == project_id)

        if isinstance(asset_type, str) and asset_type.strip():
            query = query.filter(LocationAsset.asset_type == asset_type.strip().upper())

        if isinstance(filter_type, str):
            f_clean = filter_type.strip().lower()
            if f_clean == "common":
                query = query.filter(LocationAsset.is_common == True)
            elif f_clean == "personal":
                query = query.filter(LocationAsset.is_common == False)

        all_assets = query.order_by(LocationAsset.created_at.desc()).all()

        is_privileged = False
        user_id = current_user.id if current_user else None
        if current_user:
            if current_user.role == "admin" or (project.user_id and project.user_id == current_user.id):
                is_privileged = True

        filtered = []
        for asset in all_assets:
            if asset.is_common:
                filtered.append(asset)
            else:
                if is_privileged or (user_id is not None and asset.user_id == user_id):
                    filtered.append(asset)

        return filtered

    @staticmethod
    def get_location_asset_detail(
        db: Session,
        asset_id: int,
        current_user: Optional[User] = None
    ) -> LocationAsset:
        """단일 장소 자료 상세 조회 및 권한 확인"""
        asset = db.query(LocationAsset).filter(LocationAsset.asset_id == asset_id).first()
        if not asset:
            raise HTTPException(status_code=404, detail="해당 장소 자료를 찾을 수 없습니다.")

        if not asset.is_common:
            is_privileged = False
            if current_user:
                if current_user.role == "admin":
                    is_privileged = True
                elif asset.project and asset.project.user_id == current_user.id:
                    is_privileged = True
                elif asset.user_id == current_user.id:
                    is_privileged = True
            if not is_privileged:
                raise HTTPException(status_code=403, detail="해당 개인 장소 자료에 대한 열람 권한이 없습니다.")

        return asset

    @staticmethod
    def delete_location_asset(
        db: Session,
        asset_id: int,
        current_user: Optional[User] = None
    ) -> bool:
        """장소 자료 삭제 (물리 파일 및 DB 레코드 제거, 소유자/관리자 전용)"""
        asset = db.query(LocationAsset).filter(LocationAsset.asset_id == asset_id).first()
        if not asset:
            raise HTTPException(status_code=404, detail="해당 장소 자료를 찾을 수 없습니다.")

        is_owner = False
        if current_user:
            if current_user.role == "admin":
                is_owner = True
            elif asset.user_id == current_user.id:
                is_owner = True
            elif asset.project and asset.project.user_id == current_user.id:
                is_owner = True

        if not is_owner:
            raise HTTPException(status_code=403, detail="자료 삭제 권한이 없습니다. (작성자 또는 관리자만 삭제 가능)")

        if asset.file_url and asset.file_url.startswith("/api/mobile/assets/files/"):
            parts = asset.file_url.split("/api/mobile/assets/files/")[-1].split("/")
            if len(parts) == 2:
                local_file = os.path.join(UPLOAD_DIR, parts[0], parts[1])
                if os.path.exists(local_file):
                    try:
                        os.remove(local_file)
                    except Exception:
                        pass

        db.delete(asset)
        db.commit()
        return True

    # ==========================================
    # 4. 맞춤형 AI 촬영 기법 추천 & 피드백 (Phase 5)
    # ==========================================
    @staticmethod
    def get_technique_catalog(smartphone_only: bool = False) -> List[TechniqueCatalogItem]:
        from backend.services.technique_service import technique_service
        techniques = technique_service.get_all_techniques(filter_supported_only=smartphone_only)
        return [TechniqueCatalogItem(**t.to_dict()) for t in techniques]

    @staticmethod
    def get_personalized_techniques(
        db: Session,
        project_id: int,
        current_user: Optional[User] = None,
        limit: int = 4,
        smartphone_only: bool = False
    ) -> PersonalizedRecommendationResponse:
        from backend.services.technique_service import technique_service
        project = db.query(ShootingProject).filter(ShootingProject.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="해당 촬영 프로젝트를 찾을 수 없습니다.")

        recommendations = technique_service.recommend_techniques(
            db=db,
            user=current_user,
            project=project,
            limit=limit,
            smartphone_only=smartphone_only
        )

        user_name = current_user.username if current_user else "게스트 조종사"
        context_str = f"{user_name}님의 과거 촬영 스타일 및 선호도 분석 완료"

        return PersonalizedRecommendationResponse(
            project_id=project.id,
            user_id=current_user.id if current_user else None,
            user_context=context_str,
            count=len(recommendations),
            recommendations=[TechniqueRecommendationItem(**r) for r in recommendations]
        )

    @staticmethod
    def select_project_technique(
        db: Session,
        project_id: int,
        technique_id: str,
        current_user: Optional[User] = None
    ) -> TechniqueSelectResponse:
        from backend.services.technique_service import technique_service
        user_id = current_user.id if current_user else 1
        res = technique_service.record_technique_selection(
            db=db,
            user_id=user_id,
            project_id=project_id,
            technique_id=technique_id
        )
        return TechniqueSelectResponse(**res)

    @staticmethod
    def record_technique_feedback(
        db: Session,
        project_id: int,
        req: TechniqueFeedbackRequest,
        current_user: Optional[User] = None
    ) -> TechniqueFeedbackResponse:
        from backend.services.technique_service import technique_service
        user_id = current_user.id if current_user else 1

        # shooting_number가 누락되었을 때 무조건 1로 저장하지 않고 실제 촬영 회차 조회
        actual_shooting_number = req.shooting_number
        if not actual_shooting_number:
            latest_path = db.query(ShootingPath).filter(
                ShootingPath.project_id == project_id
            )
            if current_user:
                latest_path = latest_path.filter(ShootingPath.user_id == user_id)
            latest_path = latest_path.order_by(ShootingPath.shooting_number.desc()).first()
            if latest_path and latest_path.shooting_number:
                actual_shooting_number = latest_path.shooting_number
            else:
                latest_analysis = db.query(ShootingAnalysis).filter(
                    ShootingAnalysis.project_id == project_id
                ).order_by(ShootingAnalysis.created_at.desc()).first()
                if latest_analysis and latest_analysis.target_coordinates and isinstance(latest_analysis.target_coordinates, dict):
                    an_s_num = latest_analysis.target_coordinates.get("shooting_number")
                    if an_s_num:
                        actual_shooting_number = int(an_s_num)
            if not actual_shooting_number:
                actual_shooting_number = 1

        res = technique_service.record_technique_feedback(
            db=db,
            user_id=user_id,
            project_id=project_id,
            technique_id=req.technique_id,
            shooting_number=actual_shooting_number,
            was_shot=req.was_shot,
            satisfaction_score=req.satisfaction_score,
            comment=req.comment,
            composition_type=getattr(req, "composition_type", None),
            is_liked=getattr(req, "is_liked", None)
        )
        return TechniqueFeedbackResponse(**res)

mobile_service = MobileService()
