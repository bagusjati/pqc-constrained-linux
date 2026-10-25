#!/usr/bin/env bash
# Pilot on the M1: one repetition, three tiers, fifteen algorithms (about 40 minutes).
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
python3 host/make_schedule.py --host m1 --pilot --out "$SCHEDULE_DIR/schedule_m1_pilot.json"
caffeinate -i python3 host/run_campaign.py --schedule "$SCHEDULE_DIR/schedule_m1_pilot.json" --image "$IMAGE" --results "$RESULTS_DIR/m1_pilot"
python3 host/collect.py --results "$RESULTS_DIR/m1_pilot"
(cd "$RESULTS_DIR/.." && zip -qr "$ARCHIVE_DIR/pilot_m1.zip" "$(basename "$RESULTS_DIR")/m1_pilot") && echo "written $ARCHIVE_DIR/pilot_m1.zip"
