from course.core import *

module(16, "Firewall and Hardening", """\
Principle: default DENY incoming, allow only what is needed, from where it is needed.  ALWAYS allow SSH BEFORE enabling a firewall on a remote server!
ufw:  ufw default deny incoming | ufw default allow outgoing | ufw allow from 192.168.56.0/24 to any port 22 proto tcp | ufw allow 80/tcp | ufw enable | ufw status numbered | ufw delete N
Allow a port only for one address:  ufw allow from 10.0.0.5 to any port 3306 proto tcp        Rate limit SSH:  ufw limit 22/tcp
nftables/iptables are the engines under ufw; firewall logs: journalctl -k | grep 'UFW BLOCK'
What is exposed?   ss -tlnp   (0.0.0.0:PORT or *:PORT = every interface;  127.0.0.1:PORT = this machine only)
In this module you PLAN firewalls as scripts which the trainer checks (we never enable a real firewall on your SSH VM).""", track="Infrastructure")

# ---------------------------------------------------------------- F1  exposure audit
def g_m16t1(x, r):
    ports = r.sample(range(20000, 40000), 4)
    spawn("fw-pub1", "--http", ports[0]); spawn("fw-pub2", "--http", ports[1])
    spawn("fw-loc1", "--http", ports[2], "--bind", "127.0.0.1"); spawn("fw-loc2", "--http", ports[3], "--bind", "127.0.0.1")
    return {"exposed_ports": (",".join(map(str, sorted(ports[:2]))), "ports of the fw-* helpers reachable from ALL interfaces, ascending, comma separated, no spaces"),
            "local_only_ports": (",".join(map(str, sorted(ports[2:]))), "ports of the fw-* helpers bound to 127.0.0.1 only, ascending, comma separated")}

answers_task("M16-T1", "Attack surface: what is exposed?", 
    lambda x: """\
SCENARIO   Four helper services (names start with fw-, see `ps aux`) listen on random TCP ports. Two are reachable from the network,
           two only from the machine itself. A firewall plan starts with this inventory.
USE        sudo ss -tlnp | grep labproc      (Local Address: 0.0.0.0:PORT or *:PORT = exposed,  127.0.0.1:PORT = local only)""",
    g_m16t1,
    hints=["ss -tlnp shows the process in the last column; the helper name is in `ps -fp PID`.", "pgrep -af 'fw-' lists the helpers with their ports in the arguments."],
    debrief="You cannot protect what you have not listed. Bind internal services to 127.0.0.1 and firewall the rest.")

# ---------------------------------------------------------------- F2  ufw plan (linted)
def s_m16t2(x):
    x.own(x.work)

def c_m16t2(x):
    f, q = x.work / "firewall.sh", []
    txt = f.read_text() if f.is_file() else ""
    cmds = [re.sub(r"^sudo\s+", "", l.strip()) for l in txt.splitlines() if re.match(r"^\s*(sudo\s+)?ufw\s", l)]
    def idx(rx):
        for i, c in enumerate(cmds):
            if re.search(rx, c): return i
        return None
    en = idx(r"^ufw\s+(--force\s+)?enable\b")
    ssh = idx(r"^ufw\s+allow\s+from\s+192\.168\.56\.0/24\s+to\s+any\s+port\s+22(\s+proto\s+tcp)?\s*$")
    q.append(R("script contains 'ufw ... enable'", en is not None))
    q.append(R("SSH is allowed ONLY from 192.168.56.0/24 (port 22)", ssh is not None))
    q.append(R("the SSH rule comes BEFORE 'ufw enable' (otherwise you lock yourself out!)", ssh is not None and en is not None and ssh < en))
    q.append(R("'ufw enable' is the LAST ufw command", en is not None and en == len(cmds) - 1))
    q.append(R("default deny incoming", idx(r"^ufw\s+default\s+deny\s+(incoming|in)\b") is not None))
    q.append(R("default allow outgoing", idx(r"^ufw\s+default\s+allow\s+(outgoing|out)\b") is not None))
    q.append(R("HTTP and HTTPS open to everybody (80/tcp and 443/tcp, or http/https)",
               idx(r"^ufw\s+allow\s+(80(/tcp)?|http)\s*$") is not None and idx(r"^ufw\s+allow\s+(443(/tcp)?|https)\s*$") is not None))
    q.append(R("MySQL 3306 allowed only from 10.0.0.5",
               idx(r"^ufw\s+allow\s+from\s+10\.0\.0\.5\s+to\s+any\s+port\s+3306(\s+proto\s+tcp)?\s*$") is not None and idx(r"^ufw\s+allow\s+(3306|mysql)(/tcp)?\s*$") is None))
    q.append(R("port 22 is NOT open to the whole world", idx(r"^ufw\s+allow\s+(22|ssh)(/tcp)?\s*$") is None and idx(r"^ufw\s+allow\s+from\s+any\s+to\s+any\s+port\s+22") is None))
    return q

