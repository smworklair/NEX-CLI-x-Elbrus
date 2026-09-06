	.file	"poly_symm.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  adds,1	0x1, 0x0, %r4
	  ldd,2	0x0, [ _f64,_lts2 B +32 ], %g16
	  scld,3,sm	0x3, 0x4, %r3
	  scld,4,sm	0x3, 0x4, %g17
	  scld,5,sm	0x3, 0x4, %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +40 ], %g19
	  cmplsb,1,sm	0x0, %r4, %pred0
	  ldd,2	0x0, [ _f64,_lts2 B +16 ], %g20
	  addd,3	0x6, 0x0, %r9
	  adds,4	0x0, 0x0, %r7
	  addd,5	0x0, 0x0, %r6
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +24 ], %g21
	  merges,1,sm	0x1, %r4, %r12, %pred0
	  ldd,2	0x0, [ _f64,_lts2 B ], %g22
	  ldb,3,sm	%g17, [ _f64,_lts2 B ], %empty, mas=0x20
	  scld,4,sm	0x7, 0x3, %r11
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +8 ], %g17
	  addd,1	0x0, [ _f64,_lts2 C +32 ], %r19
	  ldd,2	0x0, [ _f64,_lts2 C +32 ], %g23
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 C +40 ], %g24
	  addd,1	0x0, [ _f64,_lts2 C +40 ], %r20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 C +16 ], %g25
	  addd,1	0x0, [ _f64,_lts2 C +24 ], %r18
	  ldd,2	0x0, [ _f64,_lts2 C +24 ], %g26
	  addd,3	0x0, [ _f64,_lts0 C +16 ], %r17
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A ], %g27
	  addd,1	0x0, [ _f64,_lts2 C +8 ], %r16
	  ldd,2	0x0, [ _f64,_lts2 C +8 ], %g28
	  ldb,3,sm	%g18, [ _f64,_lts0 A ], %empty, mas=0x20
	}
	{
	  ldd,0	0x0, [ _f64,_lts2 C ], %g18
	  addd,1	0x0, _f64,_lts0 0x3ff8000000000000, %r5
	  ldb,2,sm	%r3, [ _f64,_lts2 C ], %empty, mas=0x20
	  addd,4	0x0, [ _f64,_lts2 C ], %r15
	}
	{
	  fmuld,0	%r5, %g21, %g21
	  fmuld,1	%r5, %g16, %g16
	  fmuld,2	%r5, %g19, %g19
	  addd,3	0x0, _f64,_lts0 0x20fc2000000000, %g29
	}
	{
	  fmuld,0	%r5, %g22, %g22
	  fmuld,1	%r5, %g23, %g23
	  fmuld,2	%r5, %g17, %g17
	  fmuld,3	%r5, %g24, %g24
	  fmuld,4	%r5, 0x0, %g30
	  fmuld,5	%r5, %g20, %g20
	}
	{
	  fmuld,0	%r5, %g26, %g26
	  fmuld,2	%r5, %g25, %g25
	  insfd,3	%g29, _f32s,_lts0 0x8800, %r12, %r10
	}
	{
	  fmuld,0	%r5, %g28, %g28
	}
	{
	  fmuld,0	%r5, %g18, %g18
	  fmuld,1	%g16, %g27, %g16
	  fmuld,2	%g19, %g27, %g19
	}
	{
	  nop 2
	  fmuld,0	%g17, %g27, %g17
	  fmuld,1	%g21, %g27, %g21
	  fmuld,2	%g22, %g27, %g22
	  fmuld,3	%g20, %g27, %g20
	}
	{
	  faddd,0	%g23, %g16, %g16
	  faddd,1	%g24, %g19, %g19
	}
	{
	  nop 2
	  faddd,0	%g28, %g17, %g17
	  faddd,1	%g26, %g21, %g21
	  faddd,2	%g18, %g22, %g18
	  faddd,3	%g25, %g20, %g20
	}
	{
	  faddd,0	%g16, %g30, %g16
	  faddd,1	%g19, %g30, %g19
	}
	{
	  nop 2
	  faddd,0	%g17, %g30, %g17
	  faddd,1	%g21, %g30, %g21
	  faddd,2	%g18, %g30, %g18
	  faddd,3	%g20, %g30, %g20
	}
	{
	  qppackdl,0	%g19, %g16, %g16
	}
	{
	  qppackdl,0	%g17, %g18, %g17
	  stqp,2	0x0, [ _f64,_lts0 C +32 ], %g16
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 C ], %g17
	}
	{
	  qppackdl,0	%g21, %g20, %g16
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 C +16 ], %g16
	}
