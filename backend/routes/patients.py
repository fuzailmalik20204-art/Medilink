from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User, Patient
from schemas import PatientUpdate
from security import get_current_user

router = APIRouter(
    prefix="/api/patients",
    tags=["Patients"]
)


def get_current_patient(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(
            status_code=403, 
            detail="Access denied. Patient account required."
        )

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        patient = Patient(
            user_id=current_user.id,
            patient_id=f"PAT-{current_user.id:05d}"
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
    return patient


# ==========================================
# 1. GET CURRENT PATIENT PROFILE FROM DB
# ==========================================
@router.get("/me")
def get_patient_profile(
    patient: Patient = Depends(get_current_patient),
    current_user: User = Depends(get_current_user)
):
    return {
        "id": patient.id,
        "user_id": current_user.id,
        "patient_id": patient.patient_id,
        "name": current_user.name,
        "email": current_user.email,
        "blood_group": patient.blood_group or "",
        "phone": patient.phone or "",
        "address": patient.address or "",
        "emergency_contact": patient.emergency_contact or "",
        "date_of_birth": str(patient.date_of_birth) if patient.date_of_birth else None,
        "gender": patient.gender or ""
    }


# ==========================================
# 2. UPDATE PATIENT PROFILE IN DB
# ==========================================
@router.put("/me")
def update_patient_profile(
    profile_data: PatientUpdate,
    patient: Patient = Depends(get_current_patient),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Update User table
    if profile_data.name is not None and profile_data.name.strip():
        current_user.name = profile_data.name.strip()

    # Update Patient table
    if profile_data.blood_group is not None:
        patient.blood_group = profile_data.blood_group.strip()
    if profile_data.phone is not None:
        patient.phone = profile_data.phone.strip()
    if profile_data.emergency_contact is not None:
        patient.emergency_contact = profile_data.emergency_contact.strip()
    if profile_data.address is not None:
        patient.address = profile_data.address.strip()
    if profile_data.date_of_birth is not None:
        patient.date_of_birth = profile_data.date_of_birth
    if profile_data.gender is not None:
        patient.gender = profile_data.gender

    db.commit()
    db.refresh(patient)
    db.refresh(current_user)

    return {
        "message": "Patient profile updated successfully in database",
        "profile": {
            "name": current_user.name,
            "patient_id": patient.patient_id,
            "blood_group": patient.blood_group,
            "phone": patient.phone,
            "emergency_contact": patient.emergency_contact,
            "address": patient.address
        }
    }