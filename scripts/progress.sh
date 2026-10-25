#!/usr/bin/env bash
# Monitoring: bash scripts/progress.sh pi   (or m1)
source "$(dirname "$0")/load-config.sh"
H=${1:-pi}; D="$RESULTS_DIR/$H"
total=$(python3 -c "import json,sys;s=json.load(open(sys.argv[1]));print(sum(len(b['algorithms'])+1 for b in s['blocks']))" "$D/schedule.json" 2>/dev/null || echo "?")
done_=$(($(wc -l < "$D/run_log.csv" 2>/dev/null || echo 1) - 1))
echo "completed $done_ of $total containers"
echo "last status:"; tail -n 3 "$D/run_log.csv" | cut -d, -f1-6,10-13,19
echo "status not ok:"; awk -F, 'NR>1 && $NF!="ok"' "$D/run_log.csv" | wc -l
[ "$H" = pi ] && { vcgencmd measure_temp; vcgencmd get_throttled; }
docker ps --format '{{.Names}}'
