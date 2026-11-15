from course.core import *

module(15, "Mail Server (Postfix)", """\
Postfix basics: /etc/postfix/main.cf (postconf -n shows what differs from default; postconf -e 'key = value' edits)   systemctl reload postfix
Key settings: myhostname  mydomain  mydestination (domains delivered LOCALLY)  inet_interfaces  relayhost (smarthost for outgoing mail)
Queue: postqueue -p (list)   postqueue -f (flush/retry)   postsuper -d ID | -d ALL (delete)   postcat -q ID (show a queued message)
Logs: journalctl -u postfix@-  or  /var/log/mail.log      status=deferred (...reason...) = will be retried;  status=bounced = permanent failure
Aliases: /etc/aliases  ("name: user1, user2")  then  newaliases.     Local mailboxes: /var/mail/USER     Send a test:  echo body | mail -s subject user@localhost
Mail DNS records:  MX (where to deliver)   A for the mail host   PTR (reverse)   TXT SPF "v=spf1 mx -all"   TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:..."   DKIM selector TXT
In this lab Postfix listens on loopback only.""", track="Infrastructure")

def ensure_postfix():
    sh('echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections; echo "postfix postfix/mailname string lab.test" | debconf-set-selections')
    apt_install("postfix", "bsd-mailx")
    save_orig("/etc/postfix/main.cf")
    save_orig("/etc/aliases")
    if sh("postconf -h myhostname")[1].strip() != "lab.test":
        sh("postconf -e 'myhostname = lab.test' 'inet_interfaces = loopback-only' 'mydestination = $myhostname, localhost.$mydomain, localhost' 'relayhost =' 'inet_protocols = ipv4'")
    for u in ("lab_mail1", "lab_mail2"):
        sh(f"id {u} >/dev/null 2>&1 || useradd -m -s /bin/bash {u}")
    sh("systemctl enable postfix >/dev/null 2>&1; systemctl restart postfix")
    time.sleep(1)

def probe(to, marker):
    return sh(f"printf 'Subject: probe\\n\\n{marker}\\n' | /usr/sbin/sendmail -f lab_probe@localhost {to}")[0]

def mailbox_has(user, marker, wait=20):
    f = Path("/var/mail") / user
    for _ in range(wait):
        try:
            if marker in f.read_text(errors="replace"): return True
        except OSError:
            pass
        time.sleep(1)
    return False

# ---------------------------------------------------------------- P1  local delivery
def s_m15t1(x):
    ensure_postfix()
    sh("postconf -e 'mydestination ='; systemctl reload postfix")

def c_m15t1(x):
    q = []
    q.append(R("mydestination contains localhost", "localhost" in sh("postconf -h mydestination")[1]))
    m = "chk" + rnd_word(random.Random(), 8)
    probe("lab_mail1@localhost", m)
    q.append(R("a test message to lab_mail1@localhost arrives in /var/mail/lab_mail1 (waits up to 20 s)", mailbox_has("lab_mail1", m)))
    return q

add("M15-T1", "Postfix: local mail is not delivered",
    lambda x: """\
INCIDENT   Mail to local users (e.g. lab_mail1@localhost) never arrives. Postfix runs but mail disappears into the queue or bounces.
TASK       1. echo "hello" | mail -s test lab_mail1@localhost     2. postqueue -p     3. journalctl -u postfix@- -n 20 --no-pager  (or tail /var/log/mail.log)
           4. postconf -n    - which setting decides which domains are delivered locally?
           5. Fix it with  postconf -e '...'  (or main.cf), systemctl reload postfix, send again and look into /var/mail/lab_mail1
EXPECTED RESULT   A new message appears in the local mailbox.""",
    s_m15t1, c_m15t1,
    hints=["The log says 'mail for localhost loops back to myself' - localhost is not in mydestination.", "postconf -e 'mydestination = $myhostname, localhost.$mydomain, localhost'  (single quotes so $ is not expanded)"],
    debrief="mydestination lists the domains Postfix accepts for LOCAL delivery; empty = nothing is local.")

# ---------------------------------------------------------------- P2  aliases
def s_m15t2(x):
    ensure_postfix()

def c_m15t2(x):
    q, r = [], random.Random()
    m1, m2 = "sup" + rnd_word(r, 8), "sal" + rnd_word(r, 8)
    probe("support@localhost", m1)
    probe("sales@localhost", m2)
    q.append(R("support@localhost is delivered to lab_mail1", mailbox_has("lab_mail1", m1)))
    q.append(R("sales@localhost is delivered to lab_mail1 ...", mailbox_has("lab_mail1", m2, 8)))
    q.append(R("... and ALSO to lab_mail2", mailbox_has("lab_mail2", m2, 8)))
    txt = Path("/etc/aliases").read_text()
    q.append(R("root alias was not changed to an external address", not re.search(r"^root:.*@", txt, re.M)))
    return q

add("M15-T2", "Mail aliases",
    lambda x: """\
SCENARIO   Role addresses are needed on this server (domain localhost):
             support@  -> lab_mail1
             sales@    -> lab_mail1 AND lab_mail2
TASK       Edit /etc/aliases (format  name: target1, target2), run newaliases, test with  echo hi | mail -s t support@localhost
           and look at /var/mail/lab_mail1 and /var/mail/lab_mail2.   Do not forward 'root' anywhere else.
EXPECTED RESULT   Both aliases deliver to the right mailboxes.""",
    s_m15t2, c_m15t2,
    hints=["support: lab_mail1", "sales: lab_mail1, lab_mail2   then  newaliases"],
    debrief="/etc/aliases + newaliases map role names to real mailboxes without creating accounts.")

