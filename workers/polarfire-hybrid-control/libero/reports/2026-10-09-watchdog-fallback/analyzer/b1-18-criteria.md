# Watchdog fallback: b1

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | B1 | REJECT | clear-to-rise=572173278 ns; poll gap over 50 us=True |
| 1 | B2 | FAIL | fallback_latency_ns=None; end-to-end_ns=None |
| 1 | B3 | FAIL | fallback_step=None |
| 1 | B4 | FAIL | sustained flat=False |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 2 | B1 | REJECT | clear-to-rise=429272957 ns; poll gap over 50 us=True |
| 2 | B2 | FAIL | fallback_latency_ns=66000; end-to-end_ns=429338957 |
| 2 | B3 | PASS | fallback_step=0.0 |
| 2 | B4 | PASS | sustained flat=True |
| 2 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |

Rejected repetitions: 2
