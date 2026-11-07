# lattice-database #16/#17 in the published image: what actually ran

Executor record for lattice-database#16 and #17. Every command below ran inside the
published image (`ghcr.io/dzackgarza/sage@sha256:220293469c53…`, unpacked at
`~/sage-image/rootfs`) through `docker/sage-image.py --rootfs … run`, on a real checkout of
lattice-database with its real dependency graph — no synthetic package, no rewritten source.

The owner's scripts were run from the checkout itself:
`results/real-image-tests.sh` translated from `docker exec` to the image runner, and
`results/026e-real-adapter-request.sage.py` unmodified.

## Revisions, as imported

| what | revision | how it was established |
| --- | --- | --- |
| lattice-database | `33534455ab8147dbace2eba4a8757e2f255e028b` (main) | `git -C <checkout> rev-parse HEAD` |
| sage-extensions (provider) | `3e4812618ce0d5f67dc88959a161ac6ebeb75da2` | the lock pin, real clone, `rev-parse HEAD` |
| sage-indefinite-port | `991b88b095a42a1e3679569ea42328c900c120f6` | the lock pin, held; not moved |
| research | `dbf178cf30c1d26e5f98753c1d9cdbcc16ee3d25` | the lock pin |
| image | Sage 11.0.beta5, GAP 4.16.1, Julia 1.12.7 | `research-environment-check.py`'s own record |

One correction to the earlier probe records: the first run in this session bound the research
tree as an extracted `git archive` (no `.git`), and a `git -C <that tree> rev-parse HEAD`
printed **this repository's** commit because git walked up to the enclosing repository. The
revision of the research tree in force is `dbf178cf30`; the printed value was an artifact of
the extraction, not the pin. Later runs bound a real clone at the pin for exactly this
reason.

## The 026E adapter request — it emits a number

`results/026e-real-adapter-request.sage.py`, unmodified, `--chdir /repos/lattice-database`,
`PYTHONPATH=/repos/research/src:/repos/lattice-database/src`, exit **0**:

    {"tag": "026E", "by": "research preamble", "primitive_orbits": {"O": {"constant": 1, "z": [], "w": []}, "SO": {"constant": 1, "z": [], "w": []}, "Otilde": {"constant": 1, "z": [], "w": []}, "SOtilde": {"constant": 1, "z": [], "w": []}, "O+": {"constant": 1, "z": [], "w": []}, "SO+": {"constant": 1, "z": [], "w": []}, "Otilde+": {"constant": 1, "z": [], "w": []}, "SOtilde+": {"constant": 1, "z": [], "w": []}}}
    EMITTED_JSON {"tag": "026E", "by": "research preamble", "primitive_orbits": {"O": {"constant": 1, "z": [], "w": []}, "SO": {"constant": 1, "z": [], "w": []}, "Otilde": {"constant": 1, "z": [], "w": []}, "SOtilde": {"constant": 1, "z": [], "w": []}, "O+": {"constant": 1, "z": [], "w": []}, "SO+": {"constant": 1, "z": [], "w": []}, "Otilde+": {"constant": 1, "z": [], "w": []}, "SOtilde+": {"constant": 1, "z": [], "w": []}}}
    CONSTANT_IS_FINITE 1

Its assertions passed: `constant.is_finite()`, `int(constant) == constant.cardinality()`,
and `json.loads(line)["primitive_orbits"]["O"]["constant"] == 1`. So the adapter's
`primitive_orbits` emitter converts the `Cardinalities.parent_class` element the provider
returns (results/latticedb-026e-cardinality.md) into its exact number, and the emitted JSON
round-trips. The eight groups carry `constant 1` and empty `z`/`w` on this card.

The script's last line, `NONFINITE_CONVERSION aleph0`, is the synthetic `Infinite` probe the
owner has already been sent back for; it is **not** evidence for anything and is excluded.

