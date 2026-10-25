#!/usr/bin/env python3
"""
run_campaign.py - executes a schedule produced by make_schedule.py on the host.
One Docker container per (block, algorithm). Resumable: runs whose result JSON
already exists are skipped, so the script can be restarted after any failure.

  python host/run_campaign.py --schedule schedules/schedule_m1.json
  python host/run_campaign.py --schedule schedules/schedule_pi.json --pi

  The image and the results folder default to IMAGE and <RESULTS_DIR>/<host>
  (<host>_pilot for a pilot schedule) from params.conf.

Per container:
  docker run --name <n> --cpu-period 100000 --cpu-quota <c*100000> --memory <m>m --memory-swap <m>m \
             --cpuset-cpus 0 (Pi only) -v <abs results>/blocks/NNNN:/out <image> \
             --algorithm A --out /out/A.json --iterations-out /out/A.iter.csv --meta '{...}'
  then docker inspect -> ExitCode, OOMKilled; container stderr saved; docker rm.

Host-side log (run_log.csv): one row per container with UTC start/end, exit
code, OOMKilled, CPU temperature and frequency before/after (Pi), and
vcgencmd get_throttled (Pi). Keep this file, it is part of the deliverable.
"""
import argparse, csv, json, os, shutil, subprocess, sys, time

import params

PI_TEMP = "/sys/class/thermal/thermal_zone0/temp"
PI_FREQ = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
PI_GOV = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""


def sh(cmd, timeout=None, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr}")
    return r


def pi_state(is_pi):
    if not is_pi:
        return {"temp_c": "", "freq_khz": "", "governor": "", "get_throttled": ""}
    t = read(PI_TEMP)
    thr = ""
    if shutil.which("vcgencmd"):
        thr = sh(["vcgencmd", "get_throttled"]).stdout.strip().replace("throttled=", "")
    return {"temp_c": (int(t) / 1000.0) if t.isdigit() else "", "freq_khz": read(PI_FREQ),
            "governor": read(PI_GOV), "get_throttled": thr}


