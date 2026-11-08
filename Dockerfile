# syntax=docker/dockerfile:1.4
# Hardened Qdrant Vector Database Container for FerrousCX
# Adheres strictly to Tier 2 DevSecOps standards (AD-13, NFR-13)

FROM qdrant/qdrant:v1.12.0

LABEL org.opencontainers.image.title="ferrous-vectordb" \
      org.opencontainers.image.description="Hardened Qdrant vector database container for FerrousCX" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.vendor="FerrousCX" \
      org.opencontainers.image.licenses="Apache-2.0"

# Install minimal runtime dependencies (ca-certificates, curl) and clean package cache
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Create unprivileged non-root user and group (UID/GID 10001)
RUN groupadd -g 10001 qdrant && \
    useradd -u 10001 -g qdrant -m -d /qdrant -s /sbin/nologin qdrant && \
    mkdir -p /qdrant/storage /qdrant/snapshots /qdrant/config && \
    chown -R 10001:10001 /qdrant

WORKDIR /qdrant

# Copy custom configuration files
COPY --chown=10001:10001 config/config.yaml /qdrant/config/config.yaml
COPY --chown=10001:10001 config/config.yaml /qdrant/config/production.yaml

# Switch to rootless runtime user (UID 10001)
USER 10001:10001

# Volumes for persistent vector storage and snapshots
VOLUME ["/qdrant/storage", "/qdrant/snapshots"]

# Expose HTTP REST (6333) and gRPC (6334) ports
EXPOSE 6333 6334

# Container health probe validating readiness endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD ["curl", "-f", "http://localhost:6333/readyz"]

ENV QDRANT__STORAGE__STORAGE_PATH=/qdrant/storage \
    QDRANT__STORAGE__SNAPSHOTS_PATH=/qdrant/snapshots

ENTRYPOINT ["./qdrant"]
CMD ["--config-path", "/qdrant/config/config.yaml"]
