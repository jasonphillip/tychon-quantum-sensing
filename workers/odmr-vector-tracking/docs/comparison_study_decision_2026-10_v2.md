# Comparison study decision

Outcome: niche_to_confirm

Best classical: E3. Lowest clean-cell lost rate among E2/E3/E4: 0.475.

## Qualifying cells

- classical on realistic: angular improvement 101.82 deg, RMSE improvement 0.841, RMSE diff CI95 ['-5.150', '-4.600'] mT, AE p90 diff CI95 ['-144.70', '-97.03'] deg
- classical on realistic_linewidth_MHz_1p5: angular improvement 52.96 deg, RMSE improvement 0.842, RMSE diff CI95 ['-3.990', '-3.533'] mT, AE p90 diff CI95 ['-69.92', '-11.10'] deg
- classical on realistic_linewidth_MHz_3: angular improvement 131.34 deg, RMSE improvement 0.904, RMSE diff CI95 ['-4.697', '-4.413'] mT, AE p90 diff CI95 ['-138.81', '-124.90'] deg
- classical on realistic_linewidth_MHz_7: angular improvement 102.54 deg, RMSE improvement 0.854, RMSE diff CI95 ['-5.615', '-5.108'] mT, AE p90 diff CI95 ['-149.27', '-97.95'] deg
- classical on realistic_contrast_pct_3: angular improvement 103.80 deg, RMSE improvement 0.850, RMSE diff CI95 ['-6.241', '-5.645'] mT, AE p90 diff CI95 ['-126.24', '-97.91'] deg
- classical on realistic_snr_inf: angular improvement 99.01 deg, RMSE improvement 0.814, RMSE diff CI95 ['-5.023', '-4.398'] mT, AE p90 diff CI95 ['-106.24', '-88.71'] deg
- classical on realistic_snr_30: angular improvement 100.15 deg, RMSE improvement 0.829, RMSE diff CI95 ['-5.087', '-4.513'] mT, AE p90 diff CI95 ['-140.74', '-91.84'] deg
- classical on realistic_snr_3: angular improvement 96.66 deg, RMSE improvement 0.800, RMSE diff CI95 ['-4.986', '-4.415'] mT, AE p90 diff CI95 ['-103.88', '-90.84'] deg
- classical on realistic_baseline_slope_pct_minus2: angular improvement 35.75 deg, RMSE improvement 0.840, RMSE diff CI95 ['-5.363', '-4.771'] mT, AE p90 diff CI95 ['-50.43', '-28.03'] deg
- classical on realistic_frequency_offset_MHz_0: angular improvement 99.91 deg, RMSE improvement 0.838, RMSE diff CI95 ['-5.153', '-4.570'] mT, AE p90 diff CI95 ['-146.41', '-92.66'] deg
- classical on realistic_frequency_offset_MHz_minus0p3: angular improvement 105.06 deg, RMSE improvement 0.851, RMSE diff CI95 ['-5.213', '-4.649'] mT, AE p90 diff CI95 ['-151.06', '-98.64'] deg
- classical on extrapolation: angular improvement 56.05 deg, RMSE improvement 0.316, RMSE diff CI95 ['-1.131', '-0.876'] mT, AE p90 diff CI95 ['-64.04', '-42.32'] deg

## All cells (win tests)

