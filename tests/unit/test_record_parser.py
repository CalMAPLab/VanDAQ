"""Unit tests for RecordParser and apply_alarms."""

from datetime import datetime

import pytest

from acquirers import Acquirer, RecordParser


def test_strip_non_numeric(mock_logger, co2simulator_config):
    parser = RecordParser(co2simulator_config, mock_logger)
    assert parser.strip_non_numeric("P=12.3mbar") == "12.3"
    assert parser.strip_non_numeric("-1.5e2") == "-1.5e2"


def test_parse_co2simulator_line(mock_logger, co2simulator_config):
    parser = RecordParser(co2simulator_config, mock_logger)
    line = "400.5,210.0,900.0,45.2"
    records = parser.parse_simple_string_to_record(line)

    assert records is not None
    assert len(records) == 4
    by_param = {r["parameter"]: r for r in records}
    assert by_param["CO2"]["value"] == pytest.approx(400.5)
    assert by_param["CO2"]["platform"] == "van1"
    assert by_param["CO2"]["instrument"] == "CO2_Simulator"
    assert by_param["H2O"]["unit"] == "ppm"


def test_inst_datetime_24_hour_rollover(mock_logger):
    config = {
        "platform": "van1",
        "instrument": "test_inst",
        "measurement_delay_secs": 0,
        "stream": {
            "item_delimiter": ",",
            "items": "inst_datetime,CO2",
            "formats": "%m/%d/%Y %H:%M:%S,f",
            "units": "datetime,ppm",
            "acqTypes": "inst_datetime,measurement_calibrated",
        },
    }
    parser = RecordParser(config, mock_logger)
    line = "01/15/2025 24:00:00,42.0"
    records = parser.parse_simple_string_to_record(line)

    assert len(records) == 2
    co2 = next(r for r in records if r["parameter"] == "CO2")
    assert co2["value"] == pytest.approx(42.0)
    assert co2["instrument_time"] == datetime(2025, 1, 16, 0, 0, 0)


def test_apply_alarms_pressure_underrange(mock_logger, aeris_config):
    acq = Acquirer.__new__(Acquirer)
    acq.config = aeris_config
    acq.logger = mock_logger

    messages = [
        {
            "parameter": "P",
            "value": 230.0,
            "platform": "van1",
            "instrument": "Aeris_CH4_C2H6",
        }
    ]
    out = acq.apply_alarms(messages)

    assert "alarms" in out[0]
    assert out[0]["alarms"][0]["alarm_type"] == "underrange"
    assert out[0]["alarms"][0]["data_impacted"] is True


def test_apply_alarms_pressure_in_range(mock_logger, aeris_config):
    acq = Acquirer.__new__(Acquirer)
    acq.config = aeris_config
    acq.logger = mock_logger

    messages = [{"parameter": "P", "value": 240.0}]
    out = acq.apply_alarms(messages)

    assert "alarms" not in out[0]


def test_apply_alarms_substr_is(mock_logger):
    config = {
        "alarms": {
            "Status": [
                {
                    "substr_is": {
                        "substr_begin": 0,
                        "substr_end": 3,
                        "value": "ERR",
                        "alarm_level": "warning",
                        "alarm_type": "status_flag",
                        "alarm_message": "Instrument reported ERR",
                        "impacts_data": False,
                    }
                }
            ]
        }
    }
    acq = Acquirer.__new__(Acquirer)
    acq.config = config
    acq.logger = mock_logger

    messages = [{"parameter": "Status", "string": "ERR: fault"}]
    out = acq.apply_alarms(messages)

    assert out[0]["alarms"][0]["alarm_type"] == "status_flag"
    assert out[0]["alarms"][0]["data_impacted"] is False
