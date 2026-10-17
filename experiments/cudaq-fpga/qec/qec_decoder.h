#ifndef QEC_DECODER_H
#define QEC_DECODER_H
#include <stdint.h>

// Input: Z-check bits 0..3, X-check bits 4..7; one perfect measurement round.
// Output: X correction mask in bits 0..8, Z correction mask in bits 9..17.
// This updates a Pauli frame. It is not a qubit pulse generator.
uint32_t qec_decode(uint8_t syndrome);
uint32_t qec_decode_separate_css(uint8_t syndrome);
uint32_t qec_decode_joint_min_weight(uint8_t syndrome);
#endif
