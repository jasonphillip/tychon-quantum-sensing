# Reference Corpus

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

This repo has a dedicated reference corpus at `~/.corpus/polarfire-control-corpus/`. Search it with the `search-corpus` skill (e.g. `/search-corpus polarfire-control-corpus "<query>"`) BEFORE making any claims about:
- Microchip toolchain APIs (SmartHLS pragmas, ap_fixpt, Libero Tcl, PDC io.pdc/fp.pdc split)
- PolarFire SoC fabric details (FIC_0/1/2/3 capabilities, MSS memory map, AXI4-Lite slave behavior)
- CoreVectorBlox v2.0.1 IP (control register map, output_valid semantics, WSTRB rules)
- Synplify Pro message IDs (CL189, CL260, BN362, MO129, MO156, etc.) — the OEM Message Reference is in the corpus
- Lur'e / Circle Criterion / sector-bounded NN stability (Khalil, recent arxiv on NN-in-loop control)
- ODMR closed-loop frequency tracking (NV-center magnetometer literature, bandwidth/slew constraints)
- **VectorBlox V250 DEPLOYMENT (added 2026-06-02):** the CoreVectorBlox control-register bit-map (IP Handbook, `vectorblox-sdk-docs-bee/`), bare-metal vs Linux runtime (`vbx_cnn_api.c` dual-path), the supported Linux/Yocto/Icicle flow (`microchip-support/VBX_2.0.3_Icicle_porting_000017296.md`), `generic-uio`+`udmabuf` device-tree mechanism, HSS/U-Boot boot chain, PolarFire SoC fabric-master cache coherency (`CoreAXI4DMAController_HB` §1.10, `mpfs-memory-hierarchy`), and the CartPole/F1TENTH FPGA-control demo benchmark. Query e.g. `/search-corpus polarfire-control-corpus "VectorBlox udmabuf generic-uio bare-metal coherency"`.

Also includes two user-contributed deep-research syntheses on SmartHLS PID datapath survival in the MPFS_ICICLE_VectorBlox design at `raw/user-contributed/`. The NN/ODMR-physics deep-research (NN-over-PID drift prediction, FPGA frequency-locking, edge-ML magnetometry) is in the complementary `odmr-pnt-nv-docs` corpus (expanded 2026-06-02).

Do NOT rely on training data for these topics — the corpus has authoritative primary sources (Microchip user guides, vendor handbooks, peer-reviewed papers) that may contradict assumptions. The complementary `pow-rf` corpus covers the RF/SDR/anomaly-detection side.
