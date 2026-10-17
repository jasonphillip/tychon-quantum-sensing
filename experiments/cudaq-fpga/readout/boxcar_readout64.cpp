#include <stdint.h>

// Optimized form of the selected boxcar baseline. Assumes interleaved I,Q.
// 64 signed int16 values sum into int32 without overflow. The trained model's
// score bound is checked outside the core. No floating point or allocation.
extern "C" int64_t boxcar_readout64(const int16_t input[128],
                                   int16_t weight_i, int16_t weight_q,
                                   int64_t bias) {
    int32_t sum_i = 0;
    int32_t sum_q = 0;
    for (unsigned k = 0; k < 64; ++k) {
        sum_i += input[2*k];
        sum_q += input[2*k+1];
    }
    return bias + (int64_t)sum_i*weight_i + (int64_t)sum_q*weight_q;
}
