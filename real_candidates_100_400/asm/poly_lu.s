	.file	"poly_lu.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xe, nfx = 0x1, dbl = 0x1
	  adds,1,sm	0x5, 0x0, %r15
	  addd,2	0x1f, 0x9, %r17
	  ldd,3	0x0, [ _f64,_lts2 A ], %g16
	  addd,4,sm	0x18, 0x0, %r13
	  scld,5	0x3, 0x4, %r16
	}
	{
	  cmpesb,0,sm	0x0, 0x1, %pred8
	  cmpesb,1,sm	0x0, 0x1, %pred7
	  ldd,2,sm	0x0, [ _f64,_lts2 A +8 ], %g18
	  ldd,3	0x0, [ _f64,_lts0 A +40 ], %g17
	  cmpesb,4,sm	0x0, 0x0, %pred6
	  addd,5,sm	0x0, 0x0, %r14
	}
	{
	  cmpesb,1,sm	0x0, 0x0, %pred5
	  ldd,2,sm	0x0, [ _f64,_lts2 A +16 ], %g19
	  cmpesb,3,sm	0x0, 0x0, %pred4
	  cmpesb,4,sm	0x0, 0x0, %pred3
	  addd,5,sm	0x1f, 0x1, %r11
	}
	{
	  cmpesb,0,sm	0x0, 0x1, %pred0
	  cmpesb,1,sm	0x0, 0x1, %pred2
	  ldd,2	0x0, [ _f64,_lts0 A +48 ], %g20
	  addd,3,sm	0x0, [ _f64,_lts0 A +48 ], %r18
	  cmpesb,4,sm	0x0, 0x1, %pred1
	  ldd,5,sm	0x0, [ _f64,_lts2 A +56 ], %g21
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 A +24 ], %r12
	  merged,1,sm	%r17, _f16s,_lts0lo 0x668, %g22, %pred8
	  addd,3,sm	0x1f, 0x9, %r0
	  merged,4,sm	%r16, _f16s,_lts0hi 0x670, %g23, %pred8
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +64 ], %r9
	  addd,1,sm	0x0, [ _f64,_lts2 A +72 ], %r10
	  addd,2,sm	0x0, [ _f64,_lts0 A +64 ], %r8
	}
	{
	  nop 2
	  addd,1,sm	%g22, [ _f64,_lts0 A ], %r7
	  addd,2,sm	%g23, [ _f64,_lts0 A ], %r6
	  fdivd,5	%g17, %g16, %g16
	}
	{
	  nop 7
	  addd,0,sm	0x0, %r12, %r5
	}
	{
	  nop 2
	}
	{
	  nop 1
	  fmuld,3,sm	%g16, %g18, %g17
	  fmuld,4,sm	%g16, %g19, %g18
	  std,5	0x0, [ _f64,_lts0 A +40 ], %g16
	}
	{
	  nop 1
	  addd,0,sm	0x0, %g16, %r4
	  addd,5,sm	0x0, %g16, %r3
	}
	{
	  nop 3
	  fsubd,3,sm	%g20, %g17, %g16
	  fsubd,4	%g21, %g18, %g17
	}
	{
	  std,5	0x0, [ _f64,_lts0 A +48 ], %g16
	}
	{
	  std,5	0x0, [ _f64,_lts0 A +56 ], %g17
	}
