	.file	"poly_trmm.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x12, nfx = 0x0, dbl = 0x1
	  adds,1,sm	0x0, 0x0, %r29
	  addd,2	0x0, _f64,_lts2 0x3ff8000000000000, %r26
	  addd,3	0xc, 0x0, %r25
	  adds,4	0x0, 0x0, %r24
	  addd,5,sm	0x0, 0x0, %r16
	}
	{
	  nop 1
	  addd,0	0x0, 0x0, %r28
	}
.L14:
	{
	  adds,0	%r29, 0x1, %r17
	  subs,1,sm	0xb, %r29, %r13
	  addd,2	0x0, 0x0, %r5
	  sxt,3,sm	0x2, 0x1, %g16
	  addd,4	%r16, [ _f64,_lts0 B ], %r15
	  addd,5,sm	%r16, [ _f64,_lts2 B +8 ], %r23
	}
	{
	  cmplsb,0,sm	%r17, 0xc, %pred0
	  sxt,1	0x2, %r17, %r30
	  sxt,2,sm	0x2, %r13, %g17
	  shld,3,sm	%g16, 0x5, %g16
	  shld,4,sm	%g16, 0x6, %g18
	  adds,5,sm	0x0, 0x0, %r14
	}
	{
	  subs,0,sm	%r13, 0x1, %g19 ? %pred0
	  subs,1,sm	0x1, 0x1, %g19 ? ~%pred0
	  shld,2,sm	%r30, 0x6, %g20
	  addd,3,sm	%g18, %g16, %r6
	  addd,4,sm	%r5, [ _f64,_lts0 B ], %g21
	  ldb,5,sm	%r15, 0x0, %empty, mas=0x20
	}
	{
	  cmplsb,0	%g19, _f16s,_lts0lo 0xc8, %pred1
	  shld,1,sm	%r30, 0x5, %g22
	  shld,2,sm	%g17, 0x6, %g23
	  shld,3,sm	%g17, 0x5, %g17
	  addd,4,sm	%r15, %r5, %r11
	}
	{
	  addd,0,sm	%g20, %g22, %r22
	  merges,1	%g19, _f16s,_lts0lo 0xc8, %g19, ~%pred1
	  addd,2,sm	%g23, %g16, %g16
	  addd,3,sm	%g18, %g17, %g18
	  addd,4,sm	%r23, %r5, %r7
	}
	{
	  addd,0	%r22, _f16s,_lts0lo 0xffa8, %r19
	  addd,1	%r22, _f16s,_lts0hi 0xffa0, %r18
	  sxt,2	0x2, %g19, %g19
	  addd,3,sm	%g23, %g17, %g17
	}
	{
	  addd,0,sm	%r22, %r28, %g20
	  addd,1,sm	%r22, [ _f64,_lts0 B ], %r12
	  addd,2	0x8, %r22, %r21
	  addd,3,sm	%r22, [ _f64,_lts2 B +8 ], %r20
	  addd,4,sm	%r22, %g21, %r4
	}
	{
	  shld,0	%g19, 0x6, %g23
	  addd,1,sm	%r19, %g21, %g22
	  shld,2	%g19, 0x5, %g19
	  addd,3,sm	%r20, %r5, %r0
	  addd,4,sm	%r18, %g21, %r10
	}
	{
	  ldb,0,sm	%r12, 0x0, %empty, mas=0x20
	  addd,1,sm	%g20, [ _f64,_lts0 A ], %r27
	  addd,2,sm	%r21, %g21, %r9
	  addd,3,sm	%r10, %g16, %r34 ? ~%pred0
	  addd,4,sm	%r10, %g17, %r34 ? %pred0
	  addd,5,sm	%r12, %r5, %r3
	}
	{
	  addd,1,sm	%g22, %g16, %r33 ? ~%pred0
	  addd,2,sm	%g22, %g18, %r32 ? %pred0
	  addd,3,sm	%g22, %r6, %r32 ? ~%pred0
	  addd,4,sm	%r10, %g18, %r31 ? %pred0
	  addd,5,sm	%g22, %g17, %r33 ? %pred0
	}
	{
	  addd,0	%g23, %g19, %r2
	}
