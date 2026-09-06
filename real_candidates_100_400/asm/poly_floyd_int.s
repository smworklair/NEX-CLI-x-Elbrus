	.file	"poly_floyd_int.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  addd,1,sm	0x0, 0x0, %r3
	  addd,4,sm	0x0, 0x0, %r0
	}
	{
	  ldw,2	0x0, [ _f64,_lts0 path +36 ], %r39
	  ldw,3	0x0, [ _f64,_lts2 path +40 ], %r38
	}
	{
	  ldw,2	0x0, [ _f64,_lts2 path +32 ], %r36
	}
	{
	  rwd,0	_f64,_lts0 0x1fe0002000000006, %lsr
	  ldw,2	0x0, [ _f64,_lts2 path +56 ], %r37
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +48 ], %r35
	  ldw,2	0x0, [ _f64,_lts2 path +52 ], %r34
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +72 ], %r33
	  ldw,2	0x0, [ _f64,_lts2 path +44 ], %r32
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +64 ], %r31
	  ldw,2	0x0, [ _f64,_lts2 path +68 ], %r30
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +88 ], %r29
	  ldw,2	0x0, [ _f64,_lts2 path +60 ], %r28
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +80 ], %r27
	  ldw,2	0x0, [ _f64,_lts2 path +84 ], %r26
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +104 ], %r25
	  ldw,2	0x0, [ _f64,_lts2 path +76 ], %r24
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +96 ], %r23
	  ldw,2	0x0, [ _f64,_lts2 path +100 ], %r22
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +116 ], %r21
	  ldw,2	0x0, [ _f64,_lts2 path +92 ], %r20
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +108 ], %r19
	  ldw,2	0x0, [ _f64,_lts2 path +112 ], %r18
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +120 ], %r17
	  ldw,2	0x0, [ _f64,_lts2 path +124 ], %r16
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +128 ], %r15
	  ldw,2	0x0, [ _f64,_lts2 path +132 ], %r14
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +136 ], %r13
	  ldw,2	0x0, [ _f64,_lts2 path +140 ], %r12
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path ], %r11
	  ldw,2	0x0, [ _f64,_lts2 path +4 ], %r10
	  ldb,3,sm	0x0, [ _f64,_lts0 path ], %empty, mas=0x20
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +8 ], %r9
	  ldw,2	0x0, [ _f64,_lts2 path +12 ], %r8
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +16 ], %r7
	  ldw,2	0x0, [ _f64,_lts2 path +20 ], %r6
	}
	{
	  ldw,0	0x0, [ _f64,_lts0 path +24 ], %r5
	  ldw,2	0x0, [ _f64,_lts2 path +28 ], %r4
	}
