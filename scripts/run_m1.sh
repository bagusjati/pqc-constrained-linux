#!/usr/bin/env bash
# Full M1 campaign: main (10 repetitions) + ablation (10 repetitions). About 10 to 14 hours.
# Can be rerun at any time: runs that already have a result are skipped.
set -euo pipefail
source "$(dirname "$0")/load-config.sh"
S="$SCHEDULE_DIR/schedule_m1.json"
[ -f "$S" ] || python3 host/make_schedule.py --host m1 --out "$S"
mkdir -p "$RESULTS_DIR/m1"
caffeinate -i python3 host/run_campaign.py --schedule "$S" --image "$IMAGE" --results "$RESULTS_DIR/m1" 2>&1 | tee -a "$RESULTS_DIR/m1/console.log"
