#!/usr/bin/env bash
# Full Raspberry Pi 4 campaign: main 10 reps + ablation 10 reps + lowclock 5 reps (3 to 4 days).
# Run inside tmux:  tmux new -s campaign  then  bash scripts/run_pi.sh
# Can be rerun at any time: runs that already have a result are skipped.
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
bash scripts/check_pi.sh | tail -1 | grep -q "ALL OK" || { echo "check_pi failed"; exit 1; }
S="$SCHEDULE_DIR/schedule_pi.json"
[ -f "$S" ] || python3 host/make_schedule.py --host pi --out "$S"
sudo mkdir -p "$RESULTS_DIR/pi"
sudo python3 host/run_campaign.py --schedule "$S" --image "$IMAGE" --results "$RESULTS_DIR/pi" --pi 2>&1 | sudo tee -a "$RESULTS_DIR/pi/console.log"
