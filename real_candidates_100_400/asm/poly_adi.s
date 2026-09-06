	.file	"poly_adi.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0xd, nfx = 0x1, dbl = 0x0
	  scrd,1	0x1, 0x1, %g18
	  addd,2	0xe, 0x0, %r12
	  istofd,3	_f16s,_lts1lo 0x10, %g16
	  istofd,4	0x2, %g17
	  adds,5	0x0, 0x0, %r11
	}
	{
	  scld,0	0x1, 0x7, %r24
	  adds,1	0x1, 0x0, %r23
	  addd,2	0x0, 0x0, %r20
	  addd,3	0x0, _f64,_lts0 0x3ff0000000000000, %r13
	  addd,4	0x0, _f64,_lts2 0x4000000000000000, %g19
	  addd,5	0x0, 0x0, %r18
	}
	{
	  addd,1	0x0, _f64,_lts2 0x3fe0000000000000, %g20
	  xornd,2	0xf, 0x0, %r22
	  subd,5	0x0, 0x1, %r17
	}
	{
	  addd,0	0x10, 0x0, %r21
	  addd,1	0x0, _f64,_lts0 0xffffffff, %r19
	}
	{
	  nop 1
	  fdivd,5	%r13, %g17, %g17
	}
	{
	  nop 7
	  fdivd,5	%r13, %g16, %g16
	}
	{
	  nop 3
	}
	{
	  nop 1
	  fmuld,3	%g19, %g17, %g21
	  fmuld,4	%r13, %g17, %g17
	}
	{
	  nop 3
	  fmuld,3	%g16, %g16, %g16
	}
	{
	  nop 1
	  fdivd,5	%g17, %g16, %g17
	}
	{
	  nop 7
	  fdivd,5	%g21, %g16, %g16
	}
	{
	  nop 3
	}
	{
	  nop 1
	  faddd,3	%r13, %g17, %r9
	}
	{
	  xord,0	%g17, %g18, %g17
	  faddd,3	%r13, %g16, %r8
	}
	{
	  fmuld,0	%g17, %g20, %r5
	}
	{
	  xord,0	%g16, %g18, %g16
	}
	{
	  nop 1
	  fmuld,0	%g16, %g20, %r4
	}
	{
	  nop 1
	  fmuld,0	%g19, %r5, %g16
	}
	{
	  nop 1
	  fmuld,0	%g19, %r4, %g17
	  xord,1	%r5, %g18, %r3
	}
	{
	  nop 1
	  faddd,0	%r13, %g16, %r7
	  xord,1	%r4, %g18, %r0
	}
	{
	  faddd,0	%r13, %g17, %r6
	}
.L37:
	{
	  scld,0,sm	0x1, 0x7, %g16
	  addd,1	0x8, 0x0, %r2
	  adds,2,sm	0x1, 0x0, %r16
	  ldb,3,sm	0x8, [ _f64,_lts0 u +120 ], %empty, mas=0x20
	  scld,4	0x1, 0x7, %r10
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts0 u +120 ], %g17
	  ldb,3,sm	%r10, [ _f64,_lts2 p +112 ], %empty, mas=0x20
	}
	{
	  nop 3
	  ldb,0,sm	%g16, [ _f64,_lts0 q +112 ], %empty, mas=0x20
	  ldd,2,sm	%r2, [ _f64,_lts2 u +128 ], %r15
	}
	{
	  nop 3
	  fmuld,0,sm	%r3, %g17, %r14
	}
