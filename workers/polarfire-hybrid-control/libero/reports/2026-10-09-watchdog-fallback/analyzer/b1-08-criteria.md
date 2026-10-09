# Watchdog fallback: b1

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | B1 | REJECT | clear-to-rise=1001525162 ns; poll gap over 50 us=True |
| 1 | B2 | FAIL | fallback_latency_ns=68000; end-to-end_ns=1001593162 |
| 1 | B3 | PASS | fallback_step=0.0 |
| 1 | B4 | PASS | sustained flat=True |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |

Rejected repetitions: 1
