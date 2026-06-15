// vnnx_smoke.c — minimal CoreVectorBlox V250 inference smoke test (Linux/UIO runtime).
// Target: MPFS250T Icicle Kit, seed_7 bitstream, Linux on the U54 cores.
// Part of the 2026-06-15 Linux/Yocto bring-up path (docs/track0_bringup_runbook.md).
//
// Uses the VectorBlox SDK 2.0.3 SoC runtime (drivers/vectorblox/vbx_cnn_api.c +
// vbx_cnn_model.c). API signatures verified against vbx_cnn_api.h this session.
// Self-checking: feeds the model's embedded test input, so no external CSV is
// needed for the first smoke run. (Rung G later replaces the input fill with a
// per-row ODMR CSV stream around the start/poll loop.)
//
// Runtime (per Microchip support #000017296 + agent research):
//   * Icicle build = POLL mode (USE_INTERRUPTS=0) + MSS-DDR udmabuf (MSS_DDR).
//   * vbx_cnn_init(NULL) auto-finds the V250 by scanning /sys/class/uio/uioN/name
//     for "vbx" (the seed7_vbx_pid.dtso overlay must be applied first), mmaps its
//     control page, and mmaps the non-cached DMA pool /dev/udmabuf-ddr-nc0.
//
// Build (on bee): make vnnx_smoke  (see firmware/linux/Makefile for the exact
//   flags + the required toolchain PATH, which must include dependencies/lib/cygwin).
// Run (on target): ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "vbx_cnn_api.h"

// fread the .vnnx, grow to the runtime's required allocation, copy into a
// DMA-resident buffer, return the DMA copy (model_get_* then read from there).
static model_t *read_model_file(vbx_cnn_t *vbx, const char *fn)
{
    FILE *f = fopen(fn, "rb");
    if (!f) { perror("fopen .vnnx"); return NULL; }
    fseek(f, 0, SEEK_END);
    long fsz = ftell(f);
    fseek(f, 0, SEEK_SET);
    model_t *m = (model_t *)malloc(fsz);
    if (!m || fread(m, 1, fsz, f) != (size_t)fsz) { fclose(f); free(m); return NULL; }
    fclose(f);

    size_t alloc = model_get_allocate_bytes(m);   // model data + runtime scratch
    void *dma = vbx_allocate_dma_buffer(vbx, alloc, 0);
    if (!dma) { free(m); return NULL; }
    memcpy(dma, m, model_get_data_bytes(m));
    free(m);
    return (model_t *)dma;
}

int main(int argc, char **argv)
{
    const char *vnnx = (argc > 1) ? argv[1] : "fcnn_v2_residual_dataset_a.vnnx";

    vbx_cnn_t *vbx = vbx_cnn_init(NULL);           // NULL -> auto-find UIO "vbx"
    if (!vbx || !vbx->initialized) {
        fprintf(stderr, "vbx_cnn_init failed (overlay applied? /dev/uioN present?)\n");
        return 1;
    }
    printf("V250 control plane alive (vbx_cnn initialized).\n");

    model_t *model = read_model_file(vbx, vnnx);
    if (!model) { fprintf(stderr, "read_model_file(%s) failed\n", vnnx); return 1; }

    size_t nin  = model_get_num_inputs(model);
    size_t nout = model_get_num_outputs(model);
    printf("model: %zu input(s), %zu output(s)\n", nin, nout);

    vbx_cnn_io_ptr_t io[MAX_IO_BUFFERS];           // uint64_t addresses
    // Inputs: use the model's embedded test vector (self-checking smoke run).
    for (size_t i = 0; i < nin; ++i)
        io[i] = (vbx_cnn_io_ptr_t)(uintptr_t)model_get_test_input(model, (int)i);
    // Outputs: INT8, allocate as u32 slots like the SDK example.
    for (size_t o = 0; o < nout; ++o) {
        size_t n = model_get_output_length(model, (int)o);
        void *ob = vbx_allocate_dma_buffer(vbx, n * sizeof(uint32_t), 0);
        if (!ob) { fprintf(stderr, "alloc output %zu failed\n", o); return 1; }
        memset(ob, 0, n * sizeof(uint32_t));
        io[nin + o] = (vbx_cnn_io_ptr_t)(uintptr_t)ob;
    }

    if (vbx_cnn_model_start(vbx, model, io) != 0) {
        fprintf(stderr, "model_start refused (state FULL/ERROR), err=%d\n",
                (int)vbx_cnn_get_error_val(vbx));
        return 1;
    }
    while (vbx_cnn_model_poll(vbx) > 0) { /* spin: IRQ disabled on Icicle */ }
    if (vbx_cnn_get_error_val(vbx)) {
        fprintf(stderr, "inference error %d\n", (int)vbx_cnn_get_error_val(vbx));
        return 1;
    }
    printf("inference complete.\n");

    // Dequantize INT8 -> float: (q - zero_point) * (scale_fix16 / 65536).
    for (size_t o = 0; o < nout; ++o) {
        size_t n = model_get_output_length(model, (int)o);
        int scale_fix16 = model_get_output_scale_fix16_value(model, (int)o);
        int zp          = model_get_output_zeropoint(model, (int)o);
        int8_t *out = (int8_t *)(uintptr_t)io[nin + o];
        double scale = scale_fix16 / 65536.0;
        printf("out[%zu] len=%zu scale=%.6f zp=%d:", o, n, scale, zp);
        for (size_t k = 0; k < n && k < 8; ++k)
            printf(" %.4f", ((int)out[k] - zp) * scale);
        printf("%s\n", n > 8 ? " ..." : "");
    }
    return 0;
}
