"""params.py - loads the global parameters of params.conf (repository root).

Relative paths resolve from the repository root. A value set in the
environment takes precedence over params.conf.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    cfg = {}
    with open(os.path.join(ROOT, "params.conf")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip()
    for key in cfg:
        cfg[key] = os.environ.get(key, cfg[key])
    return cfg


def path(value):
    return value if os.path.isabs(value) else os.path.join(ROOT, value)


CFG = load()
IMAGE = CFG["IMAGE"]
SEED = int(CFG["SEED"])
RESULTS_DIR = path(CFG["RESULTS_DIR"])
SCHEDULE_DIR = path(CFG["SCHEDULE_DIR"])
ARCHIVE_DIR = path(CFG["ARCHIVE_DIR"])
