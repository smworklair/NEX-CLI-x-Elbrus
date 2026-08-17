! options passed: --mcpu-internal=elbrus-v6 -O3 /home/shokha/e2k-toolchain/probe.c
! -----------------------------------------------------------------------------
	.file	"probe.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = /home/shokha/e2k-toolchain/probe.c : 6
	! stack shift = 0 (0x0)
	! outgoing stack size = 16 (0x10)
	! frame pointer = %r1
	! stack pointer = %r2
							! /home/shokha/e2k-toolchain/probe.c : 6
	! <0000>
	{
	  setwd	wsz = 0xc, nfx = 0x1, dbl = 0x0	! /home/shokha/e2k-toolchain/probe.c : 6
	  setbn	rsz = 0x3, rbs = 0x8, rcur = 0x0	! /home/shokha/e2k-toolchain/probe.c : 6
	  disp	%ctpr1, printf				! /home/shokha/e2k-toolchain/probe.c : 18
	  getsp,0	_f32s,_lts1 0xfffffff0, %dr2		! /home/shokha/e2k-toolchain/probe.c : 6
	}
	! <0001>
	{
	  ldw,3	0x0, [ _f64,_lts0 a ], %r3		! /home/shokha/e2k-toolchain/probe.c : 7
	}
	! <0002>
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %r4		! /home/shokha/e2k-toolchain/probe.c : 7
	}
	! <0003>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +4 ], %r5		! /home/shokha/e2k-toolchain/probe.c : 8
	}
	! <0004>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +4 ], %r6		! /home/shokha/e2k-toolchain/probe.c : 8
	}
	! <0005>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +8 ], %r7		! /home/shokha/e2k-toolchain/probe.c : 9
	}
	! <0006>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +8 ], %r8		! /home/shokha/e2k-toolchain/probe.c : 9
	}
	! <0007>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +12 ], %r9		! /home/shokha/e2k-toolchain/probe.c : 10
	}
	! <0008>
	{
	  nop 1
	  ldw,3	0x0, [ _f64,_lts0 b +12 ], %r10		! /home/shokha/e2k-toolchain/probe.c : 10
	  sdivs,5	%r3, %r4, %r3				! /home/shokha/e2k-toolchain/probe.c : 7
	}
	! <0010>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +16 ], %r5		! /home/shokha/e2k-toolchain/probe.c : 12
	  sdivs,5	%r5, %r6, %r4				! /home/shokha/e2k-toolchain/probe.c : 8
	}
	! <0011>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +16 ], %r6		! /home/shokha/e2k-toolchain/probe.c : 12
	}
	! <0012>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +20 ], %r8		! /home/shokha/e2k-toolchain/probe.c : 13
	  sdivs,5	%r7, %r8, %r7				! /home/shokha/e2k-toolchain/probe.c : 9
	}
	! <0013>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +20 ], %r11		! /home/shokha/e2k-toolchain/probe.c : 13
	}
	! <0014>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +24 ], %r10		! /home/shokha/e2k-toolchain/probe.c : 14
	  sdivs,5	%r9, %r10, %r9				! /home/shokha/e2k-toolchain/probe.c : 10
	}
	! <0015>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +24 ], %r12		! /home/shokha/e2k-toolchain/probe.c : 14
	}
	! <0016>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +28 ], %r13		! /home/shokha/e2k-toolchain/probe.c : 15
	}
	! <0017>
	{
	  muls,0	%r5, %r6, %r5				! /home/shokha/e2k-toolchain/probe.c : 12
	  addd,1	0x0, [ _f64,_lts2 .LC.1 ], %db[0]	! /home/shokha/e2k-toolchain/probe.c : 18
	  ldw,2	0x0, [ _f64,_lts0 b +28 ], %r14		! /home/shokha/e2k-toolchain/probe.c : 15
	}
	! <0018>
	{
	  std,2	%dr2, 0x0, %db[0]				! /home/shokha/e2k-toolchain/probe.c : 18
	}
	! <0019>
	{
	  muls,0	%r8, %r11, %r6				! /home/shokha/e2k-toolchain/probe.c : 13
	}
	! <0020>
	{
	  nop 1
	  muls,0	%r10, %r12, %r8				! /home/shokha/e2k-toolchain/probe.c : 14
	}
	! <0022>
	{
	  muls,0	%r13, %r14, %r10				! /home/shokha/e2k-toolchain/probe.c : 15
	}
	! <0023>
	{
	  nop 1
	  adds,0	%r3, %r4, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0025>
	{
	  adds,0	%r3, %r7, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0026>
	{
	  adds,0	%r5, %r3, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0027>
	{
	  adds,0	%r3, %r9, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0028>
	{
	  adds,0	%r6, %r3, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0029>
	{
	  adds,0	%r3, %r8, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0030>
	{
	  adds,0	%r3, %r10, %r3				! /home/shokha/e2k-toolchain/probe.c : 17
	}
	! <0031>
	{
	  sxt,0	0x2, %r3, %db[1]				! /home/shokha/e2k-toolchain/probe.c : 18
	}
	! <0032>
	{
	  std,2	%dr2, 0x8, %db[1]				! /home/shokha/e2k-toolchain/probe.c : 18
	}
	! <0033>
	{
	  call	%ctpr1, wbs = 0x8			! /home/shokha/e2k-toolchain/probe.c : 18
	}
	! <0034>
	{
	  nop 5
	  return	%ctpr3				! /home/shokha/e2k-toolchain/probe.c : 19
	  addd,3	0x0, 0x0, %dr0				! /home/shokha/e2k-toolchain/probe.c : 19
	}
	! <0040>
	{
	  ct	%ctpr3					! /home/shokha/e2k-toolchain/probe.c : 19
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	a
	.type	a, #object
	.size	a, 0x20
	.align	16
a:
	.uadword	0x300000002
	.uadword	0x500000004
	.uadword	0x700000006
	.uadword	0x900000008
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x20
	.align	16
b:
	.uadword	0xc0000000b
	.uadword	0xe0000000d
	.uadword	0x100000000f
	.uadword	0x1200000011
! -----------------------------------------------------------------------------
	.section .rodata
	.align	16
.LC.1:
	.ascii	"sum = %d\n\000"
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
