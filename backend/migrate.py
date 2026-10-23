from database import engine
from sqlalchemy import text


def create_requests_table():
    sql = """
    CREATE TABLE IF NOT EXISTS access_requests (
        id SERIAL PRIMARY KEY,
        patient_id INTEGER NOT NULL REFERENCES patients(id),
        doctor_id INTEGER NOT NULL REFERENCES doctors(id),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        message VARCHAR(255),
        can_view_records BOOLEAN NOT NULL DEFAULT TRUE,
        can_edit_records BOOLEAN NOT NULL DEFAULT FALSE,
        can_view_medications BOOLEAN NOT NULL DEFAULT FALSE,
        can_edit_medications BOOLEAN NOT NULL DEFAULT FALSE,
        can_view_documents BOOLEAN NOT NULL DEFAULT FALSE,
        can_edit_documents BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE
    );
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
        print("Table 'access_requests' created in PostgreSQL successfully!")
    except Exception as e:
        print(f"Migration error: {e}")


if __name__ == "__main__":
    create_requests_table()