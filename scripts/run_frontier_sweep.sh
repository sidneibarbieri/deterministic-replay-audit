#!/usr/bin/env bash
#
# Collect the frontier 2x3 adversarial sweep (OpenAI + Anthropic, three prompt
# arms) under one fair configuration. Each arm is collected fresh in a single
# invocation, so its run_manifest wall-clock time is honest end-to-end.
#
# The script is interruption-safe: a relaunch keeps arms that already finished
# cleanly (72 runs, zero truncation) and re-collects any incomplete arm from
# scratch, so a killed run never leaves a half-cached arm with corrupted timing.
#
# Usage: scripts/run_frontier_sweep.sh [cache_root] [scenarios_json]

set -u

PYTHON="${PYTHON:-.venv/bin/python}"
CACHE_ROOT="${1:-/tmp/frontier_full}"
SCENARIOS="${2:-paper/data/adversarial_scenarios.json}"
RUNS=3
EXPECTED_RUNS=72  # 24 scenarios x 3 runs

arm_is_complete() {
  local arm_dir="$1"
  local manifest="${arm_dir}/run_manifest.json"
  [ -f "${manifest}" ] || return 1
  local run_count
  run_count=$(find "${arm_dir}" -name "*__run*.json" | wc -l | tr -d ' ')
  [ "${run_count}" = "${EXPECTED_RUNS}" ] || return 1
  local truncated
  truncated=$("${PYTHON}" -c "import json,sys; sys.stdout.write(str(json.load(open('${manifest}')).get('truncated_runs', 1)))")
  [ "${truncated}" = "0" ]
}

for provider in openai anthropic; do
  for arm in bare policy scaffold; do
    arm_dir=$(find "${CACHE_ROOT}/${provider}" -type d -name "${arm}" 2>/dev/null | head -1)
    if [ -n "${arm_dir}" ] && arm_is_complete "${arm_dir}"; then
      echo "SKIP ${provider}/${arm}: already complete (${EXPECTED_RUNS}/${EXPECTED_RUNS}, truncation 0)"
      continue
    fi
    [ -n "${arm_dir}" ] && { echo "WIPE incomplete ${provider}/${arm}"; rm -rf "${arm_dir}"; }
    echo "===== $(date +%H:%M:%S) RUN ${provider}/${arm} ====="
    "${PYTHON}" scripts/collect_advisor_runs.py \
      --provider "${provider}" --arm "${arm}" \
      --runs "${RUNS}" --live --max-calls 90 \
      --delay 1.5 --attempts 5 --backoff 5.0 \
      --temperature 1.0 \
      --scenarios "${SCENARIOS}" \
      --cache-root "${CACHE_ROOT}"
  done
done
echo "===== $(date +%H:%M:%S) ALL ARMS COMPLETE ====="
