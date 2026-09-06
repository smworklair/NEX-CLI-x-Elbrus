	.file	"poly_gemm.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x20, nfx = 0x1, dbl = 0x0
	  ldisp	%ctpr2, .L1416
	  addd,1	0x8, 0x0, %g20
	  addd,2	0x0, [ _f64,_lts2 C ], %g22
	  adds,3	0x0, 0x0, %g23
	  addd,4	0x0, 0x0, %g21
	}
	{
	  setwd	wsz = 0x53, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x32, rbs = 0x20, rcur = 0x0
	  disp	%ctpr1, .L965
	  rwd,0	_f64,_lts1 0x107f72700000008, %lsr
	}
	{
	  rwd,0	%g20, %lsr1
	  addd,1	0x0, [ _f64,_lts2 A ], %g24
	  aaurwd,5	%g20, %aaincr2
	}
	{
	  addd,1	0x0, _f64,_lts0 0x3ff8000000000000, %g19
	  aaurwd,2	%g22, %aad1
	  addd,3	0x0, _f64,_lts0 0x3ff8000000000000, %g18
	  aaurwd,5	%g20, %aaincr1
	}
	{
	  aaurwd,2	%g21, %aasti3
	  aaurwd,5	%g22, %aaind2
	}
	{
	  aaurwd,2	%g24, %aaind1
	  aaurw,5	%g23, %aad0
	}
	{
	  bap
	  ldd,0	0x0, [ _f64,_lts0 B +72 ], %g17
	  ldd,2	0x0, [ _f64,_lts2 B +64 ], %g16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +88 ], %r63
	  ldd,2	0x0, [ _f64,_lts2 B +80 ], %r62
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +104 ], %r61
	  ldd,2	0x0, [ _f64,_lts2 B +96 ], %r60
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +120 ], %r59
	  ldd,2	0x0, [ _f64,_lts2 B +112 ], %r58
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +136 ], %r57
	  ldd,2	0x0, [ _f64,_lts2 B +128 ], %r56
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +152 ], %r55
	  ldd,2	0x0, [ _f64,_lts2 B +144 ], %r54
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +168 ], %r53
	  ldd,2	0x0, [ _f64,_lts2 B +160 ], %r52
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +184 ], %r51
	  ldd,2	0x0, [ _f64,_lts2 B +176 ], %r50
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +200 ], %r49
	  ldd,2	0x0, [ _f64,_lts2 B +192 ], %r48
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +216 ], %r47
	  ldd,2	0x0, [ _f64,_lts2 B +208 ], %r46
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +232 ], %r45
	  ldd,2	0x0, [ _f64,_lts2 B +224 ], %r44
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +248 ], %r43
	  ldd,2	0x0, [ _f64,_lts2 B +240 ], %r42
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +264 ], %r41
	  ldd,2	0x0, [ _f64,_lts2 B +256 ], %r40
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +280 ], %r39
	  ldd,2	0x0, [ _f64,_lts2 B +272 ], %r38
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +296 ], %r37
	  ldd,2	0x0, [ _f64,_lts2 B +288 ], %r36
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +312 ], %r35
	  ldd,2	0x0, [ _f64,_lts2 B +304 ], %r34
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +328 ], %r33
	  ldd,2	0x0, [ _f64,_lts2 B +320 ], %r32
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +344 ], %r31
	  ldd,2	0x0, [ _f64,_lts2 B +336 ], %r30
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +360 ], %r29
	  ldd,2	0x0, [ _f64,_lts2 B +352 ], %r28
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +376 ], %r27
	  ldd,2	0x0, [ _f64,_lts2 B +368 ], %r26
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +392 ], %r25
	  ldd,2	0x0, [ _f64,_lts2 B +384 ], %r24
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +408 ], %r23
	  ldd,2	0x0, [ _f64,_lts2 B +400 ], %r22
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +424 ], %r21
	  ldd,2	0x0, [ _f64,_lts2 B +416 ], %r20
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +440 ], %r19
	  ldd,2	0x0, [ _f64,_lts2 B +432 ], %r18
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +496 ], %r17
	  ldd,2	0x0, [ _f64,_lts2 B +504 ], %r16
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +480 ], %r15
	  ldd,2	0x0, [ _f64,_lts2 B +488 ], %r14
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +464 ], %r13
	  ldd,2	0x0, [ _f64,_lts2 B +472 ], %r12
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +448 ], %r11
	  ldd,2	0x0, [ _f64,_lts2 B +456 ], %r10
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +8 ], %r9
	  ldd,2	0x0, [ _f64,_lts2 B ], %r8
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +24 ], %r7
	  ldd,2	0x0, [ _f64,_lts2 B +16 ], %r6
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +40 ], %r5
	  ldd,2	0x0, [ _f64,_lts2 B +32 ], %r4
	}
	{
	  ldd,0	0x0, [ _f64,_lts0 B +56 ], %r3
	  ldd,2	0x0, [ _f64,_lts2 B +48 ], %r0
	}
	{
	  nop 4
	  disp	%ctpr1, .L965
	}
	{
	  ct	%ctpr1
	}
	.align	8
