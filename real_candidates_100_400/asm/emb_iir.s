	.file	"emb_iir.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	iir1
	.type	iir1, #function
	.align	8
iir1:

	{
	  setwd	wsz = 0x5, nfx = 0x1, dbl = 0x0
	  disp	%ctpr2, .L466
	  addd,0,sm	%r3, _f32s,_lts2 0x300, %g19
	  subd,1,sm	%r3, _f16s,_lts1lo 0x10, %g18
	  ldh,2	%r1, 0x0, %g20
	  addd,3,sm	%r0, _f16s,_lts1hi 0x190, %g17
	  addd,4,sm	0x8, %r0, %g16
	  addd,5,sm	%r3, _f32s,_lts3 0x310, %g21
	}
	{
	  disp	%ctpr1, .L425
	  addd,5,sm	%r0, _f16s,_lts0lo 0x188, %g22
	}
	{
	  cmpledb,0,sm	%g16, %g18, %pred0
	  cmpledb,1,sm	%g17, %g18, %pred1
	  cmpledb,3	%g17, %g19, %pred2
	  cmpledb,4,sm	%g21, %g22, %pred3
	}
	{
	  cmpledb,0,sm	%r3, %g22, %pred5
	  cmpledb,1,sm	%r3, %r0, %pred6
	  pass	%pred2, @p0
	  pass	%pred1, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred1
	  pass	%pred0, @p2
	  landp	@p4, @p2, @p5
	  pass	@p5, %pred2
	  pass	%pred3, @p3
	  landp	~@p4, ~@p3, @p6
	  pass	@p6, %pred4
	}
	{
	  addd,0,sm	0x0, %r0, %r1
	  pass	%pred0, @p0
	  pass	%pred3, @p1
	  landp	~@p0, @p1, @p4
	  pass	@p4, %pred7
	  pass	%pred1, @p2
	  landp	@p2, ~@p4, @p5
	  pass	@p5, %pred8
	  landp	~@p0, ~@p1, @p6
	  pass	@p6, %pred0
	}
	{
	  addd,0,sm	0x0, %r3, %r7
	  sxt,1	0x1, %g20, %r8
	  addd,2,sm	0x0, %r0, %r5
	  pass	%pred1, @p0
	  pass	%pred0, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred0
	  pass	%pred8, @p2
	  pass	%pred4, @p3
	  landp	~@p2, ~@p3, @p5
	  pass	@p5, %pred1
	}
	{
	  ct	%ctpr2 ? %pred2
	  addd,0,sm	0x0, %r3, %r6
	  pass	%pred5, @p0
	  pass	%pred6, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred2
	  pass	%pred1, @p2
	  landp	@p2, @p4, @p5
	  pass	@p5, %pred3
	  landp	@p2, ~@p0, @p6
	  pass	@p6, %pred1
	}
	{
	  ct	%ctpr1 ? %pred4
	}
	{
	  ct	%ctpr1 ? %pred0
	}
	{
	  ct	%ctpr1 ? %pred3
	}
	{
	  ct	%ctpr1 ? %pred1
	}
