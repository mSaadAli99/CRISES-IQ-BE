import os
from dotenv import load_dotenv
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

_raw_url = os.environ.get("NEON_DATABASE_URL", "")

if not _raw_url:
    raise RuntimeError("NEON_DATABASE_URL environment variable is not set")


def _to_asyncpg_url(url: str) -> tuple[str, dict]:
    """Convert any postgres URL to asyncpg format and extract SSL flag."""
    # Normalise scheme
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # If already has +asyncpg, keep as-is

    # Strip sslmode from the query string; asyncpg uses connect_args instead
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sslmode = params.pop("sslmode", [None])[0]
    params.pop("channel_binding", None)  # asyncpg doesn't support this param

    new_query = urlencode({k: v[0] for k, v in params.items()})
    cleaned_url = urlunparse(parsed._replace(query=new_query))

    connect_args = {}
    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require"

    return cleaned_url, connect_args


def _to_sync_url(url: str) -> str:
    """Convert any postgres URL to a psycopg2-compatible sync URL (keeps sslmode)."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


DATABASE_URL, _connect_args = _to_asyncpg_url(_raw_url)
SYNC_DATABASE_URL = _to_sync_url(_raw_url)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
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
