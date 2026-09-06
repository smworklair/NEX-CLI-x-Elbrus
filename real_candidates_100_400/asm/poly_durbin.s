	.file	"poly_durbin.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xe, nfx = 0x0, dbl = 0x1
	  getsp,0	_f32s,_lts1 0xffffffa0, %r2
	  adds,1,sm	0x1, 0x0, %r5
	  ldd,2	0x0, [ _f64,_lts2 r ], %g16
	  addd,3	0x2, 0x0, %r20
	  adds,4	0x0, 0x0, %r8
	  addd,5	0x8, 0x0, %r3
	}
	{
	  addd,0	0x0, _f64,_lts2 0xff2000000000, %g18
	  cmplsb,1,sm	0x0, %r5, %pred0
	  addd,3	0x0, 0x0, %r13
	  addd,4	0x0, _f64,_lts0 0x3ff0000000000000, %g17
	  addd,5	0x1, 0x0, %r4
	}
	{
	  addd,0	%r2, _f64,_lts0 0x60, %r1
	  merges,1,sm	0x1, %r5, %r6, %pred0
	  ldb,2,sm	0x8, [ _f64,_lts2 y +-16 ], %empty, mas=0x20
	  subd,3	0x0, 0x1, %r18
	  subd,4	0x0, 0x2, %r17
	  addd,5	0x0, %g17, %r7
	}
	{
	  insfd,0	%g18, _f32s,_lts0 0x8800, %r6, %r9
	  addd,1	0x0, %g17, %r16
	  ldb,2,sm	0x8, [ _f64,_lts1 r +-8 ], %empty, mas=0x20
	}
	{
	  addd,0	0x0, [ _f64,_lts0 y ], %r23
	}
	{
	  addd,0,sm	%r1, _f16s,_lts0lo 0xffa0, %r22
	  xord,1	%g16, _f64,_lts1 0x8000000000000000, %r0
	  addd,2,sm	%r1, _f16s,_lts0lo 0xffa0, %r21
	  addd,3	%r1, _f16s,_lts0lo 0xffa0, %r15
	}
	{
	  addd,0,sm	0x0, %r22, %r19
	  std,2	0x0, [ _f64,_lts0 y ], %r0
	}
