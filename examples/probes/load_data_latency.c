/* Латентность загрузки, когда результат потребляется КАК ДАННЫЕ (не как адрес).
   Пара к load_latency.c, где та же загрузка потребляется как адрес. */
volatile long v[8] = {1,2,3,4,5,6,7,8};
volatile long out;
int main(void) {
    long a = v[0] + 1;
    long b = v[1] + 1;
    long c = v[2] + 1;
    out = a + b + c;
    return 0;
}
