/* Exercise the real replay function with a fake MMIO page and scripted clock.
 * No /dev/mem access, real mmap, sleep, or hardware is possible in this binary.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#define _DEFAULT_SOURCE
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE
#endif
#include <assert.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static int fake_open(const char *,int,...);
static int fake_close(int);
static int fake_flock(int,int);
static void *fake_mmap(void *,size_t,int,int,int,off_t);
static int fake_munmap(void *,size_t);
static long fake_sysconf(int);
static int fake_clock_gettime(clockid_t,struct timespec *);
#define open fake_open
#define close fake_close
#define flock fake_flock
#define mmap fake_mmap
#define munmap fake_munmap
#define sysconf fake_sysconf
#define clock_gettime fake_clock_gettime
#define main included_runner_main
#include "quantum_demo_run.c"
#undef main
#undef open
#undef close
#undef flock
#undef mmap
#undef munmap
#undef sysconf
#undef clock_gettime

static uint32_t fake_regs[QD_SPAN/sizeof(uint32_t)];
static uint64_t clock_script[8];
static unsigned clock_count,clock_calls,signal_at,open_calls,close_calls;

static int fake_open(const char *path,int flags,...) {
    assert(!strcmp(path,"/dev/mem"));assert(flags==(O_RDWR|O_SYNC));
    ++open_calls;return 77;
}
static int fake_close(int fd) {assert(fd==77);++close_calls;return 0;}
static int fake_flock(int fd,int flags) {assert(fd==77);assert(flags==(LOCK_EX|LOCK_NB));return 0;}
static void *fake_mmap(void *address,size_t length,int prot,int flags,int fd,off_t offset) {
    assert(address==NULL && length==QD_SPAN && prot==(PROT_READ|PROT_WRITE));
    assert(flags==MAP_SHARED && fd==77 && (uint64_t)offset==QD_BASE);return fake_regs;
}
static int fake_munmap(void *address,size_t length) {assert(address==fake_regs && length==QD_SPAN);return 0;}
static long fake_sysconf(int name) {assert(name==_SC_PAGESIZE);return 4096;}
static int fake_clock_gettime(clockid_t id,struct timespec *ts) {
    assert(id==CLOCK_MONOTONIC);assert(clock_calls<clock_count);
    const uint64_t value=clock_script[clock_calls++];
    ts->tv_sec=(time_t)(value/UINT64_C(1000000000));
    ts->tv_nsec=(long)(value%UINT64_C(1000000000));
    /* The second clock read precedes START. Pre-arm the page to represent
     * immediate device completion when the next status read occurs.
     * This catches a runner that accepts DONE before checking time/signal.
     */
    if (clock_calls==2) {
        fake_regs[QD_STATUS/4]=QD_DONE;
        fake_regs[QD_COMPLETED_COUNT/4]=1;
        fake_regs[QD_CYCLES/4]=5;
    }
    if (signal_at && clock_calls==signal_at)interrupted=1;
    return 0;
}
static void run_case(const char *name,const uint64_t *times,unsigned n,unsigned interrupt_call,
                     int expected_exit,uint32_t expected_control) {
    memset(fake_regs,0,sizeof(fake_regs));
    fake_regs[QD_ID/4]=QD_ID_VALUE;fake_regs[QD_ABI/4]=QD_ABI_VALUE;
    fake_regs[QD_TIMEOUT/4]=1000000;
    memcpy(clock_script,times,n*sizeof(*times));clock_count=n;clock_calls=0;
    open_calls=0;close_calls=0;signal_at=interrupt_call;interrupted=0;
    options_t options={.core=QD_QEC,.repeat=1,.timeout_ms=100,.core_name="qec"};
    unsigned char input_bytes[1]={0},expected_bytes[4]={0};
    blob_t input={input_bytes,sizeof(input_bytes)},expected={expected_bytes,sizeof(expected_bytes)},scores={0};
    uint64_t host_ns[1]={0},call_ns[1]={0};
    result_t result={.planned=1,.host_ns=host_ns,.call_ns=call_ns,.cycle_min=UINT32_MAX,.reason="not started"};
    FILE *csv=tmpfile();assert(csv!=NULL);
    const int actual=replay(&options,&input,&expected,&scores,1,csv,&result);
    assert(actual==expected_exit && result.exit_code==expected_exit);
    assert(result.identity_verified && result.attempted==1);
    assert(result.completed==(expected_exit==0?1u:0u));
    assert(result.timed==(expected_exit==0?1u:0u));
    assert(fake_regs[QD_CONTROL/4]==expected_control);
    assert(fake_regs[QD_TIMEOUT/4]==1000000);
    assert(open_calls==1 && close_calls==1 && clock_calls<=n);
    assert(fclose(csv)==0);
    printf("{\"case\":\"%s\",\"passed\":true,\"exit_code\":%d,\"clock_calls\":%u,\"mmio\":false}\n",name,actual,clock_calls);
}
int main(void) {
    const uint64_t success[]={0,100,200,300};
    const uint64_t late_done[]={0,100,UINT64_C(100000101),UINT64_C(100000102)};
    const uint64_t boundary_done[]={0,100,UINT64_C(100000100),UINT64_C(100000101)};
    const uint64_t signal_done[]={0,100,200,300};
    const uint64_t late_output[]={0,100,200,UINT64_C(100000100),UINT64_C(100000101)};
    const uint64_t signal_output[]={0,100,200,300,400};
    run_case("done_within_deadline",success,4,0,0,QD_START);
    run_case("done_observed_after_deadline",late_done,4,0,E_TIMEOUT,QD_ABORT);
    run_case("done_at_deadline",boundary_done,4,0,E_TIMEOUT,QD_ABORT);
    run_case("signal_before_done_acceptance",signal_done,4,2,E_TIMEOUT,QD_ABORT);
    run_case("deadline_during_output_read",late_output,5,0,E_TIMEOUT,QD_START);
    run_case("signal_during_output_read",signal_output,5,4,E_TIMEOUT,QD_START);
    return 0;
}
