#include "qec_decoder.h"
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <time.h>

static double monotonic_ns() {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return static_cast<double>(value.tv_sec) * 1e9 + static_cast<double>(value.tv_nsec);
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--dump") == 0) {
        for (unsigned s = 0; s < 256; ++s) {
            printf("%u %u %u %u\n", s, qec_decode(static_cast<uint8_t>(s)),
                   qec_decode_separate_css(static_cast<uint8_t>(s)),
                   qec_decode_joint_min_weight(static_cast<uint8_t>(s)));
        }
        return 0;
    }
    if (argc != 2 || strcmp(argv[1], "--benchmark") != 0) {
        fprintf(stderr, "Usage: host_benchmark --dump|--benchmark\n");
        return 2;
    }
    const unsigned iterations = 1000000;
    uint32_t (*functions[])(uint8_t) = {qec_decode, qec_decode_separate_css, qec_decode_joint_min_weight};
    const char *names[] = {"fixed_ml", "separate_css", "joint_min_weight"};
    printf("{\"iterations_per_repeat\":%u,\"host_only\":true,\"measurements\":[", iterations);
    for (unsigned decoder = 0; decoder < 3; ++decoder) {
        if (decoder) printf(",");
        printf("{\"decoder\":\"%s\",\"ns_per_lookup_repeats\":[", names[decoder]);
        uint64_t checksum = 0;
        for (unsigned repeat = 0; repeat < 5; ++repeat) {
            uint32_t state = 0x8e97ab31u;
            const double begin = monotonic_ns();
            for (unsigned i = 0; i < iterations; ++i) {
                state = 1664525u * state + 1013904223u;
                checksum += functions[decoder](static_cast<uint8_t>(state >> 24));
            }
            const double end = monotonic_ns();
            const double ns = (end - begin) / iterations;
            if (repeat) printf(",");
            printf("%.6f", ns);
        }
        printf("],\"checksum\":%llu}", static_cast<unsigned long long>(checksum));
    }
    printf("]}\n");
}
