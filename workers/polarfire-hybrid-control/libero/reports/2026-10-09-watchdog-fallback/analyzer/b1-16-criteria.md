# Watchdog fallback: b1

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | B1 | REJECT | clear-to-rise=1001523529 ns; poll gap over 50 us=True |
| 1 | B2 | FAIL | fallback_latency_ns=68001; end-to-end_ns=1001591530 |
| 1 | B3 | PASS | fallback_step=0.0 |
| 1 | B4 | PASS | sustained flat=True |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |

Rejected repetitions: 1
