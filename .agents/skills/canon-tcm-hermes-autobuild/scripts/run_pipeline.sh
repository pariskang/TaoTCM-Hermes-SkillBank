#!/usr/bin/env bash
set -euo pipefail
canon all --input "${1:-data/raw/data.xlsx}" --run-id "${2:-run001}"
