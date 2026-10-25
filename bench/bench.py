#!/usr/bin/env python3
"""
bench.py - runs INSIDE the container. Benchmarks exactly ONE algorithm and
writes one JSON result plus one per-iteration CSV.

Usage (inside container):
  python bench.py --algorithm ML-KEM-512 --out /out/ML-KEM-512.json \
                  --iterations-out /out/ML-KEM-512.iter.csv \
                  --n-warmup 10 --n-measured 100 --n-slow 20 --slow-threshold-s 0.3

Design (see daftar_tugas_revisi_ijies.md, bagian 4):
  * three operations per algorithm: keygen, encaps|sign, decaps|verify
  * 10 warm-up iterations (discarded), then n_measured iterations
  * if the warm-up median of an operation exceeds slow-threshold-s,
    that operation is measured with n_slow iterations instead of n_measured
  * gc disabled during measured loops, perf_counter_ns timer
  * tracemalloc peak per operation (wrapper-visible memory)
  * cgroup v2 counters read at process start and end:
      cpu.stat (nr_periods, nr_throttled, throttled_usec), memory.peak,
      memory.current, memory.max, cpu.max
  * correctness checked on every decaps/verify (failures counted)
"""
import argparse, csv, gc, hashlib, json, os, platform, statistics, sys, time, tracemalloc

# ----------------------------------------------------------------------------
# algorithm table: paper label -> (family, backend, liboqs candidate names)
# liboqs names differ between versions, so each entry lists candidates in
# order of preference; the first one enabled in this liboqs build is used.
# ----------------------------------------------------------------------------
ALGOS = {
    "ML-KEM-512":        ("kem", "oqs", ["ML-KEM-512", "Kyber512"]),
    "ML-KEM-768":        ("kem", "oqs", ["ML-KEM-768", "Kyber768"]),
    "ML-KEM-1024":       ("kem", "oqs", ["ML-KEM-1024", "Kyber1024"]),
    "FrodoKEM-640":      ("kem", "oqs", ["FrodoKEM-640-AES"]),
    "BIKE-L1":           ("kem", "oqs", ["BIKE-L1"]),
    "HQC-128":           ("kem", "oqs", ["HQC-1", "HQC-128"]),
    "ECDH-X25519":       ("kem", "classical", []),
    "ML-DSA-44":         ("sig", "oqs", ["ML-DSA-44", "Dilithium2"]),
    "ML-DSA-65":         ("sig", "oqs", ["ML-DSA-65", "Dilithium3"]),
    "ML-DSA-87":         ("sig", "oqs", ["ML-DSA-87", "Dilithium5"]),
    "SLH-DSA-SHA2-128s": ("sig", "oqs", ["SLH_DSA_PURE_SHA2_128S", "SLH-DSA-SHA2-128s", "SPHINCS+-SHA2-128s-simple"]),
    "SLH-DSA-SHA2-192s": ("sig", "oqs", ["SLH_DSA_PURE_SHA2_192S", "SLH-DSA-SHA2-192s", "SPHINCS+-SHA2-192s-simple"]),
    "SLH-DSA-SHA2-256s": ("sig", "oqs", ["SLH_DSA_PURE_SHA2_256S", "SLH-DSA-SHA2-256s", "SPHINCS+-SHA2-256s-simple"]),
    "ECDSA-P256":        ("sig", "classical", []),
    "RSA-2048":          ("sig", "classical", []),
}

# fixed 32-byte message for every signature scheme (same value on every host)
MESSAGE = hashlib.sha256(b"pqc-tier-bench-message").digest()
assert len(MESSAGE) == 32


