"""The image's check fails the build when a document tool is absent (sage#22).

The two site builds outside the image install quarto, a full TeX Live, pdf2svg,
poppler-utils and node at every run. The image carries them, and
`docker/research-environment-check.py` asserts each by doing what a site build does
with it: a page through pdf2svg and poppler, TeX's own file lookup for the files the
figures load, `quarto --version`, `node --version`.

This runs that block out of the real file -- only the image's absence of the tools
is simulated, by a PATH that holds just the ones a test provides -- so what it pins
is the check's own verdicts: the line it prints for each tool when they are there,
and the failure naming the tool when one is not.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
CHECK = REPOSITORY / "docker" / "research-environment-check.py"
BLOCK_START = "# ---- the document toolchain the project sites build with (sage#22)"
BLOCK_END = 'print(f"node {node_version}")'

QUARTO = "1.11.9"
NODE = "v20.19.0"
LUA = "LuaHBTeX, Version 1.23.0 (TeX Live 2025)"


def document_block() -> str:
    """The check's document-toolchain block, as the image runs it."""
    text = CHECK.read_text(encoding="utf-8")
    block = text[text.index(BLOCK_START):text.index(BLOCK_END) + len(BLOCK_END)]
    assert block.count("document_tools") >= 1, block[:200]
    return block


def tool(stubs: Path, name: str, body: str) -> None:
    """A stand-in for one tool: a Python script, so no PATH is needed to run it."""
    stub = stubs / name
    stub.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    stub.chmod(0o755)


def stubs_for(tmp_path: Path, omit: tuple[str, ...] = (), no_tex: tuple[str, ...] = (),
              texlive_installed: bool = True, pdf2svg_breaks: bool = False) -> Path:
    """Every tool the block asks for, except the ones a test withholds.

    The PATH the block runs under holds these and nothing else, so "absent" means
    absent: the host's own pdf2svg or node cannot stand in for the image's.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    bodies = {
        "quarto": (
            "import sys\n"
            "from pathlib import Path\n"
            "if sys.argv[1:2] == ['render']:\n"
            "    Path(sys.argv[2]).with_name('page.pdf').write_bytes(b'%PDF-1.4\\n%%EOF\\n')\n"
            "    print('rendered a page')\n"
            "else:\n"
            f"    print({QUARTO!r})\n"
        ),
        "pdf2svg": (
            "raise SystemExit(1)\n" if pdf2svg_breaks else
            "import sys\nopen(sys.argv[2], 'w').write('<svg xmlns=\\\"http://www.w3.org/2000/svg\\\"/>')\n"
        ),
        "pdftoppm": (
            "import sys, pathlib\n"
            "if '-v' in sys.argv:\n"
            "    print('pdftoppm version 25.06.0', file=sys.stderr)\n"
            "    raise SystemExit(0)\n"
            "pathlib.Path(sys.argv[-1]).with_suffix('.png').write_bytes(b'\\x89PNG')\n"
        ),
        "kpsewhich": (
            f"import sys\nno_tex = {list(no_tex)!r}\n"
            "name = sys.argv[1]\n"
            "print('' if name in no_tex else f'/usr/share/texlive/texmf-dist/tex/latex/{name}')\n"
        ),
        "node": f"print({NODE!r})\n",
        "lualatex": f"print({LUA!r})\n",
        "dpkg-query": (
            f"print({'install ok installed'!r})" if texlive_installed
            else f"print({'unknown ok not-installed'!r})"
        ) + "\n",
    }
    for name, body in bodies.items():
        if name not in omit:
            tool(stubs, name, body)
    return stubs


def run_block(tmp_path: Path, stubs: Path) -> subprocess.CompletedProcess:
    harness = tmp_path / "check-documents.py"
    harness.write_text(
        "import subprocess, tempfile\nfrom pathlib import Path\n" + document_block(),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(harness)],
        capture_output=True, text=True, check=False,
        env={"PATH": str(stubs), "HOME": str(tmp_path)},
    )


def test_every_document_tool_present_passes_and_reports_each(tmp_path):
    result = run_block(tmp_path, stubs_for(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"quarto {QUARTO}" in result.stdout
    assert "texlive-full with 12 files the sites load" in result.stdout
    assert "quarto rendered a page with a TikZ figure through pdf2svg: " in result.stdout
    assert f"node {NODE}" in result.stdout


@pytest.mark.parametrize("missing", ["quarto", "pdf2svg", "pdftoppm", "node", "lualatex", "kpsewhich"])
def test_an_absent_tool_fails_the_check_naming_it(tmp_path, missing):
    result = run_block(tmp_path, stubs_for(tmp_path, omit=(missing,)))
    assert result.returncode != 0, result.stdout
    assert missing in result.stderr, result.stderr


def test_texlive_full_must_be_installed(tmp_path):
    result = run_block(tmp_path, stubs_for(tmp_path, texlive_installed=False))
    assert result.returncode != 0
    assert "texlive-full is not installed" in result.stderr


def test_a_tex_file_texlive_cannot_find_fails_the_check(tmp_path):
    """A partial TeX Live is the divergence the sites' comment warns about."""
    result = run_block(tmp_path, stubs_for(tmp_path, no_tex=("luahyperbolic.sty",)))
    assert result.returncode != 0
    assert "luahyperbolic.sty" in result.stderr


def test_pdf2svg_must_render_the_page(tmp_path):
    """Presence is not enough: a binary whose library is missing must not pass."""
    result = run_block(tmp_path, stubs_for(tmp_path, pdf2svg_breaks=True))
    assert result.returncode != 0
