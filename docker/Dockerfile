# pqc-tier-bench image. Build ONCE on the M1 (linux/arm64), then docker save /
# docker load on the Raspberry Pi so that both hosts run byte-identical binaries.
#
#   docker build --platform linux/arm64 -t pqc-tier-bench:1.0 -f docker/Dockerfile .
#   docker save pqc-tier-bench:1.0 | gzip > pqc-tier-bench-1.0.tar.gz      # copy to Pi
#   docker load < pqc-tier-bench-1.0.tar.gz                                 # on the Pi
#
# Pinned components (record these in the paper):
#   python 3.12 (python:3.12-slim-bookworm), liboqs 0.16.0 (built from source,
#   HQC and BIKE enabled, OQS_DIST_BUILD=ON), liboqs-python 0.16.0.1,
#   cryptography 46.0.7
FROM python:3.12-slim-bookworm

ARG LIBOQS_TAG=0.16.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# liboqs C library, one fixed tag, one fixed set of build flags
RUN git clone --depth 1 --branch ${LIBOQS_TAG} https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs \
    && cmake -S /tmp/liboqs -B /tmp/liboqs/build -GNinja \
         -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_INSTALL_PREFIX=/usr/local \
         -DBUILD_SHARED_LIBS=ON \
         -DOQS_BUILD_ONLY_LIB=ON \
         -DOQS_DIST_BUILD=ON \
         -DOQS_USE_OPENSSL=OFF \
         -DOQS_ENABLE_KEM_HQC=ON \
         -DOQS_ENABLE_KEM_BIKE=ON \
    && ninja -C /tmp/liboqs/build install \
    && ldconfig \
    && (cd /tmp/liboqs && git rev-parse HEAD > /usr/local/liboqs-commit.txt) \
    && rm -rf /tmp/liboqs

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip freeze > /usr/local/pip-freeze.txt

COPY bench/bench.py /bench/bench.py
WORKDIR /bench

# self-check at build time: every algorithm of the study must be enabled
COPY bench/selfcheck.py /bench/selfcheck.py
RUN python /bench/selfcheck.py

ENTRYPOINT ["python", "/bench/bench.py"]
