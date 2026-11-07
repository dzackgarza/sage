# Comment for lattice-database#16/#17 — to relay

Posted by the orchestrator; this repository cannot write issues. Evidence:
`results/latticedb-16-17-real-runtime.md`, full log `results/latticedb-16-17-run.log`,
in `dzackgarza/sage` at `432ddece95ffa828d8d68fc553bd987024b0dcd5`.

---

Ran your `results/real-image-tests.sh` steps on a real checkout, in the published image
(`sha256:220293469c53…`, Sage 11.0.beta5, GAP 4.16.1, Julia 1.12.7), with the provider at
the lock pin rather than a synthetic package. Imported revisions:
lattice-database `33534455` (and `ca17c53e` for the rerun), sage-extensions
`3e4812618c`, sage-indefinite-port `991b88b0`, research `dbf178cf30`.

**#16 — the adapter emits the number.** `results/026e-real-adapter-request.sage.py` exits 0:

    {"tag": "026E", "by": "research preamble", "primitive_orbits": {"O": {"constant": 1, "z": [], "w": []}, "SO": {"constant": 1, "z": [], "w": []}, "Otilde": {"constant": 1, "z": [], "w": []}, "SOtilde": {"constant": 1, "z": [], "w": []}, "O+": {"constant": 1, "z": [], "w": []}, "SO+": {"constant": 1, "z": [], "w": []}, "Otilde+": {"constant": 1, "z": [], "w": []}, "SOtilde+": {"constant": 1, "z": [], "w": []}}}
    CONSTANT_IS_FINITE 1

`json.loads` round-trips it and the script's assertions pass, so the
`Cardinalities.parent_class` object is converted to its exact number. (The synthetic
`Infinite` line at the end of the script is excluded, as you asked.)

**#17 — the tests, on `33534455`:** 2 failed, 11 passed.
`test_a_ledger_entry_must_be_in_the_shard_of_its_own_tag` fails exactly where you said: both
`0012 integral.genus_symbol` and `0012 genus_symbol` hash to shard `2f`, so keeping both is
correct; the misplaced-shard block earlier in the same test does raise
`… belongs to the shard 2f, not 00`, so the loader's enforcement is intact.
`test_shards_push_progress_repeatedly_without_touching_their_worktrees` fails because its
attempts carry only `reason`; `failures.Attempt` requires nine fields.

**On `ca17c53e`, the two corrected fixtures still fail, each for a new reason:**

1. the ledger test keeps the misplaced copy in `failures/00.yaml` while asserting that both
   lawful keys load, so the leftover raises before the assertion can hold —
   `ValueError: …/00.yaml: 0012 integral.genus_symbol belongs to the shard 2f, not 00`.
   Emptying that file (or writing the two lawful keys in their own root) is enough.
2. `failure_attempt()` passes `recorded_at` as `datetime(...).isoformat()`; the model wants a
   `datetime`, and the ISO string is rejected:
   `Input should be a valid datetime [input_value='2026-11-07T00:00:00+00:00', input_type=str]`.
   Passing the `datetime` object matches what the passing tests in `test_failures.py` do.

Both will be rerun unchanged once repaired. **The ordinary `latticedb certify --tag 026E
--phase fields` has not completed yet** — it was admitted once and stopped before its first
work unit while the host was at load 16 with ~1.2 GB free; it needs one clear window. The
recovery verifier is being held for your next revision, per instruction.
