"""Standard-library static checks for the 1.0.0 documentation release."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
README_FILES = ("README.md", "README.en.md", "README.zh-TW.md")
ASSETS = tuple(f"docs/assets/v1.0.0/{name}" for name in (
    "hero.png", "story-a.png", "story-b.png", "principles.png",
    "architecture.svg", "architecture.mmd", "visual-production.md",
))
RELEASE_FILES = (*README_FILES, *ASSETS, "pyproject.toml", "SKILL.md",
    "codex_capability_router/__init__.py", "CHANGELOG.md",
    "references/discovery-and-provenance.md", "references/routing-policy.md",
    "docs/releases/v1.0.0.md", "docs/validation/v1.0.0-validation.md",
    "scripts/verify_release.py", "tests/test_foundation.py", "tests/test_v1_release.py")
CORE_FACTS = (
    "v1.0.0", "v0.2.0-beta.10", "TaskAnalysis", "digest batches",
    "Host Skill decisions", "Execution Needs", "Provider decisions", "route()",
    "FINALIZED", "ExecutionAttempt", "COMPLETE", "PARTIAL", "needs_detail",
    "SPARSE", "OPAQUE", "app", "mcp", "builtin_tool", "host_tool",
    "fixed top-k", "fixed Skill maximum", "redundancy",
    "SELECTION_REVALIDATION_REQUIRED", "HANDOFF_REJECTION_AFTER_ONE_REFRESH",
    "caller/session-owned cache", "persistent preference learning",
    "automatic Host integration", "private capability inventory",
)
SECRET = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"
    r"|sk-(?:proj-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
LOCAL_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def text(relative: str) -> str:
    return (ROOT / relative).read_bytes().decode("utf-8", errors="strict").replace("\r\n", "\n")


def check_versions() -> None:
    metadata = tomllib.loads(text("pyproject.toml"))
    assert metadata["project"]["version"] == "1.0.0", "package version"
    assert metadata["project"]["dependencies"] == [], "runtime dependencies changed"
    assignments = ast.parse(text("codex_capability_router/__init__.py")).body
    version = next(ast.literal_eval(node.value) for node in assignments
                   if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets))
    assert version == "1.0.0", "import version"
    assert "Contract (1.0.0)" in text("SKILL.md"), "Skill contract version"
    for path in README_FILES:
        header = text(path).split("\n\n", 8)[:8]
        joined = "\n".join(header)
        assert "v1.0.0" in joined and "Stable" in joined, path
        assert "releases/tag/v1.0.0" in text(path), path


def check_readmes() -> None:
    for path in README_FILES:
        content = text(path)
        for fact in CORE_FACTS:
            assert fact.lower() in content.lower(), f"{path}: missing core fact {fact}"
        assert not re.search(r"\b\d+\s+(?:installed\s+)?(?:Skills|Plugins)\b", content), path
        for asset in ASSETS[:6]:
            assert asset in content, f"{path}: unreferenced asset {asset}"
        for destination in LOCAL_LINK.findall(content):
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (ROOT / Path(path).parent / unquote(parsed.path)).resolve()
            assert target.is_relative_to(ROOT), f"{path}: link escapes repository"
            assert target.is_file(), f"{path}: missing local link {parsed.path}"
    zh, en = text("README.md"), text("README.en.md")
    for language in ("powershell", "bash"):
        pattern = rf"```{language}\n(.*?)```"
        zh_blocks, en_blocks = re.findall(pattern, zh, re.S), re.findall(pattern, en, re.S)
        assert zh_blocks and en_blocks, f"{language} installation block missing"
        assert zh_blocks == en_blocks, language
    assert text("README.zh-TW.md") == zh, "Traditional Chinese compatibility page"


def check_assets() -> None:
    for path in ASSETS:
        assert (ROOT / path).is_file(), f"missing asset {path}"
        if path.endswith(".png"):
            data = (ROOT / path).read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG {path}"
            width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
            assert min(width, height) >= 1000, f"insufficient source resolution {path}"
        elif path.endswith(".svg"):
            svg = ET.fromstring(text(path))
            assert svg.tag == "{http://www.w3.org/2000/svg}svg", path
            assert svg.get("viewBox") and svg.get("role") == "img", path
            assert svg.find("{http://www.w3.org/2000/svg}title") is not None, path
            assert svg.find("{http://www.w3.org/2000/svg}desc") is not None, path
    diagram = text("docs/assets/v1.0.0/architecture.mmd")
    for label in ("User Task", "Host TaskAnalysis", "trusted discovery", "digest batches",
                  "Host Skill decisions", "Skill handoff", "Skill Coverage Check",
                  "Execution Needs", "Provider decisions", "route()", "FINALIZED Receipt",
                  "ExecutionAttempt", "Empty: skip Providers"):
        assert label in diagram, f"missing flow stage: {label}"


def check_public_files() -> int:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    paths = sorted(set(filter(None, tracked)) | set(RELEASE_FILES))
    private_roots = {str(Path.home()), Path.home().as_posix(), str(ROOT), ROOT.as_posix()}
    checked = 0
    for relative in paths:
        path = ROOT / relative
        data = path.read_bytes()
        for private in private_roots:
            assert private.encode("utf-8") not in data, f"{relative}: private path"
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".zip"}:
            content = data.decode("utf-8", errors="strict")
            assert "\ufffd" not in content, f"{relative}: replacement character"
            assert not SECRET.search(content), f"{relative}: credential pattern"
            checked += 1
    return checked


def main() -> None:
    check_versions()
    check_readmes()
    check_assets()
    count = check_public_files()
    print(json.dumps({"version": "1.0.0", "version_parity": "PASS", "readme_links": "PASS",
        "readme_assets": "PASS", "svg_xml": "PASS", "utf8_privacy_static": "PASS",
        "text_files_checked": count, "visual_qa": "SEPARATE_OBSERVATION_REQUIRED"}))


if __name__ == "__main__":
    main()
