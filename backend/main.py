from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, parse_allowed_origins
import models

from routes.auth import router as auth_router
from routes.patients import router as patient_router
from routes.records import router as records_router
from routes.doctors import router as doctor_router
from routes.permissions import router as permission_router
from routes.access_logs import router as access_logs_router
from routes.documents import router as documents_router
from routes.medications import router as medications_router

# =========================================================
# CREATE FASTAPI APP
# =========================================================

app = FastAPI(
    title="MediLink API",
    description="Backend API for MediLink Healthcare Platform",
    version="1.0.0",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_origin_regex=(
        r"^https?://(?:localhost|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
        r"(?::(?:3000|5500))?$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# =========================================================
# REGISTER ROUTES
# =========================================================

app.include_router(auth_router)
app.include_router(patient_router)
app.include_router(records_router)
app.include_router(doctor_router)
app.include_router(permission_router)
app.include_router(access_logs_router)
app.include_router(documents_router)
app.include_router(medications_router)


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "message": "Welcome to MediLink API",
        "status": "Backend is running",
    }


# =========================================================
# TEST API
# =========================================================

@app.get("/api/test")
def test_api():
    return {"message": "MediLink API is working successfully"}