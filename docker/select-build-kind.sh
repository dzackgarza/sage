#!/usr/bin/env bash
# Decide whether this image build is full or incremental, and say why.
#
# A full build starts from debian:trixie and lays down every layer; an incremental
# one is `FROM` the published image and adds what the source change needs. Three
# things force the full build:
#
#  * an isolated spinor image, which is built from scratch by construction;
#  * a file deleted since the base image, which the incremental copy cannot delete
#    (it rsyncs, and deletes nothing), or a change to
#    docker/research-environment.Dockerfile, which is where the system layers are;
#  * a Mathlib head that has moved (sage#13). The image is one shared Lean project on
#    the head this build resolved; an incremental build over a base that carries
#    another leaves the old closure layer underneath the new one -- OCI layers only
#    add -- so the image would carry ~10.7 GiB of a Mathlib it is not on. The label
#    the publish step writes, `dev.dzackgarza.mathlib.revision`, is how this step
#    reads that head without pulling the image.
#
# Two more rules are carried from #9 and #13's first landing, and both are about the
# image being one image rather than a heap of layers: a base with no zstd layer
# selects the full build, because an increment over it would recompress only the small
# layers it writes and leave the Sage build layer gzip (the transition is one-way, and
# the image it publishes is the base of the increments after it).
#
#   BASE_IMAGE         the published image this build extends
#   MATHLIB_REVISION   the Mathlib head this build resolved (the `mathlib` step)
#   IS_SPINOR          "true" builds an isolated spinor image
#   SOURCE             the checkout to compare with the base image (default
#                      sage-source)
#   GITHUB_OUTPUT      where `kind=...` is written (default: standard output)
#
# Prints one line saying which build it selected and why, then writes the output.
set -euo pipefail

base_image="${BASE_IMAGE:?BASE_IMAGE is required}"
mathlib_revision="${MATHLIB_REVISION:-}"
source_dir="${SOURCE:-sage-source}"
output="${GITHUB_OUTPUT:-/dev/stdout}"

select_full() {
    printf 'full build: %s\n' "$1"
    printf 'kind=full\n' >> "${output}"
    exit 0
}

if [ "${IS_SPINOR:-false}" = "true" ]; then
    select_full "an isolated spinor image is built from scratch"
fi

if [ -z "${mathlib_revision}" ]; then
    select_full "this build resolved no Mathlib head to compare with the base"
fi

label() {
    docker buildx imagetools inspect "${base_image}" \
        --format "{{ index .Image.Config.Labels \"$1\" }}" 2>/dev/null || true
}

# A revision a previous build recorded, or nothing. `<no value>` is what the format
# prints for a label the image does not carry, which an image published before the
# label existed does not.
is_revision() {
    case "$1" in
        '' | *[!0-9a-f]*) return 1 ;;
    esac
    [ "${#1}" -eq 40 ]
}

base_mathlib="$(label dev.dzackgarza.mathlib.revision)"
if ! is_revision "${base_mathlib}"; then
    select_full "the base image records no Mathlib revision, so there is none to keep"
fi
if [ "${base_mathlib}" != "${mathlib_revision}" ]; then
    select_full "the Mathlib head moved from ${base_mathlib} to ${mathlib_revision}"
fi
printf 'the base image carries mathlib %s, the head this build resolved\n' "${base_mathlib}"

# The compression the base was published with. A published layer keeps the
# compression it was exported with, and an incremental build inherits every one of the
# base's layers.
base_zstd=0
for manifest in $(docker buildx imagetools inspect --raw "${base_image}" \
    | grep -o 'sha256:[0-9a-f]\{64\}'); do
    if docker buildx imagetools inspect --raw "${base_image}@${manifest}" \
        | grep -q 'tar+zstd'; then
        base_zstd=1
        break
    fi
done
if [ "${base_zstd}" = 0 ]; then
    select_full "the base image carries no zstd layer, so an increment would leave its build layer gzip"
fi
printf 'the base image carries zstd layers\n'

base_revision="$(label org.opencontainers.image.revision)"
if ! is_revision "${base_revision}"; then
    printf 'the base image records no source revision; building from what it carries\n' >&2
    echo "kind=incremental" >> "${output}"
    exit 0
fi

# The base image's revision is fetched rather than assumed: the checkout is shallow
# and filtered, so it holds only what this build checked out.
git -C "${source_dir}" fetch --depth 1 origin "${base_revision}" 2>/dev/null || true
if ! git -C "${source_dir}" rev-parse --verify --quiet "${base_revision}^{commit}" > /dev/null; then
    select_full "the base image's revision ${base_revision} cannot be read, so nothing proves an increment is safe"
fi
changes="$(git -C "${source_dir}" diff --name-status "${base_revision}" HEAD)"
printf 'changes since the base image (%s):\n%s\n' "${base_revision}" "${changes}"
if grep -qE '^D|docker/research-environment\.Dockerfile$' <<< "${changes}"; then
    select_full "the change deletes a file or touches the system layers"
fi

printf 'incremental build: the source change is laid over %s\n' "${base_revision}"
printf 'kind=incremental\n' >> "${output}"
