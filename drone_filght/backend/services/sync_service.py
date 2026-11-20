import io
import base64
try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
except ImportError:
    qrcode = None
    StyledPilImage = None
    RoundedModuleDrawer = None
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.config import settings
from backend.models.models import ShootingProject, ShootingAnalysis, User
from backend.services.auth_service import auth_service
from backend.schemas.schemas import (
    SyncProjectCreate,
    SyncProjectResponse,
    SyncStatusUpdate,
    SyncAnalysisResultCreate,
    SyncAnalysisResultResponse
)
from backend.external import external_manager

class SyncService:
    """
    PC·모바일 실시간 데이터 연동 및 동기화 서비스 (7단계)
    - 고유 프로젝트 ID/코드 자동 생성 (예: DRONE_001)
    - PC 촬영 계획 데이터 저장
    - 프로젝트 접속용 QR코드 자동 생성 (Base64 Data URI)
    - 모바일 프로젝트 조회 (ID 또는 DRONE_001 코드로 단번에 로드)
    - 모바일 현장 AI 분석 결과 및 녹화 영상 저장
    - PC 결과 실시간 대시보드 조회
    - 생명주기 상태 관리: CREATED ➔ ANALYZING ➔ COMPLETED ➔ FAILED
    """

    @classmethod
    def generate_next_project_code(cls, db: Session) -> str:
        """
        사람이 식별하기 쉽고 스마트폰에서 입력하기 쉬운 고유 코드 자동 발급 (예: DRONE_001, DRONE_002)
        """
        latest = db.query(ShootingProject).filter(
            ShootingProject.project_code.like("DRONE_%")
        ).order_by(ShootingProject.id.desc()).first()

        if not latest or not latest.project_code:
            return "DRONE_001"

        try:
            num_part = int(latest.project_code.split("_")[1])
            return f"DRONE_{num_part + 1:03d}"
        except Exception:
            count = db.query(ShootingProject).count()
            return f"DRONE_{count + 1:03d}"

    @classmethod
    def generate_qr_base64(cls, url: str) -> str:
        """
        모바일 접속용 URL을 담은 스캔 가능한 고해상도 QR코드(PNG Base64) 생성
        """
        try:
            if qrcode is None:
                return ""
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="#080d16", back_color="#ffffff")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64_str}"
        except Exception as e:
            # Fallback placeholder if QR fails
            return ""

    @classmethod
    def find_project(cls, db: Session, identifier: Union[int, str]) -> ShootingProject:
        """ID(정수) 또는 project_code(문자열 e.g. DRONE_001)로 프로젝트 탐색"""
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            proj = db.query(ShootingProject).filter(ShootingProject.id == int(identifier)).first()
        else:
            proj = db.query(ShootingProject).filter(ShootingProject.project_code == str(identifier)).first()

        if not proj:
            raise HTTPException(status_code=404, detail=f"프로젝트 '{identifier}'를 찾을 수 없습니다.")
        return proj

    @classmethod
    def create_pc_project(
        cls,
        db: Session,
        project_in: SyncProjectCreate,
        current_user: Optional[User] = None
    ) -> SyncProjectResponse:
        """
        [PC] 1. 신규 촬영 프로젝트 생성 ➔ 고유 ID/코드 발급 ➔ 암호화 서명 토큰 및 QR코드 생성
        """
        proj_code = cls.generate_next_project_code(db)

        # 위치 좌표 지오코딩 보정
        lat = project_in.latitude
        lon = project_in.longitude
        if not lat or not lon:
            loc = external_manager.search_location(project_in.place_name)
            lat = loc.get("latitude", 37.5284)
            lon = loc.get("longitude", 126.9328)

        user_id = current_user.id if isinstance(current_user, User) else None

        db_proj = ShootingProject(
            project_code=proj_code,
            user_id=user_id,
            title=project_in.title,
            place_name=project_in.place_name,
            scene_intent=project_in.scene_intent,
            target_date=project_in.target_date,
            target_time=project_in.target_time,
            recommended_mode=project_in.recommended_mode or "패럴랙스 리빌 & 선셋 아크",
            recommended_shutter=project_in.recommended_shutter or "1/50s",
            recommended_nd_filter=project_in.recommended_nd_filter or "ND16",
            latitude=lat,
            longitude=lon,
            status="CREATED"
        )
        db.add(db_proj)
        db.commit()
        db.refresh(db_proj)

        # 모바일 접근용 암호화 서명 보안 토큰 생성
        project_token = auth_service.create_project_access_token(
            project_code=proj_code,
            project_id=db_proj.id,
            user_id=user_id
        )
        db_proj.project_token = project_token
        db.commit()
        db.refresh(db_proj)

        # 모바일 웹 직접 연결 URL 생성 (토큰 파라미터 포함 ➔ 타인 무단 열람 차단)
        mobile_url = f"{settings.MOBILE_WEB_URL}/camera.html?project_code={proj_code}&token={project_token}"
        qr_data = cls.generate_qr_base64(mobile_url)

        return SyncProjectResponse(
            id=db_proj.id,
            project_code=db_proj.project_code,
            title=db_proj.title,
            place_name=db_proj.place_name,
            scene_intent=db_proj.scene_intent,
            target_date=db_proj.target_date,
            target_time=db_proj.target_time,
            recommended_mode=db_proj.recommended_mode,
            recommended_shutter=db_proj.recommended_shutter,
            recommended_nd_filter=db_proj.recommended_nd_filter,
            latitude=db_proj.latitude,
            longitude=db_proj.longitude,
            status=db_proj.status,
            project_token=project_token,
            mobile_access_url=mobile_url,
            qr_code_base64=qr_data,
            created_at=db_proj.created_at,
            updated_at=db_proj.updated_at,
            analysis_count=0
        )

    @classmethod
    def get_project_sync(
        cls,
        db: Session,
        identifier: Union[int, str],
        for_mobile: bool = False,
        current_user: Optional[User] = None,
        project_token: Optional[str] = None
    ) -> SyncProjectResponse:
        """
        [모바일/PC 공통] 프로젝트 정보 조회 (보안 접근 제어 적용)
        - project_token이 있으면 유효성 검증
        - current_user가 있으면 소유권(user_id) 검증
        - 모바일이 열었을 경우 자동으로 상태를 'CREATED' ➔ 'ANALYZING'으로 상태 전이
        """
        proj = cls.find_project(db, identifier)

        # 1. 보안 접근 제어 (모바일 토큰 또는 사용자 소유권 검사)
        user_obj = current_user if isinstance(current_user, User) else None
        if project_token:
            auth_service.verify_project_access_token(project_token, expected_project_code=proj.project_code)
        elif user_obj:
            if user_obj.role != "admin" and proj.user_id is not None and proj.user_id != user_obj.id:
                raise HTTPException(
                    status_code=403,
                    detail=f"해당 프로젝트({proj.project_code})에 대한 접근 권한이 없습니다. (타인 프로젝트 접근 차단)"
                )
        elif for_mobile and proj.user_id is not None:
            # 소유자가 지정된 프로젝트에 토큰 없이 모바일 무단 접근 시 차단
            raise HTTPException(
                status_code=403,
                detail="타인의 프로젝트에 접근할 수 없습니다. QR코드의 유효한 보안 토큰(?token=...)이 필요합니다."
            )

        # 2. 모바일 현장 접속 시 상태 자동 전이
        if for_mobile and proj.status == "CREATED":
            proj.status = "ANALYZING"
            db.commit()
            db.refresh(proj)

        token_param = f"&token={proj.project_token}" if proj.project_token else ""
        mobile_url = f"{settings.MOBILE_WEB_URL}/camera.html?project_code={proj.project_code}{token_param}"
        qr_data = cls.generate_qr_base64(mobile_url)
        analysis_count = len(proj.analyses) if proj.analyses else 0

        return SyncProjectResponse(
            id=proj.id,
            project_code=proj.project_code or f"DRONE_{proj.id:03d}",
            title=proj.title,
            place_name=proj.place_name,
            scene_intent=proj.scene_intent,
            target_date=proj.target_date,
            target_time=proj.target_time,
            recommended_mode=proj.recommended_mode,
            recommended_shutter=proj.recommended_shutter,
            recommended_nd_filter=proj.recommended_nd_filter,
            latitude=proj.latitude,
            longitude=proj.longitude,
            status=proj.status,
            project_token=proj.project_token,
            mobile_access_url=mobile_url,
            qr_code_base64=qr_data,
            created_at=proj.created_at,
            updated_at=proj.updated_at,
            analysis_count=analysis_count
        )

    @classmethod
    def save_mobile_analysis_result(
        cls,
        db: Session,
        identifier: Union[int, str],
        result_in: SyncAnalysisResultCreate,
        current_user: Optional[User] = None,
        project_token: Optional[str] = None
    ) -> SyncAnalysisResultResponse:
        """
        [모바일] 2. 촬영 현장 구도 분석 및 녹화 결과 저장 ➔ 프로젝트 상태 'COMPLETED' 자동 전이
        """
        proj = cls.find_project(db, identifier)

        # 보안 검증: 서명된 모바일 토큰 또는 소유자 권한 확인
        user_obj = current_user if isinstance(current_user, User) else None
        if project_token:
            auth_service.verify_project_access_token(project_token, expected_project_code=proj.project_code)
        elif user_obj:
            if user_obj.role != "admin" and proj.user_id is not None and proj.user_id != user_obj.id:
                raise HTTPException(
                    status_code=403,
                    detail="본인 소유의 프로젝트에 대해서만 촬영 결과를 저장할 수 있습니다."
                )
        elif proj.user_id is not None:
            raise HTTPException(
                status_code=403,
                detail="타인의 프로젝트에 결과를 업로드할 수 없습니다. 유효한 보안 토큰(?token=...)이 필요합니다."
            )

        coords = {
            "offset_x": result_in.offset_x,
            "offset_y": result_in.offset_y,
            "guide_direction": result_in.guide_direction
        }
        record = ShootingAnalysis(
            project_id=proj.id,
            analysis_status="completed",
            target_summary=result_in.guide_direction or "피사체 인식 완료",
            environment_summary=result_in.guide_message,
            recommended_composition="AI 맞춤 추천 구도",
            target_coordinates=coords,
            composition_score=float(result_in.frame_score or 0),
            guide_message=result_in.guide_message,
            representative_image_path=result_in.recorded_video_url
        )
        db.add(record)

        # 촬영 완료로 상태 갱신
        proj.status = "COMPLETED"
        db.commit()
        db.refresh(record)
        db.refresh(proj)

        return SyncAnalysisResultResponse(
            id=record.id,
            project_id=record.project_id,
            frame_score=record.frame_score,
            offset_x=record.offset_x,
            offset_y=record.offset_y,
            guide_direction=record.guide_direction,
            guide_message=record.guide_message,
            recorded_video_url=record.recorded_video_url,
            created_at=record.created_at
        )

    @classmethod
    def get_pc_project_results(
        cls,
        db: Session,
        identifier: Union[int, str],
        current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        [PC] 3. 모바일에서 현장 저장한 촬영 분석 결과 및 영상 실시간 확인
        """
        proj = cls.find_project(db, identifier)
        user_obj = current_user if isinstance(current_user, User) else None

        if user_obj and user_obj.role != "admin" and proj.user_id is not None and proj.user_id != user_obj.id:
            raise HTTPException(
                status_code=403,
                detail="해당 프로젝트의 결과를 열람할 권한이 없습니다. (타인 프로젝트 접근 차단)"
            )
        results = [
            {
                "id": a.id,
                "frame_score": a.frame_score,
                "offset_x": a.offset_x,
                "offset_y": a.offset_y,
                "guide_direction": a.guide_direction,
                "guide_message": a.guide_message,
                "recorded_video_url": a.recorded_video_url,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            for a in (proj.analyses or [])
        ]

        return {
            "project_id": proj.id,
            "project_code": proj.project_code,
            "title": proj.title,
            "status": proj.status,
            "place_name": proj.place_name,
            "target_date": proj.target_date,
            "target_time": proj.target_time,
            "total_shots_count": len(results),
            "analysis_results": results
        }

    @classmethod
    def update_project_status(cls, db: Session, identifier: Union[int, str], status: str) -> Dict[str, Any]:
        """
        데이터 상태 관리: CREATED ➔ ANALYZING ➔ COMPLETED ➔ FAILED
        """
        proj = cls.find_project(db, identifier)
        valid_statuses = ["CREATED", "ANALYZING", "COMPLETED", "FAILED"]
        clean_status = status.upper().strip()
        if clean_status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 상태값입니다. ({', '.join(valid_statuses)})")

        proj.status = clean_status
        db.commit()
        db.refresh(proj)
        return {
            "project_id": proj.id,
            "project_code": proj.project_code,
            "status": proj.status,
            "message": f"프로젝트 상태가 '{proj.status}'(으)로 갱신되었습니다."
        }

sync_service = SyncService()
