# Experimental data provenance

## zenodo_odmr/ — the 25-spectrum reference set

Source: Zenodo record 10.5281/zenodo.7233869 — "Data from article: 'Wide-field
magnetometry using nitrogen-vacancy color centers with randomly oriented
micro-diamonds'" (Sengottuvel, Mrózek, Sawczak et al., *Sci Rep* 12:17997, 2022,
paper DOI 10.1038/s41598-022-22610-5). License: CC-BY-4.0.

Identification evidence (TVW external sweep, 2026-08-28):
- The record holds 25 files `f0.fits`…`f24.fits`; this directory holds the matching
  `f0_odmr.csv`…`f24_odmr.csv` extractions (see `scripts/extract_zenodo_odmr.py`).
- FITS headers read from the Zenodo API: STARTFREQ 2700 MHz, STOPFREQ 3000 MHz,
  STEPSIZE 1.5 MHz (nominal), NSCANS 5 — matching this set's sweep geometry. Note:
  the extracted CSVs hold 200 inclusive points over 2700–3000 MHz, so the actual
  grid spacing is 300/199 ≈ 1.5075 MHz; the header's 1.5 is the nominal step.
- Per-file size 2,621,445,120 bytes ≈ 1280×1024×200×5 px × 2 B + FITS header
  overhead, independently confirming the spatial dimensions (this one leg is
  arithmetic inference; all other legs are direct metadata reads).

A near-identical record `zenodo.7233868` exists (concept-DOI artifact of the same
deposit, not separately investigated).

## External sets added 2026-08-28 (gitignored; loaders in src/nv_sensor_sim/datasets/)

| Directory | Source | License |
|---|---|---|
| borealis_sbquantum_DRTLGW/ | Borealis (SBQuantum) doi:10.5683/SP3/DRTLGW — real NV vector-magnetometry B-field rotation sweep, 271 files | CC BY-SA 4.0 |
| zenodo_ml_scan_7481960/ | zenodo.org/records/7481960 — experimental NV ODMR scans for ML training | CC BY 4.0 |
| zenodo_zerofield_10629041/ | zenodo.org/records/10629041 — zero-field ODMR strain mapping, 47 positions | CC BY 4.0 |
| harvard_lowfield_6TFFPG/ | Harvard Dataverse doi:10.7910/DVN/6TFFPG — ODMR-like PL spectra at 0.5/1 mT, sim-vs-exp files | CC0 1.0 |
| darus_gradiometry_2817/ | DaRUS doi:10.18419/DARUS-2817 — subpicotesla DC magnetometry/gradiometry figure data | CC BY 4.0 |

Each directory retains its repository metadata as `_zenodo_metadata.json` /
`_dataverse_metadata.json`. Raw data is not committed; re-download via the
repository APIs using the DOIs above.
