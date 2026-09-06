	.file	"poly_gramschmidt.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x10, rcur = 0x0
	  getsp,0	_f32s,_lts1 0xfffffff0, %r2
	  addd,1,sm	0x0, 0x0, %r14
	  addd,2	0x0, 0x0, %r9
	  adds,3	0x0, 0x0, %r8
	  addd,4	0x0, 0x0, %r11
	  addd,5,sm	0x0, 0x0, %r13
	}
	{
	  adds,0,sm	0x0, 0x0, %r12
	  addd,1	0x0, 0x0, %r10
	  addd,4	0xc, 0x0, %r7
	}
	{
	  ldb,2,sm	0x0, [ _f64,_lts2 A +96 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts2 A +96 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts2 A +288 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +192 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts2 A +288 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts0 A +192 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +480 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts2 A +384 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts0 A +480 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +384 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts2 A +672 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts2 A +672 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +576 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts0 A +576 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts2 A +864 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +768 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts0 A +768 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts2 A +864 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	0x0, [ _f64,_lts0 A +1056 ], %empty, mas=0x20
	  ldb,2,sm	0x0, [ _f64,_lts0 A +1056 ], %empty, mas=0x20
	  ldb,3,sm	0x0, [ _f64,_lts2 A +960 ], %empty, mas=0x20
	  ldb,5,sm	0x0, [ _f64,_lts2 A +960 ], %empty, mas=0x20
	}
.L14:
	{
	  disp	%ctpr2, .L78
	  ldd,0	%r11, [ _f64,_lts0 A ], %r3
	  addd,1,sm	0x8, %r11, %r5
	  ldd,2	%r11, [ _f64,_lts2 A +96 ], %r4
	}
	{
	  disp	%ctpr1, sqrt
	  ldd,0	%r11, [ _f64,_lts0 A +192 ], %r6
	  ldd,2	%r11, [ _f64,_lts2 A +288 ], %r15
	}
	{
	  ldd,0	%r11, [ _f64,_lts0 A +384 ], %r16
	  ldd,2	%r11, [ _f64,_lts2 A +480 ], %r17
	  ldb,3,sm	%r5, [ _f64,_lts0 A +384 ], %empty, mas=0x20
	  ldb,5,sm	%r5, [ _f64,_lts2 A +480 ], %empty, mas=0x20
	}
	{
	  ldd,0	%r11, [ _f64,_lts0 A +576 ], %r18
	  ldd,2	%r11, [ _f64,_lts2 A +672 ], %r19
	  ldb,3,sm	%r5, [ _f64,_lts0 A +576 ], %empty, mas=0x20
	  ldb,5,sm	%r5, [ _f64,_lts2 A +672 ], %empty, mas=0x20
	}
	{
	  ldd,0	%r11, [ _f64,_lts0 A +768 ], %r20
	  ldd,2	%r11, [ _f64,_lts2 A +864 ], %r21
	  ldb,3,sm	%r5, [ _f64,_lts0 A +768 ], %empty, mas=0x20
	  ldb,5,sm	%r5, [ _f64,_lts2 A +864 ], %empty, mas=0x20
	}
	{
	  ldd,0	%r11, [ _f64,_lts0 A +960 ], %r22
	  fmuld,1	%r3, %r3, %r3
	  ldd,2	%r11, [ _f64,_lts2 A +1056 ], %r23
	  ldb,3,sm	%r5, [ _f64,_lts2 A +1056 ], %empty, mas=0x20
	  ldb,5,sm	%r5, [ _f64,_lts0 A +960 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%r5, [ _f64,_lts0 A +288 ], %empty, mas=0x20
	  ldb,2,sm	%r5, [ _f64,_lts2 A +960 ], %empty, mas=0x20
	  ldb,3,sm	%r5, [ _f64,_lts0 A +288 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%r5, [ _f64,_lts0 A +192 ], %empty, mas=0x20
	  fmuld,1	%r4, %r4, %r4
	  ldb,2,sm	%r5, [ _f64,_lts2 A +96 ], %empty, mas=0x20
	  ldb,3,sm	%r5, [ _f64,_lts0 A +192 ], %empty, mas=0x20
	  ldb,5,sm	%r5, [ _f64,_lts2 A +96 ], %empty, mas=0x20
	}
	{
	  ldb,0,sm	%r5, [ _f64,_lts0 A ], %empty, mas=0x20
	  ldb,2,sm	%r5, [ _f64,_lts2 A +864 ], %empty, mas=0x20
	  ldb,3,sm	%r5, [ _f64,_lts0 A ], %empty, mas=0x20
	}
	{
	  faddd,0	0x0, %r3, %r3
	  ldb,2,sm	%r5, [ _f64,_lts0 A +672 ], %empty, mas=0x20
	  ldb,3,sm	%r5, [ _f64,_lts2 A +768 ], %empty, mas=0x20
	}
	{
	  ldb,2,sm	%r5, [ _f64,_lts0 A +480 ], %empty, mas=0x20
	  ldb,3,sm	%r5, [ _f64,_lts2 A +576 ], %empty, mas=0x20
	}
	{
	  nop 1
	  fmuld,0	%r6, %r6, %r6
	  ldb,2,sm	%r5, [ _f64,_lts0 A +384 ], %empty, mas=0x20
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r15, %r15, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r6, %r3
	}
	{
	  nop 1
	  fmuld,0	%r16, %r16, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r17, %r17, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r18, %r18, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r19, %r19, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r20, %r20, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r21, %r21, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r22, %r22, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r23, %r23, %r4
	}
	{
	  nop 3
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 3
	  faddd,0	%r3, %r4, %r2
	}
	{
	  fcmpledb,0	0x0, %r2, %pred0
	}
	{
	  nop 2
	}
	{
	  addd,0,sm	0x0, %r2, %b[0] ? ~%pred0
	}
	{
	  ct	%ctpr2 ? %pred0
	}
	{
	  call	%ctpr1, wbs = 0x10 ? ~%pred0
	}
	{
	  nop 1
	  disp	%ctpr3, .L59
	  addd,3	0x0, %b[0], %r0 ? ~%pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L78:
	{
	  nop 7
	  fsqrtid,5	%r2, %r3
	}
	{
	  nop 2
	}
	{
	  nop 7
	  fsqrttd,5	%r2, %r3, %r0
	}
	nop
.L59:
	{
	  adds,0	%r12, 0x1, %r6
	  ldd,3	%r11, [ _f64,_lts0 A +768 ], %r3
	  ldd,5	%r11, [ _f64,_lts2 A +864 ], %r15
	}
	{
	  sxt,0	0x2, %r6, %r18
	  ldd,3	%r11, [ _f64,_lts0 A +960 ], %r16
	  ldd,5	%r11, [ _f64,_lts2 A +1056 ], %r17
	}
	{
	  shld,0,sm	%r18, 0x3, %r2
	  ldd,3	%r11, [ _f64,_lts0 A +576 ], %r19
	  ldd,5	%r11, [ _f64,_lts2 A +672 ], %r20
	}
	{
	  ldd,3	%r11, [ _f64,_lts0 A +384 ], %r18
	  ldd,5	%r11, [ _f64,_lts2 A +480 ], %r21
	}
	{
	  ldd,3	%r11, [ _f64,_lts0 A +192 ], %r22
	  ldd,5	%r11, [ _f64,_lts2 A +288 ], %r23
	}
	{
	  ldb,0,sm	%r2, [ _f64,_lts0 A ], %empty, mas=0x20
	  ldd,3	%r11, [ _f64,_lts0 A ], %r24
	  ldd,5	%r11, [ _f64,_lts2 A +96 ], %r25
	}
	{
	  addd,1,sm	%r11, [ _f64,_lts0 Q ], %r5
	  addd,2	%r13, [ _f64,_lts2 R ], %r4
	  fdivd,5	%r17, %r0, %r17
	}
	{
	  std,2	%r14, [ _f64,_lts0 R ], %r0
	}
	{
	  nop 1
	  fdivd,5	%r16, %r0, %r16
	}
	{
	  nop 1
	  fdivd,5	%r15, %r0, %r15
	}
	{
	  nop 1
	  fdivd,5	%r3, %r0, %r3
	}
	{
	  nop 1
	  fdivd,5	%r20, %r0, %r20
	}
	{
	  nop 1
	  fdivd,5	%r19, %r0, %r19
	}
	{
	  nop 1
	  fdivd,5	%r18, %r0, %r18
	}
	{
	  fdivd,5	%r21, %r0, %r21
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q +1056 ], %r17
	}
	{
	  fdivd,5	%r23, %r0, %r17
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q +960 ], %r16
	}
	{
	  fdivd,5	%r22, %r0, %r16
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q +864 ], %r15
	}
	{
	  fdivd,5	%r25, %r0, %r15
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q +768 ], %r3
	}
	{
	  fdivd,5	%r24, %r0, %r0
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q +672 ], %r20
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +576 ], %r19
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +384 ], %r18
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +480 ], %r21
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +288 ], %r17
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +192 ], %r16
	}
	{
	  nop 1
	  std,5	%r11, [ _f64,_lts0 Q +96 ], %r15
	}
	{
	  std,5	%r11, [ _f64,_lts0 Q ], %r0
	}
