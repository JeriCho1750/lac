from course.core import *

module(18, "Cron, Timers and Boot Behaviour", """\
Cron:  /etc/cron.d/NAME lines have 6 time/user fields:  m h dom mon dow USER command    e.g.  */5 * * * * root /path/script.sh >> /var/log/x.log 2>&1
 Rules: file owned by root, NOT writable by group/others (mode 644), must end with a newline, use ABSOLUTE paths, script must be executable. Cron's PATH is minimal!
 Logs: journalctl -u cron   (cron logs every start:  CMD (...))      crontab -l / crontab -e  (per-user)
systemd timers: NAME.timer + NAME.service (Type=oneshot).  [Timer] OnBootSec=15s  OnUnitActiveSec=20s  (or OnCalendar=*-*-* 03:00:00)  [Install] WantedBy=timers.target
 systemctl enable --now NAME.timer     systemctl list-timers --all     systemd-analyze calendar '*-*-* 03:00'
Boot: 'enabled' = starts at boot (symlink in *.wants), 'active' = running now.  Both are independent!  systemctl is-enabled X ; systemctl is-active X ; systemctl --failed
You cannot reboot here: decide by is-enabled + is-active what WOULD happen after a reboot.""", track="Infrastructure")

# ---------------------------------------------------------------- C1  cron job not running
def s_m18t1(x):
    apt_install("cron")
    sh("systemctl enable --now cron")
    put(BIN / "lab-report.sh", "#!/bin/bash\ndate +%s >> /opt/linux-lab/run/cron-report.log\n", 0o644)
    put(RUN / "cron-report.log", "", 0o666)
    put("/etc/cron.d/lab-report", "* * * * * /opt/linux-lab/bin/lab-report.sh", 0o666)

def c_m18t1(x):
    q, f, s = [], Path("/etc/cron.d/lab-report"), BIN / "lab-report.sh"
    txt = f.read_text() if f.is_file() else ""
    st = f.stat() if f.is_file() else None
    q.append(R("/etc/cron.d/lab-report: owner root and NOT writable by group/others (mode 644)", bool(st) and st.st_uid == 0 and st.st_mode & 0o022 == 0, oct(st.st_mode & 0o777) if st else "missing"))
    q.append(R("file ends with a newline", txt.endswith("\n")))
    q.append(R("valid line: 5 time fields + USER root + absolute script path", re.search(r"^\*\s+\*\s+\*\s+\*\s+\*\s+root\s+/opt/linux-lab/bin/lab-report\.sh\b", txt, re.M) is not None))
    q.append(R("script is executable", os.access(s, os.X_OK)))
    q.append(R("cron service is active", svc("cron.service").get("ActiveState") == "active"))
    if all(r[1] for r in q):
        log = RUN / "cron-report.log"
        n0 = log.stat().st_size
        print(dim("  waiting for cron to run the job (up to 80 s) ..."))
        ok = False
        for _ in range(80):
            time.sleep(1)
            if log.stat().st_size > n0: ok = True; break
        q.append(R("cron really executed the job (log grew)", ok))
    return q

add("M18-T1", "A cron job that never runs",
    lambda x: f"""\
INCIDENT   /etc/cron.d/lab-report should run {BIN}/lab-report.sh EVERY MINUTE (it appends a timestamp to {RUN}/cron-report.log). Nothing happens.
TASK       1. ls -l /etc/cron.d/lab-report {BIN}/lab-report.sh    cat -A /etc/cron.d/lab-report     journalctl -u cron -n 20 --no-pager
           2. Find ALL faults (think: fields, permissions, newline at the end, executable bit) and fix them.
           3. Wait about a minute: the log file must grow:   tail {RUN}/cron-report.log
EXPECTED RESULT   The trainer checks the rules statically and then waits for a real cron run (check can take up to 80 s).""",
    s_m18t1, c_m18t1,
    hints=["Files in /etc/cron.d need a USER column between the time fields and the command.", "cron ignores files that are writable by others (journalctl shows 'INSECURE MODE') and lines without a final newline.", "chmod 644 /etc/cron.d/lab-report ; chmod +x script"],
    debrief="cron is picky and silent: check user column, mode 644, trailing newline, absolute paths and +x.")

# ---------------------------------------------------------------- C2  systemd timer
def s_m18t2(x):
    put(BIN / "lab-tick.sh", "#!/bin/bash\ndate +%s >> /opt/linux-lab/run/tick.log\n", 0o755)
    put(RUN / "tick.log", "", 0o666)
    put("/etc/systemd/system/lab-tick.service", "[Unit]\nDescription=Lab tick job\n\n[Service]\nType=oneshot\nExecStart=/opt/linux-lab/bin/lab-tick.sh\n")
    sh("systemctl daemon-reload")

def c_m18t2(x):
    q, f = [], Path("/etc/systemd/system/lab-tick.timer")
    txt = f.read_text() if f.is_file() else ""
    q.append(R("lab-tick.timer exists with OnBootSec and OnUnitActiveSec (or OnCalendar)", "OnBootSec" in txt and "OnUnitActiveSec" in txt or "OnCalendar" in txt))
    q.append(R("[Install] WantedBy=timers.target", re.search(r"^WantedBy=timers\.target", txt, re.M) is not None))
    q.append(R("timer is enabled", sh("systemctl is-enabled lab-tick.timer")[1].strip() == "enabled"))
    q.append(R("timer is active (waiting)", sh("systemctl is-active lab-tick.timer")[1].strip() == "active"))
    if all(r[1] for r in q):
        log = RUN / "tick.log"; n0 = log.stat().st_size
        print(dim("  waiting for the timer to fire (up to 50 s) ..."))
        ok = False
        for _ in range(50):
            time.sleep(1)
            if log.stat().st_size > n0: ok = True; break
        q.append(R("the timer really triggered the service (tick.log grew)", ok))
    return q

