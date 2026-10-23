import unittest
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import MedicalRecord, Medication, Patient, User
from routes.visit_brief import get_visit_brief


class VisitBriefTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)()
        self.patient_user = User(
            name="Test Patient",
            email="patient@example.test",
            password="not-a-real-password-hash",
            role="patient",
        )
        self.other_user = User(
            name="Test Doctor",
            email="doctor@example.test",
            password="not-a-real-password-hash",
            role="doctor",
        )
        self.db.add_all([self.patient_user, self.other_user])
        self.db.flush()
        self.patient = Patient(user_id=self.patient_user.id, patient_id="PAT-TEST")
        self.db.add(self.patient)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_brief_contains_only_patient_records_and_current_dated_medications(self):
        today = date.today()
        another_patient_user = User(
            name="Another Patient",
            email="another-patient@example.test",
            password="not-a-real-password-hash",
            role="patient",
        )
        self.db.add(another_patient_user)
        self.db.flush()
        another_patient = Patient(
            user_id=another_patient_user.id,
            patient_id="PAT-OTHER",
        )
        self.db.add(another_patient)
        self.db.flush()
        self.db.add_all(
            [
                MedicalRecord(
                    patient_id=self.patient.id,
                    title="Annual visit",
                    diagnosis="Example condition",
                    description="Patient-provided record note",
                    doctor_name="Dr. Example",
                    record_date=today,
                ),
                MedicalRecord(
                    patient_id=another_patient.id,
                    title="Private record belonging to another patient",
                    record_date=today,
                ),
                Medication(
                    patient_id=self.patient.id,
                    name="Current medicine",
                    dosage="1 tablet",
                    frequency="Daily",
                    start_date=today - timedelta(days=2),
                    end_date=today + timedelta(days=5),
                ),
                Medication(
                    patient_id=self.patient.id,
                    name="Past medicine",
                    end_date=today - timedelta(days=1),
                ),
            ]
        )
        self.db.commit()

        brief = get_visit_brief(self.patient_user, self.db)

        self.assertEqual(brief["record_count"], 1)
        self.assertEqual(brief["records"][0]["source"], "Medical record #1")
        self.assertEqual(brief["records"][0]["diagnosis"], "Example condition")
        self.assertEqual(brief["active_medication_count"], 1)
        self.assertEqual(brief["medications"][0]["name"], "Current medicine")
        self.assertIn("not an AI-generated medical assessment", brief["notice"])
        self.assertTrue(brief["discussion_questions"])

    def test_non_patient_cannot_generate_visit_brief(self):
        with self.assertRaises(HTTPException) as error:
            get_visit_brief(self.other_user, self.db)

        self.assertEqual(error.exception.status_code, 403)

    def test_missing_patient_profile_returns_not_found(self):
        unprofiled_patient = User(
            name="New Patient",
            email="new-patient@example.test",
            password="not-a-real-password-hash",
            role="patient",
        )
        self.db.add(unprofiled_patient)
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            get_visit_brief(unprofiled_patient, self.db)

        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
