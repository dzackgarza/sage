#!/usr/bin/env bash
# Bring an unpacked rootfs onto the Sage-owned GAP that the image now builds.
#
# The image builds GAP from the pinned source into $SAGE_LOCAL
# (docker/research-environment.Dockerfile): executable, libgap, headers, gac, the
# GAP root with its sysinfo.gap, and the packages under $SAGE_LOCAL/lib/gap/pkg.
# An unpacked rootfs that predates that build has none of it -- it runs the
# distribution GAP (4.14.0, kernel ABI kv9) and an orb module is not interchangeable
# between the two ABIs, so copying package directories alone cannot work. The whole
# GAP installation moves as a unit.
#
#   gap-capability-install.sh preflight   no writes: boundary, layouts, what differs
#   gap-capability-install.sh apply       copy the installation, recording every path
#   gap-capability-install.sh verify      run GAP in the rootfs and load the packages
#   gap-capability-install.sh rollback    remove exactly what apply added
#
# SOURCE refuses to be a rootfs that still has the distribution-only layout.
set -euo pipefail

rootfs="${SAGE_IMAGE_ROOTFS:-$HOME/sage-image/rootfs}"
source_rootfs="${SAGE_PUBLISHED_ROOTFS:-$HOME/sage-consumer/image/rootfs}"
manifest="${MANIFEST:-$(cd "$(dirname "$0")" && pwd)/gap-capability-installed.txt}"
prefix=sage/.venv

# Everything the GAP build installs, as one unit. Paths are relative to the rootfs.
paths=(
    "$prefix/bin/gap"
    "$prefix/bin/gac"
    "$prefix/lib/libgap.so"
    "$prefix/lib/libgap.so.11"
    "$prefix/lib/pkgconfig/libgap.pc"
    "$prefix/include/gap"
    "$prefix/lib/gap"          # pkg/ and sysinfo.gap
    "$prefix/share/gap"        # the GAP library itself: lib/init.g and friends
    "etc/ld.so.conf.d/sage-local.conf"
)

say() { printf '%s\n' "$*"; }
fail() { printf 'gap-capability-install: %s\n' "$*" >&2; exit 1; }

users() {
    pgrep -af 'proot|udocker|bwrap' 2>/dev/null | grep -F "$rootfs" || true
}

case "${1:-}" in
preflight)
    say "rootfs:  $rootfs"
    say "source:  $source_rootfs"
    running="$(users)"
    if [ -n "$running" ]; then
        say "BOUNDARY NOT HELD — processes inside the rootfs:"
        printf '%s\n' "$running" | cut -c1-140
        exit 1
    fi
    say "no process inside the rootfs"
    [ -x "$source_rootfs/$prefix/bin/gap" ] \
        || fail "the source rootfs has no $prefix/bin/gap; it predates the Sage-owned GAP build"
    [ -d "$source_rootfs/$prefix/lib/gap/pkg" ] \
        || fail "the source rootfs has no GAP root at $prefix/lib/gap"
    say "source carries the Sage-owned GAP"
    for rel in "${paths[@]}"; do
        if [ -e "$rootfs/$rel" ]; then
            say "  $rel: ALREADY PRESENT (this target is not a clean pre-adoption rootfs)"
        else
            say "  $rel: would be installed"
        fi
    done
    ;;
apply)
    [ -z "$(users)" ] || fail "the boundary is not held; run preflight"
    [ -x "$source_rootfs/$prefix/bin/gap" ] || fail "source has no Sage-owned GAP"
    for rel in "${paths[@]}"; do
        [ -e "$rootfs/$rel" ] && fail "$rel already exists in the target; nothing written"
    done
    : > "$manifest"
    for rel in "${paths[@]}"; do
        [ -e "$source_rootfs/$rel" ] || fail "source is missing $rel"
        mkdir -p "$(dirname "$rootfs/$rel")"
        cp -a "$source_rootfs/$rel" "$rootfs/$rel"
        say "/$rel" >> "$manifest"
        say "installed /$rel"
    done
    # The conf.d entry is inert until the cache is rebuilt; the image build does this
    # in its own RUN, so an in-place adoption has to do it too or libgap.so.11 is not
    # found by the loader (gap dies with exit 127 / "cannot open shared object file").
    if command -v ldconfig >/dev/null; then
        ldconfig -r "$rootfs" 2>/dev/null || ldconfig 2>/dev/null || say "note: run ldconfig in the rootfs before use"
    fi
    say "recorded $(wc -l < "$manifest") path(s) in $manifest"
    ;;
verify)
    [ -x "$rootfs/$prefix/bin/gap" ] || fail "no Sage-owned GAP in $rootfs"
    command -v bwrap >/dev/null || fail "bwrap is required to run the gate"
    # Exec the binary directly rather than through a shell inside the rootfs, so
    # this works against a full image and against a test tree alike.
    bwrap --ro-bind "$rootfs" / --dev /dev --proc /proc --tmpfs /tmp \
        --setenv LD_LIBRARY_PATH "/$prefix/lib" \
        -- "/$prefix/bin/gap" -q --nointeract \
        -c 'Print("version=", GAPInfo.Version, "\n"); Print("root=", GAPInfo.RootPaths, "\n"); for n in ["orb", "forms", "genss", "recog"] do Print(n, "=", LoadPackage(n), " "); od; Print("\nRecognizeGroup=", IsBound(RecognizeGroup), "\n");'
    ;;
rollback)
    [ -f "$manifest" ] || fail "no manifest at $manifest; nothing recorded to remove"
    while read -r rel; do
        [ -n "$rel" ] || continue
        rm -rf "${rootfs:?}${rel}"
        say "removed $rel"
    done < "$manifest"
    ;;
*)
    fail "usage: $0 {preflight|apply|verify|rollback}"
    ;;
esac
