#!/usr/bin/env bash
# Owner-managed reconciliation of the shared unpacked image to the published
# build source. Nothing here runs without the coordinated all-project boundary.
#
#   runtime-adoption.sh preflight   read-only: is the runtime quiet, does the
#                                   recorded pre-state still hold?
#   runtime-adoption.sh verify      read-only: what still differs from b1997dd
#   runtime-adoption.sh adopt       bounded: the reconciliation steps
#   runtime-adoption.sh check       read-only: the image's own environment check
#   runtime-adoption.sh rollback    restore the snapshotted working state
set -euo pipefail

rootfs="${SAGE_IMAGE_ROOTFS:-$HOME/sage-image/rootfs}"
sage="$rootfs/sage"
snapshot="${SNAPSHOT:-$(cd "$(dirname "$0")" && pwd)/runtime-rollback-snapshot}"
published=6a1d6d9f8ebf276a06245f3045b78834219ea09a
# The runtime's source now, and what a rollback returns to: #6 moved it to 9f1680d2.
base=9f1680d2a7bcf001e50714768e6066e6652d1708

# Expected at the published commit.
expected_uv_lock=f070d20194761a12d2a42218d1416e983a966a51ee7511447f7095e9560d9f98
expected_launcher=d1df681a03f2fe847fff4d668fe5b3cb3b3d658b270b5f26d196e881c7aabb4b
expected_provisioner=3ad79f623b4a2238152b9356a156ce17ea6099052367517b0dca93fc7e3cc973
expected_installer=8cb222c15b65742ab0354575202aa4967da0cad3fe127f695a34be6f5d00f0b9
expected_check=46ca46caab41e598f44e17aff565268a608a911b55b2cfac943558124cf5a030
# The file whose purge makes the image's GAP single (sage#11). It is load-bearing for
# the environment now, so the live copy is held to the published bytes like the rest.
expected_incremental_dockerfile=216671b91d5058a035f00f79182274edf2958f6870791dd2283d2d3cf01a8b20
expected_meson=d8119d97dfa923a7887894458895930fa7348e1cf316ae62b3fb313ba2707201
# The Maxima share prefix (a20baff): the file whose absence made a reconfigure
# regenerate config.py with an empty MAXIMA_PREFIX.
expected_maxima_meson=a25ab4a58e5a788d6bd5a1bbae93b48a3b5075609afa6077dc70fc9f2a2e6eb7
# The Sage-owned GAP the published image builds: binary, libgap, root, package set.
expected_gap_packages=173

say() { printf '%s\n' "$*"; }
fail() { printf 'runtime-adoption: %s\n' "$*" >&2; exit 1; }
sha() { [ -f "$1" ] && sha256sum "$1" | cut -d' ' -f1 || echo absent; }

case "${1:-}" in
preflight)
    say "rootfs: $rootfs"
    running="$(pgrep -af 'proot|udocker|bwrap' 2>/dev/null | grep -F "$rootfs" || true)"
    if [ -n "$running" ]; then
        say "BOUNDARY NOT HELD — processes inside the rootfs:"
        printf '%s\n' "$running" | cut -c1-160
        exit 1
    fi
    say "no process inside the rootfs"
    say "sage HEAD: $(git -C "$sage" rev-parse HEAD)"
    say "sage diff: $(git -C "$sage" diff | sha256sum | cut -d' ' -f1)"
    say "uv.lock  : $(sha "$sage/uv.lock")"
    say "module   : $(sha "$sage/.venv/lib/python3.14/site-packages/sage/graphs/bliss.cpython-314-x86_64-linux-gnu.so")"
    # The launcher is a regular file (docker/julia-launcher.sh), not a symlink:
    # readlink printed "none" for a correct installation.
    say "launcher : $(sha "$rootfs/usr/local/bin/julia")"
    say "free     : $(df -h "$rootfs" | awk 'NR==2 {print $4}')"
    ;;