def set_governor(mode):
    """mode: performance | powersave. Needs sudo. Applied to every core."""
    cur = read(PI_GOV)
    if cur == mode:
        return
    r = subprocess.run(f"echo {mode} | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null",
                       shell=True, capture_output=True, text=True)
    if r.returncode != 0 or read(PI_GOV) != mode:
        raise SystemExit(f"could not set governor to {mode}: {r.stderr}")
    time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", required=True)
    ap.add_argument("--image", default=params.IMAGE)
    ap.add_argument("--results", default=None, help="default: <RESULTS_DIR>/<host>[_pilot]")
    ap.add_argument("--pi", action="store_true", help="host is the Raspberry Pi: set governor, pin to cpu 0, log temperature")
    ap.add_argument("--sleep-algos", type=float, default=10.0, help="seconds between containers")
    ap.add_argument("--sleep-blocks", type=float, default=30.0, help="seconds between blocks")
    ap.add_argument("--timeout-s", type=int, default=4 * 3600, help="kill a container after this many seconds")
    ap.add_argument("--n-warmup", type=int, default=10)
    ap.add_argument("--n-measured", type=int, default=100)
    ap.add_argument("--n-slow", type=int, default=20)
    ap.add_argument("--slow-threshold-s", type=float, default=0.3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.schedule) as f:
        sched = json.load(f)
    host = sched["host"]
    if a.results is None:
        a.results = os.path.join(params.RESULTS_DIR, host + ("_pilot" if sched.get("pilot") else ""))
    res_root = os.path.abspath(a.results)
    os.makedirs(res_root, exist_ok=True)
    shutil.copy(a.schedule, os.path.join(res_root, "schedule.json"))
    image_id = sh(["docker", "image", "inspect", "--format", "{{.Id}}", a.image]).stdout.strip()
    with open(os.path.join(res_root, "image_id.txt"), "w") as f:
        f.write(image_id + "\n")
    log_path = os.path.join(res_root, "run_log.csv")
    new_log = not os.path.exists(log_path)
    log = open(log_path, "a", newline="")
    w = csv.writer(log)
    if new_log:
        w.writerow(["block_index", "phase", "config", "rep", "order_in_block", "algorithm", "container", "start_utc", "end_utc",
                    "wall_s", "exit_code", "oom_killed", "temp_c_start", "temp_c_end", "freq_khz_start", "freq_khz_end",
                    "governor", "get_throttled_start", "get_throttled_end", "status"])

    total = sum(len(b["algorithms"]) + 1 for b in sched["blocks"])
    done = 0
    for b in sched["blocks"]:
        bdir = os.path.join(res_root, "blocks", f"{b['block_index']:04d}")
        os.makedirs(bdir, exist_ok=True)
        if a.pi:
            set_governor(b["clock"])
        # BASELINE first (idle interpreter: memory baseline + container warm start), then the algorithms
        for order, algo in enumerate(["BASELINE"] + b["algorithms"]):
            done += 1
            out_json = os.path.join(bdir, f"{algo}.json")
            if os.path.exists(out_json) and os.path.getsize(out_json) > 0:
                continue
            meta = dict(host=host, block_index=b["block_index"], phase=b["phase"], config=b["config"], label=b["label"],
                        cpus=b["cpus"], mem_mb=b["mem_mb"], clock=b["clock"], rep=b["rep"], order_in_block=order,
                        block_seed=b["seed"], image_id=image_id)
            name = f"ptb-{host}-{b['block_index']:04d}-{algo.replace('+', 'p')}"
            cmd = ["docker", "run", "--name", name,
                   "--cpu-period", "100000", "--cpu-quota", str(int(round(b["cpus"] * 100000))),
                   "--memory", f"{b['mem_mb']}m", "--memory-swap", f"{b['mem_mb']}m",
                   "-v", f"{bdir}:/out"]
            if a.pi:
                cmd += ["--cpuset-cpus", "0"]
            cmd += [a.image, "--algorithm", algo, "--out", f"/out/{algo}.json", "--iterations-out", f"/out/{algo}.iter.csv",
                    "--n-warmup", str(a.n_warmup), "--n-measured", str(a.n_measured), "--n-slow", str(a.n_slow),
                    "--slow-threshold-s", str(a.slow_threshold_s), "--meta", json.dumps(meta)]
            print(f"[{done}/{total}] block {b['block_index']} {b['phase']} {b['config']} rep{b['rep']} {algo}", flush=True)
            if a.dry_run:
                print("   ", " ".join(cmd))
                continue
            sh(["docker", "rm", "-f", name])  # leftover from an interrupted run, if any
            s0 = pi_state(a.pi)
            t0 = time.time(); start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            status = "ok"
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout_s)
                stderr = r.stderr
            except subprocess.TimeoutExpired as e:
                sh(["docker", "kill", name]); status = "timeout"; stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); wall = time.time() - t0
            ins = sh(["docker", "inspect", "--format", "{{.State.ExitCode}} {{.State.OOMKilled}}", name]).stdout.split()
            exit_code, oom = (ins + ["", ""])[:2]
            sh(["docker", "rm", "-f", name])
            s1 = pi_state(a.pi)
            with open(os.path.join(bdir, f"{algo}.stderr.txt"), "w") as f:
                f.write(stderr)
            if oom == "true":
                status = "oom"
                # keep a marker so the run is not retried as "missing"
                with open(out_json, "w") as f:
                    json.dump({"algorithm": algo, "meta": meta, "oom_killed": True, "exit_code": exit_code,
                               "start_utc": start, "end_utc": end}, f)
            elif exit_code != "0":
                status = f"error-{exit_code}"
            w.writerow([b["block_index"], b["phase"], b["config"], b["rep"], order, algo, name, start, end, f"{wall:.1f}",
                        exit_code, oom, s0["temp_c"], s1["temp_c"], s0["freq_khz"], s1["freq_khz"], s1["governor"],
                        s0["get_throttled"], s1["get_throttled"], status])
            log.flush()
            time.sleep(a.sleep_algos)
        if not a.dry_run:
            time.sleep(a.sleep_blocks)
    if a.pi and not a.dry_run:
        set_governor("performance")
    log.close()
    print("campaign finished")


if __name__ == "__main__":
    main()
