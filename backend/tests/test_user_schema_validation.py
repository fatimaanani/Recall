"""
test_user_schema_validation.py

Pure Pydantic-layer tests for the shared date_of_birth rule
(app.schemas.user.validate_date_of_birth) and the two schemas that use it:
RegisterRequest (always required) and UpdateProfileRequest (optional,
same rule when provided). No database/service layer involved -- these are
schema-only validators, so no mocker/db fixtures are needed here.

1. validate_date_of_birth -- boundary behavior (exact age math)
2. RegisterRequest -- required field + validator wiring
3. UpdateProfileRequest -- optional field, same rule when provided
"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.user import MIN_REGISTRATION_AGE, UpdateProfileRequest, validate_date_of_birth

# ===========================================================================
# Shared helpers
# ===========================================================================


def _today() -> datetime.date:
    return datetime.date.today()


def _years_ago(years: int, *, days: int = 0) -> datetime.date:
    """A date `years` years before today, then shifted by `days` (positive
    = later/younger, negative = earlier/older) -- used to land exactly on
    or just off the MIN_REGISTRATION_AGE boundary without hand-computing
    calendar math per test."""
    d = _today().replace(year=_today().year - years)
    return d + datetime.timedelta(days=days)


def _register_payload(**overrides) -> dict:
    defaults = dict(
        full_name="Test User",
        username="testuser",
        email="test@example.com",
        password="password123",
        date_of_birth=_years_ago(20),
        gender=None,
        occupation=None,
    )
    defaults.update(overrides)
    return defaults


# ===========================================================================
# 1. validate_date_of_birth -- boundary behavior
# ===========================================================================


def test_exactly_minimum_age_today_is_accepted():
    dob = _years_ago(MIN_REGISTRATION_AGE)
    assert validate_date_of_birth(dob) == dob


def test_one_day_younger_than_minimum_age_is_rejected():
    # Born one day later than the exact-boundary date above -- turns
    # MIN_REGISTRATION_AGE tomorrow, not today.
    dob = _years_ago(MIN_REGISTRATION_AGE, days=1)
    with pytest.raises(ValueError, match=f"at least {MIN_REGISTRATION_AGE} years old"):
        validate_date_of_birth(dob)


def test_one_day_older_than_minimum_age_is_accepted():
    dob = _years_ago(MIN_REGISTRATION_AGE, days=-1)
    assert validate_date_of_birth(dob) == dob


def test_one_year_old_is_rejected():
    dob = _years_ago(1)
    with pytest.raises(ValueError, match="years old"):
        validate_date_of_birth(dob)


def test_newborn_today_is_rejected():
    dob = _today()
    with pytest.raises(ValueError, match="years old"):
        validate_date_of_birth(dob)


def test_future_date_is_rejected():
    dob = _today() + datetime.timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        validate_date_of_birth(dob)


def test_far_future_date_is_rejected():
    dob = _today().replace(year=_today().year + 5)
    with pytest.raises(ValueError, match="future"):
        validate_date_of_birth(dob)


def test_valid_adult_is_accepted():
    dob = _years_ago(30)
    assert validate_date_of_birth(dob) == dob


def test_leap_year_birthday_february_29_is_handled():
    # A Feb 29 birthday only recurs every 4 years -- real year/month/day
    # comparison (not naive year subtraction) must still land on the
    # correct side of the boundary in both leap and non-leap current years.
    dob = datetime.date(2012, 2, 29)
    # However old that actually makes them today -- just confirm no crash
    # and a real bool-ish outcome via age math, not a hardcoded expectation
    # of a specific age (would break every year this suite runs).
    today = _today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    if age >= MIN_REGISTRATION_AGE:
        assert validate_date_of_birth(dob) == dob
    else:
        with pytest.raises(ValueError, match="years old"):
            validate_date_of_birth(dob)


# ===========================================================================
# 2. RegisterRequest -- required field + validator wiring
# ===========================================================================


def test_register_request_accepts_valid_adult_dob():
    req = RegisterRequest(**_register_payload(date_of_birth=_years_ago(25)))
    assert req.date_of_birth == _years_ago(25)


def test_register_request_missing_date_of_birth_is_rejected():
    payload = _register_payload()
    del payload["date_of_birth"]
    with pytest.raises(ValidationError, match="date_of_birth"):
        RegisterRequest(**payload)


def test_register_request_under_minimum_age_is_rejected():
    with pytest.raises(ValidationError, match="years old"):
        RegisterRequest(**_register_payload(date_of_birth=_years_ago(5)))


def test_register_request_future_date_is_rejected():
    with pytest.raises(ValidationError, match="future"):
        RegisterRequest(**_register_payload(date_of_birth=_today() + datetime.timedelta(days=30)))


def test_register_request_exactly_minimum_age_today_is_accepted():
    dob = _years_ago(MIN_REGISTRATION_AGE)
    req = RegisterRequest(**_register_payload(date_of_birth=dob))
    assert req.date_of_birth == dob


# ===========================================================================
# 3. UpdateProfileRequest -- optional field, same rule when provided
# ===========================================================================


def test_update_profile_request_allows_omitted_date_of_birth():
    req = UpdateProfileRequest(full_name="New Name")
    assert req.date_of_birth is None


def test_update_profile_request_allows_explicit_none():
    req = UpdateProfileRequest(date_of_birth=None)
    assert req.date_of_birth is None


def test_update_profile_request_accepts_valid_adult_dob():
    dob = _years_ago(40)
    req = UpdateProfileRequest(date_of_birth=dob)
    assert req.date_of_birth == dob


def test_update_profile_request_rejects_under_minimum_age():
    with pytest.raises(ValidationError, match="years old"):
        UpdateProfileRequest(date_of_birth=_years_ago(2))


def test_update_profile_request_rejects_future_date():
    with pytest.raises(ValidationError, match="future"):
        UpdateProfileRequest(date_of_birth=_today() + datetime.timedelta(days=1))
