! LOADS ON A SINGLE CHANNEL — an avoidable queue
! nex: src=10 orc=7 err=0
!
! Loads can execute on ,0 ,2 ,3 ,5 and return a value
! after 5 cycles. Here all four are placed on ,0 — meaning
! they are serialized unnecessarily: the addresses are independent,
! so there is no reason for them to wait on each other.
!
! Exact search packs them into a single cycle across four channels, and
! all subsequent arithmetic shifts 3 cycles earlier.
{
  ldw,0 %r10, %r20
}
{
  ldw,0 %r11, %r21
}
{
  ldw,0 %r12, %r22
}
{
  ldw,0 %r13, %r23
}
nop 2
{
  adds,1 %r20, %r21, %r30
}
nop 1
{
  adds,1 %r22, %r23, %r31
}
{
  adds,1 %r30, %r31, %r32
}