.L561:
	{
	  ldisp	%ctpr2, .L2228
	  rwd,0	%r10, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r15, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  addd,4	0x0, 0x0, %r0
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L1041
	  rwd,0	%r12, %lsr1
	  addd,1	%r3, [ _f64,_lts1 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,3,sm	%r11, _f16s,_lts0hi 0x38, %g20
	  addd,4,sm	%r3, _f16s,_lts0lo 0x30, %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L1041
	  addd,1,sm	%r3, [ _f64,_lts0 A ], %g16
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  ldd,0	%r3, [ _f64,_lts0 B ], %g17
	  ldb,2,sm	%g20, [ _f64,_lts2 A ], %empty, mas=0x20
	  ldb,3,sm	%g19, [ _f64,_lts2 A ], %empty, mas=0x20
	  ldb,5,sm	%g19, [ _f64,_lts0 B ], %empty, mas=0x20
	}
	{
	  bap
	  ldb,0,sm	%g19, [ _f64,_lts0 C ], %empty, mas=0x20
	  ldd,2,sm	0x0, [ _f64,_lts0 C ], %g18
	  ldd,3,sm	%r3, [ _f64,_lts2 A ], %g19
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 B ], %g20
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +48 ], %g21
	  ldd,2,sm	%g16, 0x8, %b[4]
	  ldd,3,sm	0x0, [ _f64,_lts2 B +48 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +96 ], %b[3]
	  ldd,2,sm	%g16, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +96 ], %b[8]
	  fmuld,1	%r5, %g17, %r2
	}
	{
	  nop 1
	  fmuld,0,sm	%g20, %g19, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %g19, %g18, %b[11]
	  fmul_addd,1,sm	%r2, %b[4], %g21, %b[9]
	}
	nop
	{
	  ct	%ctpr1
	}
	.align	8
.L2228:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=0
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=0
	}
.L1041:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  ldd,0	%r11, [ _f64,_lts1 A ], %r10
	}
	{
	  cmplsb,0,sm	0x0, %r4, %pred0
	  adds,1	0x0, 0x0, %g18
	  ldd,2	%r3, [ _f64,_lts0 C ], %g16
	  ldd,5	%r3, [ _f64,_lts2 B +8 ], %g17
	}
	{
	  disp	%ctpr2, disp=0x0
	  addd,0	0x0, _f64,_lts0 0x20fc2000000000, %g19
	  merges,1,sm	0x1, %r4, %r14, %pred0
	  aaurw,2	%g18, %aabf0
	}
	{
	  nop 1
	  insfd,0	%g19, _f32s,_lts0 0x8800, %r14, %r13
	  fmuld,2	%r5, %r0, %g18
	  addd,5	0x0, 0x0, %r0
	}
	{
	  fmuld,0	%r2, %r10, %g19
	}
	{
	  nop 3
	  fmuld,0	%r5, %g16, %g16
	  fmuld,1	%r5, %g17, %r2
	}
	{
	  nop 3
	  faddd,0	%g16, %g19, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g18, %g16
	}
	{
	  std,2	%r3, [ _f64,_lts0 C ], %g16
	}

	{
	  ldisp	%ctpr2, .L2205
	  rwd,0	%r13, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r16, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L1016
	  rwd,0	%r14, %lsr1
	  addd,1	%r3, [ _f64,_lts0 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,4,sm	%r3, [ _f64,_lts2 A ], %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L1016
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 C +8 ], %g16
	}
	{
	  bap
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +8 ], %g18
	  ldd,3,sm	%g19, 0x8, %b[4]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +56 ], %g20
	  ldd,2,sm	0x0, [ _f64,_lts2 B +56 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +104 ], %b[3]
	  ldd,2,sm	%g19, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +104 ], %b[8]
	}
	{
	  fmul_addd,0,sm	%r2, %g17, %g16, %b[11]
	  fmuld,1,sm	%g18, %g17, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %b[4], %g20, %b[9]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2205:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=8
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=8
	}
