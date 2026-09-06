	.file	"poly_jacobi2d.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  adds,1	0x0, 0x0, %r7
	  addd,2	0xe, 0x0, %r6
	  adds,3	0x0, 0x0, %r5
	  addd,4	0x0, 0x0, %r4
	  addd,5	0x0, [ _f64,_lts2 A +136 ], %r38
	}
	{
	  addd,0	0x0, [ _f64,_lts0 B +136 ], %r37
	  addd,1	0x0, [ _f64,_lts2 A ], %r36
	  addd,2	0x10, 0x0, %r3
	}
	{
	  addd,1	0x0, [ _f64,_lts2 B ], %r35
	}
	{
	  addd,0	0x0, _f64,_lts0 0x3fc999999999999a, %r0
	}
.L6:
	{
	  ldisp	%ctpr2, .L2143
	  rwd,0	_f64,_lts0 0x1c2fd220000000e, %lsr
	  aaurwd,2	%r37, %aad1
	  aaurwd,5	%r4, %aasti2
	}
	{
	  disp	%ctpr1, .L17
	  rwd,0	%r6, %lsr1
	  aaurwd,2	%r3, %aaincr2
	  aaurwd,5	%r36, %aaind1
	}
	{
	  disp	%ctpr1, .L17
	  aaurw,2	%r5, %aad0
	  aaurwd,5	%r3, %aaincr1
	}
	{
	  setwd	wsz = 0x41, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x2c, rbs = 0x14, rcur = 0x0
	  ldd,0,sm	0x0, [ _f64,_lts1 A +112 ], %g16
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +240 ], %g17
	  ldd,2,sm	0x0, [ _f64,_lts2 A +104 ], %g18
	}
	{
	  bap
	  ldd,0,sm	0x0, [ _f64,_lts0 A +232 ], %g19
	  ldd,2,sm	0x0, [ _f64,_lts2 A +96 ], %g20
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +224 ], %g21
	  ldd,2,sm	0x0, [ _f64,_lts2 A +88 ], %g22
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +216 ], %g23
	  ldd,2,sm	0x0, [ _f64,_lts2 A +80 ], %g24
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +208 ], %g25
	  ldd,2,sm	0x0, [ _f64,_lts2 A +72 ], %g26
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +200 ], %g27
	  ldd,2,sm	0x0, [ _f64,_lts2 A +64 ], %g28
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +192 ], %g29
	  ldd,2,sm	0x0, [ _f64,_lts2 A +56 ], %g30
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +184 ], %g31
	  ldd,2,sm	0x0, [ _f64,_lts2 A +48 ], %r2
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +176 ], %r8
	  ldd,2,sm	0x0, [ _f64,_lts2 A +40 ], %r9
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +168 ], %r10
	  ldd,2,sm	0x0, [ _f64,_lts2 A +32 ], %r11
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +160 ], %r12
	  ldd,2,sm	0x0, [ _f64,_lts2 A +24 ], %r13
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +152 ], %r14
	  ldd,2,sm	0x0, [ _f64,_lts2 A +16 ], %r15
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +144 ], %r16
	  ldd,2,sm	0x0, [ _f64,_lts2 A +8 ], %r17
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +136 ], %r18
	}
	{
	  addd,1,sm	0x0, %r11, %b[39]
	  addd,2,sm	0x0, %r9, %b[23]
	  addd,3,sm	0x0, %r10, %b[21]
	  addd,4,sm	0x0, %r2, %b[28]
	  addd,5,sm	0x0, %r8, %b[26]
	}
	{
	  addd,0,sm	0x0, %r13, %b[44]
	  addd,1,sm	0x0, %r12, %b[37]
	  addd,2,sm	0x0, %g30, %b[60]
	  addd,3,sm	0x0, %g31, %b[58]
	  addd,4,sm	0x0, %g28, %b[47]
	  addd,5,sm	0x0, %g29, %b[45]
	}
	{
	  addd,0,sm	0x0, %r15, %b[20]
	  addd,1,sm	0x0, %r14, %b[42]
	  addd,2,sm	0x0, %g26, %b[52]
	  addd,3,sm	0x0, %g27, %b[50]
	  addd,4,sm	0x0, %g24, %b[55]
	  addd,5,sm	0x0, %g25, %b[53]
	}
	{
	  addd,0,sm	0x0, %r17, %b[5]
	  addd,1,sm	0x0, %r16, %b[18]
	  addd,2,sm	0x0, %g22, %b[15]
	  addd,3,sm	0x0, %g23, %b[13]
	  addd,4,sm	0x0, %g20, %b[36]
	  addd,5,sm	0x0, %g21, %b[34]
	}
	{
	  addd,0,sm	0x0, %r18, %b[3]
	  addd,1,sm	0x0, %g18, %b[31]
	  addd,2,sm	0x0, %g19, %b[29]
	  addd,3,sm	0x0, %g16, %b[4]
	  addd,4,sm	0x0, %g17, %b[2]
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L2143:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=0, disp=312
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=0, disp=280
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=8, disp=248
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=344
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=128
	}
