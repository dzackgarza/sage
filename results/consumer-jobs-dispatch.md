# Consumer checks: the patch to publish, and the dispatch that runs them

`results/consumer-jobs-workflow.patch` — 303 lines, 203 insertions and 22 deletions in
`.github/workflows/research-environment-image.yml`, sha256
`d2f655d2da5f95b6dc2c18d1ec6b470f15085564c011b8552c86e9c3542ec4cf`.

It applies to the workflow as published at `6ec2c55c6668462b56e8c5ef2c5265547a876626` — checked by
applying it to that exact file, which reproduces this repository's local copy byte for byte
(sha256 `20c8566e5faf5616f4c642fb9ac1b950858e3ff6ca1dc253dfe328ce9093a6a3`).

## What it changes

* **Five jobs instead of one.** `consumer-acceptance` was cancelled at 60:04 in run 42407502517
  ("exceeded its one-hour maximum") after T_Co 14:13, the isotropic suite 9:08 and 6JRR 21:03; the
  stage-1 records were interrupted and the known-family records, owner contracts and CoxIter never
  ran. They are now:

  | job | budget | steps |
  | --- | --- | --- |
  | `consumer-mathematics` | 45 min | four-spinor (gated on `sage_source_sha`), T_Co, isotropic suite |
  | `consumer-certify` | 45 min | 6JRR certification, upload |
  | `consumer-records` | 40 min | stage-1 and known-family reproductions, upload |
  | `consumer-contracts` | 30 min | the provider's owner contracts (#15) |
  | `consumer-chamber` | 20 min | CoxIter on the I_{1,8} chamber (#18) |

  All fourteen step bodies are carried over unchanged — `run`, `uses`, `with`, `env` and `if`
  compared field by field — so every assertion is the one that was there before.
* **The 6JRR artifact carries its evidence.** The upload now takes
  `/repos/lattice-database/lattices/6JRR.md` and `/tmp/certify-6JRR.log` beside
  `certificates/`, so the seven new certificate keys root found in artifact 13590945084 can be
  checked against the card values that produced them, and the child's exit read directly. The step
  still does not gate on that exit, by design — it reports, and now the report travels.
* **A named image, no rebuild.** `workflow_dispatch` gains `image` and
  `expected_source_revision`; when an image is given, `publish` is skipped
  (`if: inputs.image == ''`) and each consumer job runs in that image, guarded by
  `if: ${{ always() && (inputs.image != '' || needs.publish.result == 'success') }}`. The
  published-image assertion needs a source revision, and with no publish there is no output to
  read: `expected_source_revision` supplies it (`087adc21c8…` for the image above, which its
  `/sage/.spinor-source-revision` records), and the step fails with that sentence rather than
  comparing against an empty string. It stays distinct from `sage_source_sha`, which applies an
  isolated patch and enables the four-spinor test.

## The dispatch

Against the image this repository already published
(`ghcr.io/dzackgarza/sage@sha256:0fe2ebf4e6ffb4a55117d379ff0e9de3028f106023aceb4518d813aec69d1d7e`,
the digest `develop` resolved to after run 42407502517):

    gh workflow run research-environment-image.yml --ref develop \
      -f image=ghcr.io/dzackgarza/sage@sha256:0fe2ebf4e6ffb4a55117d379ff0e9de3028f106023aceb4518d813aec69d1d7e \
      -f expected_source_revision=087adc21c8068e8f68e500cd21e41e9b62074f6a

or, equivalently, `POST /repos/dzackgarza/sage/actions/workflows/research-environment-image.yml/dispatches`
with `{"ref": "develop", "inputs": {"image": "ghcr.io/dzackgarza/sage@sha256:0fe2ebf4…",
"expected_source_revision": "087adc21c8068e8f68e500cd21e41e9b62074f6a"}}`.

Nothing is built, nothing is published, and the five jobs run independently: a failure or a slow
call in one no longer skips or delays the others.

## What is left to CI

The results themselves — T_Co's numbers, the twelve owner contracts, the chamber's labelled
adjacency comparison, the record reproductions, and 6JRR's child status with its card. The owner
contracts go to #15, the chamber to #18, the certification evidence to #17, and any concrete
failure to its owning repository.
