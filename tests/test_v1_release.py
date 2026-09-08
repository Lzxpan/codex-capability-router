"""Release documentation checks; no changes to Router execution semantics."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py"
SPEC = importlib.util.spec_from_file_location("release_checks", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class StableReleaseTests(unittest.TestCase):
    def test_current_versions_are_consistent(self) -> None:
        checks.check_versions()

    def test_bilingual_contract_and_local_links(self) -> None:
        checks.check_readmes()

    def test_installation_parity_handles_line_endings_and_missing_blocks(self) -> None:
        # Catch CRLF silently bypassing comparison or empty matches passing parity.
        original_read = Path.read_bytes
        for ending in ("lf", "crlf", "mixed"):
            for case in ("equal", "different", "missing"):
                with self.subTest(ending=ending, case=case):
                    def read_bytes(path: Path) -> bytes:
                        data = original_read(path)
                        if path.name in checks.README_FILES:
                            data = data.replace(b"\r\n", b"\n")
                            if case == "different" and path.name == "README.en.md":
                                data = data.replace(b"```powershell\n", b"```powershell\ngit status\n")
                            elif case == "missing":
                                data = data.replace(b"```powershell\n", b"```text\n")
                            if ending == "crlf" or (ending == "mixed" and path.name == "README.en.md"):
                                data = data.replace(b"\n", b"\r\n")
                        return data
                    with patch.object(Path, "read_bytes", read_bytes):
                        if case == "equal":
                            checks.check_readmes()
                        else:
                            with self.assertRaisesRegex(AssertionError, "powershell"):
                                checks.check_readmes()

    def test_assets_and_architecture_source(self) -> None:
        checks.check_assets()

    def test_secret_patterns_reject_synthetic_credentials(self) -> None:
        for prefix in ("ghp_", "github_pat_", "sk-proj-"):
            with self.subTest(prefix=prefix):
                self.assertIsNotNone(checks.SECRET.search(prefix + "x" * 50))
        self.assertIsNone(checks.SECRET.search("Read credentials from the Host, never publish them."))


if __name__ == "__main__":
    unittest.main()
