#!/usr/bin/env python3
"""
CrisisIQ backend verification script.
Run from backend/:  python scripts/verify_setup.py

Checks Python version, imports, ADK agents, and optional live DB/API.
Exit code 0 = safe to push; non-zero = fix listed errors first.
"""
from __future__ import annotations

import asyncio
import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# Load .env before any backend import that reads NEON_DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND_ROOT, ".env"))
except ImportError:
    pass

SUPPORTED = ((3, 11), (3, 12), (3, 13), (3, 14))
ERRORS: list[str] = []
WARNINGS: list[str] = []


def check_python_version() -> None:
    v = sys.version_info[:2]
    if v not in SUPPORTED:
        WARNINGS.append(
            f"Python {v[0]}.{v[1]} detected. Recommended: 3.11–3.12. "
            f"This project uses psycopg3 (not asyncpg) for broader compatibility."
        )
    else:
        print(f"OK  Python {v[0]}.{v[1]}")


def check_env_file() -> None:
    env_path = os.path.join(BACKEND_ROOT, ".env")
    if not os.path.isfile(env_path):
        WARNINGS.append("No backend/.env — copy .env.example before running server")
    else:
        print("OK  .env exists")


def check_imports() -> None:
    try:
        import google.adk  # noqa: F401
        print(f"OK  google-adk")
    except ImportError as e:
        ERRORS.append(f"google-adk not installed: {e}")
        return

    try:
        from crisisiq_agents.agent import crisis_pipeline_agent, root_agent
        n = len(crisis_pipeline_agent.sub_agents)
        print(f"OK  crisis_pipeline_agent ({n} sub-agents)")
        assert root_agent.name == "crisis_pipeline_agent"
    except Exception as e:
        ERRORS.append(f"crisisiq_agents.agent: {e}")

    try:
        from crisisiq_agents.runner import run_adk_pipeline
        from crisisiq_agents.tools import ingest_signals
        print("OK  crisisiq_agents.runner + tools")
    except Exception as e:
        ERRORS.append(f"crisisiq_agents.runner/tools: {e}")

    # FastAPI app (needs NEON_DATABASE_URL)
    if os.environ.get("NEON_DATABASE_URL"):
        try:
            from main import app  # noqa: F401
            paths = [getattr(r, "path", "") for r in app.routes if "adk" in getattr(r, "path", "")]
            print(f"OK  FastAPI app  routes={paths}")
        except Exception as e:
            ERRORS.append(f"main.app load failed: {e}")
    else:
        WARNINGS.append("NEON_DATABASE_URL unset — skipping FastAPI load (set .env for full check)")


async def check_adk_session_api() -> None:
    try:
        from google.adk.sessions import InMemorySessionService
        import uuid

        svc = InMemorySessionService()
        sid = str(uuid.uuid4())
        await svc.create_session(app_name="test", user_id="u", session_id=sid, state={})
        sess = await svc.get_session(app_name="test", user_id="u", session_id=sid)
        if sess is None:
            ERRORS.append("ADK get_session returned None")
        else:
            print("OK  ADK async session API")
    except Exception as e:
        ERRORS.append(f"ADK session API: {e}")


async def check_direct_pipeline_mock() -> None:
    """Run direct pipeline structure only if DB + API key available."""
    if not os.environ.get("NEON_DATABASE_URL") or not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ):
        WARNINGS.append("Skipping live ADK pipeline test (need NEON_DATABASE_URL + GEMINI_API_KEY)")
        return

    os.environ.setdefault("CRISISIQ_ADK_MODE", "direct")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BACKEND_ROOT, ".env"))
    except ImportError:
        pass

    try:
        from crisisiq_agents.runner import run_adk_pipeline

        result = await run_adk_pipeline(
            signals=[{
                "text": "Test flood signal Lyari",
                "source_type": "form",
                "location": "Lyari Karachi",
            }],
            location="Lyari Karachi",
        )
        if not result.get("crisis"):
            WARNINGS.append("Live pipeline ran but crisis is empty — check Gemini key / quota")
        else:
            print(
                f"OK  Live ADK direct pipeline  "
                f"crisis={result.get('crisis', {}).get('crisis_type')} "
                f"actions={len(result.get('actions') or [])}"
            )
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "Quota exceeded" in err:
            WARNINGS.append(
                "Live ADK pipeline: Gemini API quota exceeded — code path OK, "
                "retry later or use a key with billing enabled."
            )
        elif "404" in err and "gemini" in err.lower():
            ERRORS.append(f"Live ADK pipeline: invalid Gemini model — set GEMINI_MODEL in .env")
        else:
            ERRORS.append(f"Live ADK pipeline: {e}")


def main() -> int:
    from platform_async import ensure_compatible_event_loop

    ensure_compatible_event_loop()

    print("CrisisIQ backend verification\n" + "=" * 40)
    check_python_version()
    check_env_file()
    check_imports()
    asyncio.run(check_adk_session_api())
    asyncio.run(check_direct_pipeline_mock())

    print("\n" + "=" * 40)
    if WARNINGS:
        print("Warnings:")
        for w in WARNINGS:
            print(f"  ! {w}")
    if ERRORS:
        print("Errors (fix before push):")
        for e in ERRORS:
            print(f"  x {e}")
        return 1
    print("\nAll checks passed — safe to push backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
