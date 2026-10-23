from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User, Patient, Doctor, AccessPermission, AccessRequest, AccessLog
from schemas import AccessPermissionCreate, AccessPermissionUpdate, AccessRequestRespond
from security import get_current_user

router = APIRouter(
    prefix="/api/permissions",
    tags=["Access Permissions"]
)


# ==========================================
# PATIENT: GET INCOMING ACCESS REQUESTS
# ==========================================
@router.get("/requests")
def get_pending_access_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        return {"requests": []}

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        return {"requests": []}

    requests = db.query(AccessRequest).filter(
        AccessRequest.patient_id == patient.id,
        AccessRequest.status == "pending"
    ).order_by(AccessRequest.created_at.desc()).all()

    result = []
    for req in requests:
        doctor = db.query(Doctor).filter(Doctor.id == req.doctor_id).first()
        doctor_user = db.query(User).filter(User.id == doctor.user_id).first() if doctor else None

        result.append({
            "request_id": req.id,
            "doctor_id": req.doctor_id,
            "doctor_code": doctor.doctor_id if doctor else "DOC",
            "doctor_name": doctor_user.name if doctor_user else "Doctor",
            "specialization": doctor.specialization if doctor else "General",
            "hospital": doctor.hospital if doctor else "MediLink Network",
            "message": req.message or "Requesting consultation access",
            "can_view_records": req.can_view_records,
            "can_edit_records": req.can_edit_records,
            "can_view_medications": req.can_view_medications,
            "can_edit_medications": req.can_edit_medications,
            "can_view_documents": req.can_view_documents,
            "can_edit_documents": req.can_edit_documents,
            "requested_at": req.created_at
        })

    return {"requests": result, "total": len(result)}


# ==========================================
# PATIENT: RESPOND TO ACCESS REQUEST
# ==========================================
@router.post("/requests/{request_id}/respond")
def respond_access_request(
    request_id: int,
    body: AccessRequestRespond,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can approve or reject access requests")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    req = db.query(AccessRequest).filter(
        AccessRequest.id == request_id,
        AccessRequest.patient_id == patient.id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Access request not found")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"This request has already been {req.status}")

    if body.action == "reject":
        req.status = "rejected"
        db.commit()
        return {"message": "Access request declined"}

    elif body.action == "approve":
        req.status = "approved"

        # Check if permission already exists, otherwise create
        perm = db.query(AccessPermission).filter(
            AccessPermission.patient_id == patient.id,
            AccessPermission.doctor_id == req.doctor_id
        ).first()

        can_view_rec = body.can_view_records if body.can_view_records is not None else req.can_view_records
        can_edit_rec = body.can_edit_records if body.can_edit_records is not None else req.can_edit_records
        can_view_med = body.can_view_medications if body.can_view_medications is not None else req.can_view_medications
        can_edit_med = body.can_edit_medications if body.can_edit_medications is not None else req.can_edit_medications
        can_view_doc = body.can_view_documents if body.can_view_documents is not None else req.can_view_documents
        can_edit_doc = body.can_edit_documents if body.can_edit_documents is not None else req.can_edit_documents

        if not perm:
            perm = AccessPermission(
                patient_id=patient.id,
                doctor_id=req.doctor_id,
                can_view_records=can_view_rec,
                can_edit_records=can_edit_rec,
                can_view_medications=can_view_med,
                can_edit_medications=can_edit_med,
                can_view_documents=can_view_doc,
                can_edit_documents=can_edit_doc
            )
            db.add(perm)
        else:
            perm.can_view_records = can_view_rec
            perm.can_edit_records = can_edit_rec
            perm.can_view_medications = can_view_med
            perm.can_edit_medications = can_edit_med
            perm.can_view_documents = can_view_doc
            perm.can_edit_documents = can_edit_doc

        # Log
        log = AccessLog(
            patient_id=patient.id,
            doctor_id=req.doctor_id,
            action=f"Patient {current_user.name} approved doctor access request"
        )
        db.add(log)
        db.commit()
        return {"message": "Access request approved successfully"}

    raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")


# ==========================================
# GRANT ACCESS DIRECTLY
# ==========================================
@router.post("/")
def grant_access(
    permission_data: AccessPermissionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can grant access")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    doctor = db.query(Doctor).filter(Doctor.id == permission_data.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    existing_permission = db.query(AccessPermission).filter(
        AccessPermission.patient_id == patient.id,
        AccessPermission.doctor_id == doctor.id
    ).first()

    if existing_permission:
        raise HTTPException(
            status_code=400,
            detail="Access permission already exists. Edit the existing permission instead."
        )

    new_permission = AccessPermission(
        patient_id=patient.id,
        doctor_id=doctor.id,
        can_view_records=permission_data.can_view_records,
        can_edit_records=permission_data.can_edit_records,
        can_view_medications=permission_data.can_view_medications,
        can_edit_medications=permission_data.can_edit_medications,
        can_view_documents=permission_data.can_view_documents,
        can_edit_documents=permission_data.can_edit_documents,
        expires_at=permission_data.expires_at
    )

    db.add(new_permission)
    db.commit()
    db.refresh(new_permission)

    return {
        "message": "Access granted successfully",
        "permission": {
            "id": new_permission.id,
            "patient_id": new_permission.patient_id,
            "doctor_id": new_permission.doctor_id,
            "can_view_records": new_permission.can_view_records,
            "can_edit_records": new_permission.can_edit_records,
            "can_view_medications": new_permission.can_view_medications,
            "can_edit_medications": new_permission.can_edit_medications,
            "can_view_documents": new_permission.can_view_documents,
            "can_edit_documents": new_permission.can_edit_documents,
            "granted_at": new_permission.granted_at,
            "expires_at": new_permission.expires_at
        }
    }


# ==========================================
# VIEW MY ACCESS PERMISSIONS
# ==========================================
@router.get("/")
def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can view access permissions")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    permissions = db.query(AccessPermission).filter(
        AccessPermission.patient_id == patient.id
    ).all()

    result = []
    for permission in permissions:
        doctor = db.query(Doctor).filter(Doctor.id == permission.doctor_id).first()
        doctor_user = db.query(User).filter(User.id == doctor.user_id).first() if doctor else None

        result.append({
            "permission_id": permission.id,
            "doctor_id": permission.doctor_id,
            "doctor_name": doctor_user.name if doctor_user else "Doctor",
            "can_view_records": permission.can_view_records,
            "can_edit_records": getattr(permission, "can_edit_records", False),
            "can_view_medications": permission.can_view_medications,
            "can_edit_medications": getattr(permission, "can_edit_medications", False),
            "can_view_documents": permission.can_view_documents,
            "can_edit_documents": getattr(permission, "can_edit_documents", False),
            "granted_at": permission.granted_at,
            "expires_at": permission.expires_at
        })

    return {
        "patient_id": patient.patient_id,
        "total_permissions": len(result),
        "permissions": result
    }