.L493:
	{
	  disp	%ctpr2, .L1083
	  addd,0,sm	%r9, %r2, %g16
	  cmpledb,1,sm	%r0, %r11, %pred1
	  addd,2,sm	%r10, %r6, %r31 ? ~%pred0
	  cmpledb,3,sm	%r7, %r34, %pred2 ? %pred0
	  addd,4,sm	0x8, %r5, %g17
	  addd,5	%r16, %r5, %r0
	}
	{
	  disp	%ctpr1, .L1057
	  cmpledb,0,sm	%r32, %r11, %pred3 ? ~%pred0
	  cmpledb,1,sm	%r33, %r11, %pred3 ? %pred0
	  addd,2,sm	%r4, %r2, %g18
	  ldd,3	%r15, %r5, %r6
	  addd,4,sm	%r16, %g17, %g19
	  ldb,5,sm	%r12, %g17, %empty, mas=0x20
	}
	{
	  cmpledb,0,sm	%r7, %g18, %pred5
	  cmpledb,1,sm	%g16, %r11, %pred4
	  cmpledb,3,sm	%r7, %r3, %pred6
	  cmpledb,4,sm	%r7, %r31, %pred2 ? ~%pred0
	  ldb,5,sm	%g19, [ _f64,_lts0 B ], %empty, mas=0x20
	}
	{
	  pass	%pred3, @p0
	  pass	%pred4, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred3
	  pass	%pred1, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred1
	}
	{
	  pass	%pred2, @p0
	  pass	%pred5, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred3
	  pass	%pred6, @p2
	  landp	@p4, ~@p2, @p5
	  pass	@p5, %pred4
	  pass	%pred1, @p3
	  landp	~@p3, ~@p0, @p6
	  pass	@p6, %pred6
	}
	{
	  pass	%pred1, @p0
	  pass	%pred4, @p1
	  landp	~@p0, @p1, @p4
	  pass	@p4, %pred3
	  pass	%pred2, @p2
	  landp	~@p0, @p2, @p5
	  pass	@p5, %pred2
	  pass	%pred5, @p3
	  landp	@p5, ~@p3, @p6
	  pass	@p6, %pred4
	}
	{
	  ct	%ctpr2 ? %pred1
	}
	{
	  ct	%ctpr1 ? %pred6
	}
	{
	  ct	%ctpr1 ? %pred3
	}
	{
	  ct	%ctpr1 ? %pred4
	}
