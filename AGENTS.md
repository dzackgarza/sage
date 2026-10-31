# Agent instructions

Use the [shared math container](https://github.com/dzackgarza/ai-review-ci/blob/main/SAGE-CONTAINER.md#use-the-image)
(`ghcr.io/dzackgarza/sage:develop`) for Lean/elan, Sage with mypy, GAP,
Julia/Oscar, Macaulay2, and Singular. The guide covers image pull/run commands,
CI use, and the host launchers.

The image is published from this fork's default branch, `develop`; there is no
`main`. Provisioning is owned here: [docker/SAGE-ENVIRONMENT.md](docker/SAGE-ENVIRONMENT.md)
documents the supported invocations, including `docker/sage-image.py` for hosts
without Docker, chroot or PRoot, and the check the image build runs. A
distribution Sage is not this environment — its import and version failures say
nothing about the libraries in the image — and consumers do not keep their own
provisioning copy.
