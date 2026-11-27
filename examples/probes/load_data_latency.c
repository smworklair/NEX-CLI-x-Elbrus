/* Load latency when the result is consumed AS DATA (not as an address).
   Counterpart to load_latency.c, where the same load is consumed as an address. */
volatile long v[8] = {1,2,3,4,5,6,7,8};
volatile long out;
int main(void) {
    long a = v[0] + 1;
    long b = v[1] + 1;
    long c = v[2] + 1;
    out = a + b + c;
    return 0;
}
