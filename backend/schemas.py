from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str | None = "patient"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PatientCreate(BaseModel):
    date_of_birth: date | None = None
    gender: str | None = None
    blood_group: str | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact: str | None = None


class MedicalRecordCreate(BaseModel):
    title: str
    diagnosis: str | None = None
    description: str | None = None
    doctor_name: str | None = None
    record_date: date


class MedicalRecordUpdate(BaseModel):
    title: str | None = None
    diagnosis: str | None = None
    description: str | None = None
    notes: str | None = None
    doctor_name: str | None = None
    record_date: date | None = None


class DoctorCreate(BaseModel):
    specialization: str | None = None
    hospital: str | None = None
    license_number: str | None = None
    phone: str | None = None


class AccessPermissionCreate(BaseModel):
    doctor_id: int
    can_view_records: bool = True
    can_edit_records: bool = False
    can_view_medications: bool = False
    can_edit_medications: bool = False
    can_view_documents: bool = False
    can_edit_documents: bool = False
    expires_at: datetime | None = None


class AccessPermissionUpdate(BaseModel):
    can_view_records: bool | None = None
    can_edit_records: bool | None = None
    can_view_medications: bool | None = None
    can_edit_medications: bool | None = None
    can_view_documents: bool | None = None
    can_edit_documents: bool | None = None
    expires_at: datetime | None = None


# NEW: ACCESS REQUEST SCHEMAS
class AccessRequestCreate(BaseModel):
    patient_code: str
    message: str | None = None
    can_view_records: bool = True
    can_edit_records: bool = False
    can_view_medications: bool = False
    can_edit_medications: bool = False
    can_view_documents: bool = False
    can_edit_documents: bool = False


class AccessRequestRespond(BaseModel):
    action: str  # "approve" or "reject"
    can_view_records: bool | None = None
    can_edit_records: bool | None = None
    can_view_medications: bool | None = None
    can_edit_medications: bool | None = None
    can_view_documents: bool | None = None
    can_edit_documents: bool | None = None


class DocumentCreate(BaseModel):
    title: str
    document_type: str | None = None
    file_name: str
    file_path: str
    doctor_name: str | None = None
    document_date: date | None = None


class MedicationCreate(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    dose_times: list[str] = Field(default_factory=list)
    duration: str | None = None
    doctor_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class MedicationUpdate(BaseModel):
    name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    dose_times: list[str] | None = None
    duration: str | None = None
    doctor_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class MedicationDoseLogCreate(BaseModel):
    dose_date: date
    dose_time: str
    status: str


class PatientUpdate(BaseModel):
    name: str | None = None
    blood_group: str | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None