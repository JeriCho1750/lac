from course.core import *

# ------------------------------------------------------------------ 8. Logs
module(8, "Logs and Troubleshooting", """\
journalctl -u NAME -n 50 --no-pager    journalctl -p err -b    journalctl --since '10 min ago'    journalctl -f
/var/log/: syslog, auth.log, nginx/error.log, nginx/access.log ...    tail -f FILE    grep -i error FILE    zcat FILE.gz
awk '{print $1}' LOG | sort | uniq -c | sort -rn | head      awk '$9>=500' LOG      cut -d' ' -f1
Method: 1) what exactly is the symptom? 2) read the ERROR message in the log 3) change ONE thing 4) re-test.
systemd start limit: after ~5 fast failures use  systemctl reset-failed NAME  before starting again.""", track="Foundation")

ACC_RX = re.compile(r'^(\S+) \S+ \S+ \[(\S+) \+0000\] "\w+ (\S+) HTTP/1\.1" (\d{3}) (\d+)')

def parse_access(lines):
    from collections import Counter
    ips, miss, e5, first5 = Counter(), Counter(), 0, None
    for ln in lines:
        m = ACC_RX.match(ln)
        if not m: continue
        ip, t, url, st, _ = m.groups()
        ips[ip] += 1
        if st == "404": miss[url] += 1
        if st.startswith("5"):
            e5 += 1
            first5 = first5 or t.split(":", 1)[1]
    return len(lines), e5, ips, miss, first5

def s_m08t1(x):
    r = random.Random()
    paths = ["/", "/index.html", "/about", "/login", "/api/items", "/api/orders", "/static/app.js", "/static/site.css", "/contact"]
    missing = ["/wp-login.php", "/old-page", "/favicon.ico", "/admin", "/.env"]
    while True:
        ips = [f"10.0.{r.randint(0,5)}.{r.randint(1,254)}" for _ in range(25)]
        lines, t = [], 8 * 3600
        for _ in range(800):
            t += r.randint(1, 5)
            ip = r.choice(ips[:5]) if r.random() < 0.4 else r.choice(ips)
            st = r.choices([200, 301, 404, 500, 502, 503], [70, 5, 14, 4, 4, 3])[0]
            url = r.choice(missing) if st == 404 else r.choice(paths)
            ts = f"03/Mar/2025:{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}"
            lines.append(f'{ip} - - [{ts} +0000] "GET {url} HTTP/1.1" {st} {r.randint(200,9000)} "-" "curl/7.88"')
        _, e5, ips_c, miss, _f = parse_access(lines)
        a, b = ips_c.most_common(2), miss.most_common(2)
        if a[0][1] > a[1][1] and b[0][1] > b[1][1] and e5 > 0:
            break
    put(x.work / "access.log", "\n".join(lines) + "\n")
    x.own(x.work)

def c_m08t1(x):
    lines = (x.work / "access.log").read_text().splitlines()
    total, e5, ips, miss, first5 = parse_access(lines)
    a, q = answers(x), []
    chk(q, a, "total_requests", total, "total number of requests", "int")
    chk(q, a, "count_5xx", e5, "number of responses with status 5xx", "int")
    chk(q, a, "top_ip", ips.most_common(1)[0][0], "client IP with the most requests")
    chk(q, a, "top_404_url", miss.most_common(1)[0][0], "URL that returns 404 most often")
    chk(q, a, "first_5xx_time", first5, "time (HH:MM:SS) of the first 5xx response")
    return q

add("M08-T1", "Web access log forensics",
    lambda x: f"""\
INCIDENT #008   Users report errors on the website. Analyse the access log {x.work}/access.log
                (format: IP - - [date:HH:MM:SS +0000] "GET /url HTTP/1.1" STATUS BYTES ...).
TASK   Create {x.work}/answers.txt :
    total_requests=<number of lines>
    count_5xx=<number of requests whose STATUS starts with 5>
    top_ip=<client IP with the most requests>
    top_404_url=<URL most often answered with 404>
    first_5xx_time=<HH:MM:SS of the FIRST 5xx response>
USE   wc -l, awk, grep, sort, uniq -c.   The status code is field $9 when split by spaces.
EXPECTED RESULT   Five correct lines.""",
    s_m08t1, c_m08t1,
    hints=["awk '$9 ~ /^5/' access.log | wc -l", "awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -3",
           "awk '$9==404 {print $7}' access.log | sort | uniq -c | sort -rn | head -3 ; first 5xx: awk '$9 ~ /^5/' access.log | head -1  then read the time"],
    debrief="Pipelines (awk | sort | uniq -c | sort -rn) answer most log questions in seconds.")

