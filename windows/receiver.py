"""Private Collector -> OTLP/JSON -> existing PostgreSQL ledger roles."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import time

from normalize import records

MAX_BODY = 1024 * 1024


def write(rows):
    import psycopg
    with psycopg.connect(host=os.getenv("PGHOST", "ledger"), port=int(os.getenv("PGPORT", "5432")),
                        dbname=os.getenv("PGDATABASE", "usage_ledger"),
                        user="ledger_writer", connect_timeout=3,
                        password=Path(os.environ["PGPASSWORD_FILE"]).read_text().strip()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_database_size(current_database())")
            if cur.fetchone()[0] >= int(os.getenv("USAGE_DATABASE_MAX_BYTES", str(2*1024**3))):
                raise RuntimeError("capacity_limit")
            for row in rows:
                columns = list(row)
                cur.execute("INSERT INTO usage.requests (" + ",".join(columns) + ") VALUES (" +
                            ",".join(["%s"] * len(columns)) + ") ON CONFLICT (event_key) DO NOTHING",
                            [row[k] for k in columns])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No request URLs, IDs, payloads or database exception strings.

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                write([])
                self.reply(200, {"healthy": True})
            except Exception:
                self.reply(503, {"healthy": False})
        else:
            self.reply(404, {})

    def do_POST(self):
        if self.path != "/v1/traces" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.reply(415, {})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.reply(413, {})
                return
            self.connection.settimeout(3)
            payload = json.loads(self.rfile.read(length))
            rows = list(records(payload))
        except (ValueError, TypeError, AttributeError, KeyError, TimeoutError):
            self.reply(400, {})
            return
        try:
            write(rows)
        except Exception:
            # Collector retries the entire batch; transaction and key make
            # an uncertain response safe. No acknowledgement before commit.
            print("ledger_write_failed", flush=True)
            self.reply(503, {})
            return
        self.reply(200, {})


if __name__ == "__main__":
    HTTPServer((os.getenv("LISTEN_HOST", "127.0.0.1"), int(os.getenv("LISTEN_PORT", "14320"))), Handler).serve_forever()
