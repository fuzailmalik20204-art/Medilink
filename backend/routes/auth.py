from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import get_db
from models import User, Patient, Doctor
from schemas import UserCreate, UserLogin
from security import create_access_token, get_current_user


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# ==========================================
# SIGNUP
# ==========================================

@router.post("/signup")
def signup(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    hashed_password = pwd_context.hash(
        user.password
    )

    user_role = getattr(user, "role", None) or "patient"

    new_user = User(
        name=user.name,
        email=user.email,
        password=hashed_password,
        role=user_role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Auto-create profile on signup
    generated_code = None

    if user_role == "patient":
        generated_code = f"PAT-{new_user.id:05d}"
        new_patient = Patient(
            user_id=new_user.id,
            patient_id=generated_code
        )
        db.add(new_patient)
        db.commit()
        db.refresh(new_patient)

    elif user_role in ["doctor", "provider"]:
        generated_code = f"DOC-{new_user.id:05d}"
        new_doctor = Doctor(
            user_id=new_user.id,
            doctor_id=generated_code
        )
        db.add(new_doctor)
        db.commit()
        db.refresh(new_doctor)

    return {
        "message": "User registered successfully",
        "user_id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
        "role": new_user.role,
        "profile_id": generated_code
    }


# ==========================================
# LOGIN (WITH AUTO-REPAIR FOR EXISTING USERS)
# ==========================================

@router.post("/login")
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):

    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not existing_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    password_correct = pwd_context.verify(
        user.password,
        existing_user.password
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # -------------------------------------------------------------
    # AUTO-REPAIR: If this user was created earlier without a profile,
    # create it now so the dashboard won't return 404!
    # -------------------------------------------------------------
    if existing_user.role == "patient":
        patient_profile = db.query(Patient).filter(
            Patient.user_id == existing_user.id
        ).first()

        if not patient_profile:
            patient_profile = Patient(
                user_id=existing_user.id,
                patient_id=f"PAT-{existing_user.id:05d}"
            )
            db.add(patient_profile)
            db.commit()

    elif existing_user.role in ["doctor", "provider"]:
        doctor_profile = db.query(Doctor).filter(
            Doctor.user_id == existing_user.id
        ).first()

        if not doctor_profile:
            doctor_profile = Doctor(
                user_id=existing_user.id,
                doctor_id=f"DOC-{existing_user.id:05d}"
            )
            db.add(doctor_profile)
            db.commit()
    # -------------------------------------------------------------

    token_data = {
        "user_id": existing_user.id,
        "email": existing_user.email,
        "role": existing_user.role
    }

    access_token = create_access_token(
        token_data
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": existing_user.id,
            "name": existing_user.name,
            "email": existing_user.email,
            "role": existing_user.role
        }
    }


# ==========================================
# CURRENT USER
# ==========================================

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user)
):

    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role
    }