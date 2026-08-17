! options passed: --mcpu-internal=elbrus-v6 -O3 probe_mul8.c
! -----------------------------------------------------------------------------
	.file	"probe_mul8.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = probe_mul8.c : 13
	! stack shift = 0 (0x0)
	! outgoing stack size = 16 (0x10)
	! frame pointer = %r1
	! stack pointer = %r2
							! probe_mul8.c : 13
	! <0000>
	{
	  setwd	wsz = 0xc, nfx = 0x1, dbl = 0x0	! probe_mul8.c : 13
	  setbn	rsz = 0x3, rbs = 0x8, rcur = 0x0	! probe_mul8.c : 13
	  disp	%ctpr1, printf				! probe_mul8.c : 24
	  getsp,0	_f32s,_lts1 0xfffffff0, %dr2		! probe_mul8.c : 13
	}
	! <0001>
	{
	  ldw,0	0x0, [ _f64,_lts0 a ], %r3		! probe_mul8.c : 14
	}
	! <0002>
	{
	  ldw,0	0x0, [ _f64,_lts0 b ], %r4		! probe_mul8.c : 14
	}
	! <0003>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +4 ], %r5		! probe_mul8.c : 15
	}
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +4 ], %r6		! probe_mul8.c : 15
	}
	! <0005>
	{
	  ldw,0	0x0, [ _f64,_lts0 a +8 ], %r7		! probe_mul8.c : 16
	}
	! <0006>
	{
	  ldw,0	0x0, [ _f64,_lts0 b +8 ], %r8		! probe_mul8.c : 16
	}
	! <0007>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +12 ], %r9		! probe_mul8.c : 17
	}
	! <0008>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +12 ], %r10		! probe_mul8.c : 17
	}
	! <0009>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +16 ], %r11		! probe_mul8.c : 18
	}
	! <0010>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +16 ], %r12		! probe_mul8.c : 18
	}
	! <0011>
	{
	  ldw,2	0x0, [ _f64,_lts0 a +20 ], %r13		! probe_mul8.c : 19
	}
	! <0012>
	{
	  ldw,2	0x0, [ _f64,_lts0 b +20 ], %r14		! probe_mul8.c : 19
	}
	! <0013>
	{
	  muls,0	%r3, %r4, %r3				! probe_mul8.c : 14
	  muls,1	%r5, %r6, %r4				! probe_mul8.c : 15
	  ldw,2	0x0, [ _f64,_lts0 a +24 ], %r15		! probe_mul8.c : 20
	}
	! <0014>
	{
	  muls,0	%r7, %r8, %r6				! probe_mul8.c : 16
	  ldw,2	0x0, [ _f64,_lts0 b +24 ], %r5		! probe_mul8.c : 20
	}
	! <0015>
	{
	  muls,0	%r9, %r10, %r8				! probe_mul8.c : 17
	  ldw,2	0x0, [ _f64,_lts0 a +28 ], %r7		! probe_mul8.c : 21
	}
	! <0016>
	{
	  muls,0	%r11, %r12, %r10				! probe_mul8.c : 18
	  addd,1	0x0, [ _f64,_lts2 .LC.1 ], %db[0]	! probe_mul8.c : 24
	  ldw,2	0x0, [ _f64,_lts0 b +28 ], %r9		! probe_mul8.c : 21
	}
	! <0017>
	{
	  nop 1
	  muls,0	%r13, %r14, %r11				! probe_mul8.c : 19
	  std,2	%dr2, 0x0, %db[0]				! probe_mul8.c : 24
	}
	! <0019>
	{
	  muls,0	%r15, %r5, %r5				! probe_mul8.c : 20
	  adds,1	%r3, %r4, %r3				! probe_mul8.c : 23
	}
	! <0020>
	{
	  adds,0	%r3, %r6, %r3				! probe_mul8.c : 23
	}
	! <0021>
	{
	  muls,0	%r7, %r9, %r4				! probe_mul8.c : 21
	  adds,1	%r3, %r8, %r3				! probe_mul8.c : 23
	}
	! <0022>
	{
	  adds,0	%r3, %r10, %r3				! probe_mul8.c : 23
	}
	! <0023>
	{
	  nop 1
	  adds,1	%r3, %r11, %r3				! probe_mul8.c : 23
	}
	! <0025>
	{
	  nop 1
	  adds,0	%r3, %r5, %r3				! probe_mul8.c : 23
	}
	! <0027>
	{
	  adds,0	%r3, %r4, %r3				! probe_mul8.c : 23
	}
	! <0028>
	{
	  sxt,0	0x2, %r3, %db[1]				! probe_mul8.c : 24
	}
	! <0029>
	{
	  std,2	%dr2, 0x8, %db[1]				! probe_mul8.c : 24
	}
	! <0030>
	{
	  call	%ctpr1, wbs = 0x8			! probe_mul8.c : 24
	}
	! <0031>
	{
	  nop 5
	  return	%ctpr3				! probe_mul8.c : 25
	  addd,3	0x0, 0x0, %dr0				! probe_mul8.c : 25
	}
	! <0037>
	{
	  ct	%ctpr3					! probe_mul8.c : 25
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
