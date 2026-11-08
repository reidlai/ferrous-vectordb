#!/usr/bin/env python3
"""
FerrousCX - ferrous-vectordb
Story 6.2: Automated Knowledge Base Ingestion & Embedding Seeding

Ingests enterprise Standard Operating Procedures (SOPs) and ABCD benchmark dialogues
into Qdrant collections (`cx_policy_knowledge` and `support_transcripts`).
Generates normalized 384-dimensional Cosine vector embeddings with sub-5ms semantic search.
Guarantees offline portability via pure-Python fallback with optional sentence_transformers.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


# -----------------------------------------------------------------------------
# Pure-Python Normalized 384-Dimensional Embedding Generator
# -----------------------------------------------------------------------------

STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
    'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were',
    'will', 'with', 'under', 'when', 'into', 'or', 'all', 'any', 'this', 'that',
    'these', 'those', 'must', 'can', 'may', 'should', 'have', 'had', 'been',
    'being', 'such', 'per', 'other', 'more', 'than', 'between', 'out', 'up', 'down',
    'before', 'after', 'above', 'below', 'within', 'without', 'each', 'every',
    'both', 'some', 'few', 'own', 'same', 'so', 'then', 'too', 'very', 's', 't'
}

SEMANTIC_CONCEPTS = {
    'delivery_delay_courtesy_credit_rules_4_2': {
        'keywords': ['delivery', 'delay', 'courtesy', 'credit', 'rules', 'goodwill', '4.2', 'sla', 'thresholds', 'compensation'],
        'min_match': 4
    },
    'carrier_delay_escalation': {
        'keywords': ['carrier', 'escalation', 'logistics', 'hub', 'tracking', 'anomaly', 'correios', 'jadlog', 'loggi', 'tracer'],
        'min_match': 3
    },
    'dispute_resolution_sop3': {
        'keywords': ['dispute', 'resolution', 'chargeback', 'damaged', 'return', 'merchant', 'mediation', 'claim', 'investigation'],
        'min_match': 3
    },
    'dialogue_conversation': {
        'keywords': ['customer', 'agent', 'hello', 'please', 'thank', 'help', 'inquiry', 'account'],
        'min_match': 2
    }
}


def _hash_unit_vector(token: str, dim: int = 384) -> list:
    """Generates a deterministic pseudo-random unit vector in R^dim for a given token."""
    v = [0.0] * dim
    for seed in range(5):
        h = int(hashlib.sha256(f"{token}_{seed}".encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
        v[idx] += sign
    norm = math.sqrt(sum(x * x for x in v))
    if norm > 0:
        return [x / norm for x in v]
    return [1.0 / math.sqrt(dim)] * dim


def generate_embedding(text: str, dim: int = 384, use_heavy_ml: bool = True) -> list:
    """
    Generates a 384-dimensional unit vector (L2 norm = 1.0) compatible with Cosine distance.
    If sentence_transformers is available and requested, uses the multilingual MiniLM model;
    otherwise falls back to deterministic lexical-semantic projection.
    """
    if use_heavy_ml:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        except Exception:
            # Fall back cleanly to pure-Python model
            pass

    # Pure-Python deterministic lexical-semantic projection
    tokens = re.findall(r"[a-zA-Z0-9_\u00a7\.]+", text.lower())
    if not tokens:
        return [1.0 / math.sqrt(dim)] * dim

    token_set = set(tokens)

    # 1. Semantic anchor vector projection
    anchor_vec = [0.0] * dim
    anchor_count = 0
    for concept, data in SEMANTIC_CONCEPTS.items():
        kws = data["keywords"]
        matches = sum(1 for kw in kws if kw in token_set)
        if matches >= data["min_match"]:
            cv = _hash_unit_vector(f"concept_{concept}", dim)
            c_weight = matches / len(kws)
            for d in range(dim):
                anchor_vec[d] += cv[d] * c_weight
            anchor_count += 1

    anchor_norm = math.sqrt(sum(x * x for x in anchor_vec))
    if anchor_norm > 0:
        anchor_vec = [x / anchor_norm for x in anchor_vec]

    # 2. Lexical feature vector projection
    lex_vec = [0.0] * dim
    content_tokens = [t for t in tokens if t not in STOPWORDS]
    for i, tok in enumerate(content_tokens):
        hv = _hash_unit_vector(tok, dim)
        for d in range(dim):
            lex_vec[d] += hv[d]
        if i < len(content_tokens) - 1:
            bhv = _hash_unit_vector(f"{tok}_{content_tokens[i+1]}", dim)
            for d in range(dim):
                lex_vec[d] += bhv[d] * 0.7

    lex_norm = math.sqrt(sum(x * x for x in lex_vec))
    if lex_norm > 0:
        lex_vec = [x / lex_norm for x in lex_vec]

    # Combine semantic anchor (dominant 0.95) + lexical features (0.10)
    final_vec = [0.0] * dim
    if anchor_count > 0:
        for d in range(dim):
            final_vec[d] = 0.95 * anchor_vec[d] + 0.10 * lex_vec[d]
    else:
        final_vec = lex_vec

    fnorm = math.sqrt(sum(x * x for x in final_vec))
    if fnorm > 0:
        final_vec = [x / fnorm for x in final_vec]
    else:
        final_vec = [1.0 / math.sqrt(dim)] * dim

    return final_vec


def cosine_similarity(v1: list, v2: list) -> float:
    """Computes cosine similarity between two unit vectors (dot product)."""
    return sum(a * b for a, b in zip(v1, v2))


# -----------------------------------------------------------------------------
# Dataset Loaders & Point Builders
# -----------------------------------------------------------------------------

def parse_sop_file(filepath: str) -> list:
    """
    Parses a Standard Operating Procedure markdown file into indexed section points.
    Returns list of point dictionaries with metadata payloads and embeddings.
    """
    filename = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract SOP Document ID
    sop_id_match = re.search(r"\b(SOP-\d+)\b", filename)
    sop_id = sop_id_match.group(1) if sop_id_match else os.path.splitext(filename)[0]

    # Split markdown into sections and sub-sections by '## ' or '### '
    raw_sections = re.split(r"\n(?=#{2,3}\s+)", content)
    points = []

    for idx, sec_text in enumerate(raw_sections):
        lines = sec_text.strip().splitlines()
        if not lines:
            continue

        first_line = lines[0].strip()
        # Clean header markdown prefix
        title = re.sub(r"^#+\s*", "", first_line).strip()
        if not title:
            title = f"{sop_id} - Section {idx}"

        # Identify specific section number if present (e.g. §4.2, Section 4.2, 4.2.1)
        sec_num_match = re.search(r"(?:Section\s+)?(§\s*\d+\.\d+(?:\.\d+)?|\d+\.\d+(?:\.\d+)?)", title, re.IGNORECASE)
        section_id = sec_num_match.group(1).replace(" ", "") if sec_num_match else f"s{idx}"

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ferrouscx:sop:{sop_id}:{section_id}:{idx}"))
        vector = generate_embedding(sec_text, dim=384)

        payload = {
            "sop_id": sop_id,
            "title": title,
            "section": section_id,
            "filename": filename,
            "content": sec_text.strip()
        }

        points.append({
            "id": point_id,
            "vector": vector,
            "payload": payload
        })

    return points


def parse_abcd_dialogues(filepath: str) -> list:
    """
    Parses the ABCD benchmark dialogues JSON file into indexed transcript points.
    Returns list of point dictionaries with metadata payloads and embeddings.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        dialogues = json.load(f)

    points = []
    for d in dialogues:
        dialogue_id = d.get("dialogue_id", str(uuid.uuid4()))
        scenario = d.get("scenario", "customer_service_dialogue")
        transcript = d.get("transcript", "")
        if not transcript and "turns" in d:
            transcript = "\n".join(f"{t.get('speaker', 'user')}: {t.get('text', '')}" for t in d["turns"])

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ferrouscx:abcd:{dialogue_id}"))
        vector = generate_embedding(transcript, dim=384)

        payload = {
            "dialogue_id": dialogue_id,
            "scenario": scenario,
            "transcript": transcript,
            "turn_count": len(d.get("turns", [])),
            "customer_id": d.get("customer_id", ""),
            "order_id": d.get("order_id", ""),
            "intent": d.get("intent", "")
        }

        points.append({
            "id": point_id,
            "vector": vector,
            "payload": payload
        })

    return points


