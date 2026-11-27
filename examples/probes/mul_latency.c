/* Multiplication latency: CHAIN of dependent multiplications. Each waits on
   the previous result, so the compiler MUST space them across cycles
   by exact latency — and will show this with explicit nop N stalls between them. */
volatile int a = 3, b = 5;
volatile int out;

int main(void) {
    int x = a * b;
    x = x * b;
    x = x * b;
    x = x * b;
    x = x * b;
    x = x * b;
    out = x;
    return 0;
}
