"""Local web server for the Scalper 12 live dashboard.

The MT5 robot (mt5/Scalper12Indicators.mq5) writes Scalper12_status.json every second into the
MetaTrader "Common\\Files" folder. This server shows it at http://localhost:8765.

    python server.py                 # finds the MT5 Common\\Files folder by itself
    python server.py --file PATH     # or give the JSON path
    python server.py --lan           # also reachable from a phone on the same Wi-Fi
    python server.py --demo          # sample data, to preview the page without MT5

Python 3.8+, standard library only.
"""
import argparse, http.server, json, os, socket, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def default_status_path():
    candidates = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files", "Scalper12_status.json"))
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, ".wine", "drive_c", "users", os.environ.get("USER", ""), "AppData", "Roaming",
                     "MetaQuotes", "Terminal", "Common", "Files", "Scalper12_status.json"),
        os.path.join(home, "Library", "Application Support", "net.metaquotes.wine.metatrader5", "drive_c", "users",
                     "user", "AppData", "Roaming", "MetaQuotes", "Terminal", "Common", "Files", "Scalper12_status.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0] if candidates else "Scalper12_status.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="path of Scalper12_status.json")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="listen on the local network (phone access)")
    ap.add_argument("--demo", action="store_true", help="serve sample data")
    a = ap.parse_args()
    status = os.path.join(HERE, "sample_status.json") if a.demo else (a.file or default_status_path())

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path == "/status.json":
                try:
                    with open(status, "rb") as f:
                        body = f.read()
                    json.loads(body.decode("utf-8", "replace"))          # only serve complete JSON
                    self._send(200, body, "application/json; charset=utf-8")
                except (OSError, ValueError):
                    self._send(503, b'{"error":"robot data not available yet"}', "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args):
            pass

    host = "0.0.0.0" if a.lan else "127.0.0.1"
    srv = http.server.ThreadingHTTPServer((host, a.port), Handler)
    print(f"Données lues dans : {status}")
    print(f"Tableau de bord : http://localhost:{a.port}")
    if a.lan:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
            print(f"Depuis le téléphone (même Wi-Fi) : http://{s.getsockname()[0]}:{a.port}")
            s.close()
        except OSError:
            pass
    print("Ctrl+C pour arrêter.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
