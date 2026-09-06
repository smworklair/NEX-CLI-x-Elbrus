	.file	"poly_jacobi1d.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x4, nfx = 0x0, dbl = 0x0
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts1 A +8 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +16 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 A ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +24 ], %g19
	  ldd,2	0x0, [ _f64,_lts2 A +64 ], %g20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +72 ], %g21
	  ldd,2	0x0, [ _f64,_lts2 A +48 ], %g22
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +56 ], %g23
	  ldd,2	0x0, [ _f64,_lts2 A +32 ], %g24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +40 ], %g25
	  ldd,2	0x0, [ _f64,_lts2 A +80 ], %g26
	}
	{
	  faddd,0	%g18, %g16, %g16
	  faddd,1	%g16, %g17, %g27
	  ldd,2	0x0, [ _f64,_lts2 A +88 ], %g28
	  addd,4	0x0, _f64,_lts0 0x3fd555475a31a4be, %g29
	}
	{
	  faddd,1	%g17, %g19, %g30
	  ldd,2	0x0, [ _f64,_lts0 B ], %g31
	  ldd,3	0x0, [ _f64,_lts2 B +88 ], %r2
	}
	{
	  faddd,0	%g20, %g21, %r3
	}
	{
	  faddd,0	%g22, %g23, %r4
	  faddd,1	%g23, %g20, %r5
	  faddd,2	%g19, %g24, %r6
	}
	{
	  faddd,0	%g27, %g19, %g19
	  faddd,1	%g16, %g17, %g16
	  faddd,2	%g24, %g25, %g17
	  faddd,3	%g25, %g22, %g27
	  faddd,4	%g21, %g26, %r7
	}
	{
	  faddd,0	%g30, %g24, %g24
	}
	{
	  faddd,0	%r3, %g26, %g26
	}
	{
	  faddd,0	%r4, %g20, %g20
	  faddd,1	%r5, %g21, %g21
	  faddd,2	%r6, %g25, %g25
	}
	{
	  fmuld,0	%g29, %g19, %g19
	  fmuld,1	%g29, %g16, %g16
	  faddd,2	%g17, %g22, %g17
	  faddd,3	%g27, %g23, %g22
	  faddd,4	%r7, %g28, %g23
	}
	{
	  fmuld,0	%g29, %g24, %g24
	}
	{
	  fmuld,0	%g29, %g26, %g26
	}
	{
	  fmuld,0	%g29, %g20, %g20
	  fmuld,1	%g29, %g21, %g21
	  fmuld,2	%g29, %g25, %g25
	}
	{
	  faddd,0	%g31, %g16, %g27
	  faddd,1	%g16, %g19, %g16
	  fmuld,2	%g29, %g17, %g17
	  fmuld,3	%g29, %g22, %g22
	  fmuld,4	%g29, %g23, %g23
	}
	{
	  nop 1
	  faddd,0	%g19, %g24, %g30
	}
	{
	  faddd,0	%g20, %g21, %r3
	  faddd,1	%g21, %g26, %r4
	  faddd,2	%g24, %g25, %r5
	}
	{
	  faddd,0	%g27, %g19, %g19
	  faddd,1	%g16, %g24, %g16
	  faddd,2	%g25, %g17, %g24
	  faddd,3	%g26, %g23, %g27
	}
	{
	  faddd,0	%g30, %g25, %g25
	  faddd,3	%g22, %g20, %r6
	}
	{
	  faddd,0	%g17, %g22, %g30
	}
	{
	  faddd,0	%r3, %g26, %g26
	  faddd,1	%r4, %g23, %g23
	  faddd,2	%r5, %g17, %g17
	}
	{
	  fmuld,0	%g29, %g19, %g19
	  fmuld,1	%g29, %g16, %g16
	  faddd,2	%g24, %g22, %g22
	  faddd,3	%g27, %r2, %g24
	}
	{
	  fmuld,0	%g29, %g25, %g25
	  faddd,3	%r6, %g21, %g21
	}
	{
	  faddd,0	%g30, %g20, %g20
	}
	{
	  fmuld,0	%g29, %g26, %g26
	  fmuld,1	%g29, %g23, %g23
	  fmuld,2	%g29, %g17, %g17
	}
	{
	  faddd,0	%g18, %g19, %g18
	  faddd,1	%g19, %g16, %g19
	  fmuld,2	%g29, %g22, %g22
	  fmuld,3	%g29, %g24, %g24
	}
	{
	  faddd,0	%g16, %g25, %g27
	  fmuld,3	%g29, %g21, %g21
	}
	{
	  fmuld,0	%g29, %g20, %g20
	}
	{
	  faddd,0	%g26, %g23, %g30
	  faddd,1	%g25, %g17, %r3
	}
	{
	  faddd,0	%g18, %g16, %g16
	  faddd,1	%g19, %g25, %g18
	  faddd,2	%g17, %g22, %g19
	}
	{
	  faddd,0	%g27, %g17, %g17
	  faddd,3	%g21, %g26, %g25
	  faddd,4	%g23, %g24, %r4
	}
	{
	  faddd,0	%g22, %g20, %g27
	}
	{
	  faddd,0	%g20, %g21, %r5
	  faddd,1	%g30, %g24, %g24
	  faddd,2	%r3, %g22, %g22
	}
	{
	  fmuld,0	%g29, %g16, %g16
	  fmuld,1	%g29, %g18, %g18
	  faddd,2	%g19, %g20, %g19
	}
	{
	  fmuld,0	%g29, %g17, %g17
	  faddd,3	%g25, %g23, %g20
	  faddd,4	%r4, %g28, %g23
	}
	{
	  faddd,0	%g27, %g21, %g21
	}
	{
	  faddd,0	%r5, %g26, %g25
	  fmuld,1	%g29, %g24, %g24
	  fmuld,2	%g29, %g22, %g22
	}
	{
	  faddd,0	%g16, %g18, %g26
	  fmuld,1	%g29, %g19, %g19
	  std,2	0x0, [ _f64,_lts0 B +8 ], %g16
	}
	{
	  faddd,2	%g18, %g17, %g27
	  fmuld,3	%g29, %g23, %g23
	  fmuld,5	%g29, %g20, %g20
	}
	{
	  fmuld,2	%g29, %g21, %g21
	}
	{
	  faddd,0	%g17, %g22, %g28
	  qppackdl,1	%g17, %g18, %g30
	  fmuld,2	%g29, %g25, %g25
	  faddd,5	%g31, %g16, %g16
	}
	{
	  faddd,0	%g26, %g17, %g17
	  faddd,1	%g22, %g19, %g26
	  stqp,2	0x0, [ _f64,_lts0 B +16 ], %g30
	}
	{
	  qppackdl,1	%g19, %g22, %g22
	  faddd,2	%g27, %g22, %g27
	  faddd,3	%g24, %g23, %g31
	  qppackdl,4	%g24, %g20, %r3
	  faddd,5	%g20, %g24, %g30
	}
	{
	  faddd,0	%g19, %g21, %r4
	  stqp,2	0x0, [ _f64,_lts2 B +32 ], %g22
	  std,5	0x0, [ _f64,_lts0 B +80 ], %g23
	}
	{
	  faddd,0	%g25, %g20, %g22
	  faddd,1	%g21, %g25, %r5
	  faddd,2	%g28, %g19, %g19
	  faddd,3	%g16, %g18, %g16
	  stqp,5	0x0, [ _f64,_lts0 B +64 ], %r3
	}
	{
	  faddd,0	%g26, %g21, %g18
	  qppackdl,1	%g25, %g21, %g21
	  fmuld,2	%g29, %g17, %g17
	}
	{
	  fmuld,0	%g29, %g27, %g27
	  stqp,2	0x0, [ _f64,_lts0 B +48 ], %g21
	  faddd,3	%g30, %g23, %g23
	  faddd,4	%g31, %r2, %g26
	}
	{
	  faddd,0	%r4, %g25, %g21
	}
	{
	  faddd,0	%g22, %g24, %g22
	  faddd,1	%r5, %g20, %g20
	  fmuld,2	%g29, %g19, %g19
	  fmuld,3	%g29, %g16, %g16
	}
	{
	  fdtoistr,0	%g17, %g24
	  fmuld,1	%g29, %g18, %g18
	}
	{
	  fmuld,3	%g29, %g26, %g25
	  fmuld,5	%g29, %g23, %g23
	}
	{
	  fmuld,2	%g29, %g21, %g21
	}
	{
	  fmuld,0	%g29, %g22, %g22
	  fmuld,1	%g29, %g20, %g20
	  qppackdl,4	%g27, %g17, %g17
	  std,5	0x0, [ _f64,_lts0 A +8 ], %g16
	}
	{
	  qppackdl,0	%g18, %g19, %g16
	  stqp,5	0x0, [ _f64,_lts0 A +16 ], %g17
	}
	{
	  stqp,2	0x0, [ _f64,_lts2 A +32 ], %g16
	  std,5	0x0, [ _f64,_lts0 A +80 ], %g25
	}
	{
	  sxt,3	0x2, %g24, %r0
	}
	{
	  qppackdl,0	%g23, %g22, %g16
	  qppackdl,1	%g20, %g21, %g17
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 A +64 ], %g16
	}
	{
	  ct	%ctpr3
	  stqp,2	0x0, [ _f64,_lts0 A +48 ], %g17
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x60
	.align	16
A:
	.skip	0x60
	.global	B
	.type	B, #object
	.size	B, 0x60
	.align	16
B:
	.skip	0x60
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
