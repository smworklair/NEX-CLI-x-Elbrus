	.file	"poly_syrk.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xf, nfx = 0x0, dbl = 0x1
	  adds,1,sm	0x0, 0x0, %r21
	  adds,2	0x0, 0x0, %r25
	  adds,3	0x0, 0x0, %r28
	  addd,4	0x0, _f64,_lts2 0x3ff8000000000000, %r26
	  addd,5	0x0, 0x0, %r12
	}
	{
	  adds,0,sm	%r21, 0x1, %r17
	  addd,1	0x0, 0x0, %r24
	  addd,2	0x1f, 0x1, %r23
	  addd,3	0x2, 0x0, %r22
	  addd,4	0x2, 0x0, %r27
	}
	{
	  cmplsb,0,sm	0x0, %r17, %pred1
	}
	{
	  merges,0,sm	0x1, %r17, %r4, %pred1
	}
	{
	  shrs,0	%r4, 0x1, %r3
	}
	{
	  nop 2
	  cmpesb,0	%r3, 0x0, %pred0
	}
.L236:
	{
	  ibranch	.L1226 ? %pred0
	  addd,0	0x0, 0x0, %r2
	  addd,1,sm	0x0, _f64,_lts0 0x40f22000000000, %r6
	  addd,2,sm	%r12, [ _f64,_lts2 C +192 ], %r5
	}
	{
	  cmplsb,0,sm	0x0, %r3, %pred0
	}

	{
	  ldisp	%ctpr2, .L2064
	  merges,0	0x1, %r3, %g16, %pred0
	  addd,1,sm	%r12, [ _f64,_lts2 C ], %g17
	  aaurwd,2	%r2, %aasti2
	  addd,4	0x0, _f64,_lts0 0x3ff8000000000000, %r0
	  aaurwd,5	%r27, %aaincr1
	}
	{
	  disp	%ctpr1, .L379
	  insfd,1	%r6, _f32s,_lts0 0x8800, %g16, %g18
	  aaurwd,2	%g17, %aad1
	  aaurw,5	%r28, %aad0
	}
	{
	  disp	%ctpr1, .L379
	  rwd,0	%g18, %lsr
	  andd,1	%g18, _f64,_lts0 0xffffffff, %g18
	  aaurwd,2	%r5, %aaind1
	  ldd,5,sm	%r12, [ _f64,_lts2 C +8 ], %g19
	}
	{
	  rwd,0	%g16, %lsr1
	  shld,1	%g18, 0x1, %r2
	  ldd,2,sm	%r12, [ _f64,_lts0 C ], %g16
	  ldd,3,sm	%r12, [ _f64,_lts2 C +24 ], %g20
	}
	{
	  setwd	wsz = 0x1e, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0xe, rbs = 0xf, rcur = 0x0
	  ldd,0,sm	%r12, [ _f64,_lts1 C +16 ], %g18
	}
	{
	  ldd,0,sm	%r12, [ _f64,_lts0 C +40 ], %g21
	  ldd,2,sm	%r12, [ _f64,_lts2 C +32 ], %g22
	}
	{
	  ldd,0,sm	%r12, [ _f64,_lts0 C +48 ], %g23
	  ldd,2,sm	%r12, [ _f64,_lts2 C +56 ], %g24
	}
	{
	  bap
	  ldd,0,sm	%r12, [ _f64,_lts0 C +64 ], %g25
	  ldd,2,sm	%r12, [ _f64,_lts2 C +72 ], %g26
	}
	{
	  ldd,0,sm	%r12, [ _f64,_lts0 C +80 ], %g27
	  ldd,2,sm	%r12, [ _f64,_lts2 C +88 ], %g28
	}
	{
	  ldd,0,sm	%r12, [ _f64,_lts0 C +96 ], %g29
	  ldd,2,sm	%r12, [ _f64,_lts2 C +104 ], %g30
	}
	{
	  ldd,0,sm	%g17, _f16s,_lts0lo 0x78, %b[10]
	  ldd,2,sm	%g17, _f16s,_lts0hi 0x70, %b[11]
	  ldd,3,sm	%g17, _f16s,_lts1lo 0x88, %b[8]
	  ldd,5,sm	%g17, _f16s,_lts1hi 0x80, %b[9]
	}
	{
	  ldd,0,sm	%g17, _f16s,_lts0lo 0x98, %b[6]
	  fmuld,1,sm	%g24, %r0, %b[20]
	  ldd,2,sm	%g17, _f16s,_lts0hi 0x90, %b[7]
	  ldd,3,sm	%g17, _f16s,_lts1lo 0xa8, %b[4]
	  fmuld,4,sm	%g23, %r0, %b[21]
	  ldd,5,sm	%g17, _f16s,_lts1hi 0xa0, %b[5]
	}
	{
	  ldd,0,sm	%g17, _f16s,_lts0lo 0xb8, %b[2]
	  fmuld,1,sm	%g26, %r0, %b[18]
	  ldd,2,sm	%g17, _f16s,_lts0hi 0xb0, %b[3]
	  fmuld,4,sm	%g25, %r0, %b[19]
	}
	{
	  fmuld,0,sm	%g28, %r0, %b[16]
	  fmuld,1,sm	%g27, %r0, %b[17]
	}
	{
	  nop 1
	  fmuld,0,sm	%g30, %r0, %b[14]
	  fmuld,1,sm	%g29, %r0, %b[15]
	}
	{
	  nop 3
	  fmuld,0,sm	%g19, %r0, %g17
	  fmuld,1,sm	%g16, %r0, %g16
	  fmuld,2,sm	%g20, %r0, %g19
	  fmuld,3,sm	%g18, %r0, %g18
	  fmuld,4,sm	%g21, %r0, %g20
	  fmuld,5,sm	%g22, %r0, %g21
	}
	{
	  nop 1
	  qppackdl,0,sm	%g17, %g16, %b[28]
	  qppackdl,3,sm	%g20, %g21, %b[24]
	}
	{
	  nop 1
	  qppackdl,0,sm	%g19, %g18, %b[26]
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L2064:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=16, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L379:
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  qppackdl,0,sm	%b[20], %b[21], %b[22]
	  fmuld,1,sm	%b[11], %r0, %b[13]
	  fmuld,2,sm	%b[10], %r0, %b[12]
	  staaqp,5	%b[28], %aad1[ %aasti2 ]
	  incr,5	%aaincr0
	  movad,0	area=0, ind=0, am=0, be=0, %b[1]
	  movad,1	area=0, ind=8, am=1, be=0, %b[0]
	}

	{
	  setwd	wsz = 0xf, nfx = 0x0, dbl = 0x1
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	}
.L1226:
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A ], %empty, mas=0x20
	  shld,1,sm	%r2, 0x3, %g16
	  ldb,2,sm	0x0, [ _f64,_lts2 A +56 ], %empty, mas=0x20
	  ldb,3,sm	%r12, [ _f64,_lts2 A +56 ], %empty, mas=0x20
	  shls,4	%r3, 0x1, %g17
	  adds,5	0x0, 0x0, %r10
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +128 ], %empty, mas=0x20
	  addd,1,sm	%r12, %g16, %g16
	  cmpesb,4	%g17, %r4, %pred0
	  addd,5,sm	%r12, [ _f64,_lts2 C ], %r16
	}
	{
	  nop 4
	  ldd,0,sm	%g16, [ _f64,_lts0 C ], %g17
	  addd,1	0x0, 0x0, %r9
	}
	{
	  nop 3
	  fmuld,0,sm	%g17, _f64,_lts0 0x3ff8000000000000, %g17
	}
	{
	  std,2	%g16, [ _f64,_lts0 C ], %g17 ? ~%pred0
	}
