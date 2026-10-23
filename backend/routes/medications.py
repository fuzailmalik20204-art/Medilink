import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import AccessLog, AccessPermission, Doctor, Medication, MedicationDoseLog, Patient, User
from schemas import MedicationDoseLogCreate, MedicationUpdate
from security import get_current_user

router = APIRouter(prefix="/api/medications", tags=["Medications"])


def normalize_dose_times(values):
    if values is None:
        return []
    if not isinstance(values, list):
        raise HTTPException(status_code=422, detail="Dose times must be a list of 24-hour times")

    normalized = set()
    for value in values:
        try:
            parsed = datetime.strptime(value, "%H:%M").time()
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Dose times must use HH:MM format")
        normalized.add(parsed.strftime("%H:%M"))
    return sorted(normalized)


def medication_is_active_on(medication, target_date):
    return not (
        (medication.start_date and target_date < medication.start_date)
        or (medication.end_date and target_date > medication.end_date)
    )


def require_patient(current_user, db):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can manage dose tracking")
    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return patient


@router.post("/")
def create_medication(
    name: str = Form(...),
    dosage: str | None = Form(None),
    frequency: str | None = Form(None),
    dose_times: str | None = Form(None),
    duration: str | None = Form(None),
    doctor_name: str | None = Form(None),
    start_date: date | None = Form(None),
    end_date: date | None = Form(None),
    notes: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    patient = require_patient(current_user, db)

    try:
        submitted_times = json.loads(dose_times) if dose_times else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Dose times must be valid JSON")

    medication = Medication(
        patient_id=patient.id,
        name=name,
        dosage=dosage,
        frequency=frequency,
        dose_times=normalize_dose_times(submitted_times),
        duration=duration,
        doctor_name=doctor_name,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
    )

    db.add(medication)
    db.commit()
    db.refresh(medication)

    return {
        "message": "Medication added successfully",
        "medication": {
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
            "created_at": medication.created_at,
        },
    }


@router.get("/")
def get_my_medications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can view medications")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    medications = (
        db.query(Medication)
        .filter(Medication.patient_id == patient.id)
        .order_by(Medication.created_at.desc())
        .all()
    )

    return {
        "patient_id": patient.patient_id,
        "total_medications": len(medications),
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
                "created_at": medication.created_at,
            }
            for medication in medications
        ],
    }


@router.put("/{medication_id}")
def update_medication(
    medication_id: int,
    med_data: MedicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    medication = db.query(Medication).filter(Medication.id == medication_id).first()
    if not medication:
        raise HTTPException(status_code=404, detail="Medication record not found")

    if current_user.role == "patient":
        patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not patient or medication.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="You do not own this medication entry")
    elif current_user.role in ["doctor", "provider"]:
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor profile not found")

        permission = (
            db.query(AccessPermission)
            .filter(
                AccessPermission.doctor_id == doctor.id,
                AccessPermission.patient_id == medication.patient_id,
                AccessPermission.can_view_medications.is_(True),
            )
            .first()
        )

        if not permission:
            raise HTTPException(
                status_code=403,
                detail="No permission to modify this patient's medications",
            )

        if permission.expires_at and permission.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Permission has expired")

        medication.doctor_name = current_user.name
        db.add(
            AccessLog(
                patient_id=medication.patient_id,
                doctor_id=doctor.id,
                action=f"Updated medication #{medication.id} ({medication.name})",
            )
        )
    else:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if med_data.name is not None:
        medication.name = med_data.name
    if med_data.dosage is not None:
        medication.dosage = med_data.dosage
    if med_data.frequency is not None:
        medication.frequency = med_data.frequency
    if med_data.dose_times is not None:
        medication.dose_times = normalize_dose_times(med_data.dose_times)
    if med_data.duration is not None:
        medication.duration = med_data.duration
    if med_data.start_date is not None:
        medication.start_date = med_data.start_date
    if med_data.end_date is not None:
        medication.end_date = med_data.end_date
    if med_data.notes is not None:
        medication.notes = med_data.notes

    db.commit()
    db.refresh(medication)

    return {"message": "Medication updated successfully", "medication_id": medication.id}


