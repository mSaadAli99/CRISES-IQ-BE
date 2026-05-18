"""Windows-compatible asyncio policy for psycopg async SQLAlchemy."""
import asyncio
import sys


def ensure_compatible_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