The run took 29 minutes wall under a loaded host (load 16, ~1.2 GB MemAvailable, other
projects' Sage/Julia jobs active); the same computation took about 7 minutes on a quiet box,
so the duration says nothing about the algorithm.

## The database's own tests

`python -m pytest -q tests/test_failures.py tests/test_merge.py tests/test_persist.py`
at `33534455`: **2 failed, 11 passed in 43.55 s**.

1. `test_a_ledger_entry_must_be_in_the_shard_of_its_own_tag` — `DID NOT RAISE ValueError`
   at the block that puts **two computations of tag `0012`** in `0012`'s own shard and
   expects the loader to reject them. Both keys hash to shard `2f`, so accepting both is
   correct; the expectation is false. Measured directly in the image:

       shard of 0012 = 2f | shard of the entry = 2f | shard of '0012 genus_symbol' = 2f
       own shard, one entry      -> ['0012 integral.genus_symbol']
       wrong shard               -> ValueError: .../failures/00.yaml: 0012 integral.genus_symbol belongs to the shard 2f, not 00
       two operations on 0012    -> both kept, no error: ['0012 genus_symbol', '0012 integral.genus_symbol']

   The earlier block — an entry in another card's shard — does raise, with the message the
   test matches, so the loader's shard enforcement is present and correct; only the
   two-computations expectation was wrong.

2. `test_shards_push_progress_repeatedly_without_touching_their_worktrees` — the test writes
   failure entries whose attempts carry only `reason`; `failures.Attempt` requires
   `hash, gram_tensor, reason, stderr, seconds, recorded_at, run_url, database_revision,
   research_revision`, so `failures.load` raises a pydantic `ValidationError` with eight
   missing-field errors. A stale fixture against the current model.

Both are properties of the checkout, not of the image: neither path imports Sage, the port or
the provider.

## The corrected revision, rerun

At `ca17c53ef0b8dd4328b93083c1ef049ba2b871f1` (main), same command, only the two modules
that failed: **2 failed, 8 passed in 36.10 s**. Both fixtures were rewritten and both still
fail, each for a new and concrete reason:

1. `test_a_ledger_entry_must_be_in_the_shard_of_its_own_tag` — the fix asserts that two
   computations of `0012` are both kept, which is right, but it removed the line that emptied
   the *misplaced* copy written earlier in the same test, so that copy is still in
   `failures/00.yaml` when the assertion runs:

       ValueError: .../failures/00.yaml: 0012 integral.genus_symbol belongs to the shard 2f, not 00

   The assertion is correct and the fixture ordering defeats it: the misplaced file has to be
   emptied (or the two lawful keys written in their own root) before it.

2. `test_shards_push_progress_repeatedly_without_touching_their_worktrees` — the new
   `failure_attempt()` passes `recorded_at` as
   `datetime(2026, 11, 7, tzinfo=UTC).isoformat()`, a string, and the model wants a
   `datetime`:

       `0001 integral.genus_symbol`.attempts.0.recorded_at
         Input should be a valid datetime [type=datetime_type, input_value='2026-11-07T00:00:00+00:00', input_type=str]

   Passing the `datetime` object itself is enough; `yaml.safe_dump` writes it as a timestamp
   and the loader reads a `datetime` back, which is what the passing tests in
   `test_failures.py` already do.

Both are awaiting the owner's repair; the same two tests should be rerun unchanged once it
lands.

## The shard slice of #17

`failures.load` reads one YAML per group and enforces both invariants in `load` itself
(`failures.py:55-66`): an entry whose card's shard differs from the file's name raises
`… belongs to the shard …`, and an entry seen in two shards raises `… is also in another
shard`. `failures.group("0012 integral.genus_symbol")` and
`failures.group("0012 genus_symbol")` both return `2f`, so a card's several computations
share one shard file by construction, as `save` writes them.

## Not done here, and why

- **The ordinary certify path has not completed.** `python -m latticedb certify --tag 026E
  --phase fields --minutes 30 --workers 1` was admitted once and stopped before its first
  work unit: the host was at load 16 with ~1.2 GB MemAvailable and other projects' jobs
  running, so a 30-minute run would have competed with them and been cut by its own deadline.
  It needs one clear window; nothing about it is known to be broken.
- **The recovery verifier was not run.** `results/verify-recovered-values.py` and
  `results/reverify.sh` are for the next owner revision: at `ca17c53e` the verifier still has
  the derive-branch parsing defect and the unused failure-history data the owner is fixing,
  and running it now would measure those rather than the artifacts.
- **#15 stays blocked** by sage-extensions#291: the owner-contract suite fails
  `test_root_and_theta_catalogue_invariants_are_owned_by_the_lattice` at
  `definite_lattices.py:294` (`'int' object has no attribute 'parent'`), which is the
  provider's, not the image's (results/consumer-acceptance-rehearsal.md).
