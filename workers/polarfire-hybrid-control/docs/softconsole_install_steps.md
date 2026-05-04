# SoftConsole 2022.2 Install Instructions (Beelink)

The Microchip SoftConsole installer is gated behind Akamai/Microchip portal sign-in — direct `curl` returns HTTP 403, so we cannot fetch it headlessly. Manual install steps:

## What you're installing

**SoftConsole v2022.2-RISC-V (build 747)** — the latest release. Microchip has not shipped a newer version; "2025" branding only applies to Libero SoC and the MSS Configurator, not to SoftConsole itself.

- Filename: `Microchip-SoftConsole-v2022.2-RISC-V-747-windows-x64-installer.exe`
- Approximate size: ~1.5 GB
- License: free, click-through EULA on first install
- Bundled toolchain: `riscv-none-elf-gcc` (newlib bare-metal target) + `gdb` + Eclipse IDE + OpenOCD + reference linker scripts + mpfs_hal source tree

## Steps on the Beelink (Windows host, ~30–45 min)

1. In a browser on the Beelink, go to:
   **https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/soc-fpga/softconsole**

2. Click **"Download Software"** at the top of the page (or scroll to the SoftConsole v2022.2 section).

3. Click **"SoftConsole v2022.2 Download for Windows®"**. If prompted, sign in with your myMicrochip account (or create one — free, takes 2 min). Accept the EULA.

4. The installer (`Microchip-SoftConsole-v2022.2-RISC-V-747-windows-x64-installer.exe`) downloads to `~\Downloads\`.

5. Right-click the installer → **Run as administrator**. Default install location is `C:\Microchip\SoftConsole-v2022.2\`. Accept all defaults; the install populates:
   - `C:\Microchip\SoftConsole-v2022.2\riscv-unknown-elf-gcc\bin\` — toolchain (note: actual subdir name may differ slightly; verify after install)
   - `C:\Microchip\SoftConsole-v2022.2\eclipse\` — IDE
   - `C:\Microchip\SoftConsole-v2022.2\openocd\` — debugger backend

6. After install, verify from MSYS2/Git Bash:
   ```bash
   ssh bee 'find /c/Microchip/SoftConsole-v2022.2 -maxdepth 4 -name "riscv-none-elf-gcc*" 2>/dev/null'
   ssh bee '/c/Microchip/SoftConsole-v2022.2/riscv-unknown-elf-gcc/bin/riscv-none-elf-gcc.exe --version'
   ```
   Expected: prints GCC version (e.g., `riscv-none-elf-gcc (xPack GNU RISC-V Embedded GCC x86_64) 10.2.0` or similar).

7. (Optional but useful) Add the toolchain to `$PATH` for the `bee` user. Append to `~/.bashrc` on Beelink:
   ```bash
   export PATH="/c/Microchip/SoftConsole-v2022.2/riscv-unknown-elf-gcc/bin:$PATH"
   ```

## What this unlocks

After install, Part 3 of the demo-bringup plan (`~/.claude/plans/i-plugged-in-j11-optimized-quilt.md`) can build firmware via `make` against the Microchip-curated `mpfs_hal` source tree, link with the right RISC-V startup code and linker scripts, and load the resulting `.elf` to the Icicle Kit MSS over JTAG.

## Fallback if Microchip portal is down

`xPack RISC-V Embedded GCC` standalone via `npm install -g @xpack-dev-tools/riscv-none-elf-gcc` (~250 MB, no signup, Node.js already on Beelink). Trades the curated `mpfs_hal` + reference projects for raw toolchain only — Part 3 then needs to clone `polarfire-soc/polarfire-soc-bare-metal-library` from GitHub separately for the HAL.

---

**Open this file:** `~/projects/polarfire-hybrid-control/docs/softconsole_install_steps.md`
