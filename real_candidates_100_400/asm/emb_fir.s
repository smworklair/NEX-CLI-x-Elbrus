	.file	"emb_fir.c"
	.ignore	ld_st_style
	.ignore	strict_delay
	.text
	.global	fir_no_red_ld
	.type	fir_no_red_ld, #function
	.align	8
fir_no_red_ld:

	{
	  setwd	wsz = 0x1c, nfx = 0x1, dbl = 0x0
	  return	%ctpr3
	  addd,1	0x0, 0x0, %g16
	  scls,2	0xd, 0xa, %r5
	  addd,4	0x2, 0x0, %g17
	}
	{
	  rwd,0	_f64,_lts0 0x1fe0002000000032, %lsr
	  aaurwd,2	%g16, %aasti1
	  aaurwd,5	%g17, %aaincr1
	}
	{
	  ldb,3,sm	%r0, 0x0, %empty, mas=0x20
	  addd,4,sm	0x0, 0x0, %r2
	  aaurwd,5	%r2, %aad0
	}
	{
	  nop 1
	  ldb,0,sm	%r0, _f16s,_lts0lo 0x40, %empty, mas=0x20
	  ldb,2,sm	%r0, _f16s,_lts0hi 0x80, %empty, mas=0x20
	}
.L692:
	{
	  loop_mode
	  disp	%ctpr1, .L692
	  ldh,0	%r1, 0x2, %g17
	  addd,1,sm	%r0, %r2, %g16
	  ldh,2	%r1, 0x0, %g18
	  ldh,3	%r1, 0xa, %g19
	  ldh,5	%r1, 0x8, %g20
	}
	{
	  loop_mode
	  ldh,0	%r0, %r2, %g21
	  addd,1,sm	0x14, %r2, %g25
	  ldh,2	%r1, 0x6, %g22
	  ldh,3	%r1, 0x4, %g23
	  addd,4,sm	0x4, %r2, %r2
	  ldh,5	%r1, _f16s,_lts0lo 0x12, %g24
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x10, %g26
	  ldh,2	%r1, 0xe, %g27
	  ldh,3	%r1, 0xc, %g28
	  ldh,5	%r1, _f16s,_lts0hi 0x1a, %g29
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x18, %g30
	  ldh,2	%r1, _f16s,_lts0hi 0x16, %g31
	  ldh,3	%r1, _f16s,_lts1lo 0x14, %r4
	  ldh,5	%r1, _f16s,_lts1hi 0x22, %r6
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x20, %r7
	  ldh,2	%r1, _f16s,_lts0hi 0x1e, %r8
	  ldh,3	%r1, _f16s,_lts1lo 0x1c, %r9
	  ldh,5	%r1, _f16s,_lts1hi 0x2a, %r10
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x28, %r11
	  getfs,1	%g18, %r5, %g18
	  ldh,2	%r1, _f16s,_lts0hi 0x26, %r12
	  ldh,3	%r1, _f16s,_lts1lo 0x24, %r13
	  getfs,4	%g17, %r5, %g17
	  ldh,5	%r1, _f16s,_lts1hi 0x32, %r14
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x30, %r15
	  getfs,1	%g21, %r5, %g21
	  ldh,2	%r1, _f16s,_lts0hi 0x2e, %r16
	  ldh,3	%r1, _f16s,_lts1lo 0x2c, %r17
	  getfs,4	%g23, %r5, %g23
	  ldh,5	%r1, _f16s,_lts1hi 0x3a, %r18
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x38, %r19
	  getfs,1	%g20, %r5, %g20
	  ldh,2	%r1, _f16s,_lts0hi 0x36, %r20
	  ldh,3	%r1, _f16s,_lts1lo 0x34, %r21
	  getfs,4	%g22, %r5, %g22
	  ldh,5	%r1, _f16s,_lts1hi 0x3e, %r22
	}
	{
	  loop_mode
	  ldh,0	%r1, _f16s,_lts0lo 0x3c, %r23
	  getfs,1	%g28, %r5, %g28
	  ldh,2	%g16, 0x4, %r24
	  ldh,3	%g16, 0x2, %r25
	  getfs,4	%g19, %r5, %g19
	  ldh,5	%g16, 0xc, %r26
	}
	{
	  loop_mode
	  ldh,0	%g16, 0xa, %r27
	  getfs,1	%g26, %r5, %g26
	  ldh,2	%g16, 0x8, %r28
	  ldh,3	%g16, 0x6, %r29
	  getfs,4	%g27, %r5, %g27
	  ldh,5	%g16, _f16s,_lts0lo 0x14, %r30
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x12, %r31
	  getfs,1	%r4, %r5, %r4
	  ldh,2	%g16, _f16s,_lts0hi 0x10, %r32
	  ldh,3	%g16, 0xe, %r33
	  getfs,4	%g24, %r5, %g24
	  ldh,5	%g16, _f16s,_lts1lo 0x1c, %r34
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x1a, %r35
	  getfs,1	%g30, %r5, %g30
	  ldh,2	%g16, _f16s,_lts0hi 0x18, %r36
	  ldh,3	%g16, _f16s,_lts1lo 0x16, %r37
	  getfs,4	%g31, %r5, %g31
	  ldh,5	%g16, _f16s,_lts1hi 0x24, %r38
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x22, %r39
	  getfs,1	%r9, %r5, %r9
	  ldh,2	%g16, _f16s,_lts0hi 0x20, %r40
	  ldh,3	%g16, _f16s,_lts1lo 0x1e, %r41
	  getfs,4	%g29, %r5, %g29
	  ldh,5	%g16, _f16s,_lts1hi 0x2c, %r42
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x2a, %r43
	  getfs,1	%r7, %r5, %r7
	  ldh,2	%g16, _f16s,_lts0hi 0x28, %r44
	  ldh,3	%g16, _f16s,_lts1lo 0x26, %r45
	  getfs,4	%r8, %r5, %r8
	  ldh,5	%g16, _f16s,_lts1hi 0x34, %r46
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x32, %r47
	  getfs,1	%r13, %r5, %r13
	  ldh,2	%g16, _f16s,_lts0hi 0x30, %r48
	  ldh,3	%g16, _f16s,_lts1lo 0x2e, %r49
	  getfs,4	%r6, %r5, %r6
	  ldh,5	%g16, _f16s,_lts1hi 0x3c, %r50
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x3a, %r51
	  getfs,1	%r11, %r5, %r11
	  ldh,2	%g16, _f16s,_lts0hi 0x38, %r52
	  ldh,3	%g16, _f16s,_lts1lo 0x36, %r53
	  getfs,4	%r12, %r5, %r12
	  ldh,5	%g16, _f16s,_lts1hi 0x40, %r54
	}
	{
	  loop_mode
	  ldh,0	%g16, _f16s,_lts0lo 0x3e, %g16
	  getfs,1	%r17, %r5, %r17
	  ldb,2,sm	%r0, %g25, %empty, mas=0x20
	  muls,3	%g21, %g18, %g21
	  getfs,4	%r10, %r5, %r10
	}
	{
	  loop_mode
	  getfs,1	%r14, %r5, %g25
	  getfs,3	%r15, %r5, %r14
	  getfs,4	%r16, %r5, %r15
	  getfs,5	%r23, %r5, %r16
	}
	{
	  loop_mode
	  getfs,0	%r18, %r5, %r18
	  getfs,1	%r19, %r5, %r19
	  getfs,2	%r20, %r5, %r20
	  getfs,4	%r21, %r5, %r21
	  getfs,5	%r22, %r5, %r22
	}
	{
	  loop_mode
	  getfs,0	%r27, %r5, %r23
	  getfs,1	%r28, %r5, %r27
	  getfs,2	%r29, %r5, %r28
	  getfs,3	%r24, %r5, %r24
	  getfs,4	%r25, %r5, %r25
	  getfs,5	%r37, %r5, %r29
	}
	{
	  loop_mode
	  getfs,0	%r30, %r5, %r30
	  getfs,1	%r31, %r5, %r31
	  getfs,2	%r32, %r5, %r32
	  getfs,3	%r33, %r5, %r33
	  getfs,4	%r26, %r5, %r26
	  getfs,5	%r39, %r5, %r37
	}
	{
	  loop_mode
	  getfs,0	%r40, %r5, %r39
	  getfs,1	%r41, %r5, %r40
	  getfs,2	%r34, %r5, %r34
	  getfs,3	%r35, %r5, %r35
	  getfs,4	%r36, %r5, %r36
	  getfs,5	%r49, %r5, %r41
	}
	{
	  loop_mode
	  getfs,0	%r42, %r5, %r42
	  getfs,1	%r43, %r5, %r43
	  getfs,2	%r44, %r5, %r44
	  getfs,3	%r45, %r5, %r45
	  getfs,4	%r38, %r5, %r38
	  getfs,5	%r51, %r5, %r49
	}
	{
	  loop_mode
	  getfs,0	%r52, %r5, %r51
	  getfs,1	%r53, %r5, %r52
	  getfs,2	%r46, %r5, %r46
	  getfs,3	%r47, %r5, %r47
	  getfs,4	%r48, %r5, %r48
	  getfs,5	%r54, %r5, %r53
	}
	{
	  loop_mode
	  getfs,0	%r50, %r5, %r50
	  muls,1	%r25, %g18, %g18
	  getfs,2	%g16, %r5, %g16
	  muls,3	%r25, %g17, %r25
	  muls,4	%r28, %g23, %r54
	  sxt,5	0x2, %g21, %g21
	}
	{
	  loop_mode
	  muls,0	%r28, %g22, %r28
	  muls,1	%r24, %g17, %g17
	  muls,3	%r24, %g23, %g23
	  muls,4	%r23, %g20, %r24
	}
	{
	  loop_mode
	  muls,0	%r23, %g19, %r23
	  muls,1	%r27, %g22, %g22
	  muls,3	%r27, %g20, %g20
	  muls,4	%r33, %g28, %r27
	}
	{
	  loop_mode
	  muls,0	%r33, %g27, %r33
	  muls,1	%r26, %g19, %g19
	  muls,3	%r26, %g28, %g28
	  muls,4	%r31, %g26, %r26
	}
	{
	  loop_mode
	  muls,0	%r31, %g24, %r31
	  muls,1	%r32, %g27, %g27
	  muls,3	%r32, %g26, %g26
	  muls,4	%r29, %r4, %r32
	}
	{
	  loop_mode
	  muls,0	%r29, %g31, %r29
	  muls,1	%r30, %g24, %g24
	  muls,3	%r30, %r4, %r4
	  muls,4	%r35, %g30, %r30
	}
	{
	  loop_mode
	  muls,0	%r35, %g29, %r35
	  muls,1	%r36, %g31, %g31
	  sxt,2	0x2, %g18, %g18
	  muls,3	%r36, %g30, %g30
	  muls,4	%r40, %r9, %r36
	  sxt,5	0x2, %r25, %r25
	}
	{
	  loop_mode
	  muls,0	%r40, %r8, %r40
	  muls,1	%r34, %g29, %g29
	  sxt,2	0x2, %g17, %g17
	  muls,3	%r34, %r9, %r9
	  muls,4	%r37, %r7, %r34
	  sxt,5	0x2, %g23, %g23
	}
	{
	  loop_mode
	  muls,0	%r37, %r6, %r37
	  muls,1	%r39, %r8, %r8
	  sxt,2	0x2, %r54, %r54
	  muls,3	%r39, %r7, %r7
	  muls,4	%r45, %r13, %r39
	  sxt,5	0x2, %r28, %r28
	}
	{
	  loop_mode
	  muls,0	%r45, %r12, %r45
	  muls,1	%r38, %r6, %r6
	  sxt,2	0x2, %g22, %g22
	  muls,3	%r38, %r13, %r13
	  muls,4	%r43, %r11, %r38
	  sxt,5	0x2, %g20, %g20
	}
	{
	  loop_mode
	  muls,0	%r43, %r10, %r43
	  muls,1	%r44, %r12, %r12
	  sxt,2	0x2, %r24, %r24
	  muls,3	%r44, %r11, %r11
	  muls,4	%r41, %r17, %r44
	  sxt,5	0x2, %r23, %r23
	}
	{
	  loop_mode
	  muls,0	%r41, %r15, %r41
	  muls,1	%r42, %r10, %r10
	  sxt,2	0x2, %g19, %g19
	  muls,3	%r42, %r17, %r17
	  muls,4	%r47, %r14, %r42
	  sxt,5	0x2, %g28, %g28
	}
	{
	  loop_mode
	  muls,0	%r47, %g25, %r47
	  muls,1	%r48, %r15, %r15
	  sxt,2	0x2, %r27, %r27
	  muls,3	%r48, %r14, %r14
	  muls,4	%r52, %r21, %r48
	  sxt,5	0x2, %r33, %r33
	}
	{
	  loop_mode
	  muls,0	%r52, %r20, %r52
	  muls,1	%r46, %g25, %g25
	  sxt,2	0x2, %g27, %g27
	  muls,3	%r46, %r21, %r21
	  muls,4	%r49, %r19, %r46
	  sxt,5	0x2, %g26, %g26
	}
	{
	  loop_mode
	  muls,0	%r49, %r18, %r49
	  muls,1	%r51, %r20, %r20
	  sxt,2	0x2, %r26, %r26
	  muls,3	%r51, %r19, %r19
	  muls,4	%g16, %r16, %r51
	  sxt,5	0x2, %r31, %r31
	}
	{
	  loop_mode
	  muls,0	%g16, %r22, %g16
	  muls,1	%r50, %r18, %r18
	  sxt,2	0x2, %g24, %g24
	  muls,3	%r50, %r16, %r16
	  muls,4	%r53, %r22, %r22
	  sxt,5	0x2, %r4, %r4
	}
	{
	  loop_mode
	  sxt,2	0x2, %r32, %r32
	  sxt,5	0x2, %r29, %r29
	}
	{
	  loop_mode
	  sxt,2	0x2, %g31, %g31
	  sxt,5	0x2, %g30, %g30
	}
	{
	  loop_mode
	  sxt,0	0x2, %r40, %r40
	  sxt,1	0x2, %g29, %g29
	  sxt,2	0x2, %r9, %r9
	  sxt,3	0x2, %r30, %r30
	  sxt,4	0x2, %r35, %r35
	  sxt,5	0x2, %r13, %r13
	}
	{
	  loop_mode
	  sxt,0	0x2, %r34, %r34
	  sxt,1	0x2, %r37, %r37
	  sxt,2	0x2, %r8, %r8
	  sxt,3	0x2, %r7, %r7
	  sxt,4	0x2, %r36, %r36
	  sxt,5	0x2, %r43, %r43
	}
	{
	  loop_mode
	  sxt,0	0x2, %r12, %r12
	  sxt,1	0x2, %r11, %r11
	  sxt,2	0x2, %r39, %r39
	  sxt,3	0x2, %r45, %r45
	  sxt,4	0x2, %r6, %r6
	  sxt,5	0x2, %r14, %r14
	}
	{
	  loop_mode
	  sxt,0	0x2, %r44, %r44
	  sxt,1	0x2, %r41, %r41
	  sxt,2	0x2, %r10, %r10
	  sxt,3	0x2, %r17, %r17
	  sxt,4	0x2, %r38, %r38
	  sxt,5	0x2, %r52, %r50
	}
	{
	  loop_mode
	  sxt,0	0x2, %g25, %g25
	  sxt,1	0x2, %r21, %r21
	  sxt,2	0x2, %r42, %r42
	  sxt,3	0x2, %r47, %r47
	  sxt,4	0x2, %r15, %r15
	  sxt,5	0x2, %r16, %r16
	}
	{
	  loop_mode
	  sxt,0	0x2, %r46, %r46
	  sxt,1	0x2, %r49, %r49
	  sxt,2	0x2, %r20, %r20
	  sxt,3	0x2, %r19, %r19
	  sxt,4	0x2, %r48, %r48
	  sxt,5	0x2, %r22, %r22
	}
	{
	  loop_mode
	  sxt,0	0x2, %r51, %r51
	  sxt,1	0x2, %g16, %g16
	  sxt,2	0x2, %r18, %r18
	  addd,3	%r24, %r32, %r24
	  addd,4	%g20, %r4, %g20
	  addd,5	%r7, %r40, %r4
	}
	{
	  loop_mode
	  addd,0	%r27, %r36, %r7
	  addd,1	%r37, %r33, %r27
	  addd,2	%g19, %r30, %g19
	  addd,3	%g28, %r9, %g28
	  addd,4	%r23, %g30, %g30
	  addd,5	%r34, %r8, %r8
	}
	{
	  loop_mode
	  addd,0	%r26, %r39, %r9
	  addd,1	%r31, %r11, %r11
	  addd,2	%r6, %g27, %g27
	  addd,3	%g26, %r13, %g26
	  addd,4	%r45, %r28, %r6
	  addd,5	%r44, %r10, %r10
	}
	{
	  loop_mode
	  addd,0	%r17, %r43, %r13
	  addd,1	%r29, %r14, %r14
	  addd,2	%g24, %r38, %g24
	  addd,3	%r12, %g22, %g22
	  addd,4	%r41, %r25, %r12
	  addd,5	%r19, %r50, %r17
	}
	{
	  loop_mode
	  addd,0	%r48, %g25, %g25
	  addd,1	%r21, %r47, %r19
	  addd,2	%r49, %r35, %r21
	  addd,3	%g31, %r42, %g31
	  addd,4	%r15, %g17, %g17
	  addd,5	%g21, %g16, %g16
	}
	{
	  loop_mode
	  addd,0	%r46, %r20, %g21
	  addd,1	%r18, %g29, %g29
	  addd,2	%r51, %r54, %r15
	  addd,3	%r16, %g23, %g23
	  addd,4	%g18, %r22, %g18
	  addd,5	%g24, %r8, %g24
	}
	{
	  loop_mode
	  addd,0	%r11, %r4, %r4
	  addd,1	%r24, %r9, %r8
	  addd,2	%g20, %g26, %g20
	  addd,3	%r14, %r6, %g26
	  addd,4	%r13, %r12, %r6
	  addd,5	%r19, %r17, %r9
	}
	{
	  loop_mode
	  addd,0	%g25, %g21, %g21
	  addd,1	%r21, %r27, %g25
	  addd,2	%g31, %g22, %g22
	  addd,3	%r10, %g17, %g17
	  addd,4	%g23, %g28, %g23
	  addd,5	%g29, %g27, %g27
	}
	{
	  loop_mode
	  addd,0	%g16, %g30, %g16
	  addd,1	%r15, %r7, %g28
	  addd,2	%g18, %g19, %g18
	  addd,3	%g23, %g26, %g19
	  addd,4	%r6, %g20, %g20
	  addd,5	%g17, %r8, %g17
	}
	{
	  loop_mode
	  addd,0	%g27, %g21, %g21
	  addd,1	%g24, %g18, %g18
	  addd,2	%g25, %r9, %g23
	  addd,3	%g20, %g19, %g19
	}
	{
	  loop_mode
	  addd,0	%r4, %g16, %g16
	  addd,1	%g28, %g22, %g20
	  addd,2	%g18, %g21, %g18
	}
	{
	  loop_mode
	  addd,0	%g16, %g23, %g16
	  addd,1	%g17, %g20, %g17
	}
	{
	  loop_mode
	  addd,0	%g18, %g17, %g17
	  addd,1	%g16, %g19, %g16
	}
	{
	  loop_mode
	  sard,0	%g17, 0xf, %g17
	  sard,1	%g16, 0xf, %g16
	}
	{
	  loop_mode
	  ct	%ctpr1 ? %NOT_LOOP_END
	  alc	alcf=1, alct=1
	  staad,2	%g17, %aad0[ %aasti1 + _f32s,_lts0 0x8 ]
	  staad,5	%g16, %aad0[ %aasti1 ]
	  incr,5	%aaincr1
	}

	{
	  adds,0	0x0, 0x0, %g16
	}
	{
	  ct	%ctpr3
	  aaurw,2	%g16, %aabf0
	}
	.size	fir_no_red_ld, .- fir_no_red_ld
	.global	main
	.type	main, #function
	.align	8
main:

	{
	  setwd	wsz = 0x8, nfx = 0x1, dbl = 0x0
	  setbn	rsz = 0x3, rbs = 0x4, rcur = 0x0
	  disp	%ctpr1, fir_no_red_ld
	  getsp,0	_f32s,_lts1 0xffffffe0, %r2
	}
	{
	  addd,0	0x0, [ _f64,_lts0 H ], %b[1]
	  addd,1	0x0, [ _f64,_lts2 Y ], %b[2]
	}
	{
	  nop 2
	  addd,0	0x0, [ _f64,_lts0 X ], %b[0]
	}
.LCS.1:
	{
	  call	%ctpr1, wbs = 0x4
	}
	{
	  nop 4
	  return	%ctpr3
	  ldd,0	0x0, [ _f64,_lts0 Y +24 ], %r3
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
	.global	X
	.type	X, #object
	.size	X, 0x140
	.align	16
X:
	.skip	0x140
	.global	H
	.type	H, #object
	.size	H, 0x80
	.align	16
H:
	.skip	0x80
	.global	Y
	.type	Y, #object
	.size	Y, 0x500
	.align	16
Y:
	.skip	0x500
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
