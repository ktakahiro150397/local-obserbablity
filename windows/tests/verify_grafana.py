"""Read-only authenticated provisioning/query verification; prints no data."""
import base64
import json
from pathlib import Path
import urllib.request
import urllib.error
import time

root=Path.home()/"AIUsage"
password=(root/"secrets/ui").read_text().strip()
headers={"Authorization":"Basic "+base64.b64encode(("owner:"+password).encode()).decode(),"Content-Type":"application/json"}
def call(path,data=None):
    req=urllib.request.Request("http://127.0.0.1:13002"+path,headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    return json.load(urllib.request.urlopen(req,timeout=15))


def sql_string(value):
    values=value if isinstance(value,list) else [value]
    return ','.join("'"+str(v).replace("'","''")+"'" for v in values)


def query_all(queries):
    return call("/api/ds/query",{"queries":queries,"from":str(int((time.time()-7*86400)*1000)),"to":str(int(time.time()*1000))})


health=call("/api/datasources/uid/private-usage/health")
assert health["status"]=="OK",health.get("status")
print("PASS provisioned PostgreSQL datasource health")
for uid in ("hermes-requests-v1","windows-codex-v1","hermes-usage-overview-v1"):
    dashboard=call("/api/dashboards/uid/"+uid)["dashboard"]
    variables=dashboard['templating']['list']
    defaults={}
    choices={}
    for variable in variables:
        name=variable['name']
        # Actual custom All value bypasses :sqlstring. Do not substitute a
        # hand-written quoted sentinel, which masked the browser's SQL error.
        defaults[name]=variable['allValue'] if variable.get('includeAll') else sql_string(variable['current']['value'])
        if variable['type']=='query':
            result=query_all([dict(refId='A',datasource=variable['datasource'],rawSql=variable['query'],rawQuery=True,format='table')])
            choices[name]=[v for frame in result['results']['A'].get('frames',[]) for v in frame['data']['values'][0] if v is not None]
    cases={'all':defaults,
           'single':{**defaults,**{k:sql_string(v[:1] or ['missing']) for k,v in choices.items()}},
           'multiple':{**defaults,**{k:sql_string(v[:2]+['not-present']) for k,v in choices.items()}},
           'quoted-no-match':{**defaults,**{k:sql_string("not'present") for k in choices}}}
    if 'bucket' in defaults:
        cases['hour']={**defaults,'bucket':sql_string('hour')}
    if 'scope' in defaults:
        for scope in ('all','system','unattributed'):
            cases['scope-'+scope]={**defaults,'scope':sql_string(scope)}
    for label,values in cases.items():
        queries=[]
        for panel in dashboard['panels']:
            for target in panel.get('targets',[]):
                query=dict(target)
                for name,value in values.items():
                    query['rawSql']=query['rawSql'].replace('${'+name+':sqlstring}',value)
                query.update(refId='P'+str(panel['id']),intervalMs=60000,maxDataPoints=1000)
                queries.append(query)
        try:
            result=query_all(queries)
        except urllib.error.HTTPError as error:
            raise AssertionError(f'{uid}: {label} query failed with HTTP {error.code}') from None
        assert all('error' not in r for r in result['results'].values()),f'{uid}: {label} query failed'
    print(f'PASS {uid}: every panel, variable query, and {len(cases)} filter cases (values withheld)')
try:
    urllib.request.urlopen("http://127.0.0.1:13002/api/dashboards/uid/hermes-requests-v1")
    raise AssertionError("anonymous dashboard access allowed")
except urllib.error.HTTPError as e:
    assert e.code==401
print("PASS anonymous dashboard access denied")
