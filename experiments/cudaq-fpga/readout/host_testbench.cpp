#include <stdint.h>
#include <stdio.h>
#include "hls_vectors.h"

extern "C" int64_t readout_score128(const int16_t[128], const int16_t[128], int64_t);
extern "C" int64_t boxcar_readout64(const int16_t[128], int16_t, int16_t, int64_t);

int main() {
    unsigned failed = 0;
    for (unsigned k = 0; k < VECTOR_COUNT; ++k) {
        const int64_t generic = readout_score128(INPUTS[k], WEIGHTS, BIAS);
        const int64_t boxcar = boxcar_readout64(INPUTS[k], WEIGHTS[0], WEIGHTS[1], BIAS);
        if (generic != EXPECTED[k] || boxcar != EXPECTED[k]) ++failed;
    }
    printf("%u/%u fixed-input vectors bit-exact; generic and boxcar cores; host only\n",
           VECTOR_COUNT-failed, VECTOR_COUNT);
    return failed ? 1 : 0;
}
