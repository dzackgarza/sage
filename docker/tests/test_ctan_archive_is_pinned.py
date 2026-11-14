"""The image's luahyperbolic archive comes from one host, checked against its digest (sage#38).

CTAN has no download host of its own: ``mirrors.ctan.org`` answers each request with a
redirect to a mirror it picks, and so does ``ctan.org``'s ``/tex-archive``. Image run
43544885598 stopped at this step twice with

    curl: (60) SSL certificate problem: unable to get local issuer certificate

because the mirror that request drew -- ``ctan.math.utah.edu``, whose leaf is issued by
``InCommon RSA OV SSL CA 3`` -- does not serve that intermediate, so no client can
complete the chain. The drawn mirror decides the *content* too: measured on the day of
that run, ``mirrors.dotsrc.org`` and ``mirror.ox.ac.uk`` still served the 2026-03-16
archive (3556123 bytes) while CTAN carried the 2026-11-13 one (3828806 bytes). An
unpinned fetch is therefore not one build input but whichever input the request drew.

The step now names one host and compares the archive against a SHA-256 before it
unpacks anything, the way the quarto ``.deb`` beside it is pinned, and keeps
``kpsewhich luahyperbolic.sty`` as its verdict -- the file the image check asserts
``kpsewhich`` finds.

What is pinned here is the step's shape: one https host that is not a multiplexor, a
digest compared before the unpack, and the ``kpsewhich`` verdict last. That the digest
is the archive's is the image build's own check, and cannot be asserted from here.

    pytest docker/tests/test_ctan_archive_is_pinned.py
"""

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
DOCKERFILE = REPOSITORY / "docker" / "research-environment.Dockerfile"

# The hosts that answer a request with a redirect to a mirror of their choosing.
MULTIPLEXORS = {"mirrors.ctan.org", "mirror.ctan.org", "ctan.org", "www.ctan.org"}

DIGEST = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
URL = re.compile(r"https?://[^\s\"']+")


def instructions() -> list[str]:
    """The Dockerfile's RUN instructions, continuations joined into one line each."""
    found, collected = [], None
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if collected is None:
            if not line.startswith("RUN"):
                continue
            collected = [line[len("RUN"):].strip()]
        else:
            collected.append(line.strip())
        if not collected[-1].endswith("\\"):
            found.append(" ".join(collected))
            collected = None
    assert collected is None, "a RUN instruction runs past the end of the file"
    return found


def luahyperbolic_commands() -> list[str]:
    """The step's commands: the one RUN instruction that fetches the archive, split."""
    steps = [step for step in instructions() if "luahyperbolic.zip" in step]
    assert len(steps) == 1, steps
    return [command.strip() for command in steps[0].replace("\\", "").split(";") if command.strip()]


COMMANDS = luahyperbolic_commands()


def command_starting_with(prefix: str) -> str:
    found = [command for command in COMMANDS if command.startswith(prefix)]
    assert len(found) == 1, (prefix, found, COMMANDS)
    return found[0]


def test_the_archive_comes_from_one_named_host():
    """One https host, and not one that redirects to a mirror it picks per request."""
    urls = [url for command in COMMANDS for url in URL.findall(command)]
    assert len(urls) == 1, urls
    url = urls[0]
    assert url.startswith("https://"), url
    host = url.removeprefix("https://").split("/")[0]
    assert host not in MULTIPLEXORS, (
        f"{host} redirects each request to a mirror of its own choosing, which is what "
        f"failed run 43544885598: name one mirror instead"
    )
    assert "luahyperbolic.zip" in url, url


def test_the_digest_is_compared_before_anything_is_unpacked():
    """A failed digest stops the step: `set -eu`, the comparison, then the unpack."""
    assert COMMANDS[0] == "set -eu", COMMANDS[0]
    pinned = command_starting_with("sha256=").removeprefix("sha256=")
    assert DIGEST.fullmatch(pinned), pinned
    comparison = command_starting_with("echo ")
    assert comparison.endswith("sha256sum -c -"), comparison
    assert "$sha256" in comparison, comparison
    checked = COMMANDS.index(comparison)
    unpacked = COMMANDS.index(command_starting_with("unzip "))
    assert checked < unpacked, COMMANDS


def test_the_steps_last_verdict_is_kpsewhich_finding_the_package():
    """What the image check asserts is this step's own check: TeX finds the file."""
    assert COMMANDS[-1] == "kpsewhich luahyperbolic.sty", COMMANDS[-1]


def test_the_step_installs_into_a_tree_kpsewhich_searches():
    """The unpack target is under /usr/local/share/texmf, which is on TeX's path."""
    unpack = command_starting_with("unzip ")
    assert "-d /usr/local/share/texmf/tex/lualatex" in unpack, unpack
    assert command_starting_with("mktexlsr ") == "mktexlsr /usr/local/share/texmf"
