"""
Pytest hooks for VanDAQ: repo import paths and mocks for optional hardware SDKs.

Mocks are registered at conftest import time so ``import acquirers`` works in CI
without LabJack, Phidget22, or (when missing) ipcqueue.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _subdir in ("common", "acquirer", "collector", "submitter"):
    _path = str(_REPO_ROOT / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _install_labjack_mock() -> None:
    labjack = MagicMock()
    ljm = MagicMock()
    ljm.openS = MagicMock(return_value=MagicMock())
    ljm.eWriteName = MagicMock()
    ljm.eReadName = MagicMock(return_value=0.0)
    labjack.ljm = ljm
    sys.modules.setdefault("labjack", labjack)
    sys.modules.setdefault("labjack.ljm", ljm)


def _install_phidget_mocks() -> None:
    sys.modules.setdefault("Phidget22", MagicMock())
    sys.modules.setdefault("Phidget22.Phidget", MagicMock())

    voltage_mod = MagicMock()
    voltage_mod.VoltageInput = MagicMock()
    sys.modules.setdefault("Phidget22.Devices.VoltageInput", voltage_mod)

    digital_mod = MagicMock()
    digital_mod.DigitalInput = MagicMock()
    sys.modules.setdefault("Phidget22.Devices.DigitalInput", digital_mod)


def _install_ipcqueue_mock_if_needed() -> None:
    try:
        import ipcqueue  # noqa: F401
    except ImportError:
        ipcqueue = MagicMock()
        ipcqueue.posixmq = MagicMock()
        sys.modules["ipcqueue"] = ipcqueue


_install_labjack_mock()
_install_phidget_mocks()
_install_ipcqueue_mock_if_needed()


import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_REPO = Path(__file__).resolve().parents[1]

# SQLite cannot create geolocation (composite PK) or the alarm view; omit for DB tests.
_SQLITE_TABLES = None


def _sqlite_metadata_tables():
    global _SQLITE_TABLES
    if _SQLITE_TABLES is None:
        from vandaq_schema import (
            DimAcquisitionType,
            DimAlarmLevel,
            DimAlarmType,
            DimInstrument,
            DimParameter,
            DimPlatform,
            DimTime,
            DimUnit,
            FactAlarm,
            FactMeasurement,
        )

        _SQLITE_TABLES = [
            DimPlatform.__table__,
            DimInstrument.__table__,
            DimParameter.__table__,
            DimUnit.__table__,
            DimAcquisitionType.__table__,
            DimTime.__table__,
            DimAlarmLevel.__table__,
            DimAlarmType.__table__,
            FactMeasurement.__table__,
            FactAlarm.__table__,
        ]
    return _SQLITE_TABLES


@pytest.fixture
def repo_root():
    return _REPO


@pytest.fixture
def co2simulator_config(repo_root):
    path = repo_root / "acquirer/config/disabled/co2simulator.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def aeris_config(repo_root):
    path = repo_root / "acquirer/config/Aeris_CH4_C2H6.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def airmar_config(repo_root):
    path = repo_root / "acquirer/config/Airmar_WX200.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def licor_config(repo_root):
    path = repo_root / "acquirer/config/Licor_7200_CO2.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def ecophysics_config(repo_root):
    path = repo_root / "acquirer/config/EcoPhysics_NOX.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def bare_acquirer(mock_logger):
    """Minimal Acquirer instance without queues or serial."""

    def _make(config):
        from acquirers import Acquirer

        acq = Acquirer.__new__(Acquirer)
        acq.config = config
        acq.logger = mock_logger
        return acq

    return _make


@pytest.fixture
def bare_nmea_acquirer(mock_logger):
    """SerialNmeaAcquirer without opening serial."""

    def _make(config):
        from acquirers import SerialNmeaAcquirer

        acq = SerialNmeaAcquirer.__new__(SerialNmeaAcquirer)
        acq.config = config
        acq.logger = mock_logger
        acq.measurement_delay = config.get("measurement_delay_secs", 0)
        return acq

    return _make


@pytest.fixture
def bare_gps_acquirer(mock_logger):
    def _make(config):
        from acquirers import SerialNmeaGPSAcquirer

        acq = SerialNmeaGPSAcquirer.__new__(SerialNmeaGPSAcquirer)
        acq.config = config
        acq.logger = mock_logger
        acq.measurement_delay = config.get("measurement_delay_secs", 0)
        return acq

    return _make


@pytest.fixture
def sqlite_inserter(mock_logger):
    """Inserter backed by in-memory SQLite (subset of schema)."""
    from vandaq_collector import Inserter
    from vandaq_schema import Base

    from vandaq_schema import DimTime

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_sqlite_metadata_tables())
    session = sessionmaker(bind=engine)()
    config = {"insert_batch_seconds": 1, "cache_time_seconds": 0}
    inserter = Inserter(engine, session, config, mock_logger)

    # SQLite bulk_insert_mappings does not fill BIGINT ids; assign for DimTime rows.
    _time_id = [1]
    _orig_bulk = session.bulk_insert_mappings

    def _bulk_with_time_ids(model, mappings, **kwargs):
        if model is DimTime:
            for row in mappings:
                row["id"] = _time_id[0]
                _time_id[0] += 1
        return _orig_bulk(model, mappings, **kwargs)

    session.bulk_insert_mappings = _bulk_with_time_ids

    # SQLite does not autoincrement BIGINT; assign ids explicitly for fact rows.
    _meas_id = [1]
    _alarm_id = [1]

    def _sqlite_batch_insert_measurements(self, measurements):
        from vandaq_schema import FactMeasurement

        updated = []
        for measurement in measurements:
            row = {k: v for k, v in measurement.items() if k != "alarms"}
            rec = FactMeasurement(id=_meas_id[0], **row)
            _meas_id[0] += 1
            self.session.add(rec)
            self.session.flush()
            updated.append({**measurement, "id": rec.id})
        return updated

    def _sqlite_batch_insert_alarms(self, alarms):
        from vandaq_schema import FactAlarm

        if not alarms:
            return
        for row in alarms:
            self.session.add(FactAlarm(id=_alarm_id[0], **row))
            _alarm_id[0] += 1
        self.session.flush()

    inserter.batch_insert_measurements = _sqlite_batch_insert_measurements.__get__(
        inserter, Inserter
    )
    inserter.batch_insert_alarms = _sqlite_batch_insert_alarms.__get__(inserter, Inserter)

    yield inserter, session
    session.close()


@pytest.fixture
def sample_measurement():
    from datetime import datetime

    now = datetime(2025, 6, 1, 12, 0, 0)
    return {
        "platform": "van1",
        "instrument": "CO2_Simulator",
        "parameter": "CO2",
        "unit": "ppm",
        "acquisition_type": "measurement_calibrated",
        "acquisition_time": now,
        "sample_time": now,
        "instrument_time": now,
        "value": 400.0,
    }


@pytest.fixture
def aeris_csv_line():
    return (
        "01/15/2025 12:00:00.0,0,240.0,25.0,25.0,25.0,25.0,25.0,2.5,100.0,1.0,0.5,"
        "x,25.0,0,x,x"
    )


@pytest.fixture
def serial_stream_acquirer(aeris_config, mock_logger):
    """SerialStreamAcquirer with mocked POSIX queue and serial port."""
    from unittest.mock import patch

    from acquirers import Acquirer, SerialStreamAcquirer

    mock_port = MagicMock()
    mock_port.in_waiting = 0
    mock_port.read.return_value = b""

    with patch.object(Acquirer, "open_queue", return_value=MagicMock()):
        with patch("acquirers.serial.Serial", return_value=mock_port):
            acq = SerialStreamAcquirer(aeris_config)
    acq.serial_port = mock_port
    acq.serial_open = True
    return acq, mock_port


@pytest.fixture
def mock_logger():
    """Logger that records error calls for parser tests."""
    logger = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    return logger
