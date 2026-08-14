import os
from typing import Generator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Load environment variables from the .env file (useful for local development)
load_dotenv(override=True)

# PostgreSQL database configuration
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "mydatabase")

# URL-encode credentials to support special characters in username/password
DB_USER_QUOTED = quote_plus(DB_USER)
DB_PASSWORD_QUOTED = quote_plus(DB_PASSWORD)

# SQLAlchemy connection URL for PostgreSQL
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER_QUOTED}:{DB_PASSWORD_QUOTED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Create the SQLAlchemy engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Configure the session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a database session and ensures proper cleanup."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
