# 026E's primitive orbits, and the corpus run's distinct failures

Both read from the corpus repository's own records at current main (`d8b98587`), not from logs.

## 026E: the field was requested, and it failed with the original #16 error

The queue builds the request for `026E` as

    fields requested: ['primitive_orbits', 'modular_scale', 'anisotropic_primes',
                       'local_representations', 'local_densities']
    searches phase: False

so `integral.primitive_orbits` is **first in the list, not absent** — the earlier suggestion that
it was "never selected" is wrong. `applies('primitive_orbits')` is `True` for this card, and it is
not a semi-decision.

What happened to it is in the failure ledger, in all 249 shards at `7e0a202a` and again at
`19471f78e7` and at current main `d8b98587`:

    026E integral.primitive_orbits   disposition: open   reason: exit status 1
    stderr: raise TypeError(f'Object of type {o.__class__.__name__} '
            f'is not JSON serializable')
            TypeError: Object of type Cardinalities.parent_class is not JSON serializable
            when serializing dict item 'constant'
            when serializing dict item 'O'
            when serializing dict item 'primitive_orbits'

That is the original #16 signature, in production, unchanged since the run. So:

* the four fields the job printed and certified are the *rest* of that request — the worker went on
  after `primitive_orbits` failed, which is why the job is green;
* **#16 is not fixed in production.** The adapter's `VALUES['primitive_orbits']` emitter does
  convert the constant, as the local run showed, but the worker serialises the provider's raw
  value to JSON on the way back and hits the `Cardinalities.parent_class` there. The defect is in
  the database's worker serialisation, not in the emitter, and it is the owner's to fix.

## The corpus run's failures, by cause

16,111 failure entries across 249 shards (`open` 16,104, `resolved` 7), grouped by their recorded
stderr:

| entries | last stderr line | owner |
| --- | --- | --- |
| 10,842 | `AttributeError: 'int' object has no attribute 'parent'` | sage-extensions#291 — the defect the reviewed `240cd3f8` repairs; this run predates it |
| 4,975 | `TypeError: _OwnedAlgebraParent.__init__() got an unexpected keyword argument 'algebra_generating_family'` | sage-extensions, a **different** defect from #291: an owned-algebra constructor signature |
| 223 | (no stderr) | runner losses and budget ends |
| 16 | `when serializing dict item 'primitive_orbits'` | lattice-database #16, above |
| ~28 | `numpy._core._exceptions._ArrayMemoryError: Unable to allocate 21.7–326 GiB for an array of shape (54000, 54000) …` | the computation's own size, not a defect; the owner's memory policy recorded them |
| 3 | `RecursionError: maximum recursion depth exceeded` | unassigned |
| 142 | reason `worker or runner lost (recovered from exceeded)` | infrastructure |
| 43 | reason `certification budget exhausted` (35 recovered) | budget, as designed |

So the 16 shards' failure is not one thing and has no blanket quota explanation: the overwhelming
majority is #291 (repaired by the pin now on `develop`), a second large block is an
`_OwnedAlgebraParent` constructor mismatch, a handful are #16, and the rest are memory, budget and
runner losses.