.L266:
	{
	  ldisp	%ctpr2, .L1157
	  rwd,0	%r9, %lsr
	  addd,1	0x0, [ _f64,_lts0 y +16 ], %g16
	  aaurwd,2	%r18, %aaincr1
	  fmuld,3	%r0, %r0, %g18
	  addd,4	%r3, [ _f64,_lts2 r +-24 ], %g17
	  aaurw,5	%r8, %aad0
	}
	{
	  disp	%ctpr1, .L427
	  rwd,0	%r6, %lsr1
	  addd,1,sm	0x8, %r3, %g16
	  aaurwd,2	%g16, %aaind1
	  addd,3	0x0, 0x0, %r0
	  addd,4,sm	%r3, [ _f64,_lts0 r +-8 ], %g17
	  aaurwd,5	%g17, %aaind2
	}
	{
	  disp	%ctpr1, .L427
	}
	{
	  ldd,0,sm	%r3, [ _f64,_lts0 r +-8 ], %g19
	  ldd,2,sm	0x0, [ _f64,_lts2 y ], %g20
	  ldb,3,sm	%g16, [ _f64,_lts0 r +-8 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%g16, [ _f64,_lts0 y +-16 ], %empty, mas=0x20
	  fsubd,4	%r16, %g18, %g18
	}
	{
	  nop 2
	  bap
	}
	{
	  fmuld,3	%g18, %r7, %r7
	}
	{
	  setwd	wsz = 0x12, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x3, rbs = 0xe, rcur = 0x0
	}
	{
	  nop 7
	  ldd,0,sm	%g17, _f16s,_lts0lo 0xfff8, %b[3]
	  fmuld,1,sm	%g19, %g20, %b[6]
	  ldd,2,sm	0x0, [ _f64,_lts1 y +8 ], %b[2]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L1157:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=1, asz=5, abs=0, disp=0
	}
.L427:
	{
	  loop_mode
	  nop 1
	}
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[1]
	  movad,3	area=0, ind=0, am=1, be=0, %b[0]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[3], %b[2], %b[4]
	  faddd,2,sm	%r0, %b[6], %r0
	}

	{
	  setwd	wsz = 0xe, nfx = 0x0, dbl = 0x1
	  ldd,3	%r3, [ _f64,_lts1 r ], %g16
	}
	{
	  cmplsb,0,sm	0x0, %r5, %pred0
	  cmplsb,1,sm	0x0, %r5, %pred1
	  addd,2	0x0, 0x0, %g17
	  adds,4	0x0, 0x0, %g18
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r5, %r14, %pred0
	  subd,1,sm	%r4, %g17, %g19
	  aaurw,2	%g18, %aabf0
	  merges,3,sm	0x1, %r5, %r9, %pred1
	}
	{
	  shrs,0	%r14, 0x1, %r12
	  shld,1,sm	%g17, 0x3, %r10
	  shld,2,sm	%g19, 0x3, %r2
	}
	{
	  cmpesb,0	%r12, 0x0, %pred0
	  shls,1,sm	%r12, 0x1, %r11
	}
	{
	  nop 3
	  faddd,3	%g16, %r0, %g16
	}
	{
	  pxord,3	%g16, _f64,_lts0 0x8000000000000000, %g16
	}
	{
	  nop 7
	  fdivd,5	%g16, %r7, %r0
	}
	{
	  ibranch	.L636 ? %pred0
	}
	{
	  nop 5
	}

	{
	  ldisp	%ctpr2, .L1131
	  cmplsb,0	0x0, %r12, %pred0
	  addd,1	0x0, _f64,_lts0 0x40ef2000000000, %g16
	  aaurwd,2	%r21, %aad1
	  addd,3	%r3, [ _f64,_lts2 y +-256 ], %g17
	  aaurwd,5	%r13, %aasti3
	}
	{
	  disp	%ctpr1, .L405
	  merges,0	0x1, %r12, %g18, %pred0
	  addd,1	0x0, [ _f64,_lts0 y +240 ], %g19
	  aaurwd,2	%r20, %aaincr3
	  addd,3,sm	%r3, [ _f64,_lts2 y +-16 ], %g20
	  aaurwd,5	%r20, %aaincr2
	}
	{
	  disp	%ctpr1, .L405
	  insfd,1	%g16, _f32s,_lts0 0x8800, %g18, %g16
	  aaurwd,2	%r17, %aaincr1
	  aaurwd,5	%g17, %aaind1
	}
	{
	  rwd,0	%g16, %lsr
	  andd,1	%g16, _f64,_lts0 0xffffffff, %g16
	  aaurw,2	%r8, %aad0
	  aaurwd,5	%g19, %aaind2
	}
	{
	  rwd,0	%g18, %lsr1
	  shld,1	%g16, 0x1, %r10
	  ldd,2,sm	%r3, [ _f64,_lts0 y +-16 ], %g17
	  ldd,3,sm	0x0, [ _f64,_lts2 y +8 ], %g18
	}
	{
	  setwd	wsz = 0x25, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x16, rbs = 0xe, rcur = 0x0
	  ldd,0,sm	%r3, [ _f64,_lts1 y +-8 ], %g16
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y ], %g19
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-32 ], %g21
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +24 ], %g22
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-24 ], %g23
	}
	{
	  bap
	  ldd,0,sm	0x0, [ _f64,_lts0 y +16 ], %g24
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-48 ], %g25
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +40 ], %g26
	  fmul_addd,1,sm	%r0, %g17, %g18, %b[20]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-40 ], %g27
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +32 ], %g17
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-64 ], %g18
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +56 ], %g28
	  fmul_addd,1,sm	%r0, %g16, %g19, %b[21]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-56 ], %g29
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +48 ], %g16
	  fmul_addd,1,sm	%r0, %g21, %g22, %b[18]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-80 ], %g19
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +72 ], %g21
	  fmul_addd,1,sm	%r0, %g23, %g24, %b[19]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-72 ], %g22
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +64 ], %g23
	  fmul_addd,1,sm	%r0, %g25, %g26, %b[16]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-96 ], %g24
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +88 ], %g25
	  fmul_addd,1,sm	%r0, %g27, %g17, %b[17]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-88 ], %g26
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +80 ], %g17
	  fmul_addd,1,sm	%r0, %g18, %g28, %b[14]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-112 ], %g27
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +104 ], %g18
	  fmul_addd,1,sm	%r0, %g29, %g16, %b[15]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-104 ], %g28
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +96 ], %g16
	  fmul_addd,1,sm	%r0, %g19, %g21, %b[12]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-128 ], %g29
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +120 ], %g19
	  fmul_addd,1,sm	%r0, %g22, %g23, %b[13]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-120 ], %g21
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +112 ], %g22
	  fmul_addd,1,sm	%r0, %g24, %g25, %b[10]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-144 ], %g23
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +136 ], %g24
	  fmul_addd,1,sm	%r0, %g26, %g17, %b[11]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-136 ], %g25
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +128 ], %g17
	  fmul_addd,1,sm	%r0, %g27, %g18, %b[8]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-160 ], %g26
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +152 ], %g18
	  fmul_addd,1,sm	%r0, %g28, %g16, %b[9]
	  ldd,2,sm	%r3, [ _f64,_lts2 y +-152 ], %g27
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts2 y +144 ], %g16
	  fmul_addd,1,sm	%r0, %g29, %g19, %b[6]
	  ldd,2,sm	%g20, _f16s,_lts0lo 0xff60, %b[32]
	  ldd,3,sm	%g20, _f16s,_lts0hi 0xff68, %b[45]
	  ldd,5,sm	%g20, _f16s,_lts1lo 0xff50, %b[30]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +168 ], %b[33]
	  fmul_addd,1,sm	%r0, %g21, %g22, %b[7]
	  ldd,2,sm	0x0, [ _f64,_lts2 y +160 ], %b[44]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts2 y +184 ], %b[31]
	  fmul_addd,1,sm	%r0, %g23, %g24, %b[4]
	  ldd,2,sm	%g20, _f16s,_lts0lo 0xff58, %b[43]
	  ldd,3,sm	%g20, _f16s,_lts0hi 0xff40, %b[28]
	  ldd,5,sm	%g20, _f16s,_lts1lo 0xff48, %b[41]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +176 ], %b[42]
	  fmul_addd,1,sm	%r0, %g25, %g17, %b[5]
	  ldd,2,sm	0x0, [ _f64,_lts2 y +200 ], %b[29]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts2 y +192 ], %b[40]
	  fmul_addd,1,sm	%r0, %g26, %g18, %b[2]
	  ldd,2,sm	%g20, _f16s,_lts0lo 0xff30, %b[26]
	  ldd,3,sm	%g20, _f16s,_lts0hi 0xff38, %b[39]
	  ldd,5,sm	%g20, _f16s,_lts1lo 0xff20, %b[24]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 y +216 ], %b[27]
	  fmul_addd,1,sm	%r0, %g27, %g16, %b[3]
	  ldd,2,sm	0x0, [ _f64,_lts2 y +208 ], %b[38]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 y +232 ], %b[25]
	  ldd,2,sm	%g20, _f16s,_lts0lo 0xff28, %b[37]
	}
	{
	  ct	%ctpr1
	  ldd,0,sm	0x0, [ _f64,_lts0 y +224 ], %b[36]
	}
