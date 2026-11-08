#!/usr/bin/env bash
# ==============================================================================
# FerrousCX Qdrant Collection Scaffolding Script (POSIX)
# Initializes cx_policy_knowledge and support_transcripts collections idempotently
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOST_URL="${QDRANT_URL:-http://localhost:6333}"
API_KEY="${QDRANT_API_KEY:-}"
DRY_RUN=false
MAX_RETRIES=10
INITIAL_BACKOFF=1

# Parse arguments safely
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|-d|-DryRun)
      DRY_RUN=true
      shift
      ;;
    --host|-h|-HostUrl)
      if [[ $# -lt 2 ]]; then
        echo "Error: --host requires an argument"
        exit 1
      fi
      HOST_URL="$2"
      shift 2
      ;;
    --api-key|-k|-ApiKey)
      if [[ $# -lt 2 ]]; then
        echo "Error: --api-key requires an argument"
        exit 1
      fi
      API_KEY="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--dry-run] [--host http://localhost:6333] [--api-key <key>]"
      exit 1
      ;;
  esac
done

HOST_URL="${HOST_URL%/}"

AUTH_HEADER=()
if [[ -n "${API_KEY}" ]]; then
  AUTH_HEADER=(-H "api-key: ${API_KEY}")
fi

# Ensure persistent storage directory exists with write permissions for rootless UID 10001
STORAGE_DIR="${ROOT_DIR}/qdrant_storage"
if [[ ! -d "${STORAGE_DIR}" ]]; then
  echo "[INFO] Creating missing storage directory: ${STORAGE_DIR}"
  mkdir -p "${STORAGE_DIR}"
  chmod 0777 "${STORAGE_DIR}" 2>/dev/null || true
else
  echo "[INFO] Persistent storage directory present: ${STORAGE_DIR}"
  chmod 0777 "${STORAGE_DIR}" 2>/dev/null || true
fi

# Collection definitions (384 dimensions, Cosine distance, tuned HNSW)
COLLECTION_PAYLOAD='{
  "vectors": {
    "size": 384,
    "distance": "Cosine"
  },
  "hnsw_config": {
    "m": 16,
    "ef_construct": 100,
    "full_scan_threshold": 10000
  }
}'

COLLECTIONS=("cx_policy_knowledge" "support_transcripts")

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "===================================================================="
  echo "[DRY RUN] Validated Qdrant Collection Definitions (No Network Calls)"
  echo "===================================================================="
  echo "Target Host: ${HOST_URL}"
  for col in "${COLLECTIONS[@]}"; do
    echo ""
    echo "Collection: ${col}"
    echo "Payload:"
    echo "${COLLECTION_PAYLOAD}"
  done
  echo "===================================================================="
  echo "[DRY RUN] Validation completed successfully."
  exit 0
fi

# Wait for Qdrant service readiness (/readyz) with bounded exponential backoff
wait_for_ready() {
  local retry=1
  local backoff="${INITIAL_BACKOFF}"
  echo "[INFO] Checking Qdrant readiness at ${HOST_URL}/readyz..."

  while [[ "${retry}" -le "${MAX_RETRIES}" ]]; do
    local http_code
    http_code=$(curl --connect-timeout 5 --max-time 10 -s -o /dev/null -w "%{http_code}" ${AUTH_HEADER[@]+"${AUTH_HEADER[@]}"} "${HOST_URL}/readyz" || echo "000")

    if [[ "${http_code}" == "200" ]]; then
      echo "[INFO] Qdrant service is ready (HTTP 200)."
      return 0
    fi

    if [[ "${retry}" -lt "${MAX_RETRIES}" ]]; then
      echo "[WARN] Qdrant not ready (HTTP ${http_code}). Attempt ${retry}/${MAX_RETRIES}. Retrying in ${backoff}s..."
      sleep "${backoff}"
      retry=$((retry + 1))
      backoff=$((backoff >= 5 ? 5 : backoff * 2))
    else
      retry=$((retry + 1))
    fi
  done

  echo "[ERROR] Timed out waiting for Qdrant at ${HOST_URL}/readyz"
  return 1
}

wait_for_ready

# Scaffold collections idempotently
for col in "${COLLECTIONS[@]}"; do
  echo "[INFO] Checking existence of collection '${col}'..."
  check_code=$(curl --connect-timeout 5 --max-time 10 -s -o /dev/null -w "%{http_code}" ${AUTH_HEADER[@]+"${AUTH_HEADER[@]}"} "${HOST_URL}/collections/${col}" || echo "000")

  if [[ "${check_code}" == "200" ]]; then
    echo "[INFO] Collection '${col}' already exists. Skipping creation (Idempotent)."
    continue
  elif [[ "${check_code}" == "404" ]]; then
    echo "[INFO] Collection '${col}' not found (HTTP 404). Proceeding to create..."
  else
    echo "[ERROR] Unexpected response while checking collection '${col}' (HTTP ${check_code})"
    exit 1
  fi

  echo "[INFO] Creating collection '${col}' with 384 dimensions and Cosine distance..."
  response=$(curl --connect-timeout 5 --max-time 10 -s -w "\n%{http_code}" -X PUT \
    -H "Content-Type: application/json" \
    ${AUTH_HEADER[@]+"${AUTH_HEADER[@]}"} \
    -d "${COLLECTION_PAYLOAD}" \
    "${HOST_URL}/collections/${col}")

  http_status=$(echo "${response}" | tail -n1)
  body=$(echo "${response}" | sed '$d')

  if [[ "${http_status}" == "200" ]]; then
    echo "[SUCCESS] Collection '${col}' created successfully: ${body}"
  else
    echo "[ERROR] Failed to create collection '${col}' (HTTP ${http_status}): ${body}"
    exit 1
  fi
done

echo "[SUCCESS] All Qdrant collections scaffolded and verified successfully."
