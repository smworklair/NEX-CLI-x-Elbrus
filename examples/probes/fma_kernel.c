/* Real compute kernel: mix of arithmetic, memory, and division —
   the kind of workload the compiler scheduler actually operates on. */
#define N 16
double a[N], b[N], c[N], d[N];

void kernel(void) {
    for (int i = 0; i < N; i++) {
        double x = a[i] * b[i] + c[i];
        double y = a[i] - b[i] * c[i];
        double z = x / (y + 1.0);
        d[i] = z * x + y * b[i] - c[i] / (x + 2.0);
    }
}
