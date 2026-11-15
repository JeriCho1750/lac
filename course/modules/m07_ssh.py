from course.core import *

# ------------------------------------------------------------------ 7. SSH
module(7, "SSH and Server Security", """\
ssh-keygen -t ed25519 -f KEY -N ""    ssh -i KEY -p PORT user@host    ssh -o BatchMode=yes ...
Server: ~/.ssh = 700, ~/.ssh/authorized_keys = 600, owned by that user (StrictModes refuses otherwise).
sshd_config: PermitRootLogin no | PasswordAuthentication no | PubkeyAuthentication yes | AllowUsers NAME | MaxAuthTries 3
sshd -t -f FILE (syntax test)    sshd -T -f FILE (effective settings)    systemctl restart|reload SERVICE
ALWAYS test a new sshd config with a SECOND open session before closing the first one.
Log analysis: grep 'Failed password' LOG | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head""", track="Foundation")

def s_m07t1(x):
    if not have("sshd"):
        ensure_pkgs("openssh-server")
    sh("useradd -m -s /bin/bash lab_ssh && usermod -p '*' lab_ssh")
    d = LAB / "sshd"
    d.mkdir(parents=True, exist_ok=True)
    sh(f"ssh-keygen -q -t ed25519 -N '' -f {d}/ssh_host_ed25519_key")
    put(d / "sshd_config", f"""Port 2222
ListenAddress 127.0.0.1
HostKey {d}/ssh_host_ed25519_key
PidFile {d}/sshd.pid
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication no
MaxAuthTries 10
X11Forwarding yes
StrictModes yes
""")
    put("/etc/systemd/system/lab-sshd.service", f"""[Unit]
Description=Lab practice SSH daemon (port 2222)

[Service]
ExecStartPre=/bin/mkdir -p /run/sshd
ExecStart=/usr/sbin/sshd -D -e -f {d}/sshd_config
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
""")
    sh("systemctl daemon-reload; systemctl start lab-sshd")
    x.own(x.work)

def c_m07t1(x):
    q, cfg, key = [], LAB / "sshd/sshd_config", x.work / "lab_key"
    rc, out = sh(f"sshd -t -f {cfg}")
    q.append(R("sshd -t: configuration syntax is valid", rc == 0, out[:100]))
    rc, out = sh(f"sshd -T -f {cfg}")
    eff = {}
    for l in out.splitlines():
        k, _, v = l.partition(" ")
        eff[k] = v
    q.append(R("PermitRootLogin no", eff.get("permitrootlogin") == "no"))
    q.append(R("PasswordAuthentication no", eff.get("passwordauthentication") == "no"))
    q.append(R("PubkeyAuthentication yes", eff.get("pubkeyauthentication") == "yes"))
    q.append(R("AllowUsers lab_ssh (only)", eff.get("allowusers", "").split() == ["lab_ssh"]))
    q.append(R("MaxAuthTries <= 3", eff.get("maxauthtries", "99").isdigit() and int(eff["maxauthtries"]) <= 3))
    q.append(R("X11Forwarding no", eff.get("x11forwarding") == "no"))
    q.append(R("lab-sshd service is active", svc("lab-sshd.service").get("ActiveState") == "active"))
    opts = "-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 -p 2222"
    runas = None if x.student == "root" else x.student
    rc, out = sh(f"ssh -i {key} -o IdentitiesOnly=yes {opts} lab_ssh@127.0.0.1 whoami", user=runas) if key.exists() else (1, "key file missing")
    q.append(R("key login as lab_ssh works on port 2222", rc == 0 and out.strip().endswith("lab_ssh"), out[-120:]))
    rc, out = sh(f"ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no {opts} lab_ssh@127.0.0.1 true")
    q.append(R("RUNNING daemon refuses passwords (config really reloaded)", "(publickey)" in out, out[-100:]))
    return q

