! options passed: --mcpu-internal=elbrus-v6 -O3 probe_div_lat.c
! -----------------------------------------------------------------------------
	.file	"probe_div_lat.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = probe_div_lat.c : 4
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! probe_div_lat.c : 4
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! probe_div_lat.c : 4
	  return	%ctpr3				! probe_div_lat.c : 11
	  addd,3	0x0, 0x0, %dr0				! probe_div_lat.c : 11
	}
	! <0001>
	{
	  ldw,3	0x0, [ _f64,_lts0 a ], %g16		! probe_div_lat.c : 5
	}
	! <0002>
	{
	  nop 2
	  ldw,3	0x0, [ _f64,_lts0 b ], %g17		! probe_div_lat.c : 5
	}
	! <0005>
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %g18		! probe_div_lat.c : 6
	}
	! <0006>
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %g19		! probe_div_lat.c : 7
	}
	! <0007>
	{
	  ldw,3	0x0, [ _f64,_lts0 b ], %g17		! probe_div_lat.c : 8
	  sdivs,5	%g16, %g17, %g16				! probe_div_lat.c : 5
	}
	! <0008>
	{
	  nop 7
	  ldw,3	0x0, [ _f64,_lts0 b ], %g20		! probe_div_lat.c : 9
	}
	! <0016>
	{
	  nop 1
	}
	! <0018>
	{
	  nop 7
	  sdivs,5	%g16, %g18, %g16				! probe_div_lat.c : 6
	}
	! <0026>
	{
	  nop 2
	}
	! <0029>
	{
	  nop 7
	  sdivs,5	%g16, %g19, %g16				! probe_div_lat.c : 7
	}
	! <0037>
	{
	  nop 2
	}
	! <0040>
	{
	  nop 7
	  sdivs,5	%g16, %g17, %g16				! probe_div_lat.c : 8
	}
	! <0048>
	{
	  nop 2
	}
	! <0051>
	{
	  nop 7
	  sdivs,5	%g16, %g20, %g16				! probe_div_lat.c : 9
	}
	! <0059>
	{
	  nop 2
	}
	! <0062>
	{
	  stw,5	0x0, [ _f64,_lts0 out ], %g16		! probe_div_lat.c : 10
	}
	! <0063>
	{
	  ct	%ctpr3					! probe_div_lat.c : 11
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	a
	.type	a, #object
	.size	a, 0x4
	.align	4
a:
	.uaword	0xf4240
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x4
	.align	4
b:
	.uaword	0x3
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
