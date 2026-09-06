	.file	"poly_fdtd.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x0
	  addd,1	0xc, 0x0, %r14
	  addd,2,sm	0x0, 0x0, %r9
	  addd,3	0x0, 0x0, %r12
	  adds,4	0x0, 0x0, %r13
	  addd,5	0x0, [ _f64,_lts2 ey +96 ], %r25
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 _fict_ ], %empty, mas=0x20
	  adds,1,sm	0x0, 0x0, %r11
	  addd,2	0xb, 0x0, %r10
	  addd,3	0x0, [ _f64,_lts2 hz ], %r23
	}
	{
	  addd,1	0x0, [ _f64,_lts2 ex +8 ], %r24
	}
	{
	  addd,0	0x0, [ _f64,_lts0 ex ], %r22
	  addd,1	0x0, [ _f64,_lts2 ey ], %r21
	}
	{
	  addd,0	0x0, _f64,_lts0 0x3fe0000000000000, %r0
	  addd,1	0x0, _f64,_lts2 0x3fe6666666666666, %r7
	}
.L14:
	{
	  ldisp	%ctpr2, .L2172
	  rwd,0	_f64,_lts0 0x2e3fb230000000b, %lsr
	  ldd,3	%r9, [ _f64,_lts2 _fict_ ], %g16
	  aaurwd,5	%r25, %aad2
	}
	{
	  disp	%ctpr1, .L56
	  rwd,0	%r10, %lsr1
	  aaurwd,2	%r12, %aasti5
	  aaurwd,5	%r24, %aad1
	}
	{
	  disp	%ctpr1, .L56
	  aaurwd,2	%r12, %aasti4
	  aaurwd,5	%r14, %aaincr2
	}
	{
	  aaurwd,2	%r22, %aaind3
	  aaurwd,5	%r21, %aaind2
	}
	{
	  aaurwd,2	%r23, %aaind1
	  aaurw,5	%r13, %aad0
	}
	{
	  qppackdl,0	%g16, %g16, %g16
	  aaurwd,2	%r14, %aaincr1
	}
	{
	  setwd	wsz = 0x4d, nfx = 0x0, dbl = 0x0
	  setbn	rsz = 0x3b, rbs = 0x11, rcur = 0x0
	  stqp,2	0x0, [ _f64,_lts1 ey ], %g16
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ey +16 ], %g16
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ey +32 ], %g16
	  stqp,5	0x0, [ _f64,_lts2 ey +48 ], %g16
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ey +64 ], %g16
	  stqp,5	0x0, [ _f64,_lts2 ey +80 ], %g16
	}
	{
	  nop 7
	  bap
	}
	{
	  nop 7
	}
	{
	  nop 4
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L2172:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=2, abs=0, disp=96
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=2, abs=0, disp=128
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=2, abs=4, disp=160
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=4, disp=0
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=8, disp=32
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=8, disp=64
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=12, disp=96
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=12, disp=128
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=16, disp=160
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=3, asz=3, abs=16, disp=8
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=3, asz=3, abs=24, disp=40
	  fapb	dpl=0, dcd=0, fmt=4, mrng=24, d=0, incr=1, ind=3, asz=3, abs=24, disp=72
	}
