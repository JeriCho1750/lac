from course.core import *
import ipaddress

# ------------------------------------------------------------------ 6. Networking
module(6, "Networking and DNS", """\
ip -br a (addresses)   ip route (default gateway)   cat /etc/resolv.conf (DNS servers)   ss -tulpn (listening ports + owner process)
ping -c3 HOST   curl -sI URL   curl -s -o /dev/null -w '%{http_code}\\n' URL   dig +short NAME   getent hosts NAME
Resolution order is set in /etc/nsswitch.conf ('hosts: files dns'): /etc/hosts is read FIRST, the first matching line wins.
Troubleshooting ladder: link/IP (ip a) -> gateway (ping) -> DNS (dig/getent) -> port (ss, curl) -> app logs.""", track="Foundation")

def net_truth():
    gw = dev = ip = ns = None
    m = re.search(r"default via (\S+) dev (\S+)", sh("ip -4 route show default")[1])
    if m:
        gw, dev = m.groups()
        m2 = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", sh(f"ip -4 -o addr show dev {dev}")[1])
        ip = m2.group(1) if m2 else None
    try:
        m3 = re.search(r"^nameserver\s+(\S+)", Path("/etc/resolv.conf").read_text(), re.M)
        ns = m3.group(1) if m3 else None
    except OSError:
        pass
    ssh = set()
    for ln in sh("ss -tlnpH")[1].splitlines():
        if "sshd" in ln:
            ssh.add(ln.split()[3].rsplit(":", 1)[-1])
    return gw, ip, ns, ssh

def s_m06t1(x):
    port = random.randint(20000, 40000)
    pid = spawn("demo-listener", "--http", port)
    x.secret = {"port": port, "pid": pid}
    x.own(x.work)

def c_m06t1(x):
    q, a = [], answers(x)
    gw, ip, ns, ssh = net_truth()
    for key, val, lab in (("gateway", gw, "default gateway"), ("primary_ip", ip, "primary IPv4 address"), ("dns_server", ns, "first DNS server")):
        if val is None:
            q.append(R(f"{lab} (not available in this VM - skipped)", True))
        else:
            chk(q, a, key, val, lab)
    chk(q, a, "listener_port", x.secret["port"], "TCP port of demo-listener", "int")
    chk(q, a, "listener_pid", proc("demo-listener").pid, "PID of demo-listener", "int")
    got = (a or {}).get("ssh_port")
    q.append(R("SSH daemon port", got in ssh if ssh else got is not None, f"you wrote {got!r}"))
    code, _ = http(f"http://127.0.0.1:{x.secret['port']}/")
    chk(q, a, "http_status", code, "HTTP status code returned by the listener", "int")
    return q

add("M06-T1", "Network inventory of a server",
    lambda x: f"""\
SCENARIO   You take over an unknown server. Document its network identity before touching anything.
TASK       Create {x.work}/answers.txt with these lines (key=value):
    primary_ip=<IPv4 address (no /mask) of the interface that carries the default route>
    gateway=<default gateway IP>
    dns_server=<first 'nameserver' in /etc/resolv.conf>
    ssh_port=<TCP port the SSH daemon listens on>
    listener_port=<TCP port opened by the process named demo-listener (random!)>
    listener_pid=<PID of that process>
    http_status=<HTTP status code you get from  curl http://127.0.0.1:LISTENER_PORT/ >
USE   ip, ss -tulpn, cat /etc/resolv.conf, curl -s -o /dev/null -w '%{{http_code}}' URL
EXPECTED RESULT   Seven correct lines.""",
    s_m06t1, c_m06t1,
    hints=["ip route  -> 'default via GATEWAY dev IFACE'; ip -br a shows the IPs.", "sudo ss -tulpn | grep -E 'sshd|labproc' shows ports with PIDs."],
    debrief="You now know addresses, routes, DNS and listening services - step one of every network investigation.")

def s_m06t2(x):
    port = random.randint(20000, 40000)
    spawn("lab-app", "--http", port)
    with open("/etc/hosts", "a") as f:
        f.write("10.255.255.1 lab-app.internal # LAB wrong address\n127.0.0.1 lab-app.internal # LAB\n")
    x.secret = {"port": port}

def c_m06t2(x):
    q, p = [], x.secret["port"]
    def res(n):
        out = sh(f"getent hosts {n}")[1].split()
        return out[0] if out else None
    q.append(R("lab-app.internal resolves to 127.0.0.1", res("lab-app.internal") == "127.0.0.1", f"now {res('lab-app.internal')}"))
    q.append(R("lab-db.internal resolves to 127.0.0.1", res("lab-db.internal") == "127.0.0.1", f"now {res('lab-db.internal')}"))
    code, body = http(f"http://lab-app.internal:{p}/", 5)
    q.append(R(f"curl http://lab-app.internal:{p}/ returns LAB-OK", code == 200 and "LAB-OK" in body, f"status {code}"))
    hosts = Path("/etc/hosts").read_text()
    q.append(R("/etc/hosts still contains the localhost entry", re.search(r"^127\.0\.0\.1\s+localhost", hosts, re.M) is not None))
    return q

add("M06-T2", "Name resolution trouble (/etc/hosts)",
    lambda x: f"""\
INCIDENT #006
  The internal app is available at  http://lab-app.internal:{x.secret['port']}/  but users get timeouts.
  It must live on THIS server (127.0.0.1). Also a new name lab-db.internal must point to 127.0.0.1.
TASK
  1. Reproduce:  curl -m 3 http://lab-app.internal:{x.secret['port']}/      getent hosts lab-app.internal
  2. Find the cause (hint: how does the system choose between several lines? which file is read first?)
  3. Make a backup:  cp /etc/hosts /etc/hosts.bak   then fix /etc/hosts. Keep the localhost lines!
  4. Verify with getent hosts and curl.
EXPECTED RESULT   Both names resolve to 127.0.0.1 and curl prints LAB-OK.""",
    s_m06t2, c_m06t2,
    hints=["cat /etc/hosts - are there two lines for the same name? The first one wins.", "Remove the wrong line (10.255.255.1 ...), add: 127.0.0.1 lab-db.internal"],
    debrief="/etc/hosts overrides DNS. Always back up a config before editing and test after.")

