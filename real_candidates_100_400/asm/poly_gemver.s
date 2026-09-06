	.file	"poly_gemver.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x12, nfx = 0x0, dbl = 0x0
	  return	%ctpr3
	  ldd,2	0x0, [ _f64,_lts2 u1 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 v1 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 v1 +8 ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 u1 +8 ], %g19
	  ldd,2	0x0, [ _f64,_lts2 u2 ], %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 v2 ], %g21
	  ldd,2	0x0, [ _f64,_lts2 A ], %g22
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 u1 +16 ], %g23
	  ldd,2	0x0, [ _f64,_lts2 A +32 ], %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 u2 +8 ], %g25
	  ldd,2	0x0, [ _f64,_lts2 v2 +8 ], %g26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 v1 +16 ], %g28
	  fmuld,1	%g16, %g17, %g27
	  ldd,2	0x0, [ _f64,_lts2 A +8 ], %g29
	}
	{
	  fmuld,0	%g19, %g17, %g31
	  fmuld,1	%g16, %g18, %g30
	  ldd,2	0x0, [ _f64,_lts0 u1 +24 ], %r3
	  ldd,3	0x0, [ _f64,_lts2 A +64 ], %r4
	}
	{
	  fmuld,1	%g20, %g21, %r5
	  ldd,2	0x0, [ _f64,_lts2 u2 +16 ], %r6
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 v1 +24 ], %r7
	  ldd,2	0x0, [ _f64,_lts2 A +40 ], %r9
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +16 ], %g27
	  faddd,1	%g22, %g27, %g22
	  ldd,2	0x0, [ _f64,_lts2 v2 +16 ], %r10
	}
	{
	  fmuld,0	%g19, %g18, %r11
	  fmuld,1	%g23, %g17, %r12
	  fmuld,2	%g25, %g21, %r13
	  fmuld,3	%g20, %g26, %r14
	  fmuld,4	%g16, %g28, %r15
	  addd,5	0x0, _f64,_lts0 0x3ff8000000000000, %r16
	}
	{
	  faddd,0	%g29, %g30, %g29
	  faddd,1	%g24, %g31, %g24
	  ldd,5	0x0, [ _f64,_lts0 y ], %g30
	}
	{
	  ldd,2	0x0, [ _f64,_lts0 u2 +24 ], %g31
	  ldd,3	0x0, [ _f64,_lts2 A +96 ], %r17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +48 ], %r5
	  faddd,1	%g22, %r5, %g22
	  ldd,2	0x0, [ _f64,_lts2 A +72 ], %r18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +24 ], %r19
	  fmuld,1	%g23, %g18, %r21
	  ldd,2	0x0, [ _f64,_lts2 v2 +24 ], %r20
	  fmuld,3	%g19, %g28, %r22
	  fmuld,4	%g25, %g26, %r23
	  fmuld,5	%r3, %g17, %g17
	}
	{
	  fmuld,0	%r6, %g21, %r24
	  faddd,1	%r4, %r12, %r4
	  fmuld,2	%g16, %r7, %g16
	  faddd,3	%g27, %r15, %g27
	  fmuld,4	%g20, %r10, %r12
	}
	{
	  faddd,0	%g24, %r13, %g24
	  faddd,1	%r9, %r11, %r9
	  faddd,2	%g29, %r14, %g29
	  ldd,5	0x0, [ _f64,_lts0 x ], %r11
	}
	{
	  fmuld,1	%r16, %g22, %r13
	  ldd,3	0x0, [ _f64,_lts0 y +8 ], %r14
	  ldd,5	0x0, [ _f64,_lts2 A +80 ], %r15
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +104 ], %r25
	  fmuld,1	%g23, %g28, %r27
	  ldd,2	0x0, [ _f64,_lts2 A +56 ], %r26
	  fmuld,3	%r3, %g18, %g18
	  fmuld,4	%r6, %g26, %r28
	  fmuld,5	%g19, %r7, %g19
	}
	{
	  fmuld,0	%g25, %r10, %r29
	  fmuld,1	%g31, %g21, %g21
	  faddd,2	%r4, %r24, %r4
	  faddd,3	%r17, %g17, %g17
	  faddd,4	%r5, %r22, %r5
	  faddd,5	%g27, %r12, %g27
	}
	{
	  faddd,0	%r9, %r23, %r9
	  faddd,1	%r18, %r21, %r12
	  fmuld,2	%g20, %r20, %g20
	}
	{
	  fmuld,0	%r16, %g24, %r17
	  faddd,1	%r19, %g16, %g16
	  fmuld,2	%r16, %g29, %r18
	  ldd,3	0x0, [ _f64,_lts0 x +8 ], %r19
	  ldd,5	0x0, [ _f64,_lts2 A +112 ], %r21
	}
	{
	  fmuld,0	%r6, %r10, %r30
	  fmuld,1	%r13, %g30, %r22
	  fmuld,2	%g23, %r7, %g23
	  ldd,3	0x0, [ _f64,_lts0 y +16 ], %r23
	  fmuld,4	%r3, %g28, %g28
	  ldd,5	0x0, [ _f64,_lts2 A +88 ], %r24
	}
	{
	  fmuld,0	%g31, %g26, %g26
	  fmuld,1	%g25, %r20, %g25
	  fmuld,2	%r16, %r4, %r31
	  faddd,3	%r26, %g19, %g19
	  faddd,4	%r25, %g18, %g18
	  fmuld,5	%r16, %g27, %r25
	}
	{
	  fmuld,0	%r16, %r9, %r26
	  faddd,1	%r15, %r27, %r15
	  faddd,2	%r12, %r28, %r12
	  qppackdl,3	%g29, %g22, %g22
	}
	{
	  faddd,0	%r5, %r29, %g21
	  faddd,1	%g17, %g21, %g17
	  faddd,2	%g16, %g20, %g16
	  ldd,3	0x0, [ _f64,_lts0 x +16 ], %g20
	  ldd,5	0x0, [ _f64,_lts2 A +120 ], %g29
	}
	{
	  fmuld,0	%r18, %g30, %r27
	  fmuld,1	%r17, %r14, %r5
	  faddd,2	%r11, %r22, %r11
	  ldd,3	0x0, [ _f64,_lts0 y +24 ], %r22
	  fmuld,4	%r3, %r7, %r3
	  fmuld,5	%g31, %r10, %r7
	}
	{
	  faddd,0	%r24, %g23, %g23
	  fmuld,1	%r6, %r20, %r6
	  fmuld,2	%r31, %r23, %r10
	  fmuld,3	%r25, %g30, %r21
	  faddd,4	%r21, %g28, %g28
	  stqp,5	0x0, [ _f64,_lts0 A ], %g22
	}
	{
	  fmuld,0	%r26, %r14, %r15
	  faddd,1	%r15, %r30, %g22
	  fmuld,2	%r16, %r12, %r24
	  qppackdl,3	%r9, %g24, %g24
	  ldd,5	0x0, [ _f64,_lts0 x +24 ], %r28
	}
	{
	  faddd,0	%g18, %g26, %g18
	  fmuld,1	%r16, %g17, %g26
	  faddd,2	%g19, %g25, %g19
	  ldd,3	0x0, [ _f64,_lts0 z ], %g25
	  ldd,5	0x0, [ _f64,_lts2 z +8 ], %r9
	}
	{
	  fmuld,0	%r16, %g21, %r29
	  fmuld,1	%r16, %g16, %r30
	  faddd,2	%r19, %r27, %r19
	  faddd,3	%g29, %r3, %g29
	  fmuld,4	%g31, %r20, %g31
	  ldd,5	0x0, [ _f64,_lts0 w +24 ], %r3
	}
	{
	  faddd,0	%g23, %r6, %g23
	  faddd,1	%r11, %r5, %r5
	  stqp,2	0x0, [ _f64,_lts2 A +32 ], %g24
	  faddd,3	%g20, %r21, %g20
	  faddd,4	%g28, %r7, %g28
	  ldd,5	0x0, [ _f64,_lts0 w +16 ], %r6
	}
	{
	  fdtoistr,0	%g22, %r20
	  fmuld,1	%r16, %g22, %g24
	  fmuld,2	%r24, %r23, %r7
	  ldd,5	0x0, [ _f64,_lts0 w +8 ], %r11
	}
	{
	  fmuld,0	%r16, %g19, %r32
	  fmuld,1	%r16, %g18, %r21
	  fmuld,2	%g26, %r22, %r27
	  ldd,3	0x0, [ _f64,_lts2 z +16 ], %r34
	  ldd,5	0x0, [ _f64,_lts0 w ], %r33
	}
	{
	  faddd,0	%r19, %r15, %r15
	  fmuld,1	%r29, %r14, %r35
	  fmuld,2	%r30, %g30, %g30
	  ldd,3	0x0, [ _f64,_lts0 z +24 ], %g31
	  qppackdl,4	%r12, %r4, %r4
	  faddd,5	%g29, %g31, %g29
	}
	{
	  fmuld,0	%r16, %g23, %r12
	  faddd,2	%r5, %r10, %r5
	  qppackdl,4	%g16, %g27, %g16
	  fmuld,5	%r16, %g28, %r10
	}
	{
	  fmuld,2	%g24, %r23, %g27
	  qppackdl,3	%g18, %g17, %g17
	  qppackdl,4	%g19, %g21, %g18
	  stqp,5	0x0, [ _f64,_lts0 A +64 ], %r4
	}
	{
	  fmuld,0	%r21, %r22, %g19
	  fmuld,1	%r32, %r14, %g21
	  qppackdl,3	%g23, %g22, %g22
	  stqp,5	0x0, [ _f64,_lts0 A +16 ], %g16
	}
	{
	  faddd,0	%r28, %g30, %g16
	  faddd,1	%g20, %r35, %g20
	  faddd,2	%r15, %r7, %g23
	  fmuld,3	%r16, %g29, %g30
	  qppackdl,4	%g29, %g28, %g28
	  stqp,5	0x0, [ _f64,_lts0 A +96 ], %g17
	}
	{
	  faddd,0	%r5, %r27, %g17
	  fmuld,1	%r12, %r23, %r4
	  stqp,2	0x0, [ _f64,_lts0 A +48 ], %g18
	  fmuld,3	%r10, %r22, %g29
	  sxt,4	0x2, %r20, %r0
	  stqp,5	0x0, [ _f64,_lts2 A +80 ], %g22
	}
	{
	  nop 1
	  stqp,5	0x0, [ _f64,_lts0 A +112 ], %g28
	}
	{
	  faddd,0	%g16, %g21, %g16
	  faddd,1	%g20, %g27, %g18
	  faddd,2	%g23, %g19, %g19
	  fmuld,3	%g30, %r22, %g20
	}
	{
	  nop 2
	  faddd,0	%g17, %g25, %g17
	}
	{
	  faddd,0	%g16, %r4, %g16
	  faddd,1	%g18, %g29, %g18
	  faddd,2	%g19, %r9, %g19
	}
	{
	  fmuld,0	%r17, %g17, %g21
	  fmuld,1	%r31, %g17, %g22
	  fmuld,2	%g26, %g17, %g23
	}
	{
	  nop 1
	  fmuld,0	%r13, %g17, %g25
	}
	{
	  faddd,0	%g16, %g20, %g16
	  fmuld,1	%r21, %g19, %g20
	  faddd,2	%g18, %r34, %g18
	}
	{
	  fmuld,0	%r18, %g19, %g26
	  faddd,1	%r11, %g21, %g21
	  fmuld,2	%r26, %g19, %g27
	}
	{
	  faddd,0	%r6, %g22, %g22
	  faddd,1	%r3, %g23, %g23
	  fmuld,2	%r24, %g19, %g28
	  qppackdl,3	%g19, %g17, %g17
	}
	{
	  faddd,0	%r33, %g25, %g19
	  stqp,5	0x0, [ _f64,_lts0 x ], %g17
	}
	{
	  fmuld,0	%r29, %g18, %g17
	  fmuld,1	%g24, %g18, %g24
	  fmuld,2	%r10, %g18, %g25
	}
	{
	  faddd,0	%g16, %g31, %g16
	  fmuld,1	%r25, %g18, %g29
	  faddd,2	%g21, %g27, %g21
	}
	{
	  faddd,0	%g22, %g28, %g22
	  faddd,1	%g23, %g20, %g20
	}
	{
	  nop 1
	  faddd,0	%g19, %g26, %g19
	}
	{
	  fmuld,0	%r12, %g16, %g26
	  fmuld,1	%g30, %g16, %g27
	  fmuld,2	%r32, %g16, %g23
	}
	{
	  faddd,0	%g22, %g24, %g22
	  faddd,1	%g20, %g25, %g20
	  fmuld,2	%r30, %g16, %g28
	}
	{
	  faddd,0	%g21, %g17, %g17
	  faddd,2	%g19, %g29, %g19
	  qppackdl,3	%g16, %g18, %g16
	}
	{
	  nop 1
	  stqp,5	0x0, [ _f64,_lts0 x +16 ], %g16
	}
	{
	  faddd,0	%g22, %g26, %g16
	  faddd,1	%g20, %g27, %g18
	}
	{
	  nop 2
	  faddd,0	%g19, %g28, %g19
	  faddd,1	%g17, %g23, %g17
	}
	{
	  qppackdl,0	%g18, %g16, %g16
	}
	{
	  qppackdl,0	%g17, %g19, %g17
	  stqp,2	0x0, [ _f64,_lts0 w +16 ], %g16
	}
	{
	  ct	%ctpr3
	  stqp,2	0x0, [ _f64,_lts0 w ], %g17
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x80
	.align	16
A:
	.skip	0x80
	.global	u1
	.type	u1, #object
	.size	u1, 0x20
	.align	16
u1:
	.skip	0x20
	.global	v1
	.type	v1, #object
	.size	v1, 0x20
	.align	16
v1:
	.skip	0x20
	.global	u2
	.type	u2, #object
	.size	u2, 0x20
	.align	16
u2:
	.skip	0x20
	.global	v2
	.type	v2, #object
	.size	v2, 0x20
	.align	16
v2:
	.skip	0x20
	.global	w
	.type	w, #object
	.size	w, 0x20
	.align	16
w:
	.skip	0x20
	.global	x
	.type	x, #object
	.size	x, 0x20
	.align	16
x:
	.skip	0x20
	.global	y
	.type	y, #object
	.size	y, 0x20
	.align	16
y:
	.skip	0x20
	.global	z
	.type	z, #object
	.size	z, 0x20
	.align	16
z:
	.skip	0x20
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
