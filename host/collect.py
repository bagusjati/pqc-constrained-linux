#!/usr/bin/env python3
"""
collect.py - merges all result JSONs of one host into flat files and prints a
sanity report. Run it after a pilot and after every phase.

  python host/collect.py --host m1          (folder <RESULTS_DIR>/m1 from params.conf)
  python host/collect.py --results results/m1
  -> results/m1/summary.csv        one row per (block, algorithm, operation)
     results/m1/iterations.csv.gz  one row per measured iteration
     results/m1/baseline.csv       idle-interpreter cgroup memory per block
     results/m1/report.txt         sanity report (also printed)
"""
import argparse, csv, glob, gzip, json, os, statistics
from collections import Counter, defaultdict

import params

SUMMARY_COLS = ["host", "phase", "config", "label", "cpus", "mem_mb", "clock", "rep", "block_index", "order_in_block",
                "algorithm", "family", "liboqs_name", "operation", "n_warmup", "n_measured", "slow_mode", "warmup_median_ms",
                "median_ms", "mean_ms", "min_ms", "max_ms", "p25_ms", "p75_ms", "total_ms", "tracemalloc_peak_kb",
                "cgroup_memory_peak_mb", "cgroup_memory_max_mb", "nr_periods", "nr_throttled", "throttled_usec", "usage_usec",
                "oom_killed", "correctness_failures", "public_key_bytes", "artifact_bytes", "start_utc", "end_utc",
                "liboqs_version", "cryptography_version", "python", "image_id"]


def mb(x):
    return round(x / 1048576.0, 3) if isinstance(x, int) else ""


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--results", help="results folder of one host")
    g.add_argument("--host", help="host name, resolved as <RESULTS_DIR>/<host>")
    a = ap.parse_args()
    root = a.results or os.path.join(params.RESULTS_DIR, a.host)
    rows, base_rows, iter_files = [], [], []
    oom, errors = [], []
    for path in sorted(glob.glob(os.path.join(root, "blocks", "*", "*.json"))):
        with open(path) as f:
            r = json.load(f)
        m = r.get("meta", {})
        if r.get("algorithm") == "BASELINE":
            ce = r.get("cgroup_end", {})
            base_rows.append([m.get("block_index"), m.get("config"), m.get("rep"), mb(ce.get("memory_peak")), mb(ce.get("memory_current"))])
            continue
        if r.get("oom_killed"):
            oom.append((m.get("block_index"), m.get("config"), r["algorithm"]))
            rows.append({**{c: "" for c in SUMMARY_COLS}, "host": m.get("host"), "phase": m.get("phase"), "config": m.get("config"),
                         "rep": m.get("rep"), "block_index": m.get("block_index"), "algorithm": r["algorithm"], "oom_killed": True})
            continue
        ce, d = r.get("cgroup_end", {}), r.get("cgroup_delta", {})
        for op in r["operations"]:
            rows.append({
                "host": m.get("host"), "phase": m.get("phase"), "config": m.get("config"), "label": m.get("label"),
                "cpus": m.get("cpus"), "mem_mb": m.get("mem_mb"), "clock": m.get("clock"), "rep": m.get("rep"),
                "block_index": m.get("block_index"), "order_in_block": m.get("order_in_block"),
                "algorithm": r["algorithm"], "family": r["family"], "liboqs_name": r.get("liboqs_name") or "",
                "operation": op["operation"], "n_warmup": op["n_warmup"], "n_measured": op["n_measured"], "slow_mode": op["slow_mode"],
                "warmup_median_ms": op["warmup_median_ms"], "median_ms": op["median_ms"], "mean_ms": op["mean_ms"],
                "min_ms": op["min_ms"], "max_ms": op["max_ms"], "p25_ms": op["p25_ms"], "p75_ms": op["p75_ms"], "total_ms": op["total_ms"],
                "tracemalloc_peak_kb": op["tracemalloc_peak_kb"],
                "cgroup_memory_peak_mb": mb(ce.get("memory_peak")), "cgroup_memory_max_mb": mb(ce.get("memory_max")),
                "nr_periods": d.get("nr_periods", ""), "nr_throttled": d.get("nr_throttled", ""),
                "throttled_usec": d.get("throttled_usec", ""), "usage_usec": d.get("usage_usec", ""),
                "oom_killed": False, "correctness_failures": r.get("correctness_failures"),
                "public_key_bytes": r.get("public_key_bytes"), "artifact_bytes": r.get("artifact_bytes"),
                "start_utc": r.get("start_utc"), "end_utc": r.get("end_utc"), "liboqs_version": r.get("liboqs_version"),
                "cryptography_version": r.get("cryptography_version"), "python": r.get("python"), "image_id": m.get("image_id"),
            })
        if r.get("correctness_failures"):
            errors.append((m.get("block_index"), r["algorithm"], r["correctness_failures"]))
        it = path[:-5] + ".iter.csv"
        if os.path.exists(it):
            iter_files.append((m, r["algorithm"], it))

    with open(os.path.join(root, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLS); w.writeheader(); w.writerows(rows)
    with open(os.path.join(root, "baseline.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["block_index", "config", "rep", "memory_peak_mb", "memory_current_mb"]); w.writerows(base_rows)
    with gzip.open(os.path.join(root, "iterations.csv.gz"), "wt", newline="") as f:
        w = csv.writer(f); w.writerow(["host", "phase", "config", "rep", "block_index", "algorithm", "operation", "iteration", "ns"])
        for m, algo, it in iter_files:
            with open(it) as g:
                rd = csv.reader(g); next(rd)
                for op, i, ns in rd:
                    w.writerow([m.get("host"), m.get("phase"), m.get("config"), m.get("rep"), m.get("block_index"), algo, op, i, ns])

    # ---- sanity report ----
    lines = []
    cells = Counter((r["config"], r["algorithm"], r["operation"]) for r in rows if r["operation"])
    per_cfg = defaultdict(set)
    for r in rows:
        if r["operation"]:
            per_cfg[r["config"]].add((r["algorithm"], r["rep"]))
    lines.append(f"algorithm runs: {len({(r['block_index'], r['algorithm']) for r in rows})}, operation rows: {len(rows)}")
    for cfg in sorted(per_cfg):
        reps = Counter(alg for alg, _ in per_cfg[cfg])
        lines.append(f"  {cfg}: {len(reps)} algorithms, reps per algorithm min={min(reps.values())} max={max(reps.values())}")
    lines.append(f"OOM-killed runs: {len(oom)} {oom[:10]}")
    lines.append(f"correctness failures: {len(errors)} {errors[:10]}")
    thr = defaultdict(list)
    for r in rows:
        if r["operation"] == "keygen" and r["nr_throttled"] != "":
            thr[r["config"]].append(int(r["nr_throttled"]))
    for cfg in sorted(thr):
        lines.append(f"  throttling {cfg}: nr_throttled per run median={statistics.median(thr[cfg])} max={max(thr[cfg])}")
    slow = Counter((r["config"], r["algorithm"], r["operation"]) for r in rows if r["slow_mode"] is True)
    lines.append(f"operations measured in slow mode (20 iterations): {len(slow)} cells -> {sorted(slow)[:12]}")
    mem = [r["cgroup_memory_peak_mb"] for r in rows if r["cgroup_memory_peak_mb"] != ""]
    if mem:
        lines.append(f"cgroup memory peak MB: min={min(mem)} max={max(mem)}")
    report = "\n".join(lines)
    with open(os.path.join(root, "report.txt"), "w") as f:
        f.write(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
