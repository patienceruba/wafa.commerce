import logging
import os
import dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

dotenv.load_dotenv(override=True)

logger = logging.getLogger(__name__)

db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASS", "")
db_host = os.getenv("DB_HOST", "localhost")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "ecommerce_db")


# Connect to PostgreSQL if DB_USER, DB_HOST, and DB_NAME are defined
is_postgres = bool(db_user and db_host and db_name)
if is_postgres:
    auth_str = f"{db_user}:{db_pass}" if db_pass else db_user
    db_url = f"postgresql://{auth_str}@{db_host}:{db_port}/{db_name}"
    connect_args = {}
else:
    db_url = "sqlite:///./ecommerce.db"
    connect_args = {"check_same_thread": False}
    logger.info("PostgreSQL configuration not complete. Using SQLite fallback: ecommerce.db")

try:
    engine = create_engine(db_url, echo=False, connect_args=connect_args)
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
