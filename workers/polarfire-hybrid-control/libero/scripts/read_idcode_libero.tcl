#---------------------------------------------------------------------------
# read_idcode_libero.tcl  —  Libero Designer headless IDCODE capture
#
# Opens the seed_7 project and uses Libero Designer's Tcl read_id_code to
# obtain the raw 32-bit hex IDCODE from the silicon on the JTAG chain.
#
# Libero Designer Tcl is documented at
#   ww1.microchip.com/.../libero-soc-tcl-cmd-ref-ug-2025-2pdf.md
#---------------------------------------------------------------------------

puts "================================================================"
puts "Libero Designer headless IDCODE read"
puts "================================================================"
flush stdout

# --- open the seed_7 reference design project ---
set PRJX "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/MPFS_ICICLE_Vectorblox.prjx"
if {[catch {open_project -file $PRJX} err]} {
    # Try alternative seed_7 location
    set PRJX_ALT "~/libero_seedsweep/seed_7/MPFS_ICICLE_Vectorblox.prjx"
    puts "Trying alt: $PRJX_ALT"
    if {[catch {open_project -file $PRJX_ALT} err2]} {
        puts "FATAL: open_project failed: $err / $err2"
        flush stdout
        exit 91
    }
    set PRJX $PRJX_ALT
}
puts "OPENED: $PRJX"
flush stdout

# --- read IDCODE ---
if {[catch {set idcode [read_id_code]} err]} {
    puts "FATAL: read_id_code failed: $err"
    flush stdout
    exit 92
}

puts "================================================================"
puts "RAW IDCODE = $idcode"
puts "================================================================"
flush stdout

exit 0
