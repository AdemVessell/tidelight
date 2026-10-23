#!/bin/zsh
# Repeat the fixed experiment in a new directory, preserving first-attempt evidence.
set -eu
inlet_root="$(cd -- "$(dirname -- "$0")" && pwd)"
inlet_run="$inlet_root/replays/$(date -u +%Y%m%dT%H%M%SZ)-$$"
inlet_python="${CINEMATIC_PYTHON:-/usr/bin/python3}"
inlet_blender="${CINEMATIC_BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
mkdir -p "$inlet_run/evaluation-private" "$inlet_run/targets" "$inlet_run/review/targets"
for inlet_file in scene.py recovery.py render_service.py evaluate.py PROTOCOL.md FREEZE.json TARGET_RECEIPT.json; do
  cp "$inlet_root/$inlet_file" "$inlet_run/$inlet_file"
done
cp "$inlet_root/evaluation-private/truth.json" "$inlet_run/evaluation-private/truth.json"
cp "$inlet_root/targets/"*.npy "$inlet_run/targets/"
cp "$inlet_root/review/targets/"*.png "$inlet_run/review/targets/"
cd "$inlet_run"
"$inlet_blender" -b --factory-startup --python render_service.py -- --queue-dir render-queue --scene scene.py > service.log 2>&1 &
inlet_service_pid=$!
trap 'kill -TERM "$inlet_service_pid" 2>/dev/null || true' EXIT INT TERM
set +e
"$inlet_python" recovery.py fit --targets targets --out fit --queue-dir render-queue --budget 70 --width 256 --height 144 --samples 16 --seed 13579 > fit.log 2>&1
inlet_fit_status=$?
set -e
if [[ "$inlet_fit_status" -ne 0 && "$inlet_fit_status" -ne 2 ]]; then
  printf 'Fit failed; retained logs at %s\n' "$inlet_run"
  exit "$inlet_fit_status"
fi
# Exit 2 includes budget exhaustion; evaluation separately determines threshold success.
"$inlet_python" evaluate.py evaluate --queue render-queue --width 256 --height 144 --samples 64 --seed 24680 > evaluation.log 2>&1
printf 'Replay results: %s/RESULTS.json\n' "$inlet_run"