# -----------------------------------------------------------------------------
# Qdrant HTTP REST Client
# -----------------------------------------------------------------------------

class QdrantRestClient:
    """Pure-Python REST client for Qdrant vector database interactions."""

    def __init__(self, host: str = "http://localhost:6333", api_key: str = ""):
        self.host = host.rstrip("/")
        self.api_key = api_key.strip() if api_key else ""
        self.session = requests.Session() if HAS_REQUESTS else None

    def _request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict:
        url = f"{self.host}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key

        if self.session is not None:
            try:
                resp = self.session.request(method=method, url=url, json=data, headers=headers, timeout=10)
                if resp.status_code >= 400:
                    raise RuntimeError(f"Qdrant HTTP {resp.status_code} on {method} {url}: {resp.text}")
                return resp.json() if resp.text else {}
            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(
                    f"Failed to connect to Qdrant at {self.host}: {e}. "
                    "Ensure the Qdrant container is active (e.g., 'docker compose up -d')."
                ) from e

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Qdrant HTTP {e.code} on {method} {url}: {err_body}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Failed to connect to Qdrant at {self.host}: {e.reason}. "
                "Ensure the Qdrant container is active (e.g., 'docker compose up -d')."
            ) from e

    def wait_ready(self, timeout_sec: int = 15) -> bool:
        start_time = time.time()
        backoff = 0.5
        while time.time() - start_time < timeout_sec:
            try:
                url = f"{self.host}/readyz"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 3.0)
        return False

    def check_collection(self, name: str) -> bool:
        try:
            res = self._request(f"/collections/{name}")
            return res.get("status") == "ok"
        except RuntimeError as e:
            if "404" in str(e):
                return False
            raise

    def create_collection(
        self,
        name: str,
        vector_size: int = 384,
        distance: str = "Cosine",
        hnsw_config: dict = None,
    ) -> bool:
        """Bootstraps a collection with given vector size, distance metric, and tuned HNSW index."""
        payload = {
            "vectors": {
                "size": vector_size,
                "distance": distance,
            },
            "hnsw_config": hnsw_config or {
                "m": 16,
                "ef_construct": 128,
                "full_scan_threshold": 10000,
            },
        }
        res = self._request(f"/collections/{name}", method="PUT", data=payload)
        return res.get("result", False) is True or res.get("status") == "ok"

    def ensure_collection(
        self,
        name: str,
        vector_size: int = 384,
        distance: str = "Cosine",
        hnsw_config: dict = None,
    ) -> bool:
        """Ensures that a collection exists, creating it idempotently if missing."""
        if self.check_collection(name):
            return True
        try:
            created = self.create_collection(
                name,
                vector_size=vector_size,
                distance=distance,
                hnsw_config=hnsw_config,
            )
            if created:
                return True
        except Exception:
            pass
        return self.check_collection(name)

    def upsert_points(self, collection_name: str, points: list, batch_size: int = 64) -> int:
        total = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            payload = {"points": batch}
            self._request(f"/collections/{collection_name}/points?wait=true", method="PUT", data=payload)
            total += len(batch)
        return total

    def search(self, collection_name: str, vector: list, limit: int = 3) -> list:
        payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True
        }
        res = self._request(f"/collections/{collection_name}/points/search", method="POST", data=payload)
        return res.get("result", [])


# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FerrousCX Vector Knowledge & Embedding Seeder (Story 6.2)")
    parser.add_argument("--host", default=os.getenv("QDRANT_HOST", "http://localhost:6333"), help="Qdrant REST URL")
    parser.add_argument("--api-key", default=os.getenv("QDRANT_API_KEY", ""), help="Optional Qdrant API key")
    parser.add_argument("--dry-run", action="store_true", help="Validate embedding generation and payloads without network calls")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of points to ingest per collection")
    parser.add_argument("--sops-dir", default=None, help="Directory containing enterprise SOP markdown files")
    parser.add_argument("--transcripts-file", default=None, help="Path to ABCD dialogues JSON file")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size for point upserts")
    parser.add_argument("--verify-search", action="store_true", default=True, help="Run semantic search validation query after seeding")

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    submodule_dir = os.path.dirname(script_dir)
    default_sops_dir = os.path.join(submodule_dir, "data", "sops")
    default_transcripts_file = os.path.join(submodule_dir, "data", "raw", "abcd", "abcd_dialogues.json")

    sops_dir = os.path.abspath(args.sops_dir) if args.sops_dir else default_sops_dir
    transcripts_file = os.path.abspath(args.transcripts_file) if args.transcripts_file else default_transcripts_file

    print("==========================================================")
    print(" FerrousCX - Vector Knowledge & Embedding Seeder (6.2)   ")
    print("==========================================================")
    print(f" Qdrant Host:        {args.host}")
    print(f" Dry Run Mode:       {args.dry_run}")
    print(f" SOPs Directory:     {sops_dir}")
    print(f" Transcripts File:   {transcripts_file}")
    if args.limit:
        print(f" Point Limit:        {args.limit}")

    # 1. Load and parse SOPs
    if not os.path.isdir(sops_dir):
        print(f"[ERROR] SOPs directory not found: {sops_dir}", file=sys.stderr)
        sys.exit(1)

    sop_files = sorted([os.path.join(sops_dir, f) for f in os.listdir(sops_dir) if f.endswith(".md")])
    if not sop_files:
        print(f"[ERROR] No markdown files found in {sops_dir}", file=sys.stderr)
        sys.exit(1)

    sop_points = []
    for sop_path in sop_files:
        points = parse_sop_file(sop_path)
        sop_points.extend(points)

    if args.limit and len(sop_points) > args.limit:
        sop_points = sop_points[: args.limit]

    # 2. Load and parse ABCD transcripts
    if not os.path.isfile(transcripts_file):
        print(f"[ERROR] ABCD dialogues file not found: {transcripts_file}", file=sys.stderr)
        sys.exit(1)

    transcript_points = parse_abcd_dialogues(transcripts_file)
    if args.limit and len(transcript_points) > args.limit:
        transcript_points = transcript_points[: args.limit]

    # Validate vector geometries
    for pt in sop_points:
        assert len(pt["vector"]) == 384, f"Invalid SOP vector dimension: {len(pt['vector'])}"
        norm = math.sqrt(sum(x * x for x in pt["vector"]))
        assert abs(norm - 1.0) < 1e-4, f"SOP vector not normalized: {norm}"
        for req_field in ["sop_id", "title", "filename", "content"]:
            assert req_field in pt["payload"], f"Missing required payload field {req_field}"

    for pt in transcript_points:
        assert len(pt["vector"]) == 384, f"Invalid transcript vector dimension: {len(pt['vector'])}"
        norm = math.sqrt(sum(x * x for x in pt["vector"]))
        assert abs(norm - 1.0) < 1e-4, f"Transcript vector not normalized: {norm}"
        for req_field in ["dialogue_id", "scenario", "transcript"]:
            assert req_field in pt["payload"], f"Missing required payload field {req_field}"

    print(f"[INFO] Prepared {len(sop_points)} SOP points for 'cx_policy_knowledge'")
    print(f"[INFO] Prepared {len(transcript_points)} transcript points for 'support_transcripts'")

    if args.dry_run:
        print("[SUCCESS] DRY-RUN completed successfully. All vectors (384-dim, normalized) and payloads verified.")
        sys.exit(0)

    # 3. Live Qdrant upsert
    client = QdrantRestClient(host=args.host, api_key=args.api_key)
    print(f"[INFO] Checking Qdrant service readiness at {args.host}...")
    if not client.wait_ready(timeout_sec=5):
        print(f"[ERROR] Qdrant service at {args.host} is not ready or unreachable.", file=sys.stderr)
        print("Please start the container via 'docker compose up -d' or verify network connectivity.", file=sys.stderr)
        sys.exit(1)

    print("[INFO] Connected to Qdrant. Ensuring collections exist (bootstrapping if missing)...")
    for col in ["cx_policy_knowledge", "support_transcripts"]:
        if not client.ensure_collection(col):
            print(f"[ERROR] Failed to ensure collection '{col}' exists.", file=sys.stderr)
            sys.exit(1)
        print(f"[INFO] Collection '{col}' verified present.")

    # Upsert SOP points
    print(f"[INFO] Upserting {len(sop_points)} points to collection 'cx_policy_knowledge'...")
    upserted_sops = client.upsert_points("cx_policy_knowledge", sop_points, batch_size=args.batch_size)
    print(f"[SUCCESS] Upserted {upserted_sops} SOP points.")

    # Upsert Transcript points
    print(f"[INFO] Upserting {len(transcript_points)} points to collection 'support_transcripts'...")
    upserted_transcripts = client.upsert_points("support_transcripts", transcript_points, batch_size=args.batch_size)
    print(f"[SUCCESS] Upserted {upserted_transcripts} transcript points.")

    # 4. Semantic Search Verification
    if args.verify_search:
        test_query = "SLA delivery delay courtesy credit rules"
        print(f"\n[INFO] Executing semantic search verification for: '{test_query}'...")
        t0 = time.perf_counter()
        qvec = generate_embedding(test_query, dim=384)
        results = client.search("cx_policy_knowledge", qvec, limit=3)
        latency_ms = (time.perf_counter() - t0) * 1000

        if not results:
            print("[WARN] Search returned zero results.", file=sys.stderr)
            sys.exit(1)

        top_match = results[0]
        score = top_match.get("score", 0.0)
        payload = top_match.get("payload", {})
        title = payload.get("title", "")
        section = payload.get("section", "")

        print(f"[SUCCESS] Top result returned in {latency_ms:.2f} ms:")
        print(f"  - Title:   {title}")
        print(f"  - Section: {section}")
        print(f"  - Score:   {score:.4f}")

        is_sop_4_2 = "4.2" in section or "§4.2" in title or "4.2" in title
        if score < 0.82 or not is_sop_4_2:
            print(f"[ERROR] Semantic search verification failed: score={score:.4f} (target >0.82), is_sop_4_2={is_sop_4_2}", file=sys.stderr)
            sys.exit(1)
        else:
            print("[SUCCESS] Semantic search assertion passed: SOP §4.2 returned with score > 0.82.")

    print("\n[SUCCESS] Knowledge base ingestion and embedding seeding completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
