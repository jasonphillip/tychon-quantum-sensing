/* vbx_probe.c — bounded on-silicon V250 inference validation probe (KEEP).
 *
 * History: originally a temporary A/B diagnostic. It settled the rung-F root cause (the
 * bitstream shipped CoreVectorBlox 1.1.12/V500 instead of the stack's 2.0.1/V250) and then
 * VALIDATED the 2.0.1/V250 rebuild on silicon (2026-06-16): CTRL advances 0x00->0x04->done,
 * RESULT: INFERENCE COMPLETED, VER=0x20000000. Retained as a fast, self-contained, bounded
 * health check for the V250 inference path.
 *
 * Purpose: run the *stock* VectorBlox 2.0.3 SoC runtime through one full inference and report
 * whether the V250 advances past START (CTRL=0x02) to RUNNING/done, or sticks at CTRL=0x02 /
 * ERR=0 (the historical vnnx_smoke symptom). Bounded poll → never spins forever.
 *
 * Faithfulness: links the UNMODIFIED stock driver sources
 *   drivers/vectorblox/vbx_cnn_api.c + vbx_cnn_model.c
 * and follows example/soc-c/run-model.cpp's exact TEST_DATA path
 *   vbx_cnn_init -> read model into DMA -> (throwaway input alloc + model_get_test_input)
 *   -> output DMA alloc -> vbx_cnn_model_start -> poll
 * It omits ONLY run-model's post-inference plumbing (PDMA output copy, libjpeg image
 * load, postprocess), which runs *after* OUTPUT_VALID and cannot affect START->RUNNING.
 *
 * Differences from run-model that matter for diagnosis: NONE in the start/poll path.
 * Additions: logs CTRL/ERR/MODEL/IO/VERSION at each stage; the poll loop is BOUNDED
 * (never spins forever).
 *
 * Build (bee, mirrors firmware/linux/Makefile vnnx_smoke recipe; cygwin1.dll on PATH):
 *   VBX=/c/Microchip/VectorBlox-SDK
 *   riscv64-unknown-linux-gnu-gcc -O2 -Wall -DVBX_SOC_DRIVER -DMSS_DDR -DUSE_INTERRUPTS=0 \
 *     -I$VBX/drivers/vectorblox vbx_probe.c \
 *     $VBX/drivers/vectorblox/vbx_cnn_api.c $VBX/drivers/vectorblox/vbx_cnn_model.c \
 *     -o vbx_probe -lm -lpthread
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "vbx_cnn_api.h"

/* word-indexed control page: CTRL=0, ERR=1, MODEL=4, IO=6, VERSION=10 */
static void dump(const char *tag, vbx_cnn_t *v) {
    volatile uint32_t *r = v->ctrl_reg;
    printf("[%-12s] CTRL=0x%08x ERR=0x%08x MODEL=0x%08x IO=0x%08x VER=0x%08x\n",
           tag, r[0], r[1], r[4], r[6], r[10]);
    fflush(stdout);
}

int main(int argc, char **argv) {
    const char *vnnx = (argc > 1) ? argv[1] : "fcnn_v2_residual_dataset_a.vnnx";

    vbx_cnn_t *vbx = vbx_cnn_init(NULL);
    if (!vbx || !vbx->initialized) { fprintf(stderr, "vbx_cnn_init failed\n"); return 1; }
    printf("init OK (control plane alive)\n");
    dump("after_init", vbx);               /* after soft-reset (init writes SOFT_RESET then 0) */

    FILE *f = fopen(vnnx, "rb");
    if (!f) { perror("fopen .vnnx"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    model_t *tmp = (model_t *)malloc(sz);
    if (!tmp || fread(tmp, 1, sz, f) != (size_t)sz) { fprintf(stderr, "read vnnx failed\n"); return 1; }
    fclose(f);
    size_t need = model_get_allocate_bytes(tmp);
    void *dma = vbx_allocate_dma_buffer(vbx, need, 0);
    if (!dma) { fprintf(stderr, "model DMA alloc failed\n"); return 1; }
    memcpy(dma, tmp, model_get_data_bytes(tmp));
    free(tmp);
    model_t *model = (model_t *)dma;

    int nin = model_get_num_inputs(model), nout = model_get_num_outputs(model);
    printf("model: %d input(s) / %d output(s), sanity=%d\n", nin, nout, model_check_sanity(model));

    vbx_cnn_io_ptr_t io[MAX_IO_BUFFERS];
    for (int i = 0; i < nin; ++i) {
        /* run-model allocates an input buffer then (TEST_DATA) overwrites with test input */
        vbx_allocate_dma_buffer(vbx, model_get_input_length(model, i) * sizeof(uint8_t), 1);
        io[i] = (vbx_cnn_io_ptr_t)(uint8_t *)model_get_test_input(model, i);
    }
    for (int o = 0; o < nout; ++o)
        io[nin + o] = (vbx_cnn_io_ptr_t)vbx_allocate_dma_buffer(
            vbx, model_get_output_length(model, o) * sizeof(uint32_t), 0);
    dump("before_start", vbx);

    int status = vbx_cnn_model_start(vbx, model, io);
    printf("vbx_cnn_model_start ret=%d\n", status);
    dump("after_start", vbx);

    /* BOUNDED poll: up to ~3 s, then stop. NEVER infinite. */
    int p = 1, it; const int MAXIT = 600;
    for (it = 0; it < MAXIT; ++it) {
        p = vbx_cnn_model_poll(vbx);
        if (p <= 0) break;
        if (it < 5 || it % 100 == 0) {
            volatile uint32_t *r = vbx->ctrl_reg;
            printf("  poll#%d ret=%d CTRL=0x%08x ERR=0x%08x\n", it, p, r[0], r[1]);
            fflush(stdout);
        }
        usleep(5000);
    }
    printf("poll ended: iters=%d last_poll_ret=%d\n", it, p);
    dump("final", vbx);
    printf("error_val=%d\n", (int)vbx_cnn_get_error_val(vbx));

    if (p <= 0 && !vbx_cnn_get_error_val(vbx)) printf("RESULT: INFERENCE COMPLETED\n");
    else if (it >= MAXIT)                       printf("RESULT: STUCK (bounded poll exhausted)\n");
    else                                        printf("RESULT: ERROR\n");
    return 0;
}
