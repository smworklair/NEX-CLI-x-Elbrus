	.file	"cm_bitextract.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	matrix_mul_matrix_bitextract
	.type	matrix_mul_matrix_bitextract, #function
	.align	8
matrix_mul_matrix_bitextract:

	{
	  setwd	wsz = 0x9, nfx = 0x1, dbl = 0x1
	  return	%ctpr3
	  adds,0	0x0, 0x0, %r16
	  adds,1,sm	0x0, 0x0, %r15
	}
	{
	  cmpbsb,0	0x0, %r0, %pred0
	}
	{
	  nop 1
	  adds,0,sm	0x0, 0x0, %r14 ? %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
.L7:
	{
	  adds,0	0x0, 0x0, %r12
	  adds,1	0x0, 0x0, %r11
	  adds,2	0x0, 0x0, %r9
	}
	{
	  adds,0	%r14, %r12, %g16
	}
	{
	  shld,0	%g16, 0x2, %r8
	}
.L13:
	{
	  stw,2	%r1, %r8, %r15
	}
.L127:
	{
	  disp	%ctpr3, .L109
	  muls,0	%r9, %r0, %g16
	  cmpbsb,1	%r9, %r0, %pred0
	  subs,2,sm	%r0, %r9, %g17
	  scls,3	0xd, 0xa, %r5
	  addd,4	0x0, _f64,_lts1 0x20ff2000000000, %g18
	  adds,5	0x0, _f16s,_lts0lo 0x1c5, %r7
	}
	{
	  disp	%ctpr1, .L188
	  cmpbsb,0,sm	%g17, _f32s,_lts1 0x7fffffff, %pred1
	  adds,1	0x1, 0x0, %g19 ? ~%pred0
	  adds,2	%r14, %r9, %r10
	  adds,3	0x0, _f16s,_lts0lo 0x102, %r6
	}
	{
	  merges,1,sm	%g17, _f32s,_lts0 0x7fffffff, %g19, ~%pred1 ? %pred0
	}
	{
	  cmplsb,0,sm	0x0, %g19, %pred0
	  adds,1	%r9, %g19, %r13
	}
	{
	  merges,0,sm	0x1, %g19, %g17, %pred0
	}
	{
	  setwd	wsz = 0x2e, nfx = 0x1, dbl = 0x1
	  setbn	rsz = 0x24, rbs = 0x9, rcur = 0x0
	  insfd,0	%g18, _f32s,_lts1 0x8800, %g17, %g18
	}
	{
	  adds,0,sm	%r10, 0x0, %b[14]
	  adds,1	%r12, %g16, %r9
	  adds,2,sm	0x0, 0x0, %b[9]
	  adds,3,sm	0x0, %r11, %b[18]
	  adds,4,sm	0x7, 0x1, %b[71]
	}
	{
	  shld,0,sm	%b[14], 0x1, %b[46]
	  adds,1,sm	%r0, %b[9], %g16
	  adds,2,sm	%r9, %b[9], %b[12]
	}
	{
	  shld,0,sm	%b[12], 0x1, %b[31]
	  adds,1,sm	%r9, %g16, %b[10]
	  adds,2,sm	%r0, %g16, %g16
	  adds,4,sm	%r10, 0x1, %b[12]
	}
	{
	  adds,0,sm	%r9, %g16, %b[8]
	  shld,1,sm	%b[10], 0x1, %b[29]
	  adds,2,sm	%r10, 0x2, %b[10]
	  ldh,3,sm	%r2, %b[46], %b[45], mas=0x4
	  shld,4,sm	%b[12], 0x1, %b[44]
	}
	{
	  ldh,0,sm	%r3, %b[31], %b[15], mas=0x4
	  shld,1,sm	%b[8], 0x1, %b[27]
	  shld,2,sm	%b[10], 0x1, %b[42]
	  ldh,3,sm	%r2, %b[44], %b[43], mas=0x4
	  adds,4,sm	%r0, %g16, %g16
	  adds,5,sm	%r10, 0x3, %b[8]
	}
	{
	  ldh,0,sm	%r3, %b[29], %b[13], mas=0x4
	  adds,4,sm	%r9, %g16, %b[6]
	  adds,5,sm	%r0, %g16, %g16
	}
	{
	  ldh,0,sm	%r3, %b[27], %b[11], mas=0x4
	  adds,1,sm	%r10, 0x4, %b[6]
	  shld,2,sm	%b[8], 0x1, %b[40]
	  ldh,3,sm	%r2, %b[42], %b[41], mas=0x4
	  shld,4,sm	%b[6], 0x1, %b[25]
	  adds,5,sm	%r9, %g16, %b[4]
	}
	{
	  ldh,0,sm	%r2, %b[40], %b[39], mas=0x4
	  adds,1,sm	%r0, %g16, %g16
	  shld,2,sm	%b[6], 0x1, %b[38]
	  ldh,3,sm	%r3, %b[25], %b[9], mas=0x4
	  shld,4,sm	%b[4], 0x1, %b[23]
	  adds,5,sm	%r10, 0x5, %b[4]
	}
	{
	  ldh,0,sm	%r2, %b[38], %b[37], mas=0x4
	  getfs,1,sm	%b[45], %r5, %b[30]
	  adds,2,sm	%r9, %g16, %b[2]
	  ldh,3,sm	%r3, %b[23], %b[7], mas=0x4
	  shld,4,sm	%b[4], 0x1, %b[36]
	}
	{
	  rwd,0	%g18, %lsr
	  getfs,1,sm	%b[15], %r5, %g19
	  shld,2,sm	%b[2], 0x1, %b[21]
	  ldh,3,sm	%r2, %b[36], %b[35], mas=0x4
	  getfs,4,sm	%b[43], %r5, %b[28]
	  adds,5,sm	%r0, %g16, %g16
	}
	{
	  muls,0,sm	%b[30], %g19, %g19
	  getfs,1,sm	%b[13], %r5, %g18
	  adds,2,sm	%r10, 0x6, %b[2]
	  adds,4,sm	%r9, %g16, %b[0]
	  adds,5,sm	%r0, %g16, %g16
	}
	{
	  muls,0,sm	%b[28], %g18, %g18
	  getfs,1,sm	%b[11], %r5, %g20
	  getfs,2,sm	%b[41], %r5, %b[26]
	  ldh,3,sm	%r3, %b[21], %b[5], mas=0x4
	  shld,4,sm	%b[0], 0x1, %b[19]
	  adds,5,sm	%r9, %g16, %b[72]
	}
	{
	  muls,1,sm	%b[26], %g20, %g20
	  shld,2,sm	%b[2], 0x1, %b[34]
	  ldh,3,sm	%r3, %b[19], %b[3], mas=0x4
	  getfs,4,sm	%b[39], %r5, %b[24]
	  adds,5,sm	%r10, 0x7, %b[0]
	}
	{
	  rwd,0	%g17, %lsr1
	  getfs,1,sm	%b[37], %r5, %b[22]
	  adds,2,sm	%r0, %g16, %b[67]
	  shld,4,sm	%b[72], 0x1, %b[17]
	  shld,5,sm	%b[0], 0x1, %b[32]
	}
	{
	  ldh,0,sm	%r2, %b[34], %b[33], mas=0x4
	  getfs,2,sm	%b[7], %r5, %g17
	  getfs,4,sm	%b[9], %r5, %g16
	}
	{
	  muls,0,sm	%b[22], %g17, %b[48]
	  muls,3,sm	%b[24], %g16, %b[50]
	}
	{
	  getfs,0,sm	%g19, %r6, %g16
	  getfs,1,sm	%g19, %r7, %g17
	  getfs,2,sm	%b[5], %r5, %b[47]
	}
	{
	  muls,0,sm	%g16, %g17, %b[68]
	  getfs,1,sm	%g18, %r7, %g18
	  getfs,2,sm	%g18, %r6, %g19
	}
	{
	  nop 1
	  muls,0,sm	%g19, %g18, %b[66]
	  getfs,2,sm	%g20, %r6, %b[59]
	  getfs,5,sm	%g20, %r7, %b[58]
	}
.L188:
	{
	  loop_mode
	  rbranch	.L1021
	  ldh,0,sm	%r3, %b[17], %b[1], mas=0x4 ? %pcnt7
	  adds,1,sm	%b[71], 0x1, %b[69]
	  ldh,2	%r3, %b[31], %b[15], mas=0x3 ? %pcnt0
	  getfs,3,sm	%b[35], %r5, %b[20]
	  muls,4,sm	%b[59], %b[58], %b[64]
	  ldh,5	%r2, %b[46], %b[45], mas=0x3 ? %pcnt0
	}
.L1032:
	{
	  loop_mode
	  adds,0,sm	%r0, %b[67], %b[65]
	  adds,1,sm	%r10, %b[71], %b[72]
	  adds,2,sm	%r9, %b[67], %b[70]
	  ldh,3,sm	%r2, %b[32], %b[31], mas=0x4 ? %pcnt7
	  muls,4,sm	%b[20], %b[47], %b[46]
	  adds,5,sm	%b[18], %b[68], %b[16]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  shld,0,sm	%b[72], 0x1, %b[30]
	  shld,1,sm	%b[70], 0x1, %b[15]
	  getfs,2,sm	%b[3], %r5, %b[45]
	  getfs,3,sm	%b[50], %r7, %b[56]
	  getfs,4,sm	%b[50], %r6, %b[57]
	  stw,5	%r1, %r8, %b[16]
	}

	{
	  setwd	wsz = 0x9, nfx = 0x1, dbl = 0x1
	  disp	%ctpr2, .L127
	  addd,0	0x0, 0x0, %g16
	  adds,1,sm	0x0, %b[18], %r11
	}
	{
	  nop 2
	  cmpbsb,0	%r13, %r0, %pred0
	  adds,1	0x0, %r13, %r9
	  mmurw,2	%g16, %dam_inv
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
	{
	  ct	%ctpr2 ? %pred0
	}
.L109:
	{
	  disp	%ctpr1, .L13
	  adds,0	%r12, 0x1, %r12
	  adds,1,sm	0x0, 0x0, %r11
	  adds,2,sm	0x0, 0x0, %r9
	}
	{
	  cmpbsb,0	%r12, %r0, %pred0
	}
	{
	  adds,0	%r14, %r12, %g16 ? %pred0
	}
	{
	  nop 1
	  shld,0,sm	%g16, 0x2, %r8
	}
	{
	  ct	%ctpr1 ? %pred0
	}

	{
	  disp	%ctpr1, .L7
	  adds,0	%r16, 0x1, %r16
	  adds,1,sm	%r0, %r14, %r14
	}
	{
	  nop 2
	  return	%ctpr3
	  cmpbsb,0	%r16, %r0, %pred0
	}
	{
	  ct	%ctpr3 ? ~%pred0
	}
	{
	  ct	%ctpr1 ? %pred0
	}
.L1021:
	{
	  getfs,0,sm	%b[15], %r5, %b[57]
	  getfs,1,sm	%b[45], %r5, %b[30]
	}
	{
	  nop 5
	  muls,0,sm	%b[30], %b[57], %b[56]
	}
	{
	  getfs,0,sm	%b[56], %r7, %b[62]
	  getfs,1,sm	%b[56], %r6, %b[63]
	}
	{
	  nop 4
	  muls,0,sm	%b[63], %b[62], %b[68]
	}
	{
	  ibranch	.L1032
	}
	.size	matrix_mul_matrix_bitextract, .- matrix_mul_matrix_bitextract
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x4, rcur = 0x0
	  disp	%ctpr1, matrix_mul_matrix_bitextract
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
