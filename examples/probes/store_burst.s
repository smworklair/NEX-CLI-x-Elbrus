! options passed: --mcpu-internal=elbrus-v6 -O3 store_burst.c
! -----------------------------------------------------------------------------
	.file	"store_burst.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	main
	.type	main, #function
	.align	8
main:
	! source = store_burst.c : 8
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r1
	! stack pointer = %r2
							! store_burst.c : 8
	! <0000>
	{
	  setwd	wsz = 0x4, nfx = 0x1, dbl = 0x0	! store_burst.c : 8
	  return	%ctpr3				! store_burst.c : 17
	  addd,3	0x0, 0x0, %dr0				! store_burst.c : 17
	}
	! <0001>
	{
	  ldw,0	0x0, [ _f64,_lts0 src ], %g16		! store_burst.c : 9
	}
	! <0002>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +4 ], %g17	! store_burst.c : 9
	}
	! <0003>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +8 ], %g18	! store_burst.c : 9
	}
	! <0004>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +12 ], %g19	! store_burst.c : 9
	}
	! <0005>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +16 ], %g20	! store_burst.c : 10
	}
	! <0006>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +20 ], %g21	! store_burst.c : 10
	}
	! <0007>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +24 ], %g22	! store_burst.c : 10
	}
	! <0008>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +28 ], %g23	! store_burst.c : 10
	}
	! <0009>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +32 ], %g24	! store_burst.c : 11
	}
	! <0010>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +36 ], %g25	! store_burst.c : 11
	}
	! <0011>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +40 ], %g26	! store_burst.c : 11
	}
	! <0012>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +44 ], %g27	! store_burst.c : 11
	}
	! <0013>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +48 ], %g28	! store_burst.c : 12
	}
	! <0014>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +52 ], %g29	! store_burst.c : 12
	}
	! <0015>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +56 ], %g30	! store_burst.c : 12
	}
	! <0016>
	{
	  ldw,0	0x0, [ _f64,_lts0 src +60 ], %g31	! store_burst.c : 12
	}
	! <0017>
	{
	  stw,2	0x0, [ _f64,_lts0 out ], %g16		! store_burst.c : 13
	}
	! <0018>
	{
	  stw,2	0x0, [ _f64,_lts0 out +4 ], %g17	! store_burst.c : 13
	}
	! <0019>
	{
	  stw,2	0x0, [ _f64,_lts0 out +8 ], %g18	! store_burst.c : 13
	}
	! <0020>
	{
	  stw,2	0x0, [ _f64,_lts0 out +12 ], %g19	! store_burst.c : 13
	}
	! <0021>
	{
	  stw,2	0x0, [ _f64,_lts0 out +16 ], %g20	! store_burst.c : 14
	}
	! <0022>
	{
	  stw,2	0x0, [ _f64,_lts0 out +20 ], %g21	! store_burst.c : 14
	}
	! <0023>
	{
	  stw,2	0x0, [ _f64,_lts0 out +24 ], %g22	! store_burst.c : 14
	}
	! <0024>
	{
	  stw,2	0x0, [ _f64,_lts0 out +28 ], %g23	! store_burst.c : 14
	}
	! <0025>
	{
	  stw,2	0x0, [ _f64,_lts0 out +32 ], %g24	! store_burst.c : 15
	}
	! <0026>
	{
	  stw,2	0x0, [ _f64,_lts0 out +36 ], %g25	! store_burst.c : 15
	}
	! <0027>
	{
	  stw,2	0x0, [ _f64,_lts0 out +40 ], %g26	! store_burst.c : 15
	}
	! <0028>
	{
	  stw,2	0x0, [ _f64,_lts0 out +44 ], %g27	! store_burst.c : 15
	}
	! <0029>
	{
	  stw,2	0x0, [ _f64,_lts0 out +48 ], %g28	! store_burst.c : 16
	}
	! <0030>
	{
	  stw,2	0x0, [ _f64,_lts0 out +52 ], %g29	! store_burst.c : 16
	}
	! <0031>
	{
	  stw,2	0x0, [ _f64,_lts0 out +56 ], %g30	! store_burst.c : 16
	}
	! <0032>
	{
	  stw,2	0x0, [ _f64,_lts0 out +60 ], %g31	! store_burst.c : 16
	}
	! <0033>
	{
	  ct	%ctpr3					! store_burst.c : 17
	}
	.size	main, .- main
! -----------------------------------------------------------------------------
	.section .bss
	.global	out
	.type	out, #object
	.size	out, 0x40
	.align	16
out:
	.skip	0x40
! -----------------------------------------------------------------------------
	.data
	.global	src
	.type	src, #object
	.size	src, 0x40
	.align	16
src:
	.uadword	0x200000001
	.uadword	0x400000003
	.uadword	0x600000005
	.uadword	0x800000007
	.uadword	0xa00000009
	.uadword	0xc0000000b
	.uadword	0xe0000000d
	.uadword	0x100000000f
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
