	.file	"cm_vect.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	matrix_mul_vect
	.type	matrix_mul_vect, #function
	.align	8
matrix_mul_vect:

	{
	  setwd	wsz = 0x9, nfx = 0x1, dbl = 0x1
	  return	%ctpr3
	  adds,0,sm	0x0, 0x0, %r6
	  adds,1	0x0, 0x0, %r14
	  adds,2,sm	0x0, 0x0, %r15
	  addd,3,sm	0x0, _f64,_lts1 0x20ff2000000000, %r10
	  adds,4,sm	0x0, 0x0, %r9
	}
	{
	  cmpbsb,0	0x0, %r0, %pred1
	  cmpbsb,1,sm	%r6, %r0, %pred2
	  subs,2,sm	%r0, %r6, %g16
	}
	{
	  cmpbsb,0,sm	%g16, _f32s,_lts0 0x7fffffff, %pred3
	  shld,1,sm	%r14, 0x2, %r8
	  adds,2,sm	0x0, 0x0, %r12 ? %pred1
	  pass	%pred1, @p0
	  pass	%pred2, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred4
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred2
	}
	{
	  merges,1,sm	%g16, _f32s,_lts0 0x7fffffff, %r16, ~%pred3 ? %pred2
	  adds,2	0x1, 0x0, %r16 ? %pred4
	}
	{
	  ct	%ctpr3 ? ~%pred1
	  cmplsb,0,sm	0x0, %r16, %pred0
	  stw,2	%r1, %r8, %r15 ? %pred1
	}
.L7:
	{
	  merges,0,sm	0x1, %r16, %r11, %pred0
	}
.L91:
	{
	  setwd	wsz = 0x1d, nfx = 0x1, dbl = 0x1
	  setbn	rsz = 0x13, rbs = 0x9, rcur = 0x0
	  disp	%ctpr3, .L80
	  scls,0	0xd, 0xa, %r5
	  insfd,1	%r10, _f32s,_lts1 0x8800, %r11, %g16
	  adds,2	%r12, %r6, %r7
	}
	{
	  disp	%ctpr1, .L153
	  rwd,0	%g16, %lsr
	  adds,1,sm	0x0, 0x0, %b[6]
	  adds,2	%r6, %r16, %r13
	  adds,3,sm	0x0, %r9, %b[12]
	}
	{
	  rwd,0	%r11, %lsr1
	  adds,1,sm	%b[6], 0x1, %g16
	  adds,2,sm	%r6, %b[6], %b[8]
	}
	{
	  adds,1,sm	%g16, 0x1, %g17
	  adds,2,sm	%r7, %b[6], %b[5]
	}
	{
	  adds,0,sm	%r7, %g16, %b[3]
	  adds,1,sm	%r6, %g16, %b[6]
	  shld,2,sm	%b[8], 0x1, %b[19]
	  adds,3,sm	%g16, 0x2, %g18
	  adds,4,sm	%g16, 0x3, %g16
	}
	{
	  shld,0,sm	%b[3], 0x1, %b[20]
	  shld,1,sm	%b[5], 0x1, %b[22]
	  shld,2,sm	%b[6], 0x1, %b[17]
	  adds,3,sm	%r7, %g17, %b[1]
	  adds,4,sm	%r6, %g17, %b[4]
	  adds,5,sm	%r6, %g18, %b[2]
	}
	{
	  ldh,0,sm	%r3, %b[19], %b[9], mas=0x4
	  adds,1,sm	%r7, %g18, %b[39]
	  adds,2,sm	%r6, %g16, %b[0]
	  shld,3,sm	%b[4], 0x1, %b[15]
	  shld,4,sm	%b[1], 0x1, %b[18]
	  shld,5,sm	%b[2], 0x1, %b[13]
	}
	{
	  ldh,0,sm	%r2, %b[22], %b[27], mas=0x4
	  shld,1,sm	%b[39], 0x1, %b[16]
	  adds,2,sm	%r7, %g16, %b[37]
	  ldh,3,sm	%r3, %b[17], %b[7], mas=0x4
	  adds,4,sm	%g16, 0x1, %b[36]
	}
	{
	  ldh,0,sm	%r2, %b[20], %b[25], mas=0x4
	  shld,1,sm	%b[0], 0x1, %b[11]
	  ldh,3,sm	%r3, %b[15], %b[5], mas=0x4
	}
	{
	  ldh,0,sm	%r2, %b[18], %b[23], mas=0x4
	  ldh,3,sm	%r3, %b[13], %b[3], mas=0x4
	}
	{
	  ldh,0,sm	%r2, %b[16], %b[21], mas=0x4
	}
	{
	  getfs,1,sm	%b[9], %r5, %b[32]
	}
	{
	  getfs,0,sm	%b[27], %r5, %g16
	  getfs,1,sm	%b[7], %r5, %b[30]
	}
	{
	  muls,0,sm	%g16, %b[32], %b[26]
	  getfs,1,sm	%b[5], %r5, %b[28]
	  getfs,2,sm	%b[25], %r5, %g17
	}
	{
	  muls,0,sm	%g17, %b[30], %b[24]
	}
