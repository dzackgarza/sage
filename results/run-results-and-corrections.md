# The three runs, their actual results, and two corrections

Read from GitHub's own run and job records (runs API), not inferred from earlier assumptions.

## 42379122786 — the pinned image

`Research environment image`, revision `552169cece` (the provider pin), push, completed **failure**.
Job by job: `publish` **success**, `no-runtime` **success**, `zstd-probe`/`zstd-pull` skipped,
`consumer-acceptance` **failure** — and inside that job:

    step  8  Construct T_Co and compute its O(T_Co) generators            failure
    step  9  Run sage-extensions' isotropic-line-orbit suite              skipped
    step 10  Certify lattice-database card 6JRR                           skipped
    step 12  Reproduce the stage-1 research records                       skipped
    step 13  Reproduce the stage-1 known-family records                   skipped
    step 14  Run lattice-database's owner contracts                       skipped
    step 15  Read the I_{1,8} chamber with CoxIter                        skipped

So an image **was** published at the pin and the runtime checks passed, but the acceptance job
aborted at its first substantive step. **#15's owner contracts and #18's chamber step have no
published-image result yet** — they did not run, rather than failing. Job logs are admin-only
(`403 Must have admin rights to Repository`), so the deciding line for step 8 has to be pasted;
without it I will not guess at a cause. A candidate worth checking first: step 8 now begins with
the provenance assertion added in `f836a1dce1`, which compares each installed checkout's `HEAD`
with `/sage/uv.lock` — and this is the first image whose lock pins a *revision* rather than a
branch.

## 42363689427 — the corpus certification

`certify`, schedule, revision `dde534ecd9d7c61af3800d20eb1635bc7541f38a`, created and started
**10:22:31Z**, completed **failure**: `plan` success, and **all sixteen shards failed**
(`certify (14, 16)`, `(6, 16)`, … `(5, 16)`). Two corrections follow from that record:

1. **It does not carry the `240cd3f8` repair.** It began at 10:22:31Z; the provider commit was
   pushed and pinned hours later (the pin commit `552169cece` is 13:54:55Z). Whatever provider the
   run used, it is not the repaired one, and the local binding has nothing to do with it. So the
   claim that "the production corpus run already includes 6JRR *under the repair*" was wrong: the
   plan covers every card, but this run predates the repair — and its shards failed besides.
2. **A log with no completed computation does not show that `records.derive` was reached.** It
   shows only that no computation completed. Loading the corpus, selecting the card, starting the
   worker and building the request all precede `derive` (`cli.py` → `genus.certify` →
   `sage_genus._compute`), and my single-worker attempt was killed at 356 s with 6,155 MiB in one
   worker and **no** printed line — which is consistent with being anywhere in that prefix,
   including setup.

**Still owed for #17:** an actual production attempt at the repaired provider. Neither run so far
supplies one — 42363689427 predates the pin and failed; the pinned image's 6JRR step was skipped.
The prepared check is unchanged: `certify --tag 6JRR --minutes 20 --workers 1 --root <corpus>` at
corpus `d1711db05f`, provider `240cd3f8`, and the evidence is a `6JRR …` entry in
`certificates/e1.yaml`, or 6JRR in `exceeded.yaml` / `failures/`.

## 42370898252 — the dispatched 026E certification

`certify`, workflow_dispatch, revision `9fa82dcb80f273d47184ca56671edb85b1fc4b21`, started
12:05:03Z, completed **success**: `plan` success and `certify (026E, 0, 1)` success. The ordinary
026E certification the orchestrator dispatched therefore completed in its production environment,
at the provider pinned then (`3e4812618c`), which is before the repair — a result for #16's card,
not for the repaired provider.

## Step 8's actual failure, from the job log

The log root supplied (`results/image-42379122786-failed.log`) shows the provenance block doing
what it was written to do for the port, and then dying on the provider:

    sage-indefinite-port: imported from /repos/sage-indefinite-port/src/sage_indefinite_port/__init__.py
    sage-indefinite-port: checkout /repos/sage-indefinite-port at 991b88b0…, held 991b88b0…
    sage-extensions: direct_url.json commit_id None
    subprocess.CalledProcessError: Command '['git', '-C', '/__w/sage/sage', 'rev-parse', 'HEAD']' returned non-zero exit status 128.

Two things are established and one is not. **Established:** `sage_extensions` was imported from
`/__w/sage/sage`, the workflow's own checkout — the step above installs it editable to test the
published image against live consumer code — not from the image's `/repos/sage-extensions`; and the
port's provenance was read correctly, both sides `991b88b0`. **Not established:** why git answered
128. The traceback prints the command and the status but not git's stderr, so "dubious ownership"
would be a guess, and suppressing the check would hide whichever cause it is.

**The defect is mine, and it is a path assumption, not a check to relax.** `checkout_of` found the
workspace's `.git` and `head()` treated that checkout as if it were the image's — so the step both
asked the wrong question of the wrong tree and died when git refused to answer. The repair keeps
every assertion where it belongs:

* a checkout under `/repos/` is the image's, and its revision is still **asserted** against the
  image's `/sage/uv.lock` (the port: `991b88b0`, as before);
* a checkout elsewhere is the job's own, so its revision is **reported** as what ran, not held to
  the image's pin;
* `git`'s own words are printed when it refuses, instead of becoming an uncaught
  `CalledProcessError`.

Reproduced in the image, three cases:

| case | provider imported from | result |
| --- | --- | --- |
| the image's copies | `/repos/sage-extensions` | both revisions asserted against the lock, pass |
| a workspace checkout | `/__w/sage/sage/src/…` at `240cd3f8`, held `7b222e86` | reported, **not** asserted, exit 0 |
| a checkout git will not describe | `/__w/sage/sage` | `revision unreadable here: fatal: not a git repository …`, reported, exit 0 |

The third case reproduces the exit-128 *class* of failure; it does not identify the CI's cause,
which the log does not carry.

## 026E's certificate: the field #16 is about is not in it

`git show 7e0a202a` — the commit that run pushed — changes **only `exceeded.yaml`**, and only two
`seconds` values (`0016 root_span.norms`, `0016 root_span.roots`, 3634 -> 5437). It mints nothing.
At that commit, card `026E` carries **15 certifications** and its shard `f1` holds the same 15
entries, and **`integral.primitive_orbits` is not among them**:

    automorphisms.automorphism_group_generator_morphisms, derive, form.integer_valued,
    integral.anisotropic_primes, integral.discriminant_form, integral.elementary_primes,
    integral.genus_class_count, integral.genus_symbol, integral.hyperbolic_index,
    integral.local_densities, integral.local_representations, integral.modular_scale,
    integral.overlattice_count, integral.spinor_genera, integral.spinor_genus_count

So that run is **not** evidence for #16, exactly as the review concluded: a green job whose only
push is an `exceeded.yaml` delta has not certified the field. `primitive_orbits` is not one of the
semi-decisions (`SEMI_DECISIONS = {roots, norms, reflective, regular, spinor_regular}`), so the
fields phase should have asked for it, and why it did not — or was not certified — is not yet
established here. The run's log, which prints `modular_scale`, `anisotropic_primes`,
`local_representations` and `local_densities` but no `primitive_orbits`, is the evidence that will
settle it.