add("M18-T2", "Replace cron with a systemd timer",
    lambda x: f"""\
SCENARIO   The one-shot service lab-tick.service already exists (it appends a timestamp to {RUN}/tick.log). It needs a schedule.
TASK       Create /etc/systemd/system/lab-tick.timer:  first run 15 seconds after boot (OnBootSec=15s), then every 20 seconds after the previous run
           (OnUnitActiveSec=20s), installed into timers.target.  daemon-reload, enable --now, verify with:  systemctl list-timers --all | grep tick
EXPECTED RESULT   Timer enabled + active, log grows (check waits up to 50 s).""",
    s_m18t2, c_m18t2,
    hints=["[Timer]\nOnBootSec=15s\nOnUnitActiveSec=20s\n[Install]\nWantedBy=timers.target", "You enable/start the TIMER (lab-tick.timer), not the service."],
    debrief="Timers give you logs in the journal, dependencies and catch-up runs - and are the modern replacement for many cron jobs.")

# ---------------------------------------------------------------- C3  boot persistence audit
def s_m18t3(x):
    mk_service("lab-boot1", enable=True, start=True)
    mk_service("lab-boot2", enable=False, start=True)
    mk_service("lab-boot3", mode=0o644, enable=True, start=True)
    mk_service("lab-boot4", enable=False, start=False)

def c_m18t3(x):
    q = []
    for n in ("lab-boot1", "lab-boot2", "lab-boot3"):
        q += svc_reqs(n, enabled=True, hb=False)
    s4 = svc("lab-boot4.service")
    q.append(R("lab-boot4 (maintenance job) stays DISABLED", s4.get("UnitFileState") != "enabled", s4.get("UnitFileState", "")))
    q.append(R("lab-boot4 stays STOPPED", s4.get("ActiveState") != "active"))
    return q

add("M18-T3", "What survives a reboot?",
    lambda x: """\
SCENARIO   Four services: lab-boot1 .. lab-boot4. After the planned reboot tonight the PORTAL needs lab-boot1, lab-boot2 and lab-boot3 running.
           lab-boot4 is a manual maintenance job: it must NOT start at boot and must not run now.
TASK       1. For each unit: systemctl is-enabled UNIT ; systemctl is-active UNIT ; systemctl status UNIT
           2. Make the end state right (you cannot test with a real reboot - the states are the proof). One service is currently FAILED: find out why.
EXPECTED RESULT   boot1-3 enabled + active, boot4 disabled + inactive.""",
    s_m18t3, c_m18t3,
    hints=["A service can be running now but disabled (gone after reboot), or enabled but failing (203/EXEC).", "systemctl enable --now UNIT ; systemctl status shows 'Active: failed (Result: exit-code)' and the status code."],
    debrief="Always check BOTH is-active and is-enabled: 'it runs now' says nothing about the next boot.")

# ---------------------------------------------------------------- C4  failed units
def s_m18t4(x):
    sh("useradd -r -s /usr/sbin/nologin lab_runner")
    mk_service("lab-fail1", user="lab_missing", enable=False, start=True)
    body = ('#!/bin/bash\nC=/opt/linux-lab/run/fail2.conf\n[ -f "$C" ] || { echo "FATAL: $C not found" >&2; exit 78; }\n'
            'grep -q "^MODE=on$" "$C" || { echo "FATAL: MODE=on missing in $C" >&2; exit 78; }\n' + hb_script("lab-fail2").split("\n", 1)[1])
    mk_service("lab-fail2", body, enable=False, start=True)

def c_m18t4(x):
    q = []
    failed = sh("systemctl --failed --no-legend --plain")[1]
    q.append(R("`systemctl --failed` lists no lab-* unit", "lab-" not in failed, failed[:100]))
    q += svc_reqs("lab-fail1", enabled=False, hb=True)
    q += svc_reqs("lab-fail2", enabled=False, hb=True)
    return q

add("M18-T4", "systemctl --failed: clean up two broken units",
    lambda x: """\
INCIDENT   After the last deployment `systemctl --failed` shows two lab units. Monitoring wants a clean list.
TASK       For each failed unit read status + journal, find the REAL cause, fix it (not by deleting the unit!) and verify it runs:
             systemctl --failed ; systemctl status lab-fail1 lab-fail2 ; journalctl -u lab-fail1 -u lab-fail2 -n 20 --no-pager
           Unprivileged service user available on this host: lab_runner.   After fixing a unit file: daemon-reload, reset-failed, restart.
EXPECTED RESULT   Both units active, `systemctl --failed` clean.""",
    s_m18t4, c_m18t4,
    hints=["status=217/USER = the User= in the unit does not exist.", "The second one tells you in the journal which file and which line it wants."],
    debrief="Failed units each have a distinct exit status and journal line - read them before touching anything.")

compose("M18-X1", "BLOCK EXAM: scheduling and boot", "Cron, timers and boot state on one server.", ["M18-T1", "M18-T2", "M18-T3", "M18-T4"])