def s_m08t2(x):
    conf = x.work / "batch.conf"
    put(BIN / "lab-batch.sh", f"""#!/bin/bash
CONF={conf}
[ -r "$CONF" ] || {{ echo "FATAL: configuration file $CONF not found" >&2; exit 78; }}
source "$CONF"
[ -n "${{BATCH_MODE:-}}" ] || {{ echo "FATAL: BATCH_MODE is not set in $CONF (allowed: nightly|hourly)" >&2; exit 78; }}
case "$BATCH_MODE" in nightly|hourly) ;; *) echo "FATAL: invalid BATCH_MODE=$BATCH_MODE" >&2; exit 64;; esac
[ -d "${{OUTPUT_DIR:-/nonexistent}}" ] || {{ echo "FATAL: OUTPUT_DIR must be an existing directory (got '${{OUTPUT_DIR:-}}')" >&2; exit 73; }}
while true; do date +%s > "$OUTPUT_DIR/batch.done"; sleep 2; done
""", 0o755)
    put("/etc/systemd/system/lab-batch.service", """[Unit]
Description=Lab nightly batch job

[Service]
ExecStart=/opt/linux-lab/bin/lab-batch.sh
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
""")
    sh("systemctl daemon-reload; systemctl start lab-batch")
    x.own(x.work)

def c_m08t2(x):
    q, s = [], svc("lab-batch.service")
    conf = x.work / "batch.conf"
    txt = conf.read_text() if conf.exists() else ""
    q.append(R("batch.conf sets BATCH_MODE=nightly", re.search(r"^\s*BATCH_MODE=\"?nightly\"?\s*$", txt, re.M) is not None))
    q.append(R(f"batch.conf sets OUTPUT_DIR={x.work}/out", re.search(rf"^\s*OUTPUT_DIR=\"?{re.escape(str(x.work))}/out/?\"?\s*$", txt, re.M) is not None))
    q.append(R("service lab-batch is active", s.get("ActiveState") == "active"))
    f = x.work / "out/batch.done"
    time.sleep(2.5)
    age = time.time() - int(f.read_text()) if f.exists() and f.read_text().strip().isdigit() else 999
    q.append(R("out/batch.done is fresh (the job really runs)", age < 6))
    q.append(R("journal was consulted (journalctl / systemctl status)", x.used(r"(journalctl|systemctl\s+status)") is not False))
    return q

add("M08-T2", "A batch service that keeps failing",
    lambda x: f"""\
INCIDENT #009
  Service lab-batch (script {BIN}/lab-batch.sh) must run in NIGHTLY mode and write its heartbeat file
  {x.work}/out/batch.done . It crashes immediately and systemd gave up.
RULES   Do NOT edit the script. All fixes go into the config file the script reads, plus system state.
TASK
  1. systemctl status lab-batch ; journalctl -u lab-batch -n 20 --no-pager     (read the FATAL messages!)
  2. Fix the problems ONE AT A TIME; each restart reveals the next message. You need:
       a config file with BATCH_MODE=nightly and OUTPUT_DIR={x.work}/out   (and that directory)
  3. If systemd says 'start-limit-hit' use  systemctl reset-failed lab-batch  then start again.
EXPECTED RESULT   Service active, batch.done refreshed every 2 seconds.""",
    s_m08t2, c_m08t2,
    hints=["The first FATAL line names the missing file. Create it with the settings in VAR=value form.", "mkdir the OUTPUT_DIR (journal tells you when it is missing)."],
    debrief="Read the exact error, fix one cause, retest. Services often hide a chain of faults.")

# ---------------------------------------------------------------- M08-T3  logrotate
def s_m08t3(x):
    apt_install("logrotate")
    put(x.work / "logs/app.log", b"2025-01-01 INFO line\n" * 150000)