.L1016:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  ldd,0	%r3, [ _f64,_lts1 C +8 ], %g16
	}
	{
	  cmplsb,0,sm	0x0, %r4, %pred0
	  fmuld,1	%r2, %r10, %g17
	  ldd,2	%r3, [ _f64,_lts2 B +16 ], %g18
	  adds,3	0x0, 0x0, %g19
	  addd,4	0x0, _f64,_lts0 0x20fc2000000000, %g20
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r4, %r14, %pred0
	  aaurw,2	%g19, %aabf0
	}
	{
	  nop 1
	  insfd,0	%g20, _f32s,_lts0 0x8800, %r14, %r13
	  fmuld,2	%r5, %r0, %g19
	  addd,5	0x0, 0x0, %r0
	}
	{
	  fmuld,0	%r5, %g16, %g16
	}
	{
	  nop 2
	  fmuld,0	%r5, %g18, %r2
	}
	{
	  nop 3
	  faddd,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g19, %g16
	}
	{
	  std,2	%r3, [ _f64,_lts0 C +8 ], %g16
	}

	{
	  ldisp	%ctpr2, .L2182
	  rwd,0	%r13, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r17, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L991
	  rwd,0	%r14, %lsr1
	  addd,1	%r3, [ _f64,_lts0 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,4,sm	%r3, [ _f64,_lts2 A ], %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L991
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 C +16 ], %g16
	}
	{
	  bap
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +16 ], %g18
	  ldd,3,sm	%g19, 0x8, %b[4]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +64 ], %g20
	  ldd,2,sm	0x0, [ _f64,_lts2 B +64 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +112 ], %b[3]
	  ldd,2,sm	%g19, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +112 ], %b[8]
	}
	{
	  fmul_addd,0,sm	%r2, %g17, %g16, %b[11]
	  fmuld,1,sm	%g18, %g17, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %b[4], %g20, %b[9]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2182:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=16
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=16
	}
.L991:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  ldd,0	%r3, [ _f64,_lts1 C +16 ], %g16
	}
	{
	  cmplsb,0,sm	0x0, %r4, %pred0
	  fmuld,1	%r2, %r10, %g17
	  ldd,2	%r3, [ _f64,_lts2 B +24 ], %g18
	  adds,3	0x0, 0x0, %g19
	  addd,4	0x0, _f64,_lts0 0x20fc2000000000, %g20
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r4, %r14, %pred0
	  aaurw,2	%g19, %aabf0
	}
	{
	  nop 1
	  insfd,0	%g20, _f32s,_lts0 0x8800, %r14, %r13
	  fmuld,2	%r5, %r0, %g19
	  addd,5	0x0, 0x0, %r0
	}
	{
	  fmuld,0	%r5, %g16, %g16
	}
	{
	  nop 2
	  fmuld,0	%r5, %g18, %r2
	}
	{
	  nop 3
	  faddd,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g19, %g16
	}
	{
	  std,2	%r3, [ _f64,_lts0 C +16 ], %g16
	}

	{
	  ldisp	%ctpr2, .L2159
	  rwd,0	%r13, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r18, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L966
	  rwd,0	%r14, %lsr1
	  addd,1	%r3, [ _f64,_lts0 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,4,sm	%r3, [ _f64,_lts2 A ], %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L966
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 C +24 ], %g16
	}
	{
	  bap
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +24 ], %g18
	  ldd,3,sm	%g19, 0x8, %b[4]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +72 ], %g20
	  ldd,2,sm	0x0, [ _f64,_lts2 B +72 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +120 ], %b[3]
	  ldd,2,sm	%g19, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +120 ], %b[8]
	}
	{
	  fmul_addd,0,sm	%r2, %g17, %g16, %b[11]
	  fmuld,1,sm	%g18, %g17, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %b[4], %g20, %b[9]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2159:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=24
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=24
	}