# ----------------------------------------------------------------------------
# cgroup helpers (v2 first, v1 fallback). Missing files -> None, never crash.
# ----------------------------------------------------------------------------
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def read_cgroup():
    out = {"cgroup_version": None}
    base = "/sys/fs/cgroup"
    cpu_stat = _read(f"{base}/cpu.stat")
    if cpu_stat is not None:  # cgroup v2
        out["cgroup_version"] = 2
        for line in cpu_stat.splitlines():
            k, _, v = line.partition(" ")
            if k in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec"):
                out[k] = int(v)
        out["cpu_max"] = _read(f"{base}/cpu.max")
        for k in ("memory.peak", "memory.current", "memory.max", "memory.swap.max"):
            v = _read(f"{base}/{k}")
            out[k.replace(".", "_")] = int(v) if v not in (None, "max") else v
        ev = _read(f"{base}/memory.events")
        if ev:
            for line in ev.splitlines():
                k, _, v = line.partition(" ")
                out["memory_events_" + k] = int(v)
        return out
    cpu_stat = _read(f"{base}/cpu/cpu.stat") or _read(f"{base}/cpu,cpuacct/cpu.stat")
    if cpu_stat is not None:  # cgroup v1
        out["cgroup_version"] = 1
        for line in cpu_stat.splitlines():
            k, _, v = line.partition(" ")
            if k in ("nr_periods", "nr_throttled", "throttled_time"):
                out[k] = int(v)
        if "throttled_time" in out:
            out["throttled_usec"] = out.pop("throttled_time") // 1000
        q = _read(f"{base}/cpu/cpu.cfs_quota_us"); p = _read(f"{base}/cpu/cpu.cfs_period_us")
        out["cpu_max"] = f"{q} {p}"
        v = _read(f"{base}/memory/memory.max_usage_in_bytes")
        out["memory_peak"] = int(v) if v else None
        v = _read(f"{base}/memory/memory.usage_in_bytes")
        out["memory_current"] = int(v) if v else None
        v = _read(f"{base}/memory/memory.limit_in_bytes")
        out["memory_max"] = int(v) if v else None
        v = _read(f"{base}/memory/memory.failcnt")
        out["memory_failcnt"] = int(v) if v else None
    return out


# ----------------------------------------------------------------------------
# backends
# ----------------------------------------------------------------------------
class OqsKem:
    def __init__(self, name):
        import oqs
        self.oqs = oqs
        self.kem = oqs.KeyEncapsulation(name)
        self.pk = None
        self.details = self.kem.details

    def keygen(self):
        self.pk = self.kem.generate_keypair()

    def encaps(self):
        ct, ss = self.kem.encap_secret(self.pk)
        return ct, ss

    def decaps(self, ct):
        return self.kem.decap_secret(ct)

    def sizes(self, ct):
        return len(self.pk), len(ct)


class X25519Kem:
    """ECDH-X25519 expressed in KEM form: encaps = ephemeral keypair + exchange,
    transmitted artifact = ephemeral public key (32 bytes, raw)."""
    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives import serialization
        self.x = x25519; self.ser = serialization
        self.sk = None; self.pk = None

    def keygen(self):
        self.sk = self.x.X25519PrivateKey.generate()
        self.pk = self.sk.public_key()

    def encaps(self):
        eph = self.x.X25519PrivateKey.generate()
        ss = eph.exchange(self.pk)
        ct = eph.public_key().public_bytes(self.ser.Encoding.Raw, self.ser.PublicFormat.Raw)
        return ct, ss

    def decaps(self, ct):
        return self.sk.exchange(self.x.X25519PublicKey.from_public_bytes(ct))

    def sizes(self, ct):
        return len(self.pk.public_bytes(self.ser.Encoding.Raw, self.ser.PublicFormat.Raw)), len(ct)


class OqsSig:
    def __init__(self, name):
        import oqs
        self.sig = oqs.Signature(name)
        self.pk = None
        self.details = self.sig.details

    def keygen(self):
        self.pk = self.sig.generate_keypair()

    def sign(self):
        return self.sig.sign(MESSAGE)

    def verify(self, s):
        return self.sig.verify(MESSAGE, s, self.pk)

    def sizes(self, s):
        return len(self.pk), len(s)


