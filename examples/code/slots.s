! IDLE SLOTS — eight multiplications issued one per cycle
! nex: src=15 orc=8 err=0
!
! muls can execute on FOUR channels: ,0 ,1 ,3 ,4 —
! verified with the assembler. The compiler placed all eight on
! ,0, one operation per cycle: the schedule is valid,
! computes correctly, and utilizes only 17% of machine slots.
!
! F5 — run, F6 — rewrite from oracle.
{
  muls,0 %r10, %r11, %r20
}
{
  muls,0 %r12, %r13, %r21
}
{
  muls,0 %r14, %r15, %r22
}
{
  muls,0 %r16, %r17, %r23
}
{
  muls,0 %r18, %r19, %r24
}
{
  muls,0 %r30, %r31, %r25
}
{
  muls,0 %r32, %r33, %r26
}
{
  muls,0 %r34, %r35, %r27
}
{
  adds,1 %r20, %r21, %r40
}
{
  adds,1 %r22, %r23, %r41
}
{
  adds,1 %r24, %r25, %r42
}
{
  adds,1 %r26, %r27, %r43
}
{
  adds,2 %r40, %r41, %r44
}
{
  adds,2 %r42, %r43, %r45
}
{
  adds,3 %r44, %r45, %r46
}
