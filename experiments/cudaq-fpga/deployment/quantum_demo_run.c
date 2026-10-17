/* Linux userspace replay for the isolated quantum-demo image.
 * The fixed physical address is shared with an older PID image. ID and ABI
 * must match before any write. Host self-test never opens /dev/mem.
 * Build: cc -O2 -std=c11 -Wall -Wextra -Werror quantum_demo_run.c -o quantum_demo_run
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE
#endif
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "../hardware/quantum_demo_abi.h"

enum { E_USAGE=2,E_INPUT=3,E_DEVICE=4,E_TIMEOUT=5,E_REFERENCE=6,E_PROTOCOL=7,E_IO=8 };
enum { MAX_RECORDS=1048576, MAX_CALLS=16777216 };
typedef struct {
    uint32_t core,repeat,timeout_ms;
    const char *core_name,*inputs,*expected,*scores,*output,*json;
    int self_test;
} options_t;
typedef struct { unsigned char *data; size_t size; } blob_t;
typedef struct {
    uint64_t planned,attempted,completed,mismatches,validated_records;
    uint32_t id,abi,fabric_timeout_cycles,last_status,last_error,cycle_min,cycle_max;
    uint64_t *host_ns,*call_ns;
    size_t timed;
    int exit_code,hardware_opened,identity_verified;
    const char *reason;
} result_t;
static volatile sig_atomic_t interrupted=0;

static void stop_requested(int signo) { (void)signo; interrupted=1; }

static uint16_t le16(const unsigned char *p) {
    return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));
}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t le64(const unsigned char *p) {
    return (uint64_t)le32(p)|((uint64_t)le32(p+4)<<32);
}
static void io_fence(void) {
#if defined(__riscv)
    __asm__ __volatile__("fence iorw, iorw" ::: "memory");
#else
    __sync_synchronize();
#endif
}
static uint32_t reg_read(volatile uint32_t *regs,uint32_t offset) {
    io_fence();
    const uint32_t value=regs[offset/4];
    io_fence();
    return value;
}
static void reg_write(volatile uint32_t *regs,uint32_t offset,uint32_t value) {
    io_fence(); regs[offset/4]=value; io_fence();
}
static int now_ns(uint64_t *out) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    *out=(uint64_t)ts.tv_sec*UINT64_C(1000000000)+(uint64_t)ts.tv_nsec;
    return 0;
}
static int positive(const char *text,uint32_t maximum,uint32_t *out) {
    char *end=NULL;
    if (!text || !*text || text[0]=='-' || text[0]=='+') return -1;
    errno=0;
    unsigned long value=strtoul(text,&end,10);
    if (errno || *end || !value || value>maximum) return -1;
    *out=(uint32_t)value; return 0;
}
static int parse_args(int argc,char **argv,options_t *o) {
    memset(o,0,sizeof(*o));o->repeat=1;o->timeout_ms=100;
    unsigned seen=0;
    for (int i=1;i<argc;++i) {
        const char *arg=argv[i],*value=NULL;
        unsigned bit=0;
        if (!strcmp(arg,"--self-test")) {
            if (o->self_test) return -1;
            o->self_test=1;continue;
        }
        if (i+1>=argc) return -1;
        value=argv[++i];
        if (!strcmp(arg,"--core")) {
            bit=1u<<0;o->core_name=value;
            if (!strcmp(value,"readout")) o->core=QD_READOUT;
            else if (!strcmp(value,"nv")) o->core=QD_NV;
            else if (!strcmp(value,"qec")) o->core=QD_QEC;
            else return -1;
        } else if (!strcmp(arg,"--inputs")) {bit=1u<<1;o->inputs=value;}
        else if (!strcmp(arg,"--expected")) {bit=1u<<2;o->expected=value;}
        else if (!strcmp(arg,"--scores")) {bit=1u<<3;o->scores=value;}
        else if (!strcmp(arg,"--output")) {bit=1u<<4;o->output=value;}
        else if (!strcmp(arg,"--json")) {bit=1u<<5;o->json=value;}
        else if (!strcmp(arg,"--repeat")) {bit=1u<<6;if(positive(value,256,&o->repeat))return -1;}
        else if (!strcmp(arg,"--timeout-ms")) {bit=1u<<7;if(positive(value,1000,&o->timeout_ms))return -1;}
        else return -1;
        if (seen&bit) return -1;
        seen|=bit;
    }
    if (!o->core || !o->inputs || !o->expected) return -1;
    if ((o->core==QD_NV) != (o->scores!=NULL)) return -1;
    if (!o->self_test && (!o->output || !o->json)) return -1;
    return 0;
}

static int load_file(const char *path,size_t maximum,blob_t *out) {
    int fd=open(path,O_RDONLY);
    struct stat st;
    if (fd<0) {fprintf(stderr,"cannot open %s: %s\n",path,strerror(errno));return -1;}
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 || (uintmax_t)st.st_size>maximum) {
        fprintf(stderr,"invalid file type or length: %s\n",path);close(fd);return -1;
    }
    out->size=(size_t)st.st_size;
    out->data=malloc(out->size);
    if (!out->data) {close(fd);return -1;}
    size_t offset=0;
    while (offset<out->size) {
        ssize_t n=read(fd,out->data+offset,out->size-offset);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) {close(fd);return -1;}
        offset+=(size_t)n;
    }
    unsigned char extra;
    ssize_t tail;
    do {tail=read(fd,&extra,1);} while(tail<0 && errno==EINTR);
    close(fd);
    if (tail!=0) {fprintf(stderr,"file changed during read: %s\n",path);return -1;}
    return 0;
}
static int validate_packs(const options_t *o,blob_t *input,blob_t *expected,blob_t *scores,size_t *records) {
    const size_t input_stride=o->core==QD_QEC ? 1 : 256;
    const size_t output_stride=o->core==QD_READOUT ? 8 : (o->core==QD_NV ? 2 : 4);
    if (load_file(o->inputs,(size_t)MAX_RECORDS*input_stride,input) ||
        load_file(o->expected,(size_t)MAX_RECORDS*output_stride,expected)) return -1;
    if (input->size%input_stride) {fprintf(stderr,"partial input record\n");return -1;}
    *records=input->size/input_stride;
    if (expected->size!=*records*output_stride) {fprintf(stderr,"expected output length does not match input records\n");return -1;}
    if ((uint64_t)*records*o->repeat>MAX_CALLS) {fprintf(stderr,"total calls exceed %u\n",MAX_CALLS);return -1;}
    if (o->core==QD_NV) {
        if (load_file(o->scores,(size_t)MAX_RECORDS*8,scores) || scores->size!=*records*8) {
            fprintf(stderr,"NV score length does not match input records\n");return -1;
        }
        for (size_t i=0;i<*records;++i) {
            if (le16(expected->data+2*i)>120 || le64(scores->data+8*i)>UINT64_C(549739036800)) {
                fprintf(stderr,"NV reference outside frozen model bounds\n");return -1;
            }
        }
    } else if (o->core==QD_QEC) {
        for (size_t i=0;i<*records;++i) {
            if (le32(expected->data+4*i)&~UINT32_C(0x3ffff)) {
                fprintf(stderr,"QEC reference has reserved correction bits set\n");return -1;
            }
        }
    }
    return 0;
}
static FILE *new_output(const char *path) {
    if (!path) return NULL;
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0644);
    if (fd<0) {fprintf(stderr,"output must be a new writable file: %s: %s\n",path,strerror(errno));return NULL;}
    FILE *stream=fdopen(fd,"w");
    if (!stream) close(fd);
    return stream;
}
static uint64_t expected_value(const options_t *o,const blob_t *b,size_t index) {
    if (o->core==QD_READOUT) return le64(b->data+index*8);
    if (o->core==QD_NV) return le16(b->data+index*2);
    return le32(b->data+index*4);
}
static int compare_u64(const void *a,const void *b) {
    uint64_t x=*(const uint64_t*)a,y=*(const uint64_t*)b;
    return (x>y)-(x<y);
}
static uint64_t percentile(const uint64_t *values,size_t n,unsigned percent) {
    if (!n) return 0;
    size_t rank=(n*percent+99)/100;
    return values[rank ? rank-1 : 0];
}
static void json_string(FILE *stream,const char *s) {
    fputc('"',stream);
    for (const unsigned char *p=(const unsigned char*)s;*p;++p) {
        if (*p=='"' || *p=='\\') {fputc('\\',stream);fputc(*p,stream);}
        else if (*p<32) fprintf(stream,"\\u%04x",*p);
        else fputc(*p,stream);
    }
    fputc('"',stream);
}
static void emit_summary(FILE *stream,const options_t *o,result_t *r) {
    if (r->timed) {
        qsort(r->host_ns,r->timed,sizeof(uint64_t),compare_u64);
        qsort(r->call_ns,r->timed,sizeof(uint64_t),compare_u64);
    }
    fprintf(stream,"{\n  \"schema\": \"quantum_demo_replay_v1\",\n  \"core\": ");json_string(stream,o->core_name);
    fprintf(stream,",\n  \"mode\": \"%s\",\n  \"exit_code\": %d,\n  \"reason\": ",o->self_test?"parse_only_no_mmio":"fabric_mmio",r->exit_code);json_string(stream,r->reason);
    fprintf(stream,",\n  \"hardware_opened\": %s,\n  \"identity_verified\": %s,\n  \"id\": \"0x%08" PRIx32 "\",\n  \"abi\": \"0x%08" PRIx32 "\",\n",r->hardware_opened?"true":"false",r->identity_verified?"true":"false",r->id,r->abi);
    fprintf(stream,"  \"base\": \"0x%08" PRIx64 "\",\n  \"span\": %u,\n  \"validated_records\": %" PRIu64 ",\n  \"repeat\": %u,\n  \"planned_calls\": %" PRIu64 ",\n  \"attempted_calls\": %" PRIu64 ",\n  \"completed_calls\": %" PRIu64 ",\n  \"mismatches\": %" PRIu64 ",\n",(uint64_t)QD_BASE,QD_SPAN,r->validated_records,o->repeat,r->planned,r->attempted,r->completed,r->mismatches);
    fprintf(stream,"  \"host_timeout_ms\": %u,\n  \"fabric_timeout_cycles\": %u,\n  \"last_status\": %u,\n  \"last_error\": %u,\n  \"fabric_cycles_min\": %u,\n  \"fabric_cycles_max\": %u,\n",o->timeout_ms,r->fabric_timeout_cycles,r->last_status,r->last_error,r->timed?r->cycle_min:0,r->timed?r->cycle_max:0);
    fprintf(stream,"  \"latency_sample_count\": %zu,\n  \"host_total_ns\": {\"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",r->timed,percentile(r->host_ns,r->timed,50),percentile(r->host_ns,r->timed,99),r->timed?r->host_ns[r->timed-1]:0);
    fprintf(stream,"  \"host_call_ns\": {\"p50\": %" PRIu64 ", \"p99\": %" PRIu64 ", \"max\": %" PRIu64 "},\n",percentile(r->call_ns,r->timed,50),percentile(r->call_ns,r->timed,99),r->timed?r->call_ns[r->timed-1]:0);
    fprintf(stream,"  \"latency_scope\": \"successful completed calls only; total includes register setup/input writes and output reads; call starts immediately before START; CSV IO excluded; fabric cycles are not converted to nanoseconds\",\n  \"inputs\": ");json_string(stream,o->inputs);
    fprintf(stream,",\n  \"expected\": ");json_string(stream,o->expected);
    fprintf(stream,",\n  \"scores\": ");if(o->scores)json_string(stream,o->scores);else fprintf(stream,"null");
    fprintf(stream,"\n}\n");
}

static int replay(const options_t *o,const blob_t *input,const blob_t *expected,const blob_t *scores,size_t records,FILE *csv,result_t *r) {
    int fd=-1;
    void *mapping=MAP_FAILED;
    volatile uint32_t *regs=NULL;
    int active=0;
    long page=sysconf(_SC_PAGESIZE);
    const uint32_t endian_test=1;
    if (page<=0 || QD_BASE%(uint64_t)page || QD_SPAN%(uint32_t)page || *(const unsigned char*)&endian_test!=1) {
        r->reason="unsupported page size, mapping alignment, or host byte order";return E_DEVICE;
    }
    fd=open("/dev/mem",O_RDWR|O_SYNC);
    if (fd<0) {r->reason="cannot open /dev/mem";return E_DEVICE;}
    r->hardware_opened=1;
    if (flock(fd,LOCK_EX|LOCK_NB)) {r->reason="another cooperating MMIO replay holds the device lock";r->exit_code=E_DEVICE;goto cleanup;}
    mapping=mmap(NULL,QD_SPAN,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)QD_BASE);
    if (mapping==MAP_FAILED) {r->reason="cannot map fixed register page";r->exit_code=E_DEVICE;goto cleanup;}
    regs=(volatile uint32_t*)mapping;
    r->id=reg_read(regs,QD_ID);r->abi=reg_read(regs,QD_ABI);
    if (r->id!=QD_ID_VALUE || r->abi!=QD_ABI_VALUE) {r->reason="ID or ABI mismatch; no register writes performed";r->exit_code=E_DEVICE;goto cleanup;}
    r->identity_verified=1;
    r->fabric_timeout_cycles=reg_read(regs,QD_TIMEOUT);
    r->last_status=reg_read(regs,QD_STATUS);
    if (!r->fabric_timeout_cycles || (r->last_status&QD_BUSY)) {r->reason="device busy or invalid hardware timeout; no register writes performed";r->exit_code=E_DEVICE;goto cleanup;}
    for (uint32_t repeat=0;repeat<o->repeat;++repeat) {
        for (size_t record=0;record<records;++record) {
            if (interrupted) {r->reason="interrupted before next call";r->exit_code=E_TIMEOUT;goto cleanup;}
            uint64_t total_start,call_start,end,current;
            uint32_t before,after,cycles;
            uint64_t actual=0,score=0,want=expected_value(o,expected,record),want_score=o->core==QD_NV?le64(scores->data+record*8):0;
            if (now_ns(&total_start)) {r->reason="CLOCK_MONOTONIC failed";r->exit_code=E_IO;goto cleanup;}
            r->last_status=reg_read(regs,QD_STATUS);
            if (r->last_status&QD_BUSY) {r->reason="unexpected busy before call; no abort of another call";r->exit_code=E_PROTOCOL;goto cleanup;}
            before=reg_read(regs,QD_COMPLETED_COUNT);
            reg_write(regs,QD_CONTROL,QD_CLEAR);
            r->last_status=reg_read(regs,QD_STATUS);
            if (r->last_status&(QD_BUSY|QD_DONE|QD_FAILED)) {r->reason="CLEAR did not establish idle clean status";r->exit_code=E_PROTOCOL;goto cleanup;}
            reg_write(regs,QD_CORE,o->core);
            if (reg_read(regs,QD_CORE)!=o->core) {r->reason="core selection readback mismatch";r->exit_code=E_PROTOCOL;goto cleanup;}
            if (o->core==QD_QEC) reg_write(regs,QD_SYNDROME,input->data[record]);
            else {
                const unsigned char *p=input->data+record*256;
                for (uint32_t word=0;word<QD_INPUT_WORDS;++word) {
                    /* Preserve the two's-complement bits; never sign-extend one lane into the next. */
                    const uint32_t packed=(uint32_t)le16(p+4*word)|((uint32_t)le16(p+4*word+2)<<16);
                    reg_write(regs,QD_INPUT_BASE+word*4,packed);
                }
                if (!(reg_read(regs,QD_STATUS)&QD_INPUT_VALID)) {r->reason="input-valid status missing after full input write";r->exit_code=E_PROTOCOL;goto cleanup;}
            }
            if (now_ns(&call_start)) {r->reason="CLOCK_MONOTONIC failed";r->exit_code=E_IO;goto cleanup;}
            reg_write(regs,QD_CONTROL,QD_START);active=1;++r->attempted;
            for (;;) {
                if (now_ns(&current)) {r->reason="CLOCK_MONOTONIC failed while polling";r->exit_code=E_IO;goto call_failure;}
                if (interrupted || current-call_start>=(uint64_t)o->timeout_ms*UINT64_C(1000000)) {
                    r->reason=interrupted?"interrupted active call; ABORT issued":"host deadline exceeded; ABORT issued";
                    r->exit_code=E_TIMEOUT;goto call_failure;
                }
                r->last_status=reg_read(regs,QD_STATUS);
                if (r->last_status&QD_FAILED) {
                    r->last_error=reg_read(regs,QD_ERROR);
                    r->reason="fabric reported an error";r->exit_code=r->last_error==QD_ERR_TIMEOUT?E_TIMEOUT:E_PROTOCOL;goto call_failure;
                }
                if ((r->last_status&QD_DONE) && !(r->last_status&QD_BUSY)) break;
            }
            active=0;
            actual=(uint64_t)reg_read(regs,QD_RESULT_LO)|((uint64_t)reg_read(regs,QD_RESULT_HI)<<32);
            if (o->core==QD_NV) score=(uint64_t)reg_read(regs,QD_SCORE_LO)|((uint64_t)reg_read(regs,QD_SCORE_HI)<<32);
            cycles=reg_read(regs,QD_CYCLES);after=reg_read(regs,QD_COMPLETED_COUNT);r->last_error=reg_read(regs,QD_ERROR);
            if (now_ns(&end)) {r->reason="CLOCK_MONOTONIC failed after completion";r->exit_code=E_IO;goto call_failure;}
            if (interrupted || end-call_start>=(uint64_t)o->timeout_ms*UINT64_C(1000000)) {
                r->reason=interrupted?"interrupted after completion; result not accepted":"host deadline exceeded after completion; result not accepted";
                r->exit_code=E_TIMEOUT;goto call_failure;
            }
            if ((uint32_t)(after-before)!=1 || r->last_error) {r->reason="completion counter or error register mismatch";r->exit_code=E_PROTOCOL;goto call_failure;}
            ++r->completed;
            r->host_ns[r->timed]=end-total_start;r->call_ns[r->timed]=end-call_start;++r->timed;
            if (cycles<r->cycle_min)r->cycle_min=cycles;
            if (cycles>r->cycle_max)r->cycle_max=cycles;
            const int match=actual==want && (o->core!=QD_NV || score==want_score);
            if (!match)++r->mismatches;
            if (fprintf(csv,"%" PRIu64 ",%u,%zu,0x%016" PRIx64 ",0x%016" PRIx64 ",0x%016" PRIx64 ",0x%016" PRIx64 ",%d,%u,%u,%u,%u,%u,%" PRIu64 ",%" PRIu64 "\n",r->attempted-1,repeat,record,want,actual,want_score,score,match,r->last_status,r->last_error,before,after,cycles,end-total_start,end-call_start)<0) {r->reason="CSV write failed";r->exit_code=E_IO;goto cleanup;}
            continue;
