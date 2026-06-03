"""Verify conftest mocks allow importing core modules without hardware SDKs."""


def test_import_acquirers():
    import acquirers

    assert hasattr(acquirers, "RecordParser")
    assert hasattr(acquirers, "SimulatedAcquirer")


def test_import_collector_schema():
    import vandaq_schema

    assert hasattr(vandaq_schema, "FactMeasurement")
