#include <stdint.h>
#include <stdio.h>
#include "../nv_match.c"
#include "../artifacts/hls_reference_v1/nv_rom.h"
#include "../artifacts/hls_reference_v1/nv_vectors.h"

uint16_t nv_template_top(const int16_t input[128], uint64_t &score) {
    #pragma HLS function top
    return nv_match(input, nv_templates, &score);
}

int main() {
    for (unsigned k = 0; k < 8; ++k) {
        uint64_t score = 0;
        const uint16_t index = nv_template_top(&nv_inputs[k * 128], score);
        if (index != nv_expected_index[k] || score != nv_expected_score[k]) {
            printf("NV mismatch at vector %u\n", k);
            return 1;
        }
    }
    puts("NV wrapper host reference: 8/8 vectors agree exactly");
    return 0;
}
