from course.core import *

module(24, "Support, Tickets and Documentation", """\
Ticket priority (used in this course):  P1 = outage for ALL users or a (suspected) SECURITY incident     P2 = degraded service, or ONE user/system cannot work
                                        P3 = how-to question, routine change request
Reply structure: greeting -> acknowledge/apologise -> what happened (plain words) -> what we did -> what happens next (+ when) -> closing.  Short sentences. No jargon, no blame, no passwords.
Runbook: a numbered list anyone on shift can follow:  Symptoms / Checks (with exact commands, in order) / Fix / Escalation.
Shift handover: only OPEN items, one line each, with ticket id + current status + next action.  (resolved tickets are not repeated)
Write in clear English. Facts first (times, ids, service names), opinions never.""", track="Support")

# ---------------------------------------------------------------- S1  triage
P1T = ["The whole website is down for all our customers", "We think someone stole our admin password and logged in last night",
       "The server is unreachable and nobody in the company can work", "The payment page returns an error for every customer"]
P2T = ["The website has been very slow since this morning", "I cannot log in to the server but my colleagues can",
       "Sending email works only sometimes", "One of our two web servers keeps restarting"]
P3T = ["How do I change my mailbox password?", "Please create an account for our new intern", "Could you install the htop package on the test server?",
       "Where can I download my invoices?"]

def g_m24t1(x, r):
    pool = [(t, "P1") for t in r.sample(P1T, 2)] + [(t, "P2") for t in r.sample(P2T, 3)] + [(t, "P3") for t in r.sample(P3T, 3)]
    r.shuffle(pool)
    lines, spec = [], {}
    for i, (t, p) in enumerate(pool):
        tid = f"T{1001 + i}"
        lines.append(f"{tid}: {t}")
        spec[tid] = (p, f"priority of ticket {tid}: P1, P2 or P3")
    put(x.work / "tickets.txt", "\n".join(lines) + "\n")
    return spec

answers_task("M24-T1", "Triage the ticket queue",
    lambda x: f"""\
SCENARIO   Eight new tickets arrived ({x.work}/tickets.txt). Assign a priority to each using the policy:
             P1 = outage for ALL users, or a suspected security incident
             P2 = degraded service, or only ONE user / ONE system is affected
             P3 = how-to question or routine change request
           Keys are the ticket ids (T1001 ...), values P1, P2 or P3.""",
    g_m24t1,
    hints=["'everybody', 'all customers', 'stolen' -> P1.  'slow', 'sometimes', 'only me' -> P2.  'how do I', 'please create/install' -> P3."],
    debrief="Triage = impact first (how many users, how severe), not who shouts loudest.")

# ---------------------------------------------------------------- S2  customer reply
def g_m24t2(x, r):
    tid = f"T-{r.randint(4000, 4999)}"
    h = r.randint(9, 15)
    start, end = f"{h:02d}:{r.choice(['05','10','15'])}", f"{h:02d}:{r.choice(['40','45','50'])}"
    svc_name = r.choice(["customer portal", "online shop", "booking system"])
    put(x.work / "incident.log", f"""Ticket {tid} - internal technical notes (NOT for the customer)
{start} nginx[812]: [error] 502 Bad Gateway while connecting to upstream 127.0.0.1:9000 - connection refused
{start} kernel: Out of memory: Killed process 1544 (php-fpm) total-vm:2201344kB
{start} monitoring: service '{svc_name}' status=DOWN for all users
{end[:3]}{int(end[3:]) - 3:02d} sysadmin: raised memory limit of the app pool, cleaned up cache files, restarted php-fpm
{end} monitoring: service '{svc_name}' status=UP; response time normal
Follow-up planned: memory monitoring alert at 80%, review of the nightly import job (owner: dev team, due next Friday)
""")
    x.secret_facts = None
    return {"ticket": (tid, "ticket id (repeat it in your reply)"), "start": (start, "time the outage started"), "end": (end, "time service was restored"), "service": (svc_name, "customer-facing service name")}

