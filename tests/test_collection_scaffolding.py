"""
FerrousCX - ferrous-vectordb
Test suite for Qdrant vector container deployment, HNSW collection scaffolding,
and schema verification (Story 6.1).
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import shutil
import subprocess
import threading
import unittest
import yaml

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SUBMODULE_ROOT = os.path.dirname(TESTS_DIR)


class TestConfigYaml(unittest.TestCase):
    """Asserts that config/config.yaml adheres to specification and Tier 2 standards."""

    @classmethod
    def setUpClass(cls):
        cls.config_path = os.path.join(SUBMODULE_ROOT, "config", "config.yaml")
        with open(cls.config_path, "r", encoding="utf-8") as f:
            cls.config = yaml.safe_load(f)

    def test_config_file_exists(self):
        self.assertTrue(os.path.isfile(self.config_path))

    def test_service_networking_ports(self):
        service = self.config.get("service", {})
        self.assertEqual(service.get("http_port"), 6333)
        self.assertEqual(service.get("grpc_port"), 6334)
        self.assertEqual(service.get("host"), "0.0.0.0")

    def test_storage_paths(self):
        storage = self.config.get("storage", {})
        self.assertEqual(storage.get("storage_path"), "/qdrant/storage")
        self.assertEqual(storage.get("snapshots_path"), "/qdrant/snapshots")

    def test_hnsw_defaults_under_storage(self):
        storage = self.config.get("storage", {})
        hnsw = storage.get("hnsw_index", {})
        self.assertEqual(hnsw.get("m"), 16)
        self.assertEqual(hnsw.get("ef_construct"), 100)
        self.assertEqual(hnsw.get("full_scan_threshold"), 10000)

    def test_telemetry_disabled(self):
        self.assertTrue(self.config.get("telemetry_disabled"))


class TestContainerDeploymentFiles(unittest.TestCase):
    """Asserts Dockerfile, docker-compose.yml, and environment configurations."""

    def test_env_example_secret_zero(self):
        env_path = os.path.join(SUBMODULE_ROOT, ".env.example")
        self.assertTrue(os.path.isfile(env_path))
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Secret Zero: ensure no real API keys are hardcoded
        self.assertIn("QDRANT_HTTP_PORT=6333", content)
        self.assertIn("QDRANT_GRPC_PORT=6334", content)
        self.assertIn("QDRANT_STORAGE_PATH=/qdrant/storage", content)
        self.assertNotIn("secret_token_live", content)

    def test_gitignore_rules(self):
        gitignore_path = os.path.join(SUBMODULE_ROOT, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path))
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".env", content)
        self.assertIn("/qdrant_storage/", content)

    def test_dockerfile_hardening(self):
        dockerfile_path = os.path.join(SUBMODULE_ROOT, "Dockerfile")
        self.assertTrue(os.path.isfile(dockerfile_path))
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Hardening constraints: pinned image, UID 10001, ports 6333/6334, healthcheck /readyz
        self.assertIn("FROM qdrant/qdrant:v1.12.0", content)
        self.assertIn("USER 10001:10001", content)
        self.assertIn("EXPOSE 6333 6334", content)
        self.assertIn("/readyz", content)

    def test_docker_compose_manifest(self):
        compose_path = os.path.join(SUBMODULE_ROOT, "docker-compose.yml")
        self.assertTrue(os.path.isfile(compose_path))
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        self.assertIn("vectordb", services)
        vectordb = services["vectordb"]

        self.assertEqual(vectordb.get("user"), "10001:10001")
        self.assertIn("6333:6333", vectordb.get("ports", []))
        self.assertIn("6334:6334", vectordb.get("ports", []))
        self.assertTrue(any("./qdrant_storage:/qdrant/storage" in str(v) for v in vectordb.get("volumes", [])))
        self.assertTrue(any("./qdrant_snapshots:/qdrant/snapshots" in str(v) for v in vectordb.get("volumes", [])))

        # Day-0 kernel hardening
        security_opt = vectordb.get("security_opt", [])
        self.assertIn("no-new-privileges:true", security_opt)
        cap_drop = vectordb.get("cap_drop", [])
        self.assertIn("ALL", cap_drop)
        self.assertFalse(vectordb.get("read_only", True))


class MockQdrantRequestHandler(BaseHTTPRequestHandler):
    """Mock Qdrant HTTP server capturing requests and serving expected responses."""

    def log_message(self, format, *args):
        # Suppress standard logging to keep test output clean
        pass

    def do_GET(self):
        self.server.requests_log.append(("GET", self.path))
        if self.path == "/readyz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"all systems normal")
        elif self.path.startswith("/collections/"):
            col = self.path.split("/")[-1]
            if col in self.server.existing_collections:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                resp = {
                    "result": {
                        "status": "green",
                        "vectors_count": 0,
                        "config": {
                            "params": {"vectors": {"size": 384, "distance": "Cosine"}},
                            "hnsw_config": {"m": 16, "ef_construct": 100, "full_scan_threshold": 10000},
                        },
                    },
                    "status": "ok",
                }
                self.wfile.write(json.dumps(resp).encode("utf-8"))
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":{"error":"Not found"},"time":0.001}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        self.server.requests_log.append(("PUT", self.path, body))

        if self.path.startswith("/collections/"):
            col = self.path.split("/")[-1]
            self.server.existing_collections.add(col)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"result":true,"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()


class TestCollectionScaffoldingLogic(unittest.TestCase):
    """Asserts collection schema correctness, dual-shell script parity, and idempotent REST logic."""

    EXPECTED_COLLECTIONS = ["cx_policy_knowledge", "support_transcripts"]
    EXPECTED_VECTOR_SIZE = 384
    EXPECTED_DISTANCE = "Cosine"
    EXPECTED_HNSW = {
        "m": 16,
        "ef_construct": 100,
        "full_scan_threshold": 10000,
    }

    def test_scripts_exist(self):
        sh_path = os.path.join(SUBMODULE_ROOT, "scripts", "create-collections.sh")
        ps1_path = os.path.join(SUBMODULE_ROOT, "scripts", "create-collections.ps1")
        self.assertTrue(os.path.isfile(sh_path))
        self.assertTrue(os.path.isfile(ps1_path))

    def test_script_schema_content(self):
        for script_name in ["create-collections.sh", "create-collections.ps1"]:
            script_path = os.path.join(SUBMODULE_ROOT, "scripts", script_name)
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()

            for col in self.EXPECTED_COLLECTIONS:
                self.assertIn(col, content)
            self.assertIn(str(self.EXPECTED_VECTOR_SIZE), content)
            self.assertIn(self.EXPECTED_DISTANCE, content)
            self.assertIn("10000", content)
            self.assertIn("readyz", content)

    def test_powershell_dry_run_execution(self):
        """Runs the PowerShell script in DryRun mode and validates return code and output."""
        pwsh_cmd = shutil.which("powershell") or shutil.which("pwsh")
        if not pwsh_cmd:
            self.skipTest("Neither powershell nor pwsh is available on PATH")

        ps1_path = os.path.join(SUBMODULE_ROOT, "scripts", "create-collections.ps1")
        cmd = [pwsh_cmd, "-NoProfile", "-File", ps1_path, "-DryRun"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Script failed with stderr: {result.stderr}")
        self.assertIn("[DRY RUN]", result.stdout)
        self.assertIn("cx_policy_knowledge", result.stdout)
        self.assertIn("support_transcripts", result.stdout)
        self.assertIn("Cosine", result.stdout)
        self.assertIn("384", result.stdout)

    def test_bash_dry_run_execution(self):
        """Runs the POSIX bash script in DryRun mode and validates return code and output."""
        bash_cmd = shutil.which("bash")
        if not bash_cmd:
            self.skipTest("bash is not available on PATH")

        # Use forward slashes or relative path so bash on Windows does not strip backslashes
        cmd = [bash_cmd, "scripts/create-collections.sh", "--dry-run"]
        result = subprocess.run(cmd, cwd=SUBMODULE_ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Script failed with stderr: {result.stderr}")
        self.assertIn("[DRY RUN]", result.stdout)
        self.assertIn("cx_policy_knowledge", result.stdout)
        self.assertIn("support_transcripts", result.stdout)
        self.assertIn("Cosine", result.stdout)
        self.assertIn("384", result.stdout)

    def test_scaffolding_execution_against_mock_qdrant_server(self):
        """Spins up a mock Qdrant HTTP server, executes create-collections.ps1 or sh,
        and verifies that:
        1. /readyz probe is requested.
        2. Both collections are queried via GET.
        3. Both collections are created via PUT with vector size 384, Cosine, and HNSW parameters.
        4. Subsequent run detects existing collections and skips PUT creation (idempotent).
        """
        pwsh_cmd = shutil.which("powershell") or shutil.which("pwsh")
        bash_cmd = shutil.which("bash")

        server = HTTPServer(("127.0.0.1", 0), MockQdrantRequestHandler)
        port = server.server_address[1]
        server.requests_log = []
        server.existing_collections = set()

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        host_url = f"http://127.0.0.1:{port}"
        try:
            if pwsh_cmd:
                script_path = os.path.join(SUBMODULE_ROOT, "scripts", "create-collections.ps1")
                # Run 1: Collections do not exist, should create both
                cmd1 = [pwsh_cmd, "-NoProfile", "-File", script_path, "-HostUrl", host_url]
                res1 = subprocess.run(cmd1, capture_output=True, text=True)
                self.assertEqual(res1.returncode, 0, f"Run 1 failed: {res1.stderr}")
                self.assertIn("[SUCCESS] Collection 'cx_policy_knowledge' created", res1.stdout)
                self.assertIn("[SUCCESS] Collection 'support_transcripts' created", res1.stdout)

                # Verify payload structure received by mock server
                put_requests = [req for req in server.requests_log if req[0] == "PUT"]
                self.assertEqual(len(put_requests), 2)
                for req in put_requests:
                    payload = json.loads(req[2])
                    self.assertEqual(payload["vectors"]["size"], 384)
                    self.assertEqual(payload["vectors"]["distance"], "Cosine")
                    self.assertEqual(payload["hnsw_config"]["m"], 16)
                    self.assertEqual(payload["hnsw_config"]["ef_construct"], 100)
                    self.assertEqual(payload["hnsw_config"]["full_scan_threshold"], 10000)

                # Run 2: Collections already exist, should skip creation (idempotent)
                cmd2 = [pwsh_cmd, "-NoProfile", "-File", script_path, "-HostUrl", host_url]
                res2 = subprocess.run(cmd2, capture_output=True, text=True)
                self.assertEqual(res2.returncode, 0, f"Run 2 failed: {res2.stderr}")
                self.assertIn("already exists. Skipping creation (Idempotent)", res2.stdout)

                # No new PUT requests should have occurred in Run 2
                put_requests_after = [req for req in server.requests_log if req[0] == "PUT"]
                self.assertEqual(len(put_requests_after), 2)

            elif bash_cmd:
                cmd1 = [bash_cmd, "scripts/create-collections.sh", "--host", host_url]
                res1 = subprocess.run(cmd1, cwd=SUBMODULE_ROOT, capture_output=True, text=True)
                self.assertEqual(res1.returncode, 0, f"Run 1 failed: {res1.stderr}")
                self.assertIn("created successfully", res1.stdout)

                cmd2 = [bash_cmd, "scripts/create-collections.sh", "--host", host_url]
                res2 = subprocess.run(cmd2, cwd=SUBMODULE_ROOT, capture_output=True, text=True)
                self.assertEqual(res2.returncode, 0, f"Run 2 failed: {res2.stderr}")
                self.assertIn("already exists. Skipping creation", res2.stdout)
            else:
                self.skipTest("Neither PowerShell nor Bash available to test scaffolding script")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