.L1083:
	{
	  ldisp	%ctpr2, .L1382
	  addd,0	0x0, _f64,_lts1 0x20c42000000000, %g16
	  merges,1,sm	%r13, %r13, %g17, %pred0 ? %pred0
	  merges,2,sm	0x1, 0x1, %g17, ~%pred0 ? ~%pred0
	  addd,3	%r27, _f16s,_lts0lo 0x120, %g19
	  addd,4	%r3, _f16s,_lts0lo 0x120, %g18
	  aaurwd,5	%r25, %aaincr1
	}
	{
	  disp	%ctpr1, .L904
	  addd,0	0x0, [ _f64,_lts1 B ], %r2
	  insfd,1	%g16, _f32s,_lts0 0x8800, %g17, %g16
	  aaurw,2	%r24, %aad0
	  aaurwd,5	%g18, %aaind1
	}
	{
	  disp	%ctpr1, .L904
	  rwd,0	%g16, %lsr
	  aaurwd,2	%g19, %aaind2
	  ldd,5,sm	%r3, 0x0, %g16
	}
	{
	  setwd	wsz = 0x18, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0x12, rcur = 0x0
	  rwd,0	%g17, %lsr1
	  ldd,2,sm	%r27, 0x0, %g17
	  ldd,3,sm	%r3, _f16s,_lts1lo 0x60, %g18
	  ldd,5,sm	%r27, _f16s,_lts1lo 0x60, %g19
	}
	{
	  nop 2
	  ldd,0,sm	%r3, _f16s,_lts0lo 0xc0, %b[7]
	  ldd,2,sm	%r27, _f16s,_lts0lo 0xc0, %b[3]
	}
	{
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
	  nop 7
	  faddd,0,sm	%r6, %g16, %b[6]
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L1382:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L904:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[1]
	  movad,3	area=0, ind=0, am=1, be=0, %b[5]
	}
	{
	  loop_mode
	  nop 1
	  fmuld,1,sm	%b[3], %b[7], %b[9]
	  faddd,2,sm	%b[6], %b[11], %b[4]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  std,5	%r0, %r2, %b[6]
	}

	{
	  setwd	wsz = 0x12, nfx = 0x0, dbl = 0x1
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	}
.L499:
	{
	  disp	%ctpr1, .L493
	  cmplsb,0,sm	%r17, 0xc, %pred0
	  addd,1,sm	0x8, %r5, %r5
	  ldd,2	%r0, [ _f64,_lts0 B ], %g16
	  sxt,3,sm	0x2, 0x1, %g17
	  sxt,4,sm	0x2, %r13, %g18
	  adds,5	%r14, 0x1, %r14
	}
	{
	  disp	%ctpr2, .L134
	  addd,0,sm	%r5, [ _f64,_lts0 B ], %g20
	  addd,1,sm	%r15, %r5, %r11
	  cmplsb,3	%r14, 0xc, %pred1
	  shld,4,sm	%g17, 0x6, %g19
	  shld,5,sm	%g17, 0x5, %g17
	}
	{
	  shld,0,sm	%g18, 0x6, %g21
	  shld,1,sm	%g18, 0x5, %g18
	  addd,2,sm	%r19, %g20, %g22
	  addd,3,sm	%g19, %g17, %r6
	  addd,4,sm	%r23, %r5, %r7
	  addd,5,sm	%r12, %r5, %r3
	  pass	%pred1, @p0
	  pass	%pred0, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred2
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred3
	  landp	@p0, @p1, @p6
	  pass	@p6, %pred4
	}
	{
	  subs,0,sm	%r13, 0x1, %g23 ? %pred3
	  subs,1,sm	0x1, 0x1, %g23 ? %pred2
	  addd,2,sm	%g21, %g17, %g17
	  addd,3,sm	%r18, %g20, %r10
	  addd,4,sm	%r21, %g20, %r9
	  addd,5,sm	%r22, %g20, %r4
	  pass	%pred1, @p0
	  pass	%pred0, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred2
	  landp	@p0, ~@p1, @p5
	  pass	@p5, %pred3
	  landp	@p0, @p1, @p6
	  pass	@p6, %pred5
	}
	{
	  cmplsb,0,sm	%g23, _f16s,_lts0lo 0xc8, %pred6
	  addd,1,sm	%g21, %g18, %g20
	  addd,2,sm	%g19, %g18, %g18
	  pass	%pred1, @p0
	  pass	%pred0, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred7
	  landp	@p0, ~@p1, @p5
	  pass	@p5, %pred8
	  landp	@p0, @p1, @p6
	  pass	@p6, %pred9
	}
	{
	  fmuld,0	%r26, %g16, %g16
	  merges,1,sm	%g23, _f16s,_lts0lo 0xc8, %g19, ~%pred6
	  addd,2,sm	%r10, %g17, %r34 ? %pred2
	  addd,3,sm	%g22, %g17, %r33 ? %pred3
	  addd,4,sm	%g22, %r6, %r32 ? %pred8
	}
	{
	  sxt,0,sm	0x2, %g19, %g17
	  addd,1,sm	%g22, %g18, %r32 ? %pred5
	  addd,2,sm	%r10, %g20, %r34 ? %pred9
	  addd,3,sm	%r10, %g18, %r31 ? %pred7
	  addd,4,sm	%g22, %g20, %r33 ? %pred4
	}
	{
	  shld,1,sm	%g17, 0x6, %g18
	  shld,2,sm	%g17, 0x5, %g17
	}
	{
	  addd,0,sm	%g18, %g17, %r2
	}
	{
	  ct	%ctpr1 ? %pred1
	  addd,0,sm	%r20, %r5, %r0
	  std,2	%r0, [ _f64,_lts0 B ], %g16
	}
	{
	  ct	%ctpr2 ? ~%pred1
	}
