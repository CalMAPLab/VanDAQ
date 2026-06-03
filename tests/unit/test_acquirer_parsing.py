"""Acquirer parsing pack: real YAML fixtures, NMEA, aggregation, alarms."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from acquirers import RecordParser, SimulatedAcquirer, SerialNmeaAcquirer, SerialNmeaGPSAcquirer


def _aeris_line(**overrides):
    """Synthetic Aeris CSV matching stream.items column count."""
    defaults = {
        "dt": "01/15/2025 12:00:00.0",
        "inlet": "0",
        "p": "240.0",
        "t0": "25.0",
        "t1": "25.0",
        "t2": "25.0",
        "t5": "25.0",
        "tgas": "25.0",
        "ch4": "2.5",
        "h2o": "100.0",
        "c2h6": "1.0",
        "r": "0.5",
        "tec": "25.0",
        "wall": "0",
    }
    defaults.update(overrides)
    return ",".join(
        [
            defaults["dt"],
            defaults["inlet"],
            defaults["p"],
            defaults["t0"],
            defaults["t1"],
            defaults["t2"],
            defaults["t5"],
            defaults["tgas"],
            defaults["ch4"],
            defaults["h2o"],
            defaults["c2h6"],
            defaults["r"],
            "x",
            defaults["tec"],
            defaults["wall"],
            "x",
            "x",
        ]
    )


def test_aeris_parse_inst_datetime_and_gases(mock_logger, aeris_config):
    parser = RecordParser(aeris_config, mock_logger)
    records = parser.parse_simple_string_to_record(_aeris_line())

    assert records is not None
    by_param = {r["parameter"]: r for r in records}
    assert by_param["CH4"]["value"] == pytest.approx(2.5)
    assert by_param["P"]["unit"] == "mbar"
    assert by_param["CH4"]["instrument_time"] == datetime(2025, 1, 15, 12, 0, 0)


def test_aeris_measurement_delay_shifts_sample_time(mock_logger, aeris_config):
    aeris_config["measurement_delay_secs"] = 10
    parser = RecordParser(aeris_config, mock_logger)
    records = parser.parse_simple_string_to_record(_aeris_line())
    ch4 = next(r for r in records if r["parameter"] == "CH4")

    assert ch4["sample_time"] == ch4["acquisition_time"] - timedelta(seconds=10)


def test_aeris_parse_invalid_datetime_returns_none(mock_logger, aeris_config):
    parser = RecordParser(aeris_config, mock_logger)
    result = parser.parse_simple_string_to_record(_aeris_line(dt="not-a-date"))
    assert result is None
    mock_logger.error.assert_called()


def test_licor_tab_delimited_inst_date_time(mock_logger, licor_config):
    parser = RecordParser(licor_config, mock_logger)
    items = licor_config["stream"]["items"].split(",")
    parts = ["0"] * len(items)
    idx = {name: i for i, name in enumerate(items)}
    parts[idx["inst_date"]] = "2025-06-01"
    parts[idx["inst_time"]] = "14:30:00:000"
    parts[idx["CO2D"]] = "412.5"
    parts[idx["MeasFlowRate"]] = "10.0"
    line = "\t".join(parts)

    records = parser.parse_simple_string_to_record(line)
    by_param = {r["parameter"]: r for r in records}

    assert by_param["CO2D"]["value"] == pytest.approx(412.5)
    assert by_param["CO2D"]["instrument_time"] == datetime(2025, 6, 1, 14, 30, 0)


def test_ecophysics_aggregation_mean(mock_logger, ecophysics_config):
    parser = RecordParser(ecophysics_config, mock_logger)
    key = ecophysics_config["instrument"]

    line1 = ",1.0,2.0,,3.0,,,,,,,,,cdj,vvvv,hxf,eeee,wwww,iott"
    assert parser.parse_simple_string_to_record(line1) is None

    parser.last_aggregate_time[key] = datetime.now() - timedelta(seconds=2)
    line2 = ",4.0,5.0,,6.0,,,,,,,,,cdj,vvvv,hxf,eeee,wwww,iott"
    records = parser.parse_simple_string_to_record(line2)

    assert records is not None
    by_param = {r["parameter"]: r for r in records}
    assert by_param["NOx"]["value"] == pytest.approx(2.5)
    assert by_param["NO"]["value"] == pytest.approx(3.5)
    assert by_param["NO2"]["value"] == pytest.approx(4.5)
    assert by_param["cdj"]["string"] == "cdj"


def test_apply_alarms_ch4_overrange(bare_acquirer, aeris_config):
    acq = bare_acquirer(aeris_config)
    out = acq.apply_alarms([{"parameter": "T2", "value": 35.0}])
    assert out[0]["alarms"][0]["alarm_type"] == "overrange"


def test_apply_alarms_inlet_number_neq(bare_acquirer, aeris_config):
    acq = bare_acquirer(aeris_config)
    out = acq.apply_alarms([{"parameter": "Inlet_Number", "value": 1.0}])
    assert out[0]["alarms"][0]["alarm_type"] == "wrong_value"


def test_apply_alarms_measflow_underrange(bare_acquirer, licor_config):
    acq = bare_acquirer(licor_config)
    out = acq.apply_alarms([{"parameter": "MeasFlowRate", "value": 5.0}])
    assert out[0]["alarms"][0]["alarm_message"] == "MeasFlowRate below 8 slpm"


def test_apply_alarms_multiple_rules_first_match(bare_acquirer, aeris_config):
    acq = bare_acquirer(aeris_config)
    out = acq.apply_alarms([{"parameter": "P", "value": 250.0}])
    assert len(out[0]["alarms"]) == 1
    assert out[0]["alarms"][0]["alarm_type"] == "overrange"


def test_nmea_mwv_wind_from_airmar_config(bare_nmea_acquirer, airmar_config):
    acq = bare_nmea_acquirer(airmar_config)
    messages = acq.process_nmea_sentence("$WIMWV,215.0,R,10.5,M,A")

    assert messages is not None
    by_param = {m["parameter"]: m for m in messages}
    assert by_param["Wind_Speed"]["value"] == pytest.approx(10.5)
    assert by_param["Wind_Angle"]["value"] == pytest.approx(215.0)
    assert by_param["Wind_Speed"]["unit"] == "m/s"


def test_nmea_gga_lat_lon_skips_zero(bare_nmea_acquirer, airmar_config):
    acq = bare_nmea_acquirer(airmar_config)
    messages = acq.process_nmea_sentence(
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
    )

    by_param = {m["parameter"]: m for m in messages}
    assert by_param["latitude"]["value"] == pytest.approx(48.1173, rel=1e-3)
    assert by_param["longitude"]["value"] == pytest.approx(11.517, rel=1e-2)
    assert "latitude" not in {m["parameter"] for m in acq.process_nmea_sentence("$GPGGA,,,,,,0,,,,,,,") or []}


def test_nmea_gps_rmc_course_and_speed(bare_gps_acquirer, airmar_config):
    acq = bare_gps_acquirer(airmar_config)
    messages = acq.process_nmea_sentence(
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W"
    )

    by_param = {m["parameter"]: m for m in messages}
    assert by_param["latitude"]["acquisition_type"] == "GPS"
    assert by_param["speed"]["value"] == pytest.approx(22.4 * 0.514444, rel=1e-3)
    assert by_param["direction"]["value"] == pytest.approx(84.4)


def test_nmea_invalid_sentence_logs_error(bare_nmea_acquirer, airmar_config, mock_logger):
    acq = bare_nmea_acquirer(airmar_config)
    assert acq.process_nmea_sentence("not nmea") is None
    mock_logger.error.assert_called()


def test_simulated_make_data_line_parses(mock_logger, co2simulator_config):
    sim = SimulatedAcquirer.__new__(SimulatedAcquirer)
    sim.config = co2simulator_config
    sim.parameters = co2simulator_config["stream"]["items"].split(",")
    sim.rnd_data = np.cumsum(np.random.randn(500))
    sim.cycletime = 1

    line = sim.make_data_line()
    records = RecordParser(co2simulator_config, mock_logger).parse_simple_string_to_record(line)

    assert len(records) == 4
    assert all("value" in r for r in records)


def test_parse_with_scalers(mock_logger):
    config = {
        "platform": "van1",
        "instrument": "scaled",
        "measurement_delay_secs": 0,
        "stream": {
            "item_delimiter": ",",
            "items": "x,conc,x",
            "formats": "x,f,x",
            "units": "x,ppb,x",
            "acqTypes": "x,measurement_calibrated,x",
            "scalers": "1,1000,1",
        },
    }
    parser = RecordParser(config, mock_logger)
    records = parser.parse_simple_string_to_record(",2.5,")
    assert records[0]["value"] == pytest.approx(2500.0)