.L7061:
	{
	  disp	%ctpr1, .L7061
	  cmpledb,0,sm	%r10, %r7, %pred9
	  addd,1,sm	%r14, %r13, %g18
	  fmuld,2,sm	%r4, %r12, %g16
	  ldd,3,sm	%r11, [ _f64,_lts0 A +40 ], %g19
	  cmpledb,4,sm	%r6, %r8, %pred8
	  fmuld,5,sm	%r3, %r5, %g17
	  pass	%pred5, @p0
	  andp	@p0, @p0, @p4
	  pass	@p4, %pred10
	}
	{
	  addd,0,sm	%r13, [ _f64,_lts0 A ], %g21
	  addd,1,sm	0x8, %r14, %g20
	  addd,2,sm	%g18, [ _f64,_lts0 A ], %g18
	  ldd,3,sm	0x0, [ _f64,_lts2 A +40 ], %g22
	  addd,4,sm	%r11, [ _f64,_lts2 A +40 ], %g24
	  addd,5,sm	%r11, [ _f64,_lts0 A ], %g23
	  pass	%pred4, @p0
	  pass	%pred8, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred8
	  pass	%pred3, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred11
	}
	{
	  addd,0,sm	%g20, %g21, %g20
	  cmpledb,1,sm	%r10, %g18, %pred8
	  cmplsb,3,sm	%r15, 0x5, %pred12
	  addd,4,sm	%r11, [ _f64,_lts0 A +48 ], %g18
	  pass	%pred2, @p0
	  pass	%pred9, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred9
	  pass	%pred11, @p2
	  landp	~@p2, ~@p4, @p5
	  pass	@p5, %pred11
	}
	{
	  cmpledb,0,sm	%g20, %r8, %pred9
	  cmpledb,1,sm	%r18, %g24, %pred15
	  merged,2,sm	%r17, _f16s,_lts0lo 0x668, %g20, %pred7
	  cmpledb,3,sm	%g18, %g23, %pred14
	  merged,4,sm	%r16, _f16s,_lts0hi 0x670, %g21, %pred7
	  addd,5,sm	%r11, [ _f64,_lts1 A +8 ], %g23
	  pass	%pred1, @p0
	  pass	%pred8, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred8
	  pass	%pred0, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred13
	}
	{
	  fsubd,0,sm	%r9, %g16, %g16
	  addd,1,sm	%g20, [ _f64,_lts0 A ], %r7 ? %pred5
	  addd,2,sm	0x0, %g18, %r10 ? %pred5
	  cmpledb,3,sm	%g23, %g24, %pred6 ? %pred5
	  addd,4,sm	%g21, [ _f64,_lts0 A ], %r6 ? %pred5
	  fsubd,5,sm	%r9, %g17, %g17
	  pass	%pred6, @p0
	  pass	%pred9, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred8
	  pass	%pred13, @p2
	  landp	~@p4, ~@p2, @p5
	  pass	@p5, %pred9
	}
	{
	  cmpledb,0,sm	%g18, [ _f64,_lts1 A +40 ], %pred2 ? %pred5
	  merged,1,sm	0x0, _f16s,_lts0lo 0x1f40, %r14, %pred7 ? %pred5
	  adds,2,sm	%r15, 0x1, %r15 ? %pred5
	  addd,3,sm	0x0, %g24, %r8 ? %pred5
	  cmpesb,4,sm	0x0, 0x1, %pred7 ? %pred5
	  addd,5,sm	0x0, %g19, %r9 ? %pred5
	  pass	%pred11, @p0
	  pass	%pred9, @p1
	  landp	~@p0, ~@p1, @p4
	  pass	@p4, %pred8
	  pass	%pred15, @p2
	  pass	%pred5, @p3
	  movep	@p3, @p2, @p5
	  pass	@p5, %pred3
	  movep	@p3, @p2, @p6
	  pass	@p6, %pred4
	}
	{
	  nop 1
	  addd,1,sm	0x0, %g22, %r4 ? %pred5
	  addd,3,sm	0x0, %g22, %r3 ? %pred5
	  pass	%pred14, @p0
	  pass	%pred5, @p1
	  movep	@p1, @p0, @p4
	  pass	@p4, %pred1
	  movep	@p1, @p0, @p5
	  pass	@p5, %pred0
	}
	{
	  addd,0,sm	0x0, %r11, %r13 ? %pred5
	  std,2	%r13, [ _f64,_lts0 A +40 ], %g16 ? %pred8
	  std,5	%r13, [ _f64,_lts0 A +40 ], %g17 ? ~%pred8
	}
	{
	  nop 4
	  ldd,0,sm	%r11, [ _f64,_lts0 A ], %g16
	  addd,3,sm	0x0, %r0, %r11 ? %pred5
	  addd,4,sm	0x8, %r0, %r0 ? %pred5
	}
	{
	  ct	%ctpr1 ? %pred10
	  addd,0,sm	0x0, %g16, %r12 ? %pred5
	  addd,3,sm	0x0, %g16, %r5 ? %pred5
	  pass	%pred12, @p0
	  pass	%pred5, @p1
	  movep	@p1, @p0, @p4
	  pass	@p4, %pred5
	}

	{
	  scld,0,sm	0x5, 0x4, %r8
	  adds,1	0x2, 0x0, %r16
	  addd,2	0x5, 0x0, %r23
	  adds,3	0x0, 0x0, %r22
	}
	{
	  ldb,0,sm	%r8, [ _f64,_lts0 A ], %empty, mas=0x20
	}