verify)
    printf '%-44s %-18s %-18s %s\n' item live expected status
    check() { # name path expected
        live="$(sha "$2")"
        if [ "$live" = "$3" ]; then status=ok; elif [ "$live" = absent ]; then status=absent; else status=differs; fi
        printf '%-44s %-18s %-18s %s\n' "$1" "${live:0:16}" "${3:0:16}" "$status"
    }
    check uv.lock "$sage/uv.lock" "$expected_uv_lock"
    check install-research-repositories.sh "$sage/docker/install-research-repositories.sh" "$expected_installer"
    check research-environment-check.py "$sage/docker/research-environment-check.py" "$expected_check"
    check research-environment-incremental.Dockerfile \
        "$sage/docker/research-environment-incremental.Dockerfile" "$expected_incremental_dockerfile"
    check provision-lean-packages.sh "$sage/docker/provision-lean-packages.sh" "$expected_provisioner"
    check julia-launcher.sh "$sage/docker/julia-launcher.sh" "$expected_launcher"
    check src/.../meson.build "$sage/src/sage/graphs/meson.build" "$expected_meson"
    check src/.../libs/meson.build "$sage/src/sage/libs/meson.build" "$expected_maxima_meson"
    say ""
    # The published image builds GAP into $SAGE_LOCAL; a rootfs that predates it runs
    # the distribution GAP. Report that delta rather than only the source pin.
    if [ -x "$sage/.venv/bin/gap" ]; then
        say "GAP in \$SAGE_LOCAL  $(sha "$sage/.venv/bin/gap" | cut -c1-16)        packages $(ls "$sage/.venv/lib/gap/pkg" 2>/dev/null | wc -l)   expected $expected_gap_packages"
    else
        say "GAP in \$SAGE_LOCAL  absent                          packages $(ls "$rootfs/usr/share/gap/pkg" 2>/dev/null | wc -l) (distribution tree)   expected $expected_gap_packages"
    fi
    say "sage HEAD $(git -C "$sage" rev-parse HEAD) (published $published, rollback target $base)"
    # sage#11: a rootfs reconciled from an image built before the purge still carries
    # Debian's GAP, and the check refuses it, so the delta is reported here as well.
    distribution=""
    for path in /usr/bin/gap /usr/lib/gap /usr/share/gap /usr/lib/x86_64-linux-gnu/libgap.so.9; do
        if [ -e "$rootfs$path" ]; then distribution="$distribution $path"; fi
    done
    say "distribution GAP :${distribution:- absent}"
    # sage#10: sage-categories' own GAP allocation, installed by the sync into its
    # checkout rather than into either GAP.
    say "sage-categories .gap/pkg: $(ls "$rootfs/repos/sage-categories/.gap/pkg" 2>/dev/null | wc -l) (26 after the sync that installs them)"
    for repo in sage-indefinite-port sage-extensions research; do
        say "$repo: $(git -C "$rootfs/repos/$repo" rev-parse HEAD 2>/dev/null | cut -c1-12)"
    done
    ;;
adopt)
    [ "$(git -C "$sage" rev-parse HEAD)" = "$base" ] || fail "not at the recorded pre-adoption commit"
    timeout 300 git -C "$sage" fetch origin develop || fail "fetch timed out (5 min); nothing changed"
    timeout 120 git -C "$sage" diff --quiet "$published" -- \
        src/sage/graphs/meson.build src/sage/graphs/bliss_cpp/bliss_find_automorphisms.h \
        || fail "the patched files differ from $published; stopping"
    # The guard above proved these files already hold the published content, so
    # a forced switch discards nothing that is not in the target commit.
    timeout 120 git -C "$sage" checkout -f "$published" || fail "checkout timed out (2 min)"
    say "source at $published"
    # sage#11: Debian's GAP arrived in an old image layer, so a source checkout cannot
    # remove it, and the Dockerfile's purge only reaches a build. Do here what that
    # layer does in an image. Inside the rootfs uid 0 is this uid mapped by bwrap, so
    # dpkg runs normally and nothing outside the rootfs is touched.
    command -v bwrap >/dev/null || fail "bubblewrap is required to purge inside the rootfs"
    bwrap --bind "$rootfs" / --proc /proc --dev /dev --tmpfs /tmp \
        --unshare-user --uid 0 --gid 0 --clearenv \
        --setenv PATH /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        --setenv DEBIAN_FRONTEND noninteractive \
        -- /bin/bash -s <<'PURGE' || fail "the distribution GAP purge failed"
