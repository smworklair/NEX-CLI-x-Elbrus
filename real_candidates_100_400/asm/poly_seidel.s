	.file	"poly_seidel.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  nop 2
	  setwd	wsz = 0x1b, nfx = 0x1, dbl = 0x0
	  adds,1	0x0, 0x0, %r35
	  addd,2	0x0, [ _f64,_lts2 A ], %r38
	  adds,3	0x0, 0x0, %r37
	  addd,4	0x10, 0x0, %r36
	}
.L6:
	{
	  ldisp	%ctpr2, .L1533
	  rwd,0	_f64,_lts0 0x1fe0ff200000000e, %lsr
	  scld,1,sm	0x1, 0x7, %r0
	  aaurw,2	%r37, %aad0
	  addd,3	0x0, _f64,_lts2 0x4022000000000000, %r34
	  aaurwd,5	%r38, %aaind1
	}
	{
	  disp	%ctpr3, .L1316
	  ldd,0,sm	0x0, [ _f64,_lts0 A +120 ], %r33
	  aaurwd,2	%r36, %aaincr1
	  ldd,5,sm	0x0, [ _f64,_lts2 A +248 ], %r32
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +112 ], %r31
	  ldd,2,sm	0x0, [ _f64,_lts2 A +240 ], %r30
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +104 ], %r29
	  ldd,2,sm	0x0, [ _f64,_lts2 A +232 ], %r28
	}
	{
	  bap
	  ldd,0,sm	0x0, [ _f64,_lts0 A +96 ], %r27
	  ldd,2,sm	0x0, [ _f64,_lts2 A +224 ], %r26
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +88 ], %r25
	  ldd,2,sm	0x0, [ _f64,_lts2 A +216 ], %r24
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +80 ], %r23
	  ldd,2,sm	0x0, [ _f64,_lts2 A +208 ], %r22
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +72 ], %r21
	  ldd,2,sm	0x0, [ _f64,_lts2 A +200 ], %r20
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +64 ], %r19
	  ldd,2,sm	0x0, [ _f64,_lts2 A +192 ], %r18
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +56 ], %r17
	  ldd,2,sm	0x0, [ _f64,_lts2 A +184 ], %r16
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +48 ], %r15
	  ldd,2,sm	0x0, [ _f64,_lts2 A +176 ], %r14
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +40 ], %r13
	  ldd,2,sm	0x0, [ _f64,_lts2 A +168 ], %r12
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +32 ], %r11
	  ldd,2,sm	0x0, [ _f64,_lts2 A +160 ], %r10
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +24 ], %r9
	  ldd,2,sm	0x0, [ _f64,_lts2 A +152 ], %r8
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +16 ], %r7
	  ldd,2,sm	0x0, [ _f64,_lts2 A +144 ], %r6
	}
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 A +8 ], %r5
	  ldd,2,sm	0x0, [ _f64,_lts2 A +136 ], %r4
	}
	{
	  nop 4
	  ldd,0,sm	0x0, [ _f64,_lts0 A ], %r3
	  ldd,2,sm	0x0, [ _f64,_lts2 A +128 ], %r2
	}
	{
	  ct	%ctpr3
	}
.L167:
	{
	  disp	%ctpr1, .L6
	  adds,0	%r35, 0x1, %r35
	  adds,1	0x0, 0x0, %g16
	}
	{
	  disp	%ctpr3, .L150
	  cmplesb,0	%r35, 0x1, %pred0
	}
	{
	  nop 2
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g16, %aabf0
	}
	{
	  ct	%ctpr1 ? %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
	.align	8
.L1533:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=0, disp=256
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=0, disp=288
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=320
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=352
	}
