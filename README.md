# pqc-constrained-linux

Benchmark harness and raw results for the article *Resource-Tiered Benchmarking of
Post-Quantum Cryptographic Algorithms for Constrained Linux-Based IoT Environments*
(International Journal of Intelligent Engineering and Systems, under revision).

Fifteen algorithm variants (ML-KEM-512/768/1024, ML-DSA-44/65/87,
SLH-DSA-SHA2-128s/192s/256s, FrodoKEM-640, BIKE-L1, HQC-128, RSA-2048, ECDSA-P256,
ECDH-X25519) are measured inside Docker containers whose CPU quota and memory limit
are set per configuration, on a fixed software stack. The primary host is a
Raspberry Pi 4 running native Linux. An Apple M1 host running Docker Desktop is a
cross-host comparison.

## Repository layout

| Path | Content |
|---|---|
| `params.conf` | Global parameters: image name, image archive, folder locations (`RESULTS_DIR`, `SCHEDULE_DIR`, `ARCHIVE_DIR`), and the schedule seed. Relative paths resolve from the repository root. A value set in the environment takes precedence. |
| `docker/` | `Dockerfile` (Python 3.12, liboqs 0.16.0 built from source, liboqs-python 0.16.0.1, cryptography 46.0.7) and `requirements.txt`. |
| `bench/` | `bench.py` runs inside the container (one algorithm, three operations, per-iteration timings, cgroup v2 counters, correctness checks). `selfcheck.py` runs at build time. |
| `host/` | `make_schedule.py` (seeded execution schedule), `run_campaign.py` (one container per block and algorithm, resumable), `collect.py` (merges results), `env_report.sh` (environment record), `params.py` (reads `params.conf`). |
| `scripts/` | Wrappers for each step. All of them load `params.conf` through `load-config.sh`. |
| `results/` | Raw results of the campaigns reported in the article: `pi` and `m1`, plus the one-repetition pilots `pi_pilot` and `m1_pilot`. |

Each results folder holds `schedule.json`, `run_log.csv` (one row per container),
`image_id.txt`, `blocks/NNNN/<algorithm>.json`, `.iter.csv` and `.stderr.txt`, and the
merged files `summary.csv`, `iterations.csv.gz` (every measured iteration in
nanoseconds), `baseline.csv`, and `report.txt`. The full campaigns also hold
`env_report.txt` and `console.log`.

## Configurations

| id | CPU quota | memory | CPU clock | phase | repetitions |
|----|-----------|--------|-----------|-------|-------------|
| T1 | 1.00 core | 512 MB | performance | main | 10 |
| T2 | 0.50 core | 128 MB | performance | main | 10 |
| T3 | 0.25 core | 64 MB | performance | main | 10 |
| A1 | 0.50 core | 512 MB | performance | ablation | 10 |
| A2 | 0.25 core | 512 MB | performance | ablation | 10 |
| A3 | 1.00 core | 128 MB | performance | ablation | 10 |
| A4 | 1.00 core | 64 MB | performance | ablation | 10 |
| F1 | 1.00 core | 512 MB | powersave (minimum clock) | lowclock, Pi only | 5 |
| F2 | 0.25 core | 64 MB | powersave (minimum clock) | lowclock, Pi only | 5 |

The CPU quota is set as `--cpu-period 100000 --cpu-quota <cores x 100000>` and the
memory as `--memory` with `--memory-swap` equal to it. On the Pi the container is
pinned to core 0. Per operation, 10 warm-up iterations are discarded and 100
iterations are measured (20 when the warm-up median exceeds 0.3 s).

## Reproducing the measurements

Requirements: Docker with cgroup v2, Python 3, and `zip`. The Raspberry Pi 4 runs
Raspberry Pi OS Lite 64-bit (Bookworm) with a heatsink, a fan, the official 5 V 3 A
power supply, and a wired network connection. All commands run from the repository
root.

1. Build the image once on an arm64 host and record its Id. The image archive is
   written to `IMAGE_TAR`.
   ```bash
   bash scripts/build_image_m1.sh
   ```
2. Prepare the Raspberry Pi, reboot, load the same image, and check the host. Every
   line of `check_pi.sh` must print `OK`.
   ```bash
   sudo bash scripts/setup_pi.sh && sudo reboot
   docker load < pqc-tier-bench-1.0.tar.gz
   bash scripts/check_pi.sh
   bash host/env_report.sh > results/pi/env_report.txt
   ```
3. Optional pilot (one repetition of the main phase):
   `bash scripts/pilot_m1.sh` on the M1, `bash scripts/pilot_pi.sh` on the Pi inside `tmux`.
4. Generate the schedule. The seed in `params.conf` (20260928) regenerates the
   schedules stored in `results/<host>/schedule.json` exactly.
   ```bash
   python3 host/make_schedule.py --host pi    # writes schedules/schedule_pi.json
   python3 host/make_schedule.py --host m1    # writes schedules/schedule_m1.json
   ```
5. Run the campaign (Pi: 80 blocks, 1,200 algorithm runs, three to four days;
   M1: 70 blocks, 1,050 algorithm runs, 10 to 14 hours). The runner is resumable:
   rerunning the same command skips every run whose result already exists.
   ```bash
   tmux new -s campaign
   bash scripts/run_pi.sh          # on the Pi
   bash scripts/run_m1.sh          # on the M1
   bash scripts/progress.sh pi     # monitoring
   ```
6. Merge the results and record the environment. The archive is written to `ARCHIVE_DIR`.
   ```bash
   sudo bash scripts/finish.sh pi
   bash scripts/finish.sh m1
   ```

To analyse the published data without rerunning, read `results/<host>/summary.csv`
and `results/<host>/iterations.csv.gz`. `python3 host/collect.py --host pi`
regenerates the merged files from the raw block files.

## Citation

If you use this code or data, please cite the article (the citation will be added
upon publication).
