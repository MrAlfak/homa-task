import paramiko

LOG = "/etc/dokploy/logs/homa-task-bot-qsnkoy/homa-task-bot-qsnkoy-2026-06-27:23:02:50.log"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("217.114.40.67", username="root", password="onznbxc1BccO1Ys1",
          timeout=30, banner_timeout=120, auth_timeout=120,
          look_for_keys=False, allow_agent=False)
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sftp = c.open_sftp()
with sftp.open(LOG) as f:
    print(f.read().decode(errors="replace"))
sftp.close()
c.close()
