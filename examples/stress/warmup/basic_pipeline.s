! WARMUP: short pipeline, three kinds of pressure at once
! nex: src=11 orc=9 err=0
!
! Hand-written for this project — NOT lcc output (see docs/REAL_VS_SYNTH.md,
! which draws an honest boundary between real code and synthetic cases). Placed in
! examples/stress/warmup/ — two levels deep under examples/, specifically
! to test the file browser (^E): navigate here via examples/ -> stress/ -> warmup/.
!
! Inside: four independent multiplications (can be packed across channels ,0 ,1
! ,3 ,4 in one cycle), a 5-cycle-latency load before its consumer, and
! a short addition chain leading to the final result.
{
  ldw,0 %r1, %r2
  muls,1 %r10, %r11, %r20
  muls,3 %r12, %r13, %r21
  muls,4 %r14, %r15, %r22
}
{
  muls,0 %r16, %r17, %r23
}
{
}
{
}
{
}
{
  adds,1 %r20, %r21, %r30
  adds,3 %r22, %r23, %r31
}
{
  adds,0 %r2, %r1, %r32
}
{
  adds,1 %r30, %r31, %r33
}
{
  adds,0 %r32, %r33, %r34
}
{
  stw,2 %r34, %r0
}
