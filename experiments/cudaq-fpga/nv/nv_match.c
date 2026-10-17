#include <stdint.h>
#include <stddef.h>

/* Portable host reference. No device, DMA, synthesis, or latency claim. */
uint16_t nv_match(const int16_t *input, const int16_t *templates,
                  uint64_t *best_score) {
    uint64_t best = UINT64_MAX;
    uint16_t best_index = 0;
    for (uint16_t k = 0; k < 121; ++k) {
        uint64_t sum = 0;
        for (size_t j = 0; j < 128; ++j) {
            const int64_t delta = (int64_t)input[j] - templates[k * 128 + j];
            sum += (uint64_t)(delta * delta);
        }
        if (sum < best) { best = sum; best_index = k; }
    }
    *best_score = best;
    return best_index;
}
