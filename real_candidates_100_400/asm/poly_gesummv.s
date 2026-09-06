	.file	"poly_gesummv.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xf, nfx = 0x0, dbl = 0x0
	  return	%ctpr3
	  ldd,2	0x0, [ _f64,_lts2 A +240 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +240 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 A +192 ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +192 ], %g19
	  ldd,2	0x0, [ _f64,_lts2 A +144 ], %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +144 ], %g21
	  ldd,2	0x0, [ _f64,_lts2 A +96 ], %g22
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +96 ], %g23
	  ldd,2	0x0, [ _f64,_lts2 A +48 ], %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +48 ], %g25
	  ldd,2	0x0, [ _f64,_lts2 A ], %g26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B ], %g27
	  ldd,2	0x0, [ _f64,_lts2 x ], %g28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +248 ], %g29
	  ldd,2	0x0, [ _f64,_lts2 B +200 ], %g30
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +248 ], %g31
	  ldd,2	0x0, [ _f64,_lts2 B +152 ], %r3
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +200 ], %r4
	  ldd,2	0x0, [ _f64,_lts2 B +104 ], %r5
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +152 ], %r6
	  ldd,2	0x0, [ _f64,_lts2 B +56 ], %r7
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +104 ], %r9
	  fmuld,1	%g18, %g28, %g18
	  ldd,2	0x0, [ _f64,_lts2 B +8 ], %r10
	  fmuld,3	%g19, %g28, %g19
	  fmuld,4	%g16, %g28, %g16
	  fmuld,5	%g17, %g28, %g17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +56 ], %r11
	  fmuld,1	%g22, %g28, %g22
	  ldd,2	0x0, [ _f64,_lts2 x +8 ], %r12
	  fmuld,3	%g23, %g28, %g23
	  fmuld,4	%g20, %g28, %g20
	  fmuld,5	%g21, %g28, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +8 ], %r13
	  fmuld,1	%g26, %g28, %g26
	  fmuld,2	%g27, %g28, %g27
	  fmuld,3	%g25, %g28, %g25
	  fmuld,4	%g24, %g28, %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 B +256 ], %g28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +208 ], %r14
	  faddd,1	%g18, 0x0, %g18
	  ldd,2	0x0, [ _f64,_lts2 A +256 ], %r15
	  faddd,3	%g16, 0x0, %g16
	  faddd,4	%g19, 0x0, %g19
	  faddd,5	%g17, 0x0, %g17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +160 ], %r16
	  faddd,1	%g22, 0x0, %g22
	  ldd,2	0x0, [ _f64,_lts2 A +208 ], %r17
	  faddd,3	%g20, 0x0, %g20
	  faddd,4	%g23, 0x0, %g23
	  faddd,5	%g21, 0x0, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +112 ], %r18
	  fmuld,1	%r4, %r12, %r4
	  ldd,2	0x0, [ _f64,_lts2 A +160 ], %r19
	  fmuld,3	%g30, %r12, %g30
	  fmuld,4	%g31, %r12, %g31
	  fmuld,5	%g29, %r12, %g29
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +64 ], %r20
	  fmuld,1	%r9, %r12, %r9
	  ldd,2	0x0, [ _f64,_lts2 A +112 ], %r21
	  fmuld,3	%r5, %r12, %r5
	  fmuld,4	%r6, %r12, %r6
	  fmuld,5	%r3, %r12, %r3
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +16 ], %r22
	  fmuld,1	%r13, %r12, %r13
	  ldd,2	0x0, [ _f64,_lts2 A +64 ], %r23
	  fmuld,3	%r10, %r12, %r10
	  fmuld,4	%r11, %r12, %r11
	  fmuld,5	%r7, %r12, %r7
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 x +16 ], %r12
	  faddd,1	%g26, 0x0, %g26
	  ldd,2	0x0, [ _f64,_lts2 A +16 ], %r24
	  faddd,3	%g24, 0x0, %g24
	  faddd,4	%g27, 0x0, %g27
	  faddd,5	%g25, 0x0, %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +264 ], %r25
	  faddd,1	%r4, %g18, %g18
	  ldd,2	0x0, [ _f64,_lts2 B +264 ], %r26
	  faddd,3	%g31, %g16, %g16
	  faddd,4	%g30, %g19, %g19
	  faddd,5	%g29, %g17, %g17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +216 ], %g29
	  faddd,1	%r9, %g22, %g22
	  ldd,2	0x0, [ _f64,_lts2 B +216 ], %g30
	  faddd,3	%r6, %g20, %g20
	  faddd,4	%r5, %g23, %g23
	  faddd,5	%r3, %g21, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +168 ], %g31
	  ldd,2	0x0, [ _f64,_lts2 B +168 ], %r3
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +120 ], %r4
	  faddd,1	%r13, %g26, %g26
	  ldd,2	0x0, [ _f64,_lts2 B +120 ], %r5
	  faddd,3	%r11, %g24, %g24
	  faddd,4	%r10, %g27, %g27
	  faddd,5	%r7, %g25, %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +72 ], %r6
	  fmuld,1	%r17, %r12, %r9
	  ldd,2	0x0, [ _f64,_lts2 B +72 ], %r7
	  fmuld,3	%r14, %r12, %r10
	  fmuld,4	%r15, %r12, %r11
	  fmuld,5	%g28, %r12, %g28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +24 ], %r13
	  fmuld,1	%r21, %r12, %r15
	  ldd,2	0x0, [ _f64,_lts2 B +24 ], %r14
	  fmuld,3	%r18, %r12, %r17
	  fmuld,4	%r19, %r12, %r18
	  fmuld,5	%r16, %r12, %r16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 x +24 ], %r19
	  fmuld,1	%r24, %r12, %r24
	  fmuld,2	%r22, %r12, %r22
	  fmuld,3	%r20, %r12, %r12
	  fmuld,4	%r23, %r12, %r23
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +272 ], %r20
	  ldd,5	0x0, [ _f64,_lts2 B +272 ], %r27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +224 ], %r28
	  faddd,1	%r9, %g18, %g18
	  ldd,2	0x0, [ _f64,_lts2 B +224 ], %r29
	  faddd,3	%r11, %g16, %g16
	  faddd,4	%r10, %g19, %g19
	  faddd,5	%g28, %g17, %g17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +176 ], %g28
	  faddd,1	%r15, %g22, %g22
	  ldd,2	0x0, [ _f64,_lts2 B +176 ], %r9
	  faddd,3	%r18, %g20, %g20
	  faddd,4	%r17, %g23, %g23
	  faddd,5	%r16, %g21, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +128 ], %r10
	  faddd,1	%r24, %g26, %g26
	  ldd,2	0x0, [ _f64,_lts2 B +128 ], %r11
	  faddd,3	%r23, %g24, %g24
	  faddd,4	%r12, %g25, %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +80 ], %r12
	  faddd,1	%r22, %g27, %g27
	  ldd,2	0x0, [ _f64,_lts2 B +80 ], %r15
	  fmuld,3	%g30, %r19, %g30
	  fmuld,4	%r25, %r19, %r16
	  fmuld,5	%r26, %r19, %r17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +32 ], %r18
	  fmuld,1	%r5, %r19, %r5
	  ldd,2	0x0, [ _f64,_lts2 B +32 ], %r22
	  fmuld,3	%g31, %r19, %g31
	  fmuld,4	%r3, %r19, %r3
	  fmuld,5	%g29, %r19, %g29
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 x +32 ], %r23
	  fmuld,1	%r13, %r19, %r13
	  fmuld,2	%r14, %r19, %r14
	  fmuld,3	%r7, %r19, %r7
	  fmuld,4	%r6, %r19, %r6
	  fmuld,5	%r4, %r19, %r4
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 B +280 ], %r19
	  fdtoistr,1	%r21, %r21
	  addd,2	0x0, _f64,_lts0 0x3ff8000000000000, %r24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +232 ], %r25
	  ldd,2	0x0, [ _f64,_lts2 A +280 ], %r26
	  faddd,3	%g30, %g19, %g19
	  faddd,4	%r16, %g16, %g16
	  faddd,5	%r17, %g17, %g17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +184 ], %g30
	  faddd,1	%r5, %g23, %g23
	  ldd,2	0x0, [ _f64,_lts2 A +232 ], %r16
	  faddd,3	%g31, %g20, %g20
	  faddd,4	%r3, %g21, %g21
	  faddd,5	%g29, %g18, %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +136 ], %g29
	  faddd,1	%r13, %g26, %g26
	  ldd,2	0x0, [ _f64,_lts2 A +184 ], %g31
	  faddd,3	%r6, %g24, %g24
	  faddd,4	%r4, %g22, %g22
	  faddd,5	%r7, %g25, %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +88 ], %r3
	  faddd,1	%r14, %g27, %g27
	  ldd,2	0x0, [ _f64,_lts2 A +136 ], %r4
	  fmuld,3	%r29, %r23, %r5
	  fmuld,4	%r20, %r23, %r6
	  fmuld,5	%r27, %r23, %r7
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +40 ], %r13
	  fmuld,1	%r11, %r23, %r11
	  ldd,2	0x0, [ _f64,_lts2 A +88 ], %r14
	  fmuld,3	%g28, %r23, %g28
	  fmuld,4	%r9, %r23, %r9
	  fmuld,5	%r28, %r23, %r17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 x +40 ], %r20
	  fmuld,1	%r22, %r23, %r22
	  ldd,2	0x0, [ _f64,_lts2 A +40 ], %r27
	  fmuld,3	%r12, %r23, %r12
	  fmuld,4	%r15, %r23, %r15
	  fmuld,5	%r10, %r23, %r10
	}
	{
	  fmuld,0	%r18, %r23, %r18
	}
	{
	  sxt,0	0x2, %r21, %r0
	  faddd,3	%r5, %g19, %g19
	  faddd,4	%r6, %g16, %g16
	  faddd,5	%r7, %g17, %g17
	}
	{
	  faddd,0	%r11, %g23, %g23
	  faddd,3	%g28, %g20, %g20
	  faddd,4	%r9, %g21, %g21
	  faddd,5	%r17, %g18, %g18
	}
	{
	  faddd,0	%r22, %g27, %g27
	  faddd,3	%r12, %g24, %g24
	  faddd,4	%r15, %g25, %g25
	  faddd,5	%r10, %g22, %g22
	}
	{
	  fmuld,0	%g31, %r20, %g28
	  fmuld,1	%g30, %r20, %g30
	  fmuld,2	%r16, %r20, %g31
	  fmuld,3	%r25, %r20, %r5
	  fmuld,4	%r26, %r20, %r6
	  fmuld,5	%r19, %r20, %r7
	}
	{
	  fmuld,0	%r27, %r20, %r9
	  fmuld,1	%r13, %r20, %r10
	  fmuld,2	%r14, %r20, %r11
	  fmuld,3	%r3, %r20, %r3
	  fmuld,4	%r4, %r20, %r4
	  fmuld,5	%g29, %r20, %g29
	}
	{
	  nop 1
	  faddd,0	%r18, %g26, %g26
	}
	{
	  faddd,0	%g28, %g20, %g20
	  faddd,1	%g30, %g21, %g21
	  faddd,2	%g31, %g18, %g18
	  faddd,3	%r5, %g19, %g19
	  faddd,4	%r6, %g16, %g16
	  faddd,5	%r7, %g17, %g17
	}
	{
	  faddd,0	%r10, %g27, %g27
	  faddd,1	%r11, %g24, %g24
	  faddd,3	%r3, %g25, %g25
	  faddd,4	%r4, %g22, %g22
	  faddd,5	%g29, %g23, %g23
	}
	{
	  nop 1
	  faddd,0	%r9, %g26, %g26
	}
	{
	  fmuld,0	%r24, %g20, %g28
	  fmuld,1	%r24, %g21, %g21
	  fmuld,2	%r24, %g18, %g29
	  fmuld,3	%r24, %g19, %g19
	  fmuld,4	%r24, %g16, %g30
	  fmuld,5	%r24, %g17, %g17
	}
	{
	  fmuld,0	%r24, %g27, %g27
	  fmuld,1	%r24, %g24, %g31
	  fmuld,3	%r24, %g25, %g25
	  fmuld,4	%r24, %g22, %r3
	  fmuld,5	%r24, %g23, %g23
	}
	{
	  nop 1
	  fmuld,2	%r24, %g26, %r4
	}
	{
	  qppackdl,0	%g20, %g22, %g20
	  qppackdl,1	%g16, %g18, %g16
	  faddd,2	%g28, %g21, %g21
	  qppackdl,3	%g24, %g26, %g18
	  faddd,5	%g30, %g17, %g17
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 tmp +16 ], %g20
	  faddd,3	%r3, %g23, %g22
	  stqp,5	0x0, [ _f64,_lts2 tmp ], %g18
	}
	{
	  faddd,0	%g29, %g19, %g18
	  faddd,1	%r4, %g27, %g19
	  stqp,2	0x0, [ _f64,_lts0 tmp +32 ], %g16
	}
	{
	  nop 2
	  faddd,0	%g31, %g25, %g16
	}
	{
	  qppackdl,0	%g17, %g18, %g17
	  qppackdl,3	%g21, %g22, %g20
	}
	{
	  qppackdl,0	%g16, %g19, %g16
	  stqp,2	0x0, [ _f64,_lts2 y +32 ], %g17
	  stqp,5	0x0, [ _f64,_lts0 y +16 ], %g20
	}
	{
	  ct	%ctpr3
	  stqp,2	0x0, [ _f64,_lts0 y ], %g16
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x120
	.align	16
A:
	.skip	0x120
	.global	B
	.type	B, #object
	.size	B, 0x120
	.align	16
B:
	.skip	0x120
	.global	tmp
	.type	tmp, #object
	.size	tmp, 0x30
	.align	16
tmp:
	.skip	0x30
	.global	x
	.type	x, #object
	.size	x, 0x30
	.align	16
x:
	.skip	0x30
	.global	y
	.type	y, #object
	.size	y, 0x30
	.align	16
y:
	.skip	0x30
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
