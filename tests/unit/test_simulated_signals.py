"""Unit tests for SimulatedAcquirer signal generation."""

import numpy as np
import pytest

from acquirers import SimulatedAcquirer


@pytest.fixture
def simulator():
    acq = SimulatedAcquirer.__new__(SimulatedAcquirer)
    acq.rnd_data = np.cumsum(np.random.randn(500))
    return acq


@pytest.mark.parametrize(
    "signal_type,period,expected_at_start",
    [
        ("sine", 10, 50.0),
        ("triangle", 10, 0.0),
        ("sawtooth", 10, 0.0),
        ("square", 10, 100.0),
    ],
)
def test_simulate_signal_waveforms(simulator, signal_type, period, expected_at_start):
    # last_data_point=-1 => internal step 0 => normalized_time 0
    value, step = simulator.simulate_signal(signal_type, period, -1, 0, 100)
    assert step == 0
    assert value == pytest.approx(expected_at_start)


def test_simulate_signal_random_uses_buffer(simulator):
    v1, _ = simulator.simulate_signal("random", 100, 499, 0, 100)
    v2, _ = simulator.simulate_signal("random", 100, 999, 0, 100)
    assert v1 == pytest.approx(v2)
