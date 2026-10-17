#include "qec_decoder.h"
#include "qec_tables.h"

uint32_t qec_decode(uint8_t syndrome) {
    return QEC_ML_LUT[syndrome];
}

uint32_t qec_decode_separate_css(uint8_t syndrome) {
    return static_cast<uint32_t>(QEC_X_LUT[syndrome & 15u]) |
           (static_cast<uint32_t>(QEC_Z_LUT[syndrome >> 4]) << 9);
}

uint32_t qec_decode_joint_min_weight(uint8_t syndrome) {
    return QEC_JOINT_MW_LUT[syndrome];
}