.L1131:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=16, d=0, incr=2, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=16, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L405:
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmul_addd,0,sm	%r0, %b[45], %b[44], %b[1]
	  fmul_addd,1,sm	%r0, %b[32], %b[33], %b[0]
	  staad,2	%b[21], %aad1[ %aasti3 ]
	  staad,5	%b[20], %aad1[ %aasti3 + _f32s,_lts0 0x8 ]
	  incr,5	%aaincr3
	  movad,0	area=0, ind=0, am=0, be=0, %b[34]
	  movad,1	area=0, ind=8, am=1, be=0, %b[23]
	  movad,2	area=0, ind=8, am=0, be=0, %b[35]
	  movad,3	area=0, ind=0, am=1, be=0, %b[22]
	}

	{
	  setwd	wsz = 0xe, nfx = 0x0, dbl = 0x1
	  cmplsb,0,sm	0x0, %r5, %pred0
	  subd,1,sm	%r4, %r10, %g17
	  adds,2	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r5, %r9, %pred0
	  shld,1,sm	%g17, 0x3, %r2
	  aaurw,2	%g16, %aabf0
	  shls,3	%r12, 0x1, %r11
	  shld,4,sm	%r10, 0x3, %r10
	}
.L636:
	{
	  disp	%ctpr2, .L713
	  ldd,0,sm	%r2, [ _f64,_lts1 y +-8 ], %g17
	  shrs,1,sm	%r9, 0x1, %g16
	  shrs,2,sm	%r9, 0x1, %g18
	  addd,3,sm	%r22, _f16s,_lts0lo 0x40, %r11
	  cmpesb,4	%r11, %r14, %pred1
	}
	{
	  cmpesb,0,sm	%g16, 0x0, %pred2
	  addd,1	0x0, 0x0, %r26 ? %pred1
	  adds,2	0x0, %g18, %r24 ? ~%pred1
	  ldd,3,sm	%r10, [ _f64,_lts0 y ], %g19
	  adds,4,sm	0x0, %r9, %r25 ? %pred1
	  addd,5	0x0, 0x0, %r26 ? ~%pred1
	}
	{
	  cmpesb,0,sm	%g18, 0x0, %pred4
	  adds,1,sm	0x0, %r9, %r25 ? ~%pred1
	  adds,2	0x0, %g16, %r24 ? %pred1
	  adds,4	0x0, %g18, %r12 ? ~%pred1
	  adds,5	0x0, %g16, %r12 ? %pred1
	  pass	%pred1, @p0
	  pass	%pred2, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred3
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred2
	}
	{
	  nop 1
	  cmplsb,0,sm	0x0, %r24, %pred0
	  shld,1,sm	%r26, 0x3, %r2
	  pass	%pred1, @p0
	  pass	%pred4, @p1
	  landp	~@p0, @p1, @p4
	  pass	@p4, %pred4
	}
	{
	  ibranch	.L588 ? %pred2
	  fmuld,0,sm	%r0, %g17, %g16
	}
	{
	  ct	%ctpr2 ? %pred3
	}
	{
	  nop 1
	}
	{
	  nop 3
	  faddd,0,sm	%g19, %g16, %g16
	}
	{
	  ibranch	.L588 ? %pred4
	  std,2	%r15, %r10, %g16 ? ~%pred1
	}
