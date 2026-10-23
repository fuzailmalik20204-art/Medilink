from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Boolean, JSON, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="patient")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    patient_id = Column(String(30), unique=True, nullable=False, index=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    blood_group = Column(String(10), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    emergency_contact = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    doctor_id = Column(String(30), unique=True, nullable=False, index=True)
    specialization = Column(String(100), nullable=True)
    hospital = Column(String(150), nullable=True)
    license_number = Column(String(100), unique=True, nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    diagnosis = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    doctor_name = Column(String(150), nullable=True)
    record_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AccessPermission(Base):
    __tablename__ = "access_permissions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)

    can_view_records = Column(Boolean, default=True, nullable=False)
    can_edit_records = Column(Boolean, default=False, nullable=False)
    can_view_medications = Column(Boolean, default=False, nullable=False)
    can_edit_medications = Column(Boolean, default=False, nullable=False)
    can_view_documents = Column(Boolean, default=False, nullable=False)
    can_edit_documents = Column(Boolean, default=False, nullable=False)

    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)


class AccessRequest(Base):
    __tablename__ = "access_requests"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    message = Column(String(255), nullable=True)

    can_view_records = Column(Boolean, default=True, nullable=False)
    can_edit_records = Column(Boolean, default=False, nullable=False)
    can_view_medications = Column(Boolean, default=False, nullable=False)
    can_edit_medications = Column(Boolean, default=False, nullable=False)
    can_view_documents = Column(Boolean, default=False, nullable=False)
    can_edit_documents = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    document_type = Column(String(100), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    doctor_name = Column(String(150), nullable=True)
    document_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    dosage = Column(String(100), nullable=True)
    frequency = Column(String(100), nullable=True)
    dose_times = Column(JSON, nullable=False, default=list)
    duration = Column(String(100), nullable=True)
    doctor_name = Column(String(150), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MedicationDoseLog(Base):
    __tablename__ = "medication_dose_logs"
    __table_args__ = (
        UniqueConstraint("medication_id", "dose_date", "dose_time", name="uq_medication_dose_slot"),
    )

    id = Column(Integer, primary_key=True, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True)
    dose_date = Column(Date, nullable=False, index=True)
    dose_time = Column(String(5), nullable=False)
    status = Column(String(10), nullable=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)