add("M16-T2", "Write a safe ufw plan",
    lambda x: f"""\
SCENARIO   New production web+database server (remote, reachable only by SSH). Security policy:
             - incoming: DENY by default; outgoing: ALLOW by default
             - SSH (22/tcp) only from the admin network 192.168.56.0/24
             - HTTP (80) and HTTPS (443) for everybody
             - MySQL (3306/tcp) only from the application server 10.0.0.5
             - the firewall is switched on LAST (a wrong order locks you out of the server)
TASK       Write {x.work}/firewall.sh : one ufw command per line, in the correct ORDER, ending with 'ufw enable'.
           (The trainer only READS the script - it is never executed here.)
EXPECTED RESULT   A script you could run on a real server without losing access.""",
    s_m16t2, c_m16t2,
    hints=["ufw default deny incoming ; ufw default allow outgoing ; then the allow rules ; ufw enable at the very end", "ufw allow from 192.168.56.0/24 to any port 22 proto tcp"],
    debrief="Order matters: allow your own SSH access first, enable last. Restrict by source whenever you can.")

# ---------------------------------------------------------------- F3  firewall log reading
def g_m16t3(x, r):
    from collections import Counter, defaultdict
    srcs = [f"203.0.113.{r.randint(1, 250)}" for _ in range(6)] + [f"198.51.100.{r.randint(1, 250)}" for _ in range(4)]
    scanner = r.choice(srcs)
    lines, cnt, ports = [], Counter(), defaultdict(set)
    t = 9 * 3600
    for i in range(r.randint(250, 400)):
        t += r.randint(1, 30)
        s = r.choice(srcs)
        dpt = r.choice([22, 22, 22, 23, 80, 443, 3306, 3389])
        cnt[s] += 1; ports[s].add(dpt)
        lines.append(f"{time.strftime('%b %e %H:%M:%S', time.gmtime(t))} vm kernel: [UFW BLOCK] IN=eth0 OUT= SRC={s} DST=192.168.56.10 PROTO=TCP SPT={r.randint(1024,65000)} DPT={dpt}")
    for p in range(1000, 1040):                          # one host probes many ports
        cnt[scanner] += 1; ports[scanner].add(p)
        t += 1
        lines.append(f"{time.strftime('%b %e %H:%M:%S', time.gmtime(t))} vm kernel: [UFW BLOCK] IN=eth0 OUT= SRC={scanner} DST=192.168.56.10 PROTO=TCP SPT=40000 DPT={p}")
    r.shuffle(lines)
    pc = Counter(int(re.search(r"DPT=(\d+)", l).group(1)) for l in lines)
    top_port = pc.most_common(2)
    if top_port[0][1] == top_port[1][1] or cnt.most_common(2)[0][1] == cnt.most_common(2)[1][1]:
        return g_m16t3(x, r)
    put(x.work / "ufw.log", "\n".join(lines) + "\n")
    return {"top_blocked_source": (cnt.most_common(1)[0][0], "SRC address with the most blocked packets"),
            "top_blocked_port": (top_port[0][0], "destination port (DPT) blocked most often", "int"),
            "distinct_sources": (len(cnt), "number of different SRC addresses", "int"),
            "port_scanner": (scanner, "the SRC that probed the MOST DIFFERENT destination ports")}

answers_task("M16-T3", "Read the firewall log",
    lambda x: f"""\
SCENARIO   {x.work}/ufw.log holds blocked packets (lines with [UFW BLOCK] SRC=... DPT=...). Report to the security team.
HINT       grep -o 'SRC=[0-9.]*' | sort | uniq -c | sort -rn      a port scanner touches MANY different DPT values.""",
    g_m16t3,
    hints=["grep -o 'DPT=[0-9]*' ufw.log | sort | uniq -c | sort -rn | head -1", "for each SRC: grep \"SRC=$ip \" ufw.log | grep -o 'DPT=[0-9]*' | sort -u | wc -l"],
    debrief="Volume (top talker) and variety (many ports) tell nuisance from reconnaissance.")

compose("M16-X1", "BLOCK EXAM: firewall planning", "Inventory, plan, and log analysis for a new server.", ["M16-T1", "M16-T2", "M16-T3"])
