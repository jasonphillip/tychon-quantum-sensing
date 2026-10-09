# Safety Architecture

Formal framing of the bounded hybrid Simplex RTA using Lur'e/Circle Criterion
absolute stability theory. Reference: Platform Addendum v4, Section 3.

The AI feedforward path is treated as a sector-bounded nonlinearity phi(y,t)
within a Lur'e system. The Circle Criterion provides sufficient conditions for
absolute stability when:
- The AI output is bounded by sector clamps (±5% of actuator range)
- The slew rate is bounded (du_AI/dt per cycle)
- The classical PID loop is asymptotically stable independently

See `hls/src/safety_clamps.cpp` for the hardware implementation of these bounds.
