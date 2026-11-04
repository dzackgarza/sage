#!/usr/bin/env bash
# Owner-managed reconciliation of the shared unpacked image to the published
# build source. Nothing here runs without the coordinated all-project boundary.
#
#   runtime-adoption.sh preflight   read-only: is the runtime quiet, does the
#                                   recorded pre-state still hold?
#   runtime-adoption.sh verify      read-only: what still differs from b1997dd
#   runtime-adoption.sh adopt       bounded: the four reconciliation steps
#   runtime-adoption.sh check       read-only: the image's own environment check
#   runtime-adoption.sh rollback    restore the snapshotted working state
set -euo pipefail

rootfs="${SAGE_IMAGE_ROOTFS:-$HOME/sage-image/rootfs}"
sage="$rootfs/sage"
snapshot="${SNAPSHOT:-$(cd "$(dirname "$0")" && pwd)/runtime-rollback-snapshot}"
published=9f1680d2a7bcf001e50714768e6066e6652d1708
base=b0cd7d86e21eb450ed90e4c83707920e1d5d429a

# Expected at the published commit.
expected_uv_lock=f070d20194761a12d2a42218d1416e983a966a51ee7511447f7095e9560d9f98
expected_launcher=d1df681a03f2fe847fff4d668fe5b3cb3b3d658b270b5f26d196e881c7aabb4b
expected_provisioner=5af7c91b2b9eb9944b4d33c09529261cd660b0a56a82530dbc0f44a2936d3338
expected_installer=a46fb9a7024d80bc1f922a4753f2a8624659bb59736bb1c93186f9005ab8e816
expected_check=ee249af72d358cfd1d9188496ab9eda55475329c62aef689edfdcab3c9df7be4
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
    printf '%-34s %-18s %-18s %s\n' item live expected status
    check() { # name path expected
        live="$(sha "$2")"
        if [ "$live" = "$3" ]; then status=ok; elif [ "$live" = absent ]; then status=absent; else status=differs; fi
        printf '%-34s %-18s %-18s %s\n' "$1" "${live:0:16}" "${3:0:16}" "$status"
    }
    check uv.lock "$sage/uv.lock" "$expected_uv_lock"
    check install-research-repositories.sh "$sage/docker/install-research-repositories.sh" "$expected_installer"
    check research-environment-check.py "$sage/docker/research-environment-check.py" "$expected_check"
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
    say "sage HEAD $(git -C "$sage" rev-parse HEAD) (published $published, pre-adoption $base)"
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
    ( cd "$sage" && timeout 1200 just research-environment-sync ) \
        || fail "research-environment-sync exceeded 20 min; revert the lock and sync again"
    timeout 60 install -m 0755 "$sage/docker/julia-launcher.sh" "$rootfs/usr/local/bin/julia" \
        || fail "launcher install failed"
    say "launcher installed"
    say "next: runtime-adoption.sh check"
    ;;
check)
    timeout 1200 "$sage/.venv/bin/sage" "$sage/docker/research-environment-check.py" \
        || fail "the environment check failed (20 min limit)"
    ;;
rollback)
    [ -d "$snapshot" ] || fail "no snapshot at $snapshot"
    cp -a "$snapshot/bliss.cpython-314-x86_64-linux-gnu.so" \
        "$sage/.venv/lib/python3.14/site-packages/sage/graphs/"
    cp -a "$snapshot/bliss-repair.json" "$rootfs/opt/bliss-repair.json"
    cp -a "$snapshot/lake-views-index.json" "$rootfs/opt/lake-views/index.json"
    ln -sfn "$(cat "$snapshot/julia-launcher-target.txt")" "$rootfs/usr/local/bin/julia"
    git -C "$sage" checkout "$base" 2>/dev/null || git -C "$sage" checkout -f "$base"
    git -C "$sage" apply "$(dirname "$0")/bliss-repair.patch" "$(dirname "$0")/bliss-repair-v2.patch"
    say "restored source $base with both patches, module, stamps and launcher"
    say "to revert the lock too: git -C $sage checkout $base -- uv.lock && (cd $sage && just research-environment-sync)"
    ;;
*)
    sed -n '2,12p' "$0"
    exit 2
    ;;
esac