.L2705:
	{
	  loop_mode
	  disp	%ctpr1, .L2705
	  ldw,0	%r0, [ _f64,_lts0 path ], %g16
	  addd,1	0x18, %r0, %g18
	  ldd,2	%r3, [ _f64,_lts0 path ], %g17
	}
	{
	  loop_mode
	  ldd,0	%r3, [ _f64,_lts0 path +8 ], %g19
	  addd,1,sm	0x4, %r0, %g21
	  ldd,2	%r3, [ _f64,_lts2 path +16 ], %g20
	  addd,3,sm	0x18, %r3, %g22
	}
	{
	  loop_mode
	  ldw,0	%r0, [ _f64,_lts0 path +24 ], %g23
	  ldw,2	%r0, [ _f64,_lts2 path +48 ], %g24
	}
	{
	  loop_mode
	  ldw,0	%r0, [ _f64,_lts0 path +72 ], %g25
	  ldw,2	%r0, [ _f64,_lts2 path +96 ], %g26
	}
	{
	  loop_mode
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g27
	  ldb,2,sm	%g22, [ _f64,_lts2 path ], %empty, mas=0x20
	  ldb,3,sm	%g21, [ _f64,_lts2 path ], %empty, mas=0x20
	}
	{
	  loop_mode
	  adds,1	%g16, %g17, %g16
	  getfd,4	%g17, _f16s,_lts0lo 0x820, %g17
	}
	{
	  loop_mode
	  cmplsb,0	%r11, %g16, %pred0
	  getfd,1	%g19, _f16s,_lts0lo 0x820, %g21
	  getfd,2	%g20, _f16s,_lts0lo 0x820, %g22
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r11 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path ], %r11
	  ldw,5	%r0, [ _f64,_lts0 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r10, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r10 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +4 ], %r10
	  ldw,5	%r0, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g16, %g19, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r9, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r9 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +8 ], %r9
	  ldw,5	%r0, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g16, %g21, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r8, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r8 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +12 ], %r8
	  ldw,5	%r0, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g16, %g20, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r7, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r7 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +16 ], %r7
	  ldw,5	%r0, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g16, %g22, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r6, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r6 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +20 ], %r6
	  ldw,5	%r3, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g23, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r5, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r5 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +24 ], %r5
	  ldw,5	%g18, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +4 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r4, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r4 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +28 ], %r4
	  ldw,5	%g18, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +8 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r36, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r36 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +32 ], %r36
	  ldw,5	%g18, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +12 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r39, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r39 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +36 ], %r39
	  ldw,5	%g18, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +16 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r38, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r38 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +40 ], %r38
	  ldw,5	%g18, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +20 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r32, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r32 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +44 ], %r32
	  ldw,5	%r3, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g24, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r35, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r35 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +48 ], %r35
	  ldw,5	%r0, [ _f64,_lts0 path +48 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +4 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r34, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r34 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +52 ], %r34
	  ldw,5	%r0, [ _f64,_lts2 path +48 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +8 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r37, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r37 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +56 ], %r37
	  ldw,5	%r0, [ _f64,_lts2 path +48 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +12 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r28, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r28 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +60 ], %r28
	  ldw,5	%r0, [ _f64,_lts2 path +48 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +16 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r31, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r31 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +64 ], %r31
	  ldw,5	%r0, [ _f64,_lts2 path +48 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +20 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r30, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r30 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +68 ], %r30
	  ldw,5	%r3, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g25, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r33, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r33 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +72 ], %r33
	  ldw,5	%r0, [ _f64,_lts0 path +72 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +4 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r24, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r24 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +76 ], %r24
	  ldw,5	%r0, [ _f64,_lts2 path +72 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +8 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r27, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r27 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +80 ], %r27
	  ldw,5	%r0, [ _f64,_lts2 path +72 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +12 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r26, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r26 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +84 ], %r26
	  ldw,5	%r0, [ _f64,_lts2 path +72 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +16 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r29, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r29 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +88 ], %r29
	  ldw,5	%r0, [ _f64,_lts2 path +72 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +20 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r20, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r20 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +92 ], %r20
	  ldw,5	%r3, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g26, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r23, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r23 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +96 ], %r23
	  ldw,5	%r0, [ _f64,_lts0 path +96 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r3, [ _f64,_lts0 path +4 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g16, %g17, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r22, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r22 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +100 ], %r22
	  ldw,5	%r3, [ _f64,_lts2 path +8 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +96 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r25, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r25 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +104 ], %r25
	  ldw,5	%r3, [ _f64,_lts2 path +12 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +96 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r19, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r19 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +108 ], %r19
	  ldw,5	%r3, [ _f64,_lts2 path +16 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +96 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r18, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r18 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +112 ], %r18
	  ldw,5	%r3, [ _f64,_lts2 path +20 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +96 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r21, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r21 ? ~%pred0
	}
	{
	  loop_mode
	  nop 4
	  stw,2	0x0, [ _f64,_lts0 path +116 ], %r21
	  ldw,5	%r3, [ _f64,_lts2 path ], %g16
	}
	{
	  loop_mode
	  adds,0	%g27, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r17, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r17 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +120 ], %r17
	  ldw,5	%r3, [ _f64,_lts2 path +4 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r16, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r16 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +124 ], %r16
	  ldw,5	%r3, [ _f64,_lts2 path +8 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r15, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r15 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +128 ], %r15
	  ldw,5	%r3, [ _f64,_lts2 path +12 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r14, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r14 ? ~%pred0
	}
	{
	  loop_mode
	  stw,2	0x0, [ _f64,_lts0 path +132 ], %r14
	  ldw,5	%r3, [ _f64,_lts2 path +16 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g17
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r13, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r13 ? ~%pred0
	}
	{
	  loop_mode
	  addd,0,sm	0x18, %r3, %r3
	  stw,2	0x0, [ _f64,_lts0 path +136 ], %r13
	  ldw,5	%r3, [ _f64,_lts2 path +20 ], %g16
	}
	{
	  loop_mode
	  nop 4
	  ldw,0	%r0, [ _f64,_lts0 path +120 ], %g17
	  addd,1,sm	0x4, %r0, %r0
	}
	{
	  loop_mode
	  adds,0	%g17, %g16, %g16
	}
	{
	  loop_mode
	  cmplsb,0	%r12, %g16, %pred0
	}
	{
	  loop_mode
	  adds,0	0x0, %g16, %r12 ? ~%pred0
	}
	{
	  loop_mode
	  ct	%ctpr1 ? %NOT_LOOP_END
	  alc	alcf=1, alct=1
	  stw,2	0x0, [ _f64,_lts0 path +140 ], %r12
	}

	{
	  nop 4
	  ldw,0	0x0, [ _f64,_lts0 path +56 ], %g16
	}
	{
	  ct	%ctpr3
	  sxt,3	0x2, %g16, %r0
	}
	.size	main, .- main
	.section .bss
	.global	path
	.type	path, #object
	.size	path, 0x90
	.align	16
path:
	.skip	0x90
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
