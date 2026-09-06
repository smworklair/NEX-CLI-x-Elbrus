	.file	"tsvc_s1111.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	kern_s1111
	.type	kern_s1111, #function
	.align	8
kern_s1111:

	{
	  setwd	wsz = 0x1e, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  ldw,2	0x0, [ _f64,_lts2 b +76 ], %g16
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d +76 ], %g17
	  ldw,2	0x0, [ _f64,_lts2 d +72 ], %g18
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +76 ], %g19
	  ldw,2	0x0, [ _f64,_lts2 c +72 ], %g20
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +72 ], %g21
	  ldw,2	0x0, [ _f64,_lts2 b +68 ], %g22
	}
	{
	  ldw,0	0x0, [ _f64,_lts2 d +68 ], %g23
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d +64 ], %g24
	  ldw,2	0x0, [ _f64,_lts2 c +68 ], %g25
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +64 ], %g26
	  fmuls,1	%g17, %g16, %g28
	  ldw,2	0x0, [ _f64,_lts2 b +64 ], %g27
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +60 ], %g29
	  fmuls,1	%g19, %g16, %g16
	  ldw,2	0x0, [ _f64,_lts2 d +60 ], %g30
	  fmuls,3	%g19, %g19, %g31
	  fmuls,4	%g20, %g20, %r2
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +60 ], %r3
	  fmuls,1	%g20, %g21, %r5
	  ldw,2	0x0, [ _f64,_lts2 d +56 ], %r4
	  fmuls,4	%g18, %g21, %g21
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +56 ], %r6
	  fmuls,1	%g23, %g22, %r8
	  ldw,2	0x0, [ _f64,_lts2 b +56 ], %r7
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +52 ], %r9
	  fmuls,1	%g25, %g22, %g22
	  ldw,2	0x0, [ _f64,_lts2 d +52 ], %r10
	  fmuls,3	%g25, %g25, %r11
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d +48 ], %r12
	  fmuls,1	%g26, %g27, %r14
	  ldw,2	0x0, [ _f64,_lts2 c +52 ], %r13
	  fmuls,3	%g24, %g27, %g27
	  fmuls,4	%g26, %g26, %r15
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +48 ], %r16
	  fmuls,1	%g30, %g29, %r18
	  ldw,2	0x0, [ _f64,_lts2 b +48 ], %r17
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +44 ], %r19
	  fmuls,1	%r3, %g29, %g29
	  ldw,2	0x0, [ _f64,_lts2 d +44 ], %r20
	  fadds,3	%g16, %g28, %g16
	  fmuls,4	%r3, %r3, %r21
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +44 ], %r22
	  fmuls,1	%r6, %r7, %r24
	  ldw,2	0x0, [ _f64,_lts2 d +40 ], %r23
	  fmuls,3	%r4, %r7, %r7
	  fadds,4	%r5, %g21, %r5
	  fmuls,5	%r6, %r6, %r25
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +40 ], %r26
	  fmuls,1	%r10, %r9, %r28
	  ldw,2	0x0, [ _f64,_lts2 b +40 ], %r27
	  fmuls,3	%g17, %g19, %g17
	  fmuls,4	%g18, %g20, %g18
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +36 ], %g19
	  fmuls,1	%r13, %r9, %r9
	  ldw,2	0x0, [ _f64,_lts2 d +36 ], %g20
	  fadds,3	%g22, %r8, %g22
	  fmuls,4	%r13, %r13, %r29
	  fmuls,5	%g23, %g25, %g23
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d +32 ], %g25
	  fmuls,1	%r16, %r17, %r31
	  ldw,2	0x0, [ _f64,_lts2 c +36 ], %r30
	  fmuls,3	%r12, %r17, %r17
	  fadds,4	%r14, %g27, %r14
	  fmuls,5	%r16, %r16, %r32
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +32 ], %r33
	  fmuls,1	%r20, %r19, %r35
	  ldw,2	0x0, [ _f64,_lts2 b +32 ], %r34
	  fadds,3	%r5, %r2, %r2
	  fadds,4	%g16, %g31, %g16
	  fmuls,5	%g24, %g26, %g24
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +28 ], %g26
	  fmuls,1	%r22, %r19, %r5
	  ldw,2	0x0, [ _f64,_lts2 d +28 ], %g31
	  fadds,3	%g29, %r18, %g29
	  fmuls,4	%r22, %r22, %r19
	  fmuls,5	%g30, %r3, %g30
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +28 ], %r3
	  fmuls,1	%r26, %r27, %r37
	  ldw,2	0x0, [ _f64,_lts2 d +24 ], %r36
	  fmuls,3	%r23, %r27, %r27
	  fadds,4	%r24, %r7, %r24
	  fmuls,5	%r26, %r26, %r38
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +24 ], %r39
	  fmuls,1	%g20, %g19, %r41
	  ldw,2	0x0, [ _f64,_lts2 b +24 ], %r40
	  fadds,3	%r14, %r15, %r14
	  fadds,4	%g22, %r11, %g22
	  fmuls,5	%r4, %r6, %r4
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +20 ], %r6
	  fmuls,1	%r30, %g19, %g19
	  ldw,2	0x0, [ _f64,_lts2 d +20 ], %r11
	  fadds,3	%r9, %r28, %r9
	  fmuls,4	%r30, %r30, %r15
	  fadds,5	%g16, %g28, %g16
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d +16 ], %g28
	  fmuls,1	%r33, %r34, %r43
	  ldw,2	0x0, [ _f64,_lts2 c +20 ], %r42
	  fmuls,3	%g25, %r34, %r34
	  fadds,4	%r31, %r17, %r31
	  fmuls,5	%r33, %r33, %r44
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +16 ], %r45
	  fmuls,1	%g31, %g26, %r47
	  ldw,2	0x0, [ _f64,_lts2 b +16 ], %r46
	  fadds,3	%g29, %r21, %g29
	  fadds,4	%r24, %r25, %r21
	  fadds,5	%r2, %g21, %g21
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +12 ], %r2
	  fmuls,1	%r3, %g26, %g26
	  ldw,2	0x0, [ _f64,_lts2 d +12 ], %r24
	  fadds,3	%r5, %r35, %r5
	  fmuls,4	%r3, %r3, %r25
	  fadds,5	%g22, %r8, %g22
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +12 ], %r8
	  fmuls,1	%r39, %r40, %r49
	  ldw,2	0x0, [ _f64,_lts2 d +8 ], %r48
	  fmuls,3	%r36, %r40, %r40
	  fadds,4	%r37, %r27, %r37
	  fmuls,5	%r39, %r39, %r50
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c +8 ], %r51
	  fmuls,1	%r11, %r6, %r53
	  ldw,2	0x0, [ _f64,_lts2 b +8 ], %r52
	  fadds,3	%r31, %r32, %r31
	  fadds,4	%r9, %r29, %r9
	  fadds,5	%r14, %g27, %g27
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 b +4 ], %r14
	  fmuls,1	%r42, %r6, %r6
	  ldw,2	0x0, [ _f64,_lts2 d +4 ], %r29
	  fadds,3	%g19, %r41, %g19
	  fmuls,4	%r42, %r42, %r32
	  fadds,5	%g29, %r18, %g29
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 d ], %r18
	  fmuls,1	%r45, %r46, %r55
	  ldw,2	0x0, [ _f64,_lts2 c +4 ], %r54
	  fmuls,3	%g28, %r46, %r46
	  fadds,4	%r43, %r34, %r43
	  fmuls,5	%r45, %r45, %r56
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 c ], %r57
	  fmuls,1	%r24, %r2, %r59
	  ldw,2	0x0, [ _f64,_lts2 b ], %r58
	  fadds,3	%r5, %r19, %r5
	  fadds,4	%r37, %r38, %r19
	  fmuls,5	%r10, %r13, %r10
	}
	{
	  fmuls,0	%r8, %r2, %r2
	  fadds,1	%g26, %r47, %g26
	  fmuls,2	%r8, %r8, %r13
	  fmuls,3	%r12, %r16, %r12
	  fmuls,4	%r20, %r22, %r16
	  fadds,5	%r21, %r7, %r7
	}
	{
	  fmuls,0	%r51, %r52, %r20
	  fmuls,1	%r48, %r52, %r21
	  fadds,2	%r49, %r40, %r22
	  fmuls,3	%r51, %r51, %r37
	  fadds,4	%g19, %r15, %g19
	  fadds,5	%r31, %r17, %r15
	}
	{
	  fmuls,0	%r29, %r14, %r17
	  fadds,1	%r6, %r53, %r6
	  fadds,2	%r9, %r28, %r9
	  fadds,3	%r43, %r44, %r31
	  fmuls,4	%r23, %r26, %r23
	  fmuls,5	%g20, %r30, %g20
	}
	{
	  fmuls,0	%r54, %r14, %r14
	  fmuls,1	%r54, %r54, %r26
	  fmuls,2	%g25, %r33, %g25
	  fadds,3	%r5, %r35, %r5
	  fmuls,4	%g31, %r3, %g31
	  fadds,5	%r19, %r27, %r3
	}
	{
	  fmuls,0	%r57, %r58, %r19
	  fmuls,1	%r18, %r58, %r27
	  fadds,2	%r55, %r46, %r28
	  fmuls,3	%r57, %r57, %r30
	  fmuls,4	%r11, %r42, %r11
	  fmuls,5	%r36, %r39, %r33
	}
	{
	  fadds,0	%r2, %r59, %r2
	  fadds,1	%r20, %r21, %r20
	  fadds,2	%g26, %r25, %g26
	  fadds,3	%g19, %r41, %g19
	  fmuls,4	%r24, %r8, %r8
	  fmuls,5	%g28, %r45, %g28
	}
	{
	  fadds,0	%r6, %r32, %r6
	  fadds,1	%r22, %r50, %r22
	  fadds,2	%g16, %g17, %g16
	  fadds,3	%r31, %r34, %r24
	  fadds,4	%g21, %g18, %g17
	  fmuls,5	%r29, %r54, %g18
	}
	{
	  fadds,0	%r14, %r17, %g21
	  fmuls,1	%r48, %r51, %r14
	  fmuls,2	%r18, %r57, %r18
	  fadds,3	%g27, %g24, %g24
	  fadds,4	%g22, %g23, %g22
	  fadds,5	%g29, %g30, %g23
	}
	{
	  fadds,0	%r19, %r27, %g27
	  fadds,1	%r28, %r56, %g29
	  fadds,2	%r15, %r12, %g30
	  fadds,3	%r7, %r4, %r4
	  fadds,4	%r5, %r16, %r5
	  fadds,5	%r9, %r10, %r7
	}
	{
	  fadds,0	%r2, %r13, %r2
	  fadds,1	%r20, %r37, %r9
	  fadds,2	%g26, %r47, %g26
	  fadds,3	%r3, %r23, %r3
	  fadds,4	%g19, %g20, %g19
	}
	{
	  fadds,0	%r6, %r53, %g20
	  fadds,1	%r22, %r40, %r6
	  stw,2	0x0, [ _f64,_lts0 a +152 ], %g16
	  fadds,3	%r24, %g25, %g25
	  stw,5	0x0, [ _f64,_lts2 a +144 ], %g17
	}
	{
	  fadds,0	%g21, %r26, %g16
	  stw,5	0x0, [ _f64,_lts0 a +136 ], %g22
	}
	{
	  fadds,0	%g27, %r30, %g17
	  fadds,1	%g29, %r46, %g21
	  stw,2	0x0, [ _f64,_lts2 a +96 ], %g30
	  stw,5	0x0, [ _f64,_lts0 a +120 ], %g23
	}
	{
	  fadds,0	%r2, %r59, %g22
	  fadds,1	%r9, %r21, %g23
	  fadds,2	%g26, %g31, %g26
	  stw,5	0x0, [ _f64,_lts0 a +128 ], %g24
	}
	{
	  fadds,0	%g20, %r11, %g20
	  fadds,1	%r6, %r33, %g24
	  stw,2	0x0, [ _f64,_lts0 a +112 ], %r4
	  stw,5	0x0, [ _f64,_lts2 a +88 ], %r5
	}
	{
	  fadds,0	%g16, %r17, %g16
	  stw,2	0x0, [ _f64,_lts0 a +104 ], %r7
	  stw,5	0x0, [ _f64,_lts2 a +80 ], %r3
	}
	{
	  fadds,0	%g17, %r27, %g17
	  fadds,1	%g21, %g28, %g21
	  stw,2	0x0, [ _f64,_lts0 a +64 ], %g25
	  stw,5	0x0, [ _f64,_lts2 a +72 ], %g19
	}
	{
	  fadds,0	%g22, %r8, %g19
	  fadds,1	%g23, %r14, %g22
	  stw,2	0x0, [ _f64,_lts0 a +56 ], %g26
	}
	{
	  stw,2	0x0, [ _f64,_lts0 a +48 ], %g24
	}
	{
	  fadds,0	%g16, %g18, %g16
	  stw,2	0x0, [ _f64,_lts0 a +40 ], %g20
	}
	{
	  fadds,0	%g17, %r18, %g17
	  stw,2	0x0, [ _f64,_lts0 a +32 ], %g21
	}
	{
	  stw,2	0x0, [ _f64,_lts0 a +24 ], %g19
	}
	{
	  stw,2	0x0, [ _f64,_lts0 a +16 ], %g22
	}
	{
	  stw,2	0x0, [ _f64,_lts0 a +8 ], %g16
	}
	{
	  ct	%ctpr3
	  stw,2	0x0, [ _f64,_lts0 a ], %g17
	}
	.size	kern_s1111, .- kern_s1111
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  nop 4
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  disp	%ctpr1, kern_s1111
	}
.LCS.1:
	{
	  call	%ctpr1, wbs = 0x4
	}
	{
	  nop 4
	  return	%ctpr3
	  ldw,0	0x0, [ _f64,_lts0 a +8 ], %r3
	}
	{
	  nop 5
	  fstoistr,0	%r3, %r3
	}
	{
	  ct	%ctpr3
	  sxt,3,sm	0x2, %r3, %r0
	}
.LCS.2:
	.size	main, .- main
	.section .bss
	.global	a
	.type	a, #object
	.size	a, 0xa0
	.align	16
a:
	.skip	0xa0
	.global	b
	.type	b, #object
	.size	b, 0xa0
	.align	16
b:
	.skip	0xa0
	.global	c
	.type	c, #object
	.size	c, 0xa0
	.align	16
c:
	.skip	0xa0
	.global	d
	.type	d, #object
	.size	d, 0xa0
	.align	16
d:
	.skip	0xa0
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
