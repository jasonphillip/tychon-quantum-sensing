# Frozen noisy-round experiment

Prepared 2026-10-17 before final Monte Carlo generation.

Retain the original [[9,1,3]] support lists, logical operators, 256-entry correction table, core, and ABI.
Generate new streams for 3, 5, and 9 noisy rounds and four predeclared data/measurement probability pairs.
Run 20,000 trials per cell. No sample or result may select a new decoder, threshold, or parameter.

Each round first applies independent depolarizing data errors, then records all eight commuting stabilizer measurements.
Recorded measurement bits independently flip with probability q. There are no faulty extraction gates.
Errors accumulate; no correction is applied between rounds. The final correction is a Pauli-frame update.
Initial state is in the code space with no syndrome defects.

Online candidates compress the R noisy records into eight bits: either the last record or per-bit majority.
R is odd, so majority has no ties. Both feed the unchanged frozen table.
Majority is a deliberately simple candidate. It can miss late data errors and is not a fault-tolerant decoder.

For offline evaluation, append one perfect terminal syndrome with no further data error.
The final-perfect table control and PyMatching both receive this extra information.
Do not attribute their advantage over online candidates solely to the decoder algorithm.

The PyMatching reference builds a space-time graph from the explicit code checks.
Each data-bit fault creates spatial detection events in its round.
Each measurement-bit fault connects the corresponding check at consecutive times, including the perfect closing boundary.
No spatial errors are allowed between the last noisy record and the perfect terminal record.
X and Z sectors are decoded separately with marginal data probability 2p/3 and measurement probability q.
This ignores X/Z correlation from Y errors. It is a standard separate-sector MWPM baseline, not joint maximum likelihood.

Return corrections on the nine data qubits. Score the residual by explicit stabilizer-group membership.
Report remaining nonzero syndrome and zero-syndrome logical failure separately. Do not call every unresolved syndrome a logical flip.
Include Wilson binomial intervals. There is no monotonicity or superiority acceptance gate.

Before final evaluation, check no-error streams, all 27 single-qubit Pauli errors at each insertion round,
all single measurement faults, explicit detector-graph mapping, and deterministic majority failure on a late error.
Use Stim's independent tableau simulator to verify full ideal syndrome trajectories and both logical bases.
Stim does not supply these Monte Carlo streams; the Pauli sampler is a classical phenomenological generator.

Export the first 128 predeclared trials per cell for each compressed-table mode, plus all 256 syndrome words.
Export one-byte syndrome inputs and little-endian uint32 correction words with hashes and case provenance.
The exported algorithm failures remain in the package; matching the core reference does not mean physical correction succeeded.

Sources:

- PyMatching overview: https://pymatching.readthedocs.io/en/stable/
- PyMatching noisy-syndrome construction: https://pymatching.readthedocs.io/en/stable/toric-code-example.html#noisy-syndromes
- Stim gates and measurement definitions: https://github.com/quantumlib/Stim/blob/main/doc/gates.md

Use an isolated environment for optional dependencies. Keep the original decoder and frozen inputs unchanged.
The original CPU run budget was four threads, four GiB, and five minutes.
