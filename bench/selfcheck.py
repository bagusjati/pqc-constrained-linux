"""Build-time self-check: every algorithm of the study must be enabled in this liboqs build."""
import oqs
k = set(oqs.get_enabled_kem_mechanisms()); s = set(oqs.get_enabled_sig_mechanisms())
need_k = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "FrodoKEM-640-AES", "BIKE-L1", "HQC-1"]
need_s = ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
slh = [("SLH_DSA_PURE_SHA2_128S", "SPHINCS+-SHA2-128s-simple"), ("SLH_DSA_PURE_SHA2_192S", "SPHINCS+-SHA2-192s-simple"),
       ("SLH_DSA_PURE_SHA2_256S", "SPHINCS+-SHA2-256s-simple")]
missing = [x for x in need_k if x not in k] + [x for x in need_s if x not in s] + [a for a, b in slh if a not in s and b not in s]
print("liboqs", oqs.oqs_version(), "liboqs-python", oqs.oqs_python_version())
assert not missing, f"missing algorithms: {missing}"
import cryptography; print("cryptography", cryptography.__version__)
print("all algorithms enabled")
