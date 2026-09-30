from __future__ import annotations

import logging

from telegram_snowball.accesslog import HealthAccessFilter


def test_health_access_filter_drops_probes() -> None:
    filt = HealthAccessFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='127.0.0.1:80 - "GET /api/health HTTP/1.1" 200 OK',
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is False
    record.msg = '127.0.0.1:80 - "GET /health HTTP/1.1" 200 OK'
    assert filt.filter(record) is False
    record.msg = '172.22.0.6:53350 - "GET /api/status HTTP/1.1" 200 OK'
    assert filt.filter(record) is True