.L3747:
	{
	  disp	%ctpr1, .L7422
	  addd,0	0x1, 0x0, %r0
	  cmpssb,1	%r16, 0x1, %pred1
	  ldd,3	%r8, [ _f64,_lts1 A ], %g17
	  addd,4,sm	%r8, _f16s,_lts0lo 0x28, %g18
	  ldd,5	0x0, [ _f64,_lts1 A ], %g16
	}
	{
	  ldd,0,sm	%r8, [ _f64,_lts2 A +8 ], %r3
	  subs,1,sm	%r16, 0x1, %r7
	  adds,2	0x0, 0x0, %r7 ? ~%pred1
	  ldb,3,sm	%g18, [ _f64,_lts0 A ], %empty, mas=0x20
	  addd,4,sm	%r8, 0x8, %r4
	}
	{
	  cmplesb,0	0x1, %r7, %pred1
	  cmplesb,1,sm	0x2, %r7, %pred0
	  addd,2,sm	%r8, [ _f64,_lts0 A ], %r6
	}
	{
	  nop 1
	  adds,0	0x1, 0x0, %r5 ? ~%pred1
	  addd,1,sm	%r8, 0x8, %r15 ? ~%pred1
	  adds,2,sm	0x3, 0x0, %r11 ? %pred1
	  addd,3	0x2, 0x0, %r0 ? %pred1
	  addd,4,sm	0x10, 0x0, %r10 ? %pred1
	  scld,5,sm	0x3, 0x5, %r9 ? %pred1
	}
	{
	  nop 7
	  fdivd,5	%g17, %g16, %g16
	}
	{
	  nop 5
	}
	{
	  std,5	%r8, [ _f64,_lts0 A ], %g16
	}
	{
	  ct	%ctpr1 ? ~%pred1
	  ldd,0,sm	0x0, [ _f64,_lts0 A +48 ], %r2
	}
	{
	  nop 3
	}
.L6447:
	{
	  disp	%ctpr1, .L6447
	  ldd,0,sm	%r6, %r10, %g17
	  cmplesb,1,sm	%r11, %r7, %pred2
	  addd,2	%r0, 0x1, %r0 ? %pred0
	  fdivd,5	%r3, %r2, %g16
	  pass	%pred0, @p0
	  andp	@p0, @p0, @p4
	  pass	@p4, %pred1
	}
	{
	  nop 3
	  adds,1,sm	%r11, 0x1, %r11 ? %pred0
	}
	{
	  nop 7
	  addd,3,sm	0x0, %g17, %r3 ? %pred0
	}
	nop
	{
	  addd,0,sm	0x8, %r10, %r10 ? %pred1
	  addd,3,sm	%r8, %r10, %r4 ? %pred0
	  std,5	%r4, [ _f64,_lts0 A ], %g16
	}
	{
	  nop 4
	  ldd,0,sm	%r9, [ _f64,_lts1 A ], %g16
	  addd,1,sm	%r9, _f16s,_lts0lo 0x30, %r9 ? %pred1
	}
	{
	  ct	%ctpr1 ? %pred1
	  addd,3,sm	0x0, %g16, %r2 ? %pred0
	  pass	%pred2, @p0
	  pass	%pred0, @p1
	  movep	@p1, @p0, @p4
	  pass	@p4, %pred0
	}

	{
	  adds,0	0x1, 0x0, %r5
	  addd,1,sm	%r8, 0x8, %r15
	}
