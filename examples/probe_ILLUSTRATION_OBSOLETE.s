! ============================================================================
! WARNING: THIS IS NOT COMPILER OUTPUT. This file is a hand-drawn illustration
! created for the FIRST (incorrect) version of the model: divisions are spaced
! 13 cycles apart and multiplications 8 cycles apart to "illustrate monopoly".
!
! Testing with real lcc refuted this: divisions issue every 2 cycles,
! and multiplications encode across four channels, issuing every cycle.
! Real compiler output is nearby: examples/probe.s and examples/probes/.
!
! Kept intentionally as an exhibit: it is why wrong numbers entered the model.
! Do not use as a data source.
! ============================================================================
! Excerpt of lcc .s output for e2k (function body, abbreviated).
! Corresponds to experiment probe.c: four independent divisions and four
! independent multiplications over volatile arrays.
!
! Machine layout shown: divisions run on channel ,5 every 13 cycles,
! multiplications on channel ,0 every 8 — exclusive divider and multiplier,
! each on its own port. The compiler encodes stalls with explicit `nop N`.
	.text
	.global probe_body
probe_body:
{
	ldw,0	%r10, %r20
	ldw,2	%r11, %r21
	ldw,3	%r12, %r22
}
{
	ldw,0	%r13, %r23
	ldw,2	%r14, %r24
}
	nop 1
{
	sdivs,5	%r20, %r21, %r40
	muls,0	%r22, %r23, %r50
	adds,1	%r20, %r21, %r30
}
{
	adds,1	%r30, %r24, %r31
}
	nop 6
{
	muls,0	%r24, %r20, %r51
}
	nop 4
{
	sdivs,5	%r22, %r23, %r41
}
	nop 2
{
	muls,0	%r21, %r22, %r52
}
	nop 7
{
	muls,0	%r23, %r24, %r53
}
	nop 1
{
	sdivs,5	%r24, %r20, %r42
}
	nop 12
{
	sdivs,5	%r21, %r22, %r43
}
	nop 12
{
	adds,1	%r40, %r41, %r60
	adds,2	%r42, %r43, %r61
	adds,3	%r50, %r51, %r62
}
{
	adds,1	%r52, %r53, %r63
	adds,2	%r60, %r61, %r64
}
{
	adds,1	%r62, %r63, %r65
	adds,2	%r64, %r31, %r66
}
{
	adds,1	%r65, %r66, %r67
}
{
	stw,3	%r67, %r70
}
