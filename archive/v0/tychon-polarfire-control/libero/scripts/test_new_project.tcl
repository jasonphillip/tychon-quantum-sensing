new_project \
    -location {~/tmp_libero_test} \
    -name {test_project} \
    -family {PolarFireSoC} \
    -die {MPFS250T} \
    -package {FCVG484} \
    -speed {STD} \
    -hdl {VERILOG}

puts "SUCCESS: Project created"
close_project
file delete -force {~/tmp_libero_test}
puts "Cleaned up"
