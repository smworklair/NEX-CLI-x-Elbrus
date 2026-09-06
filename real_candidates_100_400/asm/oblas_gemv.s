	.file	"oblas_gemv.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x0
	  return	%ctpr3
	  ldd,2	0x0, [ _f64,_lts2 X ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +16 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 X +8 ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +80 ], %g19
	  ldd,2	0x0, [ _f64,_lts2 A +48 ], %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +56 ], %g21
	  ldd,2	0x0, [ _f64,_lts2 A +32 ], %g22
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +40 ], %g23
	  ldd,2	0x0, [ _f64,_lts2 A +8 ], %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +24 ], %g25
	  ldd,2	0x0, [ _f64,_lts2 A ], %g26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +144 ], %g27
	  fmuld,1	%g17, %g16, %g17
	  ldd,2	0x0, [ _f64,_lts2 X +16 ], %g28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +120 ], %g29
	  fmuld,1	%g19, %g18, %g19
	  ldd,2	0x0, [ _f64,_lts2 A +104 ], %g30
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +112 ], %g31
	  fmuld,1	%g20, %g16, %g20
	  ldd,2	0x0, [ _f64,_lts2 A +88 ], %r3
	  fmuld,3	%g22, %g16, %g22
	  fmuld,4	%g21, %g16, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +96 ], %r4
	  fmuld,1	%g23, %g16, %g23
	  ldd,2	0x0, [ _f64,_lts2 A +64 ], %r5
	  fmuld,4	%g24, %g16, %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +72 ], %r6
	  faddd,1	0x0, %g17, %g17
	  fmuld,2	%g25, %g16, %g25
	  ldd,3	0x0, [ _f64,_lts2 X +24 ], %g26
	  fmuld,4	%g26, %g16, %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 A +208 ], %r7
	  fmuld,1	%g27, %g28, %g27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +176 ], %r9
	  fmuld,1	%g29, %g18, %g29
	  ldd,2	0x0, [ _f64,_lts2 A +184 ], %r10
	  faddd,3	0x0, %g22, %g22
	  fmuld,4	%g30, %g18, %g30
	  faddd,5	0x0, %g21, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +160 ], %r11
	  faddd,1	0x0, %g20, %g20
	  ldd,2	0x0, [ _f64,_lts2 A +168 ], %r12
	  fmuld,3	%r3, %g18, %r3
	  fmuld,4	%g31, %g18, %g31
	  faddd,5	0x0, %g24, %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +136 ], %r13
	  faddd,1	%g17, %g19, %g17
	  ldd,2	0x0, [ _f64,_lts2 A +152 ], %r14
	  fmuld,3	%r4, %g18, %g19
	  fmuld,4	%r5, %g18, %r4
	  faddd,5	0x0, %g16, %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +128 ], %r5
	  faddd,1	0x0, %g23, %g23
	  fmuld,2	%r6, %g18, %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 X +32 ], %r6
	  faddd,1	0x0, %g25, %g25
	  fmuld,2	%r7, %g26, %r7
	  ldd,3	0x0, [ _f64,_lts2 A +272 ], %r15
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +240 ], %r16
	  fmuld,1	%r9, %g28, %r9
	  ldd,3	0x0, [ _f64,_lts2 A +248 ], %r17
	  fmuld,4	%r10, %g28, %r10
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +224 ], %r18
	  faddd,1	%g17, %g27, %g17
	  ldd,2	0x0, [ _f64,_lts2 A +232 ], %r19
	  fmuld,3	%r11, %g28, %g27
	  fmuld,4	%r12, %g28, %r11
	  faddd,5	%g21, %g29, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +200 ], %g29
	  fmuld,1	%r13, %g28, %r13
	  ldd,2	0x0, [ _f64,_lts2 A +216 ], %r12
	  fmuld,3	%r14, %g28, %r14
	  faddd,4	%g22, %g19, %g19
	  faddd,5	%g20, %g31, %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +192 ], %g22
	  fmuld,1	%r5, %g28, %g28
	  faddd,2	%g25, %r3, %g25
	  faddd,4	%g16, %r4, %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 X +40 ], %g24
	  faddd,1	%g23, %g30, %g23
	  fmuld,2	%r15, %r6, %g31
	  ldd,3	0x0, [ _f64,_lts2 A +336 ], %g30
	  faddd,4	%g24, %g18, %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +304 ], %r3
	  faddd,1	%g17, %r7, %g17
	  fmuld,2	%r16, %g26, %r5
	  ldd,3	0x0, [ _f64,_lts2 A +312 ], %r4
	  fmuld,4	%r17, %g26, %r7
	  faddd,5	%g21, %r10, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +288 ], %r10
	  fmuld,1	%r18, %g26, %r16
	  ldd,3	0x0, [ _f64,_lts2 A +296 ], %r15
	  fmuld,4	%r19, %g26, %r17
	  faddd,5	%g19, %g27, %g19
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +264 ], %g27
	  fmuld,1	%g29, %g26, %g29
	  ldd,2	0x0, [ _f64,_lts2 A +280 ], %r18
	  faddd,3	%g20, %r9, %g20
	  fmuld,4	%r12, %g26, %r12
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +256 ], %r9
	  fmuld,1	%g22, %g26, %g22
	  faddd,2	%g25, %r14, %g25
	  faddd,4	%g18, %r13, %g18
	  ldd,5	0x0, [ _f64,_lts2 A +400 ], %g26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 X +48 ], %g28
	  faddd,1	%g23, %r11, %g23
	  fmuld,2	%g30, %g24, %g30
	  ldd,3	0x0, [ _f64,_lts2 A +376 ], %r11
	  faddd,4	%g16, %g28, %g16
	  faddd,5	%g21, %r7, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +360 ], %r7
	  faddd,1	%g17, %g31, %g17
	  fmuld,2	%r4, %r6, %r3
	  ldd,3	0x0, [ _f64,_lts2 A +368 ], %r13
	  fmuld,4	%r3, %r6, %g31
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +344 ], %r4
	  ldd,3	0x0, [ _f64,_lts2 A +352 ], %r14
	  fmuld,4	%r10, %r6, %r10
	  fmuld,5	%r15, %r6, %r15
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +320 ], %r19
	  faddd,1	%g19, %r16, %g19
	  ldd,2	0x0, [ _f64,_lts2 A +328 ], %r20
	  fmuld,3	%r18, %r6, %r16
	  fmuld,4	%g27, %r6, %g27
	  faddd,5	%g20, %r5, %g20
	}
	{
	  faddd,0	%g25, %r12, %g25
	  fmuld,1	%r9, %r6, %r5
	  faddd,2	%g23, %r17, %g23
	  addd,3	0x0, _f64,_lts0 0x3ff8000000000000, %g29
	  faddd,4	%g18, %g29, %g18
	}
	{
	  faddd,0	%g17, %g30, %g17
	  fmuld,1	%g26, %g28, %g26
	  fmuld,2	%r11, %g24, %g30
	  ldd,3	0x0, [ _f64,_lts0 A +464 ], %g22
	  faddd,4	%g16, %g22, %g16
	  ldd,5	0x0, [ _f64,_lts2 X +56 ], %r6
	}
	{
	  faddd,0	%g21, %r3, %g21
	  fmuld,1	%r7, %g24, %r7
	  ldd,3	0x0, [ _f64,_lts0 A +432 ], %r9
	  fmuld,4	%r13, %g24, %r12
	  ldd,5	0x0, [ _f64,_lts2 A +440 ], %r11
	}
	{
	  fmuld,0	%r14, %g24, %r14
	  fmuld,1	%r4, %g24, %r4
	  ldd,2	0x0, [ _f64,_lts0 A +416 ], %r3
	  ldd,3	0x0, [ _f64,_lts2 A +424 ], %r13
	  faddd,4	%g20, %g31, %g20
	}
	{
	  fmuld,0	%r19, %g24, %r10
	  faddd,1	%g19, %r10, %g19
	  ldd,2	0x0, [ _f64,_lts0 A +392 ], %g31
	  ldd,3	0x0, [ _f64,_lts2 A +408 ], %r17
	  fmuld,4	%r20, %g24, %g24
	  faddd,5	%g18, %g27, %g18
	}
	{
	  faddd,0	%g23, %r15, %g23
	  faddd,1	%g25, %r16, %g25
	  ldd,2	0x0, [ _f64,_lts0 A +384 ], %g27
	  ldd,3	0x0, [ _f64,_lts2 A +504 ], %r15
	}
	{
	  faddd,0	%g17, %g26, %g17
	  fmuld,1	%g22, %r6, %g22
	  ldd,2	0x0, [ _f64,_lts0 A +488 ], %r5
	  ldd,3	0x0, [ _f64,_lts2 A +496 ], %r16
	  faddd,4	%g16, %r5, %g16
	}
	{
	  fmuld,0	%r11, %g28, %r11
	  fmuld,1	%r9, %g28, %r9
	  ldd,2	0x0, [ _f64,_lts0 A +472 ], %g26
	  ldd,3	0x0, [ _f64,_lts2 A +480 ], %r18
	  faddd,4	%g20, %r12, %g20
	}
	{
	  fmuld,0	%r13, %g28, %r13
	  fmuld,1	%r3, %g28, %r3
	  ldd,2	0x0, [ _f64,_lts0 A +448 ], %r12
	  ldd,3	0x0, [ _f64,_lts2 A +456 ], %r19
	  faddd,4	%g21, %g30, %g21
	  faddd,5	%g18, %g24, %g18
	}
	{
	  faddd,0	%g25, %r4, %g25
	  fmuld,1	%g31, %g28, %g24
	  faddd,2	%g19, %r14, %g19
	  ldd,3	0x0, [ _f64,_lts2 Y +16 ], %g31
	  fmuld,4	%r17, %g28, %g30
	  addd,5	0x0, _f64,_lts0 0x3ff3333333333333, %r4
	}
	{
	  faddd,0	%g23, %r7, %g23
	  fmuld,1	%g27, %g28, %g27
	  faddd,2	%g17, %g22, %g17
	  fmuld,3	%r15, %r6, %g22
	  faddd,4	%g16, %r10, %g16
	  ldd,5	0x0, [ _f64,_lts0 Y +56 ], %g28
	}
	{
	  fmuld,1	%r5, %r6, %r5
	  fmuld,4	%r16, %r6, %r7
	  ldd,5	0x0, [ _f64,_lts0 Y +48 ], %r10
	}
	{
	  fmuld,1	%g26, %r6, %g26
	  ldd,3	0x0, [ _f64,_lts0 Y +32 ], %r15
	  fmuld,4	%r18, %r6, %r14
	  ldd,5	0x0, [ _f64,_lts2 Y +40 ], %r16
	}
	{
	  fmuld,0	%r19, %r6, %r6
	  fmuld,1	%r12, %r6, %r11
	  faddd,2	%g19, %r3, %g19
	  faddd,3	%g20, %r9, %g20
	  faddd,4	%g21, %r11, %g21
	  ldd,5	0x0, [ _f64,_lts0 Y +8 ], %r3
	}
	{
	  faddd,0	%g18, %g24, %g18
	  faddd,1	%g23, %r13, %g23
	  fmuld,2	%g29, %g17, %g17
	  fmuld,3	%r4, %g31, %g31
	  ldd,5	0x0, [ _f64,_lts0 Y +24 ], %g24
	}
	{
	  fmuld,0	%r4, %g28, %g28
	  faddd,1	%g25, %g30, %g25
	  ldd,5	0x0, [ _f64,_lts0 Y ], %g30
	}
	{
	  faddd,0	%g16, %g27, %g16
	  fmuld,1	%r4, %r10, %g27
	}
	{
	  fmuld,0	%r4, %r15, %g22
	  fmuld,1	%r4, %r16, %r7
	  faddd,3	%g21, %g22, %g21
	  faddd,4	%g20, %r7, %g20
	}
	{
	  faddd,0	%g19, %r14, %g19
	  faddd,1	%g23, %r5, %g23
	  faddd,2	%g18, %r6, %g18
	  fmuld,3	%r4, %r3, %r3
	}
	{
	  faddd,0	%g25, %g26, %g25
	  fmuld,1	%r4, %g24, %g24
	}
	{
	  faddd,0	%g16, %r11, %g16
	  faddd,1	%g17, %g31, %g17
	  fmuld,2	%r4, %g30, %g26
	}
	{
	  fmuld,3	%g29, %g21, %g21
	  fmuld,4	%g29, %g20, %g20
	}
	{
	  fmuld,0	%g29, %g19, %g19
	  fmuld,1	%g29, %g23, %g23
	  fmuld,2	%g29, %g18, %g18
	}
	{
	  fmuld,0	%g29, %g25, %g25
	}
	{
	  fdtoistr,0	%g17, %g29
	  fmuld,2	%g29, %g16, %g16
	}
	{
	  faddd,3	%g21, %g28, %g21
	  faddd,4	%g20, %g27, %g20
	}
	{
	  faddd,0	%g19, %g22, %g19
	  faddd,1	%g23, %r7, %g22
	  faddd,2	%g18, %r3, %g18
	}
	{
	  faddd,0	%g25, %g24, %g23
	}
	{
	  faddd,0	%g16, %g26, %g16
	}
	{
	  qppackdl,3	%g21, %g20, %g20
	}
	{
	  qppackdl,1	%g22, %g19, %g19
	  sxt,3	0x2, %g29, %r0
	  stqp,5	0x0, [ _f64,_lts0 Y +48 ], %g20
	}
	{
	  qppackdl,0	%g23, %g17, %g17
	  stqp,2	0x0, [ _f64,_lts0 Y +32 ], %g19
	}
	{
	  qppackdl,0	%g18, %g16, %g16
	  stqp,2	0x0, [ _f64,_lts0 Y +16 ], %g17
	}
	{
	  ct	%ctpr3
	  stqp,2	0x0, [ _f64,_lts0 Y ], %g16
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x200
	.align	16
A:
	.skip	0x200
	.global	X
	.type	X, #object
	.size	X, 0x40
	.align	16
X:
	.skip	0x40
	.global	Y
	.type	Y, #object
	.size	Y, 0x40
	.align	16
Y:
	.skip	0x40
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
