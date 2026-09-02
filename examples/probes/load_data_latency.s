! options passed: --mcpu-internal=elbrus-v6 -O3 load_data_latency.c
! -----------------------------------------------------------------------------
	.file	"load_data_latency.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = load_data_latency.c : 5
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! load_data_latency.c : 5
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! load_data_latency.c : 5
	  return	%ctpr3				! load_data_latency.c : 10
	  addd,3	0x0, 0x0, %dr0				! load_data_latency.c : 10
	}
	! <0001>
	{
	  ldd,0	0x0, [ _f64,_lts0 v ], %dg16		! load_data_latency.c : 6
	}
	! <0002>
	{
	  ldd,0	0x0, [ _f64,_lts0 v +8 ], %dg17		! load_data_latency.c : 7
	}
	! <0003>
	{
	  nop 2
	  ldd,0	0x0, [ _f64,_lts0 v +16 ], %dg18		! load_data_latency.c : 8
	}
	! <0006>
	{
	  addd,0	0x3, %dg16, %dg16				! load_data_latency.c : 9
	}
	! <0007>
	{
	  addd,0	%dg16, %dg17, %dg16				! load_data_latency.c : 9
	}
	! <0008>
	{
	  addd,0	%dg16, %dg18, %dg16				! load_data_latency.c : 9
	}
	! <0009>
	{
	  std,2	0x0, [ _f64,_lts0 out ], %dg16		! load_data_latency.c : 9
	}
	! <0010>
	{
	  ct	%ctpr3					! load_data_latency.c : 10
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.data
	.global	v
	.type	v, #object
	.size	v, 0x40
	.align	16
v:
	.uadword	0x1
	.uadword	0x2
	.uadword	0x3
	.uadword	0x4
	.uadword	0x5
	.uadword	0x6
	.uadword	0x7
	.uadword	0x8
! -----------------------------------------------------------------------------
	.section .bss
	.global	out
	.type	out, #object
	.size	out, 0x8
	.align	8
out:
	.skip	0x8
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