.L48:
	{
	  ldisp	%ctpr2, .L1796
	  rwd,0	_f64,_lts0 0x40fb200000000e, %lsr
	  fmul_addd,1,sm	%r7, %r15, %r14, %g16
	  ldd,3,sm	%r2, [ _f64,_lts2 u +136 ], %g17
	  fmuld,4,sm	%r4, 0x0, %g18
	  aaurwd,5	%r18, %aasti3
	}
	{
	  disp	%ctpr1, .L799
	  rwd,0	%r12, %lsr1
	  addd,1	%r10, [ _f64,_lts0 p +8 ], %g19
	  aaurwd,2	%r18, %aasti2
	  addd,4	%r10, [ _f64,_lts2 q +8 ], %g20
	  aaurwd,5	%r21, %aaincr1
	}
	{
	  disp	%ctpr1, .L799
	  ldd,0,sm	%r2, [ _f64,_lts2 u +248 ], %g22
	  addd,1	%r2, [ _f64,_lts0 u +384 ], %g21
	  aaurwd,2	%g19, %aad2
	  addd,3,sm	0x8, %r2, %g19
	}
	{
	  std,2	%r10, [ _f64,_lts0 p ], %r20
	  std,5	%r10, [ _f64,_lts2 q ], %r13
	}
	{
	  addd,1,sm	%r10, _f16s,_lts0lo 0x80, %g20
	  std,2	%r2, [ _f64,_lts1 v ], %r13
	  faddd,4,sm	%g18, %r8, %g18
	  aaurwd,5	%g20, %aad1
	}
	{
	  addd,0,sm	%r2, [ _f64,_lts0 u ], %g21
	  aaurw,2	%r11, %aad0
	  aaurwd,5	%g21, %aaind1
	}
	{
	  bap
	  ldd,0,sm	%r2, [ _f64,_lts0 u +256 ], %g23
	  ldd,2,sm	%r2, [ _f64,_lts2 u +264 ], %g24
	}
	{
	  ldb,0,sm	%g20, [ _f64,_lts0 p +112 ], %empty, mas=0x20
	  ldb,2,sm	%g19, [ _f64,_lts2 u +120 ], %empty, mas=0x20
	}
	{
	  nop 1
	  ldb,0,sm	%g20, [ _f64,_lts0 q +112 ], %empty, mas=0x20
	  fmul_subd,1,sm	%r5, %g17, %g16, %g16
	}
	{
	  nop 3
	  fmuld,0,sm	%r3, %g22, %g17
	}
	{
	  fmul_addd,0,sm	%r7, %g23, %g17, %g17
	}
	{
	  setwd	wsz = 0x16, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x8, rbs = 0xd, rcur = 0x0
	}
	{
	  nop 5
	  ldd,0,sm	%g21, _f16s,_lts0lo 0x178, %b[9]
	  fmul_subd,1,sm	%r4, _f64,_lts2 0x3ff0000000000000, %g16, %g16
	  ldd,2,sm	%g21, _f16s,_lts0hi 0x180, %b[14]
	  ldd,3,sm	%g21, _f16s,_lts1lo 0x188, %b[13]
	  fdivd,5,sm	%r0, %g18, %b[7]
	}
	{
	  nop 3
	  fmul_subd,0,sm	%r5, %g24, %g17, %b[11]
	}
	{
	  nop 7
	  fdivd,5,sm	%g16, %g18, %b[6]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L1796:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=16, d=0, incr=1, ind=1, asz=5, abs=0, disp=120
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=136
	}
.L799:
	{
	  loop_mode
	  nop 1
	  fmuld,4,sm	%r4, %b[7], %b[8]
	}
	{
	  loop_mode
	  fmul_subd,3,sm	%r4, %b[6], %b[11], %b[10]
	}
	{
	  loop_mode
	  movad,1	area=0, ind=8, am=0, be=0, %b[12]
	}
	{
	  loop_mode
	  nop 3
	  faddd,4,sm	%b[8], %r8, %b[15]
	  fmuld,5,sm	%r3, %b[9], %b[16]
	  movad,3	area=0, ind=0, am=1, be=0, %b[11]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,3,sm	%r7, %b[14], %b[16], %b[8]
	  fdivd,5,sm	%r0, %b[15], %b[5]
	}
	{
	  loop_mode
	  nop 5
	  fdivd,5,sm	%b[10], %b[15], %b[4]
	}
	{
	  loop_mode
	  nop 3
	  fmul_subd,3,sm	%r5, %b[13], %b[8], %b[9]
	}
	{
	  loop_mode
	  staad,2	%b[7], %aad2[ %aasti3 ]
	  incr,2	%aaincr0
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staad,2	%b[6], %aad1[ %aasti2 ]
	  incr,2	%aaincr0
	  movad,1	area=0, ind=0, am=1, be=0, %b[7]
	}

	{
	  setwd	wsz = 0xd, nfx = 0x1, dbl = 0x0
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	  std,5	%r2, [ _f64,_lts0 v +1920 ], %r13
	}

	{
	  ldisp	%ctpr2, .L1772
	  rwd,0	_f64,_lts0 0x20fc200000000e, %lsr
	  addd,1	%r2, [ _f64,_lts2 v +1792 ], %g16
	  aaurwd,2	%r22, %aaincr2
	  aaurwd,5	%r17, %aaincr1
	}
	{
	  disp	%ctpr1, .L756
	  rwd,0	%r12, %lsr1
	  cmpbedb,1	%g16, _f64,_lts0 0xffffffff, %pred0
	  aaurw,2	%r11, %aad0
	  addd,4	%r2, [ _f64,_lts2 v +-4294965503 ], %g17
	}
	{
	  disp	%ctpr1, .L756
	  merged,1	%r19, %g16, %g16, %pred0
	  addd,2	%r10, [ _f64,_lts0 q +-16 ], %g18
	  addd,3	%r10, [ _f64,_lts2 p +-16 ], %g19
	  merged,4	%g17, 0x0, %g17, %pred0
	}
	{
	  addd,0,sm	%r10, [ _f64,_lts0 p ], %g16
	  addd,1,sm	%r10, [ _f64,_lts2 q ], %g17
	  aaurwd,2	%g16, %aasti3
	  aaurwd,5	%g17, %aad1
	}
	{
	  aaurwd,2	%g18, %aaind1
	  aaurwd,5	%g19, %aaind2
	}
	{
	  setwd	wsz = 0x11, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0xd, rcur = 0x0
	  bap
	  ldd,0,sm	%r10, [ _f64,_lts1 p +112 ], %g18
	}
	{
	  nop 4
	  ldd,0,sm	%r10, [ _f64,_lts1 q +112 ], %g19
	  ldd,2,sm	%g16, _f16s,_lts0lo 0x68, %b[7]
	  ldd,3,sm	%g17, _f16s,_lts0lo 0x68, %b[3]
	}
	{
	  nop 7
	  faddd,0,sm	%g18, %g19, %b[4]
	}
	{
	  nop 1
	}
	{
	  ct	%ctpr1
	}