add("M07-T1", "Harden an SSH daemon (safe practice instance)",
    lambda x: f"""\
SCENARIO
  A practice SSH daemon runs as service lab-sshd on 127.0.0.1:2222 with config {LAB}/sshd/sshd_config
  (your REAL ssh service is not involved - do not touch /etc/ssh/sshd_config or restart ssh.service).
  User lab_ssh exists (no password). The config is insecure and key login is broken.
TASK
  1. As your normal user generate a key WITHOUT passphrase:  ssh-keygen -t ed25519 -f {x.work}/lab_key -N ""
  2. Install the PUBLIC key for lab_ssh: /home/lab_ssh/.ssh/authorized_keys
     with correct ownership (lab_ssh) and modes (.ssh = 700, file = 600).
  3. Edit {LAB}/sshd/sshd_config so that:  root login is forbidden, password login is disabled,
     public-key login is enabled, ONLY user lab_ssh is allowed, MaxAuthTries is 3, X11 forwarding is off.
  4. Validate with  sshd -t -f ...  and see the effective values with  sshd -T -f ... | grep -E 'root|password|pubkey|allow'
  5. Reload/restart lab-sshd (systemctl restart lab-sshd) and test:
       ssh -i {x.work}/lab_key -p 2222 lab_ssh@127.0.0.1 whoami
EXPECTED RESULT   Key login works, passwords and root are refused, the daemon runs the NEW config.""",
    s_m07t1, c_m07t1,
    hints=["Public key goes into the file as one line (cat lab_key.pub | sudo tee -a ...). Then chown -R lab_ssh:lab_ssh /home/lab_ssh/.ssh; chmod 700 .ssh; chmod 600 authorized_keys.",
           "journalctl -u lab-sshd -n 30 shows why a login was rejected (wrong permissions, user not allowed...).",
           "A change in the config file has NO effect until you restart/reload the service."],
    bad=[(r"/etc/ssh/sshd_config", "you touched the REAL sshd config - this task is only about the lab daemon"),
         (r"systemctl\s+(restart|stop|reload|disable)\s+ssh(d)?(\.service)?(\s|$)", "you restarted/stopped the REAL ssh service - dangerous on a remote VM!")],
    debrief="Key-only, no root, allow-list, validate with sshd -t, test in a second session. Same procedure on a real server.")

def s_m07t2(x):
    r = random.Random()
    A, B, C, L = "203.0.113.5", "198.51.100.77", "192.0.2.9", "198.51.100.7"
    na, nb, nc = r.randint(150, 250), r.randint(40, 80), r.randint(5, 15)
    users = ["admin", "test", "oracle", "ubuntu", "git", "postgres", "pi", "ftp", "guest", "root"]
    invalid, ev = set(), []
    base = time.mktime((2025, 3, 3, 6, 0, 0, 0, 0, -1))
    def fail(ip, t, forced=None):
        u = forced or r.choice(users)
        port = r.randint(1024, 65000)
        if u in ("root", "deploy"):
            ev.append((t, f"Failed password for {u} from {ip} port {port} ssh2"))
        else:
            invalid.add(u)
            ev.append((t, f"Failed password for invalid user {u} from {ip} port {port} ssh2"))
    for _ in range(na): fail(A, base + r.randint(0, 10000))
    for _ in range(nc): fail(C, base + r.randint(0, 20000))
    tb = base + 14400
    for i in range(nb):
        fail(B, tb + i * 20, "deploy")
    ev.append((tb + nb * 20 + 5, f"Accepted password for deploy from {B} port 50222 ssh2"))
    for i in range(6):
        ev.append((base + r.randint(0, 20000), f"Accepted publickey for maria from {L} port {r.randint(1024,65000)} ssh2: ED25519 SHA256:abc"))
    ev.sort()
    lines = [f"{time.strftime('%b %e %H:%M:%S', time.localtime(t))} vm sshd[{r.randint(1000,9999)}]: {m}" for t, m in ev]
    put(x.work / "auth.log", "\n".join(lines) + "\n")
    x.secret = {"top": A, "n": na, "ip": B, "user": "deploy", "invalid": len(invalid)}
    x.own(x.work)

def c_m07t2(x):
    q, a, s = [], answers(x), x.secret
    chk(q, a, "top_ip", s["top"], "IP with the most failed logins")
    chk(q, a, "top_ip_failures", s["n"], "number of failed logins from that IP", "int")
    chk(q, a, "compromised_user", s["user"], "account that was successfully logged into after a brute force")
    chk(q, a, "compromised_ip", s["ip"], "IP that got in after many failures")
    chk(q, a, "distinct_invalid_users", s["invalid"], "number of different 'invalid user' names tried", "int")
    return q

