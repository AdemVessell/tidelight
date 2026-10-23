#!/usr/bin/env python3
"""Verify preserved experiment inputs and motion source; does not render."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    expected = dict(json.loads((ROOT / 'FREEZE.json').read_text())['source_hashes'])
    receipt = json.loads((ROOT / 'TARGET_RECEIPT.json').read_text())
    expected.update({'targets/' + name: value for name, value in receipt['target_hashes'].items()})
    expected['evaluation-private/truth.json'] = receipt['truth_commitment']
    expected['cinematic-shot/shot_scene.py'] = 'd2b8e6ed40a1d5dbcbc82b5fb73b7a26ffedce82b3e668b561f2d58a445a6069'
    failed = [name for name, digest in expected.items() if sha(ROOT / name) != digest]
    if failed: raise SystemExit('FAIL: changed frozen inputs: ' + ', '.join(failed))
    print(f'PASS: {len(expected)} preserved source/target/label hashes')

if __name__ == '__main__': main()