def c_m24t2(x):
    q, spec = [], x.secret["spec"]
    f = x.work / "reply.txt"
    txt = f.read_text() if f.is_file() else ""
    low = txt.lower()
    words = len(txt.split())
    q.append(R("reply.txt has 50-180 words", 50 <= words <= 180, f"{words} words"))
    q.append(R(f"mentions the ticket id {spec['ticket'][0]}", spec["ticket"][0].lower() in low))
    q.append(R("states the outage window (both times)", spec["start"][0] in txt and spec["end"][0] in txt))
    q.append(R(f"names the affected service ('{spec['service'][0]}') in the customer's words", spec["service"][0] in low))
    q.append(R("apologises", re.search(r"\b(sorry|apolog\w+)\b", low) is not None))
    q.append(R("explains the next step / follow-up (monitoring, prevention, update ...)", re.search(r"\b(monitor\w*|prevent\w*|follow[- ]up|next|will)\b", low) is not None))
    jargon = [w for w in ("502", "nginx", "php-fpm", "oom", "kernel", "upstream", "grep", "stack trace", "errno", "segfault", "127.0.0.1") if w in low]
    q.append(R("no technical jargon the customer cannot use", not jargon, "found: " + ", ".join(jargon)))
    q.append(R("has a greeting and a closing line", re.search(r"^(dear|hello|hi)\b", low.strip()) is not None and re.search(r"(regards|sincerely|best wishes|thank you)\W*[\w\s,.]*$", low.strip()) is not None))
    return q

answers_none = None  # (answers file not used in this task)
def _s_m24t2(x):
    spec = g_m24t2(x, random.Random())
    x.secret = {"spec": {k: list(v) for k, v in spec.items()}}
    x.own(x.work)

add("M24-T2", "Write the customer reply",
    lambda x: f"""\
SCENARIO   Ticket {x.secret['spec']['ticket'][0]} - the customer asks: 'Why was your {x.secret['spec']['service'][0]} down, and will it happen again?'
           You have the internal notes in {x.work}/incident.log. They contain jargon and internal names.
TASK       Write {x.work}/reply.txt - an email to the customer in clear English, 50-180 words:
             Greeting, apology, WHAT happened in plain words (e.g. 'the service ran out of memory') with the outage window (start and end times from the notes),
             what WE did, what happens NEXT (how we will prevent a repeat), polite closing. Mention the ticket id. No technical terms like process names, error codes or IP addresses.
EXPECTED RESULT   A reply you would be happy to send.""",
    _s_m24t2, c_m24t2,
    hints=["Structure: 1) Dear customer, 2) We are sorry... 3) Between HH:MM and HH:MM ... 4) We have ... 5) To prevent this we will ... 6) Kind regards, Support team", "Replace 'php-fpm ran out of memory' with 'the system behind the service ran out of memory'."],
    debrief="Customers need: what, when, what you did, what next - in their words. Internal details stay in the internal notes.")

# ---------------------------------------------------------------- S3  runbook
def s_m24t3(x):
    x.own(x.work)

def c_m24t3(x):
    f, q = x.work / "runbook.md", []
    txt = f.read_text() if f.is_file() else ""
    secs = {m.group(1).strip().lower(): m.group(2) for m in re.finditer(r"^##\s+(.+?)\s*\n(.*?)(?=^##\s|\Z)", txt, re.M | re.S)}
    q.append(R("sections: Symptoms, Checks, Fix, Escalation (each >= 8 words)", all(len(secs.get(n, "").split()) >= 8 for n in ("symptoms", "checks", "fix", "escalation")), "found: " + ", ".join(secs)))
    checks = secs.get("checks", "") + secs.get("fix", "")
    order = ["curl", "systemctl status", "error.log", "ss -tlnp", "nginx -t", "systemctl reload"]
    pos, last, ok = [], -1, True
    for token in order:
        i = checks.find(token, last + 1)
        if i < 0: ok = False; pos.append(f"{token}: missing"); continue
        last = i
    q.append(R("the check/fix steps appear in a logical order: curl, systemctl status, error.log, ss -tlnp, nginx -t, systemctl reload", ok, "; ".join(pos)))
    steps = re.findall(r"^\s*\d+[.)]\s+\S+", checks, re.M)
    q.append(R("steps are NUMBERED (at least 5 numbered lines)", len(steps) >= 5, f"{len(steps)} numbered lines"))
    q.append(R("Escalation names a role or team and a time limit (e.g. 'after 15 minutes')", re.search(r"\d+\s*(min|minutes|hour|hours)", secs.get("escalation", ""), re.I) is not None))
    return q