.L17:
	{
	  loop_mode
	  faddd,0,sm	%b[36], %b[15], %b[67]
	  faddd,1,sm	%b[81], %b[20], %b[77]
	  faddd,2,sm	%b[80], %b[32], %b[76]
	  faddd,3,sm	%b[44], %b[20], %b[63]
	  faddd,4,sm	%b[63], %b[15], %b[72]
	  faddd,5,sm	%b[67], %b[56], %b[73]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[60], %b[28], %b[70]
	  faddd,1,sm	%b[12], %b[4], %b[71]
	  faddd,2,sm	%b[66], %b[51], %b[78]
	  faddd,3,sm	%b[70], %b[27], %b[79]
	  faddd,4,sm	%b[71], %b[5], %b[80]
	  faddd,5,sm	%b[55], %b[52], %b[66]
	  movad,0	area=2, ind=0, am=1, be=0, %b[12]
	  movad,1	area=1, ind=16, am=0, be=0, %b[1]
	  movad,2	area=1, ind=24, am=0, be=0, %b[0]
	  movad,3	area=1, ind=0, am=0, be=0, %b[11]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[31], %b[36], %b[75]
	  faddd,1,sm	%b[28], %b[23], %b[81]
	  faddd,2,sm	%b[75], %b[48], %b[85]
	  faddd,3,sm	%b[23], %b[39], %b[83]
	  faddd,4,sm	%b[74], %b[43], %b[84]
	  faddd,5,sm	%b[52], %b[47], %b[82]
	  movad,0	area=1, ind=24, am=1, be=0, %b[16]
	  movad,1	area=1, ind=0, am=0, be=0, %b[74]
	  movad,2	area=1, ind=8, am=1, be=0, %b[32]
	  movad,3	area=1, ind=16, am=0, be=0, %b[27]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[47], %b[60], %b[64]
	  faddd,1,sm	%b[64], %b[40], %b[69]
	  fmuld,2,sm	%r0, %b[69], %b[87]
	  faddd,3,sm	%b[39], %b[44], %b[59]
	  faddd,4,sm	%b[59], %b[35], %b[68]
	  fmuld,5,sm	%r0, %b[68], %b[86]
	  movad,0	area=0, ind=8, am=0, be=0, %b[43]
	  movad,1	area=0, ind=16, am=0, be=0, %b[48]
	  movad,2	area=0, ind=0, am=0, be=0, %b[40]
	  movad,3	area=0, ind=8, am=0, be=0, %b[35]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[67], %b[31], %b[67]
	  faddd,1,sm	%b[77], %b[24], %b[88]
	  fmuld,2,sm	%r0, %b[76], %b[77]
	  faddd,3,sm	%b[72], %b[19], %b[73]
	  fmuld,4,sm	%r0, %b[73], %b[76]
	  faddd,5,sm	%b[2], %b[29], %b[72]
	  movad,0	area=0, ind=0, am=1, be=0, %b[56]
	  movad,1	area=0, ind=24, am=0, be=0, %b[51]
	  movad,2	area=0, ind=16, am=0, be=0, %b[19]
	  movad,3	area=0, ind=24, am=1, be=0, %b[24]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[70], %b[47], %b[70]
	  faddd,1,sm	%b[71], %b[8], %b[71]
	  fmuld,2,sm	%r0, %b[78], %b[78]
	  fmuld,3,sm	%r0, %b[79], %b[79]
	  faddd,4,sm	%b[80], %b[9], %b[80]
	  faddd,5,sm	%b[66], %b[15], %b[66]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[75], %b[4], %b[75]
	  faddd,1,sm	%b[81], %b[60], %b[83]
	  fmuld,2,sm	%r0, %b[85], %b[85]
	  faddd,3,sm	%b[83], %b[28], %b[81]
	  faddd,4,sm	%b[82], %b[55], %b[82]
	  fmuld,5,sm	%r0, %b[84], %b[84]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[64], %b[52], %b[64]
	  fmuld,1,sm	%r0, %b[69], %b[86]
	  staad,2	%b[87], %aad1[ %aasti2 + _f32s,_lts1 0x30 ]
	  faddd,3,sm	%b[5], %b[14], %b[68]
	  fmuld,4,sm	%r0, %b[68], %b[69]
	  staad,5	%b[86], %aad1[ %aasti2 + _f32s,_lts0 0x48 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[63], %b[39], %b[63]
	  fmuld,1,sm	%r0, %b[88], %b[76]
	  staad,2	%b[77], %aad1[ %aasti2 + _f32s,_lts1 0x28 ]
	  faddd,3,sm	%b[59], %b[23], %b[59]
	  fmuld,4,sm	%r0, %b[73], %b[73]
	  staad,5	%b[76], %aad1[ %aasti2 + _f32s,_lts0 0x40 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[70], %b[58], %b[70]
	  fmuld,1,sm	%r0, %b[71], %b[71]
	  staad,2	%b[78], %aad1[ %aasti2 + _f32s,_lts0 0x38 ]
	  faddd,3,sm	%b[66], %b[53], %b[66]
	  fmuld,4,sm	%r0, %b[80], %b[77]
	  staad,5	%b[79], %aad1[ %aasti2 + _f32s,_lts1 0x20 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[65], %b[44], %b[79]
	  faddd,1,sm	%b[83], %b[26], %b[78]
	  staad,2	%b[85], %aad1[ %aasti2 + _f32s,_lts1 0x10 ]
	  faddd,3,sm	%b[61], %b[36], %b[61]
	  faddd,4,sm	%b[82], %b[50], %b[65]
	  staad,5	%b[84], %aad1[ %aasti2 + _f32s,_lts0 0x18 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[72], %b[74], %b[8]
	  faddd,1,sm	%b[64], %b[45], %b[64]
	  staad,2	%b[86], %aad1[ %aasti2 + _f32s,_lts1 0x58 ]
	  faddd,3,sm	%b[81], %b[21], %b[68]
	  faddd,4,sm	%b[68], %b[20], %b[69]
	  staad,5	%b[69], %aad1[ %aasti2 + _f32s,_lts0 0x60 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[18], %b[3], %b[63]
	  faddd,1,sm	%b[63], %b[42], %b[73]
	  staad,2	%b[76], %aad1[ %aasti2 + _f32s,_lts1 0x8 ]
	  faddd,3,sm	%b[13], %b[53], %b[59]
	  faddd,4,sm	%b[59], %b[37], %b[72]
	  staad,5	%b[73], %aad1[ %aasti2 + _f32s,_lts0 0x50 ]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  faddd,0,sm	%b[67], %b[34], %b[62]
	  faddd,1,sm	%b[70], %b[62], %b[67]
	  staad,2	%b[71], %aad1[ %aasti2 + _f32s,_lts0 0x68 ]
	  faddd,3,sm	%b[75], %b[29], %b[57]
	  faddd,4,sm	%b[66], %b[57], %b[66]
	  staad,5	%b[77], %aad1[ %aasti2 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  adds,0	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	  ldd,5,sm	0x0, [ _f64,_lts0 B +80 ], %r26
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +88 ], %r28
	  ldd,2,sm	0x0, [ _f64,_lts2 B +96 ], %r30
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +104 ], %r32
	  ldd,2,sm	0x0, [ _f64,_lts2 B +112 ], %r34
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +216 ], %r27
	  ldd,2,sm	0x0, [ _f64,_lts2 B +224 ], %r29
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +232 ], %r31
	  ldd,2,sm	0x0, [ _f64,_lts2 B +240 ], %r33
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +208 ], %r25
	  ldd,2,sm	0x0, [ _f64,_lts2 B +72 ], %r24
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +200 ], %r23
	  ldd,2,sm	0x0, [ _f64,_lts2 B +64 ], %r22
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +192 ], %r21
	  ldd,2,sm	0x0, [ _f64,_lts2 B +56 ], %r20
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +184 ], %r19
	  ldd,2,sm	0x0, [ _f64,_lts2 B +48 ], %r18
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +176 ], %r17
	  ldd,2,sm	0x0, [ _f64,_lts2 B +40 ], %r16
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +168 ], %r15
	  ldd,2,sm	0x0, [ _f64,_lts2 B +32 ], %r14
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +160 ], %r13
	  ldd,2,sm	0x0, [ _f64,_lts2 B +24 ], %r12
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +152 ], %r11
	  ldd,2,sm	0x0, [ _f64,_lts2 B +16 ], %r10
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +144 ], %r9
	  ldd,2,sm	0x0, [ _f64,_lts2 B +8 ], %r8
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 B +136 ], %r2
	}

	{
	  ldisp	%ctpr2, .L2080
	  rwd,0	_f64,_lts0 0x1c2fd220000000e, %lsr
	  aaurwd,2	%r38, %aad1
	  aaurwd,5	%r4, %aasti2
	}
	{
	  disp	%ctpr1, .L114
	  rwd,0	%r6, %lsr1
	  aaurwd,2	%r3, %aaincr2
	  aaurwd,5	%r35, %aaind1
	}
	{
	  disp	%ctpr1, .L114
	  aaurw,2	%r5, %aad0
	  aaurwd,5	%r3, %aaincr1
	}
	{
	  setwd	wsz = 0x41, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x2c, rbs = 0x14, rcur = 0x0
	}
	{
	  addd,0,sm	0x0, %r8, %b[5]
	  addd,1,sm	0x0, %r2, %b[3]
	  addd,2,sm	0x0, %r10, %b[20]
	  addd,3,sm	0x0, %r9, %b[18]
	  addd,4,sm	0x0, %r12, %b[44]
	  addd,5,sm	0x0, %r11, %b[42]
	}
	{
	  bap
	  addd,0,sm	0x0, %r14, %b[39]
	  addd,1,sm	0x0, %r13, %b[37]
	  addd,2,sm	0x0, %r16, %b[23]
	  addd,3,sm	0x0, %r15, %b[21]
	  addd,4,sm	0x0, %r18, %b[28]
	  addd,5,sm	0x0, %r17, %b[26]
	}
	{
	  addd,0,sm	0x0, %r20, %b[60]
	  addd,1,sm	0x0, %r19, %b[58]
	  addd,2,sm	0x0, %r22, %b[47]
	  addd,3,sm	0x0, %r21, %b[45]
	  addd,4,sm	0x0, %r24, %b[52]
	  addd,5,sm	0x0, %r23, %b[50]
	}
	{
	  addd,0,sm	0x0, %r26, %b[55]
	  addd,1,sm	0x0, %r25, %b[53]
	  addd,2,sm	0x0, %r28, %b[15]
	  addd,3,sm	0x0, %r27, %b[13]
	  addd,4,sm	0x0, %r30, %b[36]
	  addd,5,sm	0x0, %r29, %b[34]
	}
	{
	  nop 7
	  addd,0,sm	0x0, %r32, %b[31]
	  addd,1,sm	0x0, %r31, %b[29]
	  addd,2,sm	0x0, %r34, %b[4]
	  addd,3,sm	0x0, %r33, %b[2]
	}
	{
	  nop 6
	}
	{
	  ct	%ctpr1
	}
