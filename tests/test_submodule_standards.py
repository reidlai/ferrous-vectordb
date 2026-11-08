#!/usr/bin/env python3
"""
test_submodule_standards.py: Unit tests for Submodule Documentation & Tier 2 Security CI Gate (Story 6.3).
Submodule: ferrous-vectordb
Standards: AD-13, NFR-10, NFR-11, NFR-13
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class SubmoduleStandardsUnitTests(unittest.TestCase):
    """Validates documentation, pre-commit configuration, and Tier 2 DevSecOps standards for ferrous-vectordb."""

    def test_01_ad13_pure_submodule_structure(self):
        """Verifies AD-13 invariant: pure submodule with no .github/workflows directory."""
        github_dir = REPO_ROOT / ".github"
        workflows_dir = github_dir / "workflows"
        self.assertFalse(
            workflows_dir.exists(),
            "AD-13 violation: ferrous-vectordb must not contain .github/workflows directory (CI consolidated at root)",
        )

    def test_02_pre_commit_configuration(self):
        """Verifies .pre-commit-config.yaml contains Gitleaks, hygiene formatters, and local test hooks."""
        pre_commit_file = REPO_ROOT / ".pre-commit-config.yaml"
        self.assertTrue(pre_commit_file.is_file(), ".pre-commit-config.yaml must exist at repo root")

        content = pre_commit_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        self.assertIsInstance(parsed, dict, ".pre-commit-config.yaml must be valid YAML dictionary")
        self.assertIn("repos", parsed, ".pre-commit-config.yaml must define repos list")
        self.assertIsInstance(parsed["repos"], list, "repos must be a list")

        # Collect all configured hook ids from parsed structure
        configured_hooks = []
        for repo_entry in parsed["repos"]:
            self.assertIn("hooks", repo_entry, f"Repo {repo_entry} must define hooks")
            for hook in repo_entry.get("hooks", []):
                configured_hooks.append(hook.get("id"))

        expected_hooks = [
            "trailing-whitespace",
            "end-of-file-fixer",
            "check-yaml",
            "check-added-large-files",
            "gitleaks",
            "test-collection-scaffolding",
            "test-embedding-ingestion",
            "test-submodule-standards",
            "test-container-packaging",
        ]
        for expected_id in expected_hooks:
            self.assertIn(
                expected_id,
                configured_hooks,
                f"Missing expected hook {expected_id} in parsed .pre-commit-config.yaml",
            )

    def test_03_build_and_scan_scripts_presence_and_parity(self):
        """Verifies local build-and-scan scripts configure Hadolint, Docker build, and Trivy scans."""
        ps1_script = REPO_ROOT / "scripts" / "build-and-scan.ps1"
        sh_script = REPO_ROOT / "scripts" / "build-and-scan.sh"

        self.assertTrue(ps1_script.is_file(), "scripts/build-and-scan.ps1 must exist")
        self.assertTrue(sh_script.is_file(), "scripts/build-and-scan.sh must exist")

        ps1_content = ps1_script.read_text(encoding="utf-8")
        sh_content = sh_script.read_text(encoding="utf-8")

        for content, name in [(ps1_content, "build-and-scan.ps1"), (sh_content, "build-and-scan.sh")]:
            self.assertIn("hadolint", content, f"{name} must contain Hadolint audit")
            self.assertIn("Dockerfile", content, f"{name} must reference Dockerfile")
            self.assertIn("ferrous-vectordb:latest", content, f"{name} must target ferrous-vectordb:latest")
            self.assertIn("trivy", content, f"{name} must contain Trivy vulnerability scan")
            self.assertIn("HIGH,CRITICAL", content, f"{name} must scan for HIGH,CRITICAL severities")
            self.assertIn("--ignore-unfixed", content, f"{name} must ignore unfixed vulnerabilities")
            self.assertIn("--exit-code 1", content, f"{name} must exit with code 1 on vulnerability findings")
            self.assertIn("aquasec/trivy", content, f"{name} must support aquasec/trivy container fallback")

    def test_04_build_and_scan_dry_run_execution(self):
        """Verifies both PowerShell and POSIX build-and-scan scripts run successfully in dry-run mode."""
        ps1_script = REPO_ROOT / "scripts" / "build-and-scan.ps1"
        sh_script = REPO_ROOT / "scripts" / "build-and-scan.sh"

        # PowerShell Dry-Run
        ps_exe = shutil.which("powershell") or shutil.which("pwsh")
        if ps_exe:
            res_ps = subprocess.run(
                [ps_exe, "-NoProfile", "-File", str(ps1_script), "-DryRun"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            self.assertEqual(res_ps.returncode, 0, f"PowerShell dry-run failed:\n{res_ps.stderr}\n{res_ps.stdout}")
            self.assertIn("[DRY-RUN] hadolint Dockerfile", res_ps.stdout)
            self.assertIn("docker build -t ferrous-vectordb:latest", res_ps.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL", res_ps.stdout)

        # POSIX bash Dry-Run
        bash_exe = shutil.which("bash")
        self.assertTrue(
            bool(ps_exe or bash_exe),
            "No shell interpreter (PowerShell or Bash) available to verify build-and-scan",
        )
        if bash_exe:
            # Use relative POSIX path since bash on Windows may mangle Windows backslashes
            rel_sh = sh_script.relative_to(REPO_ROOT).as_posix()
            res_sh = subprocess.run(
                [bash_exe, rel_sh, "--dry-run"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            self.assertEqual(res_sh.returncode, 0, f"Bash dry-run failed:\n{res_sh.stderr}\n{res_sh.stdout}")
            self.assertIn("[DRY-RUN] hadolint Dockerfile", res_sh.stdout)
            self.assertIn("docker build -t ferrous-vectordb:latest", res_sh.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL", res_sh.stdout)

    def test_05_readme_architecture_and_c4_slice(self):
        """Verifies README.md contains Mermaid C4 architecture slice and interaction flow."""
        readme = REPO_ROOT / "README.md"
        self.assertTrue(readme.is_file(), "README.md must exist")

        content = readme.read_text(encoding="utf-8")
        self.assertIn("```mermaid", content, "README must contain Mermaid architecture diagrams")
        self.assertIn("ferrous-agent", content, "README must document integration with ferrous-agent")
        self.assertIn("rig-core", content, "README must document rig-core copilot")
        self.assertIn("cx_policy_knowledge", content, "README must document cx_policy_knowledge collection")
        self.assertIn("support_transcripts", content, "README must document support_transcripts collection")

    def test_06_readme_collection_schemas_and_ports(self):
        """Verifies README.md contains collection schema tables and port mapping tables."""
        readme = REPO_ROOT / "README.md"
        content = readme.read_text(encoding="utf-8")

        # Port mapping table assertions
        self.assertIn("6333", content, "README must document HTTP REST / Web UI port 6333")
        self.assertIn("6334", content, "README must document gRPC port 6334")
        self.assertIn("/readyz", content, "README must document /readyz readiness endpoint")

        # Schema table assertions
        self.assertIn("384", content, "README must document 384-dimensional vector embedding")
        self.assertIn("Cosine", content, "README must document Cosine similarity metric")
        self.assertIn("sop_id", content, "README must document sop_id payload field")
        self.assertIn("dialogue_id", content, "README must document dialogue_id payload field")

    def test_07_readme_goodwill_policy_and_quickstart(self):
        """Verifies README.md documents Goodwill Policy §4.2 citations and <3 min quickstart."""
        readme = REPO_ROOT / "README.md"
        content = readme.read_text(encoding="utf-8")

        # Goodwill Policy §4.2 assertions
        self.assertTrue(
            "4.2" in content or "§4.2" in content,
            "README must cite Goodwill credit policy §4.2",
        )
        self.assertTrue(
            "$20" in content or "$20.00" in content,
            "README must document the $20 ceiling invariant",
        )
        self.assertTrue(
            "$15" in content or "$15.00" in content,
            "README must document Carlos's $15 tier 1 credit limit",
        )

        # Standalone Quickstart assertions
        self.assertIn("Quickstart", content, "README must contain Quickstart section")
        self.assertIn("build-and-scan", content, "Quickstart must reference build-and-scan script")

    def test_08_secret_and_credential_hygiene(self):
        """Verifies no committed plaintext secrets, API keys, or private key blocks exist in repository."""
        secret_patterns = [
            re.compile(r"-----BEGIN\s+(RSA|OPENSSH|EC|DSA)?\s*PRIVATE KEY-----"),
            re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
            re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{30,}"),
        ]

        text_suffixes = {".py", ".sh", ".ps1", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".example"}

        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(p in path.parts for p in (".git", "__pycache__", ".venv", "venv")):
                continue
            if path.suffix.lower() not in text_suffixes and path.name not in ("Dockerfile", ".env", ".env.example"):
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for pattern in secret_patterns:
                match = pattern.search(content)
                self.assertIsNone(
                    match,
                    f"Possible secret detected in {path.relative_to(REPO_ROOT)}: {match.group(0) if match else ''}",
                )


if __name__ == "__main__":
    unittest.main()
