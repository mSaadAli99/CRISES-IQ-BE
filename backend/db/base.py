import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

_raw_url = os.environ.get("NEON_DATABASE_URL", "")

if not _raw_url:
    raise RuntimeError("NEON_DATABASE_URL environment variable is not set")


def _to_async_db_url(url: str) -> str:
    """Convert any postgres URL to SQLAlchemy async asyncpg format and clean unsupported query params."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        
    parsed = urlparse(url)
    if parsed.query:
        from urllib.parse import parse_qsl, urlencode
        query_params = dict(parse_qsl(parsed.query))
        cleaned_params = {}
        for k, v in query_params.items():
            if k == "sslmode":
                cleaned_params["ssl"] = "require"
            elif k == "channel_binding":
                continue
            else:
                cleaned_params[k] = v
        new_query = urlencode(cleaned_params)
        parsed = parsed._replace(query=new_query)
        url = urlunparse(parsed)
    return url


def _to_sync_url(url: str) -> str:
    """Convert any postgres URL to a sync URL for Alembic (psycopg3)."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _to_async_db_url(_raw_url)
SYNC_DATABASE_URL = _to_sync_url(_raw_url)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
