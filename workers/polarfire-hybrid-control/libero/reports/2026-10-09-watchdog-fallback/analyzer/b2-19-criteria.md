# Watchdog fallback: b2

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | B1 | REJECT | clear-to-rise=411185262 ns; poll gap over 50 us=True |
| 1 | B2 | FAIL | fallback_latency_ns=None; end-to-end_ns=None |
| 1 | B3 | FAIL | fallback_step=None |
| 1 | B5 | FAIL | flat_updates=None; axi_write_count/3=None |
| 1 | B6 | FAIL | recovery_seconds=; nominal_seconds=0.3 |
| 1 | B7 | FAIL | recovery_step=None |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 2 | B1 | REJECT | clear-to-rise=590273376 ns; poll gap over 50 us=True |
| 2 | B2 | FAIL | fallback_latency_ns=68000; end-to-end_ns=590341376 |
| 2 | B3 | PASS | fallback_step=0.0 |
| 2 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 2 | B6 | PASS | recovery_seconds=0.30003319; nominal_seconds=0.3 |
| 2 | B7 | FAIL | recovery_step=0.010009765625 |
| 2 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 3 | B1 | REJECT | clear-to-rise=269602171 ns; poll gap over 50 us=True |
| 3 | B2 | FAIL | fallback_latency_ns=None; end-to-end_ns=None |
| 3 | B3 | FAIL | fallback_step=None |
| 3 | B5 | FAIL | flat_updates=None; axi_write_count/3=None |
| 3 | B6 | FAIL | recovery_seconds=; nominal_seconds=0.3 |
| 3 | B7 | FAIL | recovery_step=None |
| 3 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |

Rejected repetitions: 3
