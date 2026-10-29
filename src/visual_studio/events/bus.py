"""In-process event bus with optional best-effort webhook delivery.

The bus is the single place where domain events are emitted. It:
  * persists every event to the SQLite ``events`` table (so SSE / replays can
    read them back), and
  * if ``VISUAL_WEBHOOK_URL`` is configured, POSTs the event JSON to that URL.

Emitted event types: ``task.created``, ``task.generating``, ``task.succeeded``,
``task.failed``. The SSE endpoint (``GET /v1/events/stream``) reads persisted
events filtered by ``case_id``, so this module stays transport-agnostic.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable, Optional

from visual_studio.logging_config import get_logger

logger = get_logger()

# Payload is a JSON-serialisable dict emitted by the service.
EventCallback = Callable[[str, dict[str, Any]], None]


class EventBus:
    """Pub/sub bus that persists events and optionally forwards them via HTTP."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        store: Any = None,
        http_client: Any = None,
    ) -> None:
        self.webhook_url = webhook_url
        self._store = store
        self._http = http_client  # injectable; defaults to httpx
        self._subscribers: list[EventCallback] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: EventCallback) -> None:
        """Register an in-process subscriber (used by tests / side effects)."""
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit an event: persist, notify subscribers, and webhook (best effort)."""
        case_id = payload.get("case_id")
        payload_json = json.dumps(payload, ensure_ascii=False)

        if self._store is not None:
            try:
                self._store.append_event(event_type, case_id, payload_json)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("event persist failed: %s", exc)

        with self._lock:
            subscribers = list(self._subscribers)
        for cb in subscribers:
            try:
                cb(event_type, payload)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("subscriber error: %s", exc)

        if self.webhook_url:
            self._post_webhook(event_type, payload_json)

    def _post_webhook(self, event_type: str, payload_json: str) -> None:
        try:
            import httpx

            client = self._http or httpx
            client.post(
                self.webhook_url,
                content=payload_json,
                headers={"Content-Type": "application/json"},
                timeout=2.0,
            )
        except Exception as exc:  # pragma: no cover - network optional
            logger.warning("webhook POST failed for %s: %s", event_type, exc)
