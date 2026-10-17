/* Bounded control verification for the isolated quantum-demo image.
 * --self-test never opens /dev/mem. --run explicitly selects fabric MMIO.
 * The replay runner and this program both flock /dev/mem exclusively.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#define _DEFAULT_SOURCE
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#endif
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "../hardware/quantum_demo_abi.h"

#define DEADLINE_NS UINT64_C(100000000)
/* ROM entry 0 and hardware/vectors/qec_expected.hex entry 0 both equal 0. */
#define QEC_ZERO_CORRECTION UINT64_C(0)
enum { MAX_CHECKS=24, EXIT_USAGE=2, EXIT_DEVICE=3, EXIT_CHECK=4 };
_Static_assert(sizeof(uint32_t)==4, "MMIO requires 32-bit words");
_Static_assert(QD_BASE==UINT64_C(0x60040000), "fixed physical address");
_Static_assert(QD_SPAN==4096u, "fixed mapping span");
_Static_assert(QD_INPUT_WORDS==64u, "exact input word count");
_Static_assert(QD_INPUT_BASE+4u*QD_INPUT_WORDS<=QD_SPAN, "bounded input writes");

typedef struct {
    uint32_t status,error,cycles,count,core,syndrome,timeout;
    uint64_t result,score;
} snapshot_t;
typedef struct {
    const char *name,*detail;
    int pass,observed;
    uint32_t before;
    snapshot_t after;
} check_t;
typedef struct {
    check_t checks[MAX_CHECKS];
    unsigned count;
    int opened,identity,writes,started,timeout_saved,timeout_changed,restored,exit_code;
    uint32_t id,abi,original_timeout;
    const char *reason;
} report_t;
static volatile sig_atomic_t interrupted;
static void request_stop(int signo) { (void)signo; interrupted=1; }
static void fence_io(void) {
#if defined(__riscv)
    __asm__ __volatile__("fence iorw, iorw" ::: "memory");
#else
    __sync_synchronize();
#endif
}
static uint32_t rd(volatile uint32_t *r,uint32_t offset) {
    fence_io(); const uint32_t value=r[offset/4u]; fence_io(); return value;
}
static void wr(volatile uint32_t *r,uint32_t offset,uint32_t value,report_t *report) {
    fence_io(); r[offset/4u]=value; fence_io(); report->writes=1;
}
static int now_ns(uint64_t *value) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    *value=(uint64_t)ts.tv_sec*UINT64_C(1000000000)+(uint64_t)ts.tv_nsec;
    return 0;
}
static snapshot_t snapshot(volatile uint32_t *r) {
    snapshot_t s;
    s.status=rd(r,QD_STATUS);s.error=rd(r,QD_ERROR);s.cycles=rd(r,QD_CYCLES);
    s.count=rd(r,QD_COMPLETED_COUNT);s.core=rd(r,QD_CORE);
    s.syndrome=rd(r,QD_SYNDROME);s.timeout=rd(r,QD_TIMEOUT);
    s.result=(uint64_t)rd(r,QD_RESULT_LO)|((uint64_t)rd(r,QD_RESULT_HI)<<32);
    s.score=(uint64_t)rd(r,QD_SCORE_LO)|((uint64_t)rd(r,QD_SCORE_HI)<<32);
    return s;
}
static int add_check(report_t *r,const char *name,int pass,const char *detail,
                     uint32_t before,const snapshot_t *after) {
    if (r->count>=MAX_CHECKS) {r->exit_code=EXIT_CHECK;r->reason="check capacity exceeded";return 0;}
    check_t *c=&r->checks[r->count++];
    c->name=name;c->detail=detail;c->pass=pass;c->observed=after!=NULL;c->before=before;
    if (after)c->after=*after;
    if (!pass) {r->exit_code=EXIT_CHECK;r->reason=detail;}
    return pass;
}
/* All waits use a monotonic deadline. No sleep or unbounded busy-wait. */
static int wait_idle(volatile uint32_t *r,uint64_t begin,int require_done,int honor_signal) {
    for (;;) {
        uint64_t now;
        if (now_ns(&now) || now-begin>=DEADLINE_NS || (honor_signal && interrupted))return -1;
        const uint32_t s=rd(r,QD_STATUS);
        if (!(s&QD_BUSY) && (!require_done || (s&QD_DONE))) {
            if (now_ns(&now) || now-begin>=DEADLINE_NS)return -1;
            return 0;
        }
    }
}
static int terminal_matches(const snapshot_t *s,uint32_t before,uint32_t error) {
    const uint32_t mask=QD_BUSY|QD_DONE|QD_FAILED;
    const uint32_t want=QD_DONE|(error?QD_FAILED:0u);
    return (s->status&mask)==want && s->error==error &&
           (uint32_t)(s->count-before)==1u;
}
static int clear_matches(const snapshot_t *a,const snapshot_t *b) {
    return b->status==(a->status&QD_INPUT_VALID) && b->error==0 &&
           b->result==0 && b->score==0 && b->cycles==a->cycles &&
           b->count==a->count && b->core==a->core &&
           b->syndrome==a->syndrome && b->timeout==a->timeout;
}
static int same_snapshot(const snapshot_t *a,const snapshot_t *b) {
    return a->status==b->status && a->error==b->error && a->cycles==b->cycles &&
           a->count==b->count && a->core==b->core && a->syndrome==b->syndrome &&
           a->timeout==b->timeout && a->result==b->result && a->score==b->score;
}
static int clear_checked(volatile uint32_t *regs,report_t *r,const char *name) {
    snapshot_t a=snapshot(regs);
    if (a.status&QD_BUSY)return add_check(r,name,0,"CLEAR refused while busy",a.count,&a);
    wr(regs,QD_CONTROL,QD_CLEAR,r);
    snapshot_t b=snapshot(regs);
    return add_check(r,name,clear_matches(&a,&b),
        "CLEAR removes done/error/results; preserves cycles/count/selection/timeout/input validity",a.count,&b);
}
static int qec_call(volatile uint32_t *regs,report_t *r,const char *name,int force_timeout) {
    if (interrupted) {r->reason="interrupted before QEC start";r->exit_code=EXIT_CHECK;return 0;}
    wr(regs,QD_CORE,QD_QEC,r);wr(regs,QD_SYNDROME,0,r);
    snapshot_t a=snapshot(regs);
    if ((a.status&QD_BUSY) || a.core!=QD_QEC || a.syndrome!=0)
        return add_check(r,name,0,"QEC setup readback failed; START not written",a.count,&a);
    uint64_t begin;
    if (now_ns(&begin)) {r->reason="monotonic clock failed";r->exit_code=EXIT_CHECK;return 0;}
    wr(regs,QD_CONTROL,QD_START,r);r->started=1;
    const int waited=wait_idle(regs,begin,1,1);
    snapshot_t b=snapshot(regs);
    const uint32_t want_error=force_timeout?QD_ERR_TIMEOUT:0u;
    const int pass=waited==0 && terminal_matches(&b,a.count,want_error) &&
        b.result==QEC_ZERO_CORRECTION && b.score==0 &&
        (force_timeout?b.cycles==1u:b.cycles>0u);
    return add_check(r,name,pass,
        force_timeout?"timeout limit 1: done/timeout, count +1, cycles 1, zero outputs within 100 ms":
                      "syndrome 0: exact ROM correction 0, no error, count +1 within 100 ms",a.count,&b);
}
static int nv_abort(volatile uint32_t *regs,report_t *r) {
    wr(regs,QD_CORE,QD_NV,r);
    for (uint32_t i=0;i<QD_INPUT_WORDS;++i)wr(regs,QD_INPUT_BASE+4u*i,0,r);
    snapshot_t a=snapshot(regs);
    if ((a.status&QD_BUSY) || !(a.status&QD_INPUT_VALID) || a.core!=QD_NV)
        return add_check(r,"nv_input_setup",0,"64 zero input words did not establish ready input state",a.count,&a);
    if (interrupted) {r->reason="interrupted before NV start";r->exit_code=EXIT_CHECK;return 0;}
    uint64_t begin;
    if (now_ns(&begin)) {r->reason="monotonic clock failed";r->exit_code=EXIT_CHECK;return 0;}
    wr(regs,QD_CONTROL,QD_START,r);r->started=1;
    /* Keep BUSY observation and ABORT adjacent; do not print or sleep here. */
    const uint32_t observed=rd(regs,QD_STATUS);
    if (observed&QD_BUSY)wr(regs,QD_CONTROL,QD_ABORT,r);
    const int waited=wait_idle(regs,begin,1,1);
    snapshot_t b=snapshot(regs);
    return add_check(r,"active_nv_abort",(observed&QD_BUSY) && waited==0 &&
        terminal_matches(&b,a.count,QD_ERR_ABORTED) && b.result==0 && b.score==0,
        "observed NV busy before ABORT; aborted/count +1/zero outputs within 100 ms; scheduler race can fail this check",
        a.count,&b);
}
static void self_test(report_t *r) {
    add_check(r,"static_identity_and_layout",QD_ID_VALUE==UINT32_C(0x51465047) &&
        QD_ABI_VALUE==UINT32_C(0x00010000) && QD_INPUT_BASE==0x100u &&
        QD_INPUT_BASE+4u*(QD_INPUT_WORDS-1u)==0x1fcu,
        "fixed ABI identity and aligned 64-word input range; no MMIO",0,NULL);
    add_check(r,"static_qec_zero_reference",QEC_ZERO_CORRECTION==0,
        "syndrome 0 reference transcribed from frozen ROM and expected vector; no MMIO",0,NULL);
    snapshot_t a={.status=QD_DONE|QD_FAILED|QD_INPUT_VALID,.error=QD_ERR_ABORTED,
        .cycles=17,.count=UINT32_MAX,.core=QD_NV,.syndrome=0,.timeout=1000000,
        .result=123,.score=456};
    snapshot_t b=a;b.status=QD_INPUT_VALID;b.error=0;b.result=0;b.score=0;
    add_check(r,"static_clear_expectation",clear_matches(&a,&b),
        "validates expected CLEAR preservation predicate; no device behavior tested",a.count,NULL);
    b.count=0;b.status=QD_DONE|QD_FAILED;b.error=QD_ERR_TIMEOUT;b.cycles=1;
    add_check(r,"static_counter_wrap",terminal_matches(&b,UINT32_MAX,QD_ERR_TIMEOUT),
        "completed counter delta is modulo 2^32; no MMIO",0,NULL);
    if (!r->exit_code)r->reason="static expectations passed; no hardware opened or tested";
}
static void run_hardware(report_t *r) {
    int fd=-1;
    void *mapping=MAP_FAILED;
    volatile uint32_t *regs=NULL;
    const uint32_t endian=1;
    const long page=sysconf(_SC_PAGESIZE);
    if (page<=0 || QD_BASE%(uint64_t)page || QD_SPAN%(uint64_t)page ||
        *(const unsigned char*)&endian!=1) {
        r->reason="unsupported page size/alignment/byte order; no MMIO";r->exit_code=EXIT_DEVICE;return;
    }
    fd=open("/dev/mem",O_RDWR|O_SYNC);
    if (fd<0) {r->reason="cannot open /dev/mem";r->exit_code=EXIT_DEVICE;return;}
    r->opened=1;
    if (flock(fd,LOCK_EX|LOCK_NB)) {r->reason="exclusive /dev/mem lock unavailable";r->exit_code=EXIT_DEVICE;goto cleanup;}
    mapping=mmap(NULL,QD_SPAN,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)QD_BASE);
    if (mapping==MAP_FAILED) {r->reason="cannot map fixed register page";r->exit_code=EXIT_DEVICE;goto cleanup;}
    regs=(volatile uint32_t*)mapping;
    r->id=rd(regs,QD_ID);r->abi=rd(regs,QD_ABI);
    r->identity=r->id==QD_ID_VALUE && r->abi==QD_ABI_VALUE;
    if (!add_check(r,"identity_before_writes",r->identity,"ID and ABI must both match before any write",0,NULL))goto cleanup;
    snapshot_t initial=snapshot(regs);
    if (!add_check(r,"initial_idle",!(initial.status&QD_BUSY) && initial.timeout!=0,
        "initial busy or zero timeout stops without writes",initial.count,&initial))goto cleanup;
    r->original_timeout=initial.timeout;r->timeout_saved=1;
    if (interrupted) {r->reason="interrupted before writes";r->exit_code=EXIT_CHECK;goto cleanup;}
    if (!clear_checked(regs,r,"clear_initial"))goto cleanup;
    wr(regs,QD_TIMEOUT,1,r);r->timeout_changed=1;
    snapshot_t limited=snapshot(regs);
    if (!add_check(r,"timeout_one_readback",limited.timeout==1,
        "fabric timeout register reads back 1",limited.count,&limited))goto cleanup;
    if (!qec_call(regs,r,"forced_qec_timeout",1))goto cleanup;
    wr(regs,QD_TIMEOUT,r->original_timeout,r);
    snapshot_t restored=snapshot(regs);
    r->restored=restored.timeout==r->original_timeout;
    if (!add_check(r,"restore_timeout_before_success",r->restored,
        "original timeout restored before normal QEC call",restored.count,&restored))goto cleanup;
    if (!clear_checked(regs,r,"clear_after_timeout"))goto cleanup;
    if (!qec_call(regs,r,"qec_after_timeout",0))goto cleanup;
    if (!clear_checked(regs,r,"clear_after_success"))goto cleanup;
    if (!nv_abort(regs,r))goto cleanup;
    snapshot_t before=snapshot(regs);
    if (before.status&QD_BUSY) {r->reason="unexpected busy before idle ABORT";r->exit_code=EXIT_CHECK;goto cleanup;}
    wr(regs,QD_CONTROL,QD_ABORT,r);
    snapshot_t after=snapshot(regs);
    if (!add_check(r,"idle_abort_preserves_registers",same_snapshot(&before,&after),
        "idle ABORT resets cores without incrementing count or clearing previous status",before.count,&after))goto cleanup;
    if (!clear_checked(regs,r,"clear_after_abort"))goto cleanup;
    if (!qec_call(regs,r,"qec_after_idle_abort",0))goto cleanup;
    if (!clear_checked(regs,r,"clear_final"))goto cleanup;
    r->reason="all bounded fabric control checks passed";
