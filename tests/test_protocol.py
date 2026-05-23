"""
Unit tests for server/protocol.py validation logic.
Run with: pytest tests/test_protocol.py
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from protocol import validate_batch, validate_timestamp, validate_finite_number, STATION_ID_MAX_LENGTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_reading(**overrides):
    base = {
        "station_id": "STATION-001",
        "timestamp": "2024-01-17T12:00:00+00:00",
        "temperature": 22.5,
        "humidity": 55.0,
        "windspeed": 5.0,
    }
    base.update(overrides)
    return base


def _valid_batch(n=1, **overrides):
    return [_valid_reading(**overrides) for _ in range(n)]


# ---------------------------------------------------------------------------
# validate_timestamp
# ---------------------------------------------------------------------------

class TestValidateTimestamp:
    def test_accepts_utc_z(self):
        validate_timestamp("2024-01-17T12:00:00Z")

    def test_accepts_offset(self):
        validate_timestamp("2024-01-17T12:00:00+02:00")

    def test_accepts_microseconds(self):
        validate_timestamp("2024-01-17T12:00:00.123456Z")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="timestamp must be a string"):
            validate_timestamp(12345)

    def test_rejects_invalid_format(self):
        with pytest.raises(ValueError, match="invalid_timestamp"):
            validate_timestamp("not-a-date")

    def test_rejects_garbage_string(self):
        with pytest.raises(ValueError, match="invalid_timestamp"):
            validate_timestamp("17/01/2024 12:00")


# ---------------------------------------------------------------------------
# validate_finite_number
# ---------------------------------------------------------------------------

class TestValidateFiniteNumber:
    def test_accepts_int(self):
        validate_finite_number(25, "temperature")

    def test_accepts_float(self):
        validate_finite_number(25.5, "temperature")

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="non_finite_number"):
            validate_finite_number(float("nan"), "temperature")

    def test_rejects_inf(self):
        with pytest.raises(ValueError, match="non_finite_number"):
            validate_finite_number(float("inf"), "temperature")

    def test_rejects_bool(self):
        with pytest.raises(ValueError, match="must be a number"):
            validate_finite_number(True, "temperature")

    def test_rejects_string(self):
        with pytest.raises(ValueError, match="must be a number"):
            validate_finite_number("25.5", "temperature")


# ---------------------------------------------------------------------------
# validate_batch — structural rules
# ---------------------------------------------------------------------------

class TestValidateBatchStructure:
    def test_accepts_valid_single(self):
        validate_batch(_valid_batch(1))

    def test_accepts_valid_multi(self):
        validate_batch(_valid_batch(5))

    def test_rejects_non_list(self):
        with pytest.raises(ValueError, match="not a list"):
            validate_batch({"station_id": "X"})

    def test_rejects_oversized_batch(self):
        from protocol import MAX_BATCH_SIZE
        with pytest.raises(ValueError, match="batch size exceeds limit"):
            validate_batch(_valid_batch(MAX_BATCH_SIZE + 1))

    def test_rejects_non_dict_item(self):
        with pytest.raises(ValueError, match="not a dict"):
            validate_batch(["not-a-dict"])

    def test_rejects_missing_field(self):
        reading = _valid_reading()
        del reading["humidity"]
        with pytest.raises(ValueError, match="missing humidity"):
            validate_batch([reading])


# ---------------------------------------------------------------------------
# validate_batch — station_id rules
# ---------------------------------------------------------------------------

class TestValidateBatchStationId:
    def test_rejects_empty_station_id(self):
        with pytest.raises(ValueError, match="empty station_id"):
            validate_batch([_valid_reading(station_id="")])

    def test_rejects_non_string_station_id(self):
        with pytest.raises(ValueError, match="invalid station_id"):
            validate_batch([_valid_reading(station_id=123)])

    def test_rejects_station_id_too_long(self):
        long_id = "X" * (STATION_ID_MAX_LENGTH + 1)
        with pytest.raises(ValueError, match="station_id too long"):
            validate_batch([_valid_reading(station_id=long_id)])

    def test_accepts_max_length_station_id(self):
        max_id = "X" * STATION_ID_MAX_LENGTH
        validate_batch([_valid_reading(station_id=max_id)])


# ---------------------------------------------------------------------------
# validate_batch — range rules
# ---------------------------------------------------------------------------

class TestValidateBatchRanges:
    def test_rejects_temperature_too_low(self):
        with pytest.raises(ValueError, match="invalid temperature"):
            validate_batch([_valid_reading(temperature=-100.0)])

    def test_rejects_temperature_too_high(self):
        with pytest.raises(ValueError, match="invalid temperature"):
            validate_batch([_valid_reading(temperature=200.0)])

    def test_accepts_temperature_boundary(self):
        validate_batch([_valid_reading(temperature=-40.0)])
        validate_batch([_valid_reading(temperature=85.0)])

    def test_rejects_humidity_out_of_range(self):
        with pytest.raises(ValueError, match="invalid humidity"):
            validate_batch([_valid_reading(humidity=101.0)])

    def test_rejects_windspeed_negative(self):
        with pytest.raises(ValueError, match="invalid windspeed"):
            validate_batch([_valid_reading(windspeed=-1.0)])

    def test_rejects_windspeed_too_high(self):
        with pytest.raises(ValueError, match="invalid windspeed"):
            validate_batch([_valid_reading(windspeed=200.0)])

    def test_accepts_windspeed_boundary(self):
        validate_batch([_valid_reading(windspeed=100.0)])

    def test_rejects_non_finite_temperature(self):
        with pytest.raises(ValueError, match="non_finite_number|invalid temperature"):
            validate_batch([_valid_reading(temperature=float("nan"))])


# ---------------------------------------------------------------------------
# validate_batch — all-or-nothing semantics
# ---------------------------------------------------------------------------

class TestValidateBatchAllOrNothing:
    def test_first_valid_second_invalid_raises(self):
        batch = [_valid_reading(), _valid_reading(temperature=999.0)]
        with pytest.raises(ValueError, match="invalid temperature at index 1"):
            validate_batch(batch)

    def test_empty_batch_is_valid(self):
        validate_batch([])
