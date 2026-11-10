# image#22: the document toolchain, and two repairs carried with it

Batch: a moved Mathlib head now selects a full build (item 1 of the owner's
decision), `test_provenance_boundaries.py` reads the five consumer jobs, and the
image carries the document toolchain the project sites build with.

## A moved head selects a full build (sage#13)

The selector is now repository code — `docker/select-build-kind.sh` — instead of a
`run:` block, so a test can run it. The workflow patch that calls it is
`results/build-kind-selector-workflow.patch` (2870 bytes, sha256
`55960884449571529de6582b163e747f3d7d407f48cfbec943bfd96b6672a8db`); it replaces the
inline block with

```yaml
      env:
        BASE_IMAGE: ghcr.io/${{ github.repository_owner }}/sage:develop
        IS_SPINOR: ${{ inputs.sage_source_sha != '' }}
        MATHLIB_REVISION: ${{ steps.mathlib.outputs.revision }}
        SOURCE: sage-source
      run: ./sage-source/docker/select-build-kind.sh
```

and nothing else — the step's id, condition and outputs are unchanged, so the
build's `steps.build-kind.outputs.kind` still drives the Dockerfile choice.

What the script decides, in order, each with a line saying which rule fired:

1. an isolated spinor image → full (built from scratch by construction), and the
   registry is not consulted at all;
2. no resolved Mathlib head → full (nothing to compare);
3. the base image carries no `dev.dzackgarza.mathlib.revision` label → full. An image
   published before the label existed records no head to keep, and `docker`'s
   `<no value>` is not a revision;
4. the label differs from the resolved head → **full**, naming both revisions. This is
   the decision: an increment over a base on another head would leave that base's
   ~10.7 GiB closure layer underneath the new one, which is not "the image is one
   shared project on the head";
5. the base carries no zstd layer → full (the one-way compression transition from #9,
   carried over unchanged);
6. a deleted file or a change to `docker/research-environment.Dockerfile` → full;
7. a base whose `org.opencontainers.image.revision` cannot be read in the checkout →
   full, because no diff means nothing proves an increment is safe;
8. otherwise incremental.

Tests: `docker/tests/test_build_kind_selector.py`, **12 passed** — the real script,
with `docker` a stub that answers `imagetools inspect` the way the CLI does (a
`--format` label lookup, and `--raw` for the index and its manifests, `<no value>`
included) and a real git checkout for the diff. Each rule has its case, and two
assert that the registry is never asked anything when nothing needs comparing.

## The tests read the five jobs

`c45b08c1dfb` split `consumer-acceptance` into `consumer-mathematics`,
`consumer-certify`, `consumer-records`, `consumer-contracts` and
`consumer-chamber`. Three files still indexed the old name and failed with
`KeyError: 'consumer-acceptance'` — five tests in `test_provenance_boundaries.py`,
two in `test_certify_step_in_the_image.py` and one in
`test_coxiter_chamber_input.py`; the brief named the first, and the other two are the
same defect, so all three are fixed rather than the named one alone.

Each now names the five as `CONSUMER_JOBS`, looks its step up in whichever of them
carries it (asserting exactly one), and gains a test pinning the set: the five are
jobs, and the step is in the job whose name says so (`consumer-mathematics` for
T_Co, `consumer-certify` for 6JRR, `consumer-chamber` for the CoxIter read). A
further split now fails with a message naming the jobs the workflow has, not a
`KeyError`. **6 + 3 + 2 passed** against the unpacked image, including the whole-step
run that reaches `T_Co: rank 11, determinant -2048, signature (2, 9)`.

## The document toolchain (sage#22)

Both sites install this themselves at every run, so the image carries it and a site
build installs nothing:

| what | where it came from | why |
| --- | --- | --- |
| `texlive-full`, with its Recommends | apt | research's `docs.yml` says a partial TeX Live diverges the moment a figure reaches for a package nobody listed; new-qual-site installs `scheme-full` |
| `pdf2svg` | apt | both sites' figure pipeline |
| `poppler-utils` | apt | `pdftoppm`, which the figures go through |
| `nodejs` | apt | new-qual-site's `tests/test_static_site.py:884` runs `node` |
| quarto 1.11.9 | its release `.deb`, pinned by version and digest `64078d1623d9ab89da766591f3410a0756f3737a37efb0897c7e84b863bf092a` (140777744 bytes) | research takes it from `quarto-actions/setup`; its postinst links `/opt/quarto/bin/quarto` into `/usr/local/bin` |

`texlive-latex-extra` leaves the optional-packages block, since `texlive-full`
provides it. `luahyperbolic.sty` — the one file research's CI has to fetch from CTAN
because Ubuntu's TeX Live predates the package — is in TeX Live 2025 (CTAN revision
78431, checked in the current `texlive.tlpdb`), so `texlive-full` carries it here and
no CTAN step is needed.

**This is the largest addition the image has taken: about 5 GiB installed, roughly 2.5
GiB more on the wire, on a 14.19 GiB image — #9 pays for it on every pull.** That
trade is the issue's decision, not this change's; the sizes here are what `texlive-full`
installs on Debian, not a measurement of the new layer.

The check asserts each tool by doing what a site build does with it, and fails the
build naming the missing one:

* `quarto --version` prints a version;
* `dpkg-query` reports `texlive-full` installed, and `kpsewhich` finds each of
  `tikz.sty`, `tikz-cd.sty`, `pgfplots.sty`, `standalone.cls`, `luahyperbolic.sty`,
  `booktabs.sty`, `microtype.sty`, `fontspec.sty`, `unicode-math.sty`, `siunitx.sty`,
  `amsmath.sty`, `mathtools.sty`, with `lualatex --version` reporting LuaHBTeX;
* `pdf2svg` converts a PDF the check writes — with a real xref table, so poppler
  accepts it — and the output is asserted to be SVG; `pdftoppm -v` reports a version
  and `pdftoppm -r 10 -png` writes an image;
* `node --version` reports a version.

That list of TeX files is named rather than exhaustive: they are the figure and
typography set the sites' filters use, and `texlive-full` is the declared input that
makes an absent file a Debian packaging defect rather than a choice.

Tests: `docker/tests/test_document_toolchain_check.py`, **10 passed** — the check's
own block, taken from the file and run under a PATH holding only the stubs, so
"absent" is absent. Each of the six tools missing fails naming it; `texlive-full`
absent, a TeX file `kpsewhich` cannot find, and a `pdf2svg` that exits non-zero all
fail. Run against this host's real tools instead, the block fails as designed:
`the image carries no ['quarto', 'pdf2svg', 'node']`.

## A test that fails here, for a reason outside this batch

`docker/tests/test_gap_workspace_under_a_launcher.py` fails on this host with
`ModuleNotFoundError: No module named 'sage.libs.gap.kernel_info'`: the unpacked
image under `~/sage-image/rootfs` is older than that module, which arrives with the
next image (image#20). It is a property of the local copy, not of this change, and it
passes once the image it reads carries the module.

## Not verified here

No image has been built with any of this. The `texlive-full` install, quarto's `.deb`
under `apt-get install`, the new layer's size, and every check line above are
unmeasured until the image run; the acceptance for #22 is those lines inside the
published image, and for the selector it is a build log showing rule 4 firing when the
head has moved.

## Handing over

Land `results/build-kind-selector-workflow.patch` **after** this push is on `develop`:
the workflow calls `docker/select-build-kind.sh`, which this push adds. `git apply
--check` is clean against the committed workflow, and the patched YAML parses with the
five consumer jobs, `zstd-probe` and `zstd-pull` intact.
