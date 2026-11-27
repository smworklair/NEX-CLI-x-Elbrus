/* Store throughput: 16 independent stores to distinct addresses.
 * Method — same as div8.c: first ALL reads into local variables (let the
 * compiler issue them in parallel), then ALL result stores —
 * so the stride between stores does not hide load-latency stalls.
 */
volatile int out[16];
volatile int src[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
int main(void) {
    int v0=src[0],  v1=src[1],  v2=src[2],  v3=src[3];
    int v4=src[4],  v5=src[5],  v6=src[6],  v7=src[7];
    int v8=src[8],  v9=src[9],  v10=src[10], v11=src[11];
    int v12=src[12], v13=src[13], v14=src[14], v15=src[15];
    out[0]=v0;  out[1]=v1;  out[2]=v2;  out[3]=v3;
    out[4]=v4;  out[5]=v5;  out[6]=v6;  out[7]=v7;
    out[8]=v8;  out[9]=v9;  out[10]=v10; out[11]=v11;
    out[12]=v12; out[13]=v13; out[14]=v14; out[15]=v15;
    return 0;
}
