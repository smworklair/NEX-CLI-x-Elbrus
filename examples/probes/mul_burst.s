! options passed: --mcpu-internal=elbrus-v6 -O3 /home/shokha/e2k-toolchain/probe_mul_burst.c
! -----------------------------------------------------------------------------
	.file	"probe_mul_burst.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = /home/shokha/e2k-toolchain/probe_mul_burst.c : 11
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! /home/shokha/e2k-toolchain/probe_mul_burst.c : 11
	! <0000>
	{
	  setwd	wsz = 0x7, nfx = 0x1, dbl = 0x0	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 11
	  return	%ctpr3				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 26
	  addd,3	0x0, 0x0, %dr0				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 26
	}
	! <0001>
	{
	  ldw,0	0x0, [ _f64,_lts0 a ], %g16		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0002>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +4 ], %g17		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0003>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +8 ], %g18		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +12 ], %g19		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0005>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +16 ], %g20		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0006>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +20 ], %g21		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0007>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +24 ], %g22		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0008>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +28 ], %g23		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 12
	}
	! <0009>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g24		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0010>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +4 ], %g25		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0011>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +8 ], %g26		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0012>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +12 ], %g27		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0013>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +16 ], %g28		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0014>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +20 ], %g29		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0015>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +24 ], %g30		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0016>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +28 ], %g31		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 13
	}
	! <0017>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +32 ], %r2		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0018>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +36 ], %r3		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0019>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +40 ], %r4		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0020>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +44 ], %r5		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0021>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +48 ], %r6		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0022>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +52 ], %r7		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0023>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +56 ], %r8		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0024>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +60 ], %r9		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 14
	}
	! <0025>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +32 ], %r10		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0026>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +36 ], %r11		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0027>
	{
	  muls,0	%g16, %g24, %g16				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 17
	  ldw,2	0x0, [ _f64,_lts0 b +40 ], %r12		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0028>
	{
	  muls,0	%g17, %g25, %g17				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 17
	  ldw,2	0x0, [ _f64,_lts0 b +44 ], %g24		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0029>
	{
	  muls,0	%g18, %g26, %g18				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 17
	  ldw,2	0x0, [ _f64,_lts0 b +48 ], %g25		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0030>
	{
	  muls,0	%g19, %g27, %g19				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 17
	  ldw,2	0x0, [ _f64,_lts0 b +52 ], %g26		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0031>
	{
	  muls,0	%g20, %g28, %g20				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 18
	  ldw,2	0x0, [ _f64,_lts0 b +56 ], %g27		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0032>
	{
	  muls,0	%g21, %g29, %g21				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 18
	  ldw,2	0x0, [ _f64,_lts0 b +60 ], %g28		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 15
	}
	! <0033>
	{
	  muls,0	%g22, %g30, %g16				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 18
	  stw,2	0x0, [ _f64,_lts0 out ], %g16		! /home/shokha/e2k-toolchain/probe_mul_burst.c : 22
	}
	! <0034>
	{
	  muls,0	%g23, %g31, %g17				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 18
	  stw,2	0x0, [ _f64,_lts0 out +4 ], %g17	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 22
	}
	! <0035>
	{
	  muls,0	%r2, %r10, %g18				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 19
	  stw,2	0x0, [ _f64,_lts0 out +8 ], %g18	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 22
	}
	! <0036>
	{
	  muls,0	%r3, %r11, %g19				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 19
	  stw,2	0x0, [ _f64,_lts0 out +12 ], %g19	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 22
	}
	! <0037>
	{
	  muls,0	%r4, %r12, %g20				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 19
	  stw,2	0x0, [ _f64,_lts0 out +16 ], %g20	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 23
	}
	! <0038>
	{
	  muls,0	%r5, %g24, %g21				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 19
	  stw,2	0x0, [ _f64,_lts0 out +20 ], %g21	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 23
	}
	! <0039>
	{
	  muls,0	%r6, %g25, %g16				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 20
	  stw,2	0x0, [ _f64,_lts0 out +24 ], %g16	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 23
	}
	! <0040>
	{
	  muls,0	%r7, %g26, %g17				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 20
	  stw,2	0x0, [ _f64,_lts0 out +28 ], %g17	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 23
	}
	! <0041>
	{
	  muls,0	%r8, %g27, %g18				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 20
	  stw,2	0x0, [ _f64,_lts0 out +32 ], %g18	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 24
	}
	! <0042>
	{
	  muls,0	%r9, %g28, %g19				! /home/shokha/e2k-toolchain/probe_mul_burst.c : 20
	  stw,2	0x0, [ _f64,_lts0 out +36 ], %g19	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 24
	}
	! <0043>
	{
	  stw,2	0x0, [ _f64,_lts0 out +40 ], %g20	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 24
	}
	! <0044>
	{
	  stw,2	0x0, [ _f64,_lts0 out +44 ], %g21	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 24
	}
	! <0045>
	{
	  stw,2	0x0, [ _f64,_lts0 out +48 ], %g16	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 25
	}
	! <0046>
	{
	  stw,2	0x0, [ _f64,_lts0 out +52 ], %g17	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 25
	}
	! <0047>
	{
	  stw,2	0x0, [ _f64,_lts0 out +56 ], %g18	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 25
	}
	! <0048>
	{
	  stw,2	0x0, [ _f64,_lts0 out +60 ], %g19	! /home/shokha/e2k-toolchain/probe_mul_burst.c : 25
	}
	! <0049>
	{
	  ct	%ctpr3					! /home/shokha/e2k-toolchain/probe_mul_burst.c : 26
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	a
	.type	a, #object
	.size	a, 0x40
	.align	16
a:
	.uadword	0x200000001
	.uadword	0x400000003
	.uadword	0x600000005
	.uadword	0x800000007
	.uadword	0xa00000009
	.uadword	0xc0000000b
	.uadword	0xe0000000d
	.uadword	0x100000000f
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x40
	.align	16
b:
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
	.uadword	0x200000002
! -----------------------------------------------------------------------------
	.section .bss
	.global	out
	.type	out, #object
	.size	out, 0x40
	.align	16
out:
	.skip	0x40
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
