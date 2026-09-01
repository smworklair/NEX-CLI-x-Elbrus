! options passed: --mcpu-internal=elbrus-v6 -O3 kernel.c
! -----------------------------------------------------------------------------
	.file	"kernel.c"
	.ignore	ld_st_style
	.ignore	strict_delay
! -----------------------------------------------------------------------------
	.text
	.global	kernel
	.type	kernel, #function
	.align	8
kernel:
	! source = kernel.c : 6
	! stack shift = 0 (0x0)
	! outgoing stack size = 0 (0x0)
	! frame pointer = %r0
	! stack pointer = %r1
							! kernel.c : 7
	! <0000>
	{
	  setwd	wsz = 0xa, nfx = 0x1, dbl = 0x0	! kernel.c : 7
	  ldisp	%ctpr2, .L394				! kernel.c : 7
	  addd,0	0x0, 0x0, %dg17				! kernel.c : 7
	  adds,1	0x0, 0x0, %g18				! kernel.c : 7
	  ldd,3,sm	0x0, [ _f64,_lts1 c ], %dg16		! kernel.c : 7
	}
	! <0001>
	{
	  setwd	wsz = 0x27, nfx = 0x1, dbl = 0x0	! kernel.c : 7
	  setbn	rsz = 0x1c, rbs = 0xa, rcur = 0x0	! kernel.c : 7
	  disp	%ctpr1, .L99				! kernel.c : 7
	  ldd,3,sm	0x0, [ _f64,_lts1 b ], %dg19		! kernel.c : 7
	}
	! <0002>
	{
	  return	%ctpr3				! kernel.c : 7
	  ldd,3,sm	0x0, [ _f64,_lts0 a ], %dg20		! kernel.c : 7
	  ldd,5,sm	0x0, [ _f64,_lts2 c +8 ], %dg21		! kernel.c : 7
	}
	! <0003>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 b +8 ], %dg22		! kernel.c : 7
	  ldd,5,sm	0x0, [ _f64,_lts2 a +8 ], %dg23		! kernel.c : 7
	}
	! <0004>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 c +16 ], %dg24	! kernel.c : 9
	  ldd,5,sm	0x0, [ _f64,_lts2 b +16 ], %dg25	! kernel.c : 9
	}
	! <0005>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 a +16 ], %dg26	! kernel.c : 9
	  ldd,5,sm	0x0, [ _f64,_lts2 b +24 ], %db[37]	! kernel.c : 9
	}
	! <0006>
	{
	  ldd,3,sm	0x0, [ _f64,_lts2 c +24 ], %dg27	! kernel.c : 9
	  addd,4	0x0, _f64,_lts0 0x3ff0000000000000, %dr1	! kernel.c : 7
	  aaurwd,5	%dg17, %aasti4				! kernel.c : 7
	}
	! <0007>
	{
	  addd,1	0x0, _f64,_lts0 0x4000000000000000, %dr2	! kernel.c : 7
	  aaurw,2	%g18, %aad0				! kernel.c : 7
	  fmuld,3,sm	%dg20, %dg19, %dg20				! kernel.c : 8
	  fmul_subd,4,sm	%dg19, %dg16, %dg20, %dg17			! kernel.c : 9
	  ldd,5,sm	0x0, [ _f64,_lts2 a +24 ], %dg28	! kernel.c : 9
	}
	! <0008>
	{
	  ldd,0,sm	0x0, [ _f64,_lts2 b +32 ], %db[35]	! kernel.c : 8
	  ldd,5,sm	0x0, [ _f64,_lts0 c +32 ], %dg18	! kernel.c : 8
	}
	! <0009>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 a +32 ], %dg29	! kernel.c : 8
	  ldd,5,sm	0x0, [ _f64,_lts2 c +40 ], %db[42]	! kernel.c : 8
	}
	! <0010>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 b +40 ], %db[33]	! kernel.c : 8
	  ldd,5,sm	0x0, [ _f64,_lts2 a +40 ], %dg30	! kernel.c : 8
	}
	! <0011>
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 c +48 ], %db[40]	! kernel.c : 8
	  ldd,2,sm	0x0, [ _f64,_lts2 b +48 ], %db[31]	! kernel.c : 8
	  fmul_subd,3,sm	%dg25, %dg24, %dg26, %dr3			! kernel.c : 9
	  fmul_subd,4,sm	%dg22, %dg21, %dg23, %dg31			! kernel.c : 9
	  faddd,5,sm	%dg20, %dg16, %dg20				! kernel.c : 8
	}
	! <0012>
	{
	  ldd,2,sm	0x0, [ _f64,_lts2 c +56 ], %db[38]	! kernel.c : 11
	  ldd,3,sm	0x0, [ _f64,_lts0 a +48 ], %dr4	! kernel.c : 8
	  fmul_subd,4,sm	%db[37], %dg27, %dg28, %db[16]			! kernel.c : 9
	}
	! <0013>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 b +56 ], %db[29]	! kernel.c : 11
	  ldd,5,sm	0x0, [ _f64,_lts2 a +56 ], %dr5	! kernel.c : 11
	}
	! <0014>
	{
	  rwd,0	_f64,_lts0 0x20f12000000010, %lsr	! kernel.c : 7
	  ldd,2,sm	0x0, [ _f64,_lts2 c +64 ], %db[36]	! kernel.c : 11
	  fmul_subd,3,sm	%db[35], %dg18, %dg29, %db[14]			! kernel.c : 9
	}
	! <0015>
	{
	  rwd,0	_f16s,_lts0lo 0x10, %lsr1		! kernel.c : 7
	  fmuld,1,sm	%dg23, %dg22, %dg23				! kernel.c : 8
	  fmuld,2,sm	%dg26, %dg25, %dg26				! kernel.c : 8
	  ldd,3,sm	0x0, [ _f64,_lts1 b +64 ], %db[27]	! kernel.c : 11
	  fmul_subd,4,sm	%db[33], %db[42], %dg30, %db[12]			! kernel.c : 9
	  faddd,5,sm	%dg17, %dr1, %dr6				! kernel.c : 10
	}
	! <0016>
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 a +64 ], %dr8	! kernel.c : 11
	  addd,1	0x0, [ _f64,_lts2 d ], %dr9		! kernel.c : 7
	  faddd,3,sm	%dg20, %dr2, %dr7				! kernel.c : 11
	}
	! <0017>
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 c +72 ], %db[34]	! kernel.c : 11
	  aaurwd,2	%dr9, %aad1				! kernel.c : 7
	  fmul_subd,3,sm	%db[31], %db[40], %dr4, %db[10]			! kernel.c : 9
	  ldd,5,sm	0x0, [ _f64,_lts2 b +72 ], %db[25]	! kernel.c : 11
	}
	! <0018>
	{
	  addd,1	0x0, [ _f64,_lts0 c +104 ], %dr9	! kernel.c : 7
	  addd,2	0x0, [ _f64,_lts2 b +104 ], %dr10	! kernel.c : 7
	  fmul_subd,3,sm	%db[29], %db[38], %dr5, %db[8]			! kernel.c : 9
	}
	! <0019>
	{
	  faddd,0,sm	%dg23, %dg21, %dg23				! kernel.c : 8
	  fmuld,1,sm	%dg28, %db[37], %dg28				! kernel.c : 8
	  faddd,2,sm	%dg26, %dg24, %dg26				! kernel.c : 8
	  faddd,3,sm	%dg31, %dr1, %dr11				! kernel.c : 10
	  addd,4	0x0, [ _f64,_lts0 a +104 ], %dr12	! kernel.c : 7
	  fdivd,5,sm	%dg20, %dr6, %dr6				! kernel.c : 10
	}
	! <0020>
	{
	  aaurwd,2	%dr9, %aaind1				! kernel.c : 7
	  faddd,3,sm	%dr3, %dr1, %dr13				! kernel.c : 10
	  faddd,4,sm	%db[16], %dr1, %dr14				! kernel.c : 10
	  aaurwd,5	%dr10, %aaind2				! kernel.c : 7
	}
	! <0021>
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 a +72 ], %dr9	! kernel.c : 11
	  fmul_subd,1,sm	%db[27], %db[36], %dr8, %db[6]			! kernel.c : 9
	  aaurwd,2	%dr12, %aaind3				! kernel.c : 7
	  ldd,5,sm	0x0, [ _f64,_lts2 c +80 ], %db[32]	! kernel.c : 11
	}
	! <0022>
	{
	  bap					! kernel.c : 7
	  ldd,0,sm	0x0, [ _f64,_lts0 b +80 ], %db[23]	! kernel.c : 11
	  ldd,2,sm	0x0, [ _f64,_lts2 a +80 ], %db[50]	! kernel.c : 11
	  faddd,4,sm	%db[14], %dr1, %dr10				! kernel.c : 10
	}
	! <0023>
	{
	  faddd,0,sm	%dg28, %dg27, %dg28				! kernel.c : 8
	  faddd,1,sm	%dg23, %dr2, %dr12				! kernel.c : 11
	  faddd,2,sm	%dg26, %dr2, %dr16				! kernel.c : 11
	  faddd,4,sm	%db[12], %dr1, %dr15				! kernel.c : 10
	  ldd,5,sm	0x0, [ _f64,_lts0 c +88 ], %db[30]	! kernel.c : 11
	}
	! <0024>
	{
	  ldd,3,sm	0x0, [ _f64,_lts0 b +88 ], %db[21]	! kernel.c : 11
	  ldd,5,sm	0x0, [ _f64,_lts2 a +88 ], %db[48]	! kernel.c : 11
	}
	! <0025>
	{
	  ldd,0,sm	0x0, [ _f64,_lts0 c +96 ], %db[28]	! kernel.c : 11
	  ldd,2,sm	0x0, [ _f64,_lts2 b +96 ], %db[19]	! kernel.c : 11
	  faddd,4,sm	%db[10], %dr1, %dr17				! kernel.c : 10
	  fdivd,5,sm	%dg23, %dr11, %dr11				! kernel.c : 10
	}
	! <0026>
	{
	  fmuld,0,sm	%dr9, %db[25], %db[3]				! kernel.c : 8
	  fmul_subd,1,sm	%db[25], %db[34], %dr9, %db[4]			! kernel.c : 9
	  ldd,2,sm	0x0, [ _f64,_lts0 a +96 ], %db[46]	! kernel.c : 11
	  faddd,4,sm	%db[8], %dr1, %dr18				! kernel.c : 10
	}
	! <0027>
	{
	  nop 1
	  faddd,0,sm	%dg28, %dr2, %dr13				! kernel.c : 11
	  fmul_subd,1,sm	%db[23], %db[32], %db[50], %db[2]			! kernel.c : 9
	  fdivd,5,sm	%dg26, %dr13, %dr9				! kernel.c : 10
	}
	! <0029>
	{
	  nop 1
	  faddd,0,sm	%db[6], %dr1, %db[41]				! kernel.c : 10
	  fmuld,3,sm	%dg29, %db[35], %dg29				! kernel.c : 8
	  fdivd,5,sm	%dg28, %dr14, %dr14				! kernel.c : 10
	}
	! <0031>
	{
	  nop 1
	  fdivd,5,sm	%dg16, %dr7, %dg16				! kernel.c : 11
	}
	! <0033>
	{
	  fmuld,0,sm	%dr4, %db[31], %dg29				! kernel.c : 8
	  fmuld,1,sm	%dr5, %db[29], %dr4				! kernel.c : 8
	  fmuld,3,sm	%dr6, %dg20, %dg20				! kernel.c : 11
	  fmuld,4,sm	%dg30, %db[33], %dg30				! kernel.c : 8
	  faddd,5,sm	%dg29, %dg18, %db[17]				! kernel.c : 8
	}
	! <0034>
	{
	  nop 1
	  fdivd,5,sm	%dg21, %dr12, %db[49]				! kernel.c : 11
	}
	! <0036>
	{
	  fdivd,5,sm	%dg24, %dr16, %db[47]				! kernel.c : 11
	}
	! <0037>
	{
	  faddd,0,sm	%dg29, %db[40], %db[13]				! kernel.c : 8
	  fmuld,1,sm	%dr8, %db[27], %dg19				! kernel.c : 8
	  faddd,2,sm	%dr4, %db[38], %db[11]				! kernel.c : 8
	  fmul_addd,3,sm	%dg17, %dg19, %dg20, %dg17			! kernel.c : 11
	  faddd,4,sm	%dg30, %db[42], %db[15]				! kernel.c : 8
	}
	! <0038>
	{
	  faddd,3,sm	%db[17], %dr2, %dg20				! kernel.c : 11
	  fdivd,5,sm	%db[17], %dr10, %db[26]				! kernel.c : 10
	}
	! <0039>
	{
	  fmuld,3,sm	%dr11, %dg23, %dg21				! kernel.c : 11
	}
	! <0040>
	{
	  fdivd,5,sm	%dg27, %dr13, %db[45]				! kernel.c : 11
	}
	! <0041>
	{
	  faddd,0,sm	%dg19, %db[36], %db[9]				! kernel.c : 8
	  fmuld,4,sm	%dr9, %dg26, %dg23				! kernel.c : 11
	}
	! <0042>
	{
	  faddd,3,sm	%db[15], %dr2, %db[52]				! kernel.c : 11
	  fdivd,5,sm	%db[15], %dr15, %db[24]				! kernel.c : 10
	}
	! <0043>
	{
	  fmul_addd,3,sm	%dg31, %dg22, %dg21, %db[55]			! kernel.c : 11
	  fmuld,4,sm	%dr14, %dg28, %db[5]				! kernel.c : 11
	}
	! <0044>
	{
	  fdivd,5,sm	%db[13], %dr17, %db[22]				! kernel.c : 10
	}
	! <0045>
	{
	  fsubd,3,sm	%dg17, %dg16, %db[56]				! kernel.c : 11
	  fmul_addd,4,sm	%dr3, %dg25, %dg23, %db[53]			! kernel.c : 11
	}
	! <0046>
	{
	  nop 1
	  fdivd,5,sm	%db[11], %dr18, %db[20]				! kernel.c : 10
	}
	! <0048>
	{
	  fdivd,5,sm	%dg18, %dg20, %db[43]				! kernel.c : 11
	}
	! <0049>
	{
	  nop 4
	  disp	%ctpr1, .L99				! kernel.c : 11
	}
	! <0054>
	{
	  ct	%ctpr1				! kernel.c : 11
	}
	.align	8
