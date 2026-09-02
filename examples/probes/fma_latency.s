! options passed: --mcpu-internal=elbrus-v6 -O3 fma_latency.c
! -----------------------------------------------------------------------------
	.file	"fma_latency.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	fma_chain
	.type	fma_chain, #function
	.align	8
fma_chain:
	! source = fma_latency.c : 4
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! fma_latency.c : 4
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! fma_latency.c : 4
	  return	%ctpr3				! fma_latency.c : 7
	  addd,0	0x0, _f64,_lts1 0x3ff0000000000000, %dg16	! fma_latency.c : 5
	}
	! <0001>
	{
	  ldd,0	0x0, [ _f64,_lts0 bv ], %dg17		! fma_latency.c : 5
	}
	! <0002>
	{
	  nop 3
	  ldd,0	0x0, [ _f64,_lts0 cv ], %dg18		! fma_latency.c : 5
	}
	! <0006>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0010>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0014>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0018>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0022>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0026>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0030>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0034>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0038>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0042>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0046>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0050>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0054>
	{
	  nop 3
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0058>
	{
	  nop 3
	  faddd,0	%dg16, %dg18, %dg16				! fma_latency.c : 6
	}
	! <0062>
	{
	  nop 5
	  fmuld,0	%dg16, %dg17, %dg16				! fma_latency.c : 6
	}
	! <0068>
	{
	  nop 4
	  faddd,3	%dg16, %dg18, %dr0				! fma_latency.c : 7
	}
	! <0073>
	{
	  ct	%ctpr3					! fma_latency.c : 7
	}
	.size	fma_chain, .- fma_chain
! -----------------------------------------------------------------------------
	.data
	.global	bv
	.type	bv, #object
	.size	bv, 0x8
	.align	8
bv:
	.uadword	0x3ff000010c6f7a0b
! -----------------------------------------------------------------------------
	.global	cv
	.type	cv, #object
	.size	cv, 0x8
	.align	8
cv:
	.uadword	0x3fe0000000000000
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
