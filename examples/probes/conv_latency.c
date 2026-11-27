/* Format conversion latency: int->double->int chain.
   Each subsequent conversion waits on the previous result. */
volatile double dv = 3.5;
int main(void) {
    double d = dv; int i = 0;
    for (int k = 0; k < 6; k++) { i = (int)d; d = (double)i + 1.0; }
    dv = d; return i;
}
