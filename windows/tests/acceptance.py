"""Opt-in real PostgreSQL/Collector acceptance. Creates isolated test storage.

Never reads production rows or deletes a database/queue/backup. Requires the
portable runtime and psycopg/PyYAML; run from windows/tests or any directory.
"""
from pathlib import Path
import copy
import json
import os
import subprocess
import time
import urllib.request
import urllib.error
import uuid

import psycopg
from psycopg import sql
import yaml

ROOT = Path(os.environ.get("USAGE_RUNTIME_DIR", Path.home()/"AIUsage"))
HERE = Path(__file__).resolve().parents[1]
RUN = ROOT/"acceptance"/time.strftime("%Y%m%dT%H%M%S")
RUN.mkdir(parents=True)
DB = "usage_acceptance_" + uuid.uuid4().hex[:12]
CANARY = "SYNTHETIC_CONTENT_MUST_NEVER_PERSIST_9e485be9"
PASSWORD = (ROOT/"secrets/admin").read_text().strip()
CONNECT = dict(host="127.0.0.1",port=15432,user="ledger_admin",password=PASSWORD)
PROCESSES = []


def check(label, function, timeout=25):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            if function():
                print("PASS " + label, flush=True)
                return
        except (OSError, psycopg.Error):
            pass
        time.sleep(.2)
    raise AssertionError(label)


