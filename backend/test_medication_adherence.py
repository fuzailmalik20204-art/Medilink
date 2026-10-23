import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import AccessPermission, Doctor, Medication, Patient, User
from routes.doctors import get_patient_medications
from routes.medications import create_medication, get_medication_adherence, log_medication_dose, update_medication
from schemas import MedicationDoseLogCreate, MedicationUpdate


class MedicationAdherenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.session_factory()

        self.patient_user = User(
            name="Test Patient",
            email="patient@example.test",
            password="unused",
            role="patient",
        )
        self.doctor_user = User(
            name="Test Doctor",
            email="doctor@example.test",
            password="unused",
            role="doctor",
        )
        self.other_user = User(
            name="Other Patient",
            email="other@example.test",
            password="unused",
            role="patient",
        )
        self.db.add_all([self.patient_user, self.doctor_user, self.other_user])
        self.db.flush()

        self.patient = Patient(user_id=self.patient_user.id, patient_id="PAT-TEST")
        self.doctor = Doctor(user_id=self.doctor_user.id, doctor_id="DOC-TEST")
        self.db.add_all([self.patient, self.doctor])
        self.db.flush()

        self.medication = Medication(
            patient_id=self.patient.id,
            name="Test medication",
            dose_times=["00:00", "23:59"],
            start_date=date.today(),
        )
        self.db.add(self.medication)
        self.db.add(AccessPermission(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            can_view_medications=True,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_patient_can_update_dose_and_doctor_can_view_summary(self):
        response = get_medication_adherence(self.patient_user, self.db)
        self.assertEqual(len(response["today"]), 2)

        log_medication_dose(
            self.medication.id,
            MedicationDoseLogCreate(dose_date=date.today(), dose_time="00:00", status="taken"),
            self.patient_user,
            self.db,
        )
        response = get_medication_adherence(self.patient_user, self.db)
        self.assertEqual(response["total_taken"], 1)

        doctor_response = get_patient_medications(self.patient.id, self.doctor, self.db)
        adherence = doctor_response["medications"][0]["adherence_7d"]
        self.assertEqual(adherence["taken"], 1)
        self.assertGreaterEqual(adherence["due"], 1)

    def test_patient_cannot_log_another_patients_dose(self):
        other_patient = Patient(user_id=self.other_user.id, patient_id="PAT-OTHER")
        self.db.add(other_patient)
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            log_medication_dose(
                self.medication.id,
                MedicationDoseLogCreate(dose_date=date.today(), dose_time="00:00", status="taken"),
                self.other_user,
                self.db,
            )
        self.assertEqual(error.exception.status_code, 404)

    def test_only_scheduled_times_can_be_logged(self):
        with self.assertRaises(HTTPException) as error:
            log_medication_dose(
                self.medication.id,
                MedicationDoseLogCreate(dose_date=date.today(), dose_time="12:34", status="taken"),
                self.patient_user,
                self.db,
            )
        self.assertEqual(error.exception.status_code, 400)

    def test_medication_schedule_can_be_created_and_updated(self):
        created = create_medication(
            name="Scheduled medication",
            dosage=None,
            frequency=None,
            dose_times='["08:00", "20:00", "08:00"]',
            duration=None,
            doctor_name=None,
            start_date=None,
            end_date=None,
            notes=None,
            current_user=self.patient_user,
            db=self.db,
        )
        created_medication = created["medication"]
        self.assertEqual(created_medication["dose_times"], ["08:00", "20:00"])

        update_medication(
            created_medication["id"],
            MedicationUpdate(dose_times=["09:00"]),
            self.patient_user,
            self.db,
        )
        updated = get_medication_adherence(self.patient_user, self.db)
        self.assertIn("09:00", [dose["dose_time"] for dose in updated["today"]])


if __name__ == "__main__":
    unittest.main()