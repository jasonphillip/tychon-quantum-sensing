# Audit-007 — Soft-Narrative Verification (Final Report v3.4)

**Date.** 2026-05-03
**Driver.** Five soft-narrative items (L1–L5) carried over from the second-opinion review of `Tychon_Phase_I_Final_Report_v3.4_2026-05-03.md`.
**TVW role.** Orchestrator (web-enabled retrieval; LLM critic inference not invoked under air-gap rule — none required for citation lookups).
**Pre-flight.** Edits applied to canonical `.md` at `~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/final_report/`; not via TVW symlink.

## Summary

| # | Item | Outcome | Evidence | Action taken |
|---|------|---------|----------|--------------|
| L1 | 9.4 pT/√Hz attribution + ref [2] author list | **Resolved with substantive correction** | Brave + arXiv 1406.5235 + Lincoln Lab page | Rewrote §2.1 line 54; replaced ref [2] author list (Pham→Clevenson); removed AUDIT FLAG |
| L2 | SBQuantum thermal/heading numbers | **Verified — no edit needed** | Halde abstract + Table p.286 | None; §5.2 wording is accurate |
| L3 | Stürner 18 pT/√Hz claim | **Resolved with substantive correction** | 3 independent sources (Wiley, Frontiers, arXiv) | Replaced "18 pT/√Hz" with "approximately 344 pT/√Hz" in §2.1 |
| L4 | "55 unit tests" claim | **Resolved with update** | `pytest -q` in `~/projects/nv-sensor-sim` | Updated §5.1 count from 55 → 99 (full suite green) |
| L5 | Capability Brief defect sweep | **Clean — zero hits across all five strings** | grep | No edits required |

**Resolved:** 5/5. **Items requiring deferral:** 0. **New corpus chunks added:** 0 (all evidence drawn from the existing tychon-docs corpus + WebFetch + Brave web search).

---

## L1 — 9.4 pT/√Hz attribution and ref [2] author-list correction

### Findings

The v3.3 audit flag (preserved into v3.4) asked which paper reports the precise 9.4 pT/√Hz figure: Pham et al. 2015 (Nature Physics 11, 393) or Wolf et al. 2015 (Phys. Rev. X 5, 041001). Triangulated retrieval found:

1. **Wolf et al. 2015 (Phys. Rev. X 5, 041001 / arXiv:1411.6553)** — abstract reports a photon-shot-noise-limited sensitivity of **0.9 pT/√Hz** (sub-pT regime). The string "9.4 pT/√Hz" does not appear in the abstract.
2. **Nature Physics 11, 393 (2015), DOI 10.1038/nphys3291 / arXiv:1406.5235** — the title and DOI match the report's existing ref [2], but the **actual authors are Clevenson, Trusheim, Teale, Schröder, Braje, Englund** (6 authors), *not* the 12-author Pham roster currently printed in ref [2]. The Pham 12-author list belongs to a different Pham et al. paper, "Magnetic field imaging with nitrogen-vacancy ensembles" (~100 nT/√Hz). Verified on arXiv abstract page (1406.5235), MIT Lincoln Laboratory publication page, and Brave web search.
3. **Clevenson 2015 abstract** — headline broadband sensitivity is **~1 nT/√Hz over 0.1–10 Hz**, with a spin-projection limit at ~0.36 fT/√Hz. The figure 9.4 pT/√Hz does not appear in the Clevenson abstract.

The 9.4 pT/√Hz number, in the form previously printed in v3.3, is unsupported by any of the three candidate papers as a *headline* sensitivity claim, and was inherited as a stale fragment from an earlier reference-shuffling pass.

### Edit applied

**§2.1 line 54** — replaced the entire compound claim and removed the AUDIT FLAG:

> with demonstrated portable, fully-integrated room-temperature sensitivities of approximately 344 pT/√Hz [Stürner et al., 2021; ref [1]] and broadband DC magnetometry approaching the nT/√Hz level over the 0.1–10 Hz band in light-trapping diamond waveguide geometries [Clevenson et al., 2015; ref [2]].

**Bibliography ref [2]** — replaced the Pham author list with the actual Clevenson author list and added a parenthetical about the v3.3 mismatch:

> [2] H. Clevenson, M. E. Trusheim, C. Teale, T. Schröder, D. Braje, and D. Englund, "Broadband magnetometry and temperature sensing with a light-trapping diamond waveguide," *Nature Physics*, vol. 11, no. 5, pp. 393–397, 2015. doi: 10.1038/nphys3291. (Reports ~1 nT/√Hz broadband DC sensitivity over 0.1–10 Hz; corrects the v3.3 author-list mismatch — prior printing erroneously listed the Pham et al. 2011 "Magnetic field imaging" author roster against this paper's title and DOI.)

### Confidence

**HIGH.** Three independent sources (arXiv abstract page, MIT Lincoln Laboratory publications page, Brave web index) converge on the 6-author Clevenson identification and the 1 nT/√Hz figure.

---

## L2 — SBQuantum (Halde 2025) thermal qualification + heading error

### Findings

Direct grep against the in-corpus markdown extraction of `halde-2025-arxiv-2509.19179.pdf` (SHA-256 `cbe1d464…`) confirms every figure cited in §5.2:

- Abstract (line 11–12): "vector sensitivity of approximately 400 pT/√Hz, heading errors below 5 nT in Earth's field"
- Test table (line 286–289):
  - High Temperature: 125 °C for 335 hours
  - Low Temperature: −65 °C for 335 hours
  - Temperature cycling: 335 cycles −40 to 80 °C

§5.2 wording ("−65 °C to +125 °C for 335+ hours, ~400 pT/√Hz vector sensitivity sustained, heading errors below 5 nT [arXiv:2509.19179, 2025]") is verbatim-grounded in the paper.

### Edit applied

None required.

### Confidence

**HIGH.**

---

## L3 — Stürner 2021 sensitivity figure

### Findings

Three independent sources converge on **344 pT/√Hz** as the headline sensitivity:

1. Wiley abstract (Adv. Quantum Technol. 4, 2000111, doi 10.1002/qute.202000111): "This portable setup yields a sensitivity of ≈344 pT Hz⁻¹ᐟ²."
2. Frontiers in Photonics review (Fiberized Diamond-Based Vector Magnetometers, 2021): "The sensor constructed by Bosch achieved a sensitivity of 0.34 nT/√Hz" attributed to Stürner et al. 2021.
3. arXiv preprint 2012.01053 abstract: "sensitivity of 344 pT/SqrtHz".

The values "18 pT/√Hz" (in v3.4 as printed) and the alternate "28 pT/√Hz" suggested by second-opinion both fail to match any quoted figure from this paper. The closest sub-100-pT figure mentioned in the broader literature surrounding Stürner 2021 is the photon-shot-noise limit (~11 pT/√Hz on the Mainz fiber sensor), but that is *not* the headline measured sensitivity for the integrated portable prototype.

### Edit applied

**§2.1 line 54** — replaced "18 pT/√Hz" with "approximately 344 pT/√Hz" (folded into the L1 rewrite above).

### Confidence

**HIGH.** Three independent sources, including the canonical journal of record.

---

## L4 — Test count for `nv-sensor-sim`

### Findings

```
$ cd ~/projects/nv-sensor-sim && pytest -q
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 2.91s
```

Actual count is **99 passing tests**, not 55. Zero failures. Suite ran in 2.91 s.

### Edit applied

**§5.1** (line 185 area) — updated wording:

> 99 unit tests on the Repo 1 (`nv-sensor-sim`) generator pass (full suite green; verified `pytest -q` 2026-05-03), including end-to-end validation of analytical-vs-numerical path consistency and units-dictionary integrity in the dataset manifest.

§5.3 had no separate "55 tests" mention; only the §5.1 line carried the stale figure. Confirmed via `grep -nE "55 (unit )?tests?" report.md` → no remaining hits.

### Confidence

**HIGH.** Full test suite ran green on the current `nv-sensor-sim` HEAD.

---

## L5 — Capability Brief defect sweep

### Findings

```
=== FCSG536 ===           (no hits)
=== doubles ===           (no hits)
=== Gemini Deep Think === (no hits)
=== reference pending === (no hits)
=== CITATION NEEDED ===   (no hits)
```

All five sentinel strings return zero hits in `Tychon_Capability_Brief_2026-05-03.md`. Brief is clean.

### Edit applied

None.

### Confidence

**HIGH.**

---

## Render

- Rendered `.docx`: `~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/final_report/Tychon_Phase_I_Final_Report_v3.4_2026-05-03.docx` (62,475 bytes; pandoc warnings on `media/image1.png` and `media/image2.png` are pre-existing and benign — placeholder image text inserted by pandoc).
- Render command: `bash ~/projects/tychon-verification-workbench/tvw/scripts/render_report.sh ~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/final_report/Tychon_Phase_I_Final_Report_v3.4_2026-05-03.md`

## Items the parent session may want to escalate

- **L1 author-list correction is non-trivial.** Editor of record may wish to spot-check the Clevenson 2015 author order against the published Nature Physics issue to ensure authoritative ordering (Clevenson, Trusheim, Teale, Schröder, Braje, Englund — sourced from arXiv preprint and Lincoln Lab page). The arXiv author order may differ slightly from the print version's ordering of Teale and Schröder; current bibliography uses the form most commonly cited in the secondary literature.
- **L1 also corrected a real bibliographic defect** that was independent of the audit-flag question: the Pham 12-author list was attached to the Clevenson title and DOI in v3.3 and v3.4. This correction should be carried forward into any v3.5 revision.
- **L3 reframes a quantitative claim.** The pre-correction "18 pT/√Hz" overstated Stürner 2021's reported sensitivity by ~19×. The corrected "344 pT/√Hz" is conservatively grounded; if the editor wants a sub-100-pT NV literature anchor for §2.1, the Wolf et al. 2015 PRX paper (0.9 pT/√Hz photon-shot-noise-limited) is the closest peer-reviewed candidate and would need a new bibliography entry.
- **L4 updates a verifiable figure** with a fresh `pytest -q` run on HEAD; future report revisions should re-verify if `nv-sensor-sim` test suite changes.
