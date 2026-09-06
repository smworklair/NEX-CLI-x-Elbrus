	.file	"poly_heat3d.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  ldd,2	0x0, [ _f64,_lts2 A +328 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +336 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 A +304 ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +208 ], %g19
	  ldd,2	0x0, [ _f64,_lts2 A +200 ], %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +176 ], %g21
	  ldd,2	0x0, [ _f64,_lts2 A +296 ], %g22
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 A +168 ], %g23
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +464 ], %g24
	  ldd,2	0x0, [ _f64,_lts2 A +368 ], %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +456 ], %g26
	  ldd,2	0x0, [ _f64,_lts2 A +360 ], %g27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +424 ], %g28
	  ldd,2	0x0, [ _f64,_lts2 A +432 ], %g29
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +232 ], %g30
	  ldd,2	0x0, [ _f64,_lts2 A +240 ], %g31
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 A +344 ], %r0
	  addd,1	0x0, _f64,_lts0 0x4000000000000000, %r12
	}
	{
	  fmuld,0	%r12, %g18, %r2
	  fmuld,1	%r12, %g16, %r13
	  fmuld,2	%r12, %g17, %r14
	  ldd,3	0x0, [ _f64,_lts0 A +272 ], %r15
	  ldd,5	0x0, [ _f64,_lts2 A +312 ], %r16
	}
	{
	  fmuld,0	%r12, %g20, %r19
	  fmuld,1	%r12, %g23, %r17
	  fmuld,2	%r12, %g19, %r20
	  fmuld,3	%r12, %g22, %r21
	  fmuld,4	%r12, %g21, %r18
	  ldd,5	0x0, [ _f64,_lts0 A +264 ], %r22
	}
	{
	  addd,3	0x0, _f64,_lts0 0x3fc0000000000000, %r11
	  ldd,5	0x0, [ _f64,_lts2 A +216 ], %r23
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +72 ], %r24
	  ldd,2	0x0, [ _f64,_lts2 A +80 ], %r25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +144 ], %r26
	  fsubd,1	%g25, %r14, %g25
	  ldd,2	0x0, [ _f64,_lts2 A +184 ], %r27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +136 ], %r28
	  fsubd,1	%g20, %r17, %r30
	  ldd,2	0x0, [ _f64,_lts2 A +48 ], %r29
	  fsubd,3	%g18, %r18, %r31
	  fsubd,4	%g19, %r18, %r32
	  fsubd,5	%g28, %r21, %g28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +40 ], %r33
	  fsubd,1	%g24, %r14, %g24
	  fsubd,2	%g22, %r17, %r34
	  fsubd,3	%g29, %r2, %g29
	  fsubd,4	%g17, %r2, %r35
	  fsubd,5	%g26, %r13, %g26
	}
	{
	  fsubd,0	%g27, %r13, %g27
	  fsubd,1	%g16, %r19, %r36
	  fsubd,2	%g30, %r19, %g30
	  fsubd,3	%g31, %r20, %g31
	  fsubd,4	%g17, %r20, %r37
	  fsubd,5	%g16, %r21, %r38
	}
	{
	  fsubd,0	%g21, %r17, %r17
	  fsubd,1	%g19, %r19, %r19
	  fsubd,2	%g18, %r21, %r21
	  fsubd,3	%r16, %r2, %r2
	  fsubd,4	%g17, %r13, %r13
	  fsubd,5	%r0, %r14, %r0
	}
	{
	  fsubd,0	%r27, %r18, %r14
	  fsubd,1	%r23, %r20, %r16
	  faddd,2	%g25, %g18, %g25
	  faddd,3	%r32, %r26, %r18
	  faddd,4	%g28, %g23, %g28
	}
	{
	  faddd,0	%r30, %r28, %r23
	  faddd,1	%g24, %g19, %g24
	  faddd,3	%r31, %r29, %r26
	  faddd,4	%g26, %g20, %g26
	  ldd,5	0x0, [ _f64,_lts0 A +320 ], %r20
	}
	{
	  faddd,0	%g27, %g22, %g27
	  faddd,1	%r34, %r33, %r29
	  ldd,2	0x0, [ _f64,_lts0 A +288 ], %r27
	  faddd,3	%g31, %g21, %g31
	  faddd,4	%r38, %r22, %r22
	  ldd,5	0x0, [ _f64,_lts2 A +192 ], %r28
	}
	{
	  faddd,0	%g29, %g21, %g29
	  faddd,1	%r35, %r15, %r15
	  ldd,2	0x0, [ _f64,_lts0 A +160 ], %r30
	  faddd,3	%r37, %r25, %r25
	  faddd,4	%r2, %g22, %r2
	  faddd,5	%r0, %g16, %r0
	}
	{
	  faddd,0	%g30, %g23, %g30
	  faddd,1	%r36, %r24, %r24
	  faddd,2	%r16, %g20, %r16
	  fmuld,3	%r11, %r18, %r18
	  fmuld,4	%r11, %g28, %g28
	}
	{
	  fmuld,0	%r11, %g25, %g25
	  fmuld,1	%r11, %g24, %g24
	  faddd,2	%r14, %g23, %r14
	  fmuld,3	%r11, %r26, %r26
	  fmuld,4	%r11, %g26, %g26
	}
	{
	  fmuld,0	%r11, %r23, %r23
	  fmuld,1	%r11, %r29, %r29
	  fmuld,2	%r11, %g27, %g27
	  faddd,3	%r13, %r20, %r13
	  fmuld,4	%r11, %r22, %r20
	  fmuld,5	%r11, %g31, %g31
	}
	{
	  fmuld,0	%r11, %g29, %g29
	  fmuld,1	%r11, %r15, %r15
	  faddd,2	%r21, %r27, %r21
	  fmuld,3	%r11, %r25, %r22
	  faddd,4	%r19, %r28, %r19
	  fmuld,5	%r11, %r2, %r2
	}
	{
	  fmuld,0	%r11, %g30, %g30
	  fmuld,1	%r11, %r24, %r24
	  faddd,2	%r17, %r30, %r17
	  fmuld,3	%r11, %r0, %r0
	}
	{
	  fmuld,0	%r11, %r14, %r14
	  fmuld,1	%r11, %r16, %r16
	  faddd,2	%g24, %g25, %g24
	  faddd,3	%r26, %r18, %r18
	}
	{
	  faddd,0	%r29, %r23, %r13
	  fmuld,3	%r11, %r13, %g25
	  faddd,4	%g28, %r20, %g28
	}
	{
	  faddd,0	%g29, %r15, %g29
	  faddd,1	%g26, %g27, %g26
	  fmuld,2	%r11, %r21, %r15
	  fmuld,3	%r11, %r19, %g27
	  faddd,4	%r22, %g31, %g31
	}
	{
	  nop 1
	  fmuld,0	%r11, %r17, %r17
	  faddd,1	%r24, %g30, %g30
	}
	{
	  faddd,0	%g24, %r0, %g24
	}
	{
	  faddd,0	%r18, %r14, %r0
	  faddd,1	%g29, %r2, %g29
	  faddd,3	%g31, %r16, %g31
	}
	{
	  faddd,0	%g26, %g25, %g25
	  faddd,1	%g28, %r15, %g26
	  faddd,2	%r13, %r17, %g28
	}
	{
	  faddd,0	%g30, %g27, %g27
	}
	{
	  faddd,0	%g24, %g17, %r10
	}
	{
	  faddd,0	%r0, %g21, %r9
	  faddd,1	%g29, %g18, %r8
	  faddd,3	%g31, %g19, %r3
	}
	{
	  faddd,0	%g25, %g16, %r7
	  faddd,1	%g26, %g22, %r6
	  faddd,2	%g28, %g23, %r5
	}
	{
	  faddd,0	%g27, %g20, %r4
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +336 ], %r10
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +176 ], %r9
	  std,5	0x0, [ _f64,_lts2 B +208 ], %r3
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +304 ], %r8
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +328 ], %r7
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +296 ], %r6
	  std,5	0x0, [ _f64,_lts2 B +168 ], %r5
	}
	{
	  std,2	0x0, [ _f64,_lts0 B +200 ], %r4
	}

	{
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 B +40 ], %g17
	  fmuld,1	%r12, %r5, %g16
	  ldd,2	0x0, [ _f64,_lts2 B +136 ], %g18
	  fmuld,3	%r12, %r10, %g19
	  fmuld,4	%r12, %r8, %g20
	  fmuld,5	%r12, %r7, %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +464 ], %g22
	  fmuld,1	%r12, %r9, %g24
	  ldd,2	0x0, [ _f64,_lts2 B +368 ], %g23
	  fmuld,3	%r12, %r3, %g26
	  fmuld,4	%r12, %r4, %g25
	  fmuld,5	%r12, %r6, %g27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +456 ], %g28
	  ldd,2	0x0, [ _f64,_lts2 B +360 ], %g29
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +424 ], %g30
	  ldd,2	0x0, [ _f64,_lts2 B +432 ], %g31
	}
	{
	  fsubd,0	%r4, %g16, %r12
	  fsubd,1	%r6, %g16, %r2
	  ldd,2	0x0, [ _f64,_lts0 B +232 ], %r13
	  ldd,3	0x0, [ _f64,_lts2 B +240 ], %r14
	  fsubd,4	%r10, %g20, %r15
	  fsubd,5	%r10, %g21, %r16
	}
	{
	  fsubd,0	%r3, %g24, %r19
	  fsubd,1	%r9, %g16, %g16
	  ldd,2	0x0, [ _f64,_lts0 B +160 ], %r17
	  ldd,3	0x0, [ _f64,_lts2 B +344 ], %r18
	  fsubd,4	%r7, %g25, %r20
	  fsubd,5	%r7, %g27, %r21
	}
	{
	  fsubd,1	%r8, %g24, %r24
	  ldd,2	0x0, [ _f64,_lts0 B +272 ], %r22
	  ldd,3	0x0, [ _f64,_lts2 B +312 ], %r23
	  fsubd,4	%r10, %g26, %r25
	  fsubd,5	%r3, %g25, %r26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +216 ], %r27
	  fsubd,1	%r8, %g27, %r29
	  ldd,2	0x0, [ _f64,_lts2 B +264 ], %r28
	}
	{
	  faddd,0	%r12, %g18, %g18
	  faddd,1	%r2, %g17, %g17
	  ldd,2	0x0, [ _f64,_lts0 B +72 ], %r2
	  ldd,3	0x0, [ _f64,_lts2 B +80 ], %r12
	  fsubd,4	%g22, %g19, %g22
	  fsubd,5	%g23, %g19, %g23
	}
	{
	  fsubd,0	%g28, %g21, %g28
	  fsubd,1	%g29, %g21, %g21
	  ldd,2	0x0, [ _f64,_lts0 B +144 ], %r30
	  ldd,3	0x0, [ _f64,_lts2 B +184 ], %r31
	  fsubd,4	%g30, %g27, %g27
	  fsubd,5	%g31, %g20, %g29
	}
	{
	  faddd,0	%g16, %r17, %g16
	  fsubd,1	%r13, %g25, %g25
	  ldd,2	0x0, [ _f64,_lts0 B +48 ], %g30
	  ldd,3	0x0, [ _f64,_lts2 B +320 ], %r13
	  fsubd,4	%r14, %g26, %g31
	}
	{
	  ldd,2	0x0, [ _f64,_lts0 B +192 ], %r14
	  ldd,3	0x0, [ _f64,_lts2 B +288 ], %r17
	}
	{
	  fmuld,0	%r11, %g17, %g17
	  fmuld,1	%r11, %g18, %g18
	  fsubd,2	%r18, %g19, %g19
	  faddd,3	%g22, %r3, %g22
	  fsubd,4	%r23, %g20, %g20
	  faddd,5	%r15, %r22, %r15
	}
	{
	  fsubd,0	%r27, %g26, %g26
	  faddd,1	%r21, %r28, %r18
	  faddd,2	%g21, %r6, %g21
	  faddd,3	%g23, %r8, %g23
	  faddd,4	%g29, %r9, %g29
	  faddd,5	%r20, %r2, %r2
	}
	{
	  faddd,0	%r25, %r12, %r12
	  faddd,1	%g28, %r4, %g28
	  fsubd,2	%r31, %g24, %g24
	  faddd,3	%g27, %r5, %g27
	  faddd,4	%r19, %r30, %r19
	  faddd,5	%g31, %r9, %g31
	}
	{
	  faddd,0	%g25, %r5, %g25
	  faddd,1	%r24, %g30, %g30
	  fmuld,2	%r11, %g16, %g16
	}
	{
	  faddd,0	%g17, %g18, %g17
	  faddd,1	%r16, %r13, %g22
	  faddd,2	%g19, %r7, %g19
	  fmuld,3	%r11, %g22, %g18
	  fmuld,4	%r11, %r15, %r13
	  faddd,5	%r26, %r14, %r14
	}
	{
	  faddd,0	%r29, %r17, %r15
	  fmuld,1	%r11, %r18, %r16
	  faddd,2	%g26, %r4, %g26
	  faddd,3	%g20, %r6, %g20
	  fmuld,4	%r11, %g23, %g23
	  fmuld,5	%r11, %g29, %g29
	}
	{
	  fmuld,0	%r11, %r12, %r12
	  fmuld,1	%r11, %g28, %g28
	  fmuld,2	%r11, %g21, %g21
	  fmuld,3	%r11, %g31, %g31
	  fmuld,4	%r11, %g27, %g27
	  fmuld,5	%r11, %r19, %r17
	}
	{
	  fmuld,0	%r11, %r2, %r2
	  fmuld,1	%r11, %g25, %g25
	  faddd,2	%g24, %r5, %g24
	}
	{
	  fmuld,0	%r11, %g30, %g30
	  faddd,1	%g17, %g16, %g16
	  fmuld,2	%r11, %g22, %g17
	  fmuld,3	%r11, %r14, %g22
	}
	{
	  fmuld,0	%r11, %g19, %g19
	  fmuld,1	%r11, %r15, %g23
	  fmuld,2	%r11, %g26, %g26
	  faddd,3	%g18, %g23, %g18
	  fmuld,4	%r11, %g20, %g20
	  faddd,5	%g29, %r13, %g29
	}
	{
	  faddd,0	%g28, %g21, %g21
	}
	{
	  faddd,0	%r2, %g25, %g25
	  fmuld,1	%r11, %g24, %g24
	  faddd,3	%g27, %r16, %g27
	}
	{
	  faddd,0	%r12, %g31, %g28
	  faddd,1	%g30, %r17, %g30
	  faddd,2	%g16, %r5, %g16
	}
	{
	  faddd,3	%g29, %g20, %g20
	}
	{
	  faddd,0	%g21, %g17, %g17
	}
	{
	  faddd,0	%g18, %g19, %g18
	  faddd,1	%g25, %g22, %g21
	  faddd,3	%g27, %g23, %g19
	}
	{
	  faddd,0	%g28, %g26, %g22
	  faddd,1	%g30, %g24, %g23
	  std,2	0x0, [ _f64,_lts0 A +168 ], %g16
	}
	{
	  fdtoistr,0	%g16, %g16
	  faddd,3	%g20, %r8, %g20
	}
	{
	  faddd,0	%g17, %r7, %g17
	}
	{
	  faddd,0	%g18, %r10, %g18
	  faddd,1	%g21, %r4, %g21
	  faddd,3	%g19, %r6, %g19
	}
	{
	  faddd,0	%g22, %r3, %g22
	  faddd,1	%g23, %r9, %g23
	}
	{
	  std,5	0x0, [ _f64,_lts0 A +304 ], %g20
	}
	{
	  std,2	0x0, [ _f64,_lts0 A +328 ], %g17
	}
	{
	  std,2	0x0, [ _f64,_lts0 A +336 ], %g18
	  sxt,3	0x2, %g16, %r0
	  std,5	0x0, [ _f64,_lts2 A +296 ], %g19
	}
	{
	  std,2	0x0, [ _f64,_lts0 A +200 ], %g21
	}
	{
	  std,2	0x0, [ _f64,_lts0 A +208 ], %g22
	}
	{
	  ct	%ctpr3
	  std,2	0x0, [ _f64,_lts0 A +176 ], %g23
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x200
	.align	16
A:
	.skip	0x200
	.global	B
	.type	B, #object
	.size	B, 0x200
	.align	16
B:
	.skip	0x200
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
