"""Property-based tests for HTTP error log correctness in BoschEBikeApiClient.

Property 9: HTTP error responses produce the correct log level and content.

For any HTTP 4xx status code (excluding 401) returned by the Bosch API, the
integration SHALL emit exactly one log record at the ERROR level containing
both the status code and the endpoint URL. For any HTTP 5xx status code, the
integration SHALL emit exactly one log record at the WARNING level containing
both the status code and the endpoint URL.

**Validates: Requirements 12.1, 12.3**
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.bosch_ebike_ha.api import (
    ApiClientError,
    ApiServerError,
    BoschEBikeApiClient,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 4xx codes: 402–499 (401 is excluded — it triggers the token-refresh path,
# not the error-log path).
client_error_codes = st.integers(min_value=402, max_value=499)

# 5xx codes: 500–599
server_error_codes = st.integers(min_value=500, max_value=599)


# ---------------------------------------------------------------------------
# Log capture context manager (reused from credential safety tests)
# ---------------------------------------------------------------------------


class _ListHandler(logging.Handler):
    """A logging handler that collects records into a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def capture_logs(logger_name: str = "custom_components.bosch_ebike_ha.api"):
    """Context manager that captures all log records for *logger_name*.

    Yields the list of captured ``LogRecord`` objects. The list is populated
    as records are emitted, so it can be inspected after the ``with`` block.
    """
    handler = _ListHandler()
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger(logger_name)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_oauth_session(token: str = "test-token") -> MagicMock:
    """Return a mock OAuth2Session."""
    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock()
    session.token = {"access_token": token}
    return session


def make_response(status: int) -> AsyncMock:
    """Return a mock aiohttp response with the given status code."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value={})
    return resp


def make_client_session(response: AsyncMock) -> MagicMock:
    """Return a mock aiohttp.ClientSession whose request() returns *response*."""
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    return session


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Property 9 — 4xx errors produce exactly one ERROR log with status + URL
# ---------------------------------------------------------------------------


@given(status=client_error_codes)
@settings(max_examples=100)
def test_4xx_produces_exactly_one_error_log(status):
    """**Validates: Requirements 12.1, 12.3**

    For any HTTP 4xx status code (402–499), the API client SHALL emit exactly
    one log record at the ERROR level. That record SHALL contain both the
    numeric status code and the endpoint URL in its formatted message.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session()
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiClientError:
            pass

    # Collect records that contain the status code in their message.
    status_str = str(status)
    error_records_with_status = [
        r for r in records
        if r.levelno == logging.ERROR and status_str in r.getMessage()
    ]

    # Assert exactly one ERROR log contains the status code.
    assert len(error_records_with_status) == 1, (
        f"Expected exactly 1 ERROR log containing status {status}, "
        f"got {len(error_records_with_status)}. "
        f"All records: {[(r.levelname, r.getMessage()) for r in records]}"
    )

    # Assert the ERROR log also contains the endpoint URL.
    error_msg = error_records_with_status[0].getMessage()
    assert "/v1/bikes" in error_msg, (
        f"ERROR log for status {status} does not contain the endpoint URL. "
        f"Message: {error_msg!r}"
    )


@given(status=client_error_codes)
@settings(max_examples=100)
def test_4xx_does_not_produce_warning_log_with_status(status):
    """**Validates: Requirements 12.1, 12.3**

    For any HTTP 4xx status code (402–499), the API client SHALL NOT emit a
    WARNING log record containing the status code. The wrong log level must
    not be used for client errors.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session()
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiClientError:
            pass

    status_str = str(status)
    warning_records_with_status = [
        r for r in records
        if r.levelno == logging.WARNING and status_str in r.getMessage()
    ]

    assert len(warning_records_with_status) == 0, (
        f"Expected no WARNING log containing status {status} for a 4xx error, "
        f"but found {len(warning_records_with_status)}. "
        f"Records: {[(r.levelname, r.getMessage()) for r in warning_records_with_status]}"
    )


# ---------------------------------------------------------------------------
# Property 9 — 5xx errors produce exactly one WARNING log with status + URL
# ---------------------------------------------------------------------------


@given(status=server_error_codes)
@settings(max_examples=100)
def test_5xx_produces_exactly_one_warning_log(status):
    """**Validates: Requirements 12.1, 12.3**

    For any HTTP 5xx status code (500–599), the API client SHALL emit exactly
    one log record at the WARNING level. That record SHALL contain both the
    numeric status code and the endpoint URL in its formatted message.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session()
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiServerError:
            pass

    status_str = str(status)
    warning_records_with_status = [
        r for r in records
        if r.levelno == logging.WARNING and status_str in r.getMessage()
    ]

    # Assert exactly one WARNING log contains the status code.
    assert len(warning_records_with_status) == 1, (
        f"Expected exactly 1 WARNING log containing status {status}, "
        f"got {len(warning_records_with_status)}. "
        f"All records: {[(r.levelname, r.getMessage()) for r in records]}"
    )

    # Assert the WARNING log also contains the endpoint URL.
    warning_msg = warning_records_with_status[0].getMessage()
    assert "/v1/bikes" in warning_msg, (
        f"WARNING log for status {status} does not contain the endpoint URL. "
        f"Message: {warning_msg!r}"
    )


@given(status=server_error_codes)
@settings(max_examples=100)
def test_5xx_does_not_produce_error_log_with_status(status):
    """**Validates: Requirements 12.1, 12.3**

    For any HTTP 5xx status code (500–599), the API client SHALL NOT emit an
    ERROR log record containing the status code. The wrong log level must not
    be used for server errors.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session()
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiServerError:
            pass

    status_str = str(status)
    error_records_with_status = [
        r for r in records
        if r.levelno == logging.ERROR and status_str in r.getMessage()
    ]

    assert len(error_records_with_status) == 0, (
        f"Expected no ERROR log containing status {status} for a 5xx error, "
        f"but found {len(error_records_with_status)}. "
        f"Records: {[(r.levelname, r.getMessage()) for r in error_records_with_status]}"
    )
