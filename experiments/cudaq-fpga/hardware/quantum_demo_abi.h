#ifndef QUANTUM_DEMO_ABI_H
#define QUANTUM_DEMO_ABI_H
#include <stdint.h>
#define QD_BASE UINT64_C(0x60040000)
#define QD_SPAN 0x1000u
#define QD_ID 0x00u
#define QD_ID_VALUE 0x51465047u
#define QD_ABI 0x04u
#define QD_ABI_VALUE 0x00010000u
#define QD_CONTROL 0x08u
#define QD_STATUS 0x0cu
#define QD_CORE 0x10u
#define QD_SYNDROME 0x14u
#define QD_TIMEOUT 0x18u
#define QD_CYCLES 0x1cu
#define QD_RESULT_LO 0x20u
#define QD_RESULT_HI 0x24u
#define QD_SCORE_LO 0x28u
#define QD_SCORE_HI 0x2cu
#define QD_COMPLETED_COUNT 0x30u
#define QD_ERROR 0x34u
#define QD_INPUT_BASE 0x100u
#define QD_INPUT_WORDS 64u
#define QD_START 1u
#define QD_ABORT 2u
#define QD_CLEAR 4u
#define QD_BUSY 1u
#define QD_DONE 2u
#define QD_FAILED 4u
#define QD_INPUT_VALID 8u
#define QD_READOUT 1u
#define QD_NV 2u
#define QD_QEC 3u
#define QD_ERR_TIMEOUT 1u
#define QD_ERR_ABORTED 2u
#define QD_ERR_NV_SCORE_MISSING 3u
#endif
