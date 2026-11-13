"""Local test server: byte ranges (video seeking), wasm/mjs MIME types, and the same isolation headers the live site sends."""
import sys
from RangeHTTPServer import RangeRequestHandler
from http.server import ThreadingHTTPServer
class H(RangeRequestHandler):
    extensions_map = {**RangeRequestHandler.extensions_map, '.wasm': 'application/wasm', '.mjs': 'text/javascript', '.js': 'text/javascript', '.onnx': 'application/octet-stream', '.woff2': 'font/woff2'}
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin'); self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; style-src 'self'; img-src 'self' data: blob:; media-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        super().end_headers()
    def log_message(self, *a): pass
import os; os.chdir(sys.argv[1]); ThreadingHTTPServer(('127.0.0.1', int(sys.argv[2])), H).serve_forever()
