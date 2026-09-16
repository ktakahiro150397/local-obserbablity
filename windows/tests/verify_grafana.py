"""Read-only authenticated provisioning/query verification; prints no data."""
import base64
import json
from pathlib import Path
import urllib.request
import time

root=Path.home()/"AIUsage"
password=(root/"secrets/ui").read_text().strip()
headers={"Authorization":"Basic "+base64.b64encode(("owner:"+password).encode()).decode(),"Content-Type":"application/json"}
def call(path,data=None):
    req=urllib.request.Request("http://127.0.0.1:13002"+path,headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    return json.load(urllib.request.urlopen(req,timeout=15))

health=call("/api/datasources/uid/private-usage/health")
assert health["status"]=="OK",health.get("status")
print("PASS provisioned PostgreSQL datasource health")
for uid in ("hermes-requests-v1","windows-codex-v1"):
    dashboard=call("/api/dashboards/uid/"+uid)["dashboard"]
    for panel in dashboard["panels"]:
        query=dict(panel["targets"][0])
        for name in ("instance","model","user","thread"):
            query["rawSql"]=query["rawSql"].replace("${"+name+":sqlstring}","'__all'")
        query["rawSql"]=query["rawSql"].replace("${bucket:sqlstring}","'day'")
        query.update(intervalMs=60000,maxDataPoints=1000)
        result=call("/api/ds/query",{"queries":[query],"from":str(int((time.time()-7*86400)*1000)),"to":str(int(time.time()*1000))})
        assert all("error" not in r for r in result["results"].values()),"dashboard query failed"
    print("PASS provisioned dashboard and every Grafana query: "+uid)
try:
    urllib.request.urlopen("http://127.0.0.1:13002/api/dashboards/uid/hermes-requests-v1")
    raise AssertionError("anonymous dashboard access allowed")
except urllib.error.HTTPError as e:
    assert e.code==401
print("PASS anonymous dashboard access denied")
