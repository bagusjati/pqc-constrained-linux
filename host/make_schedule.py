#!/usr/bin/env python3
"""
make_schedule.py - generates the COMPLETE execution schedule of one host BEFORE
anything is run, so that the run order is fixed, reproducible and reportable.

  python host/make_schedule.py --host m1            -> <SCHEDULE_DIR>/schedule_m1.json
  python host/make_schedule.py --host pi            -> <SCHEDULE_DIR>/schedule_pi.json
  python host/make_schedule.py --host m1 --pilot    -> <SCHEDULE_DIR>/schedule_m1_pilot.json

  SCHEDULE_DIR and the master seed come from params.conf.

Structure of the schedule:
  phase "main"      : configs T1, T2, T3          x reps_main      (default 10)
  phase "ablation"  : configs A1, A2, A3, A4      x reps_ablation  (default 10)
  phase "lowclock"  : configs F1, F2 (Pi only)    x reps_lowclock  (default 5)

  For every repetition r of a phase, the configs of that phase are visited in a
  random order (one block per config). Inside a block, the 15 algorithms are
  visited in a random order. Every random draw is seeded from (master seed,
  host, phase, r) and stored, so the schedule can be regenerated exactly.
  Consequence: tiers are interleaved over time (T1,T3,T2 / T2,T1,T3 / ...),
  and algorithms are interleaved inside every tier. This is the answer to the
  reviewers' point on execution order, randomization and blocking.
"""
import argparse, json, os, random, time

import params

ALGORITHMS = [
    "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "FrodoKEM-640", "BIKE-L1", "HQC-128", "ECDH-X25519",
    "ML-DSA-44", "ML-DSA-65", "ML-DSA-87",
    "SLH-DSA-SHA2-128s", "SLH-DSA-SHA2-192s", "SLH-DSA-SHA2-256s", "ECDSA-P256", "RSA-2048",
]

CONFIGS = {
    # id : cpus, memory MB, cpu clock mode (Pi only; ignored on M1), phase, label
    "T1": dict(cpus=1.00, mem_mb=512, clock="performance", phase="main",     label="Unconstrained"),
    "T2": dict(cpus=0.50, mem_mb=128, clock="performance", phase="main",     label="IoT-Moderate"),
    "T3": dict(cpus=0.25, mem_mb=64,  clock="performance", phase="main",     label="IoT-Extreme"),
    "A1": dict(cpus=0.50, mem_mb=512, clock="performance", phase="ablation", label="CPU 0.50, memory fixed 512"),
    "A2": dict(cpus=0.25, mem_mb=512, clock="performance", phase="ablation", label="CPU 0.25, memory fixed 512"),
    "A3": dict(cpus=1.00, mem_mb=128, clock="performance", phase="ablation", label="memory 128, CPU fixed 1.00"),
    "A4": dict(cpus=1.00, mem_mb=64,  clock="performance", phase="ablation", label="memory 64, CPU fixed 1.00"),
    "F1": dict(cpus=1.00, mem_mb=512, clock="powersave",   phase="lowclock", label="Unconstrained quota, minimum CPU clock"),
    "F2": dict(cpus=0.25, mem_mb=64,  clock="powersave",   phase="lowclock", label="IoT-Extreme quota, minimum CPU clock"),
}
PHASE_ORDER = ["main", "ablation", "lowclock"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, choices=["m1", "pi"])
    ap.add_argument("--out", default=None, help="default: <SCHEDULE_DIR>/schedule_<host>[_pilot].json")
    ap.add_argument("--seed", type=int, default=params.SEED)
    ap.add_argument("--reps-main", type=int, default=10)
    ap.add_argument("--reps-ablation", type=int, default=10)
    ap.add_argument("--reps-lowclock", type=int, default=5)
    ap.add_argument("--phases", default=None, help="comma list, default: m1=main,ablation  pi=main,ablation,lowclock")
    ap.add_argument("--pilot", action="store_true", help="1 repetition of phase main only")
    a = ap.parse_args()

    phases = a.phases.split(",") if a.phases else (["main", "ablation"] if a.host == "m1" else PHASE_ORDER)
    reps = {"main": a.reps_main, "ablation": a.reps_ablation, "lowclock": a.reps_lowclock}
    if a.pilot:
        phases, reps = ["main"], {"main": 1}

    if a.out is None:
        a.out = os.path.join(params.SCHEDULE_DIR, f"schedule_{a.host}{'_pilot' if a.pilot else ''}.json")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    blocks = []
    for phase in PHASE_ORDER:
        if phase not in phases:
            continue
        cfg_ids = [c for c in CONFIGS if CONFIGS[c]["phase"] == phase]
        for r in range(1, reps[phase] + 1):
            rng_cfg = random.Random(f"{a.seed}-{a.host}-{phase}-rep{r}-configs")
            order = cfg_ids[:]
            rng_cfg.shuffle(order)
            for cid in order:
                seed_str = f"{a.seed}-{a.host}-{phase}-rep{r}-{cid}-algos"
                rng = random.Random(seed_str)
                algos = ALGORITHMS[:]
                rng.shuffle(algos)
                c = CONFIGS[cid]
                blocks.append(dict(block_index=len(blocks), phase=phase, config=cid, label=c["label"],
                                   cpus=c["cpus"], mem_mb=c["mem_mb"], clock=c["clock"], rep=r,
                                   seed=seed_str, algorithms=algos))
    sched = dict(host=a.host, master_seed=a.seed, generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 pilot=a.pilot, phases=phases, reps=reps, n_blocks=len(blocks),
                 n_runs=len(blocks) * len(ALGORITHMS), configs=CONFIGS, blocks=blocks)
    with open(a.out, "w") as f:
        json.dump(sched, f, indent=1)
    print(f"{a.out}: {len(blocks)} blocks, {sched['n_runs']} algorithm runs, phases={phases}, reps={ {p: reps[p] for p in phases} }")
    for b in blocks[:6]:
        print(f"  block {b['block_index']:3d} {b['phase']:8s} {b['config']} rep{b['rep']:2d} first algos: {b['algorithms'][:4]} ...")


if __name__ == "__main__":
    main()
