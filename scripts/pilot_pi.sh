#!/usr/bin/env bash
# Pilot on the Pi: run inside tmux. It may be stopped (Ctrl-C) after block 0 is complete.
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
bash scripts/check_pi.sh | tail -1 | grep -q "ALL OK" || { echo "check_pi failed"; exit 1; }
python3 host/make_schedule.py --host pi --pilot --out "$SCHEDULE_DIR/schedule_pi_pilot.json"
sudo python3 host/run_campaign.py --schedule "$SCHEDULE_DIR/schedule_pi_pilot.json" --image "$IMAGE" --results "$RESULTS_DIR/pi_pilot" --pi || true
sudo python3 host/collect.py --results "$RESULTS_DIR/pi_pilot"
(cd "$RESULTS_DIR/.." && sudo zip -qr "$ARCHIVE_DIR/pilot_pi.zip" "$(basename "$RESULTS_DIR")/pi_pilot") && echo "written $ARCHIVE_DIR/pilot_pi.zip"
