import sys
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("217.114.40.67", username="root", password="onznbxc1BccO1Ys1",
          timeout=30, banner_timeout=120, auth_timeout=120,
          look_for_keys=False, allow_agent=False)
cmd = r"""
set +e
echo '-- start local registry --'
docker start registry
sleep 2
echo '-- registry health --'
curl -s -o /dev/null -w 'v2 status: %{http_code}\n' http://127.0.0.1:5000/v2/ || echo 'curl failed'
echo '-- tag + push --'
docker tag homa-task-bot:latest 127.0.0.1:5000/homa-task-bot:latest
docker push 127.0.0.1:5000/homa-task-bot:latest 2>&1 | tail -n 6
echo '-- catalog --'
curl -s http://127.0.0.1:5000/v2/_catalog
echo
echo PUSH_DONE
"""
_, o, e = c.exec_command(cmd, timeout=180)
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace").strip()
if err:
    print("[stderr]", err[:1000])
c.close()
