#!/usr/bin/env python3
"""Download published films/scenes without putting generated binaries in Git."""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile, urllib.request

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def verified(path, asset):
    return path.stat().st_size == asset['bytes'] and digest(path) == asset['sha256']

def install(asset):
    root = ROOT.resolve()
    destinations = [(root / name).resolve() for name in asset['destinations']]
    if any(root not in path.parents for path in destinations):
        raise ValueError('Asset destination escapes the repository')
    available = None
    for path in destinations:
        if path.exists():
            if not verified(path, asset):
                raise ValueError(f'Refusing to replace changed file: {path.relative_to(root)}. Move it aside first.')
            available = path
    missing = [path for path in destinations if not path.exists()]
    if not missing:
        print('Verified:', destinations[0].relative_to(root), flush=True)
        return
    with tempfile.TemporaryDirectory(prefix='tidelight-download-') as folder:
        downloaded = Path(folder) / 'asset'
        if available is None:
            print('Downloading:', asset['url'], flush=True)
            curl = shutil.which('curl')
            if curl:
                subprocess.run([curl, '--fail', '--location', '--silent', '--show-error',
                    '--max-time', '180', '--retry', '2', '--retry-delay', '1',
                    '--output', str(downloaded), asset['url']], check=True)
            else:
                with urllib.request.urlopen(asset['url'], timeout=180) as response, downloaded.open('wb') as out:
                    shutil.copyfileobj(response, out)
            if not verified(downloaded, asset):
                raise ValueError(f'Size or SHA-256 mismatch: {asset["url"]}')
            available = downloaded
        for path in missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.tidelight-', delete=False) as f:
                temporary = Path(f.name)
            try:
                shutil.copyfile(available, temporary)
                if not verified(temporary, asset): raise ValueError('Copied asset checksum mismatch')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    print('Installed:', ', '.join(str(p.relative_to(root)) for p in missing), flush=True)

def main():
    for asset in json.loads((ROOT / 'assets.json').read_text())['assets']: install(asset)
    print('All published assets verified.')

if __name__ == '__main__': main()