.L1416:
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=2, asz=4, abs=0, disp=32
	}
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=0, d=0, incr=1, ind=1, asz=4, abs=16, disp=32
	}
.L965:
	{
	  loop_mode
	  fmul_addd,0,sm	%b[2], %r51, %b[74], %b[75]
	  fmul_addd,1,sm	%b[65], %r48, %b[75], %b[82]
	  fmul_addd,2,sm	%b[78], %r33, %b[82], %b[65]
	  fmul_addd,3,sm	%b[60], %r15, %b[87], %b[74]
	  fmuld,4,sm	%g19, %b[38], %b[0]
	  fmuld,5,sm	%b[44], %g18, %b[87]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[2], %r50, %b[71], %b[81]
	  fmul_addd,1,sm	%b[31], %r35, %b[77], %b[84]
	  fmul_addd,2,sm	%b[78], %r32, %b[81], %b[77]
	  fmul_addd,3,sm	%b[60], %r12, %b[84], %b[78]
	  fmuld,4,sm	%b[49], %g18, %b[1]
	  fmuld,5,sm	%g19, %b[37], %b[71]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[2], %r53, %b[63], %b[86]
	  fmul_addd,1,sm	%b[31], %r34, %b[64], %b[89]
	  fmul_addd,2,sm	%b[26], %r19, %b[83], %b[64]
	  fmul_addd,3,sm	%b[60], %r13, %b[86], %b[83]
	  fmuld,4,sm	%b[48], %g18, %b[10]
	  fmuld,5,sm	%g19, %b[10], %b[63]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[59], %r7, %b[12], %b[92]
	  fmul_addd,1,sm	%b[2], %r52, %b[76], %b[91]
	  fmul_addd,2,sm	%b[31], %r37, %b[88], %b[98]
	  fmul_addd,3,sm	%b[60], %r10, %b[91], %b[88]
	  fmul_addd,4,sm	%b[57], %r3, %b[53], %b[12]
	  fmuld,5,sm	%g19, %b[29], %b[76]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[59], %r6, %b[3], %b[94]
	  fmul_addd,1,sm	%b[2], %r55, %b[94], %b[95]
	  fmul_addd,2,sm	%b[31], %r36, %b[95], %b[99]
	  fmul_addd,3,sm	%b[60], %r11, %b[100], %b[60]
	  fmul_addd,4,sm	%b[57], %r0, %b[30], %b[3]
	  fmuld,5,sm	%g19, %b[45], %b[29]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[59], %r9, %b[54], %b[54]
	  fmul_addd,1,sm	%b[2], %r54, %b[96], %b[67]
	  fmul_addd,2,sm	%b[31], %r39, %b[97], %b[68]
	  fmul_addd,3,sm	%b[26], %r18, %b[67], %b[96]
	  fmul_addd,4,sm	%b[57], %r5, %b[68], %b[30]
	  fmuld,5,sm	%g19, %b[24], %b[24]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[59], %r8, %b[87], %b[59]
	  fmul_addd,1,sm	%b[2], %r57, %b[70], %b[70]
	  fmul_addd,2,sm	%b[31], %r38, %b[90], %b[87]
	  fmul_addd,3,sm	%b[26], %r21, %b[93], %b[90]
	  fmul_addd,4,sm	%b[57], %r4, %b[58], %b[17]
	  fmuld,5,sm	%g19, %b[17], %b[58]
	  movad,3	area=0, ind=16, am=0, be=0, %b[93]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r59, %b[14], %b[72]
	  fmul_addd,1,sm	%b[2], %r56, %b[72], %b[73]
	  fmul_addd,2,sm	%b[31], %r41, %b[73], %b[80]
	  fmul_addd,3,sm	%b[26], %r20, %b[66], %b[85]
	  fmuld,4,sm	%b[80], %g18, %b[66]
	  staad,5	%b[85], %aad1[ %aasti3 + _f32s,_lts0 0x38 ]
	  movad,3	area=0, ind=24, am=0, be=0, %b[97]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r58, %b[5], %b[69]
	  fmul_addd,1,sm	%b[63], %r43, %b[75], %b[75]
	  fmul_addd,2,sm	%b[31], %r40, %b[82], %b[79]
	  fmul_addd,3,sm	%b[26], %r23, %b[56], %b[82]
	  fmuld,4,sm	%b[79], %g18, %b[56]
	  staad,5	%b[69], %aad1[ %aasti3 + _f32s,_lts0 0x30 ]
	  movad,0	area=1, ind=24, am=0, be=0, %b[2]
	  movad,1	area=1, ind=0, am=0, be=0, %b[101]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r61, %b[32], %b[61]
	  fmul_addd,1,sm	%b[63], %r42, %b[81], %b[62]
	  fmul_addd,2,sm	%b[76], %r27, %b[84], %b[81]
	  fmul_addd,3,sm	%b[26], %r22, %b[61], %b[84]
	  staad,5	%b[62], %aad1[ %aasti3 + _f32s,_lts0 0x28 ]
	  movad,0	area=1, ind=8, am=1, be=0, %b[31]
	  movad,1	area=1, ind=16, am=0, be=0, %b[32]
	  movad,2	area=1, ind=24, am=0, be=0, %b[5]
	  movad,3	area=1, ind=16, am=0, be=0, %b[14]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r60, %b[19], %b[74]
	  fmul_addd,1,sm	%b[63], %r45, %b[86], %b[86]
	  fmul_addd,2,sm	%b[76], %r26, %b[89], %b[65]
	  fmul_addd,3,sm	%b[26], %r25, %b[65], %b[89]
	  staad,5	%b[74], %aad1[ %aasti3 + _f32s,_lts0 0x20 ]
	  movad,0	area=0, ind=0, am=0, be=0, %b[38]
	  movad,1	area=0, ind=24, am=0, be=0, %b[44]
	  movad,2	area=1, ind=8, am=1, be=0, %b[19]
	  movad,3	area=1, ind=0, am=0, be=0, %b[37]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r63, %b[92], %b[92]
	  fmul_addd,1,sm	%b[63], %r44, %b[91], %b[93]
	  fmul_addd,2,sm	%b[76], %r29, %b[98], %b[91]
	  fmul_addd,3,sm	%b[26], %r24, %b[77], %b[98]
	  fmuld,4,sm	%b[93], %g18, %b[26]
	  staad,5	%b[78], %aad1[ %aasti3 + _f32s,_lts0 0x18 ]
	  movad,0	area=0, ind=16, am=0, be=0, %b[45]
	  movad,1	area=0, ind=8, am=1, be=0, %b[48]
	  movad,2	area=0, ind=0, am=0, be=0, %b[77]
	  movad,3	area=0, ind=8, am=1, be=0, %b[78]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %r62, %b[94], %b[94]
	  fmul_addd,1,sm	%b[63], %r47, %b[95], %b[95]
	  fmul_addd,2,sm	%b[76], %r28, %b[99], %b[64]
	  fmul_addd,3,sm	%b[58], %r16, %b[64], %b[83]
	  fmuld,4,sm	%b[97], %g18, %b[49]
	  staad,5	%b[83], %aad1[ %aasti3 + _f32s,_lts0 0x10 ]
	}
	{
	  loop_mode
	  fmul_addd,0,sm	%b[71], %g17, %b[54], %b[68]
	  fmul_addd,1,sm	%b[63], %r46, %b[67], %b[88]
	  fmul_addd,2,sm	%b[76], %r31, %b[68], %b[54]
	  fmul_addd,3,sm	%b[58], %r17, %b[96], %b[67]
	  fmuld,4,sm	%g19, %b[101], %b[53]
	  staad,5	%b[88], %aad1[ %aasti3 + _f32s,_lts0 0x8 ]
	}
	{
	  loop_mode
	  alc	alcf=1, alct=1
	  abn	abnf=1, abnt=1
	  ct	%ctpr1 ? %NOT_LOOP_END
	  fmul_addd,0,sm	%b[71], %g16, %b[59], %b[70]
	  fmul_addd,1,sm	%b[63], %r49, %b[70], %b[71]
	  fmul_addd,2,sm	%b[76], %r30, %b[87], %b[59]
	  fmul_addd,3,sm	%b[58], %r14, %b[90], %b[60]
	  fmuld,4,sm	%b[50], %g18, %b[50]
	  staad,5	%b[60], %aad1[ %aasti3 ]
	  incr,5	%aaincr2
	}

	{
	  setwd	wsz = 0x20, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts1 C +144 ], %g16
	}
	{
	  adds,1	0x0, 0x0, %g17
	}
	{
	  nop 2
	  disp	%ctpr2, disp=0x0
	  aaurw,2	%g17, %aabf0
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
	.global	C
	.type	C, #object
	.size	C, 0x200
	.align	16
C:
	.skip	0x200
	.global	A
	.type	A, #object
	.size	A, 0x200
	.align	16
A:
	.skip	0x200
	.global	B
	.type	B, #object
	.size	B, 0x200
	.align	16
B:
	.skip	0x200
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
