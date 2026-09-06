	.file	"poly_covariance.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xf, nfx = 0x0, dbl = 0x0
	  return	%ctpr3
	  addd,1	0x0, 0x0, %g17
	  ldd,3	0x0, [ _f64,_lts2 data ], %g16
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +8 ], %g18
	  ldd,5	0x0, [ _f64,_lts2 data +32 ], %g19
	}
	{
	  ldd,3	0x0, [ _f64,_lts2 data +40 ], %g20
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +64 ], %g21
	  ldd,5	0x0, [ _f64,_lts2 data +72 ], %g22
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +16 ], %g23
	  ldd,5	0x0, [ _f64,_lts2 data +24 ], %g24
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +96 ], %g26
	  faddd,4	0x0, %g16, %g25
	  ldd,5	0x0, [ _f64,_lts2 data +104 ], %g27
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +48 ], %g29
	  faddd,4	0x0, %g18, %g28
	  ldd,5	0x0, [ _f64,_lts2 data +56 ], %g30
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 data +80 ], %g31
	  ldd,5	0x0, [ _f64,_lts2 data +88 ], %r3
	}
	{
	  addd,1	0x0, _f64,_lts0 0x3ff8000000000000, %r4
	  ldd,3	0x0, [ _f64,_lts2 data +120 ], %r5
	}
	{
	  addd,0	0x0, %r4, %r7
	  ldd,3	0x0, [ _f64,_lts0 data +112 ], %r6
	  faddd,4	%g25, %g19, %g25
	  std,5	0x0, [ _f64,_lts2 cov ], %g17
	}
	{
	  nop 2
	  fsubd,0	%r7, _f64,_lts0 0x3ff0000000000000, %g28
	  faddd,3	%g28, %g20, %g17
	}
	{
	  faddd,3	%g25, %g21, %g25
	  faddd,4	0x0, %g23, %r7
	  faddd,5	0x0, %g24, %r9
	}
	{
	  nop 2
	  faddd,3	%g17, %g22, %g17
	}
	{
	  faddd,3	%g25, %g26, %g25
	  faddd,4	%r7, %g29, %r7
	  faddd,5	%r9, %g30, %r9
	}
	{
	  nop 2
	  faddd,3	%g17, %g27, %g17
	}
	{
	  nop 1
	  faddd,3	%r7, %g31, %r7
	  faddd,4	%r9, %r3, %r9
	  fdivd,5	%g25, %r4, %g25
	}
	{
	  nop 2
	  fdivd,5	%g17, %r4, %g17
	}
	{
	  nop 3
	  faddd,3	%r7, %r6, %r7
	  faddd,4	%r9, %r5, %r9
	}
	{
	  nop 1
	  fdivd,5	%r9, %r4, %r9
	}
	{
	  nop 2
	  fdivd,5	%r7, %r4, %r4
	}
	{
	  nop 1
	  fsubd,3	%g16, %g25, %g16
	  fsubd,4	%g19, %g25, %g19
	  fsubd,5	%g21, %g25, %g21
	}
	{
	  fsubd,5	%g18, %g17, %g18
	}
	{
	  qppackdl,3	%g17, %g25, %r7
	}
	{
	  nop 1
	  fmuld,3	%g19, %g19, %r10
	  fmuld,4	%g21, %g21, %r11
	  stqp,5	0x0, [ _f64,_lts0 mean ], %r7
	}
	{
	  fmuld,3	%g18, %g18, %r7
	}
	{
	  qppackdl,3	%g18, %g16, %g16
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 data ], %g16
	}
	{
	  fsubd,3	%g24, %r9, %g16
	}
	{
	  faddd,3	0x0, %r7, %g24
	}
	{
	  fsubd,3	%g23, %r4, %g23
	  qppackdl,4	%r9, %r4, %r7
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 mean +16 ], %r7
	}
	{
	  fsubd,0	%g29, %r4, %g29
	  ldd,3	0x0, [ _f64,_lts0 data ], %r7
	  fsubd,4	%g20, %g17, %g20
	  fsubd,5	%g30, %r9, %g30
	}
	{
	  fmuld,3	%g18, %g16, %r12
	  fmuld,4	%g16, %g16, %r13
	}
	{
	  nop 1
	  fmuld,3	%g18, %g23, %r14
	  fmuld,4	%g23, %g23, %r15
	  fmuld,5	%g23, %g16, %r16
	}
	{
	  fsubd,0	%g31, %r4, %g31
	  fmuld,1	%g29, %g29, %r18
	  fmuld,2	%g19, %g29, %r19
	  fsubd,3	%g22, %g17, %g22
	  fsubd,4	%r3, %r9, %r3
	  fmuld,5	%g20, %g20, %r17
	}
	{
	  fmuld,0	%r7, %g16, %r7
	  qppackdl,1	%g16, %g23, %g16
	  fmuld,3	%r7, %r7, %r20
	  fmuld,4	%r7, %g18, %g18
	  fmuld,5	%r7, %g23, %r21
	}
	{
	  fmuld,0	%g20, %g30, %r24
	  fmuld,1	%g20, %g29, %r25
	  fmuld,2	%g29, %g30, %r26
	  fmuld,3	%g19, %g20, %g23
	  fmuld,4	%g30, %g30, %r22
	  fmuld,5	%g19, %g30, %r23
	}
	{
	  qppackdl,1	%g20, %g19, %g19
	  stqp,2	0x0, [ _f64,_lts0 data +16 ], %g16
	  faddd,3	0x0, %r12, %r12
	  faddd,4	0x0, %r13, %r13
	  faddd,5	0x0, %r14, %r14
	}
	{
	  fsubd,0	%g26, %g25, %g25
	  fsubd,1	%r5, %r9, %g26
	  fsubd,2	%r6, %r4, %g27
	  faddd,3	0x0, %r15, %g16
	  faddd,4	0x0, %r16, %g20
	  fsubd,5	%g27, %g17, %g17
	}
	{
	  faddd,0	0x0, %r7, %r6
	  fmuld,1	%g21, %g31, %r9
	  fmuld,2	%g31, %g31, %r7
	  faddd,3	0x0, %r20, %r4
	  faddd,4	0x0, %g18, %g18
	  faddd,5	0x0, %r21, %r5
	}
	{
	  fmuld,0	%g22, %r3, %r21
	  fmuld,1	%r3, %r3, %r27
	  fmuld,2	%g22, %g31, %r28
	  fmuld,3	%g22, %g22, %r15
	  fmuld,4	%g21, %g22, %r16
	  fmuld,5	%g21, %r3, %r20
	}
	{
	  fdtoistr,0	%g31, %r17
	  stqp,2	0x0, [ _f64,_lts0 data +32 ], %g19
	  faddd,3	%g24, %r17, %g24
	  faddd,4	%r13, %r22, %r13
	  fmuld,5	%g31, %r3, %r29
	}
	{
	  fmuld,0	%g25, %g25, %r14
	  fmuld,1	%g25, %g26, %r18
	  fmuld,2	%g27, %g26, %r22
	  faddd,3	%r12, %r24, %g19
	  faddd,4	%r14, %r25, %r12
	  faddd,5	%g16, %r18, %g16
	}
	{
	  faddd,0	%r6, %r23, %g23
	  fmuld,1	%g25, %g27, %r10
	  fmuld,2	%g26, %g26, %r6
	  faddd,3	%g20, %r26, %g20
	  faddd,4	%r4, %r10, %r4
	  faddd,5	%g18, %g23, %g18
	}
	{
	  fmuld,0	%g17, %g27, %r25
	  fmuld,1	%g27, %g27, %r26
	  fmuld,2	%g17, %g26, %r24
	  faddd,3	%r5, %r19, %r5
	  fmuld,4	%g25, %g17, %r23
	  fmuld,5	%g17, %g17, %r19
	}
	{
	  faddd,5	%g24, %r15, %g24
	}
	{
	  faddd,3	%r13, %r27, %r13
	  faddd,4	%r12, %r28, %r12
	  faddd,5	%g19, %r21, %g19
	}
	{
	  qppackdl,0	%g22, %g21, %g21
	  qppackdl,1	%g17, %g25, %g17
	  faddd,2	%g23, %r20, %g23
	  faddd,3	%g20, %r29, %g20
	  faddd,4	%r4, %r11, %r4
	  faddd,5	%g16, %r7, %g16
	}
	{
	  qppackdl,0	%g30, %g29, %g25
	  qppackdl,1	%r3, %g31, %g29
	  stqp,2	0x0, [ _f64,_lts0 data +64 ], %g21
	  faddd,3	%r5, %r9, %g22
	  faddd,5	%g18, %r16, %g18
	}
	{
	  qppackdl,0	%g26, %g27, %g24
	  sxt,1	0x2, %r17, %r0
	  stqp,2	0x0, [ _f64,_lts0 data +96 ], %g17
	  faddd,3	%g24, %r19, %g21
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 data +112 ], %g24
	  faddd,3	%g19, %r24, %g17
	  faddd,4	%r13, %r6, %g19
	  faddd,5	%r12, %r25, %g26
	}
	{
	  faddd,0	%g23, %r18, %g23
	  stqp,2	0x0, [ _f64,_lts0 data +48 ], %g25
	  faddd,3	%g16, %r26, %g16
	  faddd,4	%g20, %r22, %g20
	  faddd,5	%r4, %r14, %g24
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 data +80 ], %g29
	  faddd,3	%g18, %r23, %g18
	  faddd,4	%g22, %r10, %g22
	}
	{
	  nop 1
	  fdivd,5	%g21, %g28, %g21
	}
	{
	  nop 1
	  fdivd,5	%g17, %g28, %g17
	}
	{
	  nop 1
	  fdivd,5	%g22, %g28, %g22
	}
	{
	  nop 1
	  fdivd,5	%g18, %g28, %g18
	}
	{
	  nop 1
	  fdivd,5	%g16, %g28, %g16
	}
	{
	  nop 1
	  fdivd,5	%g24, %g28, %g24
	}
	{
	  nop 1
	  fdivd,5	%g23, %g28, %g23
	}
	{
	  nop 1
	  fdivd,5	%g20, %g28, %g20
	}
	{
	  nop 1
	  fdivd,5	%g19, %g28, %g19
	}
	{
	  nop 1
	  fdivd,5	%g26, %g28, %g25
	}
	{
	  qppackdl,3	%g21, %g18, %g21
	}
	{
	  nop 2
	  stqp,5	0x0, [ _f64,_lts0 cov +32 ], %g21
	}
	{
	  qppackdl,3	%g18, %g24, %g18
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 cov ], %g18
	}
	{
	  qppackdl,3	%g17, %g23, %g18
	  qppackdl,4	%g23, %g22, %g21
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 cov +96 ], %g18
	}
	{
	  qppackdl,3	%g20, %g16, %g16
	  stqp,5	0x0, [ _f64,_lts0 cov +16 ], %g21
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 cov +80 ], %g16
	}
	{
	  qppackdl,3	%g19, %g20, %g16
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 cov +112 ], %g16
	}
	{
	  qppackdl,3	%g17, %g25, %g16
	  qppackdl,4	%g25, %g22, %g17
	}
	{
	  stqp,5	0x0, [ _f64,_lts0 cov +48 ], %g16
	}
	{
	  ct	%ctpr3
	  stqp,5	0x0, [ _f64,_lts0 cov +64 ], %g17
	}
	.size	main, .- main
	.section .bss
	.global	data
	.type	data, #object
	.size	data, 0x80
	.align	16
data:
	.skip	0x80
	.global	cov
	.type	cov, #object
	.size	cov, 0x80
	.align	16
cov:
	.skip	0x80
	.global	mean
	.type	mean, #object
	.size	mean, 0x20
	.align	16
mean:
	.skip	0x20
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