.L345:
	{
	  cmplsb,0,sm	0x0, %r17, %pred0
	  addd,1	0x0, 0x0, %r11
	  addd,2,sm	%r9, %r12, %g16
	  addd,3,sm	0x0, _f64,_lts0 0x4cf22c00000000, %g17
	  adds,4,sm	%r10, 0x1, %r13
	}
	{
	  ldd,0	%g16, [ _f64,_lts0 A ], %g18
	  merges,1,sm	0x1, %r17, %r20, %pred0
	  ldd,2	%g16, [ _f64,_lts2 A +8 ], %g19
	}
	{
	  ldd,0	%g16, [ _f64,_lts0 A +16 ], %g20
	  shrs,1	%r20, 0x1, %r19
	  ldd,2	%g16, [ _f64,_lts2 A +24 ], %g21
	  shld,3,sm	%r11, 0x7, %r15
	}
	{
	  cmpesb,0	%r19, 0x0, %pred0
	  cmplsb,1,sm	0x0, %r19, %pred1
	  ldd,2	%g16, [ _f64,_lts0 A +32 ], %g22
	  ldd,5	%g16, [ _f64,_lts2 A +40 ], %g23
	}
	{
	  ldd,0	%g16, [ _f64,_lts0 A +48 ], %g24
	  merges,1	0x1, %r19, %r29, %pred1 ? ~%pred0
	  ldd,2	%g16, [ _f64,_lts2 A +56 ], %g16
	  shls,3,sm	%r19, 0x1, %r14
	}
	{
	  insfd,1,sm	%g17, _f32s,_lts0 0x8800, %r29, %r18
	}
	{
	  fmuld,0	%r26, %g19, %r3
	  fmuld,1	%r26, %g18, %r0
	}
	{
	  fmuld,0	%r26, %g21, %r5
	  fmuld,1	%r26, %g20, %r2
	}
	{
	  fmuld,0	%r26, %g23, %r7
	  fmuld,1	%r26, %g22, %r4
	}
	{
	  ibranch	.L1050 ? %pred0
	  fmuld,0	%r26, %g16, %r8
	  fmuld,1	%r26, %g24, %r6
	}
	{
	  nop 2
	}

	{
	  ldisp	%ctpr2, .L1999
	  rwd,0	%r18, %lsr
	  addd,1,sm	%r9, [ _f64,_lts2 A ], %g16
	  aaurwd,2	%r16, %aad1
	  andd,3	%r18, _f64,_lts0 0xffffffff, %g17
	  aaurwd,5	%r24, %aasti3
	}
	{
	  disp	%ctpr1, .L543
	  rwd,0	%r29, %lsr1
	  aaurwd,2	%r22, %aaincr3
	  shld,3	%g17, 0x1, %r11
	  aaurwd,5	%r16, %aaind2
	}
	{
	  disp	%ctpr1, .L543
	  aaurw,2	%r25, %aad0
	  aaurwd,5	%r22, %aaincr2
	}
	{
	  aaurwd,2	%r23, %aaincr1
	  aaurwd,5	%g16, %aaind1
	}
	{
	  setwd	wsz = 0x4b, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x3b, rbs = 0xf, rcur = 0x0
	}
	{
	  nop 7
	  bap
	}
	{
	  nop 7
	}
	{
	  nop 1
	}
	{
	  ct	%ctpr1
	}
