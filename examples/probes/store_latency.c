/* Store latency: visibility via store->load to the SAME memory location.
 * volatile prevents the compiler from eliminating memory accesses or reordering
 * the store and subsequent load. The chain forces the next store not to
 * happen until the previous value has actually been read —
 * so the stride between bundles reflects true store visibility, not a compiler
 * scheduler choice.
 */
volatile int mem;
int main(void) {
    int x = 1;
    for (int i = 0; i < 8; i++) {
        mem = x;
        x = mem + 1;
    }
    return x;
}
