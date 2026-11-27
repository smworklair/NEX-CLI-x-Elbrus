/* Fused multiply-add latency: chain x = x*b + c.
   The compiler must space adjacent fmul_addd instructions by exact latency. */
volatile double bv = 1.000001, cv = 0.5;
double fma_chain(void) {
    double x = 1.0, b = bv, c = cv;
    for (int i = 0; i < 8; i++) x = x * b + c;
    return x;
}
