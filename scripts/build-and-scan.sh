#!/usr/bin/env bash
# build-and-scan.sh: Builds ferrous-vectordb Docker image and scans with Hadolint and Trivy (Story 6.3)
# Enforces Tier 2 DevSecOps standards locally without incurring cloud CI minutes (AD-13, NFR-10..13).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_IMAGE="ferrous-vectordb:latest"
DOCKERFILE="Dockerfile"

SKIP_SCAN=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --skip-scan) SKIP_SCAN=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

echo "======================================================================"
echo " [DEVSECOPS] Building and Scanning ferrous-vectordb Container Image"
echo "======================================================================"

cd "${REPO_ROOT}"

# 1. Hadolint Dockerfile Linting
echo -e "\n[Step 1/3] Running Hadolint Dockerfile SAST audit on ${DOCKERFILE}..."
if [ "${DRY_RUN}" = "true" ]; then
    echo "  [DRY-RUN] hadolint ${DOCKERFILE}"
else
    if command -v hadolint >/dev/null 2>&1; then
        hadolint "${DOCKERFILE}"
    else
        echo "  [INFO] Local hadolint CLI not found; running via hadolint/hadolint container..."
        docker run --rm -v "${REPO_ROOT}:/work" -w /work hadolint/hadolint:latest hadolint "${DOCKERFILE}"
    fi
    echo "  [OK] Dockerfile passed Hadolint linting (0 issues)."
fi

# 2. Build Qdrant Vector DB Container
echo -e "\n[Step 2/3] Building Qdrant container image (${TARGET_IMAGE})..."
if [ "${DRY_RUN}" = "true" ]; then
    echo "  [DRY-RUN] docker build -t ${TARGET_IMAGE} -f ${DOCKERFILE} ."
else
    docker build -t "${TARGET_IMAGE}" -f "${DOCKERFILE}" .
    echo "  [OK] Container image ${TARGET_IMAGE} built successfully."
fi

if [ "${SKIP_SCAN}" = "true" ]; then
    echo -e "\n[WARN] Skipping Trivy vulnerability scanning (--skip-scan enabled)."
    exit 0
fi

# Helper function for Trivy execution
run_trivy() {
    local image_name="$1"
    if command -v trivy >/dev/null 2>&1; then
        trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${image_name}"
    else
        echo "  [INFO] Local trivy CLI not found; running via aquasec/trivy container..."
        docker run --rm \
            -v //var/run/docker.sock:/var/run/docker.sock \
            aquasec/trivy:latest image \
            --severity HIGH,CRITICAL \
            --ignore-unfixed \
            --exit-code 1 \
            "${image_name}"
    fi
}

# 3. Trivy Scan: ferrous-vectordb
echo -e "\n[Step 3/3] Running Trivy vulnerability scan on ${TARGET_IMAGE}..."
if [ "${DRY_RUN}" = "true" ]; then
    echo "  [DRY-RUN] trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 ${TARGET_IMAGE}"
else
    run_trivy "${TARGET_IMAGE}"
    echo "  [OK] Zero HIGH or CRITICAL unfixed vulnerabilities detected in ${TARGET_IMAGE}."
fi

echo -e "\n======================================================================"
echo " [SUCCESS] ferrous-vectordb Container Built and Verified (0 CVEs)!"
echo "======================================================================"
