#!/usr/bin/env bash
# Loads params.conf (repository root) into the shell scripts and changes to the
# repository root. Relative paths become absolute. A value already set in the
# environment takes precedence over params.conf.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
while IFS='=' read -r key value; do
  key="${key//[[:space:]]/}"
  [[ -z "$key" || "$key" == \#* ]] && continue
  [[ -z "${!key:-}" ]] && export "$key=$value"
done < "$ROOT/params.conf"
for key in RESULTS_DIR SCHEDULE_DIR ARCHIVE_DIR IMAGE_TAR; do
  [[ "${!key}" = /* ]] || export "$key=$ROOT/${!key}"
done
mkdir -p "$RESULTS_DIR" "$SCHEDULE_DIR" "$ARCHIVE_DIR"
