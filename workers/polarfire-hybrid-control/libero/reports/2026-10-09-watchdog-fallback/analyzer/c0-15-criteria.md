# Watchdog fallback: c0

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | C1 | PASS | high_ns=539000; expected 500000 +/- 100000 |
| 1 | C2 | PASS | trip delta=1 |
| 1 | B2 | FAIL | fallback_latency_ns=0; end-to-end_ns=995214105 |
| 1 | B3 | PASS | fallback_step=0.0 |
| 1 | B4 | PASS | sustained flat=True |
| 1 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 1 | B6 | PASS | recovery_seconds=0.300031032; nominal_seconds=0.3 |
| 1 | B7 | FAIL | recovery_step=0.0130157470703125 |
| 1 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 1 | C4 | FAIL | requires B2 through B5; B4 checks flatness through recovery |
| 2 | C1 | REJECT | high_ns=None; expected 500000 +/- 100000 |
| 2 | C2 | REJECT | trip delta=1 |

Rejected repetitions: 1
