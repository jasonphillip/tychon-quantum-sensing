# 00_full_pipeline.tcl — Source 01..04 in one Libero session
# Used for a full project bring-up + synthesis + P&R from a fresh state.
puts "=== STAGE 1: scaffold project ==="
source [file join [file dirname [info script]] 01_scaffold_proj.tcl]
puts "=== STAGE 2: import IP ==="
source [file join [file dirname [info script]] 02_import_ip.tcl]
puts "=== STAGE 3: SmartDesign wiring ==="
source [file join [file dirname [info script]] 03_smartdesign.tcl]
puts "=== STAGE 4: synthesis + P&R + reports ==="
source [file join [file dirname [info script]] 04_synth_pnr.tcl]
puts "=== PIPELINE COMPLETE ==="
