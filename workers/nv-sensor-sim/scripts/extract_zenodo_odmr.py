"""Extract 1D CW-ODMR spectra from Zenodo wide-field FITS files.

Reads 4D FITS files (x, y, freq_steps, scans) from the Zenodo ODMR dataset,
averages over spatial dimensions and scan repetitions, and writes each file
as a CSV with (frequency_Hz, pl_signal) columns suitable for
load_experimental_odmr().

Raw data location: pass --input-dir to specify (not in repo).
FITS structure: 1280x1024 pixels x 200 freq steps x 5 scans
Frequency sweep: 2700-3000 MHz in 1.5 MHz steps
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

FITS_DIR_DEFAULT = Path(".")  # Override with --input-dir
OUTPUT_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "experimental" / "zenodo_odmr"


def read_fits_header_value(header_bytes: bytes, keyword: str) -> str | None:
    """Extract a value from raw FITS header bytes."""
    for i in range(0, len(header_bytes), 80):
        card = header_bytes[i:i + 80].decode("ascii", errors="replace")
        if card[:8].strip() == keyword and "=" in card:
            val = card[10:30].split("/")[0].strip()
            return val
    return None


def extract_spectrum(fits_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Extract spatially-averaged 1D ODMR spectrum from a wide-field FITS file.

    Parameters
    ----------
    fits_path : Path
        Path to a FITS file.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (frequency_Hz, pl_signal) where frequency is in Hz.
    """
    try:
        from astropy.io import fits

        with fits.open(fits_path, memmap=False) as hdul:
            data = hdul[0].data  # shape: (nscans, nfreq, ny, nx)
            header = hdul[0].header
            start_mhz = float(header["STARFREQ"])
            stop_mhz = float(header["STOPFREQ"])
            nfreq = int(header["NAXIS3"])
    except ImportError:
        # Fallback: raw numpy FITS reading
        with open(fits_path, "rb") as f:
            header_bytes = f.read(2880)
            start_mhz = float(read_fits_header_value(header_bytes, "STARFREQ"))
            stop_mhz = float(read_fits_header_value(header_bytes, "STOPFREQ"))
            nfreq = int(read_fits_header_value(header_bytes, "NAXIS3"))
            nx = int(read_fits_header_value(header_bytes, "NAXIS1"))
            ny = int(read_fits_header_value(header_bytes, "NAXIS2"))
            nscans = int(read_fits_header_value(header_bytes, "NAXIS4"))
            bzero = float(read_fits_header_value(header_bytes, "BZERO") or 0)

            # Skip header, read data
            # FITS stores data big-endian, BITPIX=16 -> int16
            data = np.fromfile(f, dtype=">i2", count=nscans * nfreq * ny * nx)
            data = data.reshape(nscans, nfreq, ny, nx).astype(np.float64) + bzero

    # Average over spatial dims (nx, ny) and scans
    # data shape from astropy: (nscans, nfreq, ny, nx)
    spectrum = data.mean(axis=(0, 2, 3))  # -> (nfreq,)

    freq_hz = np.linspace(start_mhz * 1e6, stop_mhz * 1e6, nfreq)
    return freq_hz, spectrum


def main():
    parser = argparse.ArgumentParser(description="Extract 1D ODMR from Zenodo FITS")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=FITS_DIR_DEFAULT,
        help="Directory containing f*.fits files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR_DEFAULT,
        help="Output directory for CSV files",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    fits_files = sorted(args.input_dir.glob("f[0-9]*.fits"))
    if not fits_files:
        print(f"No FITS files found in {args.input_dir}")
        return

    print(f"Found {len(fits_files)} FITS files in {args.input_dir}")

    for fpath in fits_files:
        stem = fpath.stem
        out_csv = args.output_dir / f"{stem}_odmr.csv"
        print(f"  Extracting {fpath.name} -> {out_csv.name} ...", end=" ", flush=True)
        freq_hz, signal = extract_spectrum(fpath)
        np.savetxt(
            out_csv,
            np.column_stack([freq_hz, signal]),
            delimiter=",",
            header="frequency_Hz,pl_signal",
            comments="",
            fmt="%.6f",
        )
        print("done")

    print(f"\nWrote {len(fits_files)} CSV files to {args.output_dir}")


if __name__ == "__main__":
    main()
