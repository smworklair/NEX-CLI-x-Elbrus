#include <stdio.h>

/* 8 independent int32 multiplications. volatile prevents the compiler from
   folding or eliminating them as dead code. Goal: if a multiplier exists on
   multiple channels, NOTHING prevents the compiler from packing several muls
   into one wide instruction at once (data are independent). If there is
   only one multiplier, they will still stretch across cycles with a fixed
   stride, as in the first four-op probe. */

volatile int a[8] = {2, 3, 4, 5, 6, 7, 8, 9};
volatile int b[8] = {11, 12, 13, 14, 15, 16, 17, 18};

int main(void) {
    int m0 = a[0] * b[0];
    int m1 = a[1] * b[1];
    int m2 = a[2] * b[2];
    int m3 = a[3] * b[3];
    int m4 = a[4] * b[4];
    int m5 = a[5] * b[5];
    int m6 = a[6] * b[6];
    int m7 = a[7] * b[7];

    int sum = m0 + m1 + m2 + m3 + m4 + m5 + m6 + m7;
    printf("sum = %d\n", sum);
    return 0;
}