.L1999:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=0, disp=32
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=8, disp=128
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=160
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=16, d=0, incr=2, ind=2, asz=4, abs=16, disp=0
	}
.L543:
	{
	  loop_mode
	  fmul_addd,3,sm	%r4, %b[34], %b[117], %b[1]
	  fmul_addd,4,sm	%r4, %b[17], %b[116], %b[0]
	}
	{
	  loop_mode
	  fmul_addd,3,sm	%r8, %b[63], %b[100], %b[34]
	  fmul_addd,4,sm	%r8, %b[66], %b[87], %b[17]
	  movad,0	area=2, ind=0, am=0, be=0, %b[66]
	  movad,1	area=2, ind=8, am=1, be=0, %b[63]
	}
	{
	  loop_mode
	  fmul_addd,1,sm	%r0, %b[119], %b[68], %b[100]
	  fmul_addd,2,sm	%r0, %b[118], %b[65], %b[95]
	  fmul_addd,3,sm	%r2, %b[44], %b[111], %b[111]
	  fmul_addd,4,sm	%r2, %b[95], %b[110], %b[110]
	  movad,0	area=1, ind=24, am=0, be=0, %b[68]
	  movad,1	area=1, ind=16, am=0, be=0, %b[87]
	  movad,2	area=1, ind=24, am=0, be=0, %b[44]
	  movad,3	area=1, ind=16, am=0, be=0, %b[65]
	}
	{
	  loop_mode
	  fmul_addd,3,sm	%r7, %b[35], %b[3], %b[35]
	  fmul_addd,4,sm	%r7, %b[18], %b[2], %b[18]
	  movad,0	area=1, ind=0, am=0, be=0, %b[116]
	  movad,1	area=0, ind=0, am=0, be=0, %b[117]
	  movad,2	area=1, ind=8, am=1, be=0, %b[2]
	  movad,3	area=1, ind=0, am=0, be=0, %b[3]
	}
	{
	  loop_mode
	  fmul_addd,1,sm	%r3, %b[41], %b[102], %b[107]
	  fmul_addd,2,sm	%r3, %b[106], %b[97], %b[106]
	  fmul_addd,3,sm	%r5, %b[107], %b[113], %b[113]
	  fmul_addd,4,sm	%r5, %b[78], %b[112], %b[112]
	  movad,0	area=1, ind=8, am=1, be=0, %b[102]
	  movad,1	area=0, ind=24, am=0, be=0, %b[97]
	  movad,2	area=0, ind=24, am=0, be=0, %b[41]
	  movad,3	area=0, ind=16, am=0, be=0, %b[78]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staad,2	%b[36], %aad1[ %aasti3 ]
	  fmul_addd,3,sm	%r6, %b[96], %b[37], %b[96]
	  fmul_addd,4,sm	%r6, %b[83], %b[20], %b[83]
	  staad,5	%b[19], %aad1[ %aasti3 + _f32s,_lts0 0x8 ]
	  incr,5	%aaincr3
	  movad,0	area=0, ind=16, am=0, be=0, %b[36]
	  movad,1	area=0, ind=8, am=1, be=0, %b[37]
	  movad,2	area=0, ind=8, am=1, be=0, %b[19]
	  movad,3	area=0, ind=0, am=0, be=0, %b[20]
	}

	{
	  setwd	wsz = 0xf, nfx = 0x0, dbl = 0x1
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  shld,0,sm	%r11, 0x7, %r15
	  shls,1	%r19, 0x1, %r14
	  aaurw,2	%g16, %aabf0
	  adds,3,sm	%r10, 0x1, %r13
	}