.L56:
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g16, %b[11], %b[118]
	  fmul_subd,1,sm	%r0, %b[118], %b[10], %b[106]
	  fsubd,3,sm	%b[56], %b[44], %g18
	  fsubd,4,sm	%b[27], %b[36], %g17
	  staad,5	%b[106], %aad1[ %aasti4 + _f32s,_lts0 0x10 ]
	  movad,0	area=5, ind=0, am=0, be=0, %b[1]
	  movad,1	area=5, ind=8, am=0, be=0, %b[10]
	  movad,3	area=5, ind=0, am=0, be=0, %b[0]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g19, %b[65], %b[113]
	  fmul_subd,1,sm	%r0, %b[119], %b[20], %b[103]
	  staad,2	%b[113], %aad1[ %aasti4 ]
	  fsubd,3,sm	%b[47], %b[80], %g21
	  fsubd,4,sm	%b[39], %b[77], %g20
	  staad,5	%b[103], %aad1[ %aasti4 + _f32s,_lts0 0x8 ]
	  movad,0	area=5, ind=24, am=1, be=0, %b[11]
	  movad,1	area=5, ind=16, am=0, be=0, %b[47]
	  movad,2	area=5, ind=8, am=0, be=0, %b[39]
	  movad,3	area=5, ind=16, am=1, be=0, %b[20]
	}
	{
	  loop_mode
	  fmul_subd,1,sm	%r0, %g22, %b[84], %b[104]
	  staad,2	%b[114], %aad1[ %aasti4 + _f32s,_lts1 0x18 ]
	  fsubd,3,sm	%b[28], %b[36], %g23
	  fsubd,4,sm	%b[44], %b[35], %b[114]
	  staad,5	%b[104], %aad1[ %aasti4 + _f32s,_lts0 0x30 ]
	  movad,0	area=4, ind=0, am=0, be=0, %b[36]
	  movad,1	area=4, ind=8, am=0, be=0, %b[28]
	  movad,2	area=4, ind=24, am=0, be=0, %b[44]
	  movad,3	area=4, ind=0, am=0, be=0, %b[56]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g25, %b[60], %b[111]
	  fmul_subd,1,sm	%r0, %g24, %b[81], %b[101]
	  staad,2	%b[111], %aad1[ %aasti4 + _f32s,_lts1 0x48 ]
	  fsubd,3,sm	%b[35], %b[59], %g27
	  fsubd,4,sm	%b[19], %b[27], %g26
	  staad,5	%b[101], %aad1[ %aasti4 + _f32s,_lts0 0x50 ]
	  movad,0	area=4, ind=16, am=0, be=0, %b[65]
	  movad,1	area=4, ind=24, am=1, be=0, %b[60]
	  movad,2	area=4, ind=8, am=1, be=0, %b[77]
	  movad,3	area=4, ind=16, am=0, be=0, %b[80]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g29, %b[48], %b[112]
	  fmul_subd,1,sm	%r0, %g28, %b[51], %b[102]
	  staad,2	%b[112], %aad2[ %aasti5 + _f32s,_lts1 0x30 ]
	  fsubd,3,sm	%b[76], %b[73], %g31
	  fsubd,4,sm	%b[72], %b[68], %g30
	  staad,5	%b[102], %aad1[ %aasti4 + _f32s,_lts0 0x38 ]
	  movad,0	area=3, ind=0, am=0, be=0, %b[72]
	  movad,1	area=3, ind=8, am=0, be=0, %b[68]
	  movad,2	area=3, ind=0, am=0, be=0, %b[51]
	  movad,3	area=3, ind=8, am=0, be=0, %b[48]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %r3, %b[43], %b[109]
	  fmul_subd,1,sm	%r0, %r2, %b[24], %b[99]
	  staad,2	%b[109], %aad2[ %aasti5 + _f32s,_lts1 0x10 ]
	  fsubd,3,sm	%b[55], %b[59], %r5
	  fsubd,4,sm	%b[52], %b[35], %r4
	  staad,5	%b[99], %aad2[ %aasti5 + _f32s,_lts0 0x18 ]
	  movad,0	area=3, ind=16, am=0, be=0, %b[43]
	  movad,1	area=3, ind=24, am=1, be=0, %b[35]
	  movad,2	area=3, ind=24, am=1, be=0, %b[24]
	  movad,3	area=3, ind=16, am=0, be=0, %b[52]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g18, %b[100], %b[110]
	  fmul_subd,1,sm	%r0, %g17, %b[15], %b[100]
	  staad,2	%b[116], %aad2[ %aasti5 + _f32s,_lts1 0x38 ]
	  fsubd,3,sm	%b[69], %b[31], %g16
	  fsubd,4,sm	%b[64], %b[23], %b[116]
	  staad,5	%b[110], %aad1[ %aasti4 + _f32s,_lts0 0x28 ]
	  movad,0	area=2, ind=8, am=0, be=0, %b[31]
	  movad,1	area=2, ind=0, am=0, be=0, %b[55]
	  movad,2	area=2, ind=0, am=0, be=0, %b[23]
	  movad,3	area=2, ind=8, am=0, be=0, %b[15]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g21, %b[97], %b[107]
	  fmul_subd,1,sm	%r0, %g20, %b[92], %b[97]
	  staad,2	%b[117], %aad1[ %aasti4 + _f32s,_lts1 0x20 ]
	  fsubd,3,sm	%b[40], %b[27], %g19
	  fsubd,4,sm	%b[32], %b[19], %b[117]
	  staad,5	%b[107], %aad1[ %aasti4 + _f32s,_lts0 0x40 ]
	  incr,5	%aaincr2
	  movad,0	area=2, ind=16, am=0, be=0, %b[40]
	  movad,1	area=2, ind=24, am=1, be=0, %b[32]
	  movad,2	area=2, ind=16, am=0, be=0, %b[27]
	  movad,3	area=2, ind=24, am=1, be=0, %b[19]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g23, %b[89], %b[114]
	  fmul_subd,1,sm	%r0, %b[114], %b[14], %b[108]
	  staad,2	%r6, %aad2[ %aasti5 ]
	  fsubd,4,sm	%b[75], %b[78], %g22
	  staad,5	%b[108], %aad2[ %aasti5 + _f32s,_lts0 0x8 ]
	  movad,0	area=1, ind=0, am=0, be=0, %b[59]
	  movad,1	area=1, ind=8, am=0, be=0, %b[14]
	  movad,2	area=1, ind=0, am=0, be=0, %b[69]
	  movad,3	area=1, ind=8, am=0, be=0, %b[64]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g27, %b[5], %b[115]
	  fmul_subd,1,sm	%r0, %g26, %b[4], %b[105]
	  staad,2	%b[115], %aad2[ %aasti5 + _f32s,_lts1 0x20 ]
	  fsubd,3,sm	%b[66], %b[71], %g25
	  fsubd,4,sm	%b[78], %b[66], %g24
	  staad,5	%b[105], %aad2[ %aasti5 + _f32s,_lts0 0x28 ]
	  movad,0	area=1, ind=16, am=0, be=0, %b[5]
	  movad,1	area=1, ind=24, am=1, be=0, %b[4]
	  movad,2	area=1, ind=16, am=0, be=0, %b[76]
	  movad,3	area=1, ind=24, am=1, be=0, %b[73]
	}
	{
	  loop_mode
	  fmul_subd,0,sm	%r0, %g31, %b[96], %r6
	  fmul_subd,1,sm	%r0, %g30, %b[93], %b[106]
	  staad,2	%b[118], %aad2[ %aasti5 + _f32s,_lts1 0x50 ]
	  fsubd,3,sm	%b[57], %b[75], %g29
	  fsubd,4,sm	%b[34], %b[42], %g28
	  staad,5	%b[106], %aad2[ %aasti5 + _f32s,_lts0 0x58 ]
	  movad,0	area=0, ind=0, am=0, be=0, %b[92]
	  movad,1	area=0, ind=8, am=0, be=0, %b[89]
	  movad,2	area=0, ind=0, am=0, be=0, %b[84]
	  movad,3	area=0, ind=8, am=0, be=0, %b[81]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmul_subd,0,sm	%r0, %r5, %b[88], %b[113]
	  fmul_subd,1,sm	%r0, %r4, %b[85], %b[103]
	  staad,2	%b[113], %aad2[ %aasti5 + _f32s,_lts1 0x40 ]
	  fsubd,3,sm	%b[29], %b[17], %r3
	  fsubd,4,sm	%b[21], %b[29], %r2
	  staad,5	%b[103], %aad2[ %aasti5 + _f32s,_lts0 0x48 ]
	  incr,5	%aaincr2
	  movad,0	area=0, ind=16, am=0, be=0, %b[93]
	  movad,1	area=0, ind=24, am=1, be=0, %b[88]
	  movad,2	area=0, ind=24, am=1, be=0, %b[85]
	  movad,3	area=0, ind=16, am=0, be=0, %b[96]
	}

	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x0
	  ldd,0	0x0, [ _f64,_lts1 hz +1136 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1144 ], %g17
	  adds,1	0x0, 0x0, %g19
	  ldd,2	0x0, [ _f64,_lts2 hz +1080 ], %g18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1088 ], %g20
	  ldd,2	0x0, [ _f64,_lts2 hz +1096 ], %g21
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1104 ], %g22
	  ldd,2	0x0, [ _f64,_lts2 hz +1112 ], %g23
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1120 ], %g24
	  ldd,2	0x0, [ _f64,_lts2 hz +1128 ], %g25
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1064 ], %g26
	  ldd,2	0x0, [ _f64,_lts2 hz +1072 ], %g27
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 hz +1056 ], %g28
	  fsubd,1	%g17, %g16, %g17
	  ldd,2	0x0, [ _f64,_lts2 ex +1136 ], %g29
	}
	{
	  fsubd,0	%g20, %g18, %g20
	  fsubd,1	%g21, %g20, %g30
	  ldd,2	0x0, [ _f64,_lts0 ex +1144 ], %g31
	  ldd,3	0x0, [ _f64,_lts2 ex +1120 ], %r26
	}
	{
	  fsubd,0	%g22, %g21, %g21
	  fsubd,1	%g23, %g22, %r27
	  ldd,2	0x0, [ _f64,_lts0 ex +1128 ], %g22
	  ldd,3	0x0, [ _f64,_lts2 ex +1104 ], %r28
	}
	{
	  fsubd,0	%g24, %g23, %g23
	  fsubd,1	%g25, %g24, %r29
	  ldd,2	0x0, [ _f64,_lts0 ex +1112 ], %g24
	  ldd,3	0x0, [ _f64,_lts2 ex +1088 ], %g25
	  fsubd,4	%g16, %g25, %g16
	}
	{
	  fsubd,0	%g27, %g26, %g27
	  fsubd,1	%g18, %g27, %g18
	  ldd,2	0x0, [ _f64,_lts0 ex +1096 ], %r30
	  ldd,3	0x0, [ _f64,_lts2 ex +1072 ], %r31
	}
	{
	  fmuld,0	%r0, %g17, %g17
	  fsubd,1	%g26, %g28, %g26
	  ldd,2	0x0, [ _f64,_lts0 ex +1080 ], %g28
	  ldd,3	0x0, [ _f64,_lts2 ex +1064 ], %r32
	}
	{
	  fmuld,0	%r0, %g20, %g20
	  fmuld,1	%r0, %r27, %r27
	  fmuld,2	%r0, %g30, %g30
	  ldd,3,sm	0x0, [ _f64,_lts0 ey +80 ], %r20
	  ldd,5,sm	0x0, [ _f64,_lts2 ey +64 ], %r19
	}
	{
	  fmuld,0	%r0, %r29, %r29
	  fmuld,1	%r0, %g23, %g23
	  fmuld,2	%r0, %g21, %g21
	  ldd,3,sm	0x0, [ _f64,_lts0 ey +72 ], %r18
	  fmuld,4	%r0, %g16, %g16
	  ldd,5,sm	0x0, [ _f64,_lts2 ey +48 ], %r17
	}
	{
	  disp	%ctpr2, disp=0x0
	  fmuld,0	%r0, %g18, %g18
	  fmuld,1	%r0, %g27, %g27
	  aaurw,2	%g19, %aabf0
	  ldd,5,sm	0x0, [ _f64,_lts0 ey +56 ], %r16
	}
	{
	  fsubd,0	%g31, %g17, %g17
	  fmuld,1	%r0, %g26, %g19
	  ldd,2,sm	0x0, [ _f64,_lts0 ey +32 ], %r15
	  ldd,3,sm	0x0, [ _f64,_lts2 ey +40 ], %r6
	}
	{
	  fsubd,0	%g25, %g20, %g20
	  fsubd,1	%g24, %r27, %g24
	  fsubd,2	%r30, %g30, %g25
	  ldd,3,sm	0x0, [ _f64,_lts0 ey +16 ], %r5
	  ldd,5,sm	0x0, [ _f64,_lts2 ey +24 ], %r4
	}
	{
	  fsubd,0	%g22, %r29, %g22
	  fsubd,1	%r26, %g23, %g23
	  fsubd,2	%r28, %g21, %g21
	  ldd,3,sm	0x0, [ _f64,_lts0 ey ], %r3
	  fsubd,4	%g29, %g16, %g16
	  ldd,5,sm	0x0, [ _f64,_lts2 ey +8 ], %r2
	}
	{
	  fsubd,0	%r31, %g27, %g26
	  fsubd,1	%g28, %g18, %g18
	}
	{
	  nop 1
	  fsubd,0	%r32, %g19, %g19
	}
	{
	  qppackdl,1	%g22, %g23, %g22
	  qppackdl,3	%g17, %g16, %g16
	}
	{
	  qppackdl,0	%g25, %g20, %g17
	  qppackdl,1	%g24, %g21, %g20
	  stqp,2	0x0, [ _f64,_lts0 ex +1120 ], %g22
	  stqp,5	0x0, [ _f64,_lts2 ex +1136 ], %g16
	}
	{
	  qppackdl,0	%g18, %g26, %g16
	  std,2	0x0, [ _f64,_lts0 ex +1064 ], %g19
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ex +1088 ], %g17
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ex +1104 ], %g20
	}
	{
	  stqp,2	0x0, [ _f64,_lts0 ex +1072 ], %g16
	}

	{
	  ldisp	%ctpr2, .L2041
	  rwd,0	_f64,_lts0 0x164fa240000000b, %lsr
	  aaurwd,2	%r23, %aad1
	  aaurwd,5	%r12, %aasti4
	}
	{
	  disp	%ctpr1, .L212
	  rwd,0	%r10, %lsr1
	  aaurwd,2	%r14, %aaincr2
	  aaurwd,5	%r23, %aaind3
	}
	{
	  disp	%ctpr1, .L212
	  aaurwd,2	%r21, %aaind2
	  aaurwd,5	%r22, %aaind1
	}
	{
	  aaurw,2	%r13, %aad0
	  aaurwd,5	%r14, %aaincr1
	}
	{
	  setwd	wsz = 0x4d, nfx = 0x0, dbl = 0x0
	  setbn	rsz = 0x3b, rbs = 0x11, rcur = 0x0
	}
	{
	  bap
	  addd,0,sm	0x0, %r3, %b[42]
	  addd,1,sm	0x0, %r2, %b[14]
	  addd,2,sm	0x0, %r5, %b[25]
	  addd,3,sm	0x0, %r4, %b[20]
	  addd,4,sm	0x0, %r15, %b[85]
	  addd,5,sm	0x0, %r6, %b[55]
	}
	{
	  nop 7
	  addd,0,sm	0x0, %r17, %b[71]
	  addd,1,sm	0x0, %r16, %b[30]
	  addd,2,sm	0x0, %r19, %b[62]
	  addd,3,sm	0x0, %r18, %b[2]
	  addd,4,sm	0x0, %r20, %b[3]
	}
	{
	  nop 7
	}
	{
	  nop 2
	}
	{
	  ct	%ctpr1
	}