@router.get("/adherence")
def get_medication_adherence(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    patient = require_patient(current_user, db)
    today = date.today()
    now = datetime.now()
    first_day = today - timedelta(days=6)

    medications = db.query(Medication).filter(Medication.patient_id == patient.id).all()
    medication_ids = [medication.id for medication in medications]
    logs = (
        db.query(MedicationDoseLog)
        .filter(
            MedicationDoseLog.medication_id.in_(medication_ids),
            MedicationDoseLog.dose_date >= first_day,
            MedicationDoseLog.dose_date <= today,
        )
        .all()
        if medication_ids else []
    )
    log_by_slot = {
        (log.medication_id, log.dose_date, log.dose_time): log
        for log in logs
    }

    today_entries = []
    week = []
    for day_offset in range(6, -1, -1):
        target_date = today - timedelta(days=day_offset)
        taken_count = 0
        due_count = 0

        for medication in medications:
            if not medication_is_active_on(medication, target_date):
                continue
            for dose_time in medication.dose_times or []:
                scheduled_at = datetime.combine(target_date, time.fromisoformat(dose_time))
                log = log_by_slot.get((medication.id, target_date, dose_time))
                is_due = scheduled_at <= now
                if is_due:
                    due_count += 1
                    if log and log.status == "taken":
                        taken_count += 1

                if target_date == today:
                    today_entries.append({
                        "medication_id": medication.id,
                        "medication_name": medication.name,
                        "dosage": medication.dosage,
                        "dose_time": dose_time,
                        "status": log.status if log else ("pending" if is_due else "upcoming"),
                        "logged_at": log.logged_at if log else None,
                    })

        week.append({
            "date": target_date.isoformat(),
            "taken": taken_count,
            "due": due_count,
            "percentage": round(taken_count * 100 / due_count) if due_count else None,
        })

    return {
        "date": today.isoformat(),
        "today": today_entries,
        "week": week,
        "total_taken": sum(day["taken"] for day in week),
        "total_due": sum(day["due"] for day in week),
    }


@router.post("/{medication_id}/doses")
def log_medication_dose(
    medication_id: int,
    dose_data: MedicationDoseLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    patient = require_patient(current_user, db)
    medication = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.patient_id == patient.id)
        .first()
    )
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")

    dose_time = normalize_dose_times([dose_data.dose_time])
    dose_time = dose_time[0]
    if dose_time not in (medication.dose_times or []):
        raise HTTPException(status_code=400, detail="This time is not in the medication schedule")
    if dose_data.status not in {"taken", "skipped"}:
        raise HTTPException(status_code=422, detail="Dose status must be taken or skipped")
    if dose_data.dose_date > date.today() or dose_data.dose_date < date.today() - timedelta(days=6):
        raise HTTPException(status_code=400, detail="Dose tracking is limited to the current seven-day period")
    if not medication_is_active_on(medication, dose_data.dose_date):
        raise HTTPException(status_code=400, detail="Medication was not active on this date")
    if datetime.combine(dose_data.dose_date, time.fromisoformat(dose_time)) > datetime.now():
        raise HTTPException(status_code=400, detail="A future dose cannot be logged")

    dose_log = (
        db.query(MedicationDoseLog)
        .filter_by(medication_id=medication.id, dose_date=dose_data.dose_date, dose_time=dose_time)
        .first()
    )
    if dose_log:
        dose_log.status = dose_data.status
        dose_log.logged_at = datetime.now(timezone.utc)
    else:
        dose_log = MedicationDoseLog(
            medication_id=medication.id,
            dose_date=dose_data.dose_date,
            dose_time=dose_time,
            status=dose_data.status,
        )
        db.add(dose_log)

    db.commit()
    db.refresh(dose_log)
    return {
        "message": "Dose status saved",
        "medication_id": medication.id,
        "dose_date": dose_log.dose_date.isoformat(),
        "dose_time": dose_log.dose_time,
        "status": dose_log.status,
    }


@router.delete("/{medication_id}")
def delete_medication(
    medication_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can delete medications")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    medication = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.patient_id == patient.id)
        .first()
    )

    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")

    db.query(MedicationDoseLog).filter(MedicationDoseLog.medication_id == medication.id).delete()
    db.delete(medication)
    db.commit()

    return {"message": "Medication deleted successfully", "medication_id": medication_id}