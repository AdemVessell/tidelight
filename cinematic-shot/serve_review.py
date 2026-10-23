#!/usr/bin/env python3
"""Serve only this private film-review folder on loopback, with video ranges."""
from pathlib import Path
import importlib.util,functools
from http.server import ThreadingHTTPServer
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tidelight_range_preview',HERE.parent/'website/preview.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
handler=functools.partial(module.Handler,directory=str(HERE))
print('Private cinematic review: http://127.0.0.1:8768/review.html',flush=True)
ThreadingHTTPServer(('127.0.0.1',8768),handler).serve_forever()
