#!/usr/bin/env python3
"""
test_container_packaging.py: Unit tests for ferrous-vectordb Custom Container & Knowledge Seeder Docker Image Build (Story 6.4).
Submodule: ferrous-vectordb
Standards: AD-6, AD-13, NFR-10..13
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class MockBootstrappingServerHandler(BaseHTTPRequestHandler):
    """Simulates Qdrant REST endpoints to test collection bootstrapping."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/readyz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "18")
            self.end_headers()
            self.wfile.write(b"all systems normal")
            return

        if self.path.startswith("/collections/"):
            col_name = self.path.split("/")[2].split("?")[0].strip()
            if col_name in self.server.collections:
                resp = json.dumps({"status": "ok", "result": {"status": "green"}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            else:
                resp = json.dumps({"status": "error", "message": "Not found"}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        payload = json.loads(body) if body else {}

        if "/points" in self.path:
            # Point upsert
            resp = json.dumps({"status": "ok", "result": {"operation_id": 1, "status": "completed"}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if self.path.startswith("/collections/"):
            col_name = self.path.split("/")[2].split("?")[0].strip()
            self.server.created_collections[col_name] = payload
            self.server.collections.add(col_name)

            resp = json.dumps({"status": "ok", "result": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if "/points/search" in self.path:
            search_result = {
                "result": [
                    {
                        "id": "1",
                        "score": 0.88,
                        "payload": {"sop_id": "SOP-001", "title": "Courtesy Credit §4.2", "section": "§4.2"}
                    }
                ]
            }
            resp = json.dumps(search_result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_response(404)
        self.end_headers()


class ContainerPackagingUnitTests(unittest.TestCase):
    """Validates Dockerfile, Dockerfile.seeder, Compose manifest, DevSecOps scripts, and seeder packaging."""

    def test_01_qdrant_dockerfile_packaging(self):
        """Verifies production Qdrant Dockerfile hardening, UID 10001, readiness healthcheck, and labels."""
        dockerfile = REPO_ROOT / "Dockerfile"
        self.assertTrue(dockerfile.is_file(), "Dockerfile must exist at repo root")

        content = dockerfile.read_text(encoding="utf-8")

        # Pinned base tag and rootless non-root user
        self.assertIn("FROM qdrant/qdrant:v1.12.0", content)
        self.assertIn("USER 10001:10001", content)

        # Port exposures and persistence
        self.assertIn("EXPOSE 6333 6334", content)
        self.assertIn("/qdrant/storage", content)
        self.assertIn("/qdrant/snapshots", content)

        # Healthcheck readiness probe
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("/readyz", content)

        # OCI Metadata Labels
        self.assertIn("org.opencontainers.image.title=\"ferrous-vectordb\"", content)
        self.assertIn("org.opencontainers.image.vendor=\"FerrousCX\"", content)

    def test_02_seeder_dockerfile_packaging(self):
        """Verifies seeder Dockerfile.seeder hardening, minimal Alpine base, UID 10001, and script copying."""
        dockerfile_seeder = REPO_ROOT / "Dockerfile.seeder"
        self.assertTrue(dockerfile_seeder.is_file(), "Dockerfile.seeder must exist at repo root")

        content = dockerfile_seeder.read_text(encoding="utf-8")

        # Minimal pinned base image
        self.assertIn("FROM python:3.12-alpine", content)

        # Non-root user creation and execution
        self.assertIn("addgroup -g 10001", content)
        self.assertIn("adduser -u 10001", content)
        self.assertIn("USER 10001:10001", content)

        # Directory and scripts packaging
        self.assertIn("WORKDIR /app", content)
        self.assertIn("COPY --chown=10001:10001 scripts/seed-embeddings.py", content)
        self.assertIn("COPY --chown=10001:10001 data/", content)

        # Entrypoint configuration
        self.assertIn("ENTRYPOINT [\"python\", \"/app/scripts/seed-embeddings.py\"]", content)

        # OCI Metadata Labels
        self.assertIn("org.opencontainers.image.title=\"ferrous-vectordb-seeder\"", content)
        self.assertIn("org.opencontainers.image.vendor=\"FerrousCX\"", content)

    def test_03_docker_compose_multi_service_orchestration(self):
        """Verifies docker-compose.yml defines both vectordb and seeder with health dependency."""
        compose_file = REPO_ROOT / "docker-compose.yml"
        self.assertTrue(compose_file.is_file(), "docker-compose.yml must exist at repo root")

        content = compose_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)

        self.assertIn("services", parsed)
        services = parsed["services"]

        # 1. vectordb service assertions
        self.assertIn("vectordb", services)
        vectordb = services["vectordb"]
        self.assertEqual(vectordb.get("image"), "ferrous-vectordb:latest")
        self.assertEqual(vectordb.get("user"), "10001:10001")
        self.assertIn("6333:6333", vectordb.get("ports", []))
        self.assertIn("6334:6334", vectordb.get("ports", []))
        self.assertIn("healthcheck", vectordb)
        self.assertIn("/readyz", str(vectordb["healthcheck"].get("test", [])))

        # 2. seeder service assertions
        self.assertIn("seeder", services)
        seeder = services["seeder"]
        self.assertEqual(seeder.get("image"), "ferrous-vectordb-seeder:latest")
        self.assertEqual(seeder.get("user"), "10001:10001")

        # Dependency with service_healthy condition
        self.assertIn("depends_on", seeder)
        depends_on = seeder["depends_on"]
        self.assertIn("vectordb", depends_on)
        self.assertEqual(depends_on["vectordb"].get("condition"), "service_healthy")

        # Hardening options
        for s_name in ["vectordb", "seeder"]:
            s_conf = services[s_name]
            self.assertIn("no-new-privileges:true", s_conf.get("security_opt", []))
            self.assertIn("ALL", s_conf.get("cap_drop", []))

    def test_04_dual_shell_build_and_scan_dual_targets(self):
        """Verifies dual-shell build-and-scan scripts configure both Dockerfiles and images."""
        ps1_script = REPO_ROOT / "scripts" / "build-and-scan.ps1"
        sh_script = REPO_ROOT / "scripts" / "build-and-scan.sh"

        self.assertTrue(ps1_script.is_file())
        self.assertTrue(sh_script.is_file())

        for script, name in [(ps1_script, "build-and-scan.ps1"), (sh_script, "build-and-scan.sh")]:
            content = script.read_text(encoding="utf-8")
            self.assertIn("Dockerfile", content, f"{name} must audit Dockerfile")
            self.assertIn("Dockerfile.seeder", content, f"{name} must audit Dockerfile.seeder")
            self.assertIn("ferrous-vectordb:latest", content, f"{name} must target ferrous-vectordb:latest")
            self.assertIn("ferrous-vectordb-seeder:latest", content, f"{name} must target ferrous-vectordb-seeder:latest")
            self.assertIn("trivy", content, f"{name} must execute Trivy")
            self.assertIn("HIGH,CRITICAL", content, f"{name} must scan HIGH,CRITICAL severities")
            self.assertIn("--ignore-unfixed", content, f"{name} must ignore unfixed CVEs")
            self.assertIn("--exit-code 1", content, f"{name} must exit 1 on CVE detection")

    def test_05_build_and_scan_dual_target_dry_run(self):
        """Verifies dry-run execution processes both Dockerfiles and container images."""
        ps1_script = REPO_ROOT / "scripts" / "build-and-scan.ps1"
        sh_script = REPO_ROOT / "scripts" / "build-and-scan.sh"

        ps_exe = shutil.which("powershell") or shutil.which("pwsh")
        bash_exe = shutil.which("bash")
        self.assertTrue(bool(ps_exe or bash_exe), "No shell interpreter found for dry-run tests")

        if ps_exe:
            res_ps = subprocess.run(
                [ps_exe, "-NoProfile", "-File", str(ps1_script), "-dry-run"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            self.assertEqual(res_ps.returncode, 0, f"PowerShell dry-run failed:\n{res_ps.stderr}\n{res_ps.stdout}")
            self.assertIn("[DRY-RUN] hadolint Dockerfile", res_ps.stdout)
            self.assertIn("[DRY-RUN] hadolint Dockerfile.seeder", res_ps.stdout)
            self.assertIn("docker build -t ferrous-vectordb:latest", res_ps.stdout)
            self.assertIn("docker build -t ferrous-vectordb-seeder:latest", res_ps.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ferrous-vectordb:latest", res_ps.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ferrous-vectordb-seeder:latest", res_ps.stdout)

        if bash_exe:
            rel_sh = sh_script.relative_to(REPO_ROOT).as_posix()
            res_sh = subprocess.run(
                [bash_exe, rel_sh, "--dry-run"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            self.assertEqual(res_sh.returncode, 0, f"Bash dry-run failed:\n{res_sh.stderr}\n{res_sh.stdout}")
            self.assertIn("[DRY-RUN] hadolint Dockerfile", res_sh.stdout)
            self.assertIn("[DRY-RUN] hadolint Dockerfile.seeder", res_sh.stdout)
            self.assertIn("docker build -t ferrous-vectordb:latest", res_sh.stdout)
            self.assertIn("docker build -t ferrous-vectordb-seeder:latest", res_sh.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ferrous-vectordb:latest", res_sh.stdout)
            self.assertIn("trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ferrous-vectordb-seeder:latest", res_sh.stdout)

    def test_06_seeder_dry_run_point_counts(self):
        """Verifies seeder CLI dry-run executes cleanly and generates expected points."""
        import sys
        seeder_py = REPO_ROOT / "scripts" / "seed-embeddings.py"
        res = subprocess.run(
            [sys.executable, str(seeder_py), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(res.returncode, 0, f"Seeder dry-run failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("22 SOP points", res.stdout)
        self.assertIn("8 transcript points", res.stdout)
        self.assertIn("[SUCCESS] DRY-RUN completed successfully", res.stdout)

    def test_07_seeder_automatic_collection_bootstrapping(self):
        """Verifies QdrantRestClient automatically bootstraps missing collections with 384-dim Cosine config."""
        import sys
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import importlib
        seed_mod = importlib.import_module("seed-embeddings")
        QdrantRestClient = seed_mod.QdrantRestClient

        server = HTTPServer(("127.0.0.1", 0), MockBootstrappingServerHandler)
        server.collections = {"cx_policy_knowledge"}
        server.created_collections = {}
        port = server.server_address[1]

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = QdrantRestClient(host=f"http://127.0.0.1:{port}")

            # 1. Existing collection: check_collection returns True, ensure_collection creates nothing
            self.assertTrue(client.check_collection("cx_policy_knowledge"))
            self.assertTrue(client.ensure_collection("cx_policy_knowledge"))
            self.assertNotIn("cx_policy_knowledge", server.created_collections)

            # 2. Missing collection: check_collection returns False, ensure_collection creates it
            self.assertFalse(client.check_collection("support_transcripts"))
            res = client.ensure_collection("support_transcripts")
            self.assertTrue(res)

            # Verify collection payload sent to Qdrant
            self.assertIn("support_transcripts", server.created_collections)
            col_payload = server.created_collections["support_transcripts"]
            self.assertEqual(col_payload.get("vectors", {}).get("size"), 384)
            self.assertEqual(col_payload.get("vectors", {}).get("distance"), "Cosine")
            self.assertEqual(col_payload.get("hnsw_config", {}).get("m"), 16)
        finally:
            server.shutdown()
            server.server_close()

    def test_08_seeder_cli_bootstrapping_end_to_end(self):
        """Verifies running seeder CLI against fresh Qdrant bootstraps collections before point upserts."""
        import sys
        seeder_py = REPO_ROOT / "scripts" / "seed-embeddings.py"

        server = HTTPServer(("127.0.0.1", 0), MockBootstrappingServerHandler)
        server.collections = set()  # Empty: collections must be bootstrapped
        server.created_collections = {}
        port = server.server_address[1]

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            cmd = [
                sys.executable,
                str(seeder_py),
                "--host", f"http://127.0.0.1:{port}",
                "--limit", "2",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
            self.assertEqual(res.returncode, 0, f"Seeder CLI bootstrapping failed:\n{res.stderr}\n{res.stdout}")
            self.assertIn("cx_policy_knowledge", server.created_collections, "Must bootstrap cx_policy_knowledge")
            self.assertIn("support_transcripts", server.created_collections, "Must bootstrap support_transcripts")
            self.assertIn("Collection 'cx_policy_knowledge' verified present.", res.stdout)
            self.assertIn("Collection 'support_transcripts' verified present.", res.stdout)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
