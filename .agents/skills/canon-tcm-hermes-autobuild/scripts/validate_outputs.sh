#!/usr/bin/env bash
set -euo pipefail
canon validate --run-id "${1:-run001}"
