import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def parse_allowed_origins():
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:5500, http://localhost:8000",
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:5500", "http://localhost:8000"]


def require_database_settings():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"DATABASE_URL": database_url}

    required = {
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD"),
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_PORT": os.getenv("DB_PORT"),
        "DB_NAME": os.getenv("DB_NAME"),
    }

    if all(required.values()):
        return required

    return {}


def build_database_url():
    settings = require_database_settings()

    if "DATABASE_URL" in settings:
        database_url = settings["DATABASE_URL"]
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    if not settings:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "medilink.db"))
        return f"sqlite:///{db_path}"

    encoded_password = quote_plus(settings["DB_PASSWORD"])
    return (
        f"postgresql://{settings['DB_USER']}:{encoded_password}"
        f"@{settings['DB_HOST']}:{settings['DB_PORT']}/{settings['DB_NAME']}"
    )


DATABASE_URL = build_database_url()
engine_kwargs = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()