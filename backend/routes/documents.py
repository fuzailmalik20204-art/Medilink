import os
import uuid
import mimetypes
from datetime import date, datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User, Patient, Doctor, Document, AccessPermission, AccessLog
from security import get_current_user


router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"]
)


# ================================
# UPLOAD DOCUMENT
# ================================

@router.post("/")
async def upload_document(
    title: str = Form(...),
    document_type: str = Form(None),
    doctor_name: str = Form(None),
    document_date: date = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Only patients can upload documents"
        )

    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found"
        )

    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
    original_name = file.filename or ""
    extension = os.path.splitext(original_name)[1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type"
        )

    upload_directory = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "uploads"
    )
    os.makedirs(upload_directory, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(upload_directory, unique_filename)

    with open(file_path, "wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)

    relative_file_path = f"uploads/{unique_filename}"

    new_document = Document(
        patient_id=patient.id,
        title=title,
        document_type=document_type,
        file_name=original_name,
        file_path=relative_file_path,
        doctor_name=doctor_name,
        document_date=document_date
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return {
        "message": "Document uploaded successfully",
        "document": {
            "id": new_document.id,
            "title": new_document.title,
            "document_type": new_document.document_type,
            "file_name": new_document.file_name,
            "file_path": new_document.file_path,
            "doctor_name": new_document.doctor_name,
            "document_date": new_document.document_date,
            "created_at": new_document.created_at
        }
    }


# ================================
# GET MY DOCUMENTS (PATIENT)
# ================================

@router.get("/")
def get_my_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(
            status_code=403,
            detail="Only patients can view this list"
        )

    patient = db.query(Patient).filter(
        Patient.user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found"
        )

    documents = db.query(Document).filter(
        Document.patient_id == patient.id
    ).order_by(Document.created_at.desc()).all()

    return {
        "patient_id": patient.patient_id,
        "total_documents": len(documents),
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "document_type": doc.document_type,
                "file_name": doc.file_name,
                "file_path": doc.file_path,
                "doctor_name": doc.doctor_name,
                "document_date": doc.document_date,
                "created_at": doc.created_at
            }
            for doc in documents
        ]
    }


# ==========================================
# VIEW / STREAM DOCUMENT (PATIENT & DOCTOR)
# ==========================================

@router.get("/{document_id}/file")
@router.get("/{document_id}/view")
def view_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Fetch the document
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # 2. Check Permissions
    if current_user.role == "patient":
        patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
        if not patient or document.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="You do not own this document")

    elif current_user.role in ["doctor", "provider"]:
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor profile not found")

        # Verify access permission granted by this patient
        permission = db.query(AccessPermission).filter(
            AccessPermission.doctor_id == doctor.id,
            AccessPermission.patient_id == document.patient_id,
            AccessPermission.can_view_documents == True
        ).first()

        if not permission:
            raise HTTPException(
                status_code=403,
                detail="Patient has not granted permission to view documents"
            )

        # Check expiration if set
        if permission.expires_at and permission.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=403,
                detail="Access permission to view documents has expired"
            )

        # Log document access
        log = AccessLog(
            patient_id=document.patient_id,
            doctor_id=doctor.id,
            action=f"Viewed document #{document.id} ({document.title})"
        )
        db.add(log)
        db.commit()

    else:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # 3. Locate physical file
    full_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        document.file_path
    )

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Physical file not found on server")

    # 4. Set media type for inline viewing (PDF/images preview inside browser)
    media_type, _ = mimetypes.guess_type(full_path)
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=full_path,
        filename=document.file_name,
        media_type=media_type,
        content_disposition_type="inline"
    )


# ================================
# DELETE DOCUMENT
# ================================

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can delete documents")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    document = db.query(Document).filter(
        Document.id == document_id,
        Document.patient_id == patient.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    full_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        document.file_path
    )

    if os.path.exists(full_path):
        os.remove(full_path)

    db.delete(document)
    db.commit()

    return {
        "message": "Document deleted successfully",
        "document_id": document_id
    }