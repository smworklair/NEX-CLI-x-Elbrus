/* Load latency: chain of dependent dereferences (p = *p). */
volatile long chain[8];
int main(void) {
    volatile long **p = (volatile long **)chain;
    p = (volatile long **)*p; p = (volatile long **)*p;
    p = (volatile long **)*p; p = (volatile long **)*p;
    chain[0] = (long)p;
    return 0;
}