.L466:
	{
	  ldisp	%ctpr2, .L723
	  rwd,0	_f64,_lts0 0x40c02000000032, %lsr
	  addd,1	0x0, 0x0, %g18
	  ldh,2,sm	%r0, 0x6, %g16
	  ldh,3,sm	%r0, 0x2, %g17
	  adds,4	0x0, 0x0, %g19
	  addd,5	0x2, 0x0, %g20
	}
	{
	  disp	%ctpr1, .L343
	  rwd,0	_f16s,_lts0lo 0x32, %lsr1
	  addd,1	0x4, 0x0, %g22
	  ldh,2,sm	%r0, 0x4, %g25
	  ldd,3,sm	%r3, 0x8, %g21
	  addd,4	%r1, _f16s,_lts0hi 0x30, %g23
	  addd,5	%r7, _f16s,_lts1lo 0x60, %g24
	}
	{
	  disp	%ctpr1, .L343
	  aaurwd,2	%r7, %aad1
	  aaurwd,5	%g18, %aasti3
	}
	{
	  aaurwd,2	%g20, %aaincr3
	  aaurwd,5	%g20, %aaincr2
	}
	{
	  aaurwd,2	%g22, %aaincr1
	  aaurwd,5	%g23, %aaind1
	}
	{
	  sxt,1,sm	0x1, %g16, %g16
	  aaurw,2	%g19, %aad0
	  sxt,4,sm	0x1, %g17, %g17
	  aaurwd,5	%g24, %aaind2
	}
	{
	  bap
	  ldh,0,sm	%r0, 0x8, %g19
	  muld,1,sm	%g16, %g21, %g16
	  ldh,2,sm	%r0, 0xe, %g20
	  ldh,3,sm	%r0, 0x0, %g18
	  muld,4,sm	%g17, %g21, %g17
	  ldh,5,sm	%r0, 0xc, %g21
	}
	{
	  setwd	wsz = 0x1a, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x14, rbs = 0x5, rcur = 0x0
	  ldh,0,sm	%r0, 0xa, %g22
	  ldh,2,sm	%r0, _f16s,_lts1lo 0x10, %g23
	  ldh,3,sm	%r0, _f16s,_lts1hi 0x12, %g24
	  ldh,5,sm	%r0, _f32s,_lts2 0x14, %g26
	}
	{
	  ldd,0,sm	%r3, 0x0, %b[21]
	  ldh,2,sm	%r0, _f16s,_lts0lo 0x16, %g27
	  ldd,3,sm	%r3, _f16s,_lts0hi 0x18, %g28
	  ldd,5,sm	%r3, _f16s,_lts1lo 0x28, %g29
	}
	{
	  ldh,0,sm	%r0, _f16s,_lts0lo 0x18, %g30
	  ldh,2,sm	%r0, _f16s,_lts0hi 0x1a, %g31
	  ldh,3,sm	%r0, _f16s,_lts1lo 0x1c, %r1
	  ldh,5,sm	%r0, _f16s,_lts1hi 0x1e, %r5
	}
	{
	  ldh,0,sm	%r0, _f16s,_lts0lo 0x20, %r6
	  sxt,1,sm	0x1, %g25, %g25
	  ldd,2,sm	%r3, _f16s,_lts0hi 0x10, %b[19]
	  ldd,3,sm	%r3, _f16s,_lts0lo 0x20, %b[17]
	  ldd,5,sm	%r3, _f16s,_lts1lo 0x38, %b[16]
	}
	{
	  ldd,0,sm	%r3, _f16s,_lts0lo 0x30, %b[15]
	  sxt,1,sm	0x1, %g18, %g18
	  ldh,2,sm	%r0, _f16s,_lts0hi 0x26, %b[37]
	  ldh,3,sm	%r0, _f16s,_lts1lo 0x24, %b[36]
	  ldd,5,sm	%r3, _f16s,_lts1hi 0x48, %b[14]
	}
	{
	  ldd,0,sm	%r3, _f16s,_lts0lo 0x40, %b[13]
	  ldh,2,sm	%r0, _f16s,_lts0hi 0x22, %b[8]
	  ldh,3,sm	%r0, _f16s,_lts1lo 0x28, %b[20]
	  ldh,5,sm	%r0, _f16s,_lts1hi 0x2e, %b[35]
	}
	{
	  muld,0,sm	%g25, %b[21], %g25
	  muld,1,sm	%g18, %b[21], %g18
	  ldh,2,sm	%r0, _f16s,_lts0lo 0x2c, %b[34]
	  ldd,3,sm	%r3, _f16s,_lts0hi 0x58, %b[12]
	  ldd,5,sm	%r3, _f16s,_lts1lo 0x50, %b[11]
	}
	{
	  sxt,0,sm	0x1, %r1, %b[24]
	  sxt,1,sm	0x1, %g30, %b[9]
	  ldh,2,sm	%r0, _f16s,_lts0lo 0x2a, %b[6]
	  sxt,4,sm	0x1, %r5, %b[25]
	}
	{
	  nop 1
	  sxt,3,sm	0x1, %g31, %b[38]
	  sxt,4,sm	0x1, %r6, %b[7]
	}
	{
	  sxt,0,sm	0x1, %g19, %g19
	  sxt,1,sm	0x1, %g20, %g20
	  sxt,2,sm	0x1, %g21, %g21
	  sxt,3,sm	0x1, %g22, %g22
	  sxt,4,sm	0x1, %g23, %g23
	  sxt,5,sm	0x1, %g27, %g27
	}
	{
	  muld,0,sm	%g19, %b[19], %b[4]
	  muld,1,sm	%g20, %g28, %b[31]
	  sxt,2,sm	0x1, %g26, %g26
	  muld,3,sm	%g22, %g28, %b[5]
	  muld,4,sm	%g23, %b[17], %b[2]
	  sxt,5,sm	0x1, %g24, %g24
	}
	{
	  muld,0,sm	%g21, %b[19], %b[30]
	  muld,1,sm	%g27, %g29, %b[29]
	  addd,2,sm	%g25, %g16, %g16
	  muld,3,sm	%g24, %g29, %b[3]
	  addd,5,sm	%g18, %g17, %b[39]
	}
	{
	  nop 2
	  muld,0,sm	%g26, %b[17], %b[28]
	  sard,2,sm	%g16, 0xf, %b[10]
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L723:
	{
	  fapb	ct=1, dcd=0, fmt=2, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=16, d=0, incr=2, ind=2, asz=5, abs=0, disp=0
	}
.L343:
	{
	  loop_mode
	  sard,0,sm	%b[39], 0xf, %b[41]
	  muld,1,sm	%b[38], %b[16], %b[1]
	  addd,2,sm	%r8, %b[10], %b[40]
	  sxt,3,sm	0x1, %b[37], %b[23]
	  muld,4,sm	%b[9], %b[15], %b[0]
	  sxt,5,sm	0x1, %b[36], %b[22]
	  movah,1	area=0, ind=0, am=0, be=0, %b[18]
	}
	{
	  loop_mode
	  addd,0,sm	%b[30], %b[31], %b[38]
	  muld,1,sm	%b[25], %b[16], %b[27]
	  addd,2,sm	%b[40], %b[41], %r8
	  sxt,3,sm	0x1, %b[8], %b[36]
	  muld,4,sm	%b[24], %b[15], %b[26]
	  addd,5,sm	%b[4], %b[5], %b[37]
	  movah,0	area=0, ind=6, am=0, be=0, %b[33]
	  movah,1	area=0, ind=4, am=0, be=0, %b[32]
	  movad,2	area=0, ind=8, am=1, be=0, %b[10]
	  movad,3	area=0, ind=0, am=0, be=0, %b[9]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  sard,0,sm	%b[38], 0xf, %b[8]
	  staad,2	%b[40], %aad1[ %aasti3 ]
	  sxt,3,sm	0x1, %b[20], %b[5]
	  staad,5	%b[21], %aad1[ %aasti3 + _f32s,_lts0 0x8 ]
	  incr,5	%aaincr3
	  movah,1	area=0, ind=2, am=1, be=0, %b[4]
	}

	{
	  setwd	wsz = 0x5, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  adds,0	0x0, 0x0, %g16
	}
	{
	  nop 4
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	}
.L69:
	{
	  ct	%ctpr3
	  std,5	%r2, 0x0, %r8
	}
.L425:
	{
	  ldisp	%ctpr2, .L760
	  rwd,0	_f64,_lts1 0x40f62000000032, %lsr
	  addd,1	0x0, 0x0, %g16
	  addd,2	%r7, _f16s,_lts0lo 0x80, %g19
	  adds,3	0x0, 0x0, %g17
	  addd,4	0x2, 0x0, %g18
	  aaurwd,5	%r7, %aad1
	}
	{
	  disp	%ctpr1, .L265
	  rwd,0	_f16s,_lts0lo 0x32, %lsr1
	  addd,1,sm	%r5, _f16s,_lts0hi 0x38, %g16
	  aaurwd,2	%g16, %aasti2
	  aaurwd,5	%g18, %aaincr2
	}
	{
	  disp	%ctpr1, .L265
	  aaurwd,2	%g18, %aaincr1
	  aaurw,5	%g17, %aad0
	}
	{
	  ldb,0,sm	%g16, 0x6, %empty, mas=0x20
	  aaurwd,2	%g19, %aaind1
	}
	{
	  setwd	wsz = 0x2c, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x26, rbs = 0x5, rcur = 0x0
	}
	{
	  bap
	  ldd,0,sm	%r6, 0x0, %b[34]
	  addd,1,sm	0x0, %r5, %b[18]
	  ldd,2,sm	%r6, 0x8, %b[37]
	  ldd,3,sm	%r6, _f16s,_lts0lo 0x10, %b[32]
	  ldd,5,sm	%r6, _f16s,_lts0hi 0x18, %b[35]
	}
	{
	  ldh,0,sm	%b[18], 0x6, %b[63], mas=0x4
	  addd,1,sm	%b[18], 0x8, %b[16]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x20, %b[30]
	  ldd,3,sm	%r6, _f16s,_lts0hi 0x28, %b[33]
	  ldd,5,sm	%r6, _f16s,_lts1lo 0x30, %b[28]
	}
	{
	  ldh,0,sm	%b[16], 0x6, %b[61], mas=0x4
	  addd,1,sm	%b[16], 0x8, %b[14]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x38, %b[31]
	  ldh,3,sm	%b[18], 0x4, %b[15], mas=0x4
	  ldd,5,sm	%r6, _f16s,_lts0hi 0x40, %b[26]
	}
	{
	  ldh,0,sm	%b[16], 0x4, %b[13], mas=0x4
	  addd,1,sm	%b[14], 0x8, %b[12]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x48, %b[29]
	  ldh,3,sm	%b[16], 0x2, %b[68], mas=0x4
	  ldd,5,sm	%r6, _f16s,_lts0hi 0x50, %b[24]
	}
	{
	  ldh,0,sm	%b[18], 0x2, %b[70], mas=0x4
	  addd,1,sm	%b[12], 0x8, %b[10]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x58, %b[27]
	  ldh,3,sm	%b[18], 0x0, %b[56], mas=0x4
	  ldd,5,sm	%r6, _f16s,_lts0hi 0x60, %b[22]
	}
	{
	  ldh,0,sm	%b[16], 0x0, %b[54], mas=0x4
	  addd,1,sm	%b[10], 0x8, %b[8]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x68, %b[25]
	  ldh,3,sm	%b[14], 0x4, %b[11], mas=0x4
	  ldd,5,sm	%r6, _f16s,_lts0hi 0x70, %b[20]
	}
	{
	  ldh,0,sm	%b[14], 0x6, %b[59], mas=0x4
	  addd,1,sm	%b[8], 0x8, %b[6]
	  ldd,2,sm	%r6, _f16s,_lts0lo 0x78, %b[23]
	  ldh,3,sm	%b[12], 0x4, %b[9], mas=0x4
	}
	{
	  ldh,0,sm	%b[14], 0x2, %b[66], mas=0x4
	  addd,1,sm	%b[6], 0x8, %b[4]
	  ldh,3,sm	%b[12], 0x6, %b[57], mas=0x4
	}
	{
	  ldh,0,sm	%b[14], 0x0, %b[52], mas=0x4
	  addd,1,sm	%b[4], 0x8, %b[2]
	  ldh,3,sm	%b[10], 0x4, %b[7], mas=0x4
	}
	{
	  ldh,0,sm	%b[12], 0x2, %b[64], mas=0x4
	  ldh,3,sm	%b[10], 0x6, %b[55], mas=0x4
	}
	{
	  ldh,0,sm	%b[12], 0x0, %b[50], mas=0x4
	  sxt,1,sm	0x1, %b[54], %b[42]
	  ldh,3,sm	%b[8], 0x4, %b[5], mas=0x4
	}
	{
	  ldh,0,sm	%b[10], 0x2, %b[62], mas=0x4
	  ldh,3,sm	%b[8], 0x6, %b[53], mas=0x4
	}
	{
	  ldh,0,sm	%b[10], 0x0, %b[48], mas=0x4
	  sxt,1,sm	0x1, %b[63], %g16
	  sxt,2,sm	0x1, %b[15], %g17
	  ldh,3,sm	%b[6], 0x4, %b[3], mas=0x4
	  sxt,4,sm	0x1, %b[70], %g18
	  sxt,5,sm	0x1, %b[56], %g19
	}
	{
	  muld,0,sm	%g16, %b[37], %b[69]
	  sxt,1,sm	0x1, %b[68], %g22
	  sxt,2,sm	0x1, %b[61], %g20
	  muld,3,sm	%g19, %b[34], %b[45]
	  muld,4,sm	%g18, %b[37], %b[41]
	  sxt,5,sm	0x1, %b[13], %g21
	}
	{
	  muld,0,sm	%g20, %b[35], %b[67]
	  muld,1,sm	%g17, %b[34], %b[74]
	  muld,4,sm	%g21, %b[32], %b[72]
	}
	{
	  muld,0,sm	%g22, %b[35], %b[39]
	  ldh,3,sm	%b[8], 0x2, %b[60], mas=0x4
	}
	{
	  ldh,3,sm	%b[6], 0x6, %b[51], mas=0x4
	}
	{
	  nop 1
	  ldh,0,sm	%b[8], 0x0, %b[46], mas=0x4
	}
	{
	  ct	%ctpr1
	}
.L760:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=16, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L265:
	{
	  loop_mode
	  rbranch	.L2095
	  ldh,0,sm	%b[4], 0x4, %b[1], mas=0x4 ? %pcnt7
	  muld,1,sm	%b[42], %b[32], %b[43]
	  sxt,2,sm	0x1, %b[59], %b[17]
	  sxt,3,sm	0x1, %b[11], %b[36]
	  addd,4,sm	%b[74], %b[69], %b[47]
	  ldh,5	%b[18], 0x2, %b[70], mas=0x3 ? %pcnt0
	}
.L2124:
	{
	  loop_mode
	  rbranch	.L2099
	  ldh,0,sm	%b[4], 0x6, %b[49], mas=0x4 ? %pcnt7
	  muld,1,sm	%b[17], %b[33], %b[65]
	  ldh,2	%b[18], 0x0, %b[56], mas=0x3 ? %pcnt0
	  ldh,3,sm	%b[6], 0x2, %b[58], mas=0x4 ? %pcnt6
	  sar_addd,4,sm	%b[47], 0xf, %r8, %b[71]
	  ldh,5	%b[18], 0x6, %b[63], mas=0x3 ? %pcnt0
	}
.L2121:
	{
	  loop_mode
	  rbranch	.L2107
	  sxt,0,sm	0x1, %b[66], %b[73]
	  muld,1,sm	%b[36], %b[30], %b[70]
	  ldh,2	%b[18], 0x4, %b[15], mas=0x3 ? %pcnt0
	  ldh,3,sm	%b[6], 0x0, %b[44], mas=0x4 ? %pcnt6
	  addd,4,sm	%b[45], %b[41], %b[76]
	}
.L2118:
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  sxt,0,sm	0x1, %b[52], %b[40]
	  muld,1,sm	%b[73], %b[33], %b[37]
	  staad,2	%b[34], %aad1[ %aasti2 + _f32s,_lts0 0x8 ]
	  addd,3,sm	%b[2], 0x8, %b[0]
	  sar_addd,4,sm	%b[76], 0xf, %b[71], %r8
	  staad,5	%b[71], %aad1[ %aasti2 ]
	  incr,5	%aaincr2
	  movad,0	area=0, ind=0, am=1, be=0, %b[18]
	  movad,1	area=0, ind=8, am=0, be=0, %b[21]
	}

	{
	  setwd	wsz = 0x5, nfx = 0x1, dbl = 0x0
	  disp	%ctpr1, .L69
	}
	{
	  return	%ctpr3
	  addd,0	0x0, 0x0, %g16
	  adds,1	0x0, 0x0, %g17
	}
	{
	  nop 2
	  mmurw,2	%g16, %dam_inv
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g17, %aabf0
	}
	{
	  ct	%ctpr1
	}
