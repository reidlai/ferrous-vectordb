#!/usr/bin/env bash
# ==============================================================================
# FerrousCX - ferrous-vectordb
# Story 6.2: Automated Knowledge Base Ingestion & Embedding Seeding
# Dataset download and provisioning script with offline fallback.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../data"
OFFLINE=0
FORCE=0
REMOTE_URL=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --output-dir <path>   Target directory for datasets (default: ferrous-vectordb/data)
  --offline             Bypass remote network requests and verify local packaged artifacts
  --force               Force re-verification or re-download of datasets
  --remote-url <url>    Optional remote dataset URL for ABCD dialogues
  -h, --help            Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --offline)
            OFFLINE=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --remote-url)
            REMOTE_URL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

SOPS_DIR="${OUTPUT_DIR}/sops"
ABCD_DIR="${OUTPUT_DIR}/raw/abcd"
ABCD_JSON="${ABCD_DIR}/abcd_dialogues.json"

echo "=========================================================="
echo " FerrousCX - Dataset Provisioning & Download (Story 6.2)   "
echo "=========================================================="
echo " Target Data Directory: ${OUTPUT_DIR}"
echo " SOPs Directory:        ${SOPS_DIR}"
echo " ABCD Dialogues:        ${ABCD_JSON}"
echo " Offline Mode:          ${OFFLINE}"

mkdir -p "${SOPS_DIR}"
mkdir -p "${ABCD_DIR}"

REQUIRED_SOPS=(
    "SOP-001-Courtesy-Credit-Issuance.md"
    "SOP-002-Carrier-Delay-Escalation.md"
    "SOP-003-Customer-Dispute-Resolution.md"
)

missing_sops=0
for sop in "${REQUIRED_SOPS[@]}"; do
    if [[ ! -f "${SOPS_DIR}/${sop}" ]]; then
        echo "[WARN] Missing SOP: ${SOPS_DIR}/${sop}" >&2
        missing_sops=$((missing_sops + 1))
    fi
done

abcd_exists=0
if [[ -f "${ABCD_JSON}" && -s "${ABCD_JSON}" ]]; then
    abcd_exists=1
fi

if [[ ${OFFLINE} -eq 1 || (${FORCE} -eq 0 && ${missing_sops} -eq 0 && ${abcd_exists} -eq 1) ]]; then
    echo "[INFO] Evaluating local packaged datasets..."
    if [[ ${missing_sops} -gt 0 ]]; then
        echo "[ERROR] Missing required SOP files in offline mode" >&2
        exit 1
    fi
    if [[ ${abcd_exists} -eq 0 ]]; then
        echo "[ERROR] Missing or empty ABCD dialogue file in offline mode: ${ABCD_JSON}" >&2
        exit 1
    fi
    echo "[SUCCESS] All enterprise SOPs and ABCD benchmark datasets are present and verified."
    exit 0
fi

# Remote download attempt with fallback
if [[ -n "${REMOTE_URL}" ]]; then
    echo "[INFO] Attempting download from remote: ${REMOTE_URL}"
    if curl -fSsL --connect-timeout 5 --max-time 15 "${REMOTE_URL}" -o "${ABCD_JSON}"; then
        echo "[SUCCESS] Remote ABCD dataset downloaded successfully."
    else
        echo "[WARN] Remote download failed. Falling back to local packaged artifacts." >&2
        if [[ ${abcd_exists} -eq 0 ]]; then
            echo "[ERROR] Local fallback dataset missing at ${ABCD_JSON}" >&2
            exit 1
        fi
    fi
else
    echo "[INFO] No remote URL specified. Using authoritative packaged repository artifacts."
fi

# Final check
for sop in "${REQUIRED_SOPS[@]}"; do
    if [[ ! -f "${SOPS_DIR}/${sop}" ]]; then
        echo "[ERROR] Verification failed: missing ${sop}" >&2
        exit 1
    fi
done

if [[ ! -f "${ABCD_JSON}" || ! -s "${ABCD_JSON}" ]]; then
    echo "[ERROR] Verification failed: missing or empty ${ABCD_JSON}" >&2
    exit 1
fi

echo "[SUCCESS] Dataset provisioning completed successfully."
exit 0