# ==========================================
# UPDATE ACCESS PERMISSIONS
# ==========================================
@router.patch("/{permission_id}")
def update_access_permission(
    permission_id: int,
    permission_data: AccessPermissionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can update access permissions")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    permission = db.query(AccessPermission).filter(
        AccessPermission.id == permission_id,
        AccessPermission.patient_id == patient.id
    ).first()

    if not permission:
        raise HTTPException(status_code=404, detail="Access permission not found")

    if permission_data.can_view_records is not None:
        permission.can_view_records = permission_data.can_view_records
    if permission_data.can_edit_records is not None:
        permission.can_edit_records = permission_data.can_edit_records
    if permission_data.can_view_medications is not None:
        permission.can_view_medications = permission_data.can_view_medications
    if permission_data.can_edit_medications is not None:
        permission.can_edit_medications = permission_data.can_edit_medications
    if permission_data.can_view_documents is not None:
        permission.can_view_documents = permission_data.can_view_documents
    if permission_data.can_edit_documents is not None:
        permission.can_edit_documents = permission_data.can_edit_documents
    if permission_data.expires_at is not None:
        permission.expires_at = permission_data.expires_at

    db.commit()
    db.refresh(permission)
    return {"message": "Access permissions updated successfully"}


# ==========================================
# REVOKE ACCESS
# ==========================================
@router.delete("/{permission_id}")
def revoke_access(
    permission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can revoke access")

    patient = db.query(Patient).filter(Patient.user_id == current_user.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    permission = db.query(AccessPermission).filter(
        AccessPermission.id == permission_id,
        AccessPermission.patient_id == patient.id
    ).first()

    if not permission:
        raise HTTPException(status_code=404, detail="Access permission not found")

    db.delete(permission)
    db.commit()
    return {"message": "Access revoked successfully"}