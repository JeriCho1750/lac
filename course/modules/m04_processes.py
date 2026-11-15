from course.core import *

# ------------------------------------------------------------------ 4. Processes and services
module(4, "Processes and Services", """\
ps aux | grep NAME    pgrep -af NAME    top / htop    ls -l /proc/PID/fd    lsof FILE    fuser -v FILE    ss -tulpn
Signals: kill PID = SIGTERM(15, polite: process cleans up)   kill -STOP PID = pause (freeze)   kill -CONT PID = resume
         kill -KILL PID (=-9) = LAST RESORT, process cannot clean up.   Always check PID + command line BEFORE killing.
         Do NOT use killall/pkill by name when unsure - you may hit the wrong process.
systemd: systemctl status|start|stop|restart|enable|disable|daemon-reload|reset-failed NAME
         journalctl -u NAME -n 50 --no-pager     journalctl -xe     systemctl cat NAME
Unit file: /etc/systemd/system/NAME.service  [Unit] [Service] ExecStart= User= Restart= [Install] WantedBy=multi-user.target
After editing a unit: systemctl daemon-reload.   'enable' = start at boot, 'start' = start now.""", track="Foundation")

def s_m04t1(x):
    lock = x.work / "maintenance.lock"
    put(lock, "locked\n")
    h = spawn("maintenance-holder", "--hold", lock)
    spawn("report-writer", "--hold", x.work / "report.tmp")
    spawn("inventory-sync")
    x.secret = {"pid": h}
    x.own(x.work)

def c_m04t1(x):
    q, a = [], answers(x)
    h, w, s = proc("maintenance-holder"), proc("report-writer"), proc("inventory-sync")
    lock = x.work / "maintenance.lock"
    chk(q, a, "holder_pid", x.secret["pid"], "answer holder_pid is the PID that held the file", "int")
    chk(q, a, "holder_name", "maintenance-holder", "answer holder_name is correct")
    q.append(R("investigated before acting (ps / lsof / fuser / /proc)", x.used(r"\b(lsof|fuser|ps|pgrep|/proc)\b") is not False, "no inspection command found in your shell history"))
    q.append(R("maintenance-holder has exited", not h.alive))
    if not h.alive and "TERM" not in h.sigs:
        x.error("maintenance-holder died WITHOUT receiving SIGTERM - you used SIGKILL (or another signal). The task required SIGTERM")
    q.append(R("it was stopped with SIGTERM (clean shutdown)", "TERM" in h.sigs))
    q.append(R("lock file is no longer held by any process", not fd_holders(lock)))
    for p in (w, s):
        if not p.alive:
            x.error(f"unrelated process {p.name} was killed - it should have been left running")
    q.append(R("report-writer and inventory-sync are still running", w.alive and s.alive))
    return q

