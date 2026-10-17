#include <stdint.h>

// Fixed-size synthesis candidate. Host execution is the only current proof.
// No vendor pragmas: scheduling and interfaces belong to the FPGA owner.
extern "C" int64_t readout_score128(const int16_t input[128],
                                    const int16_t weight[128], int64_t bias) {
    int64_t score = bias;
    for (unsigned k = 0; k < 128; ++k) {
        score += (int64_t)input[k] * (int64_t)weight[k];
    }
    return score;
}