.L152:
	{
	  ldisp	%ctpr2, .L1306
	  rwd,0	_f64,_lts0 0xff200000000c, %lsr
	  addd,1	%r2, [ _f64,_lts2 A +192 ], %r0
	  std,2	%r4, %r2, %r10
	  movtd,3	0x0, %r3
	  aaurwd,5	%r7, %aaincr1
	}
	{
	  disp	%ctpr1, .L967
	  rwd,0	%r7, %lsr1
	  addd,1	%r5, _f16s,_lts0lo 0xc0, %r15
	  aaurwd,2	%r0, %aaind1
	  addd,3,sm	0x8, %r2, %r0
	  addd,4,sm	%r2, [ _f64,_lts1 A ], %r16
	  aaurw,5	%r8, %aad0
	}
	{
	  disp	%ctpr1, .L967
	  ldd,0,sm	%r2, [ _f64,_lts0 A ], %r15
	  aaurwd,2	%r15, %aaind2
	  ldd,5,sm	%r5, 0x0, %r17
	}
	{
	  ldb,0,sm	%r0, [ _f64,_lts0 A ], %empty, mas=0x20
	}
	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x10, rcur = 0x0
	}
	{
	  nop 1
	  bap
	  ldd,0,sm	%r16, _f16s,_lts0lo 0x60, %b[2]
	  ldd,2,sm	%r5, _f16s,_lts0lo 0x60, %b[3]
	}
	{
	  nop 7
	  fmuld,0,sm	%r17, %r15, %b[6]
	}
	{
	  nop 5
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L1306:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L967:
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
	  faddd,2,sm	%r3, %b[6], %r3
	}

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x10, rcur = 0x0
	  adds,0	0x0, 0x0, %r15
	}
	{
	  nop 1
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%r15, %aabf0
	}
	{
	  nop 1
	  std,2	%r4, %r2, %r3
	}
	{
	  nop 2
	  movtd,0	%r3, %r0
	}

	{
	  ldisp	%ctpr2, .L1281
	  rwd,0	_f64,_lts0 0x20ef200000000c, %lsr
	  addd,1,sm	%r2, [ _f64,_lts2 A ], %r3
	  aaurwd,2	%r9, %aasti3
	  aaurwd,5	%r7, %aaincr2
	}
	{
	  disp	%ctpr1, .L945
	  rwd,0	%r7, %lsr1
	  addd,1	%r5, _f16s,_lts0lo 0x5a0, %r15
	  aaurwd,2	%r7, %aaincr1
	  addd,4	%r2, [ _f64,_lts1 A +1440 ], %r16
	  aaurw,5	%r8, %aad0
	}
	{
	  disp	%ctpr1, .L945
	  aaurwd,2	%r3, %aad1
	  aaurwd,5	%r16, %aaind2
	}
	{
	  ldd,0,sm	%r5, 0x0, %r15
	  aaurwd,2	%r15, %aaind1
	  ldd,5,sm	%r2, [ _f64,_lts0 A ], %r16
	}
	{
	  setwd	wsz = 0x1c, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0xb, rbs = 0x10, rcur = 0x0
	  ldd,0,sm	%r5, _f16s,_lts1lo 0x60, %r17
	  ldd,2,sm	%r2, [ _f64,_lts2 A +96 ], %r18
	  ldd,3,sm	%r5, _f16s,_lts1hi 0xc0, %r19
	}
	{
	  bap
	  ldd,0,sm	%r2, [ _f64,_lts2 A +192 ], %r20
	  ldd,2,sm	%r5, _f16s,_lts0lo 0x120, %r21
	  ldd,3,sm	%r5, _f16s,_lts0hi 0x180, %r22
	  ldd,5,sm	%r5, _f16s,_lts1lo 0x1e0, %r23
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts0 A +288 ], %r24
	  ldd,2,sm	%r2, [ _f64,_lts2 A +384 ], %r25
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts2 A +480 ], %r26
	  ldd,2,sm	%r5, _f16s,_lts0lo 0x240, %r27
	  ldd,3,sm	%r5, _f16s,_lts0hi 0x2a0, %r28
	  ldd,5,sm	%r5, _f16s,_lts1lo 0x300, %r29
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts0 A +576 ], %r30
	  fmul_subd,1,sm	%r15, %r0, %r16, %b[20]
	  ldd,2,sm	%r2, [ _f64,_lts2 A +672 ], %r31
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts1 A +768 ], %r15
	  fmul_subd,1,sm	%r17, %r0, %r18, %b[18]
	  ldd,2,sm	%r5, _f16s,_lts0lo 0x360, %r16
	  ldd,3,sm	%r5, _f16s,_lts0hi 0x3c0, %b[11]
	  ldd,5,sm	%r3, _f16s,_lts0hi 0x3c0, %b[23]
	}
	{
	  ldd,0,sm	%r2, [ _f64,_lts1 A +864 ], %r17
	  fmul_subd,1,sm	%r19, %r0, %r20, %b[16]
	  ldd,2,sm	%r5, _f16s,_lts0lo 0x420, %b[9]
	  ldd,3,sm	%r3, _f16s,_lts0lo 0x420, %b[21]
	  ldd,5,sm	%r5, _f16s,_lts0hi 0x480, %b[7]
	}
	{
	  ldd,0,sm	%r3, _f16s,_lts0lo 0x480, %b[19]
	  fmul_subd,1,sm	%r21, %r0, %r24, %b[14]
	  ldd,2,sm	%r5, _f16s,_lts0hi 0x4e0, %b[5]
	  ldd,3,sm	%r3, _f16s,_lts0hi 0x4e0, %b[17]
	  fmul_subd,4,sm	%r22, %r0, %r25, %b[12]
	  ldd,5,sm	%r5, _f16s,_lts1lo 0x540, %b[3]
	}
	{
	  ldd,0,sm	%r3, _f16s,_lts0lo 0x540, %b[15]
	  fmul_subd,1,sm	%r23, %r0, %r26, %b[10]
	}
	{
	  fmul_subd,0,sm	%r27, %r0, %r30, %b[8]
	  fmul_subd,1,sm	%r28, %r0, %r31, %b[6]
	}
	{
	  fmul_subd,0,sm	%r29, %r0, %r15, %b[4]
	}
	{
	  nop 5
	  fmul_subd,0,sm	%r16, %r0, %r17, %b[2]
	}
	{
	  ct	%ctpr1
	}
