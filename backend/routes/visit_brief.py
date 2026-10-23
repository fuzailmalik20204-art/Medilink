from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import MedicalRecord, Medication, Patient, User
from security import get_current_user


router = APIRouter(prefix="/api/visit-brief", tags=["Visit Brief"])


def build_visit_brief(patient_name, records, medications, today=None):
    today = today or datetime.now(timezone.utc).date()
    current_medications = [
        medication
        for medication in medications
        if not (
            (medication.start_date and medication.start_date > today)
            or (medication.end_date and medication.end_date < today)
        )
    ]
    recent_records = records[:10]
    listed_medications = current_medications[:12]

    discussion_questions = [
        "Which details in this brief are most important for today's visit?",
        "What follow-up or next steps should I understand after this visit?",
    ]
    latest_diagnosis = next(
        (record.diagnosis for record in recent_records if record.diagnosis),
        None,
    )
    if latest_diagnosis:
        discussion_questions.insert(
            0,
            f"What should I understand about the diagnosis recorded as “{latest_diagnosis}”?",
        )
    if current_medications:
        discussion_questions.append(
            "Could you confirm that this medication list is current and complete?"
        )

    return {
        "patient_name": patient_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "active_medication_count": len(current_medications),
        "records": [
            {
                "id": record.id,
                "title": record.title,
                "record_date": record.record_date.isoformat() if record.record_date else None,
                "diagnosis": record.diagnosis,
                "description": record.description,
                "doctor_name": record.doctor_name,
                "source": f"Medical record #{record.id}",
            }
            for record in recent_records
        ],
        "records_omitted": len(records) - len(recent_records),
        "medications": [
            {
                "id": medication.id,
                "name": medication.name,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "start_date": medication.start_date.isoformat() if medication.start_date else None,
                "end_date": medication.end_date.isoformat() if medication.end_date else None,
                "doctor_name": medication.doctor_name,
                "source": f"Medication entry #{medication.id}",
            }
            for medication in listed_medications
        ],
        "medications_omitted": len(current_medications) - len(listed_medications),
        "discussion_questions": discussion_questions,
        "notice": (
            "This template-based brief organizes information saved in MediLink. "
            "It is not an AI-generated medical assessment, diagnosis, or treatment advice. "
            "Medication dates do not confirm what you currently take; verify details with your clinician. "
            "Uploaded document contents are not included."
        ),
    }


@router.get("/")
def get_visit_brief(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can generate their visit brief")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    records = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.patient_id == patient.id)
        .order_by(MedicalRecord.record_date.desc(), MedicalRecord.id.desc())
        .all()
    )
    medications = (
        db.query(Medication)
        .filter(Medication.patient_id == patient.id)
        .order_by(Medication.created_at.desc(), Medication.id.desc())
        .all()
    )

    return build_visit_brief(current_user.name, records, medications)
