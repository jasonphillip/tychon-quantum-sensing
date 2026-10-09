# Watchdog fallback: c1

| Repetition | Criterion | Result | Evidence |
|---:|---|---|---|
| 1 | C1 | PASS | high_ns=533000; expected 500000 +/- 100000 |
| 1 | C2 | PASS | trip delta=1 |
| 1 | C3 | FAIL | flat_updates=0; actuator_tracking=True; timeout_low_at_starts=True |
| 2 | C1 | REJECT | high_ns=None; expected 500000 +/- 100000 |
| 2 | C2 | REJECT | trip delta=1 |

Rejected repetitions: 1
