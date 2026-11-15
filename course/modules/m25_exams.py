from course.core import *

# ------------------------------------------------------------------ 15. Final exam
module(25, "Final Practical Exam", """\
Four final exams (A-D). No hints, no theory - work like on a real job. Method: reproduce -> read logs -> find ALL causes -> fix one at a time -> verify end-to-end -> write the report.
Report format (Markdown):  ## Summary   ## Root causes   ## Fixes applied   ## Prevention   (a few real sentences each).""", track="Exams")

def s_m15t1(x):
    ensure_nginx()
    sh("useradd -r -s /usr/sbin/nologin lab_web")
    spawn("billing-sim")
    put("/etc/systemd/system/lab-backend.service", f"""[Unit]
Description=Customer portal backend

[Service]
User=lab_webb
ExecStart=/usr/bin/python3 {BIN}/labproc.py exam-backend --http 9201
Restart=on-failure

[Install]
WantedBy=multi-user.target
""")
    put(x.work / "static/status.txt", "STATIC-OK\n", 0o600)
    (x.work / "static").chmod(0o700)
    put("/etc/nginx/conf.d/lab-exam.conf", f"""server {{
    listen 8090;
    location / {{ proxy_pass http://127.0.0.1:9210; }}
    location /static/ {{ alias {x.work}/static/; }}
}}
""")
    sh("systemctl daemon-reload; systemctl start lab-backend; nginx -t && systemctl reload nginx")

def c_m15t1(x):
    q, s = [], svc("lab-backend.service")
    code, body = http("http://127.0.0.1:8090/")
    q.append(R("GET / through nginx returns 200 from the backend", code == 200 and "LAB-OK exam-backend" in body, f"status {code}"))
    code, body = http("http://127.0.0.1:8090/static/status.txt")
    q.append(R("GET /static/status.txt returns 200 'STATIC-OK'", code == 200 and "STATIC-OK" in body, f"status {code}"))
    q.append(R("lab-backend.service active and enabled", s.get("ActiveState") == "active" and s.get("UnitFileState") == "enabled"))
    q.append(R("backend runs as lab_web (not root)", s.get("User") == "lab_web"))
    q.append(R("nginx -t passes", sh("nginx -t")[0] == 0))
    if not proc("billing-sim").alive:
        x.error("billing-sim (production) was killed!")
    q.append(R("billing-sim (unrelated production process) still running", proc("billing-sim").alive))
    rp = x.work / "incident-report.md"
    txt = rp.read_text() if rp.is_file() else ""
    secs = {m.group(1).strip().lower(): m.group(2) for m in re.finditer(r"^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)", txt, re.M | re.S)}
    need = ("summary", "root causes", "fixes applied", "prevention")
    q.append(R("incident-report.md has the 4 sections, each with >= 12 words", all(len(secs.get(n, "").split()) >= 12 for n in need), "sections found: " + ", ".join(secs) if secs else "file missing"))
    low = txt.lower()
    q.append(R("report names the user fault, the proxy port fault and the permission fault",
               re.search(r"lab_webb|user=|217", low) is not None and re.search(r"9210|9201|proxy_pass|502", low) is not None and re.search(r"403|permission|chmod", low) is not None))
    return q

add("M25-X1", "FINAL EXAM: Customer portal is down",
    lambda x: f"""\
INCIDENT #100  (priority: CRITICAL)
  The customer portal is down. Public entry point: http://127.0.0.1:8090/ (nginx, config /etc/nginx/conf.d/lab-exam.conf)
  Components:  nginx -> backend service lab-backend (port 9201)   and a static page at /static/status.txt
  Also running on this host: billing-sim (production, unrelated - do not disturb it).
  Both URLs must work:
      curl -i http://127.0.0.1:8090/               -> 200, text 'LAB-OK exam-backend'
      curl -i http://127.0.0.1:8090/static/status.txt -> 200, text 'STATIC-OK'
REQUIREMENTS
  - The backend must run as the unprivileged user lab_web (already exists) and start on boot.
  - There are SEVERAL independent faults across systemd, nginx and file permissions. Find them all with logs.
  - No chmod 777, do not restart or kill billing-sim, do not rewrite the service from scratch.
  - Write the incident report {x.work}/incident-report.md with the sections
        ## Summary   ## Root causes   ## Fixes applied   ## Prevention
    (at least 12 words in each: what broke, why, what you changed, how to prevent a repeat).
No hints in the exam.""",
    s_m15t1, c_m15t1, no_hints=True,
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="You handled a multi-fault outage end-to-end and documented it - exactly the job of a junior sysadmin.")

compose("M25-X2", "FINAL EXAM B: night shift on the infrastructure",
        "Night shift. The on-call phone rings four times in a row: a failing batch job, wrong boot state, local mail not delivered and the backup script still missing.",
        ["M08-T2", "M18-T3", "M15-T1", "M17-T3"])

compose("M25-X3", "FINAL EXAM C: hosting day (DNS, TLS, proxy, database)",
        "Customer sites are down for four different reasons: DNS zone, HTTPS configuration, a proxy and a database connection.",
        ["M09-T2", "M11-T2", "M12-T3", "M14-T1"])

compose("M25-X4", "FINAL EXAM D: automation and documentation",
        "The manager wants it all by Monday: a repaired Ansible playbook, a merged Git branch, a fixed script and a customer reply.",
        ["M23-T3", "M20-T2", "M19-T4", "M24-T2"])