.L713:
	{
	  ldisp	%ctpr2, .L1120
	  addd,0	0x0, _f64,_lts0 0x40fa2000000000, %g16
	  merges,1	0x1, %r24, %g17, %pred0
	  aaurwd,2	%r23, %aad1
	  aaurwd,5	%r13, %aasti2
	}
	{
	  disp	%ctpr1, .L388
	  insfd,0	%g16, _f32s,_lts0 0x8800, %g17, %g16
	  aaurw,2	%r8, %aad0
	  aaurwd,5	%r11, %aaind1
	}
	{
	  disp	%ctpr1, .L388
	  rwd,0	%g16, %lsr
	  andd,1	%g16, _f64,_lts0 0xffffffff, %g16
	}
	{
	  rwd,0	%g17, %lsr1
	  shld,1	%g16, 0x1, %g16
	}
	{
	  addd,1	%r26, %g16, %r2
	}
	{
	  setwd	wsz = 0x13, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x4, rbs = 0xe, rcur = 0x0
	}
	{
	  ldqp,0,sm	%r19, 0x0, %b[8]
	  ldqp,2,sm	%r19, _f16s,_lts0lo 0x10, %b[6]
	  ldqp,3,sm	%r19, _f16s,_lts0hi 0x20, %b[4]
	  ldqp,5,sm	%r19, _f16s,_lts1lo 0x30, %b[2]
	}
	{
	  nop 7
	  bap
	}
	{
	  nop 7
	}
	{
	  ct	%ctpr1
	}
.L1120:
	{
	  fapb	ct=1, dcd=0, fmt=5, mrng=16, d=0, incr=0, ind=1, asz=5, abs=0, disp=0
	}
.L388:
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staaqp,5	%b[8], %aad1[ %aasti2 ]
	  incr,5	%aaincr0
	  movaqp,1	area=0, ind=0, am=1, be=0, %b[0]
	}

	{
	  setwd	wsz = 0xe, nfx = 0x0, dbl = 0x1
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  shld,0,sm	%r2, 0x3, %r2
	  aaurw,2	%g16, %aabf0
	}
.L588:
	{
	  disp	%ctpr1, .L266
	  ldd,0,sm	%r15, %r2, %g16
	  adds,1	%r5, 0x1, %r5
	  shls,2	%r12, 0x1, %g17
	  addd,3,sm	0x0, _f64,_lts0 0xff2000000000, %g18
	  addd,4	%r4, 0x1, %r4
	}
	{
	  disp	%ctpr3, .L189
	  cmplsb,0	%r5, 0xc, %pred0
	  cmplsb,1,sm	0x0, %r5, %pred1
	}
	{
	  cmpesb,0	%g17, %r25, %pred2
	  merges,1,sm	0x1, %r5, %r6, %pred1
	}
	{
	  nop 1
	  insfd,0,sm	%g18, _f32s,_lts0 0x8800, %r6, %r9
	}
	{
	  ct	%ctpr1 ? %pred0
	  std,2	%r2, [ _f64,_lts0 y ], %g16 ? ~%pred2
	  addd,3,sm	0x8, %r3, %r3
	  std,5	%r3, [ _f64,_lts0 y ], %r0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L189:
	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 r +16 ], %g16
	}
	{
	  nop 5
	  fdtoistr,0	%g16, %g16
	}
	{
	  ct	%ctpr3
	  sxt,3	0x2, %g16, %r0
	}
	.size	main, .- main
	.section .bss
	.global	r
	.type	r, #object
	.size	r, 0x60
	.align	16
r:
	.skip	0x60
	.global	y
	.type	y, #object
	.size	y, 0x60
	.align	16
y:
	.skip	0x60
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
