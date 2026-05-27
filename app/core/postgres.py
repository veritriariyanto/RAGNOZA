from urllib.parse import parse_qsl

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

def _build_database_url():
    raw_database_url = os.getenv("DATABASE_URL")

    if raw_database_url:
        try:
            return make_url(raw_database_url)
        except ValueError:
            normalized_url = _parse_loose_postgres_url(raw_database_url)
            if normalized_url is not None:
                return normalized_url

    pg_user = os.getenv("PGUSER", "postgres")
    pg_pass = os.getenv("PGPASSWORD", "postgres")
    pg_host = os.getenv("PGHOST", "localhost")
    pg_port = os.getenv("PGPORT", "5432")
    pg_db = os.getenv("PGDATABASE", "ragdb")
    pg_sslmode = os.getenv("PGSSLMODE")

    query = {"sslmode": pg_sslmode} if pg_sslmode else None

    return URL.create(
        drivername="postgresql",
        username=pg_user or None,
        password=pg_pass or None,
        host=pg_host or None,
        port=int(pg_port) if pg_port else None,
        database=pg_db or None,
        query=query,
    )


def _parse_loose_postgres_url(raw_url):
    if "://" not in raw_url or "/" not in raw_url:
        return None

    scheme, remainder = raw_url.split("://", 1)
    if "/" not in remainder or "@" not in remainder:
        return None

    authority, database_part = remainder.rsplit("/", 1)
    query = None
    if "?" in database_part:
        database_part, query_string = database_part.split("?", 1)
        query = dict(parse_qsl(query_string, keep_blank_values=True)) or None

    userinfo, hostport = authority.rsplit("@", 1)
    if ":" in userinfo:
        username, password = userinfo.split(":", 1)
    else:
        username, password = userinfo, None

    if ":" in hostport:
        host, port_text = hostport.rsplit(":", 1)
    else:
        host, port_text = hostport, None

    try:
        port = int(port_text) if port_text else None
    except ValueError:
        return None

    return URL.create(
        drivername=scheme,
        username=username or None,
        password=password or None,
        host=host or None,
        port=port,
        database=database_part or None,
        query=query,
    )


DATABASE_URL = _build_database_url()

# Tambahkan argumen pool_pre_ping agar koneksi ke Cloud (Supabase) tidak gampang timeout
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

Base = declarative_base()

# Dependency untuk FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()