! options passed: --mcpu-internal=elbrus-v6 -O3 conv_latency.c
! -----------------------------------------------------------------------------
	.file	"conv_latency.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = conv_latency.c : 4
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! conv_latency.c : 4
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! conv_latency.c : 4
	  return	%ctpr3				! conv_latency.c : 7
	  addd,0	0x0, _f64,_lts1 0x3ff0000000000000, %dg16	! conv_latency.c : 6
	}
	! <0001>
	{
	  nop 4
	  ldd,0	0x0, [ _f64,_lts0 dv ], %dg17		! conv_latency.c : 5
	}
	! <0006>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0010>
	{
	  nop 3
	  istofd,0	%g17, %dg17				! conv_latency.c : 6
	}
	! <0014>
	{
	  nop 3
	  faddd,0	%dg17, %dg16, %dg17				! conv_latency.c : 6
	}
	! <0018>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0022>
	{
	  nop 3
	  istofd,0	%g17, %dg17				! conv_latency.c : 6
	}
	! <0026>
	{
	  nop 3
	  faddd,0	%dg17, %dg16, %dg17				! conv_latency.c : 6
	}
	! <0030>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0034>
	{
	  nop 3
	  istofd,0	%g17, %dg17				! conv_latency.c : 6
	}
	! <0038>
	{
	  nop 3
	  faddd,0	%dg17, %dg16, %dg17				! conv_latency.c : 6
	}
	! <0042>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0046>
	{
	  nop 3
	  istofd,0	%g17, %dg17				! conv_latency.c : 6
	}
	! <0050>
	{
	  nop 3
	  faddd,0	%dg17, %dg16, %dg17				! conv_latency.c : 6
	}
	! <0054>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0058>
	{
	  nop 3
	  istofd,0	%g17, %dg17				! conv_latency.c : 6
	}
	! <0062>
	{
	  nop 3
	  faddd,0	%dg17, %dg16, %dg17				! conv_latency.c : 6
	}
	! <0066>
	{
	  nop 3
	  fdtoistr,0	%dg17, %g17				! conv_latency.c : 6
	}
	! <0070>
	{
	  nop 1
	  istofd,0	%g17, %dg18				! conv_latency.c : 6
	}
	! <0072>
	{
	  nop 1
	  sxt,3	0x2, %g17, %dr0				! conv_latency.c : 7
	}
	! <0074>
	{
	  nop 3
	  faddd,0	%dg18, %dg16, %dg16				! conv_latency.c : 6
	}
	! <0078>
	{
	  std,2	0x0, [ _f64,_lts0 dv ], %dg16		! conv_latency.c : 7
	}
	! <0079>
	{
	  ct	%ctpr3					! conv_latency.c : 7
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	dv
	.type	dv, #object
	.size	dv, 0x8
	.align	8
dv:
	.uadword	0x400c000000000000
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
