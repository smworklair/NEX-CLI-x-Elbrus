! options passed: --mcpu-internal=elbrus-v6 -O3 store_latency.c
! -----------------------------------------------------------------------------
	.file	"store_latency.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = store_latency.c : 9
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! store_latency.c : 9
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! store_latency.c : 9
	  return	%ctpr3				! store_latency.c : 15
	  adds,0	0x1, 0x0, %g16				! store_latency.c : 10
	}
	! <0001>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0003>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0008>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0009>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0011>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0016>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0017>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0019>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0024>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0025>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0027>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0032>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0033>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0035>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0040>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0041>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0043>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0048>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0049>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0051>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0056>
	{
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0057>
	{
	  nop 1
	  stw,2	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 12
	}
	! <0059>
	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 mem ], %g16		! store_latency.c : 13
	}
	! <0064>
	{
	  nop 1
	  adds,0	%g16, 0x1, %g16				! store_latency.c : 13
	}
	! <0066>
	{
	  ct	%ctpr3					! store_latency.c : 15
	  sxt,3	0x2, %g16, %dr0				! store_latency.c : 15
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.section .bss
	.global	mem
	.type	mem, #object
	.size	mem, 0x4
	.align	4
mem:
	.skip	0x4
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
