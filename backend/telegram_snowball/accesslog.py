from __future__ import annotations

import logging

_HEALTH_ACCESS = (
    '"GET /health HTTP/',
    '"GET /api/health HTTP/',
    '"GET /healthz HTTP/',
    '"HEAD /health HTTP/',
    '"HEAD /api/health HTTP/',
    '"HEAD /healthz HTTP/',
)


class HealthAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(marker in message for marker in _HEALTH_ACCESS)


def quiet_health_access_logs() -> None:
    log = logging.getLogger("uvicorn.access")
    if any(isinstance(item, HealthAccessFilter) for item in log.filters):
        return
    log.addFilter(HealthAccessFilter())