.L1050:
	{
	  disp	%ctpr2, .L251
	  cmpesb,0	%r14, %r20, %pred0
	  addd,1,sm	%r15, %r9, %g16
	  addd,2,sm	%r9, _f16s,_lts0lo 0x40, %g17
	  cmplsb,3,sm	%r13, 0x2, %pred1
	  shld,4,sm	%r11, 0x3, %g18
	  adds,5,sm	%r10, 0x1, %g19
	}
	{
	  disp	%ctpr1, .L345
	  ldd,0,sm	%g16, [ _f64,_lts0 A ], %g20
	  addd,1,sm	0x0, %g17, %r9 ? %pred0
	  ldd,2,sm	%g16, [ _f64,_lts2 A +8 ], %g21
	  ldd,3,sm	%r16, %g18, %g17
	  adds,4	0x0, %r13, %r10 ? %pred0
	  pass	%pred0, @p0
	  pass	%pred1, @p1
	  landp	@p0, @p1, @p4
	  pass	@p4, %pred2
	  landp	@p0, ~@p1, @p5
	  pass	@p5, %pred1
	}
	{
	  ldd,0,sm	%g16, [ _f64,_lts0 A +16 ], %g22
	  cmplsb,1,sm	%g19, 0x2, %pred3
	  ldd,2,sm	%g16, [ _f64,_lts2 A +24 ], %g23
	  adds,4	0x0, %g19, %r10 ? ~%pred0
	}
	{
	  ldd,0,sm	%g16, [ _f64,_lts0 A +32 ], %g19
	  ldd,2,sm	%g16, [ _f64,_lts2 A +40 ], %g24
	  pass	%pred0, @p0
	  pass	%pred3, @p1
	  landp	~@p0, ~@p1, @p4
	  pass	@p4, %pred4
	  landp	~@p0, @p1, @p5
	  pass	@p5, %pred3
	}
	{
	  ct	%ctpr1 ? %pred2
	  ldd,0,sm	%g16, [ _f64,_lts0 A +48 ], %g25
	  ldd,2,sm	%g16, [ _f64,_lts2 A +56 ], %g16
	}
	{
	  ct	%ctpr2 ? %pred1
	  addd,1,sm	%r9, _f16s,_lts0lo 0x40, %g26
	}
	{
	  nop 1
	  fmuld,0,sm	%r0, %g20, %g20
	  addd,1,sm	0x0, %g26, %r9 ? ~%pred0
	}
	{
	  nop 1
	  fmuld,0,sm	%r3, %g21, %g21
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g20, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r2, %g22, %g20
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g21, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r5, %g23, %g21
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g20, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r4, %g19, %g19
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g21, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r7, %g24, %g20
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g19, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r6, %g25, %g19
	}
	{
	  nop 1
	  faddd,0,sm	%g17, %g20, %g17
	}
	{
	  nop 1
	  fmuld,0,sm	%r8, %g16, %g16
	}
	{
	  nop 3
	  faddd,0,sm	%g17, %g19, %g17
	}
	{
	  nop 3
	  faddd,0,sm	%g17, %g16, %g16
	}
	{
	  ct	%ctpr1 ? %pred3
	  std,2	%r16, %g18, %g16 ? ~%pred0
	}
	{
	  ct	%ctpr2 ? %pred4
	}
.L251:
	{
	  disp	%ctpr1, .L236
	  cmplsb,0	%r17, _f16s,_lts0lo 0x10, %pred1
	  addd,1,sm	%r12, _f16s,_lts0hi 0x80, %r12
	  adds,2	%r21, 0x1, %r21
	}
	{
	  adds,0,sm	%r21, 0x1, %r17
	}
	{
	  cmplsb,0,sm	0x0, %r17, %pred2
	}
	{
	  merges,0,sm	0x1, %r17, %r4, %pred2
	}
	{
	  shrs,0,sm	%r4, 0x1, %r3
	}
	{
	  nop 1
	  cmpesb,0,sm	%r3, 0x0, %pred0
	}
	{
	  ct	%ctpr1 ? %pred1
	}

	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 C +272 ], %g16
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
	.global	C
	.type	C, #object
	.size	C, 0x800
	.align	16
C:
	.skip	0x800
	.global	A
	.type	A, #object
	.size	A, 0x800
	.align	16
A:
	.skip	0x800
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
