	.file	"cm_mul.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	matrix_mul_matrix
	.type	matrix_mul_matrix, #function
	.align	8
matrix_mul_matrix:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x1
	  return	%ctpr3
	  adds,0	0x0, 0x0, %r15
	  adds,1,sm	0x0, 0x0, %r14
	}
	{
	  cmpbsb,0	0x0, %r0, %pred0
	}
	{
	  nop 1
	  adds,0,sm	0x0, 0x0, %r13 ? %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L7:
	{
	  adds,0	0x0, 0x0, %r11
	  adds,1	0x0, 0x0, %r10
	  adds,2	0x0, 0x0, %r9
	}
	{
	  adds,0	%r13, %r11, %g16
	  subs,1,sm	%r0, %r10, %r5
	}
	{
	  shld,0	%g16, 0x2, %r6
	}
.L13:
	{
	  stw,2	%r1, %r6, %r14
	}
.L120:
	{
	  disp	%ctpr3, .L104
	  muls,0	%r10, %r0, %g16
	  cmpbsb,1	%r10, %r0, %pred0
	  adds,2	%r13, %r10, %r8
	  cmpbsb,3,sm	%r5, _f32s,_lts0 0x7fffffff, %pred1
	  addd,4	0x0, _f64,_lts1 0x20ff2000000000, %g17
	}
	{
	  disp	%ctpr1, .L181
	  adds,0	0x1, 0x0, %g18 ? ~%pred0
	  merges,1,sm	%r5, _f32s,_lts0 0x7fffffff, %g18, ~%pred1 ? %pred0
	  scls,2	0xd, 0xa, %r5
	}
	{
	  cmplsb,0,sm	0x0, %g18, %pred0
	  adds,1	%r10, %g18, %r12
	}
	{
	  merges,0,sm	0x1, %g18, %g18, %pred0
	}
	{
	  setwd	wsz = 0x1e, nfx = 0x1, dbl = 0x1
	  setbn	rsz = 0x15, rbs = 0x8, rcur = 0x0
	  insfd,0	%g17, _f32s,_lts1 0x8800, %g18, %g17
	}
	{
	  adds,0,sm	%r8, 0x1, %b[40]
	  adds,1,sm	0x0, 0x0, %b[10]
	  adds,2,sm	%r8, 0x0, %b[42]
	  adds,3,sm	%r8, 0x2, %b[38]
	  adds,4,sm	%r8, 0x3, %b[36]
	  adds,5,sm	0x0, %r9, %b[14]
	}
	{
	  rwd,0	%g17, %lsr
	  adds,1	%r11, %g16, %r7
	  adds,2,sm	%r0, %b[10], %g16
	  adds,3,sm	%r8, 0x4, %b[34]
	  adds,4,sm	0x4, 0x1, %b[20]
	}
	{
	  rwd,0	%g18, %lsr1
	  adds,1,sm	%r7, %b[10], %b[9]
	  adds,2,sm	%r7, %g16, %b[7]
	}
	{
	  adds,1,sm	%r0, %g16, %g16
	  shld,2,sm	%b[9], 0x1, %b[31]
	  shld,3,sm	%b[42], 0x1, %b[9]
	}
	{
	  adds,0,sm	%r7, %g16, %b[5]
	  shld,1,sm	%b[7], 0x1, %b[29]
	  shld,2,sm	%b[40], 0x1, %b[7]
	  ldh,3,sm	%r2, %b[9], %b[39], mas=0x4
	}
	{
	  ldh,0,sm	%r3, %b[31], %b[19], mas=0x4
	  shld,1,sm	%b[5], 0x1, %b[27]
	  adds,2,sm	%r0, %g16, %g16
	  shld,4,sm	%b[38], 0x1, %b[5]
	}
	{
	  ldh,0,sm	%r3, %b[29], %b[17], mas=0x4
	  adds,1,sm	%r0, %g16, %g17
	  adds,2,sm	%r7, %g16, %b[3]
	  ldh,3,sm	%r2, %b[7], %b[37], mas=0x4
	}
	{
	  ldh,0,sm	%r3, %b[27], %b[15], mas=0x4
	  adds,1,sm	%r7, %g17, %b[1]
	  adds,2,sm	%r0, %g17, %g16
	  ldh,3,sm	%r2, %b[5], %b[35], mas=0x4
	}
	{
	  shld,1,sm	%b[3], 0x1, %b[25]
	  shld,2,sm	%b[36], 0x1, %b[3]
	}
	{
	  adds,0,sm	%r7, %g16, %b[43]
	  getfs,1,sm	%b[39], %r5, %b[26]
	  adds,2,sm	%r0, %g16, %b[42]
	  shld,4,sm	%b[1], 0x1, %b[23]
	}
	{
	  ldh,0,sm	%r3, %b[25], %b[13], mas=0x4
	  getfs,1,sm	%b[19], %r5, %g16
	  shld,2,sm	%b[43], 0x1, %b[21]
	  ldh,3,sm	%r2, %b[3], %b[33], mas=0x4
	}
	{
	  muls,0,sm	%b[26], %g16, %b[38]
	  getfs,1,sm	%b[17], %r5, %g17
	  getfs,2,sm	%b[37], %r5, %b[24]
	  ldh,3,sm	%r3, %b[23], %b[11], mas=0x4
	}
	{
	  muls,0,sm	%b[24], %g17, %b[36]
	  getfs,2,sm	%b[15], %r5, %b[28]
	}
.L181:
	{
	  loop_mode
	  rbranch	.L981
	  getfs,0,sm	%b[35], %r5, %b[22]
	  ldh,2	%r3, %b[31], %b[19], mas=0x3 ? %pcnt0
	  shld,4,sm	%b[34], 0x1, %b[1]
	  ldh,5	%r2, %b[9], %b[39], mas=0x3 ? %pcnt0
	}
.L989:
	{
	  loop_mode
	  ldh,0,sm	%r3, %b[21], %b[9], mas=0x4 ? %pcnt5
	  muls,1,sm	%b[22], %b[28], %b[34]
	  adds,2,sm	%r7, %b[42], %b[41]
	  ldh,3,sm	%r2, %b[1], %b[31], mas=0x4 ? %pcnt4
	  adds,4,sm	%r0, %b[42], %b[40]
	  adds,5,sm	%b[14], %b[38], %b[12]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  shld,0,sm	%b[41], 0x1, %b[19]
	  adds,2,sm	%b[20], 0x1, %b[18]
	  adds,3,sm	%r8, %b[20], %b[32]
	  getfs,4,sm	%b[13], %r5, %b[26]
	  stw,5	%r1, %r6, %b[12]
	}

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x1
	  disp	%ctpr2, .L120
	  addd,0	0x0, 0x0, %g16
	  adds,1,sm	0x0, %b[14], %r9
	}
	{
	  cmpbsb,0	%r12, %r0, %pred0
	  adds,1	0x0, %r12, %r10
	  mmurw,2	%g16, %dam_inv
	}
	{
	  nop 1
	  subs,0,sm	%r0, %r10, %r5
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
	{
	  ct	%ctpr2 ? %pred0
	}
.L104:
	{
	  disp	%ctpr1, .L13
	  adds,0	%r11, 0x1, %r11
	  adds,1,sm	0x0, 0x0, %r10
	  adds,2,sm	0x0, 0x0, %r9
	}
	{
	  cmpbsb,0	%r11, %r0, %pred0
	  subs,1,sm	%r0, %r10, %r5
	}
	{
	  adds,0	%r13, %r11, %g16 ? %pred0
	}
	{
	  nop 1
	  shld,0,sm	%g16, 0x2, %r6
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  disp	%ctpr1, .L7
	  adds,0	%r15, 0x1, %r15
	  adds,1,sm	%r0, %r13, %r13
	}
	{
	  nop 2
	  return	%ctpr3
	  cmpbsb,0	%r15, %r0, %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
	{
	  ct	%ctpr1 ? %pred0
	}
.L981:
	{
	  getfs,0,sm	%b[19], %r5, %b[32]
	  getfs,1,sm	%b[39], %r5, %b[26]
	}
	{
	  nop 4
	  muls,0,sm	%b[26], %b[32], %b[38]
	}
	{
	  ibranch	.L989
	}
	.size	matrix_mul_matrix, .- matrix_mul_matrix
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x4, rcur = 0x0
	  disp	%ctpr1, matrix_mul_matrix
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
