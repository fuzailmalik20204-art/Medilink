import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from document_content import DocumentContentError, extract_document_content
from models import Document, MedicalRecord, Medication, Patient, User
from security import get_current_user


router = APIRouter(prefix="/api/visit-brief", tags=["Visit Brief"])
logger = logging.getLogger(__name__)
UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"


def build_visit_brief(patient_name, records, medications, documents, today=None):
    today = today or datetime.now(timezone.utc).date()
    within_date_range_medications = [
        medication
        for medication in medications
        if not (
            (medication.start_date and medication.start_date > today)
            or (medication.end_date and medication.end_date < today)
        )
    ]
    discussion_questions = [
        "Which details in this brief are most important for today's visit?",
        "What follow-up or next steps should I understand after this visit?",
    ]
    latest_diagnosis = next(
        (record.diagnosis for record in records if record.diagnosis),
        None,
    )
    if latest_diagnosis:
        discussion_questions.insert(
            0,
            f"What should I understand about the diagnosis recorded as “{latest_diagnosis}”?",
        )
    if medications:
        discussion_questions.append(
            "Could you confirm that this medication list is current and complete?"
        )

    return {
        "patient_name": patient_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "medications_within_date_range_count": len(within_date_range_medications),
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
            for record in records
        ],
        "medications": [
            {
                "id": medication.id,
                "name": medication.name,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "start_date": medication.start_date.isoformat() if medication.start_date else None,
                "end_date": medication.end_date.isoformat() if medication.end_date else None,
                "doctor_name": medication.doctor_name,
                "within_date_range": medication in within_date_range_medications,
                "source": f"Medication entry #{medication.id}",
            }
            for medication in medications
        ],
        "documents": documents,
        "document_count": len(documents),
        "documents_read": sum(document["extraction_status"] in {"read", "partial"} for document in documents),
        "discussion_questions": discussion_questions,
        "notice": (
            "This source-based brief organizes information saved in MediLink; it does not infer what a patient has or diagnose. "
            "Extracted document text and OCR can contain errors; verify it against the original file. "
            "Medication dates do not confirm what you currently take; verify details with your clinician. "
            "No uploaded content is sent to an external AI service. Missing or unreadable document content is identified."
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

    document_rows = (
        db.query(Document)
        .filter(Document.patient_id == patient.id)
        .order_by(Document.document_date.desc(), Document.created_at.desc(), Document.id.desc())
        .all()
    )
    documents = []
    for document in document_rows:
        try:
            relative_path = Path(document.file_path)
            if relative_path.is_absolute():
                raise DocumentContentError("Stored document path is invalid.")
            full_path = (UPLOAD_DIRECTORY.parent / relative_path).resolve()
            if not full_path.is_relative_to(UPLOAD_DIRECTORY.resolve()):
                raise DocumentContentError("Stored document path is invalid.")
            extraction = extract_document_content(full_path, document.file_name)
            documents.append({
                "id": document.id,
                "title": document.title,
                "document_type": document.document_type,
                "file_name": document.file_name,
                "document_date": document.document_date.isoformat() if document.document_date else None,
                "doctor_name": document.doctor_name,
                "extraction_status": extraction["status"],
                "status_message": extraction["status_message"],
                "ocr_used": extraction["ocr_used"],
                "truncated": extraction["truncated"],
                "text": extraction["text"],
                "source": f"Uploaded document #{document.id}: {document.file_name}",
            })
        except DocumentContentError as error:
            documents.append({
                "id": document.id,
                "title": document.title,
                "document_type": document.document_type,
                "file_name": document.file_name,
                "document_date": document.document_date.isoformat() if document.document_date else None,
                "doctor_name": document.doctor_name,
                "extraction_status": "unavailable",
                "status_message": str(error),
                "ocr_used": False,
                "truncated": False,
                "text": None,
                "source": f"Uploaded document #{document.id}: {document.file_name}",
            })
        except OSError:
            logger.exception("Unable to read uploaded document %s for visit brief", document.id)
            documents.append({
                "id": document.id,
                "title": document.title,
                "document_type": document.document_type,
                "file_name": document.file_name,
                "document_date": document.document_date.isoformat() if document.document_date else None,
                "doctor_name": document.doctor_name,
                "extraction_status": "unavailable",
                "status_message": "The uploaded file could not be accessed. Re-upload it to include its contents.",
                "ocr_used": False,
                "truncated": False,
                "text": None,
                "source": f"Uploaded document #{document.id}: {document.file_name}",
            })

    return build_visit_brief(current_user.name, records, medications, documents)