.L966:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  ldd,0	%r3, [ _f64,_lts1 C +24 ], %g16
	}
	{
	  cmplsb,0,sm	0x0, %r4, %pred0
	  fmuld,1	%r2, %r10, %g17
	  ldd,2	%r3, [ _f64,_lts2 B +32 ], %g18
	  adds,3	0x0, 0x0, %g19
	  addd,4	0x0, _f64,_lts0 0x20fc2000000000, %g20
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r4, %r14, %pred0
	  aaurw,2	%g19, %aabf0
	}
	{
	  nop 1
	  insfd,0	%g20, _f32s,_lts0 0x8800, %r14, %r13
	  fmuld,2	%r5, %r0, %g19
	  addd,5	0x0, 0x0, %r0
	}
	{
	  fmuld,0	%r5, %g16, %g16
	}
	{
	  nop 2
	  fmuld,0	%r5, %g18, %r2
	}
	{
	  nop 3
	  faddd,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g19, %g16
	}
	{
	  std,2	%r3, [ _f64,_lts0 C +24 ], %g16
	}

	{
	  ldisp	%ctpr2, .L2136
	  rwd,0	%r13, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r19, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L941
	  rwd,0	%r14, %lsr1
	  addd,1	%r3, [ _f64,_lts0 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,4,sm	%r3, [ _f64,_lts2 A ], %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L941
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 C +32 ], %g16
	}
	{
	  bap
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +32 ], %g18
	  ldd,3,sm	%g19, 0x8, %b[4]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +80 ], %g20
	  ldd,2,sm	0x0, [ _f64,_lts2 B +80 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +128 ], %b[3]
	  ldd,2,sm	%g19, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +128 ], %b[8]
	}
	{
	  fmul_addd,0,sm	%r2, %g17, %g16, %b[11]
	  fmuld,1,sm	%g18, %g17, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %b[4], %g20, %b[9]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2136:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=32
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=32
	}
.L941:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  ldd,0	%r3, [ _f64,_lts1 C +32 ], %g16
	}
	{
	  cmplsb,0,sm	0x0, %r4, %pred0
	  fmuld,1	%r2, %r10, %g17
	  ldd,2	%r3, [ _f64,_lts2 B +40 ], %g18
	  adds,3	0x0, 0x0, %g19
	  addd,4	0x0, _f64,_lts0 0x20fc2000000000, %g20
	}
	{
	  disp	%ctpr2, disp=0x0
	  merges,0,sm	0x1, %r4, %r14, %pred0
	  aaurw,2	%g19, %aabf0
	}
	{
	  nop 1
	  insfd,0	%g20, _f32s,_lts0 0x8800, %r14, %r13
	  fmuld,2	%r5, %r0, %g19
	  addd,5	0x0, 0x0, %r0
	}
	{
	  fmuld,0	%r5, %g16, %g16
	}
	{
	  nop 2
	  fmuld,0	%r5, %g18, %r2
	}
	{
	  nop 3
	  faddd,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g19, %g16
	}
	{
	  std,2	%r3, [ _f64,_lts0 C +32 ], %g16
	}

	{
	  ldisp	%ctpr2, .L2112
	  rwd,0	%r13, %lsr
	  addd,1	0x0, [ _f64,_lts0 B +144 ], %g16
	  aaurwd,2	%r20, %aad1
	  addd,3	0x0, [ _f64,_lts2 C +144 ], %g17
	  aaurwd,5	%r6, %aasti4
	}
	{
	  disp	%ctpr1, .L916
	  rwd,0	%r14, %lsr1
	  addd,1	%r3, [ _f64,_lts0 A +24 ], %g18
	  aaurwd,2	%r9, %aaincr2
	  addd,4,sm	%r3, [ _f64,_lts2 A ], %g19
	  aaurwd,5	%r9, %aaincr1
	}
	{
	  disp	%ctpr1, .L916
	  aaurwd,2	%g16, %aaind1
	  aaurwd,5	%g17, %aaind2
	}
	{
	  aaurw,2	%r7, %aad0
	  aaurwd,5	%g18, %aaind3
	}
	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x1
	  setbn	rsz = 0x5, rbs = 0xb, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 C +40 ], %g16
	}
	{
	  bap
	  ldd,0,sm	%r3, [ _f64,_lts0 A ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +40 ], %g18
	  ldd,3,sm	%g19, 0x8, %b[4]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 C +88 ], %g20
	  ldd,2,sm	0x0, [ _f64,_lts2 B +88 ], %b[10]
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts1 C +136 ], %b[3]
	  ldd,2,sm	%g19, _f16s,_lts0lo 0x10, %b[2]
	}
	{
	  nop 1
	  ldd,0,sm	0x0, [ _f64,_lts0 B +136 ], %b[8]
	}
	{
	  fmul_addd,0,sm	%r2, %g17, %g16, %b[11]
	  fmuld,1,sm	%g18, %g17, %b[5]
	}
	{
	  nop 7
	  fmul_addd,0,sm	%r2, %b[4], %g20, %b[9]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2112:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=40
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=40
	}
