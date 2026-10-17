#include "../qec_decoder.cpp"
#include "golden_corrections.h"
#include <stdio.h>

uint32_t qec_top(uint8_t syndrome) {
#pragma HLS function top
    return qec_decode(syndrome);
}

int main() {
    unsigned mismatches = 0;
    for (unsigned syndrome = 0; syndrome < 256; ++syndrome) {
        const uint32_t actual = qec_top(static_cast<uint8_t>(syndrome));
        if (actual != GOLDEN_CORRECTIONS[syndrome]) {
            ++mismatches;
            printf("Mismatch syndrome=%u expected=%u actual=%u\n",
                   syndrome, GOLDEN_CORRECTIONS[syndrome], actual);
        }
    }
    printf("QEC golden comparisons=256 mismatches=%u\n", mismatches);
    return mismatches ? 1 : 0;
}
