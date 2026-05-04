puts "==> JOBRESTORE: starting"
flush stdout
if {[catch {restore_project -file "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/MPFS_ICICLE_KIT_BASE_DESIGN_2023_02.job" -dir "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox_d2c"} err]} {
    puts "==> JOBRESTORE: ERROR: "
    flush stdout
    exit 1
}
puts "==> JOBRESTORE: success"
flush stdout
close_project
puts "==> JOBRESTORE: closed"
flush stdout
exit 0
