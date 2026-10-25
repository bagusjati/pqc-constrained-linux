#!/usr/bin/env bash
# After a campaign:  bash scripts/finish.sh m1   or   sudo bash scripts/finish.sh pi
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
H=${1:?host: m1 or pi}
python3 host/collect.py --results "$RESULTS_DIR/$H"
bash host/env_report.sh "$IMAGE" > "$RESULTS_DIR/$H/env_report.txt"
cp NOTES.md "$RESULTS_DIR/$H/NOTES.md"
(cd "$RESULTS_DIR/.." && zip -qr "$ARCHIVE_DIR/results_$H.zip" "$(basename "$RESULTS_DIR")/$H") \
  && echo "written $ARCHIVE_DIR/results_$H.zip ($(du -h "$ARCHIVE_DIR/results_$H.zip" | cut -f1))"