def c_m08t3(x):
    q, f = [], Path("/etc/logrotate.d/lab-app")
    txt = f.read_text() if f.is_file() else ""
    q.append(R("/etc/logrotate.d/lab-app exists and names the app.log path", str(x.work / "logs/app.log") in txt))
    for pat, lab in ((r"\bsize\s+1[mM]\b", "rotate when larger than 1M (size 1M)"), (r"\brotate\s+4\b", "keep 4 rotations"), (r"\bcompress\b", "compress"),
                     (r"\bdelaycompress\b", "delaycompress"), (r"\bmissingok\b", "missingok"), (r"\bnotifempty\b", "notifempty")):
        q.append(R(lab, re.search(pat, txt) is not None))
    rc, out = sh(f"logrotate -d {f}")
    q.append(R("`logrotate -d` (dry run) reports no errors", f.is_file() and rc == 0 and "error" not in out.lower(), out[-120:]))
    q.append(R("rotation really happened (app.log.1 exists and app.log is small)", (x.work / "logs/app.log.1").exists() and (x.work / "logs/app.log").stat().st_size < 1_000_000))
    return q

add("M08-T3", "Log rotation with logrotate",
    lambda x: f"""\
INCIDENT   {x.work}/logs/app.log is ~3 MB and grows forever. Configure rotation.
TASK
  1. Create /etc/logrotate.d/lab-app for that file:  rotate when it exceeds 1M, keep 4 old logs, compress (but delaycompress),
     missingok, notifempty.
  2. Test the syntax WITHOUT rotating:  logrotate -d /etc/logrotate.d/lab-app
  3. Force one rotation now:  logrotate -f /etc/logrotate.d/lab-app   and look at the result with ls -l {x.work}/logs
     (if logrotate complains about 'insecure permissions' add the line  su root root  to the block).
EXPECTED RESULT   app.log.1 exists, app.log is small again.""",
    s_m08t3, c_m08t3,
    hints=["/path/app.log {\n    size 1M\n    rotate 4\n    ...\n}", "-d = debug/dry-run, -f = force."],
    debrief="logrotate prevents full disks; always dry-run (-d) a new rule before trusting it.")

# ---------------------------------------------------------------- M08-T4  rotated + gz logs
def g_m08t4(x, r):
    import gzip
    d = x.work / "logs"
    d.mkdir(parents=True, exist_ok=True)
    per, total = {}, 0
    for name, day in (("app.log", 5), ("app.log.1", 4), ("app.log.2.gz", 3), ("app.log.3.gz", 2)):
        lines, n = [], 0
        for i in range(r.randint(120, 260)):
            lvl = r.choice(["INFO", "INFO", "INFO", "ERROR"])
            n += lvl == "ERROR"
            lines.append(f"2025-03-0{day} {i % 24:02d}:{i % 60:02d}:00 {lvl} request {i}")
        data = ("\n".join(lines) + "\n").encode()
        if name.endswith(".gz"):
            with gzip.open(d / name, "wb") as g: g.write(data)
        else:
            (d / name).write_bytes(data)
        per[name] = n; total += n
    worst = max(per, key=per.get)
    ties = sorted(per.values())
    if ties[-1] == ties[-2]:            # make the maximum unique
        return g_m08t4(x, r)
    return {"total_errors": (total, "ERROR lines in ALL four files, compressed ones included", "int"),
            "worst_file": (worst, "name of the file with the most ERROR lines"),
            "errors_in_gz_files": (per["app.log.2.gz"] + per["app.log.3.gz"], "ERROR lines only in the two .gz files", "int")}

answers_task("M08-T4", "Searching rotated and compressed logs",
    lambda x: f"""\
INCIDENT   The error started days ago - the evidence is spread over {x.work}/logs/ (app.log, app.log.1 and gzip-compressed app.log.2.gz, app.log.3.gz).
USE        zgrep -c ERROR FILE    zcat FILE.gz | grep ...    grep -c ERROR app.log*   (zgrep also reads plain files)""",
    g_m08t4,
    hints=["zgrep -c ERROR app.log* prints a count per file (works for .gz too).", "Add the counts together for total_errors."],
    debrief="zgrep/zcat let you search old compressed logs without unpacking them.")

compose("M08-X1", "BLOCK EXAM: logs and troubleshooting", "Analyse logs, repair a failing job and configure rotation.", ["M08-T1", "M08-T2", "M08-T3", "M08-T4"])
