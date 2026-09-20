"""Create a private pg_dump; restore is NEW DATABASE ONLY (never --clean)."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import re
import subprocess
import psycopg
from psycopg import sql

p=argparse.ArgumentParser()
p.add_argument("--runtime",type=Path,default=Path.home()/"AIUsage")
p.add_argument("--restore",type=Path)
p.add_argument("--new-database")
a=p.parse_args()
pg=a.runtime/"bin/postgres-17.11/pgsql/bin"
password=(a.runtime/"secrets/admin").read_text().strip()
env=dict(os.environ,PGPASSWORD=password)
common=["-h","127.0.0.1","-p","15432","-U","ledger_admin"]
if a.restore:
    assert a.new_database and re.fullmatch(r"usage_restore_[a-z0-9_]+",a.new_database),"use a NEW usage_restore_* database"
    with psycopg.connect(host="127.0.0.1",port=15432,dbname="postgres",user="ledger_admin",password=password,autocommit=True) as c:
        assert not c.execute("SELECT 1 FROM pg_database WHERE datname=%s",(a.new_database,)).fetchone(),"existing database preserved"
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(a.new_database)))
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(a.new_database)))
    subprocess.run([str(pg/"pg_restore.exe"),*common,"--exit-on-error","-d",a.new_database,str(a.restore)],env=env,check=True)
    print("Restored into separate database. Live datasource unchanged.")
else:
    folder=a.runtime/"backups";folder.mkdir(exist_ok=True)
    target=folder/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+".dump")
    subprocess.run([str(pg/"pg_dump.exe"),*common,"-Fc","-f",str(target),"usage_ledger"],env=env,check=True)
    print("Private backup created: "+str(target))