.L916:
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[0]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,5,sm	%r2, %b[2], %b[3], %b[7]
	  movad,1	area=1, ind=0, am=1, be=0, %b[6]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmuld,1,sm	%b[10], %b[4], %b[3]
	  faddd,2,sm	%r0, %b[5], %r0
	  staad,5	%b[11], %aad1[ %aasti4 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0xb, nfx = 0x0, dbl = 0x1
	  disp	%ctpr1, .L561
	  ldd,0	%r3, [ _f64,_lts1 C +40 ], %g16
	}
	{
	  fmuld,0	%r2, %r10, %g17
	  adds,1	0x0, 0x0, %g18
	  adds,2	%r4, 0x1, %r4
	  addd,3,sm	%r11, _f16s,_lts0lo 0x38, %r11
	  addd,4,sm	0x0, _f64,_lts1 0x20fc2000000000, %g19
	}
	{
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r4, 0x6, %pred0
	  cmplsb,1,sm	0x0, %r4, %pred1
	  aaurw,2	%g18, %aabf0
	}
	{
	  disp	%ctpr2, .L160
	  fmuld,0	%r5, %r0, %g18
	  merges,1,sm	0x1, %r4, %r12, %pred1
	}
	{
	  insfd,0,sm	%g19, _f32s,_lts0 0x8800, %r12, %r10
	}
	{
	  nop 3
	  fmuld,0	%r5, %g16, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g17, %g16
	}
	{
	  nop 3
	  faddd,0	%g16, %g18, %g16
	}
	{
	  ct	%ctpr1 ? %pred0
	  addd,1,sm	%r3, _f16s,_lts0lo 0x30, %r3
	  std,2	%r3, [ _f64,_lts1 C +40 ], %g16
	}
	{
	  ct	%ctpr2 ? ~%pred0
	  ldd,0,sm	0x0, [ _f64,_lts0 C +112 ], %r2
	}
.L160:
	{
	  nop 3
	  return	%ctpr3
	}
	{
	  nop 5
	  fdtoistr,0	%r2, %g16
	}
	{
	  ct	%ctpr3
	  sxt,3	0x2, %g16, %r0
	}
	.size	main, .- main
	.section .bss
	.global	C
	.type	C, #object
	.size	C, 0x120
	.align	16
C:
	.skip	0x120
	.global	A
	.type	A, #object
	.size	A, 0x120
	.align	16
A:
	.skip	0x120
	.global	B
	.type	B, #object
	.size	B, 0x120
	.align	16
B:
	.skip	0x120
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
