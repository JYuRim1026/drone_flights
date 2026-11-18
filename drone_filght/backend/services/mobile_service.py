from sqlalchemy.orm import Session
from typing import List, Dict, Any
from backend.models.models import ShootingProject, ShootingAnalysis
from backend.schemas.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    RecommendationResponse,
    AnalysisResultCreate,
    ShootingProjectCreate,
    MobileProjectDetailResponse
)
from fastapi import HTTPException

class MobileService:
    @staticmethod
    def get_mobile_projects(db: Session) -> List[ShootingProject]:
        projects = db.query(ShootingProject).order_by(ShootingProject.id.desc()).all()
        # Seed a default project if none exists (matches user's mobile app!)
        if not projects:
            default_p = ShootingProject(
                title="한강 도시 풍경 촬영",
                place_name="서울 한강공원",
                target_date="2026년 10월 24일",
                target_time="오후 14:00 ~ 16:00",
                scene_intent="한강을 따라 이동하며 도시의 넓은 풍경과 석양 분위기를 시네마틱하게 담고 싶어요.",
                latitude=37.5284,
                longitude=126.9328,
                recommended_mode="패럴랙스 리빌 & 선셋 아크",
                recommended_shutter="1/50s",
                recommended_nd_filter="ND16",
                status="READY"
            )
            db.add(default_p)
            db.commit()
            db.refresh(default_p)
            projects = [default_p]
        return projects

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
            "has_analysis": latest_analysis is not None,
            "latest_analysis_id": latest_analysis.analysis_id if latest_analysis else None,
            "analysis_score": latest_analysis.composition_score if latest_analysis else None
        }

    @staticmethod
    def create_mobile_project(db: Session, project_in: ShootingProjectCreate) -> ShootingProject:
        """
        [Step 1] 모바일 현장에서 직접 신규 촬영 프로젝트(목적, 장소, 시간, 희망 구도)를 생성합니다.
        """
        new_project = ShootingProject(
            title=project_in.title,
            project_name=project_in.title,
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
    def save_analysis_result(db: Session, res_in: AnalysisResultCreate) -> ShootingAnalysis:
        coords = {"offset_x": res_in.offset_x, "offset_y": res_in.offset_y, "guide_direction": res_in.guide_direction}
        analysis = ShootingAnalysis(
            project_id=res_in.project_id,
            analysis_status="completed",
            target_summary=res_in.guide_direction or "피사체 인식",
            environment_summary=res_in.guide_message,
            recommended_composition="AI 맞춤 추천 구도",
            target_coordinates=coords,
            composition_score=float(res_in.frame_score or 0),
            guide_message=res_in.guide_message,
            representative_image_path=res_in.recorded_video_url
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

mobile_service = MobileService()
