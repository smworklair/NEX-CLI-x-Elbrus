#include <stdio.h>

volatile int a[8] = {2,3,4,5,6,7,8,9};
volatile int b[8] = {11,12,13,14,15,16,17,18};

int main(void) {
    int d0 = a[0] / b[0];
    int d1 = a[1] / b[1];
    int d2 = a[2] / b[2];
    int d3 = a[3] / b[3];

    int m0 = a[4] * b[4];
    int m1 = a[5] * b[5];
    int m2 = a[6] * b[6];
    int m3 = a[7] * b[7];

    int sum = d0+d1+d2+d3+m0+m1+m2+m3;
    printf("sum = %d\n", sum);
    return 0;
}
