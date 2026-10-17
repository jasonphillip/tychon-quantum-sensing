// Portable replay reference: no hardware access, no dependence on native endianness.
#include <stdint.h>
#include <stdio.h>
#include "../boxcar_readout64.cpp"

static uint64_t le64(const unsigned char b[8]) {
    uint64_t result=0;
    for (unsigned i=0;i<8;++i) result|=(uint64_t)b[i]<<(8*i);
    return result;
}

int main(int argc,char **argv) {
    if (argc!=3) { fprintf(stderr,"usage: replay_reference inputs_i16.bin expected_scores_i64.bin\n"); return 2; }
    FILE *input=fopen(argv[1],"rb");
    FILE *expected=fopen(argv[2],"rb");
    if (!input || !expected) { if(input)fclose(input);if(expected)fclose(expected);return 3; }
    unsigned long count=0,failed=0;
    unsigned char bytes[256],gold[8];
    int16_t values[128];
    for (;;) {
        const size_t got=fread(bytes,1,sizeof(bytes),input);
        if (!got) break;
        if (got!=sizeof(bytes) || fread(gold,1,8,expected)!=8) { fclose(input);fclose(expected);return 4; }
        for (unsigned k=0;k<128;++k) {
            const uint16_t u=(uint16_t)bytes[2*k]|((uint16_t)bytes[2*k+1]<<8);
            const int32_t s=(u&0x8000) ? (int32_t)u-65536 : (int32_t)u;
            values[k]=(int16_t)s;
        }
        const int64_t result=boxcar_readout64(values,-16384,2811,INT64_C(214072292));
        if ((uint64_t)result!=le64(gold)) ++failed;
        ++count;
    }
    const bool invalid=ferror(input)||ferror(expected)||fgetc(expected)!=EOF||count==0;
    fclose(input);fclose(expected);
    printf("%lu/%lu frozen readout scores bit-exact; portable host reference only\n",count-failed,count);
    return invalid ? 4 : (failed ? 1 : 0);
}
