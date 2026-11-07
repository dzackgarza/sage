# #14 consumer result for run 42362483952

The run published and its consumer-acceptance job failed. This is what its own output says,
compared with the current comparator, and what the run establishes about the revisions it
imported. The outputs are the run's uploaded artifact 13574428772 (`research-stage1-records`,
1804 bytes, zip sha256 `dd60d3beaf88fc047691020269df8d0282f8bcc747bb5c54a12e346dc25e8c71`),
kept unmodified under `results/run-42362483952/`:

    coble_isotropic_orbits.out          3ab1b0f8c8a7ad4a…
    coble_plane-half-f2.out             b32769d3d9ffae67…
    coble_I18_vinberg-chamber.out       6f2f3b00ddc06dcf…

## The revisions that actually ran

| what | revision | the evidence |
| --- | --- | --- |
| consumer image | index digest `sha256:db78c6de3d08ad0901dedacc90c8cb6e5ab65899af396bc63f9e6268e60718d9` | the run's own digest |
| sage-indefinite-port | `991b88b095a42a1e3679569ea42328c900c120f6` | the no-runtime job checks that index digest and reports `research sage-indefinite-port: 991b88b0… (checkout, lock 991b88b0…)` at 12:06:19Z; the publish build reports the same at 10:58:30Z |
| sage-extensions | `3e4812618ce0d5f67dc88959a161ac6ebeb75da2` | the installed checkout reports it, and its three tests pass |
| research | `dbf178cf30c1d26e5f98753c1d9cdbcc16ee3d25` | `uv.lock` at the run's revision; the installer checks each repository out at its lock commit |
| lattice-database | `d1711db05f11405a05269315d6b204b56b527e3d` | same |

`direct_url.json` prints `None` for both packages because both are editable installs carrying
no `vcs_info`; that is why the image's checkout, held against the image's own lock and reported
by two separate jobs, is the provenance rather than that field. The records' own header is not
provenance either: `coble_plane-half-f2.out` prints `sage-extensions: pin 15db925b0c92`, and
that string is a literal in the research script (`PIN = '15db925b0c925…'` in
`computations/reports/coble_plane-half.py`), fixed when it was written and unrelated to what
the image imported.

The run's own generator call, from its log: `O(T_Co) generators: 445 in 638.5 s`,
`discriminant_representation_is_surjective(): True in 164.2 s`, with the imported port at
`/repos/sage-indefinite-port/src/sage_indefinite_port/__init__.py`. **Neither number is a
certified arithmetic cusp count**; they are the T_Co call returning, which is what that step
asserts.

## The three records against the comparator

Committed side: the research checkout at `dbf178cf30`, the records the job compares.

**Comparator as it is on `develop` (strips `(NNN s)`)**

    coble_isotropic_orbits        exit 1   differs
    coble_plane-half-f2           exit 0   reproduced, 26 result lines match
    coble_I18_vinberg-chamber     exit 0   reproduced, 28 result lines match

The one difference in the failing record is a single line and it is elapsed time:

    - the maintained orbit partition materialised in 29.8s: 6 orbits, sizes [1, 1, 496, 496, 527, 527]
    + the maintained orbit partition materialised in 56.0s: 6 orbits, sizes [1, 1, 496, 496, 527, 527]

**Comparator extended to that prose form** (`results/record-comparison-inline-timings-workflow.patch`)

    coble_isotropic_orbits        exit 0   reproduced, 10 result lines match
                                          timing only, not compared: committed in 29.8s, this run in 56.0s
    coble_plane-half-f2           exit 0   reproduced, 26 result lines match
                                          (49 s)->(77 s), (152 s)->(202 s), (0 s)->(1 s) reported as timing only
    coble_I18_vinberg-chamber     exit 0   reproduced, 28 result lines match

So every mathematical line of all three records reproduces in that image. The residual is one
annotation form the comparator does not yet recognise — prose `in 29.8s` beside the
parenthesised `(152 s)` — and that failure decides the repair: extend the strip to it, with
every other character still compared. The regression covers both records and both annotation
forms: **19 passed, 2 failed** against the current file and **21 passed** with the patch
applied, and in both states a changed value or a dropped line is still rejected.

## What this does not establish

- It is not a whole consumer pass: the failing job is one job, and its other steps
  (certification, owner contracts, CoxIter) are separate obligations.
- It does not settle #17's full database verification, and it says nothing about #15, which
  stays blocked by sage-extensions#291.
- `445`/`164.2 s` are that step returning, nothing more.

## One observation that belongs to the port's owner

The same call, made by the same step code (identical apart from YAML indentation), at the same
port and provider pins, printed **458** generators in run 42327313317 (`1e7a615f20`) and
**445** in this run (`b6b4590f`):

    1e7a615f20  O(T_Co) generators: 458 in 516.9 s   discriminant_representation_is_surjective(): True in 132.5 s
    b6b4590f    O(T_Co) generators: 445 in 638.5 s   discriminant_representation_is_surjective(): True in 164.2 s

Both runs' images carry port `991b88b0` and provider `3e4812618c`, so this is not a pin
difference. A generating set's size is not a machine property, so either
`Aut().group_generators()` returns a set that depends on something other than the lattice, or
one of those two runs ran a path this comparison has not identified. It is reported to the
port's owner as an open question and is not resolved here; no record of it exists in
`results/` before this file.