add("M24-T3", "Write a runbook",
    lambda x: f"""\
SCENARIO   Tonight's on-call engineer has never seen this problem: 'The website returns 502 Bad Gateway' (nginx in front of an application).
TASK       Write {x.work}/runbook.md (Markdown) with exactly these ## sections:  Symptoms, Checks, Fix, Escalation.
             Checks/Fix = NUMBERED steps with the exact commands, in the order you would run them, covering at least:
                reproduce with curl -> systemctl status of the service -> read nginx error.log -> see who listens (ss -tlnp) -> nginx -t -> systemctl reload
             Escalation = who to call (a role/team) and after how many minutes.
EXPECTED RESULT   A runbook a stranger could follow at 3 a.m.""",
    s_m24t3, c_m24t3,
    hints=["## Checks\n1. curl -i http://localhost/  ...\n2. systemctl status nginx ...", "Escalation: 'If not fixed within 20 minutes call the senior sysadmin on duty.'"],
    debrief="A runbook turns one person's experience into a procedure anyone can execute.")

# ---------------------------------------------------------------- S4  shift handover
def g_m24t4(x, r):
    n = r.randint(6, 8)
    ids = [f"T-{2000 + i}" for i in range(n)]
    state, lines, t = {}, [], 8 * 60
    for tid in ids:
        t += r.randint(3, 20)
        lines.append((t, tid, "opened")); state[tid] = "open"
    for _ in range(n * 2):
        tid = r.choice(ids)
        if state[tid] == "resolved": continue
        t += r.randint(5, 25)
        ev = r.choice(["waiting-customer", "escalated", "resolved", "resolved"])
        lines.append((t, tid, ev)); state[tid] = "open" if ev == "opened" else ev
    put(x.work / "shift-log.txt", "\n".join(f"{ts // 60:02d}:{ts % 60:02d} {tid} {ev}" for ts, tid, ev in lines) + "\n")
    open_t = {k: v for k, v in state.items() if v != "resolved"}
    x.secret_state = open_t
    return {"open_tickets": (",".join(f"{k}={v}" for k, v in sorted(open_t.items())), "unresolved tickets as ID=status (status = the LAST event: open / waiting-customer / escalated), sorted by id, comma separated, no spaces")}

answers_task("M24-T4", "Shift handover",
    lambda x: f"""\
SCENARIO   Your shift ends. {x.work}/shift-log.txt lists ticket events in time order (HH:MM TICKET event; events: opened, waiting-customer, escalated, resolved).
           The next shift needs the OPEN items only. A ticket's status is its LAST event; 'opened' as last event means status 'open'.
EXAMPLE    open_tickets=T-2001=escalated,T-2003=open,T-2006=waiting-customer""",
    g_m24t4,
    hints=["For each ticket id: grep T-2003 shift-log.txt | tail -1", "Skip every ticket whose last event is 'resolved'."],
    debrief="A good handover lists only what is still open, with the current status - nothing to dig for.")

compose("M24-X1", "BLOCK EXAM: service desk shift", "Triage, answer, document and hand over.", ["M24-T1", "M24-T2", "M24-T3", "M24-T4"], report=False)
