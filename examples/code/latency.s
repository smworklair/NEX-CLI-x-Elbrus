! DEPENDENCY CHAIN LIMIT — zero headroom, and that is the right answer
! nex: src=12 orc=12 err=0
!
! Three multiplications in a row, each waiting on the previous result.
! Multiplication latency is 4 cycles (measured along a chain of
! dependent operations), so 4+4+4 = 12 cycles, and
! there is nowhere to reorder them: the order is fixed by the code.
!
! That is what the tool reports: "no headroom". Idle cycles are not
! always a compiler flaw — sometimes they are the dependency
! chain length, in which case you must change the algorithm, not
! the schedule.
{
  muls,0 %r1, %r2, %r3
}
nop 3
{
  muls,0 %r3, %r4, %r5
}
nop 3
{
  muls,0 %r5, %r6, %r7
}