.L1772:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=112
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=112
	}
.L756:
	{
	  loop_mode
	  nop 2
	  fmuld,2,sm	%b[7], %b[4], %b[1]
	}
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[5]
	}
	{
	  loop_mode
	  nop 2
	  faddd,2,sm	%b[1], %b[3], %b[2]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staad,2	%b[4], %aad1[ %aasti3 ]
	  incr,2	%aaincr2
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}

	{
	  setwd	wsz = 0xd, nfx = 0x1, dbl = 0x0
	  adds,0	0x0, 0x0, %g16
	  adds,1	%r16, 0x1, %r16
	}
	{
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r16, 0xf, %pred0
	  addd,1,sm	%r10, _f16s,_lts0lo 0x80, %r10
	  aaurw,2	%g16, %aabf0
	  addd,5,sm	0x8, %r2, %r2
	}
	{
	  disp	%ctpr3, .L48
	  ldd,3,sm	%r2, [ _f64,_lts0 u +120 ], %g16
	  ldd,5,sm	%r2, [ _f64,_lts2 u +128 ], %r15
	}
	{
	  nop 1
	  disp	%ctpr2, .L249
	}
	{
	  ct	%ctpr2 ? ~%pred0
	}
	nop
	{
	  nop 2
	  fmuld,0,sm	%r3, %g16, %r14
	}
	{
	  ct	%ctpr3 ? %pred0
	}
.L249:
	{
	  scld,0	0x1, 0x7, %r2
	  addd,1,sm	0x0, %r24, %g16
	  addd,2,sm	0x0, %r24, %g17
	  addd,3,sm	0x0, %r24, %g18
	  addd,4,sm	0x0, %r24, %g19
	  adds,5,sm	0x1, 0x0, %r15
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts0 v +-120 ], %g20
	  ldb,2,sm	%g17, [ _f64,_lts0 v +-120 ], %empty, mas=0x20
	  ldb,3,sm	%g18, [ _f64,_lts2 v +8 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%g19, [ _f64,_lts0 v +136 ], %empty, mas=0x20
	  ldb,2,sm	%g16, [ _f64,_lts2 q +112 ], %empty, mas=0x20
	}
	{
	  nop 2
	  ldb,0,sm	%r2, [ _f64,_lts0 p +112 ], %empty, mas=0x20
	  ldd,2,sm	%r2, [ _f64,_lts2 v +8 ], %r14
	}
	{
	  nop 3
	  fmuld,0,sm	%r0, %g20, %r10
	}
