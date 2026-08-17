! options passed: --mcpu-internal=elbrus-v6 -O3 probe_load_lat.c
! -----------------------------------------------------------------------------
	.file	"probe_load_lat.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = probe_load_lat.c : 3
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! probe_load_lat.c : 3
	! <0000>
	{
	  nop 4
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! probe_load_lat.c : 3
	  return	%ctpr3				! probe_load_lat.c : 8
	  ldd,0	0x0, [ _f64,_lts1 chain ], %dg16		! probe_load_lat.c : 5
	  addd,3	0x0, 0x0, %dr0				! probe_load_lat.c : 8
	}
	! <0005>
	{
	  nop 4
	  ldd,0	%dg16, 0x0, %dg16				! probe_load_lat.c : 5
	}
	! <0010>
	{
	  nop 4
	  ldd,0	%dg16, 0x0, %dg16				! probe_load_lat.c : 6
	}
	! <0015>
	{
	  nop 4
	  ldd,0	%dg16, 0x0, %dg16				! probe_load_lat.c : 6
	}
	! <0020>
	{
	  std,2	0x0, [ _f64,_lts0 chain ], %dg16		! probe_load_lat.c : 7
	}
	! <0021>
	{
	  ct	%ctpr3					! probe_load_lat.c : 8
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.section .bss
	.global	chain
	.type	chain, #object
	.size	chain, 0x40
	.align	16
chain:
	.skip	0x40
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
