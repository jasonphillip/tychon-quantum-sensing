# Comparison study — val sanity run (2026-10-14)

Sanity only (protocol: val permits implementation checks); 6 sequences per cell, every estimator, one process per cell; **never cited as a result**. Purpose: no crash, no guard failure, finite outputs accounted for under Addendum (b). Outcome: 14 of 14 cells completed, 0 errors.

| cell | est | n | RMSE mean (mT) | angular p90-of-p90 (°) | lock | lost | nonfinite frames | latency median (µs) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| clean | E1 | 6 | 0.336 | 11.284 | 0.837 | 0.333 | 0 | 3990.079 |
| clean | E2 | 6 | 0.303 | 11.284 | 0.853 | 0.167 | 0 | 4063.456 |
| clean | E3 | 6 | 0.874 | 48.520 | 0.755 | 0.500 | 2 | 4732.664 |
| clean | E4 | 6 | 1.295 | 28.108 | 0.053 | 1.000 | 0 | 2299.555 |
| clean | E5 | 6 | 0.612 | 23.429 | 0.656 | 0.667 | 0 | 253.724 |
| extrapolation | E1 | 6 | 42.666 | 80.393 | 0.000 | 1.000 | 0 | 214311.548 |
| extrapolation | E2 | 6 | 43.866 | 88.626 | 0.000 | 1.000 | 0 | 699460.782 |
| extrapolation | E3 | 6 | 2.271 | 69.739 | 0.064 | 1.000 | 1147 | 17881.013 |
| extrapolation | E4 | 6 | 3.461 | 121.240 | 0.000 | 1.000 | 0 | 2035.838 |
| extrapolation | E5 | 6 | 25.763 | 111.548 | 0.003 | 1.000 | 0 | 545.831 |
| realistic | E1 | 6 | 39.498 | 75.893 | 0.007 | 1.000 | 0 | 220911.428 |
| realistic | E2 | 6 | 61.712 | 57.547 | 0.005 | 1.000 | 0 | 413613.033 |
| realistic | E3 | 6 | 0.539 | 18.950 | 0.757 | 0.500 | 81 | 5986.388 |
| realistic | E4 | 6 | 5.877 | 169.887 | 0.000 | 1.000 | 0 | 1997.253 |
| realistic | E5 | 6 | 14.685 | 51.777 | 0.102 | 0.833 | 0 | 707.918 |
| realistic_baseline_slope_pct_0 | E1 | 6 | 2.768 | 81.465 | 0.543 | 0.667 | 0 | 10738.887 |
| realistic_baseline_slope_pct_0 | E2 | 6 | 1.775 | 87.633 | 0.548 | 0.667 | 0 | 8897.160 |
| realistic_baseline_slope_pct_0 | E3 | 6 | 0.603 | 44.814 | 0.745 | 0.500 | 196 | 6354.354 |
| realistic_baseline_slope_pct_0 | E4 | 6 | 1.327 | 22.540 | 0.035 | 1.000 | 0 | 2221.776 |
| realistic_baseline_slope_pct_0 | E5 | 6 | 1.454 | 31.009 | 0.067 | 1.000 | 0 | 316.394 |
| realistic_baseline_slope_pct_minus2 | E1 | 6 | 136.066 | 78.123 | 0.004 | 1.000 | 0 | 211659.176 |
| realistic_baseline_slope_pct_minus2 | E2 | 6 | 23.117 | 72.311 | 0.004 | 1.000 | 0 | 277907.874 |
| realistic_baseline_slope_pct_minus2 | E3 | 6 | 0.909 | 36.373 | 0.701 | 0.500 | 203 | 6265.287 |
| realistic_baseline_slope_pct_minus2 | E4 | 6 | 5.288 | 98.622 | 0.000 | 1.000 | 0 | 2351.416 |
| realistic_baseline_slope_pct_minus2 | E5 | 6 | 1.585 | 22.665 | 0.227 | 0.667 | 0 | 674.139 |
| realistic_contrast_pct_3 | E1 | 6 | 75.004 | 69.695 | 0.421 | 0.833 | 0 | 15460.778 |
| realistic_contrast_pct_3 | E2 | 6 | 22.156 | 56.897 | 0.455 | 0.667 | 0 | 28698.263 |
| realistic_contrast_pct_3 | E3 | 6 | 0.837 | 42.092 | 0.701 | 0.500 | 298 | 2156.793 |
| realistic_contrast_pct_3 | E4 | 6 | 6.778 | 174.916 | 0.000 | 1.000 | 0 | 478.241 |
| realistic_contrast_pct_3 | E5 | 6 | 16.561 | 59.585 | 0.037 | 1.000 | 0 | 103.400 |
| realistic_frequency_offset_MHz_0 | E1 | 6 | 145.134 | 68.732 | 0.006 | 1.000 | 0 | 76851.388 |
| realistic_frequency_offset_MHz_0 | E2 | 6 | 135.956 | 67.340 | 0.016 | 1.000 | 0 | 105371.895 |
| realistic_frequency_offset_MHz_0 | E3 | 6 | 0.727 | 44.207 | 0.864 | 0.333 | 97 | 2120.713 |
| realistic_frequency_offset_MHz_0 | E4 | 6 | 5.891 | 170.635 | 0.000 | 1.000 | 0 | 483.225 |
| realistic_frequency_offset_MHz_0 | E5 | 6 | 10.548 | 64.637 | 0.061 | 0.833 | 0 | 296.443 |
| realistic_frequency_offset_MHz_minus0p3 | E1 | 6 | 185.457 | 90.514 | 0.004 | 1.000 | 0 | 59227.718 |
| realistic_frequency_offset_MHz_minus0p3 | E2 | 6 | 40.831 | 84.207 | 0.005 | 1.000 | 0 | 102219.107 |
| realistic_frequency_offset_MHz_minus0p3 | E3 | 6 | 0.806 | 45.407 | 0.808 | 0.333 | 150 | 2135.337 |
| realistic_frequency_offset_MHz_minus0p3 | E4 | 6 | 5.899 | 170.635 | 0.000 | 1.000 | 0 | 482.010 |
| realistic_frequency_offset_MHz_minus0p3 | E5 | 6 | 11.581 | 65.626 | 0.044 | 1.000 | 0 | 298.043 |
| realistic_linewidth_MHz_1p5 | E1 | 6 | 53.759 | 52.391 | 0.010 | 1.000 | 0 | 48739.679 |
| realistic_linewidth_MHz_1p5 | E2 | 6 | 62.081 | 72.118 | 0.014 | 1.000 | 0 | 56064.983 |
| realistic_linewidth_MHz_1p5 | E3 | 6 | 0.684 | 42.699 | 0.742 | 0.500 | 20 | 2698.039 |
| realistic_linewidth_MHz_1p5 | E4 | 6 | 4.389 | 88.159 | 0.000 | 1.000 | 0 | 475.612 |
| realistic_linewidth_MHz_1p5 | E5 | 6 | 1.203 | 22.088 | 0.357 | 1.000 | 0 | 308.075 |
| realistic_linewidth_MHz_3 | E1 | 6 | 62.367 | 100.853 | 0.006 | 1.000 | 0 | 78391.565 |
| realistic_linewidth_MHz_3 | E2 | 6 | 68.834 | 118.287 | 0.007 | 1.000 | 0 | 105627.714 |
| realistic_linewidth_MHz_3 | E3 | 6 | 0.616 | 44.535 | 0.898 | 0.500 | 111 | 2138.473 |
| realistic_linewidth_MHz_3 | E4 | 6 | 5.160 | 157.950 | 0.000 | 1.000 | 0 | 482.232 |
| realistic_linewidth_MHz_3 | E5 | 6 | 7.612 | 42.491 | 0.170 | 1.000 | 0 | 289.989 |
| realistic_linewidth_MHz_7 | E1 | 6 | 47.429 | 134.361 | 0.005 | 1.000 | 0 | 126375.405 |
| realistic_linewidth_MHz_7 | E2 | 6 | 172.434 | 62.688 | 0.090 | 1.000 | 0 | 591505.354 |
| realistic_linewidth_MHz_7 | E3 | 6 | 0.584 | 42.626 | 0.834 | 0.500 | 145 | 5693.945 |
| realistic_linewidth_MHz_7 | E4 | 6 | 6.313 | 174.114 | 0.000 | 1.000 | 0 | 1910.574 |
| realistic_linewidth_MHz_7 | E5 | 6 | 2.383 | 41.360 | 0.093 | 0.833 | 0 | 703.011 |
| realistic_snr_3 | E1 | 6 | 170.615 | 74.772 | 0.001 | 1.000 | 0 | 76845.540 |
| realistic_snr_3 | E2 | 6 | 90.076 | 89.862 | 0.003 | 1.000 | 0 | 205438.924 |
| realistic_snr_3 | E3 | 6 | 0.974 | 38.526 | 0.656 | 0.833 | 270 | 9480.808 |
| realistic_snr_3 | E4 | 6 | 5.903 | 172.464 | 0.000 | 1.000 | 0 | 1954.827 |
| realistic_snr_3 | E5 | 6 | 12.136 | 63.120 | 0.060 | 1.000 | 0 | 834.997 |
| realistic_snr_30 | E1 | 6 | 46.248 | 132.875 | 0.005 | 1.000 | 0 | 229863.358 |
| realistic_snr_30 | E2 | 6 | 45.016 | 111.890 | 0.010 | 1.000 | 0 | 682893.383 |
| realistic_snr_30 | E3 | 6 | 1.812 | 76.011 | 0.735 | 0.500 | 69 | 5008.137 |
| realistic_snr_30 | E4 | 6 | 5.867 | 169.980 | 0.000 | 1.000 | 0 | 1838.152 |
| realistic_snr_30 | E5 | 6 | 1.677 | 22.921 | 0.077 | 1.000 | 0 | 567.782 |
| realistic_snr_inf | E1 | 6 | 118.752 | 151.749 | 0.005 | 1.000 | 0 | 52116.413 |
| realistic_snr_inf | E2 | 6 | 84.933 | 54.263 | 0.006 | 1.000 | 0 | 52940.522 |
| realistic_snr_inf | E3 | 6 | 0.825 | 48.419 | 0.764 | 0.500 | 0 | 4724.527 |
| realistic_snr_inf | E4 | 6 | 5.863 | 169.991 | 0.000 | 1.000 | 0 | 2434.022 |
| realistic_snr_inf | E5 | 6 | 0.623 | 13.807 | 0.429 | 1.000 | 0 | 249.240 |

Generated 2026-10-15T00:41+00:00 from `.scratch/task7-val-sanity/*/results.json` (not committed).
