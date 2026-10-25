#!/usr/bin/env bash
# env_report.sh - collects the host environment description required by the paper.
#   bash host/env_report.sh pqc-tier-bench:1.0 > <RESULTS_DIR>/<host>/env_report.txt
IMAGE=${1:-${IMAGE:-pqc-tier-bench:1.0}}
echo "=== date (UTC)"; date -u
echo "=== uname"; uname -a
echo "=== os-release"; cat /etc/os-release 2>/dev/null || sw_vers 2>/dev/null
echo "=== cpu"; (grep -m1 -E 'model name|Model' /proc/cpuinfo; grep -c ^processor /proc/cpuinfo) 2>/dev/null || sysctl -n machdep.cpu.brand_string hw.ncpu 2>/dev/null
echo "=== memory"; (free -m 2>/dev/null) || sysctl -n hw.memsize 2>/dev/null
echo "=== docker version"; docker version
echo "=== docker info (cgroup, runtime, resources)"; docker info 2>/dev/null | grep -iE 'cgroup|Server Version|Operating System|OSType|Architecture|CPUs|Total Memory|Kernel|Runtime'
echo "=== docker info warnings"; docker info 2>&1 | grep -i warning
echo "=== image"; docker image inspect --format 'Id={{.Id}} Created={{.Created}} Arch={{.Architecture}} Os={{.Os}}' "$IMAGE"
echo "=== inside image: liboqs commit, pip freeze, python"; docker run --rm --entrypoint sh "$IMAGE" -c 'cat /usr/local/liboqs-commit.txt; cat /usr/local/pip-freeze.txt; python --version; python -c "import oqs;print(\"liboqs\",oqs.oqs_version(),\"liboqs-python\",oqs.oqs_python_version())"'
echo "=== inside container: cgroup files visible at a 0.25 core / 64 MB quota"; docker run --rm --cpus 0.25 --memory 64m --memory-swap 64m --entrypoint sh "$IMAGE" -c 'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/cpu.stat; cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo "memory.peak missing"'
if [ -e /sys/devices/system/cpu/cpu0/cpufreq ]; then
  echo "=== cpufreq"; for f in scaling_governor scaling_available_governors scaling_min_freq scaling_max_freq scaling_cur_freq; do echo "$f=$(cat /sys/devices/system/cpu/cpu0/cpufreq/$f)"; done
fi
if command -v vcgencmd >/dev/null; then
  echo "=== raspberry pi"; cat /proc/device-tree/model; echo; vcgencmd get_throttled; vcgencmd measure_temp; vcgencmd measure_volts; cat /boot/firmware/cmdline.txt 2>/dev/null || cat /boot/cmdline.txt
fi
echo "=== other load on the host (top 5 by CPU)"; (ps -eo pcpu,comm --sort=-pcpu | head -6) 2>/dev/null