.L1057:
	{
	  ldisp	%ctpr2, .L1416
	  addd,0	0x0, _f64,_lts0 0x20fd2000000000, %g16
	  merges,1,sm	%r13, %r13, %g17, %pred0 ? %pred0
	  merges,2,sm	0x1, 0x1, %g17, ~%pred0 ? ~%pred0
	  shld,3	%r30, 0x5, %g18
	  shld,4	%r30, 0x6, %g19
	  aaurwd,5	%r25, %aaincr1
	}
	{
	  disp	%ctpr1, .L628
	  insfd,0	%g16, _f32s,_lts0 0x8800, %g17, %g16
	  addd,1	0x0, [ _f64,_lts1 B ], %r4
	  aaurw,2	%r24, %aad0
	  addd,3	%g19, %g18, %g18
	  addd,4	%r5, [ _f64,_lts1 B ], %r2
	  scld,5	0x3, 0x5, %r3
	}
	{
	  disp	%ctpr1, .L628
	  rwd,0	%g16, %lsr
	  addd,3,sm	%g18, %r28, %g16
	}
	{
	  rwd,0	%g17, %lsr1
	  addd,3	%g16, [ _f64,_lts0 A +192 ], %g17
	  addd,4,sm	%g16, [ _f64,_lts2 A ], %g16
	}
	{
	  aaurwd,5	%g17, %aaind1
	}
	{
	  setwd	wsz = 0x1a, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x7, rbs = 0x12, rcur = 0x0
	}
	{
	  ldd,0,sm	%g16, 0x0, %b[14]
	  addd,1,sm	0x0, %g18, %b[7]
	  ldd,2,sm	%g16, _f16s,_lts0lo 0x60, %b[12]
	  addd,3,sm	0x0, %r6, %b[6]
	}
	{
	  bap
	  ldd,0,sm	%r2, %b[7], %b[11], mas=0x4
	  addd,1,sm	%b[7], %r3, %b[5]
	}
	{
	  nop 3
	  ldd,0,sm	%r2, %b[5], %b[9], mas=0x4
	  addd,1,sm	%b[5], %r3, %b[3]
	}
	{
	  nop 7
	  fmuld,0,sm	%b[14], %b[11], %b[10]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L1416:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L628:
	{
	  loop_mode
	  rbranch	.L2419
	  ldd,5	%r2, %b[7], %b[11], mas=0x3 ? %pcnt0
	}
.L2425:
	{
	  loop_mode
	  nop 1
	  faddd,4,sm	%b[6], %b[10], %b[4]
	}
	{
	  loop_mode
	  fmuld,4,sm	%b[12], %b[9], %b[8]
	}
	{
	  loop_mode
	  ldd,3,sm	%r2, %b[3], %b[7], mas=0x4
	  addd,5,sm	%b[3], %r3, %b[1]
	  movad,1	area=0, ind=0, am=1, be=0, %b[10]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  std,5	%r0, %r4, %b[4]
	}

	{
	  setwd	wsz = 0x12, nfx = 0x0, dbl = 0x1
	  disp	%ctpr1, .L499
	}
	{
	  addd,0	0x0, 0x0, %g16
	  adds,1	0x0, 0x0, %g17
	}
	{
	  mmurw,2	%g16, %dam_inv
	}
	{
	  nop 1
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g17, %aabf0
	}
	{
	  ct	%ctpr1
	}
.L134:
	{
	  nop 4
	  disp	%ctpr1, .L14
	  cmplesb,0	%r17, 0xa, %pred0
	  adds,1	%r29, 0x1, %r29
	  addd,2,sm	0x8, %r28, %r28
	  addd,3,sm	%r16, _f16s,_lts0lo 0x60, %r16
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts2 A +208 ], %g16
	  addd,1	0x0, _f64,_lts0 0x3ff8000000000000, %g17
	}
	{
	  addd,1	0x0, %g17, %g18
	}
	{
	  ldqp,0	0x0, [ _f64,_lts0 B +1056 ], %g19
	  qppackdl,1	%g18, %g17, %g17
	  ldqp,2	0x0, [ _f64,_lts2 B +1072 ], %g20
	}
	{
	  ldqp,0	0x0, [ _f64,_lts0 B +1088 ], %g18
	  ldqp,2	0x0, [ _f64,_lts2 B +1104 ], %g21
	}
	{
	  ldqp,0	0x0, [ _f64,_lts0 B +1120 ], %g22
	  ldqp,2	0x0, [ _f64,_lts2 B +1136 ], %g23
	}
	{
	  nop 1
	  fdtoistr,0	%g16, %g16
	}
	{
	  qpfmuld,0	%g17, %g19, %g19
	  qpfmuld,1	%g17, %g20, %g20
	}
	{
	  qpfmuld,0	%g17, %g18, %g18
	  qpfmuld,1	%g17, %g21, %g21
	}
	{
	  nop 1
	  qpfmuld,0	%g17, %g22, %g22
	  qpfmuld,1	%g17, %g23, %g17
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 B +1056 ], %g19
	  sxt,3	0x2, %g16, %r0
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 B +1072 ], %g20
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 B +1088 ], %g18
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 B +1104 ], %g21
	}
	{
	  ct	%ctpr3
	  stqp,2	0x0, [ _f64,_lts0 B +1120 ], %g22
	  stqp,5	0x0, [ _f64,_lts2 B +1136 ], %g17
	}
.L2419:
	{
	  nop 4
	  fmuld,0,sm	%b[14], %b[11], %b[10]
	}
	{
	  ibranch	.L2425
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x480
	.align	16
A:
	.skip	0x480
	.global	B
	.type	B, #object
	.size	B, 0x480
	.align	16
B:
	.skip	0x480
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