.L7422:
	{
	  shld,0,sm	%r0, 0x5, %g16
	  shld,1,sm	%r0, 0x4, %g17
	  shld,2,sm	%r0, 0x3, %r6
	  addd,3,sm	%r8, _f16s,_lts0lo 0x20, %g18
	  addd,4	%r8, [ _f64,_lts1 A ], %r2
	}
	{
	  addd,0,sm	%g16, %g17, %r14
	  addd,1,sm	%r6, _f16s,_lts0lo 0x20, %g16
	}
	{
	  addd,0,sm	%r14, [ _f64,_lts0 A ], %g18
	  addd,1,sm	%r6, %g18, %g17
	  ldb,2,sm	%g16, [ _f64,_lts0 A ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%g17, [ _f64,_lts0 A ], %empty, mas=0x20
	  ldb,2,sm	%g18, 0x0, %empty, mas=0x20
	}
	{
	  ldb,0,sm	%g18, _f16s,_lts0lo 0x40, %empty, mas=0x20
	  ldb,2,sm	%g18, _f16s,_lts0hi 0x80, %empty, mas=0x20
	  ldb,3,sm	%g18, _f16s,_lts1lo 0xc0, %empty, mas=0x20
	  ldb,5,sm	%g18, _f16s,_lts1hi 0x100, %empty, mas=0x20
	}
.L4011:
	{
	  disp	%ctpr2, .L6310
	  ldd,0	%r6, [ _f64,_lts0 A ], %g17
	  cmplsb,1	0x1, %r5, %pred0
	  ldd,2	%r8, [ _f64,_lts0 A ], %g16
	  addd,3,sm	0x0, %r15, %r3
	  scld,4,sm	0x5, 0x4, %r13
	  adds,5,sm	0x2, 0x0, %r10
	}
	{
	  nop 3
	  disp	%ctpr1, .L4035
	  cmplsb,0,sm	0x2, %r5, %pred1
	  addd,1,sm	%r6, _f16s,_lts0lo 0x28, %r4
	  ldd,2	%r2, %r6, %g18
	  addd,3,sm	0x10, 0x0, %r12
	  addd,5	%r8, %r6, %r11
	}
	{
	  nop 3
	  fmuld,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  fsubd,0	%g18, %g16, %r0
	}
.L6310:
	{
	  std,2	%r11, [ _f64,_lts0 A ], %r0
	  ldd,5,sm	%r4, [ _f64,_lts0 A ], %r9
	}
	{
	  ct	%ctpr1 ? ~%pred0
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %r7
	}

	{
	  adds,0,sm	%r10, 0x1, %r10
	  addd,1,sm	%r13, %r6, %r4
	  addd,2,sm	%r8, %r12, %r3
	  addd,3,sm	%r13, _f16s,_lts0lo 0x28, %r13
	  addd,4,sm	0x8, %r12, %r12
	  pass	%pred1, @p0
	  andp	@p0, @p0, @p4
	  pass	@p4, %pred0
	}
	{
	  nop 2
	  cmplsb,0,sm	%r10, %r5, %pred1
	}
	{
	  nop 3
	  fmuld,0	%r7, %r9, %g16
	}
	{
	  nop 2
	  fsubd,0	%r0, %g16, %r0
	}
	{
	  ct	%ctpr2
	}
.L4035:
	{
	  disp	%ctpr1, .L4011
	  adds,0	%r5, 0x1, %r5
	  addd,1,sm	0x8, %r6, %r6
	  ldd,3	%r14, [ _f64,_lts1 A ], %g16
	  addd,4,sm	%r14, _f16s,_lts0lo 0x30, %r14
	  ldd,5	%r11, [ _f64,_lts1 A ], %g17
	}
	{
	  nop 3
	  cmplsb,0	%r5, %r16, %pred0
	}
	{
	  nop 7
	  fdivd,5	%g17, %g16, %g16
	}
	{
	  nop 5
	}
	{
	  ct	%ctpr1 ? %pred0
	  std,5	%r11, [ _f64,_lts0 A ], %g16
	}

	{
	  sxt,0	0x2, %r16, %g16
	  subs,1,sm	%r16, 0x1, %r21
	  sxt,2,sm	0x2, _f16s,_lts0lo 0xc8, %g17
	  addd,3,sm	%r8, [ _f64,_lts1 A +8 ], %r14
	  adds,4,sm	0x0, %r16, %r7
	}
	{
	  sxt,0,sm	0x2, %r21, %g19
	  shld,1,sm	%g16, 0x5, %g16
	  shld,2,sm	%g16, 0x3, %g18
	  addd,3,sm	%r8, [ _f64,_lts0 A ], %g20
	  addd,4,sm	%r8, [ _f64,_lts2 A +-8 ], %g21
	}
	{
	  addd,0	0x0, %g18, %r6
	  shld,1,sm	%g17, 0x5, %g17
	  shld,2,sm	%g17, 0x3, %g22
	  cmplsb,4	%r21, _f16s,_lts0lo 0xc8, %pred0
	}
	{
	  shld,0,sm	%g19, 0x3, %g23
	  addd,1,sm	%r6, [ _f64,_lts0 A +8 ], %r13
	  shld,2,sm	%g19, 0x5, %g19
	  ldb,3,sm	%r2, %g18, %empty, mas=0x20
	  addd,4,sm	%g16, %g18, %g16
	  addd,5,sm	%g21, %g18, %r20
	}
	{
	  addd,0,sm	%r14, %r6, %r12
	  addd,1,sm	%r2, %g23, %g21
	  addd,2,sm	%r14, %g23, %g24
	  ldb,3,sm	%g18, [ _f64,_lts0 A ], %empty, mas=0x20
	  addd,4,sm	%r2, %r6, %r11
	  addd,5,sm	%g17, %g22, %r4
	}
	{
	  cmpledb,0,sm	%r12, %g21, %pred1 ? %pred0
	  addd,1,sm	%g20, %g18, %r19
	  addd,2,sm	%g17, %g23, %r5
	  addd,4,sm	%g16, [ _f64,_lts0 A +-40 ], %r18
	  addd,5,sm	%g16, [ _f64,_lts2 A +-32 ], %r17
	}
	{
	  cmpledb,0,sm	%g24, %r11, %pred2 ? %pred0
	  addd,1,sm	%g19, %g22, %r10
	  addd,2,sm	%g19, %g23, %r9
	  addd,3,sm	%r2, %g22, %r3
	  addd,4,sm	%r14, %g22, %r0
	  addd,5,sm	%r13, %r4, %r26 ? ~%pred0
	}
	{
	  addd,0,sm	%r13, %r5, %r25 ? ~%pred0
	}
.L3775:
	{
	  disp	%ctpr1, .L5957
	  cmpledb,0,sm	%r0, %r11, %pred2 ? ~%pred0
	  cmpledb,1,sm	%r12, %r3, %pred1 ? ~%pred0
	  addd,2,sm	%r13, %r9, %r25 ? %pred0
	  cmpledb,3,sm	%r14, %r11, %pred3
	  cmpledb,4	%r19, %r11, %pred4
	  addd,5,sm	%r13, %r10, %r26 ? %pred0
	}
	{
	  disp	%ctpr2, .L5930
	  cmpledb,0,sm	%r12, %r20, %pred5
	  cmpledb,1,sm	%r12, %r2, %pred6
	  addd,2,sm	%r17, %r6, %g16
	  cmpledb,3,sm	%r26, %r11, %pred7 ? ~%pred0
	  addd,4,sm	%r6, [ _f64,_lts2 A ], %g18
	  addd,5,sm	%r6, [ _f64,_lts0 A +8 ], %g17
	  pass	%pred4, @p0
	  pass	%pred2, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred4
	  pass	%pred3, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred3
	}
	{
	  cmpledb,0,sm	%r25, %r11, %pred7 ? %pred0
	  cmpledb,1,sm	%g16, %r11, %pred8
	  addd,2,sm	%r18, %r6, %g16
	  cmpledb,3,sm	%g17, %r11, %pred9
	  addd,4,sm	%g18, %r4, %g17 ? ~%pred0
	  addd,5,sm	%g18, %r10, %g17 ? %pred0
	  pass	%pred5, @p0
	  pass	%pred1, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred4
	  pass	%pred6, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred6
	  pass	%pred3, @p3
	  landp	~@p3, ~@p0, @p6
	  pass	@p6, %pred10
	}
	{
	  addd,0,sm	%g18, %r9, %g19 ? %pred0
	  cmpledb,1,sm	%r12, %g16, %pred11
	  addd,2,sm	%g18, %r5, %g19 ? ~%pred0
	  addd,3,sm	0x8, %r6, %g16
	  cmpledb,4,sm	%r12, %g17, %pred12 ? ~%pred0
	  addd,5,sm	%r6, [ _f64,_lts0 A ], %r15
	  pass	%pred3, @p0
	  pass	%pred6, @p1
	  landp	~@p0, ~@p1, @p4
	  pass	@p4, %pred4
	  pass	%pred8, @p2
	  landp	~@p4, @p2, @p5
	  pass	@p5, %pred6
	  pass	%pred7, @p3
	  landp	@p2, @p3, @p6
	  pass	@p6, %pred8
	}
	{
	  cmplsb,0,sm	0x0, %r16, %pred13
	  cmpledb,1,sm	%r12, %g19, %pred12 ? %pred0
	  ldd,2	%r2, %r6, %r13
	  ldb,3,sm	%g16, [ _f64,_lts0 A ], %empty, mas=0x20
	  cmpledb,4,sm	%r12, %r15, %pred4
	  ldb,5,sm	%r2, %g16, %empty, mas=0x20
	  pass	%pred8, @p0
	  pass	%pred9, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred8
	  pass	%pred4, @p2
	  landp	~@p2, ~@p4, @p5
	  pass	@p5, %pred0
	}
	{
	  ct	%ctpr2 ? %pred10
	  addd,0	%r8, %r6, %r0
	  addd,1,sm	0x0, _f64,_lts0 0x20c42000000000, %g16
	  pass	%pred0, @p0
	  pass	%pred11, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred8
	  pass	%pred6, @p2
	  pass	%pred7, @p3
	  landp	@p2, @p3, @p5
	  pass	@p5, %pred6
	  landp	@p0, ~@p1, @p6
	  pass	@p6, %pred0
	}
	{
	  pass	%pred6, @p0
	  pass	%pred9, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred6
	  pass	%pred8, @p2
	  pass	%pred12, @p3
	  landp	@p2, @p3, @p5
	  pass	@p5, %pred7
	}
	{
	  merges,0,sm	0x1, %r16, %r24, %pred13 ? %pred6
	  pass	%pred7, @p0
	  pass	%pred4, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred4
	  pass	%pred3, @p2
	  pass	%pred5, @p3
	  landp	~@p2, @p3, @p5
	  pass	@p5, %pred3
	}
	{
	  ct	%ctpr2 ? %pred0
	  merges,0,sm	0x1, %r16, %r24, %pred13 ? %pred4
	  pass	%pred3, @p0
	  pass	%pred1, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred3
	}
	{
	  ct	%ctpr1 ? %pred6
	  insfd,0,sm	%g16, _f32s,_lts0 0x8800, %r24, %r4
	}
	{
	  ct	%ctpr1 ? %pred4
	}
	nop
.L5930:
	{
	  disp	%ctpr1, .L3930
	  cmplsb,0,sm	0x0, %r16, %pred0
	  addd,1	%r6, [ _f64,_lts2 A ], %r3
	  addd,2	0x0, _f64,_lts0 0x20ff2000000000, %g16
	  addd,3	0x1f, 0x9, %r4
	  addd,4	0x0, [ _f64,_lts2 A ], %r5
	}
	{
	  merges,0,sm	0x1, %r16, %g17, %pred0
	}
	{
	  setwd	wsz = 0x17, nfx = 0x1, dbl = 0x1
	  setbn	rsz = 0x8, rbs = 0xe, rcur = 0x0
	  insfd,0	%g16, _f32s,_lts1 0x8800, %g17, %g16
	}
	{
	  rwd,0	%g16, %lsr
	  addd,1,sm	0x0, 0x0, %b[14]
	  addd,2,sm	0x0, 0x0, %b[7]
	  addd,3,sm	0x0, %r13, %b[6]
	}
	{
	  ldd,0,sm	%r3, %b[7], %b[13], mas=0x4
	  addd,1,sm	%b[7], %r4, %b[5]
	  addd,2,sm	0x8, %b[14], %b[12]
	}
	{
	  rwd,0	%g17, %lsr1
	  addd,1,sm	%b[5], %r4, %b[3]
	  ldd,3,sm	%r2, %b[14], %b[17], mas=0x4
	}
	{
	  nop 3
	  ldd,0,sm	%r3, %b[5], %b[11], mas=0x4
	}
	{
	  fmuld,0,sm	%b[17], %b[13], %b[9]
	}
.L3930:
	{
	  loop_mode
	  rbranch	.L9546
	  ldd,2	%r3, %b[7], %b[13], mas=0x3 ? %pcnt0
	  ldd,3,sm	%r2, %b[12], %b[15], mas=0x4 ? %pcnt1
	  addd,4,sm	0x8, %b[12], %b[10]
	  ldd,5	%r2, %b[14], %b[17], mas=0x3 ? %pcnt0
	}
.L9552:
	{
	  loop_mode
	}
	{
	  loop_mode
	  nop 2
	  fsubd,5,sm	%b[6], %b[9], %b[4]
	}
	{
	  loop_mode
	  fmuld,5,sm	%b[15], %b[11], %b[7]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  ldd,3,sm	%r3, %b[3], %b[9], mas=0x4
	  addd,4,sm	%b[3], %r4, %b[1]
	  std,5	%r0, %r5, %b[4]
	}

	{
	  setwd	wsz = 0xe, nfx = 0x1, dbl = 0x1
	  disp	%ctpr1, .L3898
	}
	{
	  disp	%ctpr3, .L3775
	  cmplsb,0,sm	%r21, _f16s,_lts0lo 0xc8, %pred0
	  adds,1	%r7, 0x1, %r7
	  addd,2	0x0, 0x0, %g16
	  sxt,3,sm	0x2, _f16s,_lts0lo 0xc8, %r3
	  sxt,4,sm	0x2, %r21, %r0
	  addd,5,sm	0x8, %r6, %r6
	}
	{
	  nop 2
	  mmurw,2	%g16, %dam_inv
	}
	{
	  ct	%ctpr1
	}
.L5957:
	{
	  ldisp	%ctpr2, .L7283
	  rwd,0	%r4, %lsr
	  addd,1	%r15, _f16s,_lts0lo 0x78, %g16
	  aaurwd,2	%r23, %aaincr1
	  addd,3	0x0, [ _f64,_lts1 A ], %r3
	  addd,4	%r2, _f16s,_lts0hi 0x18, %g17
	  aaurw,5	%r22, %aad0
	}
	{
	  disp	%ctpr1, .L5757
	  rwd,0	%r24, %lsr1
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xe, rcur = 0x0
	  disp	%ctpr1, .L5757
	  ldd,0,sm	%r15, 0x0, %g16
	  ldd,2,sm	%r2, 0x0, %g17
	  ldd,3,sm	%r15, _f16s,_lts1lo 0x28, %g18
	  ldd,5,sm	%r2, 0x8, %g19
	}
	{
	  nop 1
	  disp	%ctpr3, .L3775
	  ldd,0,sm	%r15, _f16s,_lts0lo 0x50, %b[3]
	  ldd,2,sm	%r2, _f16s,_lts0hi 0x10, %b[7]
	}
	{
	  nop 1
	  bap
	}
	{
	  nop 2
	  fmuld,0,sm	%g19, %g18, %b[11]
	}
	{
	  nop 3
	  fmuld,0,sm	%g17, %g16, %g16
	}
	{
	  nop 6
	  fsubd,0,sm	%r13, %g16, %b[6]
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L7283:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L5757:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[5]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmuld,1,sm	%b[7], %b[3], %b[9]
	  fsubd,2,sm	%b[6], %b[11], %b[4]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  std,5	%r0, %r3, %b[6]
	}

	{
	  setwd	wsz = 0xe, nfx = 0x1, dbl = 0x1
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  cmplsb,0,sm	%r21, _f16s,_lts0lo 0xc8, %pred0
	  adds,1	%r7, 0x1, %r7
	  aaurw,2	%g16, %aabf0
	  sxt,3,sm	0x2, _f16s,_lts0lo 0xc8, %r3
	  sxt,4,sm	0x2, %r21, %r0
	  addd,5,sm	0x8, %r6, %r6
	}
.L3898:
	{
	  cmplsb,0	%r7, 0x5, %pred3
	  shld,3,sm	%r3, 0x5, %g16
	  shld,4,sm	%r3, 0x3, %g17
	  shld,5,sm	%r0, 0x3, %g18
	}
	{
	  shld,0,sm	%r0, 0x5, %g19
	  addd,1,sm	%r2, %r6, %r11
	  addd,2,sm	%r14, %r6, %r12
	  addd,3,sm	%r14, %g18, %g20
	  addd,4,sm	%r2, %g18, %g21
	  addd,5,sm	%r6, [ _f64,_lts0 A +8 ], %r13
	  pass	%pred3, @p0
	  pass	%pred0, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred4
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred5
	  landp	@p0, ~@p1, @p6
	  pass	@p6, %pred6
	}
	{
	  addd,0,sm	%g16, %g17, %r4
	  addd,1,sm	%g16, %g18, %r5
	  addd,2,sm	%r2, %g17, %r3
	  addd,3,sm	%r14, %g17, %r0
	  pass	%pred3, @p0
	  pass	%pred0, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred7
	}
	{
	  cmpledb,0,sm	%g20, %r11, %pred2 ? %pred5
	  cmpledb,1,sm	%r12, %g21, %pred1 ? %pred4
	  addd,2,sm	%g19, %g17, %r10
	  addd,3,sm	%g19, %g18, %r9
	}
	{
	  ct	%ctpr3 ? %pred3
	  addd,0,sm	%r13, %r4, %r26 ? %pred7
	  addd,1,sm	%r13, %r5, %r25 ? %pred6
	}

	{
	  disp	%ctpr1, .L3747
	  adds,0	%r16, 0x1, %r16
	  addd,1,sm	%r8, _f16s,_lts0lo 0x28, %r8
	}
	{
	  nop 2
	  cmplesb,0	%r16, 0x4, %pred0
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 A +96 ], %g16
	}
	{
	  nop 5
	  fdtoistr,0	%g16, %g16
	}
	{
	  ct	%ctpr3
	  sxt,3	0x2, %g16, %r0
	}
.L9546:
	{
	  nop 3
	  fmuld,0,sm	%b[17], %b[13], %b[9]
	}
	{
	  ibranch	.L9552
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0xc8
	.align	16
A:
	.skip	0xc8
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
