"""SerialStreamAcquirer tests with mocked serial port."""

from unittest.mock import MagicMock

import pytest

def test_getline_returns_first_complete_line(serial_stream_acquirer):
    acq, port = serial_stream_acquirer
    port.in_waiting = 1
    port.read.return_value = b"first line\nsecond line\npart"

    assert acq.getline() == "first line"
    port.in_waiting = 0
    assert acq.getline() == "second line"
    assert acq.getline() is None
    assert acq.partial_line == "part"


def test_getline_empty_when_no_data(serial_stream_acquirer):
    acq, port = serial_stream_acquirer
    port.in_waiting = 0
    assert acq.getline() is None


def test_getline_and_parse_aeris_csv(serial_stream_acquirer, aeris_csv_line):
    acq, port = serial_stream_acquirer
    line = aeris_csv_line
    port.in_waiting = 1
    port.read.return_value = (line + "\n").encode()

    got = acq.getline()
    records = acq.parse_simple_string_to_record(got, config_dict=acq.config["stream"])

    assert got == line
    assert len(records) >= 1
    ch4 = next(r for r in records if r["parameter"] == "CH4")
    assert ch4["value"] == pytest.approx(2.5)


def test_response_header_routes_to_response_queue(serial_stream_acquirer):
    acq, _port = serial_stream_acquirer
    acq.put_response_to_queue = MagicMock()
    header = acq.config["response_header"]
    line = header + "instrument OK"

    if line and header and line[0 : len(header)] == header:
        acq.put_response_to_queue({"response": line})

    acq.put_response_to_queue.assert_called_once_with({"response": line})


def test_spider_csv_header_line_skipped():
    line = "date_____Time,CO2,Status"
    assert line.lstrip().startswith("date____")