.L260:
	{
	  ldisp	%ctpr2, .L1753
	  rwd,0	_f64,_lts0 0x40fb200000000e, %lsr
	  fmul_addd,1,sm	%r6, %r14, %r10, %g16
	  ldd,3,sm	%r2, [ _f64,_lts2 v +136 ], %g17
	  fmuld,4,sm	%r5, 0x0, %g18
	  aaurwd,5	%r18, %aasti3
	}
	{
	  disp	%ctpr1, .L683
	  rwd,0	%r12, %lsr1
	  addd,1	%r2, [ _f64,_lts0 p +8 ], %g19
	  aaurwd,2	%r18, %aasti2
	  addd,4	%r2, [ _f64,_lts2 q +8 ], %g20
	  aaurw,5	%r11, %aad0
	}
	{
	  disp	%ctpr1, .L683
	  ldd,0,sm	%r2, [ _f64,_lts2 v +-112 ], %g22
	  addd,1	%r2, [ _f64,_lts0 v +-96 ], %g21
	  aaurwd,2	%g19, %aad2
	}
	{
	  std,2	%r2, [ _f64,_lts0 p ], %r20
	  std,5	%r2, [ _f64,_lts2 q ], %r13
	}
	{
	  addd,0,sm	%r2, _f16s,_lts0lo 0x80, %g19
	  std,2	%r2, [ _f64,_lts1 u ], %r13
	  faddd,3,sm	%g18, %r9, %g18
	  aaurwd,5	%g20, %aad1
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts0 v +16 ], %g20
	  aaurwd,2	%g21, %aaind1
	  ldd,5,sm	%r2, [ _f64,_lts2 v +144 ], %g21
	}
	{
	  bap
	  ldb,0,sm	%g19, [ _f64,_lts0 p +112 ], %empty, mas=0x20
	  ldb,2,sm	%g19, [ _f64,_lts2 v +-120 ], %empty, mas=0x20
	  addd,4,sm	%r2, [ _f64,_lts2 v +-120 ], %g23
	}
	{
	  ldb,0,sm	%g19, [ _f64,_lts0 q +112 ], %empty, mas=0x20
	  ldb,2,sm	%g19, [ _f64,_lts2 v +8 ], %empty, mas=0x20
	}
	{
	  nop 1
	  ldb,0,sm	%g19, [ _f64,_lts0 v +136 ], %empty, mas=0x20
	  fmul_subd,1,sm	%r4, %g17, %g16, %g16
	}
	{
	  nop 3
	  fmuld,0,sm	%r0, %g22, %g17
	}
	{
	  fmul_addd,0,sm	%r6, %g20, %g17, %g17
	}
	{
	  setwd	wsz = 0x16, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x8, rbs = 0xd, rcur = 0x0
	}
	{
	  nop 5
	  ldd,0,sm	%g23, _f16s,_lts0lo 0x10, %b[9]
	  fmul_subd,1,sm	%r5, _f64,_lts2 0x3ff0000000000000, %g16, %g16
	  ldd,2,sm	%g23, _f16s,_lts0hi 0x90, %b[14]
	  ldd,3,sm	%g23, _f16s,_lts1lo 0x110, %b[13]
	  fdivd,5,sm	%r3, %g18, %b[7]
	}
	{
	  nop 3
	  fmul_subd,0,sm	%r4, %g21, %g17, %b[11]
	}
	{
	  nop 7
	  fdivd,5,sm	%g16, %g18, %b[6]
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L1753:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=1, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=1, asz=5, abs=0, disp=128
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=1, asz=4, abs=16, disp=256
	}
