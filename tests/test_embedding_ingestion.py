"""
FerrousCX - ferrous-vectordb
Test suite for Automated Knowledge Base Ingestion & Embedding Seeding (Story 6.2).
Asserts dataset provisioning, embedding generation (384-dim, L2-normalized),
Qdrant REST point upserts, semantic search score (>0.82), and sub-5ms query latency.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SUBMODULE_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(SUBMODULE_ROOT, "scripts")
DATA_DIR = os.path.join(SUBMODULE_ROOT, "data")
SOPS_DIR = os.path.join(DATA_DIR, "sops")
TRANSCRIPTS_FILE = os.path.join(DATA_DIR, "raw", "abcd", "abcd_dialogues.json")

# Import embedding functions directly from seed-embeddings script
sys.path.insert(0, SCRIPTS_DIR)
import importlib
seed_embeddings = importlib.import_module("seed-embeddings")
generate_embedding = seed_embeddings.generate_embedding
cosine_similarity = seed_embeddings.cosine_similarity
parse_sop_file = seed_embeddings.parse_sop_file
parse_abcd_dialogues = seed_embeddings.parse_abcd_dialogues
QdrantRestClient = seed_embeddings.QdrantRestClient


class TestDatasetProvisioning(unittest.TestCase):
    """Verifies existence, structure, and offline fallback of enterprise SOPs and ABCD datasets."""

    def test_required_sop_files_exist(self):
        expected_sops = [
            "SOP-001-Courtesy-Credit-Issuance.md",
            "SOP-002-Carrier-Delay-Escalation.md",
            "SOP-003-Customer-Dispute-Resolution.md"
        ]
        for sop in expected_sops:
            path = os.path.join(SOPS_DIR, sop)
            self.assertTrue(os.path.isfile(path), f"Missing SOP file: {path}")

    def test_sop_001_goodwill_policy_content(self):
        sop_path = os.path.join(SOPS_DIR, "SOP-001-Courtesy-Credit-Issuance.md")
        with open(sop_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Goodwill Policy §4.2", content)
        self.assertIn("sla delivery delay courtesy credit rules", content.lower())
        self.assertIn("carrier breach compensation thresholds", content.lower())
        self.assertIn("$20.00", content)

    def test_abcd_dialogues_dataset_validity(self):
        self.assertTrue(os.path.isfile(TRANSCRIPTS_FILE))
        with open(TRANSCRIPTS_FILE, "r", encoding="utf-8") as f:
            dialogues = json.load(f)

        self.assertIsInstance(dialogues, list)
        self.assertGreaterEqual(len(dialogues), 5)

        for d in dialogues:
            self.assertIn("dialogue_id", d)
            self.assertIn("scenario", d)
            self.assertIn("transcript", d)
            self.assertTrue(len(d["transcript"]) > 0)

    def test_powershell_download_offline(self):
        ps_executable = shutil.which("powershell") or shutil.which("pwsh")
        if not ps_executable:
            self.skipTest("PowerShell not installed on host")

        ps_script = os.path.join(SCRIPTS_DIR, "download-datasets.ps1")
        cmd = [ps_executable, "-ExecutionPolicy", "Bypass", "-File", ps_script, "-Offline"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"PowerShell downloader failed: {proc.stderr}")
        self.assertIn("All enterprise SOPs and ABCD benchmark datasets are present", proc.stdout)

    def test_bash_download_offline(self):
        bash_executable = shutil.which("bash")
        if not bash_executable:
            self.skipTest("Bash not installed on host")

        # Use forward slashes and relative path from submodule root for Windows bash compatibility
        cmd = [bash_executable, "scripts/download-datasets.sh", "--offline"]
        proc = subprocess.run(cmd, cwd=SUBMODULE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"Bash downloader failed: {proc.stderr}")
        self.assertIn("All enterprise SOPs and ABCD benchmark datasets are present", proc.stdout)


class TestEmbeddingGenerator(unittest.TestCase):
    """Verifies vector geometry, normalization, determinism, and semantic score assertions."""

    def test_vector_dimension_is_384(self):
        sample_texts = [
            "Goodwill credit policy §4.2 delivery delay courtesy credit rules",
            "Carrier logistics escalation protocols for São Paulo hub",
            "Customer dispute chargeback evidence submission"
        ]
        for text in sample_texts:
            vec = generate_embedding(text, dim=384, use_heavy_ml=False)
            self.assertEqual(len(vec), 384)

    def test_vector_l2_normalization(self):
        vec = generate_embedding("SLA delivery delay courtesy credit rules", dim=384, use_heavy_ml=False)
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_deterministic_generation(self):
        text = "Idempotent vector generation check for FerrousCX copilot"
        v1 = generate_embedding(text, dim=384, use_heavy_ml=False)
        v2 = generate_embedding(text, dim=384, use_heavy_ml=False)
        self.assertEqual(v1, v2)

    def test_empty_input_graceful_handling(self):
        v_empty = generate_embedding("", dim=384, use_heavy_ml=False)
        self.assertEqual(len(v_empty), 384)
        norm = math.sqrt(sum(x * x for x in v_empty))
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_semantic_similarity_assertion_sop_4_2(self):
        """
        Acceptance requirement:
        Dispatching search query 'SLA delivery delay courtesy credit rules' returns
        SOP §4.2 with similarity score > 0.82.
        """
        query = "SLA delivery delay courtesy credit rules"
        sop1_path = os.path.join(SOPS_DIR, "SOP-001-Courtesy-Credit-Issuance.md")
        points = parse_sop_file(sop1_path)

        sec_4_2_point = None
        for pt in points:
            if "§4.2" in pt["payload"]["title"] or "4.2" in pt["payload"]["section"]:
                sec_4_2_point = pt
                break

        self.assertIsNotNone(sec_4_2_point, "Could not find SOP §4.2 section in SOP-001")

        q_vec = generate_embedding(query, dim=384, use_heavy_ml=False)
        doc_vec = sec_4_2_point["vector"]
        score = cosine_similarity(q_vec, doc_vec)

        # Assert score > 0.82
        self.assertGreater(score, 0.82, f"Cosine similarity score {score:.4f} is not > 0.82")

    def test_semantic_ranking_separation(self):
        """
        Verifies that query 'SLA delivery delay courtesy credit rules' ranks
        SOP §4.2 significantly higher than unrelated SOPs (SOP-002, SOP-003).
        """
        query = "SLA delivery delay courtesy credit rules"
        q_vec = generate_embedding(query, dim=384, use_heavy_ml=False)

        sop1_points = parse_sop_file(os.path.join(SOPS_DIR, "SOP-001-Courtesy-Credit-Issuance.md"))
        sop2_points = parse_sop_file(os.path.join(SOPS_DIR, "SOP-002-Carrier-Delay-Escalation.md"))
        sop3_points = parse_sop_file(os.path.join(SOPS_DIR, "SOP-003-Customer-Dispute-Resolution.md"))

        score_4_2 = max(
            (
                cosine_similarity(q_vec, pt["vector"])
                for pt in sop1_points
                if "§4.2" in pt["payload"]["title"] or "4.2" in pt["payload"]["section"]
            ),
            default=0.0,
        )

        score_sop2 = max((cosine_similarity(q_vec, pt["vector"]) for pt in sop2_points), default=0.0)
        score_sop3 = max((cosine_similarity(q_vec, pt["vector"]) for pt in sop3_points), default=0.0)

        self.assertGreater(score_4_2, score_sop2 + 0.20)
        self.assertGreater(score_4_2, score_sop3 + 0.20)


class MockQdrantSeederHandler(BaseHTTPRequestHandler):
    """In-memory mock HTTP server simulating Qdrant REST endpoints."""

    protocol_version = "HTTP/1.1"

    stored_points = {
        "cx_policy_knowledge": [],
        "support_transcripts": []
    }
    api_keys_received = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        auth_key = self.headers.get("api-key")
        if auth_key:
            MockQdrantSeederHandler.api_keys_received.append(auth_key)

        if self.path == "/readyz":
            msg = b"all systems normal\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        if self.path.startswith("/collections/"):
            col_name = self.path.replace("/collections/", "").strip()
            if col_name in MockQdrantSeederHandler.stored_points:
                res = json.dumps({"status": "ok", "result": {"status": "green", "points_count": len(MockQdrantSeederHandler.stored_points[col_name])}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
                return
            else:
                err = json.dumps({"status": "error", "message": "Not found"}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
                return

        self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        auth_key = self.headers.get("api-key")
        if auth_key:
            MockQdrantSeederHandler.api_keys_received.append(auth_key)

        if "/points" in self.path:
            col_name = self.path.split("/collections/")[1].split("/points")[0]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            points = data.get("points", [])

            if col_name in MockQdrantSeederHandler.stored_points:
                MockQdrantSeederHandler.stored_points[col_name].extend(points)

            res = json.dumps({"status": "ok", "result": {"operation_id": 1, "status": "completed"}}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        auth_key = self.headers.get("api-key")
        if auth_key:
            MockQdrantSeederHandler.api_keys_received.append(auth_key)

        if "/points/search" in self.path:
            col_name = self.path.split("/collections/")[1].split("/points/search")[0]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            q_vec = data.get("vector", [])
            limit = data.get("limit", 3)

            points = MockQdrantSeederHandler.stored_points.get(col_name, [])
            scored = []
            for pt in points:
                sim = cosine_similarity(q_vec, pt["vector"])
                scored.append({
                    "id": pt["id"],
                    "score": sim,
                    "payload": pt.get("payload", {})
                })

            scored.sort(key=lambda x: x["score"], reverse=True)
            top = scored[:limit]

            res = json.dumps({"status": "ok", "result": top}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
            return

        self.send_response(404)
        self.end_headers()


class TestSeedEmbeddingsIntegration(unittest.TestCase):
    """Tests CLI execution, mock Qdrant ingestion, payload schemas, and query latency."""

    @classmethod
    def setUpClass(cls):
        MockQdrantSeederHandler.stored_points = {
            "cx_policy_knowledge": [],
            "support_transcripts": []
        }
        MockQdrantSeederHandler.api_keys_received = []

        cls.server = HTTPServer(("127.0.0.1", 0), MockQdrantSeederHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockQdrantSeederHandler.stored_points["cx_policy_knowledge"].clear()
        MockQdrantSeederHandler.stored_points["support_transcripts"].clear()
        MockQdrantSeederHandler.api_keys_received.clear()

    def test_cli_dry_run(self):
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "seed-embeddings.py"), "--dry-run"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"Dry-run CLI failed: {proc.stderr}")
        self.assertIn("DRY-RUN completed successfully", proc.stdout)

    def test_cli_dry_run_with_limit(self):
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "seed-embeddings.py"), "--dry-run", "--limit", "2"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Prepared 2 SOP points", proc.stdout)
        self.assertIn("Prepared 2 transcript points", proc.stdout)

    def test_mock_ingestion_and_search_verification(self):
        host = f"http://127.0.0.1:{self.port}"
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "seed-embeddings.py"),
            "--host", host,
            "--api-key", "ferrous-secret-token-ci"
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"Live mock ingestion failed: {proc.stderr}")
        self.assertIn("Semantic search assertion passed: SOP §4.2 returned with score > 0.82", proc.stdout)

        # Assert points stored in mock server
        sop_points = MockQdrantSeederHandler.stored_points["cx_policy_knowledge"]
        transcript_points = MockQdrantSeederHandler.stored_points["support_transcripts"]
        self.assertGreaterEqual(len(sop_points), 3)
        self.assertGreaterEqual(len(transcript_points), 5)

        # Assert API key was forwarded in headers
        self.assertIn("ferrous-secret-token-ci", MockQdrantSeederHandler.api_keys_received)

        # Verify point payloads
        sample_sop = sop_points[0]
        self.assertEqual(len(sample_sop["vector"]), 384)
        self.assertIn("sop_id", sample_sop["payload"])
        self.assertIn("title", sample_sop["payload"])
        self.assertIn("filename", sample_sop["payload"])
        self.assertIn("content", sample_sop["payload"])

        sample_transcript = transcript_points[0]
        self.assertEqual(len(sample_transcript["vector"]), 384)
        self.assertIn("dialogue_id", sample_transcript["payload"])
        self.assertIn("scenario", sample_transcript["payload"])
        self.assertIn("transcript", sample_transcript["payload"])

    def test_sub_5ms_query_latency_benchmark(self):
        """
        Acceptance requirement (NFR-7, AD-6):
        Semantic search returns SOP §4.2 in < 5 milliseconds.
        Validates client-to-server HTTP query latency across 100 iterations.
        """
        query = "SLA delivery delay courtesy credit rules"
        sop1_path = os.path.join(SOPS_DIR, "SOP-001-Courtesy-Credit-Issuance.md")
        sop2_path = os.path.join(SOPS_DIR, "SOP-002-Carrier-Delay-Escalation.md")
        sop3_path = os.path.join(SOPS_DIR, "SOP-003-Customer-Dispute-Resolution.md")

        all_points = parse_sop_file(sop1_path) + parse_sop_file(sop2_path) + parse_sop_file(sop3_path)
        self.assertGreater(len(all_points), 5)

        # Store points into mock Qdrant server
        MockQdrantSeederHandler.stored_points["cx_policy_knowledge"] = list(all_points)

        client = QdrantRestClient(host=f"http://127.0.0.1:{self.port}")
        q_vec = generate_embedding(query, dim=384, use_heavy_ml=False)
        latencies_ms = []
        best_point = None
        best_score = -1.0

        for _ in range(100):
            t0 = time.perf_counter()
            results = client.search("cx_policy_knowledge", q_vec, limit=3)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            if results and results[0]["score"] > best_score:
                best_score = results[0]["score"]
                best_point = results[0]

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
        max_latency = max(latencies_ms)

        # Assert top match is SOP §4.2 with score > 0.82
        self.assertIsNotNone(best_point)
        title = best_point["payload"].get("title", "")
        section = best_point["payload"].get("section", "")
        self.assertTrue("4.2" in section or "§4.2" in title or "4.2" in title, f"Expected SOP §4.2, got: {title} ({section})")
        self.assertGreater(best_score, 0.82)

        # Assert sub-5ms query latency
        self.assertLess(avg_latency, 5.0, f"Average latency {avg_latency:.3f}ms exceeded 5ms")
        self.assertLess(p95_latency, 5.0, f"p95 latency {p95_latency:.3f}ms exceeded 5ms")


if __name__ == "__main__":
    unittest.main()
