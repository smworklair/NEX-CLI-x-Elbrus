/* Пропускная способность делителя: 8 НЕзависимых делений. */
volatile int a[8] = {100,200,300,400,500,600,700,800};
volatile int b[8] = {3,3,3,3,3,3,3,3};
volatile int out[8];
int main(void) {
    int d0=a[0]/b[0], d1=a[1]/b[1], d2=a[2]/b[2], d3=a[3]/b[3];
    int d4=a[4]/b[4], d5=a[5]/b[5], d6=a[6]/b[6], d7=a[7]/b[7];
    out[0]=d0; out[1]=d1; out[2]=d2; out[3]=d3;
    out[4]=d4; out[5]=d5; out[6]=d6; out[7]=d7;
    return 0;
}