# ---------------------------------------------------------------- M06-T3  port conflict
def s_m06t3(x):
    port = random.randint(20000, 40000)
    x.secret = {"port": port, "old": spawn("old-listener", "--http", port), "other": spawn("other-listener", "--http", port + 1)}
    mk_service("lab-newweb", None, exec_start=f"/usr/bin/python3 {BIN}/labproc.py newweb --http {port}", restart="on-failure",
               desc="New web frontend", start=True, no_limit=True)

def c_m06t3(x):
    q, p = [], x.secret["port"]
    old, oth = proc("old-listener"), proc("other-listener")
    q.append(R("old-listener stopped with SIGTERM (clean)", not old.alive and "TERM" in old.sigs))
    if not old.alive and "TERM" not in old.sigs:
        x.error("old-listener was SIGKILLed - SIGTERM is the polite way")
    if not oth.alive:
        x.error("other-listener (unrelated, port+1) was killed")
    q.append(R("other-listener still running", oth.alive))
    code, body = http(f"http://127.0.0.1:{p}/")
    q.append(R(f"lab-newweb now serves port {p} (answer contains 'LAB-OK newweb')", code == 200 and "newweb" in body, f"status {code} {body[:30]}"))
    s = svc("lab-newweb.service")
    q.append(R("lab-newweb is active and enabled", s.get("ActiveState") == "active" and s.get("UnitFileState") == "enabled"))
    return q

add("M06-T3", "Address already in use",
    lambda x: f"""\
INCIDENT   Service lab-newweb must listen on TCP port {x.secret['port']} but keeps failing and restarting.
           Two helper processes exist: old-listener (an obsolete test server, DISPOSABLE) and other-listener (unrelated: LEAVE IT).
TASK
  1. systemctl status lab-newweb ; journalctl -u lab-newweb -n 15 --no-pager   -> find the exact error.
  2. Who owns the port?   sudo ss -tlnp | grep {x.secret['port']}      (note PID + name)
  3. Stop the OLD owner politely (SIGTERM, by PID). Do not touch other-listener.
  4. Make sure lab-newweb is running (it may restart itself) and enabled at boot; test with curl http://127.0.0.1:{x.secret['port']}/
EXPECTED RESULT   The new service owns the port, the old process is gone, the unrelated one still runs.""",
    s_m06t3, c_m06t3,
    hints=["'Address already in use' = another process already bound that port.", "ss -tlnp | grep PORT prints users:((\"python3\",pid=NNN,...)); then kill NNN", "systemctl enable lab-newweb ; systemctl restart lab-newweb"],
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="Find the owner (ss -tlnp), decide, stop the right process, restart the service - never kill blindly.")

# ---------------------------------------------------------------- M06-T4  subnet maths
def g_m06t4(x, r):
    a = ipaddress.ip_interface(f"10.{r.randint(0,200)}.{r.randint(0,250)}.{r.randint(1,250)}/{r.randint(24,28)}")
    b = ipaddress.ip_interface(f"172.16.{r.randint(0,250)}.{r.randint(1,250)}/{r.randint(22,27)}")
    base = ipaddress.ip_network(a.network)
    c = ipaddress.ip_interface(f"{a.ip}/{a.network.prefixlen}")
    same = r.random() < 0.5
    d_ip = ipaddress.ip_address(int(base.network_address) + r.randint(1, base.num_addresses - 2)) if same else \
        ipaddress.ip_address(int(base.broadcast_address) + r.randint(5, 20))
    put(x.work / "hosts.txt", f"A {a}\nB {b}\nC {a.ip}/{a.network.prefixlen}\nD {d_ip}/{a.network.prefixlen}\n")
    return {"network_a": (str(a.network), "network address of A in CIDR form, e.g. 10.1.2.0/24"),
            "broadcast_a": (str(a.network.broadcast_address), "broadcast address of A"),
            "usable_hosts_b": (b.network.num_addresses - 2, "number of USABLE host addresses in B's network", "int"),
            "c_d_same_subnet": ("yes" if ipaddress.ip_interface(f"{d_ip}/{a.network.prefixlen}").network == a.network else "no", "do C and D share a subnet? yes/no")}

answers_task("M06-T4", "Subnet arithmetic (CIDR)",
    lambda x: f"""\
SCENARIO   Four interfaces are listed in {x.work}/hosts.txt as  NAME ADDRESS/PREFIX.  Work out the facts a network admin needs.
USE        ipcalc (apt install ipcalc) or  python3 -c "import ipaddress; n=ipaddress.ip_interface('10.1.2.77/26'); print(n.network, n.network.broadcast_address, n.network.num_addresses)"
NOTE       usable hosts = addresses in the network minus network address minus broadcast address.""",
    g_m06t4,
    hints=["network address = the IP with all host bits set to 0; broadcast = all host bits set to 1.", "usable hosts = 2^(32-prefix) - 2"],
    debrief="Subnet maths decides whether two machines can talk directly or need a router.")

compose("M06-X1", "BLOCK EXAM: networking", "Document the network, repair name resolution and a port clash.", ["M06-T1", "M06-T2", "M06-T3", "M06-T4"])
