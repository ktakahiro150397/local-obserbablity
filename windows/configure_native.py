"""Configure only a new, owner-private portable Windows installation."""
from pathlib import Path
import os
import shutil
import yaml
import psycopg
from psycopg import sql

root = Path(os.environ["USAGE_RUNTIME_DIR"]).resolve()
here = Path(__file__).resolve().parent
for name in ("app", "queue", "logs", "grafana-data", "provisioning/datasources", "provisioning/dashboards"):
    (root/name).mkdir(parents=True,exist_ok=True)
for name in ("normalize.py", "receiver.py", "001_requests.sql"):
    shutil.copy2(here/name, root/"app"/name)
shutil.copytree(here/"dashboards", root/"app/dashboards",dirs_exist_ok=True)

collector=yaml.safe_load((here/"collector.yaml").read_text())
collector["receivers"]["otlp"]["protocols"]["http"]["endpoint"]="127.0.0.1:14318"
collector["receivers"]["otlp"]["protocols"]["grpc"]={"endpoint":"127.0.0.1:14317"}
collector["exporters"]["otlphttp/usage"]["endpoint"]="http://127.0.0.1:14320"
collector["extensions"]["file_storage"]["directory"]=(root/"queue").as_posix()
collector["extensions"]["file_storage"]["compaction"]["directory"]=(root/"queue/compact").as_posix()
collector["extensions"]["health_check"]["endpoint"]="127.0.0.1:14333"
collector["service"]["telemetry"]["metrics"]["readers"][0]["pull"]["exporter"]["prometheus"]={"host":"127.0.0.1","port":14888}
(root/"collector.yaml").write_text(yaml.safe_dump(collector,sort_keys=False),encoding="utf-8")
ds=yaml.safe_load((here/"grafana-datasources.yaml").read_text())
ds["datasources"][0]["url"]="127.0.0.1:15432"
ds["datasources"][0]["secureJsonData"]["password"]="$__file{"+(root/"secrets/grafana").as_posix()+"}"
(root/"provisioning/datasources/usage.yaml").write_text(yaml.safe_dump(ds,sort_keys=False),encoding="utf-8")
dash=yaml.safe_load((here/"grafana-dashboards.yaml").read_text())
dash["providers"][0]["options"]["path"]=(root/"app/dashboards").as_posix()
(root/"provisioning/dashboards/usage.yaml").write_text(yaml.safe_dump(dash,sort_keys=False),encoding="utf-8")
(root/"grafana.ini").write_text(f"""[server]
http_addr = 127.0.0.1
http_port = 13002
root_url = http://127.0.0.1:13002
[paths]
data = {(root/'grafana-data').as_posix()}
logs = {(root/'logs').as_posix()}
provisioning = {(root/'provisioning').as_posix()}
[security]
admin_user = owner
admin_password = $__file{{{(root/'secrets/ui').as_posix()}}}
disable_gravatar = true
[users]
allow_sign_up = false
[auth.anonymous]
enabled = false
[analytics]
reporting_enabled = false
check_for_updates = false
check_for_plugin_updates = false
[log]
level = error
[plugins]
preinstall_disabled = true
""",encoding="utf-8")

password=(root/"secrets/admin").read_text().strip()
with psycopg.connect(host="127.0.0.1",port=15432,dbname="postgres",user="ledger_admin",password=password,autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='usage_ledger'").fetchone():
        c.execute("CREATE DATABASE usage_ledger")
    for role,key in (("ledger_writer","writer"),("ledger_grafana","grafana")):
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,)).fetchone():
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role),sql.Literal((root/"secrets"/key).read_text().strip())))
    c.execute("REVOKE ALL ON DATABASE usage_ledger FROM PUBLIC")
    c.execute("GRANT CONNECT ON DATABASE usage_ledger TO ledger_writer,ledger_grafana")
with psycopg.connect(host="127.0.0.1",port=15432,dbname="usage_ledger",user="ledger_admin",password=password) as c:
    c.execute((here/"001_requests.sql").read_text())
print("native_config_and_schema_ready")