cleanup:
    /* Never abort an initially busy device. Only clean up after our own START. */
    if (regs && r->identity && r->timeout_saved && r->writes) {
        uint32_t status=rd(regs,QD_STATUS);
        if ((status&QD_BUSY) && r->started) {
            uint64_t begin;
            if (!now_ns(&begin)) {
                wr(regs,QD_CONTROL,QD_ABORT,r);
                (void)wait_idle(regs,begin,0,0);
            }
            status=rd(regs,QD_STATUS);
        }
        /* TIMEOUT is writable only while idle. Do not force an illegal write. */
        if (!(status&QD_BUSY)) {
            if (r->timeout_changed)wr(regs,QD_TIMEOUT,r->original_timeout,r);
            r->restored=rd(regs,QD_TIMEOUT)==r->original_timeout;
        } else r->restored=0;
        snapshot_t end=snapshot(regs);
        (void)add_check(r,"exit_timeout_restoration",r->restored,
            "original timeout verified on exit; cannot restore while device remains busy",end.count,&end);
    }
    if (mapping!=MAP_FAILED)(void)munmap(mapping,QD_SPAN);
    if (fd>=0)(void)close(fd);
}
static void emit(const report_t *r,int is_self_test) {
    printf("{\n  \"schema\":\"quantum_demo_control_v1\",\n  \"mode\":\"%s\",\n",is_self_test?"static_no_mmio":"fabric_mmio");
    printf("  \"exit_code\":%d,\n  \"reason\":\"%s\",\n",r->exit_code,r->reason);
    printf("  \"base\":\"0x%08" PRIx64 "\",\n  \"span\":%u,\n  \"deadline_ms\":100,\n",(uint64_t)QD_BASE,QD_SPAN);
    printf("  \"hardware_opened\":%s,\n  \"identity_verified\":%s,\n  \"register_writes\":%s,\n  \"start_written\":%s,\n",
        r->opened?"true":"false",r->identity?"true":"false",r->writes?"true":"false",r->started?"true":"false");
    printf("  \"id\":%" PRIu32 ",\n  \"abi\":%" PRIu32 ",\n  \"original_timeout\":%" PRIu32 ",\n  \"timeout_restored\":%s,\n",
        r->id,r->abi,r->original_timeout,r->restored?"true":"false");
    printf("  \"cycle_scope\":\"fabric counter values only; no clock conversion or latency claim\",\n  \"checks\":[\n");
    for (unsigned i=0;i<r->count;++i) {
        const check_t *c=&r->checks[i];
        printf("    {\"name\":\"%s\",\"pass\":%s,\"detail\":\"%s\",\"hardware_snapshot\":%s",
            c->name,c->pass?"true":"false",c->detail,c->observed?"true":"false");
        if (c->observed)printf(",\"status\":%" PRIu32 ",\"error\":%" PRIu32 ",\"cycles\":%" PRIu32
            ",\"count_before\":%" PRIu32 ",\"count_after\":%" PRIu32 ",\"count_delta\":%" PRIu32
            ",\"result\":%" PRIu64 ",\"score\":%" PRIu64 ",\"timeout\":%" PRIu32,
            c->after.status,c->after.error,c->after.cycles,c->before,c->after.count,
            (uint32_t)(c->after.count-c->before),c->after.result,c->after.score,c->after.timeout);
        printf("}%s\n",i+1u<r->count?",":"");
    }
    printf("  ]\n}\n");
}
int main(int argc,char **argv) {
    if (argc!=2 || (strcmp(argv[1],"--self-test") && strcmp(argv[1],"--run"))) {
        fprintf(stderr,"usage: quantum_demo_control_test --self-test | --run\n--self-test never opens /dev/mem; --run requires the matching isolated image.\n");
        return EXIT_USAGE;
    }
    report_t report={0};report.reason="not started";
    const int is_self_test=!strcmp(argv[1],"--self-test");
    if (is_self_test)self_test(&report);
    else {
        struct sigaction action;
        memset(&action,0,sizeof(action));action.sa_handler=request_stop;sigemptyset(&action.sa_mask);
        if (sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL)) {
            report.reason="cannot install signal handlers; no MMIO";report.exit_code=EXIT_DEVICE;
        } else run_hardware(&report);
    }
    emit(&report,is_self_test);
    if (fflush(stdout) || ferror(stdout))return EXIT_CHECK;
    return report.exit_code;
}
