#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LAC - Linux Admin Labs (practice labs for Debian)
================================================
Self-contained trainer for a CLEAN Debian VM (VirtualBox).  Run as root:

    sudo python3 linux_admin_course.py

* Works with your normal Bash over SSH - real commands, real services, real faults.
* Open the trainer in one SSH window, do the work in a second one (or use the `sh` command).
* Progress/errors live in /var/lib/linux-admin-course/profile.json - NOT in the lab,
  so resetting a task (or the whole lab) never erases your statistics.
* Export the profile before you destroy the VM:  sudo python3 linux_admin_course.py --export
  and import it into the new VM:                  sudo python3 linux_admin_course.py --import FILE

Everything the trainer creates is named lab-*/lab_* or lives in /opt/linux-lab, /mnt/lab-data.
RUN IT ONLY INSIDE A DISPOSABLE VM.
"""
import argparse, grp, hashlib, json, os, pwd, random, re, shlex, shutil, signal, string
import subprocess, sys, tarfile, time, types
from pathlib import Path

VERSION = "0.2.0"
LAB = Path("/opt/linux-lab")
CACHE = LAB / "cache"          # survives lab resets (downloads, original config copies)
ORIGD = CACHE / "orig"
BIN, RUN, WORK, PRIV = LAB / "bin", LAB / "run", LAB / "work", LAB / ".private"
DATA = Path("/var/lib/linux-admin-course")
PROFILE = DATA / "profile.json"
CMDLOG = Path("/var/log/linux-lab-commands.log")
HOOK = Path("/etc/profile.d/lab-logger.sh")
MNT, IMG = Path("/mnt/lab-data"), LAB / "disk.img"

# ----------------------------------------------------------------- colours / io
_TTY = sys.stdout.isatty()
def _c(code): return lambda s: f"\033[{code}m{s}\033[0m" if _TTY else str(s)
green, red, yellow, dim, bold, cyan = _c("32"), _c("31"), _c("33"), _c("2"), _c("1"), _c("36")

_CYR = dict(zip("йцукенгшщзфывапролдячсмить", "qwertyuiopasdfghjklzxcvbnm"))

def ask(prompt="> "):
    """Read a line. A Russian keyboard layout is understood: the same physical keys as Latin letters (и -> b, с -> c ...)."""
    try:
        v = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"
    if v and not re.search(r"[A-Za-z]", v) and re.search(r"[а-яё]", v.lower()):
        mapped = "".join(_CYR.get(ch, ch) for ch in v.lower())
        print(dim(f"  (Russian layout detected: '{v}' read as '{mapped}')"))
        return mapped
    return v

def sh(cmd, timeout=40, user=None):
    """Run a shell command, return (rc, combined output)."""
    if user:
        cmd = f"runuser -u {user} -- bash -c {shlex.quote('cd /; ' + cmd)}"
    try:
        p = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True,
                           text=True, timeout=timeout, errors="replace")
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"

def put(path, text="", mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    if mode is not None:
        path.chmod(mode)
    return path

def sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None

def http(url, t=5):
    rc, out = sh(f"curl -s -m {t} -w '\\n%{{http_code}}' {shlex.quote(url)}")
    body, _, code = out.rpartition("\n")
    return (int(code) if code.isdigit() else 0), body

def svc(name):
    rc, out = sh(f"systemctl show {name} -p ActiveState,SubState,UnitFileState,User,Restart,Description,ExecMainStatus,Result,LoadState")
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)

def R(label, ok, detail=""):
    return (label, bool(ok), detail)

# ----------------------------------------------------------------- profile (persistent!)
class Profile:
    def __init__(self):
        self.d = {"version": 1, "created": int(time.time()), "events": [], "completed": {}, "current": None}
        DATA.mkdir(parents=True, exist_ok=True)
        if PROFILE.exists():
            try:
                self.d = json.loads(PROFILE.read_text())
            except Exception:
                shutil.copy(PROFILE, DATA / f"profile.corrupt-{int(time.time())}")
        for k, v in (("events", []), ("completed", {}), ("current", None)):
            self.d.setdefault(k, v)

    def save(self):
        tmp = DATA / "profile.tmp"
        tmp.write_text(json.dumps(self.d, indent=1))
        os.replace(tmp, PROFILE)
        try:
            shutil.copy(PROFILE, DATA / "profile.bak")
        except OSError:
            pass

    def log(self, task, typ, detail=""):
        self.d["events"].append({"ts": int(time.time()), "task": task, "type": typ, "detail": detail[:300]})
        if typ == "PASS":
            self.d["completed"].setdefault(task, int(time.time()))
        self.save()

    def n(self, typ, prefix=""):
        return sum(1 for e in self.d["events"] if e["type"] == typ and e["task"].startswith(prefix))

    def merge(self, other):
        seen = {(e["ts"], e["task"], e["type"], e["detail"]) for e in self.d["events"]}
        added = 0
        for e in other.get("events", []):
            k = (e["ts"], e["task"], e["type"], e["detail"])
            if k not in seen:
                self.d["events"].append(e); seen.add(k); added += 1
        self.d["events"].sort(key=lambda e: e["ts"])
        for t, ts in other.get("completed", {}).items():
            self.d["completed"][t] = min(ts, self.d["completed"].get(t, ts))
        self.save()
        return added

# ----------------------------------------------------------------- task registry
class Task:
    def __init__(self, tid, title, text, setup, check, hints=(), bad=(), debrief="", no_hints=False):
        self.tid, self.title, self.text, self.setup, self.check = tid, title, text, setup, check
        self.hints, self.bad, self.debrief, self.no_hints = list(hints), list(bad), debrief, no_hints

MODULES = []
def module(n, name, intro, track="Core"):
    MODULES.append({"n": n, "name": name, "intro": intro, "track": track, "tasks": []})
    MODULES.sort(key=lambda m: m["n"])

def add(tid, title, text, setup, check, **kw):
    mod = next(m for m in MODULES if m["n"] == int(tid[1:3]))
    mod["tasks"].append(Task(tid, title, text, setup, check, **kw))
    mod["tasks"].sort(key=lambda t: ("-X" in t.tid, t.tid))

ALL = lambda: [t for m in MODULES for t in m["tasks"]]
def task_by_id(tid): return next(t for t in ALL() if t.tid == tid)

# global "bad habit" patterns applied to the command log of every task
GLOBAL_BAD = [
    (r"\bchmod\s+(-\w+\s+)*0?777\b", "chmod 777 is never the right fix - grant the minimum permissions"),
    (r"\brm\s+-\w*r\w*f?\w*\s+/(\s|$|\*)", "DANGEROUS: rm -rf on / (root of the filesystem)"),
    (r"\bmkfs(\.\w+)?\s+/dev/", "DANGEROUS: mkfs on a real device"),
    (r"\bdd\s+.*of=/dev/(sd|vd|nvme)", "DANGEROUS: dd onto a real disk"),
]

class Ctx:
    def __init__(self, task, prof):
        self.task, self.prof, self.tid = task, prof, task.tid
        self.work = WORK / task.tid.lower()
        self.student = os.environ.get("SUDO_USER") or "root"
        self.secret = {}
        f = PRIV / f"{self.tid}.json"
        if f.exists():
            try:
                self.secret = json.loads(f.read_text())
            except Exception:
                pass

    def save_secret(self):
        PRIV.mkdir(parents=True, exist_ok=True)
        (PRIV / f"{self.tid}.json").write_text(json.dumps(self.secret))

    @property
    def started(self):
        cur = self.prof.d.get("current")
        return cur["started"] if cur else 0

    def cmds(self):
        try:
            lines = CMDLOG.read_text(errors="replace").splitlines()
        except OSError:
            return None
        out = []
        for ln in lines:
            p = ln.split("\t", 3)
            if len(p) == 4 and p[0].isdigit() and int(p[0]) >= self.started:
                out.append((int(p[0]), p[1], p[2], p[3]))
        return out

    def used(self, rx):
        """True/False if the command log shows a command matching rx; None if logging is unavailable."""
        c = self.cmds()
        if c is None or not HOOK.exists() or not c:
            return None
        return any(re.search(rx, x[3]) for x in c)

    def error(self, msg):
        """Register an incorrect action once per attempt."""
        cur = self.prof.d["current"]
        key = "state|" + msg
        if key in cur["errs"]:
            return
        cur["errs"].append(key)
        self.prof.log(self.tid, "ERROR", msg)
        print(red(f"  [ERROR] {msg}"))

    def own(self, path):
        if self.student != "root":
            sh(f"chown -R {self.student}:{self.student} {shlex.quote(str(path))}")

def scan_commands(prof, task, x):
    cmds = x.cmds() or []
    cur = prof.d["current"]
    for ts, user, cwd, cmd in cmds:
        key = f"{ts}|{hashlib.md5(cmd.encode()).hexdigest()[:8]}"
        if key in cur["errs"]:
            continue
        for rx, msg in list(task.bad) + GLOBAL_BAD:
            if re.search(rx, cmd):
                cur["errs"].append(key)
                prof.log(task.tid, "ERROR", f"{msg}  <- `{cmd[:80]}`")
                print(red(f"  [ERROR] {msg}\n          command: {cmd[:100]}"))
                break

# ----------------------------------------------------------------- answers file helpers
def answers(x, fname="answers.txt"):
    d = {}
    try:
        for ln in (x.work / fname).read_text().splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                d[k.strip().lower()] = v.strip().strip("\"'")
    except OSError:
        return None
    return d

def chk(reqs, ans, key, exp, label=None, kind="str", tol=0):
    label = label or f"answer '{key}' is correct"
    got = None if ans is None else ans.get(key.lower())
    if got is None:
        reqs.append(R(label, False, f"line '{key}=...' not found (file missing or key misspelled)"))
        return
    try:
        if kind == "int": ok = abs(int(float(got)) - int(exp)) <= tol
        elif kind == "float": ok = abs(float(got) - float(exp)) <= max(tol, 0.011)
        elif kind == "path": ok = os.path.realpath(got) == os.path.realpath(str(exp))
        else: ok = got.lower() == str(exp).lower()
    except ValueError:
        ok = False
    reqs.append(R(label, ok, "" if ok else f"you wrote {got!r}"))

# ----------------------------------------------------------------- lab helper processes
LABPROC = r'''#!/usr/bin/env python3
import os, sys, time, signal, argparse, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("--hold"); ap.add_argument("--cpu", action="store_true")
ap.add_argument("--ignore-term", action="store_true"); ap.add_argument("--http", type=int)
ap.add_argument("--mem", type=int, default=0); ap.add_argument("--leak", type=int, default=0); ap.add_argument("--bind", default="0.0.0.0"); ap.add_argument("--rundir", default="/opt/linux-lab/run")
a = ap.parse_args()
open(f"{a.rundir}/{a.name}.pid", "w").write(str(os.getpid()))
def note(s):
    with open(f"{a.rundir}/{a.name}.signals", "a") as f: f.write(s + "\n")
held = open(a.hold, "a") if a.hold else None
ballast = None
if a.mem:
    ballast = bytearray(a.mem * 1024 * 1024)
    for i in range(0, len(ballast), 4096): ballast[i] = 1
def on_term(s, f):
    if a.ignore_term: note("TERM-ignored"); return
    note("TERM"); os._exit(0)
def on_int(s, f): note("INT"); os._exit(0)
def on_hup(s, f): note("HUP"); os._exit(0)
signal.signal(signal.SIGTERM, on_term); signal.signal(signal.SIGINT, on_int)
signal.signal(signal.SIGHUP, on_hup); signal.signal(signal.SIGCONT, lambda s, f: note("CONT"))
if a.http:
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            b = ("LAB-OK " + a.name + "\n").encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *x): pass
    srv = HTTPServer((a.bind, a.http), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
leaked = []
last_leak = time.time()
while True:
    if a.leak and time.time() - last_leak >= 1 and len(leaked) < 60:
        chunk = bytearray(a.leak * 1024 * 1024)
        for i in range(0, len(chunk), 4096): chunk[i] = 1
        leaked.append(chunk); last_leak = time.time()
    if a.cpu:
        t = time.time()
        while time.time() - t < 0.09: pass
        time.sleep(0.01)
    else:
        time.sleep(1)
'''

HOOK_SH = r'''# Linux Admin Course - command logger (harmless; removed by deleting this file)
if [ -n "${BASH_VERSION:-}" ] && [ -n "${PS1:-}" ]; then
  __lab_last=$(HISTTIMEFORMAT= builtin history 1 | awk '{print $1}')
  __lab_log() {
    local n c
    read -r n c < <(HISTTIMEFORMAT= builtin history 1)
    [ -z "$n" ] && return
    [ "$n" = "${__lab_last:-}" ] && return
    __lab_last=$n
    printf '%s\t%s\t%s\t%s\n' "$(date +%s)" "${SUDO_USER:-$USER}" "$PWD" "$c" >> /var/log/linux-lab-commands.log 2>/dev/null
  }
  case ";${PROMPT_COMMAND:-};" in *";__lab_log;"*) ;; *) PROMPT_COMMAND="__lab_log${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;; esac
fi
'''

PKG = {"lsof": "lsof", "fuser": "psmisc", "curl": "curl", "rsync": "rsync", "git": "git",
       "dig": "dnsutils", "tree": "tree", "ss": "iproute2", "visudo": "sudo", "killall": "psmisc"}

def ensure_pkgs(*cmds):
    need = sorted({PKG.get(c, c) for c in cmds if not shutil.which(c)})
    if need:
        print(dim(f"  installing packages: {' '.join(need)} ..."))
        sh("DEBIAN_FRONTEND=noninteractive apt-get update -qq", timeout=300)
        rc, out = sh("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq " + " ".join(need), timeout=900)
        if rc != 0:
            raise RuntimeError("apt-get failed (is the VM online?):\n" + out[-400:])

def ensure_infra():
    for d, m in ((LAB, 0o755), (BIN, 0o755), (RUN, 0o1777), (WORK, 0o755), (PRIV, 0o700)):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(m)
    put(BIN / "labproc.py", LABPROC, 0o755)
    put(BIN / "lab-rc.sh", '[ -f ~/.bashrc ] && . ~/.bashrc\n. /etc/profile.d/lab-logger.sh\n', 0o644)
    fresh = not HOOK.exists()
    if fresh or HOOK.read_text() != HOOK_SH:
        put(HOOK, HOOK_SH, 0o644)
    if not CMDLOG.exists():
        CMDLOG.touch()
    CMDLOG.chmod(0o666)
    ensure_pkgs("lsof", "fuser", "curl", "rsync", "git", "dig", "ss", "tree")
    return fresh

def save_orig(path):
    """Remember the pristine state of a real file before a task edits it.
    Restored (once) on the next lab reset/cleanup. A file that did not exist is remembered as 'absent'."""
    p = Path(path)
    ORIGD.mkdir(parents=True, exist_ok=True)
    key = str(p).replace("/", "__")
    if (ORIGD / key).exists() or (ORIGD / (key + ".absent")).exists():
        return                                   # already saved during this lab session
    if p.exists():
        shutil.copy2(p, ORIGD / key)
    else:
        (ORIGD / (key + ".absent")).write_text("")

def restore_origs():
    restored = []
    if ORIGD.exists():
        for f in list(ORIGD.glob("*")):
            absent = f.name.endswith(".absent")
            real = Path((f.name[:-7] if absent else f.name).replace("__", "/"))
            try:
                if absent:
                    real.unlink(missing_ok=True)
                else:
                    shutil.copy2(f, real)
                    if str(real).startswith(("/home/", "/root/")):
                        st = real.parent.stat()
                        os.chown(real, st.st_uid, st.st_gid)
                restored.append(str(real))
                f.unlink()                       # one-shot: never overwrite later, legitimate changes
            except OSError:
                pass
    if any(r.startswith("/etc/postfix") for r in restored) or "/etc/aliases" in restored:
        sh("postsuper -d ALL >/dev/null 2>&1; newaliases >/dev/null 2>&1; postfix reload >/dev/null 2>&1")
    return restored

def lab_pids():
    out = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            if b"/opt/linux-lab/bin/labproc.py" in (p / "cmdline").read_bytes():
                out.append(int(p.name))
        except OSError:
            pass
    return out

def spawn(name, *args):
    for ext in ("pid", "signals"):
        (RUN / f"{name}.{ext}").unlink(missing_ok=True)
    cmd = shlex.join(["setsid", "python3", str(BIN / "labproc.py"), name, *map(str, args)])
    subprocess.run(["bash", "-c", cmd + " </dev/null >/dev/null 2>&1 &"])
    for _ in range(50):
        time.sleep(0.1)
        pf = RUN / f"{name}.pid"
        if pf.exists() and pf.read_text().strip():
            return int(pf.read_text())
    raise RuntimeError(f"could not start helper process {name}")

def pstate(pid):
    try:
        s = Path(f"/proc/{pid}/stat").read_text()
        return s[s.rindex(")") + 2]
    except (OSError, ValueError):
        return None

def proc(name):
    pf, sf = RUN / f"{name}.pid", RUN / f"{name}.signals"
    pid = int(pf.read_text()) if pf.exists() and pf.read_text().strip().isdigit() else 0
    st = pstate(pid) if pid else None
    if st:
        try:
            if name.encode() not in Path(f"/proc/{pid}/cmdline").read_bytes():
                st = None  # pid was reused by something else
        except OSError:
            st = None
    sigs = sf.read_text().split() if sf.exists() else []
    return types.SimpleNamespace(name=name, pid=pid, state=st, alive=st not in (None, "Z"), sigs=sigs)

def fd_holders(path, deleted=False):
    out = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            for fd in (p / "fd").iterdir():
                try:
                    t = os.readlink(fd)
                except OSError:
                    continue
                if t == str(path) or (deleted and t.startswith(str(path)) and t.endswith("(deleted)")):
                    out.append(int(p.name)); break
        except OSError:
            pass
    return out

def deleted_open_on(mount):
    res = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            for fd in (p / "fd").iterdir():
                try:
                    t = os.readlink(fd)
                except OSError:
                    continue
                if t.startswith(str(mount) + "/") and t.endswith("(deleted)"):
                    res.append((int(p.name), t))
        except OSError:
            pass
    return res

# ----------------------------------------------------------------- global cleanup (lab reset)
def cleanup_all():
    sysd = Path("/etc/systemd/system")
    for u in list(sysd.glob("lab-*.service")) + list(sysd.glob("lab-*.timer")):
        sh(f"systemctl disable --now {u.name} >/dev/null 2>&1")
        u.unlink(missing_ok=True)
    for l in list(sysd.glob("*.wants/lab-*")):
        l.unlink(missing_ok=True)
    sh("systemctl daemon-reload; systemctl reset-failed >/dev/null 2>&1")
    for pid in lab_pids():
        for s in (signal.SIGCONT, signal.SIGKILL):
            try: os.kill(pid, s)
            except OSError: pass
    for f in Path("/etc/sudoers.d").glob("*"):
        try:
            if f.name.startswith("lab-") or "lab_ops" in f.read_text():
                f.unlink()
        except OSError:
            pass
    for f in Path("/etc/cron.d").glob("*"):
        try:
            if f.name.startswith("lab-") or "/opt/linux-lab" in f.read_text():
                f.unlink()
        except OSError:
            pass
    nginx_touched = False
    for d in (Path("/etc/nginx/conf.d"), Path("/etc/nginx/sites-enabled")):
        for f in d.glob("*") if d.exists() else []:
            try:
                if f.name.startswith("lab-") or "/opt/linux-lab" in f.read_text():
                    f.unlink(); nginx_touched = True
            except OSError:
                pass
    if nginx_touched:
        sh("systemctl try-reload-or-restart nginx >/dev/null 2>&1")
    ap_touched = False
    for d in ("sites-enabled", "sites-available", "conf-enabled", "conf-available"):
        for f in Path("/etc/apache2", d).glob("lab-*") if Path("/etc/apache2", d).exists() else []:
            f.unlink(missing_ok=True); ap_touched = True
    if ap_touched:
        sh("systemctl try-reload-or-restart apache2 >/dev/null 2>&1")
    try:
        ft = Path("/etc/fstab").read_text().splitlines()
        keep = [l for l in ft if "lab-data" not in l and "/opt/linux-lab" not in l]
        if keep != ft:
            Path("/etc/fstab").write_text("\n".join(keep) + "\n")
    except OSError:
        pass
    for mp in (MNT, Path("/mnt/lab-data2")):
        if sh(f"mountpoint -q {mp}")[0] == 0:
            sh(f"umount -l {mp}")
    restore_origs()
    if sh(f"mountpoint -q {MNT}")[0] == 0:
        sh(f"umount -l {MNT}")
    for img in (IMG, LAB / "disk2.img"):
        if img.exists():
            for ln in sh(f"losetup -j {img}")[1].splitlines():
                sh(f"losetup -d {ln.split(':')[0]}")
            img.unlink()
    for f in Path("/etc/logrotate.d").glob("lab-*"):
        f.unlink(missing_ok=True)
    if shutil.which("docker"):
        sh("docker ps -aq --filter name=lab- | xargs -r docker rm -f >/dev/null 2>&1", timeout=120)
        sh("docker network ls -q --filter name=lab | xargs -r docker network rm >/dev/null 2>&1")
        sh("docker volume ls -q --filter name=lab- | xargs -r docker volume rm -f >/dev/null 2>&1")
        sh("docker images --format '{{.Repository}}:{{.Tag}}' | grep '^lab-' | xargs -r docker rmi -f >/dev/null 2>&1")
    for u in pwd.getpwall():
        if u.pw_name.startswith("lab_"):
            sh(f"pkill -KILL -u {u.pw_name}; userdel -r -f {u.pw_name} >/dev/null 2>&1")
    for g in grp.getgrall():
        if g.gr_name.startswith("lab_"):
            sh(f"groupdel {g.gr_name} >/dev/null 2>&1")
    try:
        hosts = Path("/etc/hosts").read_text().splitlines()
        keep = [l for l in hosts if "# LAB" not in l and not re.search(r"lab-(app|db)\.internal", l)]
        if keep != hosts:
            Path("/etc/hosts").write_text("\n".join(keep) + "\n")
    except OSError:
        pass
    if shutil.which("mysql"):
        rc, out = sh("mysql -N -B -e \"SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'lab\\\\_%'\"")
        for db in out.split() if rc == 0 else []:
            sh(f"mysql -e 'DROP DATABASE IF EXISTS `{db}`'")
        rc, out = sh("mysql -N -B -e \"SELECT user,host FROM mysql.user WHERE user LIKE 'lab\\\\_%'\"")
        for ln in out.splitlines() if rc == 0 else []:
            u, h = ln.split("\t")
            sh(f"mysql -e \"DROP USER IF EXISTS '{u}'@'{h}'\"")
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(LAB / "sshd", ignore_errors=True)
    shutil.rmtree("/etc/bind/lab-dns", ignore_errors=True)
    shutil.rmtree("/var/cache/bind/lab-dns", ignore_errors=True)
    for d in (RUN, PRIV):
        shutil.rmtree(d, ignore_errors=True)
    for d, m in ((WORK, 0o755), (RUN, 0o1777), (PRIV, 0o700)):
        d.mkdir(parents=True, exist_ok=True); d.chmod(m)


# ----------------------------------------------------------------- shared helpers
def rnd_word(r, n=4):
    return "".join(r.choice(string.ascii_lowercase) for _ in range(n))

def getuser(n):
    try: return pwd.getpwnam(n)
    except KeyError: return None

def group_members(g):
    try: return grp.getgrnam(g).gr_mem
    except KeyError: return None

def have(c):
    return bool(shutil.which(c)) or Path("/usr/sbin", c).exists()

_UPDATED = False
def apt_install(*pkgs):
    """Install Debian packages that are missing (noninteractive)."""
    global _UPDATED
    missing = [p for p in pkgs if sh(f"dpkg -s {p} 2>/dev/null | grep -q 'Status: install ok installed'")[0] != 0]
    if not missing:
        return
    print(dim(f"  installing packages: {' '.join(missing)} (needs internet) ..."))
    env = "DEBIAN_FRONTEND=noninteractive"
    if not _UPDATED:
        sh(f"{env} apt-get update -qq", timeout=300)
        _UPDATED = True
    pol = Path("/usr/sbin/policy-rc.d")
    made = not pol.exists()
    if made:
        put(pol, "#!/bin/sh\nexit 101\n", 0o755)      # do not auto-start services during install
    rc, out = sh(f"{env} apt-get install -y -qq {' '.join(missing)}", timeout=1800)
    if made:
        pol.unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError("apt-get install failed (is the VM online?):\n" + out[-400:])

def ensure_nginx():
    apt_install("nginx")
    sh("systemctl enable --now nginx")

def ensure_mariadb():
    apt_install("mariadb-server")
    sh("systemctl enable --now mariadb")

def mysql_run(sql, db="", extra=""):
    p = subprocess.run(f"mysql {extra} {db}", shell=True, input=sql, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()

def qv(sql, db="lab_shop"):
    return mysql_run(sql, db, "-N -B")[1]

def seed_shop(extra_orders=0):
    r = random.Random(7 if not extra_orders else None)
    names = ["Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Grace", "Heidi"]
    sql = ["CREATE DATABASE lab_shop CHARACTER SET utf8mb4;", "USE lab_shop;",
           "CREATE TABLE customers(id INT PRIMARY KEY, name VARCHAR(40), city VARCHAR(40));",
           "CREATE TABLE orders(id INT PRIMARY KEY AUTO_INCREMENT, customer_id INT, amount DECIMAL(10,2), status VARCHAR(10));"]
    for i, n in enumerate(names, 1):
        sql.append(f"INSERT INTO customers VALUES({i},'{n}','City{i}');")
    for _ in range(60):
        sql.append(f"INSERT INTO orders(customer_id,amount,status) VALUES({r.randint(1,8)},{r.randint(500,50000)/100},'{r.choice(['paid','paid','pending','refund'])}');")
    rc, out = mysql_run("\n".join(sql))
    if rc != 0:
        raise RuntimeError("mysql seed failed: " + out)

def task_text(t, x):
    return t.text(x) if callable(t.text) else t.text

def own_tree(path, user, mode=None):
    sh(f"chown -R {user}:{user} {shlex.quote(str(path))}")
    if mode is not None:
        sh(f"chmod -R {mode} {shlex.quote(str(path))}")

# ----------------------------------------------------------------- DSL: answers-type tasks
def answers_task(tid, title, text, gen, hints=(), bad=(), debrief="", keep_modes=False, **kw):
    """gen(x, r) builds the lab data and returns {key: (value, label[, kind[, tolerance]])}.
    The student writes answers.txt (key=value) - the checker compares every key."""
    def setup(x):
        spec = gen(x, random.Random())
        x.secret = {"spec": {k: list(v) for k, v in spec.items()}}
        if not keep_modes:               # chown clears SUID/SGID bits, so tasks about special bits skip it
            x.own(x.work)
    def check(x):
        a, q = answers(x), []
        for k, v in x.secret["spec"].items():
            kind = v[2] if len(v) > 2 else "str"
            tol = v[3] if len(v) > 3 else 0
            chk(q, a, k, v[0], v[1], kind, tol)
        return q
    def full_text(x):
        keys = "\n".join(f"    {k}=<{v[1]}>" for k, v in x.secret["spec"].items())
        return (text(x) if callable(text) else text) + (
            f"\n\nANSWER FILE   {x.work}/answers.txt   (one key=value per line, no spaces around '='):\n{keys}\n"
            "EXPECTED RESULT   every line correct. Do not modify the input data.")
    add(tid, title, full_text, setup, check, hints=hints, bad=bad, debrief=debrief, **kw)

# ----------------------------------------------------------------- DSL: services
def hb_script(name):
    return f"#!/bin/bash\nwhile true; do date +%s > /opt/linux-lab/run/{name}.hb; sleep 2; done\n"

def mk_service(name, body=None, user=None, mode=0o755, restart="on-failure", enable=False, start=True,
               unit_extra="", after="", desc=None, requires="", exec_start=None, no_limit=False):
    """Create /opt/linux-lab/bin/<name>.sh and a systemd unit <name>.service."""
    script = BIN / f"{name}.sh"
    put(script, body if body is not None else hb_script(name), mode)
    unit = f"[Unit]\nDescription={desc or name}\n"
    if after: unit += f"After={after}\n"
    if requires: unit += f"Requires={requires}\n"
    if no_limit: unit += "StartLimitIntervalSec=0\n"
    unit += "\n[Service]\n" + (f"User={user}\n" if user else "")
    unit += f"ExecStart={exec_start or script}\nRestart={restart}\nRestartSec=2\n{unit_extra}\n[Install]\nWantedBy=multi-user.target\n"
    put(f"/etc/systemd/system/{name}.service", unit)
    sh("systemctl daemon-reload")
    if enable: sh(f"systemctl enable {name} >/dev/null 2>&1")
    if start: sh(f"systemctl start {name} >/dev/null 2>&1")

def hb_age(name):
    f = RUN / f"{name}.hb"
    try: return time.time() - int(f.read_text())
    except (OSError, ValueError): return 999

def svc_reqs(name, enabled=True, hb=True, user=None):
    s = svc(f"{name}.service")
    q = [R(f"{name}: active (running)", s.get("ActiveState") == "active", f"state {s.get('ActiveState')}/{s.get('SubState')}")]
    if enabled:
        q.append(R(f"{name}: enabled at boot", s.get("UnitFileState") == "enabled"))
    if user:
        q.append(R(f"{name}: runs as {user}", s.get("User") == user))
    if hb:
        time.sleep(2.3)
        q.append(R(f"{name}: really working (heartbeat fresh)", hb_age(name) < 6))
    return q

# ----------------------------------------------------------------- DSL: block exams = composition of tasks
REPORT_NEEDS = ("summary", "root causes", "fixes applied", "prevention")

def report_reqs(x):
    rp = x.work / "incident-report.md"
    txt = rp.read_text() if rp.is_file() else ""
    secs = {m.group(1).strip().lower(): m.group(2) for m in re.finditer(r"^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)", txt, re.M | re.S)}
    ok = all(len(secs.get(n, "").split()) >= 12 for n in REPORT_NEEDS)
    return [R("incident-report.md has the 4 required sections, each >= 12 words", ok, "found: " + (", ".join(secs) or "no file"))]

def report_text(x):
    return (f"\nWRITTEN REPORT\n  Create {x.work}/incident-report.md with the sections\n"
            "     ## Summary   ## Root causes   ## Fixes applied   ## Prevention\n"
            "  (at least 12 words in each: what broke, why, what you changed, how to avoid a repeat).")

def subctx(x, t):
    sx = Ctx(t, x.prof)
    sx.student = x.student
    return sx

def compose(tid, title, intro, parts, report=True):
    """A block exam: runs the setups of several existing tasks at once, no hints, one combined check."""
    tasks = [task_by_id(p) for p in parts]
    def setup(x):
        for t in tasks:
            sx = subctx(x, t)
            sx.work.mkdir(parents=True, exist_ok=True)
            sx.own(sx.work)
            t.setup(sx)
            sx.save_secret()
    def check(x):
        out = []
        for t in tasks:
            for l, ok, d in t.check(subctx(x, t)):
                out.append((f"[{t.tid}] {l}", ok, d))
        return out + (report_reqs(x) if report else [])
    def text(x):
        out = [intro, "\nBLOCK EXAM - several incidents at once. No hints. Every part must be solved."]
        for i, t in enumerate(tasks, 1):
            out.append(f"\n{'#' * 6} PART {i}/{len(tasks)}: {t.title} {'#' * 6}\n" + task_text(t, subctx(x, t)))
        if report:
            out.append(report_text(x))
        return "\n".join(out)
    add(tid, title, text, setup, check, no_hints=True, bad=[b for t in tasks for b in t.bad],
        debrief="Block exam passed: you solved several incidents at once and documented them.")
    task_by_id(tid).parts = list(parts)

# ----------------------------------------------------------------- self check
def validate_course():
    ids, bad = set(), 0
    for m in MODULES:
        for t in m["tasks"]:
            if t.tid in ids:
                print(red(f"duplicate id {t.tid}")); bad += 1
            ids.add(t.tid)
            if not t.tid.startswith(f"M{m['n']:02d}-"):
                print(red(f"{t.tid} is in the wrong module")); bad += 1
            if not "-X" in t.tid and not t.hints:
                print(yellow(f"{t.tid}: no hints")); 
    print(f"{len(MODULES)} modules, {len(ids)} tasks, {sum(1 for i in ids if '-X' in i)} exams, {bad} problems")
    for m in MODULES:
        print(f"  {m['n']:>2} {m['track']:<16}{m['name']:<36}{len(m['tasks'])} tasks")
    return 1 if bad else 0


# =================================================================== UI / ENGINE
def task_text(t, x):
    return t.text(x) if callable(t.text) else t.text

def total_tasks():
    return len(ALL())

def level(prof):
    done = len([t for t in ALL() if t.tid in prof.d["completed"]])
    p = done / max(1, total_tasks())
    return "Beginner" if p < .25 else "Junior" if p < .55 else "Intermediate" if p < .85 else "Job-ready candidate" if p < 1 else "Graduate"

def mod_done(prof, m):
    return sum(1 for t in m["tasks"] if t.tid in prof.d["completed"])

def header(prof, title=None):
    print("\n" + bold("=" * 60))
    print(bold(f"   LAC - Linux Admin Labs  v{VERSION}"))
    if title:
        print(cyan(f"   {title}"))
    print(bold("=" * 60))

def stats_block(prof):
    mods_done = sum(1 for m in MODULES if mod_done(prof, m) == len(m["tasks"]))
    done = len([t for t in ALL() if t.tid in prof.d["completed"]])
    print("-" * 60)
    print(f"  Modules completed:  {mods_done} / {len(MODULES)}")
    print(f"  Tasks completed:    {done} / {total_tasks()}")
    print(f"  Failed checks:      {prof.n('FAIL')}    Incorrect actions: {red(str(prof.n('ERROR')))}    Hints used: {prof.n('HINT')}")
    print(f"  Current level:      {bold(level(prof))}")
    print("-" * 60)

def show_stats(prof):
    header(prof, "STATISTICS (saved outside the lab - survives resets)")
    print(f"  {'Module':<38}{'Done':>6}{'Starts':>8}{'Fails':>7}{'Errors':>8}{'Hints':>7}")
    for m in MODULES:
        pre = f"M{m['n']:02d}-"
        print(f"  {str(m['n']) + '. ' + m['name']:<38}{mod_done(prof, m):>3}/{len(m['tasks']):<2}{prof.n('START', pre) + prof.n('RESET', pre):>8}"
              f"{prof.n('FAIL', pre):>7}{prof.n('ERROR', pre):>8}{prof.n('HINT', pre):>7}")
    print("-" * 60)
    done = len(prof.d["completed"]) or 1
    print(f"  Totals: passes {prof.n('PASS')}, fails {prof.n('FAIL')}, errors {prof.n('ERROR')}, resets {prof.n('RESET')}, hints {prof.n('HINT')}")
    print(f"  Average incorrect actions per completed task: {prof.n('ERROR') / done:.1f}")
    print("\n  Last 12 events:")
    for e in prof.d["events"][-12:]:
        col = {"PASS": green, "FAIL": yellow, "ERROR": red}.get(e["type"], dim)
        print("   " + col(f"[{e['type']:<5}] {time.strftime('%m-%d %H:%M', time.localtime(e['ts']))} {e['task']} {e['detail'][:70]}"))
    ask("\n  Enter to go back ")

def start_task(prof, t, fresh=True):
    """(Re)build the lab for a task and register the attempt."""
    x = Ctx(t, prof)
    if fresh:
        print(dim("  cleaning previous lab ..."))
        cleanup_all()
        newhook = ensure_infra()
        x = Ctx(t, prof)
        x.work.mkdir(parents=True, exist_ok=True)
        x.own(x.work)
        prof.d["current"] = {"task": t.tid, "started": int(time.time()), "errs": [], "hints": 0}
        try:
            t.setup(x)
        except Exception as e:
            print(red(f"  Setup failed: {e}"))
            prof.d["current"] = None
            prof.save()
            return None
        x.save_secret()
        prof.log(t.tid, "START" if not prof.d.get("_reset") else "RESET")
        prof.d.pop("_reset", None)
        if newhook:
            print(yellow("  NOTE: command logging was just installed. Open a NEW ssh session for your work\n"
                         "        (or use the 'sh' command here) so your commands are recorded."))
    return x

def run_check(prof, t, x):
    scan_commands(prof, t, x)
    try:
        reqs = t.check(x)
    except Exception as e:
        print(red(f"  Internal checker error: {e}  (not counted)"))
        return False
    print()
    for label, ok, detail in reqs:
        print("  " + (green("[ OK ] ") if ok else red("[FAIL] ")) + label + (dim(f"  -> {detail}") if (detail and not ok) else ""))
    okn = sum(1 for r in reqs if r[1])
    if okn == len(reqs):
        prof.log(t.tid, "PASS", f"{okn}/{len(reqs)}")
        print(green(f"\n  *** TASK PASSED ({okn}/{len(reqs)}) ***"))
        if t.debrief:
            print(cyan("  Debrief: ") + t.debrief)
        return True
    failed = "; ".join(r[0] for r in reqs if not r[1])
    prof.log(t.tid, "FAIL", f"{okn}/{len(reqs)} ok. failed: {failed}")
    print(yellow(f"\n  Not yet: {okn}/{len(reqs)} requirements met. Fix the [FAIL] lines and run check again."))
    return False

ANS_RX = re.compile(r"\b([A-Za-z][A-Za-z_0-9]*)=<([^>\n]*)>")

def answer_targets(t, x):
    """[(title, work_dir, [(key, description), ...])] for this task (or for every part of a block exam)."""
    out = []
    if getattr(t, "parts", None):
        for pid in t.parts:
            pt = task_by_id(pid)
            sx = subctx(x, pt)
            keys = ANS_RX.findall(task_text(pt, sx))
            if keys:
                out.append((pt.tid, sx.work, keys))
    else:
        keys = ANS_RX.findall(task_text(t, x))
        if keys:
            out.append((t.tid, x.work, keys))
    return out

def answer_session(t, x):
    targets = answer_targets(t, x)
    if not targets:
        print(yellow("  This task has no answer file - its result is a system state or a file you create. Use  sh  and then  c."))
        return
    print(cyan("  ANSWER MODE: type the value you found for each key and press Enter. Empty line = keep the current value. 'x' = stop."))
    for title, work, keys in targets:
        f = work / "answers.txt"
        cur = answers_of(f)
        print(bold(f"\n  [{title}]  -> {f}"))
        for key, desc in keys:
            old = cur.get(key.lower(), "")
            v = ask(f"  {key}  ({desc[:70]})" + (f"  [{old}]" if old else "") + "\n    = ")
            if v == "x":
                break
            if v:
                cur[key.lower()] = v
        work.mkdir(parents=True, exist_ok=True)
        f.write_text("".join(f"{k}={v}\n" for k, v in cur.items()))
        if x.student != "root":
            sh(f"chown {x.student}:{x.student} {shlex.quote(str(f))}")
        print(green(f"  saved {len(cur)} answer(s). Run  c  to check."))

def answers_of(f):
    d = {}
    try:
        for ln in f.read_text().splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                d[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return d

def play(prof, t, resume=False):
    x = start_task(prof, t, fresh=not resume)
    if x is None:
        ask("  Enter to continue ")
        return
    def show():
        header(prof, f"{t.tid}  -  {t.title}")
        print(task_text(t, x))
        print("\n" + yellow("  >>> This prompt is NOT a Linux terminal. To run Linux commands type  sh  (a real shell opens; type  exit  to come back)"))
        print(yellow("      or open a SECOND ssh window to the VM and work there.  When you have the values type  a  - the trainer asks for them and writes answers.txt FOR YOU.  Then  c  checks."))
        print(dim("  Commands:  c=check  a=answer (no file editing!)  h=hint  r=reset  t=show task  m=command reference  sh=shell  s=stats  b=back  q=quit"))
    show()
    while True:
        cmd = ask("\n  task> ").lower()
        if cmd in ("c", "check"):
            if run_check(prof, t, x):
                prof.d["current"] = None
                prof.save()
                ask("  Enter to return to the module menu ")
                return
        elif cmd in ("h", "hint"):
            if t.no_hints:
                print(yellow("  Hints are disabled in the final exam."))
                continue
            used = prof.d["current"].get("hints", 0)
            if used >= len(t.hints):
                print(yellow("  No more hints. Re-read the task and the command reference (m)."))
                continue
            prof.d["current"]["hints"] = used + 1
            prof.log(t.tid, "HINT", f"hint {used + 1}")
            print(cyan(f"  HINT {used + 1}/{len(t.hints)}: ") + t.hints[used])
        elif cmd in ("r", "reset"):
            print("  Resetting rebuilds the task from scratch. Your statistics stay.")
            if ask("  Sure? [y/N] ").lower() == "y":
                prof.d["_reset"] = True
                nx = start_task(prof, t)
                if nx is None:
                    return
                x = nx
                show()
        elif cmd in ("a", "ans", "answer"):
            answer_session(t, x)
        elif cmd in ("t", "task"):
            show()
        elif cmd in ("m", "man", "ref"):
            m = MODULES[int(t.tid[1:3]) - 1]
            print("\n" + cyan(m["intro"]))
        elif cmd == "sh":
            rc = os.path.exists(BIN / "lab-rc.sh")
            base = ["bash", "--rcfile", str(BIN / "lab-rc.sh"), "-i"]
            print(dim("  Subshell as your normal user (use sudo as needed). Type 'exit' to return."))
            if x.student != "root":
                subprocess.call(["sudo", "-u", x.student, "-H"] + base, cwd=str(x.work))
            else:
                subprocess.call(base, cwd=str(x.work))
        elif cmd in ("s", "stats"):
            show_stats(prof); show()
        elif cmd in ("b", "back"):
            return
        elif cmd in ("q", "quit"):
            goodbye(prof)
        else:
            print(yellow(f"  '{cmd}' is not a trainer command. Linux commands do not run here:"))
            print(yellow("  type  sh  to open a shell (exit returns), or use a second ssh window. Trainer commands: c a h r t m sh s b q"))

def module_menu(prof, m):
    while True:
        header(prof, f"Module {m['n']}: {m['name']}")
        print(cyan(m["intro"]) + "\n")
        print(dim("  (tasks marked [EXAM] are block exams: no hints, several incidents at once)\n"))
        for i, t in enumerate(m["tasks"], 1):
            mark = green("[x]") if t.tid in prof.d["completed"] else "[ ]"
            cur = yellow(" <- in progress") if (prof.d.get("current") or {}).get("task") == t.tid else ""
            ex = yellow(" [EXAM]") if "-X" in t.tid else ""
            print(f"   {i}. {mark} {t.tid}  {t.title}{ex}{cur}")
        print("\n   B. Back")
        ch = ask("  select> ").lower()
        if ch in ("b", "back"):
            return
        if ch in ("q", "quit"):
            goodbye(prof)
        if not (ch.isdigit() and 1 <= int(ch) <= len(m["tasks"])):
            print(yellow(f"  Unknown choice '{ch}'. Type a task number, b (back) or q (quit) - English letters - then press Enter."))
            time.sleep(1.5)
        if ch.isdigit() and 1 <= int(ch) <= len(m["tasks"]):
            t = m["tasks"][int(ch) - 1]
            cur = prof.d.get("current")
            resume = False
            if cur and cur["task"] == t.tid:
                print("  This task is already in progress.")
                print("    c = CONTINUE with the same files   (Enter also continues)")
                print("    n = NEW start: delete the old files and build the task again (new random data)")
                resume = ask("  [c/n] > ").lower() not in ("n", "new")
            play(prof, t, resume)

def goodbye(prof):
    print(dim(f"\n  Profile saved: {PROFILE}"))
    print(dim("  Before destroying the VM:  sudo python3 run.py --export   (then scp the file out)"))
    sys.exit(0)

def export_profile(prof, path=None):
    user = os.environ.get("SUDO_USER") or "root"
    try:
        home = Path(pwd.getpwnam(user).pw_dir)
    except KeyError:
        home = Path("/root")
    p = Path(path) if path else home / f"linux-course-profile-{time.strftime('%Y%m%d-%H%M')}.json"
    prof.save()
    shutil.copy(PROFILE, p)
    if user != "root":
        sh(f"chown {user}:{user} {shlex.quote(str(p))}")
    print(green(f"  Profile exported: {p}") + dim("\n  Copy it to your main PC, e.g.:  scp USER@VM:" + str(p) + " ."))
    return p

def import_profile(prof, path):
    try:
        other = json.loads(Path(path).read_text())
        assert isinstance(other.get("events"), list)
    except Exception as e:
        print(red(f"  Cannot read profile {path}: {e}"))
        return
    n = prof.merge(other)
    print(green(f"  Imported. {n} new events merged. Completed tasks: {len(prof.d['completed'])}"))

def main_menu(prof):
    while True:
        header(prof)
        last = None
        for m in MODULES:
            if m["track"] != last:
                last = m["track"]
                print(cyan(f"  -- {last} --"))
            d = mod_done(prof, m)
            tag = green("done") if d == len(m["tasks"]) else f"{d}/{len(m['tasks'])}"
            print(f"  {m['n']:>2}. {m['name']:<36}[{tag}]")
        stats_block(prof)
        cur = prof.d.get("current")
        print("  S. Statistics      E. Export profile      I. Import profile")
        print(f"  R. Resume{(' (' + cur['task'] + ')') if cur else ' (nothing in progress)'}      W. Wipe the lab (cleanup)      Q. Quit")
        ch = ask("  > ").lower()
        if ch in ("q", "quit"):
            goodbye(prof)
        elif ch == "s":
            show_stats(prof)
        elif ch == "e":
            export_profile(prof); ask("  Enter ")
        elif ch == "i":
            import_profile(prof, ask("  path to profile json: ")); ask("  Enter ")
        elif ch == "w":
            if ask("  Remove every lab object (services, users, files)? Stats stay. [y/N] ").lower() == "y":
                cleanup_all(); prof.d["current"] = None; prof.save(); print(green("  Lab is clean."))
        elif ch == "r":
            if cur:
                t = next(t for t in ALL() if t.tid == cur["task"])
                play(prof, t, resume=True)
            else:
                print("  Nothing to resume."); time.sleep(1)
        elif ch.isdigit() and 1 <= int(ch) <= len(MODULES):
            module_menu(prof, MODULES[int(ch) - 1])
        else:
            print(yellow(f"  Unknown choice '{ch}'. Type a module number or s/e/i/r/w/q (English letters) and press Enter."))
            time.sleep(1.5)

def main():
    ap = argparse.ArgumentParser(description="Linux Admin Training Course")
    ap.add_argument("--export", nargs="?", const="", metavar="FILE", help="export the learning profile")
    ap.add_argument("--import", dest="imp", metavar="FILE", help="import (merge) a learning profile")
    ap.add_argument("--stats", action="store_true", help="print statistics and exit")
    ap.add_argument("--cleanup", action="store_true", help="remove all lab objects and exit")
    ap.add_argument("--validate", action="store_true", help="self-check the course definition and exit")
    ap.add_argument("--wipe-profile", action="store_true", help="DELETE the saved statistics (asks first)")
    a = ap.parse_args()
    if a.validate:
        sys.exit(validate_course())
    if os.geteuid() != 0:
        sys.exit("Run as root:  sudo python3 run.py")
    if not Path("/etc/debian_version").exists():
        print(yellow("WARNING: this is not Debian. The course is built for Debian; continue at your own risk."))
    prof = Profile()
    if a.export is not None:
        export_profile(prof, a.export or None); return
    if a.imp:
        import_profile(prof, a.imp); return
    if a.validate:
        sys.exit(validate_course())
    if a.stats:
        show_stats(prof); return
    if a.cleanup:
        cleanup_all(); print("lab cleaned"); return
    if a.wipe_profile:
        if input("Type DELETE to erase ALL statistics: ") == "DELETE":
            PROFILE.unlink(missing_ok=True); print("profile erased")
        return
    try:
        ensure_infra()
    except RuntimeError as e:
        sys.exit(red(str(e)))
    main_menu(prof)

