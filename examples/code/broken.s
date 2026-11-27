! THREE BUGS THE ASSEMBLER DOES NOT CATCH
! nex: src=none orc=18 err=6
!
! Check WHAT'S WRONG — line numbers are shown there:
!   · second division in cycle 1, while the divider is busy
!     until cycle 2;
!   · muls,2 — multiplication has no such channel,
!     it lives on ,0 ,1 ,3 ,4;
!   · results are read before they are ready
!     (division latency is 11 cycles).
!
! The last one is the most dangerous: the code assembles and computes
! the wrong result.
{
  sdivs,5 %r0, %r1, %r2
}
{
  sdivs,5 %r3, %r4, %r5
}
{
  muls,2 %r2, %r5, %r6
}
{
  adds,0 %r6, %r2, %r7
}
