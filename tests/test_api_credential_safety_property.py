"""Property-based tests for credential safety in BoschEBikeApiClient.

Property 6: Credentials are never present in log output.

For any access token string, and for any sequence of API calls (including
token refresh sequences), none of those credential strings SHALL appear in
any log record at any log level.

**Validates: Requirements 12.5**
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
    ApiAuthError,
    ApiClientError,
    ApiServerError,
    ApiTimeoutError,
    BoschEBikeApiClient,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate arbitrary token strings — alphanumeric plus common JWT characters.
# Minimum length 8 so the assertion is meaningful (an empty token would
# trivially never appear in logs).
token_strings = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-._~+/=",
    ),
    min_size=8,
    max_size=128,
)


# ---------------------------------------------------------------------------
# Log capture context manager
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


def make_oauth_session(token: str) -> MagicMock:
    """Return a mock OAuth2Session with the given access token."""
    session = MagicMock()
    session.async_ensure_token_valid = AsyncMock()
    session.token = {"access_token": token}
    return session


def make_response(status: int, json_data: object = None) -> AsyncMock:
    """Return a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    return resp


def make_client_session(response: AsyncMock) -> MagicMock:
    """Return a mock aiohttp.ClientSession whose request() returns *response*."""
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    return session


def assert_token_not_in_logs(token: str, records: list[logging.LogRecord]) -> None:
    """Assert the token string does not appear in any log record message."""
    for record in records:
        msg = record.getMessage()
        assert token not in msg, (
            f"Token found in log record at level {record.levelname}: {msg!r}"
        )


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Property 6 — success path
# ---------------------------------------------------------------------------


@given(token=token_strings)
@settings(max_examples=100)
def test_token_not_in_logs_success_path(token):
    """**Validates: Requirements 12.5**

    For any arbitrary token string, a successful API call (HTTP 200) must not
    include the token in any log record at any level.
    """
    resp = make_response(200, [])
    http = make_client_session(resp)
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        run(client.fetch_bikes())

    assert_token_not_in_logs(token, records)


# ---------------------------------------------------------------------------
# Property 6 — 401 force-refresh → second 401 (ApiAuthError) path
# ---------------------------------------------------------------------------


@given(token=token_strings)
@settings(max_examples=100)
def test_token_not_in_logs_401_retry_path(token):
    """**Validates: Requirements 12.5**

    For any arbitrary token string, a 401 → force-refresh → second 401 sequence
    (which raises ApiAuthError) must not include the token in any log record.
    """
    resp_401 = make_response(401)
    http = MagicMock()
    http.request = AsyncMock(return_value=resp_401)
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiAuthError:
            pass

    assert_token_not_in_logs(token, records)


# ---------------------------------------------------------------------------
# Property 6 — 401 force-refresh → success path
# ---------------------------------------------------------------------------


@given(token=token_strings)
@settings(max_examples=100)
def test_token_not_in_logs_401_then_success_path(token):
    """**Validates: Requirements 12.5**

    For any arbitrary token string, a 401 → force-refresh → 200 sequence
    (successful retry after token refresh) must not include the token in any
    log record.
    """
    first_resp = make_response(401)
    second_resp = make_response(200, [])
    http = MagicMock()
    http.request = AsyncMock(side_effect=[first_resp, second_resp])
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        run(client.fetch_bikes())

    assert_token_not_in_logs(token, records)


# ---------------------------------------------------------------------------
# Property 6 — 4xx error path
# ---------------------------------------------------------------------------


@given(
    token=token_strings,
    status=st.integers(min_value=400, max_value=499).filter(lambda s: s != 401),
)
@settings(max_examples=100)
def test_token_not_in_logs_4xx_error_path(token, status):
    """**Validates: Requirements 12.5**

    For any arbitrary token string and any 4xx status code (excluding 401),
    the resulting ApiClientError path must not include the token in any log
    record at any level.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiClientError:
            pass

    assert_token_not_in_logs(token, records)


# ---------------------------------------------------------------------------
# Property 6 — 5xx error path
# ---------------------------------------------------------------------------


@given(
    token=token_strings,
    status=st.integers(min_value=500, max_value=599),
)
@settings(max_examples=100)
def test_token_not_in_logs_5xx_error_path(token, status):
    """**Validates: Requirements 12.5**

    For any arbitrary token string and any 5xx status code, the resulting
    ApiServerError path must not include the token in any log record at any
    level.
    """
    resp = make_response(status)
    http = make_client_session(resp)
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiServerError:
            pass

    assert_token_not_in_logs(token, records)


# ---------------------------------------------------------------------------
# Property 6 — timeout path
# ---------------------------------------------------------------------------


@given(token=token_strings)
@settings(max_examples=100)
def test_token_not_in_logs_timeout_path(token):
    """**Validates: Requirements 12.5**

    For any arbitrary token string, a request that times out (asyncio.TimeoutError)
    must not include the token in any log record at any level.
    """
    http = MagicMock()
    http.request = AsyncMock(side_effect=asyncio.TimeoutError())
    oauth = make_oauth_session(token)
    client = BoschEBikeApiClient(http, oauth)

    with capture_logs() as records:
        try:
            run(client.fetch_bikes())
        except ApiTimeoutError:
            pass

    assert_token_not_in_logs(token, records)
