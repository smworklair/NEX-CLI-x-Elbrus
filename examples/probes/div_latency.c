/* Латентность деления: цепочка зависимых делений. */
volatile int a = 1000000, b = 3;
volatile int out;
int main(void) {
    int x = a / b;
    x = x / b;
    x = x / b;
    x = x / b;
    x = x / b;
    out = x;
    return 0;
}