.L1281:
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=2, asz=5, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=1, ind=1, asz=5, abs=0, disp=0
	}
.L945:
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmul_subd,4,sm	%b[11], %r0, %b[23], %b[0]
	  staad,5	%b[20], %aad1[ %aasti3 ]
	  incr,5	%aaincr2
	  movad,1	area=0, ind=0, am=1, be=0, %b[13]
	  movad,3	area=0, ind=0, am=1, be=0, %b[1]
	}

	{
	  setwd	wsz = 0x14, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x10, rcur = 0x0
	  adds,0	0x0, 0x0, %r0
	  adds,1	%r6, 0x1, %r6
	}
	{
	  disp	%ctpr2, disp=0x0
	  cmplsb,0	%r6, 0xc, %pred0
	  addd,1,sm	0x8, %r2, %r2
	  aaurw,2	%r0, %aabf0
	}
	{
	  disp	%ctpr3, .L152
	}
	{
	  nop 1
	  disp	%ctpr2, .L271
	}
	{
	  ct	%ctpr2 ? ~%pred0
	}
	nop
	{
	  ct	%ctpr3 ? %pred0
	}
.L271:
	{
	  disp	%ctpr1, .L14
	  adds,0	%r12, 0x1, %r12
	  addd,1,sm	%r13, _f16s,_lts0lo 0x60, %r13
	  addd,2,sm	%r14, _f16s,_lts0hi 0x68, %r14
	  addd,3,sm	0x8, %r11, %r11
	}
	{
	  nop 3
	  cmplesb,0	%r12, 0xa, %pred0
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  disp	%ctpr2, .L898
	  ldd,0	0x0, [ _f64,_lts0 A +88 ], %r3
	  ldd,2	0x0, [ _f64,_lts2 A +184 ], %r4
	}
	{
	  disp	%ctpr1, sqrt
	  ldd,0	0x0, [ _f64,_lts0 A +280 ], %r5
	  ldd,2	0x0, [ _f64,_lts2 A +376 ], %r6
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +472 ], %r7
	  ldd,2	0x0, [ _f64,_lts2 A +568 ], %r8
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +664 ], %r9
	  ldd,2	0x0, [ _f64,_lts2 A +760 ], %r10
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +856 ], %r11
	  ldd,2	0x0, [ _f64,_lts2 A +952 ], %r12
	}
	{
	  nop 1
	  ldd,0	0x0, [ _f64,_lts0 A +1048 ], %r13
	  fmuld,1	%r3, %r3, %r3
	  ldd,2	0x0, [ _f64,_lts2 A +1144 ], %r14
	}
	{
	  nop 1
	  fmuld,0	%r4, %r4, %r4
	}
	{
	  nop 1
	  faddd,0	0x0, %r3, %r3
	}
	{
	  nop 1
	  fmuld,0	%r5, %r5, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r6, %r6, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r7, %r7, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r8, %r8, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r9, %r9, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r10, %r10, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r11, %r11, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r12, %r12, %r4
	}
	{
	  nop 1
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 1
	  fmuld,0	%r13, %r13, %r5
	}
	{
	  nop 1
	  faddd,0	%r3, %r4, %r3
	}
	{
	  nop 1
	  fmuld,0	%r14, %r14, %r4
	}
	{
	  nop 3
	  faddd,0	%r3, %r5, %r3
	}
	{
	  nop 3
	  faddd,0	%r3, %r4, %r0
	}
	{
	  fcmpledb,0	0x0, %r0, %pred0
	}
	{
	  nop 2
	}
	{
	  addd,0,sm	0x0, %r0, %b[0] ? ~%pred0
	}
	{
	  ct	%ctpr2 ? %pred0
	}
	{
	  call	%ctpr1, wbs = 0x10 ? ~%pred0
	}
	{
	  nop 1
	  disp	%ctpr1, .L788
	  addd,3	0x0, %b[0], %r2 ? ~%pred0
	}
	{
	  ct	%ctpr1 ? ~%pred0
	}
