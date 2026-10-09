# Watchdog fallback: b2

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | B1 | REJECT | clear-to-rise=1001522723 ns; poll gap over 50 us=True |
| 1 | B2 | FAIL | fallback_latency_ns=69000; end-to-end_ns=1001591723 |
| 1 | B3 | PASS | fallback_step=0.0 |
| 1 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 1 | B6 | PASS | recovery_seconds=0.300031514; nominal_seconds=0.3 |
| 1 | B7 | FAIL | recovery_step=0.010009765625 |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 2 | B1 | REJECT | clear-to-rise=244984420 ns; poll gap over 50 us=True |
| 2 | B2 | FAIL | fallback_latency_ns=70000; end-to-end_ns=245054420 |
| 2 | B3 | PASS | fallback_step=0.0 |
| 2 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 2 | B6 | PASS | recovery_seconds=0.300031512; nominal_seconds=0.3 |
| 2 | B7 | FAIL | recovery_step=0.0170135498046875 |
| 2 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 3 | B1 | REJECT | clear-to-rise=245003418 ns; poll gap over 50 us=True |
| 3 | B2 | FAIL | fallback_latency_ns=66000; end-to-end_ns=245069418 |
| 3 | B3 | PASS | fallback_step=0.0 |
| 3 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 3 | B6 | PASS | recovery_seconds=0.30003151; nominal_seconds=0.3 |
| 3 | B7 | FAIL | recovery_step=0.0011444091796875 |
| 3 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 4 | B1 | REJECT | clear-to-rise=348795594 ns; poll gap over 50 us=True |
| 4 | B2 | FAIL | fallback_latency_ns=None; end-to-end_ns=None |
| 4 | B3 | FAIL | fallback_step=None |
| 4 | B5 | FAIL | flat_updates=None; axi_write_count/3=None |
| 4 | B6 | FAIL | recovery_seconds=; nominal_seconds=0.3 |
| 4 | B7 | FAIL | recovery_step=None |
| 4 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |

Rejected repetitions: 4