add("M07-T2", "Brute-force analysis of auth.log",
    lambda x: f"""\
INCIDENT #007
  Intrusion alarm. Analyse {x.work}/auth.log (sshd log excerpt: 'Failed password', 'Accepted ...').
TASK   Create {x.work}/answers.txt :
    top_ip=<IP with the MOST 'Failed password' lines>
    top_ip_failures=<how many failed lines that IP has>
    compromised_user=<user name that received 'Accepted password' from an IP that had failed many times before>
    compromised_ip=<that IP>
    distinct_invalid_users=<number of DIFFERENT names that appear as 'invalid user NAME'>
USE   grep, awk, cut, sort, uniq -c, wc -l.   Think: which IP is the real danger - the loudest, or the one that got in?
EXPECTED RESULT   Five correct lines. (In real life you would now lock the account and force a password change.)""",
    s_m07t2, c_m07t2,
    hints=["grep 'Failed password' auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head  (the IP is 4th from the end)",
           "grep Accepted auth.log", "grep -o 'invalid user [a-z]*' auth.log | sort -u | wc -l"],
    debrief="The noisiest attacker was not the compromise - the quiet 'Accepted password' after many failures was.")

# ---------------------------------------------------------------- shared: a HARDENED lab sshd with a working key
def lab_sshd_up(x):
    if not have("sshd"):
        apt_install("openssh-server")
    sh("useradd -m -s /bin/bash lab_ssh && usermod -p '*' lab_ssh")
    d = LAB / "sshd"
    d.mkdir(parents=True, exist_ok=True)
    sh(f"ssh-keygen -q -t ed25519 -N '' -f {d}/ssh_host_ed25519_key")
    put(d / "sshd_config", f"""Port 2222
ListenAddress 127.0.0.1
HostKey {d}/ssh_host_ed25519_key
PidFile {d}/sshd.pid
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers lab_ssh
MaxAuthTries 3
""")
    put("/etc/systemd/system/lab-sshd.service", f"""[Unit]
Description=Lab practice SSH daemon (port 2222)

[Service]
ExecStartPre=/bin/mkdir -p /run/sshd
ExecStart=/usr/sbin/sshd -D -e -f {d}/sshd_config
Restart=on-failure

[Install]
WantedBy=multi-user.target
""")
    x.work.mkdir(parents=True, exist_ok=True)
    x.own(x.work)
    user = x.student
    key = x.work / "lab_key"
    sh(f"ssh-keygen -q -t ed25519 -N '' -f {key}")
    x.own(x.work)
    ssh_dir = Path("/home/lab_ssh/.ssh")
    ssh_dir.mkdir(exist_ok=True)
    put(ssh_dir / "authorized_keys", (x.work / "lab_key.pub").read_text(), 0o600)
    sh("chown -R lab_ssh:lab_ssh /home/lab_ssh/.ssh; chmod 700 /home/lab_ssh/.ssh")
    sh("mkdir -p /home/lab_ssh/incoming && chown lab_ssh:lab_ssh /home/lab_ssh/incoming")
    sh("systemctl daemon-reload; systemctl restart lab-sshd")
    time.sleep(1)

SSH_O = "-o BatchMode=yes -o ConnectTimeout=5"

# ---------------------------------------------------------------- M07-T3  client config (REAL ~/.ssh/config)
def ssh_home(x):
    try:
        return Path(pwd.getpwnam(x.student).pw_dir)
    except KeyError:
        return Path("/root")

def s_m07t3(x):
    d = ssh_home(x) / ".ssh"
    if not d.exists():
        d.mkdir(mode=0o700)
        sh(f"chown {x.student}:{x.student} {d}")
    save_orig(d / "config")             # your real files are backed up now and restored on reset
    save_orig(d / "known_hosts")
    lab_sshd_up(x)

def c_m07t3(x):
    q, cfg = [], ssh_home(x) / ".ssh/config"
    txt = cfg.read_text() if cfg.is_file() else ""
    q.append(R("~/.ssh/config exists with a 'Host labbox' block", re.search(r"^\s*Host\s+labbox\b", txt, re.M | re.I) is not None))
    for key, val in (("HostName", "127.0.0.1"), ("Port", "2222"), ("User", "lab_ssh")):
        q.append(R(f"{key} {val}", re.search(rf"^\s*{key}\s+{re.escape(val)}\s*$", txt, re.M | re.I) is not None))
    q.append(R("IdentityFile points to lab_key", re.search(r"^\s*IdentityFile\s+\S*lab_key\s*$", txt, re.M | re.I) is not None))
    q.append(R("IdentitiesOnly yes", re.search(r"^\s*IdentitiesOnly\s+yes\s*$", txt, re.M | re.I) is not None))
    orig = ORIGD / str(cfg).replace("/", "__")
    if orig.exists():
        have_lines = {l.strip() for l in txt.splitlines()}
        missing = [l for l in orig.read_text().splitlines() if l.strip() and l.strip() not in have_lines]
        q.append(R("your EXISTING ~/.ssh/config entries are still there (you only ADDED a block)", not missing, f"missing: {missing[:2]}"))
    runas = None if x.student == "root" else x.student
    rc, out = sh(f"ssh {SSH_O} labbox whoami", user=runas) if cfg.is_file() else (1, "no ~/.ssh/config")
    q.append(R("`ssh labbox whoami` works with no other options", rc == 0 and out.strip().endswith("lab_ssh"), out[-120:]))
    return q

