#!/usr/bin/env python3
"""Portable executable/font adapter around the unchanged original compositor."""
from pathlib import Path
import argparse, importlib.util, shutil, subprocess, sys, types

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--font', type=Path)
    parser.add_argument('--stills-only', action='store_true')
    args = parser.parse_args()
    if not args.ffmpeg and not args.stills_only: parser.error('Install FFmpeg or pass --ffmpeg PATH')
    if args.font is None:
        candidates = [Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        args.font = next((path for path in candidates if path.is_file()), None)
    if args.font is None or not args.font.is_file(): parser.error('Pass --font /path/to/font.ttf')
    spec = importlib.util.spec_from_file_location('tidelight_original_compositor', ROOT / 'cinematic-shot/compose_film.py')
    compositor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compositor)
    compositor.FONT = str(args.font)
    def command(cmd):
        # Redirect only this module's recorded macOS FFmpeg executable.
        return [args.ffmpeg if cmd[0] == '/opt/homebrew/bin/ffmpeg' else cmd[0], *cmd[1:]]
    compositor.subprocess = types.SimpleNamespace(
        run=lambda cmd, **kw: subprocess.run(command(cmd), **kw),
        Popen=lambda cmd, **kw: subprocess.Popen(command(cmd), **kw), PIPE=subprocess.PIPE)
    sys.argv = [str(ROOT / 'cinematic-shot/compose_film.py')] + (['--stills-only'] if args.stills_only else [])
    compositor.main()

if __name__ == '__main__': main()