# ---------------------------------------------------------------- P3  stuck queue
def s_m15t3(x):
    ensure_postfix()
    sh("postconf -e 'relayhost = [127.0.0.1]:2525'; systemctl reload postfix")
    for i in range(3):
        probe(f"nobody{i}@example.invalid", f"queued-{i}")
    time.sleep(3)

def c_m15t3(x):
    q, a = [], answers(x)
    chk(q, a, "queued_messages", 3, "how many messages were stuck in the queue (before you cleaned up)", "int")
    chk(q, a, "queue_reason", "connection_refused", "reason shown by postqueue -p: connection_refused | timeout | host_not_found")
    q.append(R("relayhost no longer points to the dead port", "2525" not in sh("postconf -h relayhost")[1]))
    q.append(R("mail queue is empty", "queue is empty" in sh("postqueue -p")[1].lower()))
    return q

add("M15-T3", "Postfix: mail stuck in the queue",
    lambda x: f"""\
INCIDENT   Outgoing mail piles up. Three test messages to nobody0..2@example.invalid are waiting.
TASK       1. postqueue -p     - count the messages and read the reason in brackets, e.g. (connect to ...: ...)
           2. postconf -n | grep relayhost
           3. Write {x.work}/answers.txt :   queued_messages=<number>    queue_reason=<connection_refused | timeout | host_not_found>
           4. Fix the cause (the relayhost points to a port where nothing listens; this lab server delivers directly, so relayhost must be EMPTY),
              reload postfix, and delete the three undeliverable TEST messages:  postsuper -d ALL
EXPECTED RESULT   Correct diagnosis, clean config, empty queue.""",
    s_m15t3, c_m15t3,
    hints=["postqueue -p shows '(connect to 127.0.0.1[127.0.0.1]:2525: Connection refused)'", "postconf -e 'relayhost =' ; systemctl reload postfix ; postsuper -d ALL"],
    debrief="Read the queue reason first; fix the cause; only then flush or delete.")

# ---------------------------------------------------------------- P4  DNS records for mail
def s_m15t4(x):
    x.own(x.work)

def c_m15t4(x):
    f, q = x.work / "dns-records.txt", []
    txt = f.read_text() if f.is_file() else ""
    lines = [l.strip() for l in txt.splitlines() if l.strip() and not l.strip().startswith(";")]
    def has(rx): return any(re.search(rx, l, re.I) for l in lines)
    D = r"lab-mail\.example"
    q.append(R("MX record: priority 10 -> mail.lab-mail.example. (FQDN with final dot)", has(rf"\bIN\s+MX\s+10\s+mail\.{D}\.\s*$")))
    q.append(R("A record: mail.lab-mail.example. -> 203.0.113.25", has(rf"^mail\.{D}\.\s+(\d+\s+)?IN\s+A\s+203\.0\.113\.25\s*$")))
    spf = [l for l in lines if "v=spf1" in l]
    q.append(R("SPF TXT record: 'v=spf1 mx -all' (hard fail, not +all / ?all)", bool(spf) and "-all" in spf[0] and re.search(r"[+?]all", spf[0]) is None and re.search(r"\bmx\b", spf[0]) is not None))
    q.append(R("DMARC TXT on _dmarc.lab-mail.example.: p=quarantine or p=reject and rua=mailto:dmarc@lab-mail.example",
               has(rf"^_dmarc\.{D}\.") and has(r"v=DMARC1") and has(r"p=(quarantine|reject)") and has(rf"rua=mailto:dmarc@{D}")))
    q.append(R("PTR record: 25.113.0.203.in-addr.arpa. -> mail.lab-mail.example.", has(rf"^25\.113\.0\.203\.in-addr\.arpa\.\s+(\d+\s+)?IN\s+PTR\s+mail\.{D}\.\s*$")))
    return q

add("M15-T4", "Mail DNS records: MX, SPF, DMARC, PTR",
    lambda x: f"""\
SCENARIO   Domain lab-mail.example gets its own mail server mail.lab-mail.example with the public IP 203.0.113.25. Without the right DNS records
           mail from it lands in spam. Write the records (zone-file syntax, one per line, FQDNs with a FINAL DOT) into {x.work}/dns-records.txt :
             1. MX      priority 10, target mail.lab-mail.example.
             2. A       mail.lab-mail.example.  ->  203.0.113.25
             3. SPF     TXT on lab-mail.example. : only the MX hosts may send, everyone else is rejected (hard fail)
             4. DMARC   TXT on _dmarc.lab-mail.example. : policy quarantine, aggregate reports to dmarc@lab-mail.example
             5. PTR     25.113.0.203.in-addr.arpa.  ->  mail.lab-mail.example.
           Example line format:   lab-mail.example. IN TXT "..."
EXPECTED RESULT   Five correct records.""",
    s_m15t4, c_m15t4,
    hints=["SPF: \"v=spf1 mx -all\"", "DMARC: \"v=DMARC1; p=quarantine; rua=mailto:dmarc@lab-mail.example\""],
    debrief="MX + A + PTR make the server findable; SPF/DKIM/DMARC prove the mail is legitimate.")

compose("M15-X1", "BLOCK EXAM: the mail server", "Local delivery, aliases and the DNS records for mail.", ["M15-T1", "M15-T2", "M15-T4"])
