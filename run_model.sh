#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

usage() {
  echo "Usage: ./run_model.sh <model1|model2> [--times N]"
  echo "Examples:"
  echo "  ./run_model.sh model1"
  echo "  ./run_model.sh model2 --times 2"
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

MODEL="$1"
shift

TIMES=1
if [[ $# -gt 0 ]]; then
  if [[ "${1:-}" == "--times" && -n "${2:-}" ]]; then
    TIMES="$2"
    shift 2
  else
    usage
  fi
fi

if ! [[ "$TIMES" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: --times must be a positive integer."
  exit 1
fi

echo "==> Creating virtual environment (.venv) if needed"
python3 -m venv .venv

echo "==> Activating virtual environment"
source .venv/bin/activate

echo "==> Installing dependencies"
python3 -m pip install -q -r requirements.txt

case "$MODEL" in
  model1)
    TARGET="analysis/model1.py"
    ;;
  model2)
    TARGET="analysis/model2.py"
    ;;
  *)
    usage
    ;;
esac

for ((i=1; i<=TIMES; i++)); do
  echo "==> Run $i/$TIMES: $MODEL"
  python3 "$TARGET"
done

echo "==> Done."
