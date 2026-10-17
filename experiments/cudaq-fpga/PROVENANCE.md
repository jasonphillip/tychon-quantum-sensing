# Publication provenance

This package records the October 17, 2026 FPGA replay of three frozen synthetic workloads.
Track protocols and metric files describe their original software runs.
Hardware receipts describe the later integrated board run.
Stage-specific fields in earlier receipts remain unchanged.

## File integrity

[evidence/manifest.json](evidence/manifest.json) hashes the published experiment files, excluding itself.
The verifier checks those hashes before checking the saved replay records.
Hashes detect differences from this published version. They are not an external signature or independent hardware attestation.

Original-to-public mappings are stored in:

- [Readout source map](readout/SOURCE_MAP.json)
- [NV source map](nv/SOURCE_MAP.json)
- [QEC source map](qec/SOURCE_MAP.json)
- [Board and integration source map](evidence/SOURCE_MAP.json)

Each map records relative source paths, original hashes, public hashes, and transformations.
Original paths describe the archived experiment layout, not a public download location.
Frozen numerical replay binaries and reference cores retain their original bytes.
Some historical commands replace private machine paths with portable placeholders.
Board CSV files use lossless gzip compression; decompression restores the original CSV bytes.
Curated board JSON retains result numbers while removing private machine addresses and paths.

The full execution archive remains separate from this public package.
Generated vendor IP, licensed design projects, raw vendor logs, executables, and local environments are not bundled here.
Large scientific arrays omitted from individual tracks are identified in their READMEs.
Historical hashes for omitted files document the original run; they do not imply those files are included.

## Evidence limits

All 17,165 frozen records were replayed ten times across two boots.
Repeated calls test implementation consistency; they do not increase the number of independent scientific observations.
The NV pack includes interface boundary cases. The QEC pack includes exhaustive syndrome words.
The readout pack includes raw and calibrated views of the same final shots.

Saved-evidence verification checks recorded bytes and consistency with reference arithmetic.
It does not repeat hardware execution, independently validate the physical models, or establish deployment readiness.
Failed scientific comparisons remain failed when their saved evidence verifies successfully.