def launch(name, args, env):
    log = open(RUN/(name+".log"), "ab")
    p = subprocess.Popen(args, env=env, stdout=log, stderr=log,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
    PROCESSES.append(p)
    return p


def stop(p):
    if p.poll() is None:
        p.terminate()
        p.wait(timeout=10)


def request(path, data=None):
    encoded = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(path, data=encoded, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def attr(key,value):
    return {"key":key,"value":{"intValue":str(value)} if isinstance(value,int) else {"stringValue":value}}


def batch():
    spans=[]
    now=time.time_ns()
    for i,(user,thread) in enumerate([(u,t) for u in ("synthetic-a","synthetic-b")
                                    for t in ("synthetic-1","synthetic-2")],1):
        values={"usage.contract":"hermes.request.v1","usage.user.id":"discord:"+user,
                "usage.thread.id":thread,"usage.session.id":"synthetic-shared",
                "usage.turn.id":"turn-"+str(i),"usage.request.id":"request-"+str(i),
                "usage.tokens.input":100*i,"usage.tokens.output":i,
                "usage.tokens.cache_read":50,"usage.tokens.reasoning":1,
                "usage.outcome":"ok","gen_ai.request.model":"synthetic-model",
                "gen_ai.prompt":CANARY,"tool.arguments":CANARY,"error.message":CANARY}
        spans.append(dict(traceId=f"{i:032x}",spanId=f"{i:016x}",name="gen_ai.request",
            startTimeUnixNano=str(now-i*1000000000),endTimeUnixNano=str(now),
            attributes=[attr(k,v) for k,v in values.items()],
            events=[{"name":CANARY,"timeUnixNano":str(now),"attributes":[attr("body",CANARY)]}],
            status={"code":1,"message":CANARY}))
    return {"resourceSpans":[{"resource":{"attributes":[attr("service.name","backup-secretary-hermes"),
             attr("service.instance.id","synthetic-main"),attr("user.email",CANARY),attr("process.command",CANARY)]},
             "scopeSpans":[{"scope":{"name":CANARY,"version":CANARY,"attributes":[attr("secret",CANARY)]},"spans":spans}]}]}


def count():
    with psycopg.connect(dbname=DB,**CONNECT) as c:
        return c.execute("SELECT count(*) FROM usage.requests").fetchone()[0]


try:
    with psycopg.connect(dbname="postgres",autocommit=True,**CONNECT) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB)))
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO ledger_writer,ledger_grafana").format(sql.Identifier(DB)))
    with psycopg.connect(dbname=DB,**CONNECT) as c:
        c.execute((HERE/"001_requests.sql").read_text())
    config=yaml.safe_load((ROOT/"collector.yaml").read_text())
    config["receivers"]["otlp"]["protocols"]["http"]["endpoint"]="127.0.0.1:15318"
    if "grpc" in config["receivers"]["otlp"]["protocols"]:
        config["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"]="127.0.0.1:15317"
    config["exporters"]["otlphttp/usage"]["endpoint"]="http://127.0.0.1:15320"
    config["extensions"]["health_check"]["endpoint"]="127.0.0.1:15333"
    config["extensions"]["file_storage"]["directory"]=(RUN/"queue").as_posix()
    config["extensions"]["file_storage"]["compaction"]["directory"]=(RUN/"queue/compact").as_posix()
    config["service"]["telemetry"]["metrics"]["readers"][0]["pull"]["exporter"]["prometheus"]["port"]=15888
    (RUN/"collector.yaml").write_text(yaml.safe_dump(config),encoding="utf-8")
    env=dict(os.environ,PGHOST="127.0.0.1",PGPORT="15432",PGDATABASE=DB,
             PGPASSWORD_FILE=str(ROOT/"secrets/writer"),LISTEN_HOST="127.0.0.1",LISTEN_PORT="15320",GOMEMLIMIT="160MiB")
    command=[str(ROOT/"bin/otel/otelcol-contrib.exe"),"--config",str(RUN/"collector.yaml")]
    collector=launch("collector",command,env)
    check("isolated collector",lambda:request("http://127.0.0.1:15333")==200)
    payload=batch()
    assert request("http://127.0.0.1:15318/v1/traces",payload)==200
    check("offline durable queue",lambda:any(p.stat().st_size>10000 for p in (RUN/"queue").glob("*")))
    stop(collector)  # abrupt exit models an interrupted collector, not a clean drain
    for path in (RUN/"queue").rglob("*"):
        if path.is_file():
            assert CANARY.encode() not in path.read_bytes(),"content in durable queue"
    print("PASS pre-queue content removal",flush=True)
    import sys
    receiver=launch("receiver",[sys.executable,str(HERE/"receiver.py")],env)
    check("isolated receiver",lambda:request("http://127.0.0.1:15320/health")==200)
    collector=launch("collector",command,env)
    check("recovery after collector restart",lambda:count()==4)
    payload["resourceSpans"][0]["scopeSpans"][0]["spans"].reverse()
    assert request("http://127.0.0.1:15318/v1/traces",payload)==200
    time.sleep(1)
    assert count()==4
    with psycopg.connect(dbname=DB,**CONNECT) as c:
        actual=c.execute("SELECT user_id,sum(total_tokens),count(DISTINCT thread_id) FROM usage.requests GROUP BY user_id ORDER BY 1").fetchall()
        assert actual==[("discord:synthetic-a",303,2),("discord:synthetic-b",707,2)],actual
        assert c.execute("SELECT sum(total_tokens) FROM usage.requests").fetchone()[0]==1010
        serialized=c.execute("SELECT json_agg(t)::text FROM usage.requests t").fetchone()[0]
        assert CANARY not in serialized
        # Exercise every dashboard SQL query and all variable queries on real PG.
        for path in (HERE/"dashboards").glob("*.json"):
            d=json.loads(path.read_text(encoding="utf-8"))
            for v in d["templating"]["list"]:
                if v["type"]=="query": c.execute(v["query"]).fetchall()
            for p in d["panels"]:
                q=p["targets"][0]["rawSql"].replace("$__timeFilter(occurred_at)","occurred_at > now()-interval '7 days'")
                q=q.replace("$__timeFilter(observed_at)","observed_at > now()-interval '7 days'")
                for key in ("instance","model","user","thread"):
                    q=q.replace("${"+key+":sqlstring}","'__all'")
                q=q.replace("${bucket:sqlstring}","'day'")
                assert CANARY not in repr(c.execute(q).fetchall())
    print("PASS 2 users x 2 threads, replay, reverse order, SQL dashboards and DB privacy",flush=True)
    # Nullable usage, reported error usage, unrelated cumulative root discarded.
    spans=payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    extra=copy.deepcopy(spans[0]);extra.update(traceId="a"*32,spanId="a"*16)
    extra["attributes"]=[a for a in extra["attributes"] if not a["key"].startswith("usage.tokens.")]
    extra["attributes"]=[a for a in extra["attributes"] if a["key"]!="usage.outcome"]+[attr("usage.outcome","error")]
    root=copy.deepcopy(spans[0]);root.update(traceId="b"*32,spanId="b"*16,name="agent")
    spans[:]=[extra,root]
    request("http://127.0.0.1:15318/v1/traces",payload)
    check("missing usage preserved; root excluded",lambda:count()==5)
    with psycopg.connect(dbname=DB,**CONNECT) as c:
        assert c.execute("SELECT count(*) FROM usage.requests WHERE quality='missing' AND total_tokens IS NULL AND outcome='error'").fetchone()[0]==1
    # A full queue must reject (backpressure) rather than acknowledge data loss.
    stop(collector);stop(receiver)
    config["exporters"]["otlphttp/usage"]["sending_queue"]["queue_size"]=1
    config["extensions"]["file_storage"]["directory"]=(RUN/"capacity-queue").as_posix()
    config["extensions"]["file_storage"]["compaction"]["directory"]=(RUN/"capacity-queue/compact").as_posix()
    (RUN/"collector.yaml").write_text(yaml.safe_dump(config),encoding="utf-8")
    collector=launch("capacity",command,env)
    check("capacity test collector",lambda:request("http://127.0.0.1:15333")==200)
    try:
        request("http://127.0.0.1:15318/v1/traces",batch())
        raise AssertionError("full queue was acknowledged")
    except urllib.error.HTTPError as error:
        assert error.code in (429,503),error.code
    print("PASS bounded queue rejection (loss is possible at producer after retry limit)",flush=True)
    for p in PROCESSES:stop(p)
    # Restore only into a fresh isolated database. No existing database is dropped.
    pg=ROOT/"bin/postgres-17.11/pgsql/bin"
    dump=RUN/"synthetic.dump"
    pg_env=dict(os.environ,PGPASSWORD=PASSWORD)
    subprocess.run([str(pg/"pg_dump.exe"),"-h","127.0.0.1","-p","15432","-U","ledger_admin","-Fc","-f",str(dump),DB],env=pg_env,check=True)
    restore=DB+"_restore"
    with psycopg.connect(dbname="postgres",autocommit=True,**CONNECT) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restore)))
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(restore)))
    subprocess.run([str(pg/"pg_restore.exe"),"-h","127.0.0.1","-p","15432","-U","ledger_admin","--exit-on-error","-d",restore,str(dump)],env=pg_env,check=True)
    with psycopg.connect(dbname=restore,**CONNECT) as c:
        assert c.execute("SELECT count(*),sum(total_tokens) FROM usage.requests").fetchone()==(5,1010)
    for path in RUN.rglob("*"):
        if path.is_file(): assert CANARY.encode() not in path.read_bytes(),"content in runtime artifact"
    (RUN/"result.json").write_text(json.dumps({"passed":True,"database":DB,"restore":restore,"rows":5,"known_tokens":1010}))
    print("PASS backup/restore and all persisted artifacts content-free",flush=True)
finally:
    for p in PROCESSES:stop(p)
