from datetime import datetime, date, time, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from database import get_db
from models import (
    User,
    Doctor,
    Patient,
    AccessPermission,
    AccessRequest,
    AccessLog,
    MedicalRecord,
    Medication,
    MedicationDoseLog,
    Document
)
from schemas import (
    MedicalRecordCreate,
    MedicalRecordUpdate,
    MedicationCreate,
    MedicationUpdate,
    AccessRequestCreate
)
from security import get_current_user

router = APIRouter(
    prefix="/api/doctors",
    tags=["Doctors"]
)


# =========================================================
# SCHEMAS FOR DOCTOR PROFILE UPDATES
# =========================================================
class DoctorProfileUpdate(BaseModel):
    name: str | None = None
    doctor_code: str | None = None
    specialization: str | None = None
    hospital: str | None = None
    phone: str | None = None


# =========================================================
# DEPENDENCY: GET CURRENT DOCTOR PROFILE
# =========================================================
def get_current_doctor(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in ["doctor", "provider"]:
        raise HTTPException(
            status_code=403, 
            detail="Access denied. Healthcare provider account required."
        )
    
    doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
    if not doctor:
        doctor = Doctor(
            user_id=current_user.id, 
            doctor_id=f"DOC-{current_user.id:05d}"
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
    return doctor


# =========================================================
# 1. GET DOCTOR PROFILE
# =========================================================
@router.get("/me")
def get_doctor_profile(
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user)
):
    return {
        "id": doctor.id,
        "user_id": current_user.id,
        "doctor_code": doctor.doctor_id,
        "name": current_user.name,
        "email": current_user.email,
        "specialization": doctor.specialization or "General Practitioner",
        "hospital": doctor.hospital or "MediLink Network",
        "phone": doctor.phone or "Not provided"
    }


# =========================================================
# 2. UPDATE / CUSTOMIZE DOCTOR PROFILE & DOCTOR ID
# =========================================================
@router.put("/me")
def update_doctor_profile(
    profile_data: DoctorProfileUpdate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if profile_data.name is not None and profile_data.name.strip():
        current_user.name = profile_data.name.strip()

    if profile_data.doctor_code is not None and profile_data.doctor_code.strip():
        new_code = profile_data.doctor_code.strip()
        existing = db.query(Doctor).filter(
            Doctor.doctor_id == new_code,
            Doctor.id != doctor.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400, 
                detail="This Doctor ID/Code is already taken by another doctor."
            )
        doctor.doctor_id = new_code

    if profile_data.specialization is not None:
        doctor.specialization = profile_data.specialization.strip()

    if profile_data.hospital is not None:
        doctor.hospital = profile_data.hospital.strip()

    if profile_data.phone is not None:
        doctor.phone = profile_data.phone.strip()

    db.commit()
    db.refresh(doctor)
    db.refresh(current_user)

    return {
        "message": "Doctor profile updated successfully",
        "doctor_code": doctor.doctor_id,
        "name": current_user.name
    }


# =========================================================
# 3. DOCTOR DIRECTORY SEARCH (BY NUMERIC ID, CODE, NAME, HOSP, SPEC)
# =========================================================
@router.get("/directory")
def search_doctor_directory(
    q: str = Query(None, description="Search term"),
    db: Session = Depends(get_db)
):
    query = db.query(Doctor, User).join(User, Doctor.user_id == User.id)

    if q and q.strip():
        raw = q.strip()
        term = f"%{raw.lower()}%"
        conditions = [
            User.name.ilike(term),
            Doctor.specialization.ilike(term),
            Doctor.hospital.ilike(term),
            Doctor.doctor_id.ilike(term)
        ]
        if raw.isdigit():
            conditions.append(Doctor.id == int(raw))
        query = query.filter(or_(*conditions))

    doctors = query.limit(30).all()

    return {
        "doctors": [
            {
                "id": doc.Doctor.id,
                "doctor_code": doc.Doctor.doctor_id,
                "name": doc.User.name,
                "email": doc.User.email,
                "specialization": doc.Doctor.specialization or "General Practitioner",
                "hospital": doc.Doctor.hospital or "MediLink Network",
                "phone": doc.Doctor.phone or "Not provided"
            }
            for doc in doctors
        ]
    }


# =========================================================
# 4. DOCTOR SEARCHES PATIENTS BY NAME OR PATIENT CODE
# =========================================================
@router.get("/search-patients")
def search_patients_for_request(
    q: str = Query(..., min_length=1),
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    raw = q.strip()
    term = f"%{raw.lower()}%"
    query = db.query(Patient, User).join(User, Patient.user_id == User.id)
    conditions = [
        User.name.ilike(term),
        Patient.patient_id.ilike(term)
    ]
    if raw.isdigit():
        conditions.append(Patient.id == int(raw))

    patients = query.filter(or_(*conditions)).limit(20).all()

    return {
        "patients": [
            {
                "id": p.Patient.id,
                "patient_code": p.Patient.patient_id,
                "name": p.User.name,
                "email": p.User.email,
                "gender": p.Patient.gender or "N/A",
                "blood_group": p.Patient.blood_group or "N/A"
            }
            for p in patients
        ]
    }


# =========================================================
# 5. DOCTOR SENDS ACCESS REQUEST (NEW OR UPGRADED PERMISSIONS)
# =========================================================
@router.post("/request-access")
def doctor_request_access(
    req_data: AccessRequestCreate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.patient_id == req_data.patient_code.strip()
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient with this ID code not found.")

    # 1. Prevent duplicate pending requests
    existing_req = db.query(AccessRequest).filter(
        AccessRequest.patient_id == patient.id,
        AccessRequest.doctor_id == doctor.id,
        AccessRequest.status == "pending"
    ).first()

    if existing_req:
        raise HTTPException(
            status_code=400, 
            detail="An access request is already pending for this patient. Please wait for them to respond."
        )

    # 2. Check if doctor already has active permissions
    existing_perm = db.query(AccessPermission).filter(
        AccessPermission.patient_id == patient.id,
        AccessPermission.doctor_id == doctor.id
    ).first()

    if existing_perm:
        # Check if the doctor already has ALL requested permissions active
        all_already_active = (
            (not req_data.can_view_records or existing_perm.can_view_records) and
            (not req_data.can_edit_records or getattr(existing_perm, "can_edit_records", False)) and
            (not req_data.can_view_medications or existing_perm.can_view_medications) and
            (not req_data.can_edit_medications or getattr(existing_perm, "can_edit_medications", False)) and
            (not req_data.can_view_documents or existing_perm.can_view_documents) and
            (not req_data.can_edit_documents or getattr(existing_perm, "can_edit_documents", False))
        )
        clean_expiry = existing_perm.expires_at.replace(tzinfo=None) if existing_perm.expires_at else None
        is_expired = clean_expiry and clean_expiry < datetime.utcnow()

        if all_already_active and not is_expired:
            raise HTTPException(
                status_code=400,
                detail="You already have all of these requested permissions active. Select new permissions (e.g. Edit Records, Prescribe Medications, or Documents) to request upgraded access."
            )

    # 3. Create the access request
    new_req = AccessRequest(
        patient_id=patient.id,
        doctor_id=doctor.id,
        message=req_data.message or ("Requesting upgraded/extended permissions" if existing_perm else "Consultation access request"),
        can_view_records=req_data.can_view_records,
        can_edit_records=req_data.can_edit_records,
        can_view_medications=req_data.can_view_medications,
        can_edit_medications=req_data.can_edit_medications,
        can_view_documents=req_data.can_view_documents,
        can_edit_documents=req_data.can_edit_documents,
        status="pending"
    )
    db.add(new_req)

    log = AccessLog(
        patient_id=patient.id,
        doctor_id=doctor.id,
        action=f"Dr. {current_user.name} requested {'upgraded' if existing_perm else 'new'} permissions"
    )
    db.add(log)
    db.commit()
    db.refresh(new_req)

    return {
        "message": "Access upgrade request sent to patient successfully!" if existing_perm else "Access request sent successfully!",
        "request_id": new_req.id
    }
# =========================================================
# 6. GET AUTHORIZED PATIENTS FOR DOCTOR
# =========================================================
@router.get("/patients")
def get_authorized_patients(
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    permissions = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | 
        (AccessPermission.doctor_id == doctor.user_id)
    ).all()

    patient_list = []
    now = datetime.utcnow()

    for perm in permissions:
        if perm.expires_at:
            clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
            if clean_expiry < now:
                continue

        patient = db.query(Patient).filter(Patient.id == perm.patient_id).first()
        if not patient:
            continue

        patient_user = db.query(User).filter(User.id == patient.user_id).first()

        patient_list.append({
            "permission_id": perm.id,
            "patient_db_id": patient.id,
            "patient_code": patient.patient_id,
            "name": patient_user.name if patient_user else "Patient",
            "email": patient_user.email if patient_user else "",
            "gender": patient.gender or "Not specified",
            "blood_group": patient.blood_group or "N/A",
            "can_view_records": perm.can_view_records,
            "can_edit_records": getattr(perm, "can_edit_records", False),
            "can_view_medications": perm.can_view_medications,
            "can_edit_medications": getattr(perm, "can_edit_medications", False),
            "can_view_documents": perm.can_view_documents,
            "can_edit_documents": getattr(perm, "can_edit_documents", False),
            "expires_at": perm.expires_at.isoformat() if perm.expires_at else None
        })

    return {"patients": patient_list, "total": len(patient_list)}


# =========================================================
# 7. MASTER: GET ALL MEDICAL RECORDS ACROSS AUTHORIZED PATIENTS
# =========================================================
@router.get("/records")
def get_all_doctor_records(
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    permissions = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.can_view_records == True
    ).all()

    valid_patient_ids = []
    patient_map = {}

    for perm in permissions:
        if perm.expires_at:
            clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
            if clean_expiry < now:
                continue
        valid_patient_ids.append(perm.patient_id)

    if not valid_patient_ids:
        return {"records": [], "total": 0}

    patients = db.query(Patient).filter(Patient.id.in_(valid_patient_ids)).all()
    for p in patients:
        user = db.query(User).filter(User.id == p.user_id).first()
        patient_map[p.id] = {
            "name": user.name if user else "Unknown Patient",
            "code": p.patient_id,
            "blood_group": p.blood_group or "N/A"
        }

    records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id.in_(valid_patient_ids)
    ).order_by(MedicalRecord.record_date.desc()).all()

    result = []
    for r in records:
        p_info = patient_map.get(r.patient_id, {"name": "Patient", "code": "N/A", "blood_group": "N/A"})
        result.append({
            "id": r.id,
            "patient_id": r.patient_id,
            "patient_name": p_info["name"],
            "patient_code": p_info["code"],
            "blood_group": p_info["blood_group"],
            "title": r.title,
            "diagnosis": r.diagnosis,
            "description": r.description,
            "notes": r.description,
            "doctor_name": r.doctor_name,
            "record_date": str(r.record_date) if r.record_date else None,
            "created_at": r.created_at
        })

    return {"records": result, "total": len(result)}


# =========================================================
# 8. MASTER: GET ALL PRESCRIPTIONS ACROSS AUTHORIZED PATIENTS
# =========================================================
@router.get("/prescriptions")
def get_all_doctor_prescriptions(
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    permissions = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.can_view_medications == True
    ).all()

    valid_patient_ids = []
    patient_map = {}

    for perm in permissions:
        if perm.expires_at:
            clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
            if clean_expiry < now:
                continue
        valid_patient_ids.append(perm.patient_id)

    if not valid_patient_ids:
        return {"prescriptions": [], "total": 0}

    patients = db.query(Patient).filter(Patient.id.in_(valid_patient_ids)).all()
    for p in patients:
        user = db.query(User).filter(User.id == p.user_id).first()
        patient_map[p.id] = {
            "name": user.name if user else "Unknown Patient",
            "code": p.patient_id
        }

    meds = db.query(Medication).filter(
        Medication.patient_id.in_(valid_patient_ids)
    ).order_by(Medication.created_at.desc()).all()

    result = []
    for m in meds:
        p_info = patient_map.get(m.patient_id, {"name": "Patient", "code": "N/A"})
        result.append({
            "id": m.id,
            "patient_id": m.patient_id,
            "patient_name": p_info["name"],
            "patient_code": p_info["code"],
            "name": m.name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "duration": m.duration,
            "doctor_name": m.doctor_name,
            "start_date": str(m.start_date) if m.start_date else None,
            "end_date": str(m.end_date) if m.end_date else None,
            "notes": m.notes,
            "created_at": m.created_at
        })

    return {"prescriptions": result, "total": len(result)}


# =========================================================
# 9. GET PATIENT MEDICAL RECORDS (SPECIFIC PATIENT)
# =========================================================
@router.get("/patients/{patient_id}/records")
def get_patient_records(
    patient_id: int,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not perm.can_view_records:
        raise HTTPException(status_code=403, detail="You do not have permission to view this patient's records.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    log = AccessLog(
        patient_id=patient_id,
        doctor_id=doctor.id,
        action=f"Dr. {current_user.name} viewed medical records"
    )
    db.add(log)
    db.commit()

    records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(MedicalRecord.record_date.desc()).all()

    return {
        "records": records,
        "access": {
            "can_view_records": perm.can_view_records,
            "can_edit_records": getattr(perm, "can_edit_records", False)
        }
    }


# =========================================================
# 10. CREATE PATIENT RECORD (CONSULTATION)
# =========================================================
@router.post("/patients/{patient_id}/records")
def create_patient_record(
    patient_id: int,
    record_data: MedicalRecordCreate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not perm.can_view_records:
        raise HTTPException(status_code=403, detail="No permission to access this patient's records.")

    if not getattr(perm, "can_edit_records", False):
        raise HTTPException(
            status_code=403,
            detail="Patient has granted View-Only access. You cannot create new records."
        )

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    new_record = MedicalRecord(
        patient_id=patient_id,
        title=record_data.title,
        diagnosis=record_data.diagnosis,
        description=record_data.description,
        doctor_name=f"Dr. {current_user.name}",
        record_date=record_data.record_date or date.today()
    )
    db.add(new_record)

    log = AccessLog(
        patient_id=patient_id,
        doctor_id=doctor.id,
        action=f"Dr. {current_user.name} added a record: '{new_record.title}'"
    )
    db.add(log)
    db.commit()
    db.refresh(new_record)

    return {"message": "Medical record added successfully", "record": new_record}


# =========================================================
# 11. EDIT PATIENT MEDICAL RECORD
# =========================================================
@router.put("/patients/{patient_id}/records/{record_id}")
def edit_patient_record(
    patient_id: int,
    record_id: int,
    record_data: MedicalRecordUpdate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not getattr(perm, "can_edit_records", False):
        raise HTTPException(status_code=403, detail="Patient has granted View-Only access. You cannot edit records.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    record = db.query(MedicalRecord).filter(
        MedicalRecord.id == record_id,
        MedicalRecord.patient_id == patient_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found.")

    if record_data.title is not None:
        record.title = record_data.title
    if record_data.diagnosis is not None:
        record.diagnosis = record_data.diagnosis
    if record_data.notes is not None:
        record.description = record_data.notes
    elif record_data.description is not None:
        record.description = record_data.description
    if record_data.record_date is not None:
        record.record_date = record_data.record_date

    record.doctor_name = f"Dr. {current_user.name}"
    db.commit()
    db.refresh(record)

    return {"message": "Medical record updated successfully", "record_id": record.id}


# =========================================================
# 12. GET PATIENT MEDICATIONS
# =========================================================
@router.get("/patients/{patient_id}/medications")
def get_patient_medications(
    patient_id: int,
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not perm.can_view_medications:
        raise HTTPException(status_code=403, detail="You do not have permission to view medications.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    meds = db.query(Medication).filter(Medication.patient_id == patient_id).all()
    medication_ids = [medication.id for medication in meds]
    first_day = date.today() - timedelta(days=6)
    logs = (
        db.query(MedicationDoseLog)
        .filter(
            MedicationDoseLog.medication_id.in_(medication_ids),
            MedicationDoseLog.dose_date >= first_day,
            MedicationDoseLog.dose_date <= date.today(),
        )
        .all()
        if medication_ids else []
    )
    logs_by_slot = {
        (log.medication_id, log.dose_date, log.dose_time): log.status
        for log in logs
    }
    now = datetime.now()
    adherence_by_medication = {}
    for medication in meds:
        taken = 0
        due = 0
        for day_offset in range(7):
            target_date = first_day + timedelta(days=day_offset)
            if medication.start_date and target_date < medication.start_date:
                continue
            if medication.end_date and target_date > medication.end_date:
                continue
            for dose_time in medication.dose_times or []:
                scheduled_at = datetime.combine(target_date, time.fromisoformat(dose_time))
                if scheduled_at <= now:
                    due += 1
                    if logs_by_slot.get((medication.id, target_date, dose_time)) == "taken":
                        taken += 1
        adherence_by_medication[medication.id] = {"taken": taken, "due": due}

    return {
        "medications": [
            {
                "id": medication.id,
                "name": medication.name,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "dose_times": medication.dose_times or [],
                "duration": medication.duration,
                "doctor_name": medication.doctor_name,
                "start_date": medication.start_date,
                "end_date": medication.end_date,
                "notes": medication.notes,
                "adherence_7d": adherence_by_medication[medication.id],
            }
            for medication in meds
        ],
        "access": {
            "can_view_medications": perm.can_view_medications,
            "can_edit_medications": getattr(perm, "can_edit_medications", False)
        }
    }


# =========================================================
# 13. PRESCRIBE NEW MEDICATION
# =========================================================
@router.post("/patients/{patient_id}/medications")
def prescribe_patient_medication(
    patient_id: int,
    med_data: MedicationCreate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not getattr(perm, "can_edit_medications", False):
        raise HTTPException(status_code=403, detail="No permission to prescribe medications.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    new_med = Medication(
        patient_id=patient_id,
        name=med_data.name,
        dosage=med_data.dosage,
        frequency=med_data.frequency,
        duration=med_data.duration,
        doctor_name=f"Dr. {current_user.name}",
        start_date=med_data.start_date or date.today(),
        end_date=med_data.end_date,
        notes=med_data.notes
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)

    return {"message": "Medication prescribed successfully", "medication": new_med}


# =========================================================
# 14. EDIT PATIENT MEDICATION
# =========================================================
@router.put("/patients/{patient_id}/medications/{medication_id}")
def edit_patient_medication(
    patient_id: int,
    medication_id: int,
    med_data: MedicationUpdate,
    doctor: Doctor = Depends(get_current_doctor),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not getattr(perm, "can_edit_medications", False):
        raise HTTPException(status_code=403, detail="No permission to edit medications.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    medication = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.patient_id == patient_id
    ).first()

    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found.")

    if med_data.name is not None:
        medication.name = med_data.name
    if med_data.dosage is not None:
        medication.dosage = med_data.dosage
    if med_data.frequency is not None:
        medication.frequency = med_data.frequency
    if med_data.duration is not None:
        medication.duration = med_data.duration
    if med_data.notes is not None:
        medication.notes = med_data.notes

    medication.doctor_name = f"Dr. {current_user.name}"
    db.commit()
    db.refresh(medication)

    return {"message": "Medication updated successfully", "medication_id": medication.id}


# =========================================================
# 15. GET PATIENT DOCUMENTS
# =========================================================
@router.get("/patients/{patient_id}/documents")
def get_patient_documents(
    patient_id: int,
    doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    perm = db.query(AccessPermission).filter(
        (AccessPermission.doctor_id == doctor.id) | (AccessPermission.doctor_id == doctor.user_id),
        AccessPermission.patient_id == patient_id
    ).first()

    if not perm or not perm.can_view_documents:
        raise HTTPException(status_code=403, detail="No permission to view documents.")

    if perm.expires_at:
        clean_expiry = perm.expires_at.replace(tzinfo=None) if perm.expires_at.tzinfo else perm.expires_at
        if clean_expiry < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Access permission has expired.")

    docs = db.query(Document).filter(Document.patient_id == patient_id).all()
    return {
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "document_type": doc.document_type,
                "file_name": doc.file_name,
                "file_url": f"http://127.0.0.1:8000/api/documents/{doc.id}/file",
                "doctor_name": doc.doctor_name,
                "document_date": str(doc.document_date) if doc.document_date else None,
                "created_at": doc.created_at
            }
            for doc in docs
        ],
        "access": {
            "can_view_documents": perm.can_view_documents,
            "can_edit_documents": getattr(perm, "can_edit_documents", False)
        }
    }