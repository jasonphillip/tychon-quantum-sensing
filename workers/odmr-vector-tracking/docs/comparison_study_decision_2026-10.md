# Comparison study decision

Outcome: niche_to_confirm

Best classical: E3. Lowest clean-cell lost rate among E2/E3/E4: 0.442.

## Qualifying cells

- classical on realistic: angular improvement 100.67 deg, RMSE improvement 0.847, RMSE diff CI95 ['-5.256', '-4.723'] mT, AE p90 diff CI95 ['-105.05', '-94.08'] deg
- classical on realistic_linewidth_MHz_1p5: angular improvement 48.48 deg, RMSE improvement 0.851, RMSE diff CI95 ['-4.036', '-3.610'] mT, AE p90 diff CI95 ['-73.23', '-13.36'] deg
- classical on realistic_linewidth_MHz_3: angular improvement 122.34 deg, RMSE improvement 0.867, RMSE diff CI95 ['-4.652', '-4.214'] mT, AE p90 diff CI95 ['-140.85', '-81.96'] deg
- classical on realistic_linewidth_MHz_7: angular improvement 100.28 deg, RMSE improvement 0.853, RMSE diff CI95 ['-5.716', '-5.141'] mT, AE p90 diff CI95 ['-108.58', '-89.14'] deg
- classical on realistic_contrast_pct_3: angular improvement 105.26 deg, RMSE improvement 0.859, RMSE diff CI95 ['-6.268', '-5.736'] mT, AE p90 diff CI95 ['-111.24', '-101.72'] deg
- classical on realistic_snr_inf: angular improvement 109.85 deg, RMSE improvement 0.871, RMSE diff CI95 ['-5.358', '-4.890'] mT, AE p90 diff CI95 ['-145.92', '-99.52'] deg
- classical on realistic_snr_30: angular improvement 102.62 deg, RMSE improvement 0.837, RMSE diff CI95 ['-5.197', '-4.651'] mT, AE p90 diff CI95 ['-110.99', '-92.26'] deg
- classical on realistic_snr_3: angular improvement 95.54 deg, RMSE improvement 0.784, RMSE diff CI95 ['-4.984', '-4.397'] mT, AE p90 diff CI95 ['-101.24', '-89.85'] deg
- classical on realistic_baseline_slope_pct_minus2: angular improvement 35.12 deg, RMSE improvement 0.850, RMSE diff CI95 ['-5.308', '-4.694'] mT, AE p90 diff CI95 ['-71.84', '-27.99'] deg
- classical on realistic_frequency_offset_MHz_0: angular improvement 100.66 deg, RMSE improvement 0.840, RMSE diff CI95 ['-5.222', '-4.694'] mT, AE p90 diff CI95 ['-107.82', '-92.81'] deg
- classical on realistic_frequency_offset_MHz_minus0p3: angular improvement 101.70 deg, RMSE improvement 0.841, RMSE diff CI95 ['-5.225', '-4.696'] mT, AE p90 diff CI95 ['-142.49', '-92.80'] deg
- classical on extrapolation: angular improvement 49.92 deg, RMSE improvement 0.309, RMSE diff CI95 ['-1.144', '-0.850'] mT, AE p90 diff CI95 ['-63.78', '-31.39'] deg

## All cells (win tests)