add("M07-T3", "Client side: your real ~/.ssh/config",
    lambda x: f"""\
SCENARIO   A hardened lab sshd (127.0.0.1, port 2222, key only) runs on this VM and your key pair is ready: {x.work}/lab_key (+ .pub, already authorised for user lab_ssh).
           Typing  ssh -i KEY -p 2222 lab_ssh@127.0.0.1  every time is error-prone - use the client config file.
SAFETY     The trainer saved your current {ssh_home(x)}/.ssh/config and known_hosts. Keep every existing line - only ADD a block.
           When this task is reset or the lab is cleaned, both files are put back exactly as they were (or removed, if they did not exist).
TASK       Add to {ssh_home(x)}/.ssh/config :
               Host labbox         HostName 127.0.0.1      Port 2222      User lab_ssh
               IdentityFile {x.work}/lab_key       IdentitiesOnly yes
               StrictHostKeyChecking accept-new        (so the FIRST connection does not stop with 'Host key verification failed')
           The file must be mode 600 (chmod 600 ~/.ssh/config) and owned by you.
           Test:  ssh labbox whoami      -> lab_ssh
EXPECTED RESULT   One short command logs in.""",
    s_m07t3, c_m07t3,
    hints=["Use indentation inside the Host block. 'man ssh_config' lists every keyword.", "StrictHostKeyChecking accept-new trusts a host key the first time and complains if it later changes.",
           "ssh -v labbox shows which config file and key are used."],
    debrief="Client config files make logins short, safe and repeatable - and allow ProxyJump, multiple keys, etc.")

# ---------------------------------------------------------------- M07-T4  scp + remote checksum
def s_m07t4(x):
    lab_sshd_up(x)
    put(x.work / "payload.bin", os.urandom(300000))
    x.secret = {"sha": sha(x.work / "payload.bin")}
    x.own(x.work)

def c_m07t4(x):
    q, a = [], answers(x)
    remote = Path("/home/lab_ssh/incoming/payload.bin")
    q.append(R("payload.bin arrived in /home/lab_ssh/incoming/", remote.exists()))
    q.append(R("remote file is byte-identical to the local file", sha(remote) == x.secret["sha"]))
    chk(q, a, "remote_sha256", x.secret["sha"], "answer remote_sha256 = SHA-256 computed ON THE REMOTE side")
    return q

add("M07-T4", "Transfer a file over SSH and verify it",
    lambda x: f"""\
SCENARIO   Send {x.work}/payload.bin to user lab_ssh on the lab sshd (127.0.0.1, port 2222, key {x.work}/lab_key, already authorised),
           into the directory  /home/lab_ssh/incoming/  and PROVE that it arrived intact.
TASK
  1. scp (note: scp uses capital -P for the port):  scp -P 2222 -i KEY -o StrictHostKeyChecking=accept-new payload.bin lab_ssh@127.0.0.1:incoming/
  2. Compute the SHA-256 ON THE REMOTE SIDE:  ssh -p 2222 -i KEY lab_ssh@127.0.0.1 sha256sum incoming/payload.bin
  3. Write the hash into {x.work}/answers.txt :   remote_sha256=<hash>
EXPECTED RESULT   File identical on both sides; the hash you wrote matches.""",
    s_m07t4, c_m07t4,
    hints=["scp -P 2222 -i lab_key payload.bin lab_ssh@127.0.0.1:incoming/", "ssh uses lowercase -p for the port, scp uses uppercase -P."],
    debrief="Always verify transfers with a checksum computed on the destination.")

compose("M07-X1", "BLOCK EXAM: SSH and intrusion analysis", "Harden the practice daemon and analyse a brute-force log.", ["M07-T1", "M07-T2"])
