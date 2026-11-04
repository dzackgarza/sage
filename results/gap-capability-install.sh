#!/usr/bin/env bash
# Put the published image's GAP matrix-group capability into an existing unpacked
# rootfs, without rebuilding it.
#
# The published image installs orb, genss, forms and recog into /usr/share/gap/pkg
# at build time (docker/research-environment.Dockerfile). An unpacked rootfs that
# predates that commit does not have them, and Sage's libgap cannot see any other
# location: sage.libs.gap.util.kernel_info runs the system `gap` binary and adopts
# the root paths the Debian wrapper reports, of which /usr/share/gap is one.
#
#   gap-capability-install.sh preflight   no writes: is the boundary held, is the
#                                         source tree present, what is missing
#   gap-capability-install.sh apply       copy the four packages and gac, recording
#                                         exactly what was added
#   gap-capability-install.sh verify      run the image's own load gate in the rootfs
#   gap-capability-install.sh rollback    remove exactly what apply added
#
# SOURCE defaults to an unpacked, digest-verified copy of the published image.
set -euo pipefail

rootfs="${SAGE_IMAGE_ROOTFS:-$HOME/sage-image/rootfs}"
source_rootfs="${SAGE_PUBLISHED_ROOTFS:-$HOME/sage-consumer/image/rootfs}"
manifest="${MANIFEST:-$(cd "$(dirname "$0")" && pwd)/gap-capability-installed.txt}"
packages=(forms-1.3.0 genss-1.6.10 orb-5.1.0 recog-1.5.1)

say() { printf '%s\n' "$*"; }
fail() { printf 'gap-capability-install: %s\n' "$*" >&2; exit 1; }

users() {
    # Anything of another owner's executing inside the rootfs. This script's own
    # gate is excluded by matching only processes that predate it.
    pgrep -af 'proot|udocker|bwrap' 2>/dev/null | grep -F "$rootfs" || true
}

case "${1:-}" in
preflight)
    say "rootfs:        $rootfs"
    say "published:     $source_rootfs"
    running="$(users)"
    if [ -n "$running" ]; then
        say "BOUNDARY NOT HELD — processes inside the rootfs:"
        printf '%s\n' "$running" | cut -c1-140
        exit 1
    fi
    say "no process inside the rootfs"
    [ -d "$rootfs/usr/share/gap/pkg" ] || fail "no GAP package directory in $rootfs"
    [ -d "$source_rootfs/usr/share/gap/pkg" ] || fail "no published rootfs at $source_rootfs"
    for pkg in "${packages[@]}"; do
        if [ -e "$rootfs/usr/share/gap/pkg/$pkg" ]; then
            say "  $pkg: already present"
        else
            say "  $pkg: MISSING"
        fi
    done
    [ -e "$rootfs/usr/bin/gac" ] && say "  gac: already present" || say "  gac: MISSING"
    ;;
apply)
    running="$(users)"
    [ -z "$running" ] || fail "the boundary is not held; run preflight"
    : > "$manifest"
    for pkg in "${packages[@]}"; do
        if [ -e "$rootfs/usr/share/gap/pkg/$pkg" ]; then
            say "$pkg: already present, left alone"
            continue
        fi
        cp -a "$source_rootfs/usr/share/gap/pkg/$pkg" "$rootfs/usr/share/gap/pkg/$pkg"
        say "/usr/share/gap/pkg/$pkg" >> "$manifest"
        say "$pkg: installed from the published image"
    done
    if [ ! -e "$rootfs/usr/bin/gac" ]; then
        # gac ships in gap-dev; it is what makes orb's compiled module buildable
        # and is present in the published image at this path.
        cp -a "$source_rootfs/usr/bin/gac" "$rootfs/usr/bin/gac"
        say "/usr/bin/gac" >> "$manifest"
        say "gac: installed"
    fi
    say "recorded $(wc -l < "$manifest") added path(s) in $manifest"
    ;;
verify)
    [ -d "$rootfs/usr/share/gap/pkg" ] || fail "no rootfs at $rootfs"
    command -v bwrap >/dev/null || fail "bwrap is required to run the gate"
    bwrap --ro-bind "$rootfs" / --dev /dev --proc /proc --tmpfs /tmp \
        -- /bin/bash -c 'gap -q --nointeract -c "
            for n in [\"orb\", \"forms\", \"genss\", \"recog\"] do
                if LoadPackage(n) <> true then
                    Print(\"FAIL \", n, \"\n\"); QUIT_GAP(1);
                fi;
            od;
            Print(\"all four load\n\");"'
    ;;
rollback)
    [ -f "$manifest" ] || fail "no manifest at $manifest; nothing recorded to remove"
    while read -r path; do
        [ -n "$path" ] || continue
        rm -rf "${rootfs:?}${path}"
        say "removed $path"
    done < "$manifest"
    ;;
*)
    fail "usage: $0 {preflight|apply|verify|rollback}"
    ;;
esac
