import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from backend.models.models import ShootingProject, User, UserSetting
from backend.schemas.schemas import ShootingProjectCreate, ShootingProjectUpdate, UserSettingUpdate, WeatherResponse
from fastapi import HTTPException
from backend.external import external_manager

class CommonService:
    @staticmethod
    def get_project_by_id(db: Session, project_id: int) -> ShootingProject:
        project = db.query(ShootingProject).filter(
            (ShootingProject.id == project_id) | (ShootingProject.project_id == project_id)
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
        return project

    @staticmethod
    def create_project(db: Session, project_in: ShootingProjectCreate) -> ShootingProject:
        lat = project_in.latitude
        lon = project_in.longitude
        if not lat or not lon:
            loc_data = external_manager.search_location(project_in.place_name)
            lat = loc_data.get("latitude", 37.5284)
            lon = loc_data.get("longitude", 126.9328)

        d_str = datetime.now().strftime("%Y%m%d")
        r_str = uuid.uuid4().hex[:6].upper()
        p_code = getattr(project_in, "project_code", None) or f"DRONE_{d_str}_{r_str}"

        # 6개 박스 필드 매핑
        desired = list(project_in.desired_techniques or [])
        if project_in.preferred_technique and project_in.preferred_technique not in desired:
            desired.append(project_in.preferred_technique)

        intent = project_in.additional_notes or project_in.scene_intent
        purpose = project_in.shooting_purpose

        new_proj = ShootingProject(
            title=project_in.title,
            project_name=project_in.title,
            place_name=project_in.place_name,
            shooting_location=project_in.place_name,
            project_code=p_code,
            target_date=project_in.target_date,
            target_time=project_in.target_time,
            scene_intent=intent,
            shooting_purpose=purpose,
            desired_techniques=desired,
            recommended_techniques=project_in.recommended_techniques or [],
            latitude=lat,
            longitude=lon,
            recommended_mode=project_in.recommended_mode or "패럴랙스 리빌 & 선셋 아크",
            recommended_shutter=project_in.recommended_shutter or "1/50s",
            recommended_nd_filter=project_in.recommended_nd_filter or "ND16",
            status="READY"
        )
        db.add(new_proj)
        db.commit()
        db.refresh(new_proj)
        return new_proj

    @staticmethod
    def update_project(db: Session, project_id: int, project_in: ShootingProjectUpdate) -> ShootingProject:
        project = db.query(ShootingProject).filter(
            (ShootingProject.id == project_id) | (ShootingProject.project_id == project_id)
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")

        if project_in.title is not None:
            project.title = project_in.title
            project.project_name = project_in.title
        if project_in.place_name is not None:
            project.place_name = project_in.place_name
            project.shooting_location = project_in.place_name
        if project_in.target_date is not None:
            project.target_date = project_in.target_date
        if project_in.target_time is not None:
            project.target_time = project_in.target_time
        if project_in.shooting_purpose is not None:
            project.shooting_purpose = project_in.shooting_purpose
        if project_in.additional_notes is not None:
            project.scene_intent = project_in.additional_notes
        elif project_in.scene_intent is not None:
            project.scene_intent = project_in.scene_intent

        desired = project_in.desired_techniques
        if desired is None and project_in.preferred_technique:
            desired = [project_in.preferred_technique]
        if desired is not None:
            project.desired_techniques = desired

        if project_in.latitude is not None:
            project.latitude = project_in.latitude
        if project_in.longitude is not None:
            project.longitude = project_in.longitude
        if project_in.status is not None:
            project.status = project_in.status

        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def get_current_weather(lat: float, lon: float, location_name: str) -> WeatherResponse:
        if not isinstance(lat, (int, float)):
            lat = 37.5284
        if not isinstance(lon, (int, float)):
            lon = 126.9328
        if hasattr(location_name, "default"):
            location_name = "서울 여의도 한강공원"

        w_data = external_manager.get_weather(lat, lon, location_name)
        wind = w_data["wind_speed_ms"]
        gust = w_data["wind_gust_ms"]
        temp = w_data["temperature_c"]
        desc = w_data["weather_condition"]
        vis = w_data["visibility_km"]
        is_safe = w_data["is_safe_to_fly"]

        return WeatherResponse(
            location_name=location_name,
            latitude=w_data["latitude"],
            longitude=w_data["longitude"],
            weather_desc=desc,
            temp_c=temp,
            wind_speed=wind,
            wind_gust=gust,
            visibility_km=vis,
            rain_probability=w_data.get("rain_probability", 0),
            is_safe_to_fly=is_safe,
            evaluation=w_data["safety_status"],
            humidity_percent=w_data.get("humidity_percent"),
            wind_direction_text=w_data.get("wind_direction_text"),
            precipitation_mm_h=w_data.get("precipitation_mm_h", 0.0),
            source=w_data.get("source"),
            observed_at=w_data.get("observed_at"),
            kma_grid=w_data.get("kma_grid"),
            risk_factors=w_data.get("risk_factors", []),
            hourly_forecast=w_data.get("hourly_forecast", []),
        )

    @staticmethod
    def get_user_settings(db: Session) -> UserSetting:
        setting = db.query(UserSetting).first()
        if not setting:
            # Seed default setting with a default user
            user = db.query(User).first()
            if not user:
                user = User(
                    username="drone_pilot",
                    full_name="홍길동 조종사",
                    drone_model="DJI Mini 4 Pro",
                    drone_weight_g=249
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            setting = UserSetting(
                user_id=user.id,
                safety_margin_m=30,
                notification_enabled=True,
                weather_auto_refresh=True,
                preferred_camera_mode="cinematic"
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
        return setting

    @staticmethod
    def update_user_settings(db: Session, update_in: UserSettingUpdate) -> UserSetting:
        setting = CommonService.get_user_settings(db)
        if update_in.safety_margin_m is not None:
            setting.safety_margin_m = update_in.safety_margin_m
        if update_in.notification_enabled is not None:
            setting.notification_enabled = update_in.notification_enabled
        if update_in.weather_auto_refresh is not None:
            setting.weather_auto_refresh = update_in.weather_auto_refresh
        if update_in.preferred_camera_mode is not None:
            setting.preferred_camera_mode = update_in.preferred_camera_mode
        db.commit()
        db.refresh(setting)
        return setting

common_service = CommonService()
