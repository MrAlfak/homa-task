import sys
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("217.114.40.67", username="root", password="onznbxc1BccO1Ys1",
          timeout=30, banner_timeout=120, auth_timeout=120,
          look_for_keys=False, allow_agent=False)
cmd = r"""
echo '-- existing registry container inspect --'
docker inspect registry --format 'Image={{.Config.Image}} | Cmd={{.Config.Cmd}} | Ports={{.HostConfig.PortBindings}} | RestartPolicy={{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || echo 'no registry container'
echo '-- is it dokploy-managed? labels --'
docker inspect registry --format '{{json .Config.Labels}}' 2>/dev/null || true
echo '-- insecure registries --'
docker info --format '{{.RegistryConfig.InsecureRegistryCIDRs}}' 2>/dev/null
"""
_, o, e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace").strip()
if err:
    print("[stderr]", err[:800])
c.close()