.L2095:
	{
	  sxt,0,sm	0x1, %b[70], %g16
	}
	{
	  nop 3
	  muld,0,sm	%g16, %b[37], %b[41]
	}
	{
	  ibranch	.L2124
	}
.L2099:
	{
	  sxt,0,sm	0x1, %b[63], %b[21]
	  sxt,1,sm	0x1, %b[56], %g16
	}
	{
	  nop 5
	  muld,0,sm	%b[21], %b[37], %b[69]
	  muld,1,sm	%g16, %b[34], %b[45]
	}
	{
	  addd,0,sm	%b[74], %b[69], %b[47]
	}
	{
	  nop 1
	  sar_addd,1,sm	%b[47], 0xf, %r8, %b[71]
	}
	{
	  ibranch	.L2121
	}
.L2107:
	{
	  sxt,0,sm	0x1, %b[15], %g16
	}
	{
	  nop 5
	  muld,0,sm	%g16, %b[34], %b[74]
	}
	{
	  addd,0,sm	%b[74], %b[69], %b[47]
	}
	{
	  nop 2
	  sar_addd,1,sm	%b[47], 0xf, %r8, %b[71]
	}
	{
	  ibranch	.L2118
	}
	.size	iir1, .- iir1
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x4, rcur = 0x0
	  disp	%ctpr1, iir1
	  getsp,0	_f32s,_lts1 0xffffffe0, %r2
	}
	{
	  addd,0	0x0, [ _f64,_lts0 OPT ], %b[2]
	  addd,1	0x0, [ _f64,_lts2 ST ], %b[3]
	}
	{
	  nop 2
	  addd,0	0x0, [ _f64,_lts0 CO ], %b[0]
	  addd,1	0x0, [ _f64,_lts2 IN ], %b[1]
	}
.LCS.1:
	{
	  call	%ctpr1, wbs = 0x4
	}
	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 OPT ], %r3
	}
	{
	  sxt,3	0x2, %r3, %r0
	}
	{
	  ct	%ctpr3
	}
.LCS.2:
	.size	main, .- main
	.section .bss
	.global	CO
	.type	CO, #object
	.size	CO, 0x200
	.align	16
CO:
	.skip	0x200
	.global	IN
	.type	IN, #object
	.size	IN, 0x10
	.align	16
IN:
	.skip	0x10
	.global	OPT
	.type	OPT, #object
	.size	OPT, 0x40
	.align	16
OPT:
	.skip	0x40
	.global	ST
	.type	ST, #object
	.size	ST, 0x800
	.align	16
ST:
	.skip	0x800
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