.L153:
	{
	  loop_mode
	  rbranch	.L1036
	  getfs,1,sm	%b[23], %r5, %b[29]
	  ldh,2	%r2, %b[22], %b[27], mas=0x3 ? %pcnt0
	  ldh,3,sm	%r3, %b[11], %b[1], mas=0x4 ? %pcnt4
	  shld,4,sm	%b[37], 0x1, %b[14]
	  ldh,5	%r3, %b[19], %b[9], mas=0x3 ? %pcnt0
	}
.L1044:
	{
	  loop_mode
	  muls,0,sm	%b[29], %b[28], %b[22]
	  adds,1,sm	%b[36], 0x1, %b[34]
	  adds,2,sm	%r7, %b[36], %b[35]
	  ldh,3,sm	%r2, %b[14], %b[19], mas=0x4 ? %pcnt4
	  adds,4,sm	%r6, %b[36], %b[38]
	  adds,5,sm	%b[12], %b[26], %b[10]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  shld,3,sm	%b[38], 0x1, %b[9]
	  getfs,4,sm	%b[3], %r5, %b[26]
	  stw,5	%r1, %r8, %b[10]
	}

	{
	  setwd	wsz = 0x9, nfx = 0x1, dbl = 0x1
	  disp	%ctpr2, .L91
	  addd,0	0x0, 0x0, %g16
	  adds,1,sm	0x0, %b[12], %r9
	  adds,2	0x0, %r13, %r6
	}
	{
	  cmpbsb,0	%r13, %r0, %pred0
	  cmpbsb,1,sm	%r6, %r0, %pred1
	  mmurw,2	%g16, %dam_inv
	  addd,3,sm	0x0, _f64,_lts0 0x20ff2000000000, %r10
	}
	{
	  subs,0,sm	%r0, %r6, %g16
	  pass	%pred0, @p0
	  pass	%pred1, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred2
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred1
	}
	{
	  cmpbsb,0,sm	%g16, _f32s,_lts0 0x7fffffff, %pred3
	  adds,1	0x1, 0x0, %r16 ? %pred2
	}
	{
	  ct	%ctpr3 ? ~%pred0
	  merges,0,sm	%g16, _f32s,_lts0 0x7fffffff, %r16, ~%pred3 ? %pred1
	}
	{
	  cmplsb,0,sm	0x0, %r16, %pred1
	}
	{
	  ct	%ctpr2 ? %pred0
	  merges,0,sm	0x1, %r16, %r11, %pred1 ? %pred0
	}
.L80:
	{
	  disp	%ctpr1, .L7
	  adds,0	%r14, 0x1, %r14
	  adds,1,sm	0x0, 0x0, %r6
	  adds,2,sm	%r0, %r12, %r12
	  addd,3,sm	0x0, _f64,_lts0 0x20ff2000000000, %r10
	  adds,4,sm	0x0, 0x0, %r9
	}
	{
	  return	%ctpr3
	  cmpbsb,0	%r14, %r0, %pred1
	  cmpbsb,1,sm	%r6, %r0, %pred2
	  subs,2,sm	%r0, %r6, %g16
	}
	{
	  cmpbsb,0,sm	%g16, _f32s,_lts0 0x7fffffff, %pred3
	  shld,1,sm	%r14, 0x2, %r8
	  pass	%pred1, @p0
	  pass	%pred2, @p1
	  landp	@p0, ~@p1, @p4
	  pass	@p4, %pred4
	  landp	@p0, @p1, @p5
	  pass	@p5, %pred2
	}
	{
	  merges,0,sm	%g16, _f32s,_lts0 0x7fffffff, %r16, ~%pred3 ? %pred2
	  adds,1	0x1, 0x0, %r16 ? %pred4
	  stw,2	%r1, %r8, %r15 ? %pred1
	}
	{
	  ct	%ctpr3 ? ~%pred1
	  cmplsb,0,sm	0x0, %r16, %pred0
	}
	{
	  ct	%ctpr1 ? %pred1
	}
.L1036:
	{
	  getfs,0,sm	%b[27], %r5, %b[33]
	  getfs,1,sm	%b[9], %r5, %b[32]
	}
	{
	  nop 4
	  muls,0,sm	%b[33], %b[32], %b[26]
	}
	{
	  ibranch	.L1044
	}
	.size	matrix_mul_vect, .- matrix_mul_vect
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x4, rcur = 0x0
	  disp	%ctpr1, matrix_mul_vect
	  getsp,0	_f32s,_lts1 0xffffffe0, %r2
	}
	{
	  addd,0	0xa, 0x0, %b[0]
	  addd,1	0x0, [ _f64,_lts0 AA ], %b[2]
	  addd,2	0x0, [ _f64,_lts2 BB ], %b[3]
	}
	{
	  nop 2
	  addd,0	0x0, [ _f64,_lts0 CC ], %b[1]
	}
.LCS.1:
	{
	  call	%ctpr1, wbs = 0x4
	}
	{
	  nop 4
	  return	%ctpr3
	  ldw,0	0x0, [ _f64,_lts0 CC +12 ], %r3
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
	.global	AA
	.type	AA, #object
	.size	AA, 0xc8
	.align	16
AA:
	.skip	0xc8
	.global	BB
	.type	BB, #object
	.size	BB, 0xc8
	.align	16
BB:
	.skip	0xc8
	.global	CC
	.type	CC, #object
	.size	CC, 0x190
	.align	16
CC:
	.skip	0x190
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