call_failure:
            if (active) {reg_write(regs,QD_CONTROL,QD_ABORT);active=0;}
            after=reg_read(regs,QD_COMPLETED_COUNT);cycles=reg_read(regs,QD_CYCLES);
            if (now_ns(&end))end=call_start;
            (void)fprintf(csv,"%" PRIu64 ",%u,%zu,0x%016" PRIx64 ",0x%016" PRIx64 ",0x%016" PRIx64 ",0x%016" PRIx64 ",0,%u,%u,%u,%u,%u,%" PRIu64 ",%" PRIu64 "\n",r->attempted-1,repeat,record,want,actual,want_score,score,r->last_status,r->last_error,before,after,cycles,end-total_start,end-call_start);
            goto cleanup;
        }
    }
    r->reason=r->mismatches?"completed with reference mismatches":"all fabric results match exact references";
    r->exit_code=r->mismatches?E_REFERENCE:0;
cleanup:
    if (active && regs && r->identity_verified)reg_write(regs,QD_CONTROL,QD_ABORT);
    if (mapping!=MAP_FAILED)munmap(mapping,QD_SPAN);
    if(fd>=0)close(fd);
    return r->exit_code;
}

int main(int argc,char **argv) {
    options_t o;
    if (parse_args(argc,argv,&o)) {
        fprintf(stderr,"usage: quantum_demo_run --core readout|nv|qec --inputs FILE --expected FILE [--scores NV_SCORES] --output NEW.csv --json NEW.json [--repeat 1..256] [--timeout-ms 1..1000] [--self-test]\nSelf-test validates files without MMIO; output/json are optional in self-test. NV requires --scores. Existing outputs are never overwritten.\n");
        return E_USAGE;
    }
    blob_t input={0},expected={0},scores={0};size_t records=0;
    result_t r={0};r.reason="not started";r.cycle_min=UINT32_MAX;
    FILE *csv=NULL,*json=NULL;
    if (validate_packs(&o,&input,&expected,&scores,&records)) {r.exit_code=E_INPUT;r.reason="malformed or unreadable input pack; no MMIO";goto finish;}
    r.validated_records=records;r.planned=(uint64_t)records*o.repeat;
    if (o.output) {
        csv=new_output(o.output);
        if (!csv) {r.exit_code=E_IO;r.reason="cannot create CSV; no MMIO";goto finish;}
        if (fprintf(csv,"call,repeat,record,expected_hex,result_hex,expected_score_hex,score_hex,match,status,error,completed_before,completed_after,fabric_cycles,host_total_ns,host_call_ns\n")<0) {r.exit_code=E_IO;r.reason="cannot write CSV header; no MMIO";goto finish;}
    }
    if (o.json) {
        json=new_output(o.json);
        if (!json) {r.exit_code=E_IO;r.reason="cannot create JSON; no MMIO";goto finish;}
    }
    if (o.self_test) {r.reason="all input lengths, byte layouts and model bounds validated; no MMIO";goto finish;}
    if (r.planned>SIZE_MAX/sizeof(uint64_t)) {r.exit_code=E_INPUT;r.reason="latency allocation size overflow; no MMIO";goto finish;}
    r.host_ns=calloc((size_t)r.planned,sizeof(uint64_t));r.call_ns=calloc((size_t)r.planned,sizeof(uint64_t));
    if (!r.host_ns || !r.call_ns) {r.exit_code=E_IO;r.reason="cannot allocate bounded latency records; no MMIO";goto finish;}
    struct sigaction action;
    memset(&action,0,sizeof(action));action.sa_handler=stop_requested;sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL)) {r.exit_code=E_IO;r.reason="cannot install termination handlers; no MMIO";goto finish;}
    r.exit_code=replay(&o,&input,&expected,&scores,records,csv,&r);
finish:
    if (csv) {
        if (fflush(csv)||ferror(csv)) {r.exit_code=E_IO;r.reason="CSV flush failed";}
        if (fclose(csv)) {r.exit_code=E_IO;r.reason="CSV close failed";}
    }
    if (json) {
        emit_summary(json,&o,&r);
        if (fflush(json)||ferror(json))r.exit_code=E_IO;
        if(fclose(json))r.exit_code=E_IO;
    }
    emit_summary(stdout,&o,&r);
    free(input.data);free(expected.data);free(scores.data);free(r.host_ns);free(r.call_ns);
    return r.exit_code;
}