| Cell | Test | win | ang impr deg | RMSE impr | RMSE CI95 | AE p90 CI95 |
|---|---|---|---|---|---|---|
| clean | classical_beats_E4 | False | -4.90 | 0.424 | ['-0.814', '-0.343'] | ['0.20', '44.08'] |
| clean | E4_beats_classical | False | 4.90 | -0.737 | ['0.343', '0.814'] | ['-44.08', '-0.20'] |
| realistic | classical_beats_E4 | True | 100.67 | 0.847 | ['-5.256', '-4.723'] | ['-105.05', '-94.08'] |
| realistic | E4_beats_classical | False | -100.67 | -5.516 | ['4.723', '5.256'] | ['94.08', '105.05'] |
| realistic_linewidth_MHz_1p5 | classical_beats_E4 | True | 48.48 | 0.851 | ['-4.036', '-3.610'] | ['-73.23', '-13.36'] |
| realistic_linewidth_MHz_1p5 | E4_beats_classical | False | -48.48 | -5.721 | ['3.610', '4.036'] | ['13.36', '73.23'] |
| realistic_linewidth_MHz_3 | classical_beats_E4 | True | 122.34 | 0.867 | ['-4.652', '-4.214'] | ['-140.85', '-81.96'] |
| realistic_linewidth_MHz_3 | E4_beats_classical | False | -122.34 | -6.513 | ['4.214', '4.652'] | ['81.96', '140.85'] |
| realistic_linewidth_MHz_7 | classical_beats_E4 | True | 100.28 | 0.853 | ['-5.716', '-5.141'] | ['-108.58', '-89.14'] |
| realistic_linewidth_MHz_7 | E4_beats_classical | False | -100.28 | -5.806 | ['5.141', '5.716'] | ['89.14', '108.58'] |
| realistic_contrast_pct_3 | classical_beats_E4 | True | 105.26 | 0.859 | ['-6.268', '-5.736'] | ['-111.24', '-101.72'] |
| realistic_contrast_pct_3 | E4_beats_classical | False | -105.26 | -6.082 | ['5.736', '6.268'] | ['101.72', '111.24'] |
| realistic_snr_inf | classical_beats_E4 | True | 109.85 | 0.871 | ['-5.358', '-4.890'] | ['-145.92', '-99.52'] |
| realistic_snr_inf | E4_beats_classical | False | -109.85 | -6.767 | ['4.890', '5.358'] | ['99.52', '145.92'] |
| realistic_snr_30 | classical_beats_E4 | True | 102.62 | 0.837 | ['-5.197', '-4.651'] | ['-110.99', '-92.26'] |
| realistic_snr_30 | E4_beats_classical | False | -102.62 | -5.154 | ['4.651', '5.197'] | ['92.26', '110.99'] |
| realistic_snr_3 | classical_beats_E4 | True | 95.54 | 0.784 | ['-4.984', '-4.397'] | ['-101.24', '-89.85'] |
| realistic_snr_3 | E4_beats_classical | False | -95.54 | -3.637 | ['4.397', '4.984'] | ['89.85', '101.24'] |
| realistic_baseline_slope_pct_0 | classical_beats_E4 | False | -39.60 | 0.456 | ['-0.910', '-0.474'] | ['-0.60', '42.89'] |
| realistic_baseline_slope_pct_0 | E4_beats_classical | False | 39.60 | -0.837 | ['0.474', '0.910'] | ['-42.89', '0.60'] |
| realistic_baseline_slope_pct_minus2 | classical_beats_E4 | True | 35.12 | 0.850 | ['-5.308', '-4.694'] | ['-71.84', '-27.99'] |
| realistic_baseline_slope_pct_minus2 | E4_beats_classical | False | -35.12 | -5.652 | ['4.694', '5.308'] | ['27.99', '71.84'] |
| realistic_frequency_offset_MHz_0 | classical_beats_E4 | True | 100.66 | 0.840 | ['-5.222', '-4.694'] | ['-107.82', '-92.81'] |
| realistic_frequency_offset_MHz_0 | E4_beats_classical | False | -100.66 | -5.240 | ['4.694', '5.222'] | ['92.81', '107.82'] |
| realistic_frequency_offset_MHz_minus0p3 | classical_beats_E4 | True | 101.70 | 0.841 | ['-5.225', '-4.696'] | ['-142.49', '-92.80'] |
| realistic_frequency_offset_MHz_minus0p3 | E4_beats_classical | False | -101.70 | -5.304 | ['4.696', '5.225'] | ['92.80', '142.49'] |
| extrapolation | classical_beats_E4 | True | 49.92 | 0.309 | ['-1.144', '-0.850'] | ['-63.78', '-31.39'] |
| extrapolation | E4_beats_classical | False | -49.92 | -0.448 | ['0.850', '1.144'] | ['31.39', '63.78'] |
