#!/usr/bin/env python3
import time
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ACTIVE_WORKERS = 0
LOCK = threading.Lock()
TOTAL_PROCESSED = 0

class BackendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        global ACTIVE_WORKERS, TOTAL_PROCESSED
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")

        with LOCK:
            ACTIVE_WORKERS += 1
            current = ACTIVE_WORKERS
        
        try:
            # Simulate 15ms of backend DB/CPU processing (exposes Phantom Stream exhaustion)
            time.sleep(0.015)
            body = f'{{"status":"ok","active_workers":{current}}}\n'.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            with LOCK:
                ACTIVE_WORKERS -= 1
                TOTAL_PROCESSED += 1
                if TOTAL_PROCESSED % 100 == 0:
                    print(f"[BACKEND] Processed={TOTAL_PROCESSED} ActiveWorkers={ACTIVE_WORKERS}", flush=True)

    def log_message(self, format, *args):
        # Suppressing BaseHTTPRequestHandler's call of log_message so only [BACKEND] logs are seen
        pass

if __name__=="__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), BackendHandler)
    print("[BACKEND] Listening on 0.0.0.0:8080", flush=True)
    server.serve_forever()
