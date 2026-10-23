#!/usr/bin/env python3
"""Local static preview with byte-range video seeking, bound to loopback only."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import argparse,re,os

class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_range=None
        path=Path(self.translate_path(self.path))
        request_range=self.headers.get('Range')
        if not path.is_file() or not request_range:
            return super().send_head()
        size=path.stat().st_size
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',request_range)
        if not match or not any(match.groups()):
            self.send_error(416,'Invalid byte range');return None
        a,b=match.groups()
        start=int(a) if a else max(0,size-int(b))
        end=min(size-1,int(b)) if a and b else size-1
        if start>=size or start>end:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
        file=path.open('rb');file.seek(start);self.byte_range=(start,end)
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)))
        self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Content-Length',str(end-start+1));self.end_headers()
        return file
    def end_headers(self):
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-cache')
        super().end_headers()
    def copyfile(self,source,outputfile):
        try:
            if self.byte_range is None:return super().copyfile(source,outputfile)
            remaining=self.byte_range[1]-self.byte_range[0]+1
            while remaining:
                block=source.read(min(65536,remaining))
                if not block:break
                outputfile.write(block);remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8767);a=p.parse_args()
    os.chdir(Path(__file__).resolve().parent/'dist')
    print(f'Tidelight local preview: http://127.0.0.1:{a.port}/tidelight/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
