"""
Optional LangSmith tracing for VoiceIntake.

Tracing only activates when ``LANGCHAIN_API_KEY`` is set in the environment.
All other LangSmith env vars (``LANGCHAIN_PROJECT``, ``LANGCHAIN_TRACING_V2``)
are respected by the SDK automatically.

Usage::

    from backend.tracing.langsmith import is_enabled, Trace

    if is_enabled():
        t = Trace("turn_greeting", "chain", inputs={...})
        child = t.child("extraction", "tool", inputs={...}, outputs={...})
        t.finish(outputs={...})
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client: Any = None
_DISABLED = object()


def _lazy_client():
    global _client
    if _client is not None:
        return _client if _client is not _DISABLED else None
    api_key = os.environ.get("LANGCHAIN_API_KEY", "").strip()
    if not api_key:
        _client = _DISABLED
        return None
    try:
        from langsmith import Client as LangSmithClient

        _client = LangSmithClient()
        project = os.environ.get("LANGCHAIN_PROJECT", "")
        if project:
            logger.info("LangSmith tracing enabled (project=%s)", project)
        else:
            logger.info("LangSmith tracing enabled")
    except Exception as exc:
        logger.debug("LangSmith init skipped: %s", exc)
        _client = _DISABLED
        return None
    return _client


def is_enabled() -> bool:
    return _lazy_client() is not None


class Trace:
    """A single trace tree rooted at one FSM turn or operation.

    Safe to use even when LangSmith is disabled — all methods become no-ops.
    """

    def __init__(self, name: str, run_type: str, inputs: dict) -> None:
        self._client = _lazy_client()
        self._root: Any = None
        if self._client is None:
            return
        from langsmith.run_trees import RunTree

        self._root = RunTree(name=name, run_type=run_type, inputs=inputs)

    def child(
        self,
        name: str,
        run_type: str,
        inputs: dict,
        outputs: Optional[dict] = None,
    ) -> Optional[Any]:
        """Create a child run. Returns the child or None when disabled."""
        if self._root is None:
            return None
        child = self._root.create_child(name=name, run_type=run_type, inputs=inputs)
        if outputs is not None:
            child.end(outputs=outputs)
        return child

    def finish(self, outputs: Optional[dict] = None, error: Optional[str] = None) -> None:
        """End the root run and post the entire tree."""
        if self._root is None or self._client is None:
            return
        if error:
            self._root.end(error=error)
        else:
            self._root.end(outputs=outputs)
        self._client.post_run_tree(self._root)