.L683:
	{
	  loop_mode
	  nop 1
	  fmuld,4,sm	%r5, %b[7], %b[8]
	}
	{
	  loop_mode
	  fmul_subd,3,sm	%r5, %b[6], %b[11], %b[10]
	}
	{
	  loop_mode
	  movad,3	area=0, ind=0, am=1, be=0, %b[12]
	}
	{
	  loop_mode
	  nop 3
	  faddd,4,sm	%b[8], %r9, %b[15]
	  fmuld,5,sm	%r0, %b[9], %b[16]
	  movad,1	area=1, ind=0, am=1, be=0, %b[11]
	}
	{
	  loop_mode
	  nop 1
	  fmul_addd,3,sm	%r6, %b[14], %b[16], %b[8]
	  fdivd,5,sm	%r3, %b[15], %b[5]
	}
	{
	  loop_mode
	  nop 5
	  fdivd,5,sm	%b[10], %b[15], %b[4]
	}
	{
	  loop_mode
	  nop 3
	  fmul_subd,3,sm	%r4, %b[13], %b[8], %b[9]
	}
	{
	  loop_mode
	  staad,2	%b[7], %aad2[ %aasti3 ]
	  incr,2	%aaincr0
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staad,2	%b[6], %aad1[ %aasti2 ]
	  incr,2	%aaincr0
	  movad,1	area=0, ind=0, am=1, be=0, %b[7]
	}

	{
	  setwd	wsz = 0xd, nfx = 0x1, dbl = 0x0
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	  std,5	%r2, [ _f64,_lts0 u +120 ], %r13
	}

	{
	  ldisp	%ctpr2, .L1729
	  rwd,0	_f64,_lts0 0x20fc200000000e, %lsr
	  addd,1	%r2, [ _f64,_lts2 u +112 ], %g16
	  aaurwd,2	%r17, %aaincr2
	  aaurwd,5	%r17, %aaincr1
	}
	{
	  disp	%ctpr1, .L642
	  rwd,0	%r12, %lsr1
	  cmpbedb,1	%g16, _f64,_lts0 0xffffffff, %pred0
	  aaurw,2	%r11, %aad0
	  addd,4	%r2, [ _f64,_lts2 u +-4294967183 ], %g17
	}
	{
	  disp	%ctpr1, .L642
	  merged,1	%r19, %g16, %g16, %pred0
	  addd,2	%r2, [ _f64,_lts0 q +-16 ], %g18
	  addd,3	%r2, [ _f64,_lts2 p +-16 ], %g19
	  merged,4	%g17, 0x0, %g17, %pred0
	}
	{
	  addd,0,sm	%r2, [ _f64,_lts0 p ], %g16
	  addd,1,sm	%r2, [ _f64,_lts2 q ], %g17
	  aaurwd,2	%g16, %aasti3
	  aaurwd,5	%g17, %aad1
	}
	{
	  aaurwd,2	%g18, %aaind1
	  aaurwd,5	%g19, %aaind2
	}
	{
	  setwd	wsz = 0x11, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0xd, rcur = 0x0
	  bap
	  ldd,0,sm	%r2, [ _f64,_lts1 p +112 ], %g18
	}
	{
	  nop 4
	  ldd,0,sm	%r2, [ _f64,_lts1 q +112 ], %g19
	  ldd,2,sm	%g16, _f16s,_lts0lo 0x68, %b[7]
	  ldd,3,sm	%g17, _f16s,_lts0lo 0x68, %b[3]
	}
	{
	  nop 7
	  faddd,0,sm	%g18, %g19, %b[4]
	}
	{
	  nop 1
	}
	{
	  ct	%ctpr1
	}
.L1729:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=112
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=112
	}
.L642:
	{
	  loop_mode
	  nop 2
	  fmuld,2,sm	%b[7], %b[4], %b[1]
	}
	{
	  loop_mode
	  movad,1	area=0, ind=0, am=1, be=0, %b[5]
	}
	{
	  loop_mode
	  nop 2
	  faddd,2,sm	%b[1], %b[3], %b[2]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  staad,2	%b[4], %aad1[ %aasti3 ]
	  incr,2	%aaincr2
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}

	{
	  setwd	wsz = 0xd, nfx = 0x1, dbl = 0x0
	  adds,0	0x0, 0x0, %g16
	  adds,1	%r15, 0x1, %r15
	}
	{
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r15, 0xf, %pred0
	  aaurw,2	%g16, %aabf0
	  addd,5,sm	%r2, _f16s,_lts0lo 0x80, %r2
	}
	{
	  disp	%ctpr3, .L260
	  ldd,3,sm	%r2, [ _f64,_lts0 v +-120 ], %g16
	  ldd,5,sm	%r2, [ _f64,_lts2 v +8 ], %r14
	}
	{
	  nop 1
	  disp	%ctpr2, .L488
	}
	{
	  ct	%ctpr2 ? ~%pred0
	}
	nop
	{
	  nop 2
	  fmuld,0,sm	%r0, %g16, %r10
	}
	{
	  ct	%ctpr3 ? %pred0
	}
.L488:
	{
	  disp	%ctpr1, .L37
	  adds,0	%r23, 0x1, %r23
	}
	{
	  nop 3
	  cmplesb,0	%r23, 0x2, %pred0
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 u +272 ], %g16
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
	.global	u
	.type	u, #object
	.size	u, 0x800
	.align	16
u:
	.skip	0x800
	.global	v
	.type	v, #object
	.size	v, 0x800
	.align	16
v:
	.skip	0x800
	.global	p
	.type	p, #object
	.size	p, 0x800
	.align	16
p:
	.skip	0x800
	.global	q
	.type	q, #object
	.size	q, 0x800
	.align	16
q:
	.skip	0x800
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
