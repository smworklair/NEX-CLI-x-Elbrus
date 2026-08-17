! options passed: --mcpu-internal=elbrus-v6 -O3 /home/shokha/e2k-toolchain/probe_mul_lat.c
! -----------------------------------------------------------------------------
	.file	"probe_mul_lat.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = /home/shokha/e2k-toolchain/probe_mul_lat.c : 7
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! /home/shokha/e2k-toolchain/probe_mul_lat.c : 7
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! /home/shokha/e2k-toolchain/probe_mul_lat.c : 7
	  return	%ctpr3				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 15
	  addd,3	0x0, 0x0, %dr0				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 15
	}
	! <0001>
	{
	  ldw,0	0x0, [ _f64,_lts0 a ], %g16		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 8
	}
	! <0002>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g17		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 8
	}
	! <0003>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g18		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 9
	}
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g19		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 10
	}
	! <0005>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g20		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 11
	}
	! <0006>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %g21		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 12
	}
	! <0007>
	{
	  nop 2
	  ldw,0	0x0, [ _f64,_lts0 b ], %g17		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	  muls,1	%g16, %g17, %g16				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0010>
	{
	  muls,0	%g19, %g20, %g19				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0011>
	{
	  nop 2
	  muls,0	%g18, %g16, %g16				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0014>
	{
	  muls,0	%g17, %g19, %g17				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0015>
	{
	  nop 3
	  muls,0	%g21, %g16, %g16				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0019>
	{
	  nop 3
	  muls,0	%g16, %g17, %g16				! /home/shokha/e2k-toolchain/probe_mul_lat.c : 13
	}
	! <0023>
	{
	  stw,2	0x0, [ _f64,_lts0 out ], %g16		! /home/shokha/e2k-toolchain/probe_mul_lat.c : 14
	}
	! <0024>
	{
	  ct	%ctpr3					! /home/shokha/e2k-toolchain/probe_mul_lat.c : 15
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	a
	.type	a, #object
	.size	a, 0x4
	.align	4
a:
	.uaword	0x3
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x4
	.align	4
b:
	.uaword	0x5
! -----------------------------------------------------------------------------
	.section .bss
	.global	out
	.type	out, #object
	.size	out, 0x4
	.align	4
out:
	.skip	0x4
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
