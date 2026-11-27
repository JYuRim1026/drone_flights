from sqlalchemy.orm import Session
from typing import List, Optional
from backend.models.models import FlightRequest
from backend.schemas.schemas import FlightRequestCreate, AirspaceZoneResponse
from backend.external.unified_manager import external_manager

class PcService:
    @staticmethod
    def get_all_flights(db: Session) -> List[FlightRequest]:
        return db.query(FlightRequest).order_by(FlightRequest.id.desc()).all()

    @staticmethod
    def create_flight(db: Session, flight_in: FlightRequestCreate) -> FlightRequest:
        loc_info = external_manager.search_location(flight_in.location)
        lat = loc_info.get("latitude", 37.5284)
        lon = loc_info.get("longitude", 126.9328)
        
        db_flight = FlightRequest(
            location=flight_in.location,
            latitude=lat,
            longitude=lon,
            start_date=flight_in.start_date,
            end_date=flight_in.end_date,
            flight_time=flight_in.flight_time,
            drone_weight=flight_in.drone_weight,
            has_camera=flight_in.has_camera,
            purpose=flight_in.purpose,
            altitude=flight_in.altitude,
            notes=flight_in.notes,
            approval_status="READY"
        )
        db.add(db_flight)
        db.commit()
        db.refresh(db_flight)
        return db_flight

    @staticmethod
    def query_airspace(query: str, lat: Optional[float] = None, lon: Optional[float] = None) -> AirspaceZoneResponse:
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            loc_info = external_manager.search_location(query)
            lat = loc_info["latitude"]
            lon = loc_info["longitude"]

        airspace_info = external_manager.check_airspace(lat, lon, query)
        zone_name = airspace_info.get("zone_name", "비관제 일반공역 (G공역)")
        approval_req = airspace_info.get("approval_required", False)

        return AirspaceZoneResponse(
            zone_name=zone_name,
            zone_type=airspace_info.get("zone_type", "FREE"),
            latitude=lat,
            longitude=lon,
            radius_meter=1000,
            approval_required=approval_req,
            safety_score=airspace_info.get("safety_score", 80),
            status_label=airspace_info.get("permission_state", "비행승인 필요"),
            badge_color=airspace_info.get("badge_color", "#ea580c"),
            official_contacts={
                "agency": airspace_info.get("contact_agency", "서울지방항공청"),
                "phone": airspace_info.get("contact_phone", "032-740-2114")
            },
            description=f"{query} 인근 공역 통합 분석 결과입니다."
        )

    @staticmethod
    def chat_with_ai(prompt: str, location: str) -> str:
        ai_res = external_manager.ask_ai_assistant(prompt, location_context=location)
        return ai_res.get("reply", "비행 안전 규정에 따라 사전 비행승인 여부를 확인하십시오.")

pc_service = PcService()