.L1316:
	{
	  loop_mode
	  disp	%ctpr1, .L1316
	  faddd,0	%r11, %r13, %g23
	  faddd,1	%r13, %r15, %g24
	  faddd,2	%r15, %r17, %g25
	  faddd,3	%r3, %r5, %g16
	  faddd,4	%r5, %r7, %g19
	  faddd,5	%r7, %r9, %g20
	  movad,0	area=0, ind=8, am=0, be=0, %g18
	  movad,1	area=0, ind=16, am=0, be=0, %g17
	  movad,2	area=0, ind=8, am=0, be=0, %g22
	  movad,3	area=0, ind=0, am=0, be=0, %g21
	}
	{
	  loop_mode
	  disp	%ctpr3, .L167
	  faddd,0	%r21, %r23, %r40
	  faddd,1	%r23, %r25, %r41
	  faddd,2	%r25, %r27, %r42
	  faddd,3	%r9, %r11, %g28
	  faddd,4	%r17, %r19, %g31
	  faddd,5	%r19, %r21, %r39
	  movad,0	area=0, ind=24, am=0, be=0, %g27
	  movad,1	area=0, ind=0, am=1, be=0, %g26
	  movad,2	area=0, ind=24, am=0, be=0, %g30
	  movad,3	area=0, ind=16, am=1, be=0, %g29
	}
	{
	  loop_mode
	  faddd,3	%r27, %r29, %r47
	  faddd,4	%r29, %r31, %r48
	  movad,0	area=1, ind=8, am=0, be=0, %r44
	  movad,1	area=1, ind=0, am=0, be=0, %r43
	  movad,2	area=1, ind=8, am=0, be=0, %r46
	  movad,3	area=1, ind=0, am=0, be=0, %r45
	}
	{
	  loop_mode
	  movad,0	area=1, ind=24, am=0, be=0, %r50
	  movad,1	area=1, ind=16, am=1, be=0, %r49
	  movad,2	area=1, ind=24, am=0, be=0, %r52
	  movad,3	area=1, ind=16, am=1, be=0, %r51
	}
	{
	  loop_mode
	  faddd,0	%g23, %r15, %g23
	  faddd,1	%g24, %r17, %g24
	  faddd,2	%g25, %r19, %g25
	  faddd,3	%g16, %r7, %g16
	  faddd,4	%g19, %r9, %g19
	  faddd,5	%g20, %r11, %g20
	}
	{
	  loop_mode
	  faddd,0	%r40, %r25, %r40
	  faddd,1	%r41, %r27, %r41
	  faddd,2	%r42, %r29, %r42
	  faddd,3	%g28, %r13, %g28
	  faddd,4	%g31, %r21, %g31
	  faddd,5	%r39, %r23, %r39
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r47, %r31, %r47
	  faddd,4	%r48, %r33, %r48
	}
	{
	  loop_mode
	  nop 3
	  addd,0,sm	0x0, %r32, %r33
	  addd,1,sm	0x0, %g26, %r2
	  faddd,3	%g16, %r2, %g16
	  addd,5,sm	0x0, %r2, %r3
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r4, %g16
	  addd,4,sm	0x0, %g18, %r4
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r6, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g26, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g18, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g17, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g19, %g16, %g19
	  std,5	%r0, [ _f64,_lts0 A +8 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r5
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g19, %r6, %g16
	  addd,4,sm	0x0, %g17, %r6
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r8, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g18, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g17, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g27, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g20, %g16, %g18
	  std,5	%r0, [ _f64,_lts0 A +16 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r7
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g18, %r8, %g16
	  addd,4,sm	0x0, %g27, %r8
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r10, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g17, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g27, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g21, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g28, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +24 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r9
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r10, %g16
	  addd,4,sm	0x0, %g21, %r10
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r12, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g27, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g21, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g22, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g23, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +32 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r11
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r12, %g16
	  addd,4,sm	0x0, %g22, %r12
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r14, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g21, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g22, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g29, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g24, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +40 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r13
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r14, %g16
	  addd,4,sm	0x0, %g29, %r14
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r16, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g22, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g29, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g30, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g25, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +48 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r15
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r16, %g16
	  addd,4,sm	0x0, %g30, %r16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r18, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g29, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g30, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r43, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%g31, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +56 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r17
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r18, %g16
	  addd,4,sm	0x0, %r43, %r18
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r20, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %g30, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r43, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r44, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r39, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +64 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r19
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r20, %g16
	  addd,4,sm	0x0, %r44, %r20
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r22, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r43, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r44, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r49, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r40, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +72 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r21
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r22, %g16
	  addd,4,sm	0x0, %r49, %r22
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r24, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r44, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r49, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r50, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r41, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +80 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r23
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r24, %g16
	  addd,4,sm	0x0, %r50, %r24
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r26, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r49, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r50, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r45, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r42, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +88 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r25
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r26, %g16
	  addd,4,sm	0x0, %r45, %r26
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r28, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r50, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r45, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r46, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r47, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +96 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,0,sm	0x0, %g16, %r27
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r28, %g16
	  addd,4,sm	0x0, %r46, %r28
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r30, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r45, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r46, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r51, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  faddd,3	%r48, %g16, %g17
	  std,5	%r0, [ _f64,_lts0 A +104 ], %g16
	}
	{
	  loop_mode
	  nop 1
	  addd,4,sm	0x0, %g16, %r29
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g17, %r30, %g16
	  addd,4,sm	0x0, %r51, %r30
	}
	{
	  loop_mode
	  nop 3
	  addd,0,sm	0x0, %r52, %r32
	  faddd,3	%g16, %r32, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r46, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r51, %g16
	}
	{
	  loop_mode
	  nop 3
	  faddd,3	%g16, %r52, %g16
	}
	{
	  loop_mode
	  nop 7
	  fdivd,5	%g16, %r34, %g16
	}
	{
	  loop_mode
	  nop 5
	}
	{
	  loop_mode
	  nop 1
	  addd,3,sm	%r0, _f16s,_lts0lo 0x80, %r0
	  std,5	%r0, [ _f64,_lts1 A +112 ], %g16
	}
	{
	  loop_mode
	  ct	%ctpr1 ? %NOT_LOOP_END
	  alc	alcf=0, alct=1
	  addd,3,sm	0x0, %g16, %r31
	}
	{
	  loop_mode
	  ct	%ctpr3
	  alc	alcf=0, alct=1
	}
.L150:
	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 A +272 ], %g16
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
	.global	A
	.type	A, #object
	.size	A, 0x800
	.align	16
A:
	.skip	0x800
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
