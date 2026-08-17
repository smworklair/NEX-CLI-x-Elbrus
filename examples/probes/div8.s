! options passed: --mcpu-internal=elbrus-v6 -O3 probe_div8.c
! -----------------------------------------------------------------------------
	.file	"probe_div8.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = probe_div8.c : 5
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! probe_div8.c : 5
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! probe_div8.c : 5
	  return	%ctpr3				! probe_div8.c : 10
	  addd,3	0x0, 0x0, %dr0				! probe_div8.c : 10
	}
	! <0001>
	{
	  ldw,3	0x0, [ _f64,_lts0 a ], %g16		! probe_div8.c : 6
	}
	! <0002>
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %g17		! probe_div8.c : 6
	}
	! <0003>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +4 ], %g18		! probe_div8.c : 6
	}
	! <0004>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +4 ], %g19		! probe_div8.c : 6
	}
	! <0005>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +8 ], %g20		! probe_div8.c : 6
	}
	! <0006>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +8 ], %g21		! probe_div8.c : 6
	}
	! <0007>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +12 ], %g22		! probe_div8.c : 6
	}
	! <0008>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +12 ], %g23		! probe_div8.c : 6
	}
	! <0009>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +16 ], %g24		! probe_div8.c : 7
	}
	! <0010>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +16 ], %g25		! probe_div8.c : 7
	}
	! <0011>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +20 ], %g26		! probe_div8.c : 7
	}
	! <0012>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +20 ], %g27		! probe_div8.c : 7
	  sdivs,5	%g16, %g17, %g16				! probe_div8.c : 6
	}
	! <0013>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +24 ], %g17		! probe_div8.c : 7
	}
	! <0014>
	{
	  ldw,3	0x0, [ _f64,_lts0 b +24 ], %g28		! probe_div8.c : 7
	  sdivs,5	%g18, %g19, %g18				! probe_div8.c : 6
	}
	! <0015>
	{
	  ldw,3	0x0, [ _f64,_lts0 a +28 ], %g19		! probe_div8.c : 7
	}
	! <0016>
	{
	  nop 1
	  ldw,3	0x0, [ _f64,_lts0 b +28 ], %g21		! probe_div8.c : 7
	  sdivs,5	%g20, %g21, %g20				! probe_div8.c : 6
	}
	! <0018>
	{
	  nop 1
	  sdivs,5	%g22, %g23, %g22				! probe_div8.c : 6
	}
	! <0020>
	{
	  nop 1
	  sdivs,5	%g24, %g25, %g23				! probe_div8.c : 7
	}
	! <0022>
	{
	  sdivs,5	%g26, %g27, %g24				! probe_div8.c : 7
	}
	! <0023>
	{
	  stw,5	0x0, [ _f64,_lts0 out ], %g16		! probe_div8.c : 8
	}
	! <0024>
	{
	  sdivs,5	%g17, %g28, %g16				! probe_div8.c : 7
	}
	! <0025>
	{
	  stw,5	0x0, [ _f64,_lts0 out +4 ], %g18	! probe_div8.c : 8
	}
	! <0026>
	{
	  sdivs,5	%g19, %g21, %g17				! probe_div8.c : 7
	}
	! <0027>
	{
	  nop 1
	  stw,5	0x0, [ _f64,_lts0 out +8 ], %g20	! probe_div8.c : 8
	}
	! <0029>
	{
	  nop 1
	  stw,5	0x0, [ _f64,_lts0 out +12 ], %g22	! probe_div8.c : 8
	}
	! <0031>
	{
	  nop 1
	  stw,5	0x0, [ _f64,_lts0 out +16 ], %g23	! probe_div8.c : 9
	}
	! <0033>
	{
	  nop 1
	  stw,5	0x0, [ _f64,_lts0 out +20 ], %g24	! probe_div8.c : 9
	}
	! <0035>
	{
	  nop 1
	  stw,5	0x0, [ _f64,_lts0 out +24 ], %g16	! probe_div8.c : 9
	}
	! <0037>
	{
	  stw,5	0x0, [ _f64,_lts0 out +28 ], %g17	! probe_div8.c : 9
	}
	! <0038>
	{
	  ct	%ctpr3					! probe_div8.c : 10
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	a
	.type	a, #object
	.size	a, 0x20
	.align	16
a:
	.uadword	0xc800000064
	.uadword	0x1900000012c
	.uadword	0x258000001f4
	.uadword	0x320000002bc
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x20
	.align	16
b:
	.uadword	0x300000003
	.uadword	0x300000003
	.uadword	0x300000003
	.uadword	0x300000003
! -----------------------------------------------------------------------------
	.section .bss
	.global	out
	.type	out, #object
	.size	out, 0x20
	.align	16
out:
	.skip	0x20
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