class ClassicalSig:
    """ECDSA-P256 (SHA-256) or RSA-2048 (PKCS#1 v1.5, SHA-256).
    Public key size = DER SubjectPublicKeyInfo (91 bytes P-256, 294 bytes RSA-2048)."""
    def __init__(self, kind):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
        from cryptography.exceptions import InvalidSignature
        self.kind = kind; self.hashes = hashes; self.ser = serialization
        self.ec = ec; self.rsa = rsa; self.padding = padding; self.InvalidSignature = InvalidSignature
        self.sk = None; self.pk = None

    def keygen(self):
        if self.kind == "ECDSA-P256":
            self.sk = self.ec.generate_private_key(self.ec.SECP256R1())
        else:
            self.sk = self.rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pk = self.sk.public_key()

    def sign(self):
        if self.kind == "ECDSA-P256":
            return self.sk.sign(MESSAGE, self.ec.ECDSA(self.hashes.SHA256()))
        return self.sk.sign(MESSAGE, self.padding.PKCS1v15(), self.hashes.SHA256())

    def verify(self, s):
        try:
            if self.kind == "ECDSA-P256":
                self.pk.verify(s, MESSAGE, self.ec.ECDSA(self.hashes.SHA256()))
            else:
                self.pk.verify(s, MESSAGE, self.padding.PKCS1v15(), self.hashes.SHA256())
            return True
        except self.InvalidSignature:
            return False

    def sizes(self, s):
        der = self.pk.public_bytes(self.ser.Encoding.DER, self.ser.PublicFormat.SubjectPublicKeyInfo)
        return len(der), len(s)


def make_backend(label):
    family, backend, candidates = ALGOS[label]
    if backend == "classical":
        if label == "ECDH-X25519":
            return X25519Kem(), None
        return ClassicalSig(label), None
    import oqs
    enabled = oqs.get_enabled_kem_mechanisms() if family == "kem" else oqs.get_enabled_sig_mechanisms()
    for name in candidates:
        if name in enabled:
            return (OqsKem(name) if family == "kem" else OqsSig(name)), name
    raise SystemExit(f"none of {candidates} is enabled in this liboqs build ({oqs.oqs_version()})")


# ----------------------------------------------------------------------------
# timing
# ----------------------------------------------------------------------------
def timed_loop(fn, n, arg_list=None):
    """Run fn n times (fn(arg_list[i]) if arg_list given). Returns (ns list, outputs)."""
    times = []; outs = []
    gc.collect(); gc.disable()
    try:
        for i in range(n):
            a = arg_list[i] if arg_list is not None else None
            t0 = time.perf_counter_ns()
            r = fn(a) if arg_list is not None else fn()
            t1 = time.perf_counter_ns()
            times.append(t1 - t0); outs.append(r)
    finally:
        gc.enable()
    return times, outs


def summarize(ns):
    ms = sorted(t / 1e6 for t in ns)
    n = len(ms)
    q = statistics.quantiles(ms, n=4) if n >= 4 else [ms[0], statistics.median(ms), ms[-1]]
    return {"n": n, "median_ms": statistics.median(ms), "mean_ms": statistics.fmean(ms),
            "min_ms": ms[0], "max_ms": ms[-1], "p25_ms": q[0], "p75_ms": q[2],
            "total_ms": sum(ms)}


