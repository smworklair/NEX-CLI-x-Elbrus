/* Латентность сращённого умножения-сложения: цепочка x = x*b + c.
   Компилятор обязан развести соседние fmul_addd ровно на латентность. */
volatile double bv = 1.000001, cv = 0.5;
double fma_chain(void) {
    double x = 1.0, b = bv, c = cv;
    for (int i = 0; i < 8; i++) x = x * b + c;
    return x;
}