.L898:
	{
	  nop 7
	  fsqrtid,5	%r0, %r3
	}
	{
	  nop 2
	}
	{
	  nop 7
	  fsqrttd,5	%r0, %r3, %r2
	}
	nop
.L788:
	{
	  return	%ctpr3
	  ldd,3	0x0, [ _f64,_lts0 A +856 ], %r3
	  ldd,5	0x0, [ _f64,_lts2 A +1048 ], %r4
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 A +1144 ], %r5
	  ldd,5	0x0, [ _f64,_lts2 A +664 ], %r6
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 A +760 ], %r7
	  ldd,5	0x0, [ _f64,_lts2 A +952 ], %r8
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 A +472 ], %r9
	  ldd,5	0x0, [ _f64,_lts2 A +568 ], %r10
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 A +280 ], %r11
	  ldd,5	0x0, [ _f64,_lts2 A +376 ], %r12
	}
	{
	  ldd,3	0x0, [ _f64,_lts0 A +88 ], %r13
	  ldd,5	0x0, [ _f64,_lts2 A +184 ], %r14
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 A +208 ], %r15
	  fdivd,5	%r5, %r2, %r5
	}
	{
	  std,2	0x0, [ _f64,_lts0 R +1144 ], %r2
	}
	{
	  nop 1
	  fdivd,5	%r4, %r2, %r4
	}
	{
	  nop 1
	  fdivd,5	%r3, %r2, %r3
	}
	{
	  nop 1
	  fdivd,5	%r8, %r2, %r8
	}
	{
	  fdivd,5	%r7, %r2, %r7
	}
	{
	  fdtoistr,0	%r15, %r15
	}
	{
	  nop 1
	  fdivd,5	%r6, %r2, %r6
	}
	{
	  nop 1
	  fdivd,5	%r10, %r2, %r10
	}
	{
	  fdivd,5	%r9, %r2, %r9
	}
	{
	  sxt,3	0x2, %r15, %r0
	  std,5	0x0, [ _f64,_lts0 Q +1144 ], %r5
	}
	{
	  fdivd,5	%r11, %r2, %r5
	}
	{
	  std,5	0x0, [ _f64,_lts0 Q +1048 ], %r4
	}
	{
	  fdivd,5	%r12, %r2, %r4
	}
	{
	  std,5	0x0, [ _f64,_lts0 Q +856 ], %r3
	}
	{
	  fdivd,5	%r14, %r2, %r3
	}
	{
	  std,5	0x0, [ _f64,_lts0 Q +952 ], %r8
	}
	{
	  fdivd,5	%r13, %r2, %r2
	}
	{
	  std,5	0x0, [ _f64,_lts0 Q +760 ], %r7
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +664 ], %r6
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +568 ], %r10
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +472 ], %r9
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +280 ], %r5
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +376 ], %r4
	}
	{
	  nop 1
	  std,5	0x0, [ _f64,_lts0 Q +184 ], %r3
	}
	{
	  ct	%ctpr3
	  std,5	0x0, [ _f64,_lts0 Q +88 ], %r2
	}
	.size	main, .- main
	.section .bss
	.global	A
	.type	A, #object
	.size	A, 0x480
	.align	16
A:
	.skip	0x480
	.global	R
	.type	R, #object
	.size	R, 0x480
	.align	16
R:
	.skip	0x480
	.global	Q
	.type	Q, #object
	.size	Q, 0x480
	.align	16
Q:
	.skip	0x480
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
