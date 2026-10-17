#include <stdint.h>

/* Host proof of the arithmetic kernel, not a synthesized FPGA implementation.
 * Input: signed 16-bit, 11 fractional bits. Weight: signed 16-bit, 14 fractional bits.
 * Bias and score have 25 fractional bits. Caller validates the coefficient bound.
 * 128 multiplies, 127 reduction adds plus bias. No allocation or floating point.
 */
int64_t readout_score(const int16_t *input, const int16_t *weight,
                      uint32_t count, int64_t bias) {
    int64_t score = bias;
    for (uint32_t k = 0; k < count; ++k) {
        score += (int64_t)input[k] * (int64_t)weight[k];
    }
    return score;
}
