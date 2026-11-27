// Snippet 3. Predicated execution: both branches compute, writeback is gated by predicate.
{
  // Compare values and write flags to predicates %pred0 and %pred1
  cmples,0 %r10, %r11, %pred0
  cmpgts,1 %r12, %r13, %pred1
  muls,2   %r14, %r15, %r20
  muls,3   %r16, %r17, %r21
}
{
  // Instructions execute conditionally based on predicates
  adds,0 %r20, %r21, %r30 ? %pred0
  subs,1 %r20, %r21, %r30 ? ~%pred0
  muls,2 %r20, %r12, %r31 ? %pred1
  adds,3 %r21, %r13, %r31 ? ~%pred1
}
{
  // Merge branches into the final result
  adds,0 %r30, %r31, %r40
}