add("M04-T1", "Who holds this file? (process + signal)",
    lambda x: f"""\
INCIDENT #001
  A file cannot be replaced because another process is holding it open:
      {x.work}/maintenance.lock
  Three helper processes run on this server (their names appear in the command line of `ps aux`):
      maintenance-holder   - DISPOSABLE training process, created for this exercise. SAFE TO STOP.
      report-writer        - belongs to someone else. DO NOT TOUCH.
      inventory-sync       - belongs to someone else. DO NOT TOUCH.

TASK
  1. Find out which process has the lock file open (lsof / fuser). Note its PID and name.
  2. Inspect it before acting:  ps -fp PID   and   ls -l /proc/PID/fd
  3. Write your findings into {x.work}/answers.txt :
        holder_pid=<PID>
        holder_name=<process name from the command line>
  4. Stop the holder with SIGTERM (a polite stop - NOT kill -9). Use the PID, not killall/pkill.
  5. Verify: the process is gone, and `lsof {x.work}/maintenance.lock` shows nothing.
  6. Verify that report-writer and inventory-sync still run.
EXPECTED RESULT   Only maintenance-holder is stopped, cleanly.""",
    s_m04t1, c_m04t1,
    hints=["sudo lsof FILE   or   sudo fuser -v FILE", "kill PID with no signal option sends SIGTERM.", "pgrep -af labproc shows all helper processes with their arguments."],
    bad=[(r"\bkill\s+(-9|-KILL|-s\s*(9|KILL)|-SIGKILL)\b", "SIGKILL used - the task requires SIGTERM first"),
         (r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="Always: identify -> inspect -> choose the gentlest signal -> verify. SIGKILL skips cleanup and can corrupt data.")

def s_m04t2(x):
    spawn("report-cruncher", "--cpu")
    spawn("log-tailer", "--hold", x.work / "tail.log")
    spawn("billing-sim")
    spawn("stuck-sync", "--ignore-term")
    x.own(x.work)

def c_m04t2(x):
    q = []
    cr, lt, bi, st = proc("report-cruncher"), proc("log-tailer"), proc("billing-sim"), proc("stuck-sync")
    if not cr.alive and "TERM" not in cr.sigs:
        x.error("report-cruncher was killed without SIGTERM")
    q.append(R("report-cruncher: stopped with SIGTERM", not cr.alive and "TERM" in cr.sigs))
    if not lt.alive:
        x.error("log-tailer was killed - it should only be PAUSED (SIGSTOP)")
    q.append(R("log-tailer: PAUSED (state T), still alive", lt.alive and lt.state == "T"))
    if not bi.alive or bi.state == "T":
        x.error("billing-sim was disturbed - it had to be LEFT ALONE")
    q.append(R("billing-sim: untouched (running, not stopped)", bi.alive and bi.state != "T"))
    if not st.alive and "TERM-ignored" not in st.sigs:
        x.error("stuck-sync was SIGKILLed without trying SIGTERM first (procedure violation) - reset the task")
    q.append(R("stuck-sync: SIGTERM tried first and ignored", "TERM-ignored" in st.sigs))
    q.append(R("stuck-sync: finally terminated (SIGKILL)", not st.alive))
    return q

add("M04-T2", "Process triage: kill, pause, leave, escalate",
    lambda x: f"""\
INCIDENT #002
  The server is slow. Four processes are running (find them with `ps aux` / `top` / `pgrep -af labproc`).
  Your manager decided exactly what to do with each one:

  +-----------------+----------------------------------------------------------------------+
  | report-cruncher | burns CPU, disposable batch job  -> STOP IT with SIGTERM (terminate) |
  | log-tailer      | holds a file open, owner wants it later -> PAUSE it (SIGSTOP), keep alive |
  | billing-sim     | production billing, healthy          -> LEAVE IT ALONE                |
  | stuck-sync      | hung, may ignore polite signals      -> try SIGTERM first, check, then |
  |                 |                                         SIGKILL only if it survived  |
  +-----------------+----------------------------------------------------------------------+

TASK
  Perform exactly these actions using PIDs. Verify each with `ps -o pid,stat,cmd -p PID`
  (state T = stopped, Z = zombie, S/R = running).
EXPECTED RESULT   cruncher gone (clean), tailer frozen, billing running, stuck-sync gone after escalation.
NOTE  You cannot cheat the order for stuck-sync: it records every SIGTERM it ignores.""",
    s_m04t2, c_m04t2,
    hints=["kill -STOP PID pauses; kill -CONT PID resumes.", "After kill PID, run ps -p PID again. If it is still there and ignores SIGTERM, then use kill -KILL PID."],
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="Escalation ladder: SIGTERM -> wait/verify -> SIGKILL. SIGSTOP freezes a process without losing its state.")

def s_m04t3(x):
    put(BIN / "lab-heartbeat.sh", "#!/bin/bash\nwhile true; do date +%s > /opt/linux-lab/run/heartbeat; sleep 2; done\n", 0o644)
    put("/etc/systemd/system/lab-heartbeat.service", """[Unit]
Description=Lab heartbeat writer

[Service]
ExecStart=/opt/linux-lab/bin/lab-heartbeat.sh
Restart=no

[Install]
WantedBy=multi-user.target
""")
    sh("systemctl daemon-reload; systemctl start lab-heartbeat.service")
    x.own(x.work)

def c_m04t3(x):
    q, s = [], svc("lab-heartbeat.service")
    d = x.work / "diagnosis.txt"
    q.append(R("diagnosis.txt contains the exit status number from systemctl status (203)", d.is_file() and "203" in d.read_text()))
    q.append(R("service is active (running)", s.get("ActiveState") == "active"))
    q.append(R("service is enabled at boot", s.get("UnitFileState") == "enabled"))
    hb = RUN / "heartbeat"
    time.sleep(2.5)
    age = time.time() - int(hb.read_text()) if hb.exists() and hb.read_text().strip().isdigit() else 999
    q.append(R("heartbeat file is being updated (< 6 s old)", age < 6))
    q.append(R("investigated with systemctl status / journalctl", x.used(r"(systemctl\s+status|journalctl)") is not False))
    return q

add("M04-T3", "A service that will not start",
    lambda x: f"""\
INCIDENT #003
  Service lab-heartbeat should write a timestamp into {RUN}/heartbeat every 2 seconds.
  It is NOT running. Monitoring is red.

TASK
  1. Diagnose:  systemctl status lab-heartbeat   and   journalctl -u lab-heartbeat -n 20 --no-pager
  2. Write the numeric exit status systemd reports (status=NNN/WORD) into {x.work}/diagnosis.txt
  3. Fix the ROOT CAUSE (do not just run the script by hand in the background).
  4. Start the service and make it start automatically on boot.
  5. Verify:  systemctl is-active lab-heartbeat ; systemctl is-enabled lab-heartbeat ; cat {RUN}/heartbeat
EXPECTED RESULT   Service active + enabled, heartbeat updating.""",
    s_m04t3, c_m04t3,
    hints=["status=203/EXEC means systemd could not execute the file. Look at the file: ls -l.", "chmod +x on the script, then systemctl restart.",
           "enable = start on boot; start/restart = now. You usually need both."],
    debrief="203/EXEC = cannot execute (missing +x, bad path, bad shebang). Read the logs first, guess never.")

def s_m04t4(x):
    sh("useradd -r -s /usr/sbin/nologin lab_svc")
    put(BIN / "lab-hello.sh", '#!/bin/bash\nwhile true; do echo "hello from $(id -un) at $(date +%T)" >> /opt/linux-lab/run/hello.log; sleep 2; done\n', 0o755)
    put(RUN / "hello.log", "", 0o666)

def c_m04t4(x):
    q, s = [], svc("lab-hello.service")
    q.append(R("unit file /etc/systemd/system/lab-hello.service exists", Path("/etc/systemd/system/lab-hello.service").is_file()))
    q.append(R("Description is not empty", bool(s.get("Description")) and s.get("Description") != "lab-hello.service"))
    q.append(R("runs as user lab_svc", s.get("User") == "lab_svc"))
    q.append(R("Restart=on-failure", s.get("Restart") == "on-failure"))
    q.append(R("active (running)", s.get("ActiveState") == "active"))
    q.append(R("enabled at boot", s.get("UnitFileState") == "enabled"))
    n1 = (RUN / "hello.log").stat().st_size
    time.sleep(2.5)
    q.append(R("hello.log is growing and written by lab_svc", (RUN / "hello.log").stat().st_size > n1 and "hello from lab_svc" in (RUN / "hello.log").read_text()))
    return q

add("M04-T4", "Write your own systemd service",
    lambda x: f"""\
SCENARIO   A developer gives you a script and asks you to run it as a proper service.
  Script: {BIN}/lab-hello.sh   (appends a line to {RUN}/hello.log every 2 seconds)
  The unprivileged service account lab_svc already exists.
TASK
  Create /etc/systemd/system/lab-hello.service so that it:
    - has a meaningful Description
    - runs the script as user lab_svc (not root)
    - restarts automatically if it fails (Restart=on-failure, RestartSec=3)
    - starts at boot (WantedBy=multi-user.target)
  Then: daemon-reload, enable + start it, and verify with status and the log file.
EXPECTED RESULT   Service active, enabled, running as lab_svc.""",
    s_m04t4, c_m04t4,
    hints=["Sections needed: [Unit] Description=  [Service] ExecStart= User= Restart= RestartSec=  [Install] WantedBy=",
           "systemctl daemon-reload after creating the file. systemctl enable --now lab-hello"],
    debrief="You wrote a production-style unit: least-privilege user, auto-restart, boot persistence.")

# ---------------------------------------------------------------- M04-T5  unit dependencies
def s_m04t5(x):
    mk_service("lab-db-sim", start=False, desc="Lab database simulator")
    body = ('#!/bin/bash\nsystemctl is-active --quiet lab-db-sim || { echo "FATAL: database lab-db-sim is not running" >&2; exit 1; }\n'
            'while true; do date +%s > /opt/linux-lab/run/lab-app-sim.hb; sleep 2; done\n')
    mk_service("lab-app-sim", body, start=True, desc="Lab application (needs the database)")

def c_m04t5(x):
    q = []
    s = sh("systemctl show lab-app-sim.service -p Requires -p After")[1]
    q.append(R("lab-app-sim declares Requires=lab-db-sim.service", re.search(r"^Requires=.*lab-db-sim\.service", s, re.M) is not None))
    q.append(R("lab-app-sim declares After=lab-db-sim.service (start order)", re.search(r"^After=.*lab-db-sim\.service", s, re.M) is not None))
    q += svc_reqs("lab-db-sim", hb=True)
    q += svc_reqs("lab-app-sim", hb=True)
    return q

add("M04-T5", "Service dependencies and start order",
    lambda x: """\
INCIDENT #004b   lab-app-sim (the application) fails after every boot with 'database lab-db-sim is not running'.
                 The database service lab-db-sim exists but is neither started nor enabled.
TASK
  1. Read the failure:  systemctl status lab-app-sim ; journalctl -u lab-app-sim -n 10 --no-pager
  2. Fix it the systemd way: lab-app-sim must REQUIRE lab-db-sim and start AFTER it
     (edit /etc/systemd/system/lab-app-sim.service, then systemctl daemon-reload).
  3. Enable BOTH services for boot and start the application (the database must come up automatically).
  Do NOT 'fix' it by sleeping in the script.
EXPECTED RESULT   Both services active+enabled; `systemctl show lab-app-sim -p Requires -p After` lists lab-db-sim.""",
    s_m04t5, c_m04t5,
    hints=["In [Unit]: Requires=lab-db-sim.service  and  After=lab-db-sim.service", "systemctl enable --now lab-db-sim lab-app-sim ; reset-failed if systemd gave up"],
    debrief="Requires= pulls the dependency in, After= orders the start. Without both, boot order is random.")

# ---------------------------------------------------------------- M04-T6  journalctl facts
def g_m04t6(x, r):
    tag = "lab-evt-" + rnd_word(r, 5)
    n_err, n_warn, first = 0, 0, None
    for i in range(1, r.randint(25, 40)):
        pri = r.choice(["info", "info", "warning", "err", "err"] if i > 3 else ["info"])
        sh(f"logger -t {tag} -p user.{pri} 'job-{i} {pri} event'")
        if pri == "err":
            n_err += 1; first = first or i
        if pri == "warning": n_warn += 1
    time.sleep(1.5)
    sh("journalctl --sync")
    x.secret_tag = tag
    return {"tag": (tag, "the log tag used by the incident (shown in the task)"),
            "errors": (n_err, "number of entries with priority err for that tag", "int"),
            "warnings_and_worse": (n_warn + n_err, "number of entries with priority warning OR worse", "int"),
            "first_error_job": (first, "the job number N of the FIRST error entry ('job-N')", "int")}

answers_task("M04-T6", "Query the journal like a pro",
    lambda x: f"""\
INCIDENT   An unknown service logged events into the system journal under the tag  {x.secret['spec']['tag'][0]}
           (journalctl -t TAG). Answer from the journal - not from memory.
USE        journalctl -t TAG --no-pager    journalctl -t TAG -p err    (-p warning = warning AND everything more severe)
           journalctl -t TAG -o cat --no-pager | head -3""",
    g_m04t6,
    hints=["journalctl -t TAG -p err --no-pager -o cat | wc -l", "-p warning includes err, crit, alert, emerg - that is what 'and worse' means.", "journalctl -t TAG -p err -o cat | head -1"],
    debrief="journalctl filters by unit, tag, priority and time - the first stop for every incident.")

compose("M04-X1", "BLOCK EXAM: processes and services",
        "The server is in a bad state: stuck processes, failing services and broken dependencies.",
        ["M04-T1", "M04-T2", "M04-T3", "M04-T5"])