.L394:
	! <0055>
	{
	  fapb	ct=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=3, asz=4, abs=0, disp=0
	  fapb	dpl=0, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=2, asz=5, abs=0, disp=0
	}
	! <0056>
	{
	  fapb	ct=1, dcd=0, fmt=4, mrng=8, d=0, incr=0, ind=1, asz=4, abs=16, disp=0
	}
.L99:							! kernel.c : 7
	! <0057>
	{
	  loop_mode
	  fmul_subd,3,sm	%db[21], %db[30], %db[48], %db[0]			! kernel.c : 9
	  fmuld,4,sm	%db[50], %db[23], %db[1]				! kernel.c : 8
	}
	! <0058>
	{
	  loop_mode
	  faddd,3,sm	%db[3], %db[34], %db[7]				! kernel.c : 8
	  faddd,4,sm	%db[4], %dr1, %db[39]				! kernel.c : 10
	  fdivd,5,sm	%db[9], %db[41], %db[18]				! kernel.c : 10
	}
	! <0059>
	{
	  loop_mode
	  fmuld,2,sm	%db[26], %db[17], %db[3]				! kernel.c : 11
	}
	! <0060>
	{
	  loop_mode
	  alc	alcf=1, alct=1			! kernel.c : 11
	  abn	abnf=1, abnt=1			! kernel.c : 11
	  ct	%ctpr1 ? %NOT_LOOP_END				! kernel.c : 7
	  fmul_addd,0,sm	%db[16], %db[37], %db[5], %db[51]			! kernel.c : 11
	  fsubd,1,sm	%db[55], %db[49], %db[54]				! kernel.c : 11
	  staad,2	%db[56], %aad1[ %aasti4 ]
	  incr,2	%aaincr0	! kernel.c : 11
	  faddd,4,sm	%db[13], %dr2, %db[50]				! kernel.c : 11
	  fdivd,5,sm	%db[42], %db[52], %db[41]				! kernel.c : 11
	  movad,0	area=1, ind=0, am=1, be=0, %db[26]	! kernel.c : 8
	  movad,1	area=0, ind=0, am=1, be=0, %db[44]	! kernel.c : 8
	  movad,3	area=0, ind=0, am=1, be=0, %db[17]	! kernel.c : 8
	}
							! kernel.c : 7
	! <0061>
	{
	  setwd	wsz = 0xa, nfx = 0x1, dbl = 0x0	! kernel.c : 7
	  adds,0	0x0, 0x0, %g16				! kernel.c : 7
	}
	! <0062>
	{
	  disp	%ctpr2, disp=0x0				! kernel.c : 7
	  aaurw,2	%g16, %aabf0				! kernel.c : 7
	}
	! <0063>
	{
	  ct	%ctpr3					! kernel.c : 7
	}
	.size	kernel, .- kernel
! -----------------------------------------------------------------------------
	.section .bss
	.global	a
	.type	a, #object
	.size	a, 0x80
	.align	16
a:
	.skip	0x80
! -----------------------------------------------------------------------------
	.global	b
	.type	b, #object
	.size	b, 0x80
	.align	16
b:
	.skip	0x80
! -----------------------------------------------------------------------------
	.global	c
	.type	c, #object
	.size	c, 0x80
	.align	16
c:
	.skip	0x80
! -----------------------------------------------------------------------------
	.global	d
	.type	d, #object
	.size	d, 0x80
	.align	16
d:
	.skip	0x80
! -----------------------------------------------------------------------------
	.weak	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026
	elbrus_optimizing_compiler_v1.29.16_Jan_22_2026 = 0x0
