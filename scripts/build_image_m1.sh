#!/usr/bin/env bash
# Run on the Apple M1 host. Builds the image ONCE, saves it as an archive to be
# copied to the Raspberry Pi, and prints the image Id, which must be identical on both hosts.
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
docker build --platform linux/arm64 -t "$IMAGE" -f docker/Dockerfile .
docker save "$IMAGE" | gzip > "$IMAGE_TAR"
echo "IMAGE ID (record it, it must be identical on the Pi):"
docker image inspect --format '{{.Id}}' "$IMAGE" | tee "$RESULTS_DIR/image_id_m1.txt"
mkdir -p "$RESULTS_DIR/m1"
bash host/env_report.sh "$IMAGE" > "$RESULTS_DIR/m1/env_report.txt"
echo "env report: $RESULTS_DIR/m1/env_report.txt"
grep -A4 "cgroup files visible" "$RESULTS_DIR/m1/env_report.txt" || true
