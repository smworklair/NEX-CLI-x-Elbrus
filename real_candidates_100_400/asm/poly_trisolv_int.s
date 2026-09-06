	.file	"poly_trisolv_int.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xf, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  ldw,3	0x0, [ _f64,_lts1 L ], %g16
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %g17
	  ldw,5	0x0, [ _f64,_lts2 L +32 ], %g18
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b +4 ], %g19
	  ldw,5	0x0, [ _f64,_lts2 L +36 ], %g20
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +64 ], %g21
	  ldw,5	0x0, [ _f64,_lts2 L +68 ], %g22
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b +8 ], %g23
	  ldw,5	0x0, [ _f64,_lts2 L +72 ], %g24
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +96 ], %g25
	  ldw,5	0x0, [ _f64,_lts2 L +100 ], %g26
	}
	{
	  ldw,0	0x0, [ _f64,_lts2 b +12 ], %g27
	  ldw,3	0x0, [ _f64,_lts0 L +104 ], %g17
	  sdivs,5	%g17, %g16, %g16
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +108 ], %g28
	  ldw,5	0x0, [ _f64,_lts2 L +128 ], %g29
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +132 ], %g30
	  ldw,5	0x0, [ _f64,_lts2 L +136 ], %g31
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +140 ], %r2
	  sxt,4	0x2, %g24, %r0
	  ldw,5	0x0, [ _f64,_lts2 b +16 ], %r3
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +144 ], %r4
	  ldw,5	0x0, [ _f64,_lts2 L +160 ], %r5
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +164 ], %r6
	  ldw,5	0x0, [ _f64,_lts2 L +168 ], %r7
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +172 ], %r8
	  ldw,5	0x0, [ _f64,_lts2 L +176 ], %r9
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b +20 ], %r10
	  ldw,5	0x0, [ _f64,_lts2 L +180 ], %r11
	}
	{
	  ldw,0	0x0, [ _f64,_lts2 L +196 ], %r13
	  ldw,3	0x0, [ _f64,_lts0 L +192 ], %r12
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +200 ], %r14
	  ldw,5	0x0, [ _f64,_lts2 L +204 ], %r15
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +208 ], %r16
	  ldw,5	0x0, [ _f64,_lts2 L +212 ], %r17
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b +24 ], %r18
	  muls,4	%g18, %g16, %g18
	  ldw,5	0x0, [ _f64,_lts2 L +216 ], %r19
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +224 ], %r20
	  ldw,5	0x0, [ _f64,_lts2 L +228 ], %r21
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +232 ], %r22
	  ldw,5	0x0, [ _f64,_lts2 L +236 ], %r23
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +240 ], %r24
	  ldw,5	0x0, [ _f64,_lts2 L +244 ], %r25
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 b +28 ], %r26
	  ldw,5	0x0, [ _f64,_lts2 L +248 ], %r27
	}
	{
	  ldw,3	0x0, [ _f64,_lts0 L +252 ], %r28
	  stw,5	0x0, [ _f64,_lts2 x ], %g16
	}
	{
	  subs,5	%g19, %g18, %g18
	}
	{
	  nop 2
	  sdivs,5	%g18, %g20, %g18
	}
	{
	  nop 2
	  muls,0	%g29, %g16, %g21
	  muls,1	%r5, %g16, %g25
	  muls,3	%g21, %g16, %g19
	  muls,4	%g25, %g16, %g20
	}
	{
	  nop 2
	  muls,3	%r12, %g16, %g29
	  muls,4	%r20, %g16, %g16
	}
	{
	  nop 1
	  subs,0	%r3, %g21, %g21
	  subs,1	%r10, %g25, %g23
	  subs,3	%g23, %g19, %g19
	  subs,4	%g27, %g20, %g20
	}
	{
	  nop 2
	  muls,3	%g22, %g18, %g22
	  stw,5	0x0, [ _f64,_lts0 x +4 ], %g18
	}
	{
	  nop 2
	  muls,0	%r6, %g18, %g27
	  muls,1	%r13, %g18, %g30
	  subs,2	%r26, %g16, %g16
	  muls,3	%g26, %g18, %g25
	  muls,4	%g30, %g18, %g26
	  subs,5	%r18, %g29, %g29
	}
	{
	  muls,3	%r21, %g18, %g18
	  subs,5	%g19, %g22, %g19
	}
	{
	  nop 1
	  sdivs,5	%g19, %g24, %g19
	}
	{
	  nop 2
	  subs,0	%g29, %g30, %g23
	  subs,3	%g20, %g25, %g20
	  subs,4	%g21, %g26, %g21
	  subs,5	%g23, %g27, %g22
	}
	{
	  nop 5
	  subs,3	%g16, %g18, %g16
	}
	{
	  nop 2
	  muls,3	%g17, %g19, %g17
	  muls,4	%g31, %g19, %g18
	  stw,5	0x0, [ _f64,_lts0 x +8 ], %g19
	}
	{
	  nop 2
	  muls,0	%r22, %g19, %g19
	  muls,3	%r7, %g19, %g24
	  muls,4	%r14, %g19, %g25
	}
	{
	  subs,3	%g20, %g17, %g17
	  subs,4	%g21, %g18, %g18
	}
	{
	  nop 1
	  sdivs,5	%g17, %g28, %g17
	}
	{
	  nop 7
	  subs,3	%g22, %g24, %g20
	  subs,4	%g23, %g25, %g21
	  subs,5	%g16, %g19, %g16
	}
	nop
	{
	  nop 2
	  muls,3	%r2, %g17, %g19
	  muls,4	%r8, %g17, %g22
	  stw,5	0x0, [ _f64,_lts0 x +12 ], %g17
	}
	{
	  nop 2
	  muls,3	%r15, %g17, %g23
	  muls,4	%r23, %g17, %g17
	}
	{
	  subs,3	%g18, %g19, %g18
	  subs,4	%g20, %g22, %g19
	}
	{
	  nop 1
	  sdivs,5	%g18, %r4, %g18
	}
	{
	  nop 7
	  subs,3	%g21, %g23, %g20
	  subs,4	%g16, %g17, %g16
	}
	nop
	{
	  nop 2
	  muls,3	%r9, %g18, %g17
	  muls,4	%r16, %g18, %g21
	  stw,5	0x0, [ _f64,_lts0 x +16 ], %g18
	}
	{
	  nop 2
	  muls,3	%r24, %g18, %g18
	}
	{
	  subs,3	%g19, %g17, %g17
	  subs,4	%g20, %g21, %g19
	}
	{
	  nop 1
	  sdivs,5	%g17, %r11, %g17
	}
	{
	  nop 7
	  subs,3	%g16, %g18, %g16
	}
	nop
	{
	  nop 5
	  muls,3	%r17, %g17, %g18
	  muls,4	%r25, %g17, %g20
	  stw,5	0x0, [ _f64,_lts0 x +20 ], %g17
	}
	{
	  subs,3	%g19, %g18, %g17
	  subs,4	%g16, %g20, %g16
	}
	{
	  nop 7
	  sdivs,5	%g17, %r19, %g17
	}
	{
	  nop 2
	}
	{
	  nop 5
	  muls,3	%r27, %g17, %g18
	  stw,5	0x0, [ _f64,_lts0 x +24 ], %g17
	}
	{
	  subs,3	%g16, %g18, %g16
	}
	{
	  nop 7
	  sdivs,5	%g16, %r28, %g16
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr3
	  stw,5	0x0, [ _f64,_lts0 x +28 ], %g16
	}
	.size	main, .- main
	.section .bss
	.global	L
	.type	L, #object
	.size	L, 0x100
	.align	16
L:
	.skip	0x100
	.global	x
	.type	x, #object
	.size	x, 0x20
	.align	16
x:
	.skip	0x20
	.global	b
	.type	b, #object
	.size	b, 0x20
	.align	16
b:
	.skip	0x20
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
