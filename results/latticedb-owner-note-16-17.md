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

---

## Follow-up on `9fa82dcb` — the suites pass, and the old verifier rejects valid data

Executed at `9fa82dcb80f273d47184ca56671edb85b1fc4b21` on a real checkout in the supported
image, with the provider at the lock pin and the retained artifacts of run 42326648686 copied
unmodified into `attachments/you-work-the-github-s6pa/extracted/` (60 tag directories; the old
verifier's SHA256 matches the copy in the lattice-database project's attachments).

**Your storage and persistence modules are green: 13 passed in 31.08 s** —
`tests/test_failures.py tests/test_merge.py tests/test_persist.py`. Both fixtures that failed at
`33534455` and again at `ca17c53e` now pass: `0012`'s two computations stay together in shard
`2f` while a misplaced duplicate is still rejected, and `failure_attempt()` supplies a real
`datetime`.

**The recovery regression passes with the revision's own verifier**:

    results/regression-recovery-defects.py        → exit 0, PASS
    # original attempt removed from a copy:
      0066 integral.primitive_orbits: original failure attempt d75a9ad628461d9f is missing
    # on-card derive deleted in a second copy:
      0066: certifications.derive missing
      0066 derive: on-card certification is missing although the artifact supplies the
                   corresponding certificate

Both rejections name what they object to, and the preserved-later attempt survives the first
mutation. `tests/test_verify_recovery.py` passes too (1 test, 110 s), and
`results/recover-42326648686.py` reconciles every artifact with 0 conflicts across all 60 tags.

**The old verifier, on unmodified recovered data, rejects it** — which is the defect 9fa
corrects, and it is why the runner cannot reach its mutation stages with that verifier:

    $ verify-recovered-old.py artifacts
    1 recovered artifacts verified against their own patches
    1 problems found
       0066 integral.primitive_orbits: original failure attempt d75a9ad628461d9f is missing
    the actual recovered data should verify; exit 1

(An earlier attempt of mine passed that verifier as a relative path, which the runner resolves
from its temporary copy; that failed on a missing file and says nothing about the verifier. The
transcript here is the absolute-path run.)

**What I did not complete:** the verifier over all 60 tags. It ran under a 1800 s bound and
reached it (`exit 124`, 17:25 CPU, one thread, RSS 1.35 GB), and the verifier prints only at the
end, so there is no partial finding. That establishes neither agreement nor disagreement and does
not imply a longer run would pass — which is why the full verification is yours to run in the
supported image, and I am not starting a duplicate. #17 stays open on it.
