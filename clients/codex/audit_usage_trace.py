"""Run ONE non-sensitive ephemeral CLI turn; report schema, never raw telemetry.

No payload/log files are written. The HTTP sink exists only on localhost for
this child process, so already-running desktop sessions are unaffected.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import gzip
import json
import subprocess
import threading
import time
import sys
import os
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

rows=[]
class Sink(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get("Content-Length",0)))
        if self.headers.get("Content-Encoding")=="gzip": body=gzip.decompress(body)
        data=ExportTraceServiceRequest.FromString(body)
        for rs in data.resource_spans:
            service=next((a.value.string_value for a in rs.resource.attributes if a.key=="service.name"),"")
            for ss in rs.scope_spans:
                for s in ss.spans:
                    rows.append({"service":service,"span":s.name,"attributes":sorted(a.key for a in s.attributes),
                                 "events":len(s.events),"links":len(s.links)})
        self.send_response(200);self.send_header("Content-Length","0");self.end_headers()

server=HTTPServer(("127.0.0.1",15328),Sink)
threading.Thread(target=server.serve_forever,daemon=True).start()
cmd=[sys.argv[1],"exec","--ephemeral","--skip-git-repo-check","-c",'otel.exporter="none"',
     "-c",'otel.metrics_exporter="none"',"-c",'otel.log_user_prompt=false',
     "-c",'otel.trace_exporter={otlp-http={endpoint="http://127.0.0.1:15328/v1/traces",protocol="binary"}}',
     "Reply only OK. Do not use tools. This is a synthetic usage telemetry test."]
env=dict(os.environ)
# A CLI launched by the desktop inherits this value; leaving it set would
# incorrectly identify the CLI as Desktop. No global environment is changed.
env.pop("CODEX_INTERNAL_ORIGINATOR_OVERRIDE",None)
result=subprocess.run(cmd,capture_output=True,timeout=90,cwd=str(Path.home()),env=env,creationflags=subprocess.CREATE_NO_WINDOW)
time.sleep(1)
server.shutdown()
usage=[r for r in rows if r["span"] in ("handle_responses","session_task.turn")]
print(json.dumps({"exit_code":result.returncode,"span_count":len(rows),"usage_schema":usage},ensure_ascii=False))
if result.returncode or not rows:raise SystemExit(1)
