#!/usr/bin/env python3
"""
Smoke test: verify SessionStoreUnavailableError is raised when Redis is unreachable.

Usage:
    PYTHONPATH=. uv run python -m backend.tests.smoke_session_store
"""

import asyncio
import sys


async def main() -> None:
    # Ensure Redis is NOT running for this test
    print("Checking that SessionStoreUnavailableError is raised without Redis...")

    from backend.session.redis_manager import RedisSessionManager

    mgr = RedisSessionManager()

    # 1. check_available should return False
    available = await mgr.check_available()
    print(f"  check_available() → {available}")
    assert available is False, "Expected False when Redis is down"

    # 2. create_session should raise
    try:
        await mgr.create_session()
        print("  FAIL: create_session() did not raise")
        sys.exit(1)
    except Exception as e:
        from backend.session.exceptions import SessionStoreUnavailableError

        err_msg = f"Expected SessionStoreUnavailableError, got {type(e).__name__}"
        assert isinstance(e, SessionStoreUnavailableError), err_msg
        print("  create_session() → SessionStoreUnavailableError ✓")

    # 3. get_session should raise
    try:
        await mgr.get_session("nonexistent")
        print("  FAIL: get_session() did not raise")
        sys.exit(1)
    except SessionStoreUnavailableError:
        print("  get_session() → SessionStoreUnavailableError ✓")

    # 4. update_session should raise
    from backend.session.models import SessionData

    try:
        await mgr.update_session(SessionData(session_id="test"))
        print("  FAIL: update_session() did not raise")
        sys.exit(1)
    except SessionStoreUnavailableError:
        print("  update_session() → SessionStoreUnavailableError ✓")

    # 5. dev_mode fallback should succeed
    import os

    os.environ["DEV_MODE"] = "true"
    # Reimport settings with env override
    from backend.config import settings

    # Force dev_mode by patching
    settings.dev_mode = True

    from backend.session.manager import _get_session_store

    store = await _get_session_store()
    from backend.session.memory_manager import MemorySessionManager

    assert isinstance(store, MemorySessionManager), (
        f"Expected MemorySessionManager, got {type(store).__name__}"
    )
    print("  dev_mode fallback → MemorySessionManager ✓")

    sid = await store.create_session()
    s = await store.get_session(sid)
    assert s is not None, "Expected session to exist"
    print(f"  memory store create+get → {sid} ✓")

    s.call_complete = True
    await store.update_session(s)
    s2 = await store.get_session(sid)
    assert s2 is not None and s2.call_complete is True, "Expected updated session"
    print("  memory store update → call_complete=True ✓")

    await store.delete_session(sid)
    s3 = await store.get_session(sid)
    assert s3 is None, "Expected deleted session"
    print("  memory store delete → None ✓")

    print("\nAll smoke tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
