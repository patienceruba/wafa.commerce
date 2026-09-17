import logging
import os
import urllib.parse
import dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

dotenv.load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Check for full DATABASE_URL or discrete environment variables
raw_db_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or ""

if raw_db_url:
    # SQLAlchemy requires postgresql:// instead of postgres://
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    db_url = raw_db_url
    is_postgres = True
    connect_args = {}
else:
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")

    is_postgres = bool(db_user and db_host and db_name)
    if is_postgres:
        encoded_user = urllib.parse.quote_plus(db_user)
        encoded_pass = urllib.parse.quote_plus(db_pass) if db_pass else ""
        auth_str = f"{encoded_user}:{encoded_pass}" if encoded_pass else encoded_user
        
        # Add sslmode=require for remote/cloud hosts like Supabase
        ssl_suffix = "?sslmode=require" if "supabase" in db_host or "pooler" in db_host or db_host != "localhost" else ""
        db_url = f"postgresql://{auth_str}@{db_host}:{db_port}/{db_name}{ssl_suffix}"
        connect_args = {}
    else:
        db_url = "sqlite:///./ecommerce.db"
        connect_args = {"check_same_thread": False}
        logger.info("PostgreSQL configuration not complete. Using SQLite fallback: ecommerce.db")

engine_kwargs = {"echo": False, "connect_args": connect_args}
if is_postgres:
    # Prevent stale connection drops on cloud database providers like Supabase
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": 300,
    })

try:
    engine = create_engine(db_url, **engine_kwargs)
    Sessionlocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
except Exception as e:
    logger.error(f"Failed to connect to the database: {e}")
    raise

def get_db():
    db = Sessionlocal()
    try:
        yield db
    finally:
        db.close()