def run_op(name, fn, n_warm, n_meas, n_slow, slow_s, arg_list=None, iter_rows=None):
    """warm-up, decide iteration count, measure with tracemalloc, return summary+outputs."""
    warm_args = arg_list[:n_warm] if arg_list is not None else None
    w_ns, _ = timed_loop(fn, n_warm, warm_args)
    warm_median_s = statistics.median(w_ns) / 1e9
    n = n_slow if warm_median_s > slow_s else n_meas
    meas_args = arg_list[n_warm:n_warm + n] if arg_list is not None else None
    tracemalloc.start()
    m_ns, outs = timed_loop(fn, n, meas_args)
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    s = summarize(m_ns)
    s.update({"operation": name, "n_warmup": n_warm, "warmup_median_ms": warm_median_s * 1e3,
              "n_measured": n, "slow_mode": n != n_meas,
              "tracemalloc_peak_kb": peak / 1024.0})
    if iter_rows is not None:
        for i, t in enumerate(m_ns):
            iter_rows.append((name, i, t))
    return s, outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algorithm", required=True, choices=sorted(ALGOS) + ["BASELINE"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--iterations-out", required=True)
    ap.add_argument("--n-warmup", type=int, default=10)
    ap.add_argument("--n-measured", type=int, default=100)
    ap.add_argument("--n-slow", type=int, default=20)
    ap.add_argument("--slow-threshold-s", type=float, default=0.3)
    ap.add_argument("--meta", default="{}", help="JSON string copied verbatim into the result (host, config, rep, ...)")
    a = ap.parse_args()

    fam, bk = ALGOS.get(a.algorithm, ("baseline", "none", []))[:2]
    result = {"algorithm": a.algorithm, "family": fam, "backend": bk,
              "meta": json.loads(a.meta), "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "python": platform.python_version(), "machine": platform.machine(),
              "cgroup_start": read_cgroup(), "operations": [], "correctness_failures": 0}
    try:
        import oqs
        result["liboqs_version"] = oqs.oqs_version(); result["liboqs_python_version"] = oqs.oqs_python_version()
    except Exception as e:
        result["liboqs_version"] = f"unavailable: {e}"
    try:
        import cryptography
        result["cryptography_version"] = cryptography.__version__
    except Exception:
        pass

    if a.algorithm == "BASELINE":
        # memory/CPU baseline of an idle interpreter with both libraries imported
        time.sleep(1.0)
        result["cgroup_end"] = read_cgroup()
        result["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.iterations_out, "w") as f:
            f.write("operation,iteration,ns\n")
        with open(a.out, "w") as f:
            json.dump(result, f, indent=1)
        print("BASELINE", result["cgroup_end"], file=sys.stderr)
        return

    be, oqs_name = make_backend(a.algorithm)
    result["liboqs_name"] = oqs_name
    if getattr(be, "details", None):
        result["liboqs_details"] = {k: (v if isinstance(v, (int, str, bool)) else str(v)) for k, v in be.details.items()}
    iter_rows = []
    total = a.n_warmup + max(a.n_measured, a.n_slow)

    if result["family"] == "kem":
        s, _ = run_op("keygen", be.keygen, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, iter_rows=iter_rows)
        result["operations"].append(s)                       # last keypair stays in the backend
        s, outs = run_op("encaps", be.encaps, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, iter_rows=iter_rows)
        result["operations"].append(s)
        # inputs for decaps: fresh ciphertexts, generated untimed, one per iteration (warm-up + measured)
        pairs = [be.encaps() for _ in range(total)]
        cts = [p[0] for p in pairs]
        s, sss = run_op("decaps", be.decaps, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, arg_list=cts, iter_rows=iter_rows)
        result["operations"].append(s)
        expected = [p[1] for p in pairs[a.n_warmup:a.n_warmup + s["n_measured"]]]
        result["correctness_failures"] = sum(1 for x, y in zip(sss, expected) if x != y)
        pk_size, art_size = be.sizes(cts[0])
    else:
        s, _ = run_op("keygen", be.keygen, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, iter_rows=iter_rows)
        result["operations"].append(s)
        s, sigs = run_op("sign", be.sign, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, iter_rows=iter_rows)
        result["operations"].append(s)
        # verify uses the signatures produced in the measured sign phase (padded if verify needs more)
        while len(sigs) < total:
            sigs.append(be.sign())
        s, oks = run_op("verify", be.verify, a.n_warmup, a.n_measured, a.n_slow, a.slow_threshold_s, arg_list=sigs, iter_rows=iter_rows)
        result["operations"].append(s)
        result["correctness_failures"] = sum(1 for ok in oks if not ok)
        pk_size, art_size = be.sizes(sigs[0])

    result["public_key_bytes"] = pk_size
    result["artifact_bytes"] = art_size
    result["message_bytes"] = len(MESSAGE)
    result["cgroup_end"] = read_cgroup()
    cs, ce = result["cgroup_start"], result["cgroup_end"]
    result["cgroup_delta"] = {k: (ce.get(k) - cs.get(k)) for k in ("nr_periods", "nr_throttled", "throttled_usec", "usage_usec")
                              if isinstance(ce.get(k), int) and isinstance(cs.get(k), int)}
    result["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.iterations_out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["operation", "iteration", "ns"]); w.writerows(iter_rows)
    with open(a.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({k: result[k] for k in ("algorithm", "correctness_failures", "public_key_bytes", "artifact_bytes")}),
          [(o["operation"], round(o["median_ms"], 4), o["n_measured"]) for o in result["operations"]],
          result["cgroup_delta"], file=sys.stderr)


if __name__ == "__main__":
    main()