.L2080:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=0, disp=312
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=0, disp=280
	}
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=3, abs=8, disp=248
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=344
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=4, abs=16, disp=128
	}
.L114:
	{
	  loop_mode
	  faddd,0,sm	%b[36], %b[15], %b[67]
	  faddd,1,sm	%b[81], %b[20], %b[77]
	  faddd,2,sm	%b[80], %b[32], %b[76]
	  faddd,3,sm	%b[44], %b[20], %b[63]
	  faddd,4,sm	%b[63], %b[15], %b[72]
	  faddd,5,sm	%b[67], %b[56], %b[73]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[60], %b[28], %b[70]
	  faddd,1,sm	%b[12], %b[4], %b[71]
	  faddd,2,sm	%b[66], %b[51], %b[78]
	  faddd,3,sm	%b[71], %b[27], %b[80]
	  faddd,4,sm	%b[70], %b[5], %b[79]
	  faddd,5,sm	%b[55], %b[52], %b[66]
	  movad,0	area=2, ind=0, am=1, be=0, %b[12]
	  movad,1	area=1, ind=16, am=0, be=0, %b[1]
	  movad,2	area=1, ind=24, am=0, be=0, %b[0]
	  movad,3	area=1, ind=0, am=0, be=0, %b[11]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[31], %b[36], %b[75]
	  faddd,1,sm	%b[28], %b[23], %b[81]
	  faddd,2,sm	%b[75], %b[48], %b[84]
	  faddd,3,sm	%b[23], %b[39], %b[83]
	  faddd,4,sm	%b[74], %b[43], %b[85]
	  faddd,5,sm	%b[52], %b[47], %b[82]
	  movad,0	area=1, ind=24, am=1, be=0, %b[16]
	  movad,1	area=1, ind=0, am=0, be=0, %b[74]
	  movad,2	area=1, ind=8, am=1, be=0, %b[32]
	  movad,3	area=1, ind=16, am=0, be=0, %b[27]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[47], %b[60], %b[64]
	  faddd,1,sm	%b[64], %b[40], %b[69]
	  fmuld,2,sm	%r0, %b[69], %b[87]
	  faddd,3,sm	%b[39], %b[44], %b[59]
	  faddd,4,sm	%b[59], %b[35], %b[68]
	  fmuld,5,sm	%r0, %b[68], %b[86]
	  movad,0	area=0, ind=8, am=0, be=0, %b[43]
	  movad,1	area=0, ind=16, am=0, be=0, %b[48]
	  movad,2	area=0, ind=0, am=0, be=0, %b[40]
	  movad,3	area=0, ind=8, am=0, be=0, %b[35]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[67], %b[31], %b[67]
	  faddd,1,sm	%b[77], %b[24], %b[88]
	  fmuld,2,sm	%r0, %b[76], %b[77]
	  faddd,3,sm	%b[72], %b[19], %b[73]
	  fmuld,4,sm	%r0, %b[73], %b[76]
	  faddd,5,sm	%b[2], %b[29], %b[72]
	  movad,0	area=0, ind=0, am=1, be=0, %b[56]
	  movad,1	area=0, ind=24, am=0, be=0, %b[51]
	  movad,2	area=0, ind=16, am=0, be=0, %b[19]
	  movad,3	area=0, ind=24, am=1, be=0, %b[24]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[70], %b[47], %b[70]
	  faddd,1,sm	%b[71], %b[8], %b[71]
	  fmuld,2,sm	%r0, %b[78], %b[78]
	  fmuld,3,sm	%r0, %b[80], %b[80]
	  faddd,4,sm	%b[79], %b[9], %b[79]
	  faddd,5,sm	%b[66], %b[15], %b[66]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[75], %b[4], %b[75]
	  faddd,1,sm	%b[81], %b[60], %b[83]
	  fmuld,2,sm	%r0, %b[84], %b[84]
	  faddd,3,sm	%b[83], %b[28], %b[81]
	  faddd,4,sm	%b[82], %b[55], %b[82]
	  fmuld,5,sm	%r0, %b[85], %b[85]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[64], %b[52], %b[64]
	  fmuld,1,sm	%r0, %b[69], %b[86]
	  staad,2	%b[87], %aad1[ %aasti2 + _f32s,_lts1 0x30 ]
	  faddd,3,sm	%b[5], %b[14], %b[68]
	  fmuld,4,sm	%r0, %b[68], %b[69]
	  staad,5	%b[86], %aad1[ %aasti2 + _f32s,_lts0 0x48 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[63], %b[39], %b[63]
	  fmuld,1,sm	%r0, %b[88], %b[76]
	  staad,2	%b[77], %aad1[ %aasti2 + _f32s,_lts1 0x28 ]
	  faddd,3,sm	%b[59], %b[23], %b[59]
	  fmuld,4,sm	%r0, %b[73], %b[73]
	  staad,5	%b[76], %aad1[ %aasti2 + _f32s,_lts0 0x40 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[70], %b[58], %b[70]
	  fmuld,1,sm	%r0, %b[71], %b[71]
	  staad,2	%b[78], %aad1[ %aasti2 + _f32s,_lts0 0x38 ]
	  faddd,3,sm	%b[66], %b[53], %b[66]
	  fmuld,4,sm	%r0, %b[79], %b[77]
	  staad,5	%b[80], %aad1[ %aasti2 + _f32s,_lts1 0x20 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[65], %b[44], %b[79]
	  faddd,1,sm	%b[83], %b[26], %b[78]
	  staad,2	%b[84], %aad1[ %aasti2 + _f32s,_lts1 0x10 ]
	  faddd,3,sm	%b[61], %b[36], %b[61]
	  faddd,4,sm	%b[82], %b[50], %b[65]
	  staad,5	%b[85], %aad1[ %aasti2 + _f32s,_lts0 0x18 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[72], %b[74], %b[8]
	  faddd,1,sm	%b[64], %b[45], %b[64]
	  staad,2	%b[86], %aad1[ %aasti2 + _f32s,_lts1 0x58 ]
	  faddd,3,sm	%b[81], %b[21], %b[69]
	  faddd,4,sm	%b[68], %b[20], %b[68]
	  staad,5	%b[69], %aad1[ %aasti2 + _f32s,_lts0 0x60 ]
	}
	{
	  loop_mode
	  faddd,0,sm	%b[18], %b[3], %b[63]
	  faddd,1,sm	%b[63], %b[42], %b[73]
	  staad,2	%b[76], %aad1[ %aasti2 + _f32s,_lts1 0x8 ]
	  faddd,3,sm	%b[13], %b[53], %b[59]
	  faddd,4,sm	%b[59], %b[37], %b[72]
	  staad,5	%b[73], %aad1[ %aasti2 + _f32s,_lts0 0x50 ]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  faddd,0,sm	%b[67], %b[34], %b[62]
	  faddd,1,sm	%b[70], %b[62], %b[67]
	  staad,2	%b[71], %aad1[ %aasti2 + _f32s,_lts0 0x68 ]
	  faddd,3,sm	%b[75], %b[29], %b[57]
	  faddd,4,sm	%b[66], %b[57], %b[66]
	  staad,5	%b[77], %aad1[ %aasti2 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  disp	%ctpr1, .L6
	}
	{
	  disp	%ctpr3, .L208
	  ldd,0,sm	0x0, [ _f64,_lts0 A +272 ], %r2
	  adds,1	%r7, 0x1, %r7
	  adds,4	0x0, 0x0, %g16
	}
	{
	  nop 2
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r7, 0x2, %pred0
	  aaurw,2	%g16, %aabf0
	}
	{
	  ct	%ctpr1 ? %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L208:
	{
	  nop 5
	  return	%ctpr3
	  fdtoistr,0	%r2, %g16
	}
	{
	  ct	%ctpr3
	  sxt,3	0x2, %g16, %r0
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x800
	.align	16
A:
	.skip	0x800
	.global	B
	.type	B, #object
	.size	B, 0x800
	.align	16
B:
	.skip	0x800
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
