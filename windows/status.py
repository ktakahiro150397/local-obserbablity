"""Owner-local aggregate health. Never prints identities, queries or secrets."""
import json
import os
from pathlib import Path
import urllib.request
import subprocess
import re
import sys
import psycopg

root=Path(os.environ.get("USAGE_RUNTIME_DIR",Path.home()/"AIUsage"))
out={}
for key,port in (("receiver",14320),("collector",14333),("grafana",13002)):
    try:
        endpoint="/api/health" if key=="grafana" else "/health" if key=="receiver" else "/"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{endpoint}",timeout=3) as r:
            out[key]=r.status==200
    except OSError:out[key]=False
try:
    with psycopg.connect(host="127.0.0.1",port=15432,dbname="usage_ledger",user="ledger_admin",
                        password=(root/"secrets/admin").read_text().strip(),connect_timeout=3) as c:
        out["ledger"]=dict(zip(("records","measurement_start","last_received","incomplete","bytes"),c.execute(
            "SELECT count(*),min(occurred_at),max(received_at),count(*) FILTER(WHERE quality!='reported'),pg_database_size(current_database()) FROM usage.requests").fetchone()))
except Exception:out["ledger"]={"healthy":False}
try:
    metrics=urllib.request.urlopen("http://127.0.0.1:14888/metrics",timeout=3).read().decode()
    # Keep only exporter queue/failure and filter-drop counters, not attributes.
    out["collector_counters"]=[s for s in metrics.splitlines() if s.startswith((
        "otelcol_exporter_queue_", "otelcol_exporter_enqueue_failed_", "otelcol_exporter_send_failed_", "otelcol_processor_filter_spans_filtered"))]
except OSError:out["collector_counters"]="unavailable"
out["queue_disk_bytes"]=sum(p.stat().st_size for p in (root/"queue").rglob("*") if p.is_file())
samples=[(key,out[key],None,None) for key in ("receiver","collector","grafana")]
connection=root/"connection.local.json"
if connection.exists():
    alias=json.loads(connection.read_text(encoding="utf-8-sig"))["SshHost"]
    if re.fullmatch(r"[A-Za-z0-9_.@-]+",alias):
        try:
            r=subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=3",alias,
                "curl --max-time 3 -fsS http://127.0.0.1:14889/metrics"],capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
            lines=[s for s in r.stdout.splitlines() if s.startswith(("otelcol_exporter_queue_","otelcol_exporter_enqueue_failed_","otelcol_exporter_send_failed_"))]
            out["forwarder_counters"]=lines
            size=sum(float(s.rsplit(' ',1)[-1]) for s in lines if s.startswith('otelcol_exporter_queue_size{'))
            failures=sum(float(s.rsplit(' ',1)[-1]) for s in lines if '_failed_' in s)
            samples.append(("forwarder",r.returncode==0,int(size),failures))
        except (OSError,subprocess.TimeoutExpired):samples.append(("forwarder",False,None,None))
if "--record" in sys.argv:
    try:
        with psycopg.connect(host="127.0.0.1",port=15432,dbname="usage_ledger",user="ledger_admin",
                            password=(root/"secrets/admin").read_text().strip(),connect_timeout=3) as c:
            if c.execute("SELECT pg_database_size(current_database())").fetchone()[0]<2*1024**3:
                c.cursor().executemany("INSERT INTO usage.pipeline_health(component,healthy,queue_bytes,failures) VALUES (%s,%s,%s,%s)",samples)
    except Exception:out["health_recorded"]=False
print(json.dumps(out,default=str,ensure_ascii=False,indent=2))
