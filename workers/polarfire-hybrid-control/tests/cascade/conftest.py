"""Pytest configuration for cascade verify_bit_exact CI.

Adds a --mode={sim,hil} flag that selects the source of FPGA-side INT8
output for the bit-exact comparison.

  --mode=sim  (default)  Compare numpy compose_int8 reference against the
                          cached expected_int8.csv from the C++ tb_cascade
                          fixture. Available immediately; pre-Track-0.
  --mode=hil             Compare numpy compose_int8 reference against an
                          HIL-captured FPGA output (UART0 console dump or
                          SmartDebug readback) under
                          tests/cascade/fixtures/hil/. Post-Track-0 only.

The --mode=hil leg requires real hardware-in-the-loop captures to land
under tests/cascade/fixtures/hil/{capture_name}/. If no captures are
present, --mode=hil tests skip with a clear message rather than fail.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--mode",
        action="store",
        default="sim",
        choices=("sim", "hil"),
        help="Cascade verify mode: 'sim' (numpy vs golden CSV) or "
             "'hil' (numpy vs FPGA capture). Default: sim.",
    )


@pytest.fixture(scope="session")
def cascade_mode(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--mode")