.L2041:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=3, asz=2, abs=0, disp=32
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=3, asz=3, abs=0, disp=0
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=2, abs=4, disp=32
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=8, disp=0
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=3, abs=8, disp=96
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=16, disp=64
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=24, d=0, incr=1, ind=3, asz=3, abs=16, disp=64
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=3, abs=24, disp=128
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=24, d=0, incr=1, ind=2, asz=3, abs=24, disp=160
	}
.L212:
	{
	  loop_mode
	  fsubd,5,sm	%b[28], %b[60], %g16
	  movad,0	area=4, ind=8, am=0, be=0, %b[0]
	  movad,1	area=4, ind=16, am=0, be=0, %b[1]
	}
	{
	  loop_mode
	  fsubd,3,sm	%b[115], %b[117], %b[90]
	  fadd_rsubd,4,sm	%b[118], %b[27], %b[29], %b[95]
	  fsubd,5,sm	%b[53], %b[50], %b[117]
	  movad,0	area=4, ind=0, am=1, be=0, %b[60]
	  movad,1	area=3, ind=8, am=0, be=0, %b[29]
	  movad,2	area=3, ind=24, am=0, be=0, %b[28]
	  movad,3	area=3, ind=8, am=0, be=0, %b[53]
	}
	{
	  loop_mode
	  fadd_rsubd,1,sm	%b[107], %b[64], %b[66], %b[89]
	  fadd_rsubd,2,sm	%b[116], %b[87], %b[89], %b[97]
	  fsubd,3,sm	%g17, %b[115], %b[96]
	  fmul_subd,4,sm	%r7, %b[97], %b[69], %b[103]
	  fsubd,5,sm	%b[50], %b[83], %b[107]
	  movad,0	area=3, ind=16, am=0, be=0, %b[50]
	  movad,1	area=3, ind=0, am=1, be=0, %b[66]
	  movad,2	area=3, ind=16, am=0, be=0, %b[69]
	  movad,3	area=3, ind=0, am=1, be=0, %b[83]
	}
	{
	  loop_mode
	  fadd_rsubd,0,sm	%b[92], %b[44], %b[46], %b[92]
	  fadd_rsubd,1,sm	%b[98], %b[16], %b[18], %b[98]
	  fmul_subd,2,sm	%r7, %b[108], %b[49], %b[104]
	  fsubd,3,sm	%b[81], %b[77], %b[105]
	  fmul_subd,4,sm	%r7, %b[99], %b[40], %b[99]
	  staad,5	%b[105], %aad1[ %aasti4 + _f32s,_lts0 0x10 ]
	  movad,0	area=2, ind=24, am=0, be=0, %b[18]
	  movad,1	area=2, ind=0, am=0, be=0, %b[40]
	  movad,2	area=2, ind=16, am=0, be=0, %b[46]
	  movad,3	area=2, ind=24, am=0, be=0, %b[49]
	}
	{
	  loop_mode
	  fadd_rsubd,0,sm	%b[112], %b[73], %b[75], %b[106]
	  fmul_subd,1,sm	%r7, %b[114], %b[80], %b[100]
	  staad,2	%b[106], %aad1[ %aasti4 + _f32s,_lts1 0x30 ]
	  fsubd,3,sm	%b[79], %b[23], %b[108]
	  fmul_subd,4,sm	%r7, %b[100], %b[12], %b[80]
	  staad,5	%b[101], %aad1[ %aasti4 + _f32s,_lts0 0x20 ]
	  movad,0	area=2, ind=8, am=1, be=0, %b[12]
	  movad,1	area=2, ind=16, am=0, be=0, %b[23]
	  movad,2	area=2, ind=0, am=0, be=0, %b[75]
	  movad,3	area=2, ind=8, am=1, be=0, %b[79]
	}
	{
	  loop_mode
	  fadd_rsubd,0,sm	%b[119], %b[57], %b[59], %b[112]
	  fmul_subd,1,sm	%r7, %b[113], %b[41], %b[82]
	  staad,2	%b[102], %aad1[ %aasti4 + _f32s,_lts1 0x28 ]
	  fsubd,3,sm	%b[63], %b[26], %b[114]
	  fmul_subd,4,sm	%r7, %b[94], %b[19], %b[59]
	  staad,5	%b[82], %aad1[ %aasti4 + _f32s,_lts0 0x8 ]
	  movad,0	area=1, ind=16, am=0, be=0, %b[41]
	  movad,1	area=1, ind=24, am=0, be=0, %b[19]
	  movad,2	area=1, ind=0, am=0, be=0, %b[115]
	  movad,3	area=1, ind=8, am=0, be=0, %b[113]
	}
	{
	  loop_mode
	  fadd_rsubd,0,sm	%g16, %b[22], %b[24], %b[111]
	  fmul_subd,1,sm	%r7, %b[111], %b[56], %b[72]
	  staad,2	%b[84], %aad1[ %aasti4 + _f32s,_lts0 0x18 ]
	  fsubd,3,sm	%b[58], %g17, %b[116]
	  fmul_subd,4,sm	%r7, %b[91], %b[72], %b[84]
	  staad,5	%b[61], %aad1[ %aasti4 ]
	  movad,0	area=1, ind=0, am=0, be=0, %b[24]
	  movad,1	area=1, ind=8, am=1, be=0, %b[61]
	  movad,2	area=1, ind=24, am=1, be=0, %b[56]
	  movad,3	area=1, ind=16, am=0, be=0, %g17
	}
	{
	  loop_mode
	  fadd_rsubd,0,sm	%b[117], %b[5], %b[7], %b[109]
	  fmul_subd,1,sm	%r7, %b[109], %b[35], %b[86]
	  staad,2	%b[74], %aad1[ %aasti4 + _f32s,_lts1 0x50 ]
	  fsubd,3,sm	%b[21], %b[43], %b[110]
	  fmul_subd,4,sm	%r7, %b[110], %b[13], %b[91]
	  staad,5	%b[86], %aad1[ %aasti4 + _f32s,_lts0 0x40 ]
	  movad,0	area=0, ind=24, am=0, be=0, %b[7]
	  movad,1	area=0, ind=8, am=0, be=0, %b[74]
	  movad,2	area=0, ind=24, am=0, be=0, %b[35]
	  movad,3	area=0, ind=0, am=0, be=0, %b[13]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fadd_rsubd,1,sm	%b[107], %b[4], %b[6], %b[107]
	  staad,2	%b[88], %aad1[ %aasti4 + _f32s,_lts1 0x48 ]
	  fsubd,3,sm	%b[43], %b[63], %b[117]
	  fadd_rsubd,4,sm	%b[108], %b[32], %b[34], %b[108]
	  staad,5	%b[93], %aad1[ %aasti4 + _f32s,_lts0 0x38 ]
	  incr,5	%aaincr2
	  movad,0	area=0, ind=16, am=0, be=0, %b[43]
	  movad,1	area=0, ind=0, am=1, be=0, %b[34]
	  movad,2	area=0, ind=8, am=1, be=0, %b[6]
	  movad,3	area=0, ind=16, am=0, be=0, %b[63]
	}

	{
	  setwd	wsz = 0x11, nfx = 0x0, dbl = 0x0
	  disp	%ctpr1, .L14
	}
	{
	  disp	%ctpr3, .L307
	  addd,0,sm	0x8, %r9, %r9
	  adds,1	%r11, 0x1, %r11
	  ldd,2,sm	0x0, [ _f64,_lts0 ex +208 ], %r2
	  adds,4	0x0, 0x0, %g16
	}
	{
	  nop 2
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r11, 0x2, %pred0
	  aaurw,2	%g16, %aabf0
	}
	{
	  ct	%ctpr1 ? %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L307:
	{
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
	.global	ex
	.type	ex, #object
	.size	ex, 0x480
	.align	16
ex:
	.skip	0x480
	.global	ey
	.type	ey, #object
	.size	ey, 0x480
	.align	16
ey:
	.skip	0x480
	.global	hz
	.type	hz, #object
	.size	hz, 0x480
	.align	16
hz:
	.skip	0x480
	.global	_fict_
	.type	_fict_, #object
	.size	_fict_, 0x10
	.align	16
_fict_:
	.skip	0x10
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
