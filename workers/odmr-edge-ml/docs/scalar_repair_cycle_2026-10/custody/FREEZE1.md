# FREEZE1 — coordinator gate for the scalar repair validation partition

freeze_receipt_sha256: 2abda4c9f48850236ef46ba39b1b0dfa94621151fc2759e90fb6ab1d237dbeac

- Source freeze: `freeze1.json` (stage 1, schema 1), sealed read-only by the executor at 2026-10-15 11:29 EDT.
- Verified by the coordinator (Claude f368afc3) at 2026-10-15 11:30 EDT with a metadata-only check (no held-out payload exists or was opened):
  - source_commit `c6229d52279af38792023de48ec0747d93d720bb` = the evaluator worktree HEAD, tracked tree clean;
  - 16 source hashes = committed bytes = disk; protocol_sha256 = committed `experiments/scalar_repair_cycle/PROTOCOL.md`;
  - development_manifest_sha256 = accepted dev r2 `63ef0c87e56294d657d5550fe71b7cd97e03c771f8de6c43cc30e58b4d61d2e1`; data_contract = the evaluator's data_contract(dev r2 manifest); data_contract.generator_sha256 = committed custody generator `082f2bdd…` (odmr-edge-ml `portfolio/s4-scalar-data`);
  - model_records = the three frozen C_direct seeds (42, 20261014, 20261015) and their checkpoint/export files match the recorded hashes;
  - bootstrap_seed 202610152001 (analysis namespace, disjoint from data seeds); claim_route accuracy; primary implementation int8;
  - evaluation_root `…/scalar-repair-cycle-2026-10-15/evaluation` holds no val/final results or access markers.
- Authorizes: one generation of the `val` partition (master 202610161, 512 fields × 7 conditions) by the custodian, sealed read-only, then one exclusive val access receipt and release for the evaluator. Does not authorize final.