set -eu
purged="$(dpkg-query -W -f='${Package} ${Status}\n' 'gap*' 'libgap*' 2>/dev/null \
    | awk '$2 == "install" && $3 == "ok" && $4 == "installed" {print $1}')"
if [ -n "$purged" ]; then
    printf 'purging the distribution GAP: %s\n' "$purged"
    # The user namespace maps one uid, so apt cannot drop to its _apt sandbox user.
    apt-get -o APT::Sandbox::User=root purge -y $purged
fi
# libgap.pc.disabled is what an earlier repair renamed; it is dpkg's file no longer.
rm -rf /usr/share/gap /usr/lib/gap \
    /usr/lib/x86_64-linux-gnu/libgap.so.9 /usr/lib/x86_64-linux-gnu/libgap.so \
    /usr/lib/x86_64-linux-gnu/pkgconfig/libgap.pc \
    /usr/lib/x86_64-linux-gnu/pkgconfig/libgap.pc.disabled
test ! -e /usr/bin/gap
test ! -d /usr/share/gap
PURGE
    say "distribution GAP purged; the Sage-owned GAP is the only one left"
    # The sync runs the runtime's own tools, not the host's: `just`, uv and the venv
    # are inside the rootfs, and the venv's links are absolute /sage paths. The three
    # --env values are what the image declares for itself; this rootfs carries no
    # unpack stamp for the launcher to read them from. The timeout is outside the
    # sandbox, so it bounds the whole run.
    timeout 1800 python3 "${sage}/docker/sage-image.py" --rootfs "${rootfs}" run \
        --env PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig --env ELAN_HOME=/opt/elan \
        --env JULIA_DEPOT_PATH=/opt/julia-depot --chdir /sage \
        -- /bin/sh -c 'just research-environment-sync' \
        || fail "research-environment-sync failed or exceeded 30 min; revert the lock and sync again"
    timeout 60 install -m 0755 "$sage/docker/julia-launcher.sh" "$rootfs/usr/local/bin/julia" \
        || fail "launcher install failed"
    say "launcher installed"
    say "next: runtime-adoption.sh check"
    ;;
check)
    # The check is the image's own, and it runs inside the runtime for the same
    # reason the sync does: the venv's interpreter is an absolute /sage path.
    timeout 1500 python3 "${sage}/docker/sage-image.py" --rootfs "${rootfs}" run \
        --env PKG_CONFIG_PATH=/sage/.venv/lib/pkgconfig --env ELAN_HOME=/opt/elan \
        --env JULIA_DEPOT_PATH=/opt/julia-depot --chdir /sage \
        -- /sage/.venv/bin/sage docker/research-environment-check.py \
        || fail "the environment check failed (25 min limit)"
    ;;
rollback)
    [ -d "$snapshot" ] || fail "no snapshot at $snapshot"
    cp -a "$snapshot/bliss.cpython-314-x86_64-linux-gnu.so" \
        "$sage/.venv/lib/python3.14/site-packages/sage/graphs/"
    cp -a "$snapshot/bliss-repair.json" "$rootfs/opt/bliss-repair.json"
    cp -a "$snapshot/lake-views-index.json" "$rootfs/opt/lake-views/index.json"
    ln -sfn "$(cat "$snapshot/julia-launcher-target.txt")" "$rootfs/usr/local/bin/julia"
    git -C "$sage" checkout "$base" 2>/dev/null || git -C "$sage" checkout -f "$base"
    # The patches are in $base already when a rollback returns to a commit that
    # carries them; applying them again would fail, so it is tried, not required.
    if git -C "$sage" apply "$(dirname "$0")/bliss-repair.patch" "$(dirname "$0")/bliss-repair-v2.patch" 2>/dev/null; then
        say "restored source $base with both patches, module, stamps and launcher"
    else
        say "restored source $base, module, stamps and launcher; its bliss patches are already in the commit"
    fi
    # The distribution GAP the adoption purged is not restored: it came from an image
    # layer, and the Sage-owned GAP the runtime keeps is the one its modules link.
    say "note: the purged distribution GAP is not restored by this rollback"
    say "to revert the lock too: git -C $sage checkout $base -- uv.lock && (cd $sage && just research-environment-sync)"
    ;;
*)
    sed -n '2,12p' "$0"
    exit 2
    ;;
esac
