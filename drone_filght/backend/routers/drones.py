from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.database import get_db
from backend.models.models import User, RegisteredDrone
from backend.services.auth_service import get_current_user, get_optional_current_user
from backend.schemas.schemas import (
    RegisteredDroneCreate,
    RegisteredDroneUpdate,
    RegisteredDroneResponse
)

router = APIRouter(prefix="/drones", tags=["드론 기체 관리 (Drone Management)"])


@router.get("", response_model=List[RegisteredDroneResponse], summary="내 등록 드론 목록 조회")
def list_my_drones(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    현재 로그인한 사용자(user_id)가 등록한 모든 드론 목록을 최신순으로 조회합니다.
    다른 사용자의 기체 정보는 절대 노출되지 않습니다.
    """
    drones = (
        db.query(RegisteredDrone)
        .filter(RegisteredDrone.user_id == current_user.user_id)
        .order_by(RegisteredDrone.created_at.desc())
        .all()
    )
    return drones


@router.post("", response_model=RegisteredDroneResponse, status_code=status.HTTP_201_CREATED, summary="신규 드론 기체 등록")
def register_drone(
    drone_in: RegisteredDroneCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    새로운 드론 기체 정보를 현재 로그인한 사용자 계정(user_id)에 등록합니다.
    - 모델명(model_name)은 필수 입력 항목입니다.
    """
    if not drone_in.model_name or not drone_in.model_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="드론 모델명은 필수 입력 항목입니다."
        )

    new_drone = RegisteredDrone(
        user_id=current_user.user_id,
        drone_type=drone_in.drone_type or "무인멀티콥터",
        report_number=drone_in.report_number,
        model_name=drone_in.model_name.strip(),
        purpose=drone_in.purpose or "비영리",
        manufacturer=drone_in.manufacturer,
        operation_type=drone_in.operation_type or "비연구용",
        specifications=drone_in.specifications,
        takeoff_weight=drone_in.takeoff_weight or "249g",
        owner_name=drone_in.owner_name or current_user.full_name or current_user.user_name,
        phone_number=drone_in.phone_number or current_user.phone,
        safety_cert_number=drone_in.safety_cert_number,
        cert_expiry_date=drone_in.cert_expiry_date,
        insurance_status=drone_in.insurance_status or "가입",
        description=drone_in.description,
        serial_number=drone_in.serial_number,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_drone)
    db.commit()
    db.refresh(new_drone)
    return new_drone


@router.get("/{drone_id}", response_model=RegisteredDroneResponse, summary="특정 드론 상세 조회")
def get_drone_detail(
    drone_id: int = Path(..., description="조회할 드론 고유 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    특정 드론의 상세 정보를 조회합니다.
    본인이 등록한 드론이 아니면 조회가 차단됩니다. (Admin 계정 예외 허용)
    """
    drone = db.query(RegisteredDrone).filter(RegisteredDrone.drone_id == drone_id).first()
    if not drone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"해당 드론(ID: {drone_id})을 찾을 수 없습니다."
        )

    if drone.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인이 등록한 드론 정보만 조회할 수 있습니다."
        )

    return drone


@router.put("/{drone_id}", response_model=RegisteredDroneResponse, summary="드론 정보 수정")
def update_drone(
    drone_in: RegisteredDroneUpdate,
    drone_id: int = Path(..., description="수정할 드론 고유 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    기존에 등록된 드론 정보를 수정합니다.
    본인 소유의 드론만 수정 가능합니다.
    """
    drone = db.query(RegisteredDrone).filter(RegisteredDrone.drone_id == drone_id).first()
    if not drone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"해당 드론(ID: {drone_id})을 찾을 수 없습니다."
        )

    if drone.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인이 등록한 드론 정보만 수정할 수 있습니다."
        )

    update_data = drone_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(drone, field) and value is not None:
            setattr(drone, field, value)

    drone.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(drone)
    return drone


@router.delete("/{drone_id}", status_code=status.HTTP_200_OK, summary="드론 삭제")
def delete_drone(
    drone_id: int = Path(..., description="삭제할 드론 고유 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    등록된 드론 기체를 삭제합니다.
    본인 소유의 드론만 삭제 가능합니다.
    """
    drone = db.query(RegisteredDrone).filter(RegisteredDrone.drone_id == drone_id).first()
    if not drone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"해당 드론(ID: {drone_id})을 찾을 수 없습니다."
        )

    if drone.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인이 등록한 드론 정보만 삭제할 수 있습니다."
        )

    db.delete(drone)
    db.commit()
    return {"status": "success", "message": f"드론(ID: {drone_id}, 모델: {drone.model_name})이 성공적으로 삭제되었습니다."}
