"""Remove only this owner's stale Unix endpoint, never telemetry/data files.

OpenSSH client StreamLocalBindUnlink does not configure the remote sshd. Do not
change global sshd policy merely to recover our own dedicated socket.
"""
import errno
import os
from pathlib import Path
import socket
import stat
import sys

expected=Path.home()/".local/state/ai-usage/socket/otlp.sock"
path=Path(sys.argv[1]) if len(sys.argv)>1 else expected
assert path==expected and path.parent.resolve()==expected.parent,"unexpected socket path"
try:
    info=path.lstat()
except FileNotFoundError:
    print("socket_ready")
    raise SystemExit(0)
assert stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid(),"not the owner's Unix socket"
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
    probe.settimeout(1)
    try:
        probe.connect(str(path))
    except OSError as e:
        if e.errno!=errno.ECONNREFUSED:raise
    else:
        print("socket_active; preserved")
        raise SystemExit(3)
# Check again before unlink; an active replacement must not be removed.
current=path.lstat()
assert (current.st_ino,current.st_mtime_ns)==(info.st_ino,info.st_mtime_ns),"socket changed during probe"
path.unlink()
print("stale_socket_replaced; data_untouched")
