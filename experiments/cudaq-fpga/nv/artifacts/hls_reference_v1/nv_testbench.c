#include <stdint.h>
#include <stdio.h>
#include "nv_rom.h"
#include "nv_vectors.h"
uint16_t nv_match(const int16_t *, const int16_t *, uint64_t *);
int main(void) {
    for (int k = 0; k < 8; ++k) {
        uint64_t score = 0;
        const uint16_t index = nv_match(&nv_inputs[k*128],nv_templates,&score);
        if (index != nv_expected_index[k] || score != nv_expected_score[k]) return 1;
    }
    puts("NV host reference: 8/8 vectors agree exactly");
    return 0;
}
