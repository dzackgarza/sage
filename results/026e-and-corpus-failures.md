# 026E's primitive orbits, and the corpus failure ledger — corrected

Two corrections to the first version of this file: the retained failure ledger is a **history of
many runs**, not a snapshot of the latest one, and the 026E emit-path attribution was made without
the full traceback. Both are settled below from the corpus repository's own records.

## The ledger partitions by run, and the latest corpus run has no entries in it

16,111 failure entries across 249 shards at current main (`d8b98587`), by `(run_url,
database_revision)`:

| entries | run | database revision |
| --- | --- | --- |
| 10,914 | 40077222835 | `972cd798ea` |
| 4,977 | 40176964487 (2026-10-25) | `c2a89d4377` |
| 129 | (none recorded) | `dea30614e6` |
| 30 | 42326648686 | `78ef8ce628` |
| 24 | 42391523243 | `18abc0744e` |
| fewer | 42326648686 (`ad177ea3`, `97de3ec0`, `1c88196a`, `6d3ae3fc`), 41189978796 | |
| **0** | **42363689427** | — |

## What run 42363689427 actually failed on: the commit step, in all sixteen shards

From the run's own job records, every shard (0–15) passed steps 1–9 — including **"Compute and
certify uncertified card values"** — and failed step 10, **"Commit completed computations to
main"**. That is a Git-integration failure in the owner's workflow (sixteen shards pushing to one
branch), not a computation failure, and it is why the ledger gained no entries from it.

## The historical defects, each checked against current code

**`AttributeError: 'int' object has no attribute 'parent'`** — the largest block (10,842 entries,
from runs 40077222835 and others). This is sage-extensions#291, repaired by `240cd3f8`, which is
now pinned on `develop`; the owner contracts pass 12/12 at that provider locally
(results/owner-contracts-240cd3f8.log). Fixed, pinned, awaiting a published-image run.

**`TypeError: _OwnedAlgebraParent.__init__() got an unexpected keyword argument
'algebra_generating_family'`** — 4,975 entries, **all** from run 40176964487, database `c2a89d43`,
research `b7469ee7`, recorded 2026-10-25. The traceback's source frame is research's
`dzack_research/preamble/categories/algebras/free_algebras.py:254`, which passes the keyword to the
provider's `_OwnedAlgebraParent.__init__`. The provider gained that parameter on **2026-10-26**
(`c731175`, `544d940` in sage-extensions), a day *after* the run, and it is present at both
`240cd3f8` (line 5013) and current main (`4b740955`, where `free_algebras.py:299` passes it). So
this is **historical and already fixed upstream**, not an open defect; the ledger entry stays
`open` until a retry certifies the card.

**`TypeError: Object of type Cardinalities.parent_class is not JSON serializable`** — 16 entries,
from run 42326648686 at database `78ef8ce628`, research `e94f00da`. The complete stored traceback
is `sage_genus.py:293 _compute` -> `:253 _run` -> `:242 _emit` -> `json.dumps({..., **values})`,
failing at `when serializing dict item 'primitive_orbits'`, item `'O'`, item `'constant'`. The
value came from `VALUES["primitive_orbits"]`, which **at that revision** was
`lambda lattice: lattice.primitive_orbit_series()` — no conversion. From `9fa82dcb` onward it is
`lambda lattice: _orbit_series(lattice.primitive_orbit_series())`. So the emit path was the defect
and it has since been changed; what remains unproven is whether `_orbit_series` converts every
field the provider returns, and the ledger entry stays `open` until a retry certifies `026E`.

That supersedes the earlier statement that a "worker bypassed the emitter": the emitter is the
`VALUES` entry the traceback runs through.

**`RecursionError: maximum recursion depth exceeded`** — 3 entries, all run 42326648686, all
`integral.primitive_orbits`, on diagonal lattices:

   028Q  diag(2, -2, -2, -2, -2, -2, -2, -2, -2)          rank 9
   028R  diag(2, -2, -2, -2, -2, -2, -2, -2, -2, -2)      rank 10
   0125  U + (rank-8 block of -4/2 along the chain)        rank 10

with frames in `sage_extensions/categories/rings/ring_foundation.py` -> `semirings.py:265` ->
`group/magmas.py:880`. Reproducing 028Q against `240cd3f8` did not finish inside a 600 s probe
(no output, killed), so **whether current code still recurses is unverified**; the input and the
frames are exact and that is what an owning issue needs.

**The rest, without a cause claimed:** 223 entries carry no stderr (runner losses and budget ends),
142 record `worker or runner lost (recovered from exceeded)`, 43 record `certification budget
exhausted` (35 recovered), and about 28 are `numpy._ArrayMemoryError` for single allocations of
21.7–326 GiB — a computation's own size rather than a defect. None of these says anything about
whether a value is correct, and none is promoted to a defect here.
