# Watchdog fallback: c0

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | C1 | REJECT | high_ns=38000; expected 500000 +/- 100000 |
| 1 | C2 | REJECT | trip delta=1 |
| 2 | C1 | PASS | high_ns=537000; expected 500000 +/- 100000 |
| 2 | C2 | PASS | trip delta=1 |
| 2 | B2 | FAIL | fallback_latency_ns=0; end-to-end_ns=586380053 |
| 2 | B3 | PASS | fallback_step=0.0 |
| 2 | B4 | PASS | sustained flat=True |
| 2 | B5 | PASS | flat_updates=1000; axi_write_count/3=1000 |
| 2 | B6 | PASS | recovery_seconds=0.300033027; nominal_seconds=0.3 |
| 2 | B7 | FAIL | recovery_step=0.0130157470703125 |
| 2 | B8 | PASS | AI <= 0.09 and actuator in [-1.0, 1.0]=True |
| 2 | C4 | FAIL | requires B2 through B5; B4 checks flatness through recovery |
| 3 | C1 | REJECT | high_ns=None; expected 500000 +/- 100000 |
| 3 | C2 | REJECT | trip delta=1 |

Rejected repetitions: 2
