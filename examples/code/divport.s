! DIVIDER MONOPOLY — exclusive port ,5
! nex: src=22 orc=18 err=0
!
! Division lives ONLY on channel ,5 (the assembler rejects
! the other five), holds the port for 2 cycles, and delivers the result
! after 11. This is a hardware lower bound that cannot be beaten.
!
! Meanwhile, the addition chain at the bottom is independent of division:
! the compiler placed it AFTER, even though while the divider
! is busy, the other channels are idle. Exact search hoists
! it to the start — that is where the headroom comes from.
{
  sdivs,5 %r0, %r1, %r2
}
nop 1
{
  sdivs,5 %r3, %r4, %r5
}
nop 11
{
  adds,0 %r10, %r11, %r20
}
{
  adds,0 %r20, %r12, %r21
}
{
  adds,0 %r21, %r13, %r22
}
{
  muls,1 %r2, %r5, %r6
}
nop 3
{
  adds,0 %r6, %r22, %r7
}
