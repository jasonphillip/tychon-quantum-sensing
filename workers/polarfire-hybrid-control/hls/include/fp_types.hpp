#ifndef FP_TYPES_HPP
#define FP_TYPES_HPP

#include <hls/ap_fixpt.hpp>

// DO NOT use ap_fixed<W,I> — that is Xilinx Vivado/Vitis HLS
// SmartHLS uses hls::ap_fixpt<W,I> where W = total bits, I = integer bits

typedef hls::ap_fixpt<64, 34> freq_t; // Q34.30: 34 integer bits, 30 fractional
typedef hls::ap_fixpt<32, 16> gain_t; // Q16.16: 16 integer bits, 16 fractional
typedef hls::ap_fixpt<32, 16> out_t;  // Q16.16: matches gain_t for DAC interface

#endif // FP_TYPES_HPP