| Cell | Test | win | ang impr deg | RMSE impr | RMSE CI95 | AE p90 CI95 |
|---|---|---|---|---|---|---|
| clean | classical_beats_E4 | False | -46.41 | 0.246 | ['-0.598', '-0.049'] | ['5.94', '51.29'] |
| clean | E4_beats_classical | False | 46.41 | -0.325 | ['0.049', '0.598'] | ['-51.29', '-5.94'] |
| realistic | classical_beats_E4 | True | 101.82 | 0.841 | ['-5.150', '-4.600'] | ['-144.70', '-97.03'] |
| realistic | E4_beats_classical | False | -101.82 | -5.281 | ['4.600', '5.150'] | ['97.03', '144.70'] |
| realistic_linewidth_MHz_1p5 | classical_beats_E4 | True | 52.96 | 0.842 | ['-3.990', '-3.533'] | ['-69.92', '-11.10'] |
| realistic_linewidth_MHz_1p5 | E4_beats_classical | False | -52.96 | -5.314 | ['3.533', '3.990'] | ['11.10', '69.92'] |
| realistic_linewidth_MHz_3 | classical_beats_E4 | True | 131.34 | 0.904 | ['-4.697', '-4.413'] | ['-138.81', '-124.90'] |
| realistic_linewidth_MHz_3 | E4_beats_classical | False | -131.34 | -9.428 | ['4.413', '4.697'] | ['124.90', '138.81'] |
| realistic_linewidth_MHz_7 | classical_beats_E4 | True | 102.54 | 0.854 | ['-5.615', '-5.108'] | ['-149.27', '-97.95'] |
| realistic_linewidth_MHz_7 | E4_beats_classical | False | -102.54 | -5.868 | ['5.108', '5.615'] | ['97.95', '149.27'] |
| realistic_contrast_pct_3 | classical_beats_E4 | True | 103.80 | 0.850 | ['-6.241', '-5.645'] | ['-126.24', '-97.91'] |
| realistic_contrast_pct_3 | E4_beats_classical | False | -103.80 | -5.676 | ['5.645', '6.241'] | ['97.91', '126.24'] |
| realistic_snr_inf | classical_beats_E4 | True | 99.01 | 0.814 | ['-5.023', '-4.398'] | ['-106.24', '-88.71'] |
| realistic_snr_inf | E4_beats_classical | False | -99.01 | -4.388 | ['4.398', '5.023'] | ['88.71', '106.24'] |
| realistic_snr_30 | classical_beats_E4 | True | 100.15 | 0.829 | ['-5.087', '-4.513'] | ['-140.74', '-91.84'] |
| realistic_snr_30 | E4_beats_classical | False | -100.15 | -4.851 | ['4.513', '5.087'] | ['91.84', '140.74'] |
| realistic_snr_3 | classical_beats_E4 | True | 96.66 | 0.800 | ['-4.986', '-4.415'] | ['-103.88', '-90.84'] |
| realistic_snr_3 | E4_beats_classical | False | -96.66 | -4.000 | ['4.415', '4.986'] | ['90.84', '103.88'] |
| realistic_baseline_slope_pct_0 | classical_beats_E4 | False | -43.52 | 0.295 | ['-0.726', '-0.154'] | ['35.79', '52.29'] |
| realistic_baseline_slope_pct_0 | E4_beats_classical | False | 43.52 | -0.418 | ['0.154', '0.726'] | ['-52.29', '-35.79'] |
| realistic_baseline_slope_pct_minus2 | classical_beats_E4 | True | 35.75 | 0.840 | ['-5.363', '-4.771'] | ['-50.43', '-28.03'] |
| realistic_baseline_slope_pct_minus2 | E4_beats_classical | False | -35.75 | -5.241 | ['4.771', '5.363'] | ['28.03', '50.43'] |
| realistic_frequency_offset_MHz_0 | classical_beats_E4 | True | 99.91 | 0.838 | ['-5.153', '-4.570'] | ['-146.41', '-92.66'] |
| realistic_frequency_offset_MHz_0 | E4_beats_classical | False | -99.91 | -5.168 | ['4.570', '5.153'] | ['92.66', '146.41'] |
| realistic_frequency_offset_MHz_minus0p3 | classical_beats_E4 | True | 105.06 | 0.851 | ['-5.213', '-4.649'] | ['-151.06', '-98.64'] |
| realistic_frequency_offset_MHz_minus0p3 | E4_beats_classical | False | -105.06 | -5.713 | ['4.649', '5.213'] | ['98.64', '151.06'] |
| extrapolation | classical_beats_E4 | True | 56.05 | 0.316 | ['-1.131', '-0.876'] | ['-64.04', '-42.32'] |
| extrapolation | E4_beats_classical | False | -56.05 | -0.461 | ['0.876', '1.131'] | ['42.32', '64.04'] |
