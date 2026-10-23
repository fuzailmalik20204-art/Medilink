from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User, Patient, Doctor, AccessLog
from security import get_current_user


router = APIRouter(
    prefix="/api/access-logs",
    tags=["Access Logs"]
)


@router.get("/")
def get_my_access_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only patients can view their own access history
    if current_user.role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Only patients can view access history"
        )

    # Find patient profile
    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found"
        )

    # Get access logs
    logs = db.query(AccessLog).filter(
        AccessLog.patient_id == patient.id
    ).order_by(
        AccessLog.accessed_at.desc()
    ).all()

    result = []

    for log in logs:
        doctor = db.query(Doctor).filter(
            Doctor.id == log.doctor_id
        ).first()

        doctor_name = None
        doctor_id = None

        if doctor:
            doctor_id = doctor.doctor_id

            doctor_user = db.query(User).filter(
                User.id == doctor.user_id
            ).first()

            if doctor_user:
                doctor_name = doctor_user.name

        result.append({
            "id": log.id,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "action": log.action,
            "accessed_at": log.accessed_at
        })

    return {
        "patient_id": patient.patient_id,
        "total_logs": len(result),
        "logs": result
    }