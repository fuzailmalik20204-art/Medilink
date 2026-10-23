from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    User,
    Patient,
    MedicalRecord,
    Doctor,
    AccessPermission,
    AccessLog
)
from schemas import MedicalRecordCreate, MedicalRecordUpdate
from security import get_current_user


router = APIRouter(
    prefix="/api/records",
    tags=["Medical Records"]
)


# ==========================================
# CREATE MEDICAL RECORD
# ==========================================

@router.post("/")
def create_medical_record(
    record_data: MedicalRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found"
        )

    new_record = MedicalRecord(
        patient_id=patient.id,
        title=record_data.title,
        diagnosis=record_data.diagnosis,
        description=record_data.description,
        doctor_name=record_data.doctor_name,
        record_date=record_data.record_date
    )

    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {
        "message": "Medical record created successfully",
        "record": {
            "id": new_record.id,
            "title": new_record.title,
            "diagnosis": new_record.diagnosis,
            "description": new_record.description,
            "doctor_name": new_record.doctor_name,
            "record_date": new_record.record_date
        }
    }


# ==========================================
# GET MY MEDICAL RECORDS (PATIENT)
# ==========================================

@router.get("/")
def get_medical_records(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found"
        )

    records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient.id
    ).order_by(
        MedicalRecord.record_date.desc()
    ).all()

    return {
        "patient_id": patient.patient_id,
        "total_records": len(records),
        "records": [
            {
                "id": record.id,
                "title": record.title,
                "diagnosis": record.diagnosis,
                "description": record.description,
                "notes": record.description,
                "doctor_name": record.doctor_name,
                "record_date": record.record_date,
                "created_at": record.created_at
            }
            for record in records
        ]
    }


# ==========================================
# UPDATE MEDICAL RECORD (PATIENT OR AUTHORIZED DOCTOR)
# ==========================================

@router.put("/{record_id}")
def update_medical_record(
    record_id: int,
    record_data: MedicalRecordUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found")

    # 1. Patient updating their own record
    if current_user.role == "patient":
        patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not patient or record.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="You do not own this record")

    # 2. Doctor updating patient record
    elif current_user.role in ["doctor", "provider"]:
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor profile not found")

        # Check access permission
        permission = db.query(AccessPermission).filter(
            AccessPermission.doctor_id == doctor.id,
            AccessPermission.patient_id == record.patient_id,
            AccessPermission.can_view_records == True
        ).first()

        if not permission:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to view or edit this patient's records"
            )

        # STRICT CHECK: Did the patient grant editing rights?
        if not permission.can_edit_records:
            raise HTTPException(
                status_code=403,
                detail="Patient has granted you View-Only access. You cannot edit this medical record."
            )

        if permission.expires_at and permission.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Access permission has expired")

        # Update doctor name to the editor's name
        record.doctor_name = current_user.name

        # Write to access audit logs
        log = AccessLog(
            patient_id=record.patient_id,
            doctor_id=doctor.id,
            action=f"Edited medical record #{record.id} ({record.title})"
        )
        db.add(log)

    else:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Apply updates
    if record_data.title is not None:
        record.title = record_data.title
    if record_data.diagnosis is not None:
        record.diagnosis = record_data.diagnosis
    if record_data.notes is not None:
        record.description = record_data.notes
    elif record_data.description is not None:
        record.description = record_data.description
    if record_data.doctor_name is not None:
        record.doctor_name = record_data.doctor_name
    if record_data.record_date is not None:
        record.record_date = record_data.record_date

    db.commit()
    db.refresh(record)

    return {
        "message": "Medical record updated successfully",
        "record": {
            "id": record.id,
            "title": record.title,
            "diagnosis": record.diagnosis,
            "description": record.description,
            "notes": record.description,
            "doctor_name": record.doctor_name,
            "record_date": record.record_date,
            "created_at": record.created_at
        }
    }


# ==========================================
# DELETE MEDICAL RECORD
# ==========================================

@router.delete("/{record_id}")
def delete_medical_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    record = db.query(MedicalRecord).filter(
        MedicalRecord.id == record_id,
        MedicalRecord.patient_id == patient.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found")

    db.delete(record)
    db.commit()

    return {
        "message": "Medical record deleted successfully",
        "record_id": record_id
    }


# ==========================================
# DOCTOR VIEW PATIENT MEDICAL RECORDS
# ==========================================

@router.get("/patient/{patient_id}")
def doctor_view_patient_records(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in ["doctor", "provider"]:
        raise HTTPException(
            status_code=403,
            detail="Only doctors can view patient records"
        )

    doctor = db.query(Doctor).filter(
        Doctor.user_id == current_user.id
    ).first()

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    permission = db.query(AccessPermission).filter(
        AccessPermission.patient_id == patient.id,
        AccessPermission.doctor_id == doctor.id
    ).first()

    if not permission or not permission.can_view_records:
        raise HTTPException(
            status_code=403,
            detail="Patient has not granted you access to view medical records"
        )

    records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient.id
    ).order_by(MedicalRecord.record_date.desc()).all()

    access_log = AccessLog(
        patient_id=patient.id,
        doctor_id=doctor.id,
        action="Viewed medical records"
    )
    db.add(access_log)
    db.commit()

    return {
        "patient_id": patient.patient_id,
        "access": {
            "can_view_records": permission.can_view_records,
            "can_edit_records": permission.can_edit_records,
            "can_view_medications": permission.can_view_medications,
            "can_view_documents": permission.can_view_documents
        },
        "total_records": len(records),
        "records": [
            {
                "id": record.id,
                "title": record.title,
                "diagnosis": record.diagnosis,
                "description": record.description,
                "notes": record.description,
                "doctor_name": record.doctor_name,
                "record_date": record.record_date,
                "created_at": record.created_at
            }
            for record in records
        ]
    }