# GAP's matrix-group order and recognition packages in this image

`docker/research-environment.Dockerfile` installs `orb`, `forms`, `genss` and `recog` into
`/usr/share/gap/pkg`. This note records why that directory and not another, what the
packages can and cannot decide, and how a published image is validated.

## Why that directory

Sage's libgap does not run a GAP of its own here. `sage.libs.gap.util.kernel_info` runs the
system `gap` binary and hands libgap the root paths it reports; the Debian wrapper sets
them to `$HOME/gap;/usr/local/lib/gap;/usr/local/share/gap;/usr/lib/gap;/usr/share/gap`.
Sage's optional `gap_packages` spkg does list `genss`, but installs it into
`$SAGE_LOCAL/lib/gap/pkg`, which is on none of those roots -- so `sage -i gap_packages` in
this image installs files that never load. Debian trixie packages none of the four
(`sources.debian.org/api/src/<name>/` is 404), so they come from pinned release tarballs,
the way `polenta` already does. `gap-dev` supplies the `gac` that orb's C module needs.

| package | version | needs |
| --- | --- | --- |
| recog | 1.5.1 | GAP >= 4.13, AtlasRep >= 2.1.0, FactInt >= 1.6.3, Forms >= 1.2.11, genss >= 1.6.8, Orb >= 4.9.0 |
| genss | 1.6.10 | GAP >= 4.9, orb >= 4.5 |
| forms | 1.3.0 | GAP >= 4.9 |
| orb | 5.1.0 | GAP >= 4.12, compiled module |

## What the capability is, and what it is not

`StabilizerChain(G, rec(ErrorBound := e))` builds a randomized (Monte Carlo) Schreier-Sims
chain in whatever action `G` carries -- for a matrix group, the matrix action, not a
permutation representation of the natural module. `Size` of that chain is the product of
its orbit lengths. `SizeMC(G, e)` is the direct entry point.

What this does not give:

* exactness. The chain is Monte Carlo bounded by `ErrorBound`;
  `VerifyStabilizerChainMC(chain, n)` has no method for a plain matrix group ("no 1st
  choice method found"), so the package does not certify the order of such a group.
* a faster `Size(G)`. genss installs `Size` methods only for a group with a *stored*
  stabilizer chain (`HasStoredStabilizerChain`); plain `Size` still resolves through
  `grpnice.gd:241`.

So an order obtained this way is evidence that the capability exists and runs, not an
accepted order for any particular subgroup. The port's `p = 5`/`p = 7` acceptance nodes
still have to reproduce their recorded image orders themselves.

## How the image asserts it

`docker/research-environment-check.py`, run as the last step of the image build, asserts
the reported roots contain `/usr/share/gap/`, that each of the four loads there,
`RecognizeGroup` is bound, and that a deg-4 `GF(5)` upper-triangular (Borel) subgroup is
ordered through genss's chain as 62,500 = 4 * 5^6. No degree-10 computation is attempted:
the module the port cares about has 9,765,625 points at p = 5.

## Validating a published image on a host without a container runtime

```
docker/sage-image.py --cache DIR --reference sha256:<index digest> fetch
docker/sage-image.py --cache DIR --reference sha256:<index digest> info     # records both digests
PEAKRSS_LIMIT_MIB=6144 python peakrss.py -- \
    python3 docker/sage-image.py --cache DIR run -- \
        /sage/.venv/bin/sage /work/results/consumer-check.py
```

The guard is the shared process-tree RSS guard (`sage-image/peakrss.py`): it samples the
summed RSS of the whole tree every 2 s, stops the run above `PEAKRSS_LIMIT_MIB`, and
propagates the child's exit status so a killed run cannot read as a pass. Do **not**
substitute `ulimit -v` — a virtual-address cap is not the same bound and has already caused
false setup failures in this environment.

`--digest` is documented as the linux/amd64 manifest digest but `resolve()` fetches the
reference with the OCI *index* media type and then indexes into it; an amd64 manifest
digest therefore answers 404. Pin with `--reference sha256:<index digest>` and check
`info` reports the expected `index` and `manifest`.

## Consumer validation of the published image

Run on 2026-11-02 from `docker/sage-image.py --cache … run`, over a tree unpacked from
`sha256:122ccd3aac6d7dc7a991a3c35bbeb9e5749125dab8b0b62d6da004731e2ab8fb` (manifest
`sha256:83aeb8ac…`, config `sha256:20fe067d…`, `org.opencontainers.image.revision` =
`6dc2659dd4aa7156e9d812afb8ccb317df033dd5`, every layer sha256-checked before it was
applied). Command, output verbatim:

```
kernel: GAP 4.14.0 arch x86_64-pc-linux-gnu-default64-kv9
roots: /root/.gap/;/root/gap/;/usr/local/lib/gap/;/usr/local/share/gap/;/usr/lib/gap/;/usr/share/gap/
LoadPackage(orb) = true in 0.073s, version 5.1.0
LoadPackage(forms) = true in 0.000s, version 1.3.0
LoadPackage(genss) = true in 0.000s, version 1.6.10
LoadPackage(recog) = true in 0.000s, version 1.5.1
genss chain order of the deg-4 GF(5) Borel: 62500 in 0.005s (expect 62500)
CONSUMER CAPABILITY CHECK PASSED
```

The absent-package contract was checked in GAP (`LoadPackage("not_a_gap_package") = fail`);
`.sage()` on `fail` raises, so the comparison cannot be made in Sage. `IsBound` held for
`RecognizeGroup`, `StabilizerChain` and `SizeMC`.

Scope: this establishes that the published image's Sage loads the four packages through
libgap, from the root the Debian wrapper reports, and that genss's chain orders a
generated matrix subgroup there. The chain is Monte Carlo bounded by `ErrorBound` and
`VerifyStabilizerChainMC` has no method for a plain matrix group, so 62,500 is capability
evidence and **not** an exact order for any subgroup of `O(V)`; the port's `p = 5`/`p = 7`
acceptance nodes are untouched by it, and no degree-10 computation was attempted.

`PEAKRSS_LIMIT_MIB=6144` bounded the run, but it finished in ~2 s, so the sampler recorded
single 2 MiB samples and did not capture the child's peak; the earlier aborted run over the
same tree peaked at 341 MiB. Treat the guard as a bound that was in place, not as a
measured peak for this run.

## Applying the consumer workflow change

`docker/gap-consumer-workflow.patch` applies to `.github/workflows/research-image-consumer.yml`:

```
git am docker/gap-consumer-workflow.patch    # or: git apply
```

The workflow as published asserted only a `QQ` determinant, so a consumer run would pass on
an image missing every GAP package; the patch adds a step making the same assertions from a
fresh runner. This app's push is refused for that path (`without workflows permission`), so
it travels as a patch and needs a credential that has `workflows` write.
