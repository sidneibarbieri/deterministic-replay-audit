#!/usr/bin/env bash
# One-command local runner.

set -euo pipefail

exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/start.sh"
