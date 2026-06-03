"""Collector Inserter tests using in-memory SQLite."""

from datetime import datetime

from vandaq_schema import (
    DimInstrument,
    DimPlatform,
    FactAlarm,
    FactMeasurement,
)


def test_insert_subbatch_creates_measurement(sqlite_inserter, sample_measurement):
    inserter, session = sqlite_inserter

    inserter.insert_subbatch([sample_measurement])

    rows = session.query(FactMeasurement).all()
    assert len(rows) == 1
    assert rows[0].value == 400.0
    assert session.query(DimPlatform).count() == 1


def test_insert_subbatch_reuses_dimension_cache(sqlite_inserter, sample_measurement):
    inserter, session = sqlite_inserter
    msg2 = {**sample_measurement, "parameter": "H2O", "value": 2.0}

    inserter.insert_subbatch([sample_measurement, msg2])

    assert session.query(DimPlatform).count() == 1
    assert session.query(DimInstrument).count() == 1
    assert session.query(FactMeasurement).count() == 2


def test_insert_subbatch_with_alarm(sqlite_inserter, sample_measurement):
    inserter, session = sqlite_inserter
    sample_measurement["alarms"] = [
        {
            "alarm_level": "alarm",
            "alarm_type": "underrange",
            "alarm_message": "CO2 low",
            "data_impacted": True,
        }
    ]

    inserter.insert_subbatch([sample_measurement])

    assert session.query(FactMeasurement).count() == 1
    alarms = session.query(FactAlarm).all()
    assert len(alarms) == 1
    assert alarms[0].message == "CO2 low"


def test_get_or_create_time_dimension(sqlite_inserter):
    inserter, session = sqlite_inserter
    t = datetime(2025, 6, 1, 12, 0, 0)

    id1 = inserter.get_or_create_time_dimension(t)
    id2 = inserter.get_or_create_time_dimension(t)

    assert id1 == id2
    assert id1 is not None


def test_merge_gps_coordinates(sqlite_inserter):
    inserter, _session = sqlite_inserter
    records = [
        {
            "platform_id": 1,
            "instrument_id": 1,
            "sample_time_id": 10,
            "latitude": 37.87,
        },
        {
            "platform_id": 1,
            "instrument_id": 1,
            "sample_time_id": 10,
            "longitude": -122.27,
        },
    ]
    merged = inserter.merge_gps_coordinates(records)

    assert len(merged) == 1
    assert merged[0]["latitude"] == 37.87
    assert merged[0]["longitude"] == -122.27
