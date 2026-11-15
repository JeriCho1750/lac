from course.core import *

module(14, "DNS Server (BIND9)", """\
Record types: A (name->IPv4)  AAAA  CNAME (alias)  MX (mail, priority + host)  NS  TXT (SPF/DMARC/verification)  PTR (IP->name)  SOA (zone header + SERIAL)
Zone file rules: names WITHOUT a trailing dot get the zone name appended  (ns1.lab.test  ->  ns1.lab.test.lab.test.  !!)  -> always write FQDNs with a final dot.
Increase the SOA serial on every change (e.g. YYYYMMDDnn) - secondaries only update when it grows.
named-checkconf FILE    named-checkzone ZONE FILE    dig @127.0.0.1 -p 5353 NAME TYPE +short    dig -x 10.0.0.10 @127.0.0.1 -p 5353 +short
dig +noall +answer NAME  (shows TTL too)       systemctl restart lab-named      journalctl -u lab-named -n 30
Reverse zone for 10.0.0.0/24 is  0.0.10.in-addr.arpa  with records like  10 IN PTR www.lab.test.
LAB: a private BIND instance (service lab-named) answers on 127.0.0.1 port 5353.  Files: /etc/bind/lab-dns/  (named.conf, zones/).""", track="Infrastructure")

DNSD, DNSW = Path("/etc/bind/lab-dns"), Path("/var/cache/bind/lab-dns")

NAMED_CONF = """options {
    directory "/var/cache/bind/lab-dns";
    listen-on port 5353 { 127.0.0.1; };
    listen-on-v6 { none; };
    allow-query { 127.0.0.1; };
    recursion no;
    pid-file "/var/cache/bind/lab-dns/named.pid";
    session-keyfile "/var/cache/bind/lab-dns/session.key";
    dnssec-validation no;
};
zone "lab.test" { type master; file "/etc/bind/lab-dns/zones/lab.test.zone"; };
"""

def dns_up(zone_text, conf=NAMED_CONF):
    apt_install("bind9", "bind9utils", "dnsutils")
    (DNSD / "zones").mkdir(parents=True, exist_ok=True)
    DNSW.mkdir(parents=True, exist_ok=True)
    sh(f"chown bind:bind {DNSW}")
    put(DNSD / "named.conf", conf, 0o644)
    put(DNSD / "zones/lab.test.zone", zone_text, 0o644)
    for p in (DNSD, DNSD / "zones"): p.chmod(0o755)
    put("/etc/systemd/system/lab-named.service", """[Unit]
Description=Lab practice BIND9 (127.0.0.1:5353)

[Service]
ExecStart=/usr/sbin/named -g -c /etc/bind/lab-dns/named.conf -u bind
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
""")
    sh("systemctl daemon-reload; systemctl restart lab-named")
    time.sleep(1.5)

def dig(name, rtype="A", extra="+short"):
    return sh(f"dig @127.0.0.1 -p 5353 +time=2 +tries=1 {extra} {name} {rtype}")[1].strip()

GOOD_ZONE = """$TTL 3600
@    IN SOA ns1.lab.test. admin.lab.test. ( 2025010101 3600 600 604800 300 )
@    IN NS  ns1.lab.test.
ns1  IN A   10.0.0.2
www  IN A   10.0.0.10
mail IN A   10.0.0.20
@    IN MX  10 mail.lab.test.
ftp  IN CNAME www.lab.test.
"""

def zone_serial_file():
    m = re.search(r"\(\s*(\d+)", (DNSD / "zones/lab.test.zone").read_text())
    return int(m.group(1)) if m else 0

# ---------------------------------------------------------------- D1  broken zone
BAD_ZONE = GOOD_ZONE.replace("@    IN NS  ns1.lab.test.", "@    IN NS  ns1.lab.test").replace("www  IN A   10.0.0.10", "www  IN A   10.0.0.1000")

def s_m14t1(x):
    dns_up(BAD_ZONE)

def reqs_forward():
    z = DNSD / "zones/lab.test.zone"
    rc, out = sh(f"named-checkzone lab.test {z}")
    q = [R("named-checkzone lab.test reports OK", rc == 0, out.splitlines()[-1] if out else "")]
    q.append(R("lab-named service is running", svc("lab-named.service").get("ActiveState") == "active"))
    q.append(R("www.lab.test -> 10.0.0.10", dig("www.lab.test") == "10.0.0.10", dig("www.lab.test") or "no answer"))
    q.append(R("mail.lab.test -> 10.0.0.20", dig("mail.lab.test") == "10.0.0.20"))
    q.append(R("lab.test NS is ns1.lab.test.", dig("lab.test", "NS") == "ns1.lab.test.", dig("lab.test", "NS")))
    q.append(R("lab.test MX is '10 mail.lab.test.'", dig("lab.test", "MX") == "10 mail.lab.test."))
    q.append(R("ftp.lab.test is a CNAME to www.lab.test.", dig("ftp.lab.test", "CNAME") == "www.lab.test."))
    return q

c_m14t1 = lambda x: reqs_forward()

TXT_D1 = lambda x: f"""\
INCIDENT   The authoritative DNS service for lab.test (lab-named, 127.0.0.1:5353) does not answer. Zone file: /etc/bind/lab-dns/zones/lab.test.zone
TASK       1. systemctl status lab-named ; journalctl -u lab-named -n 20 --no-pager
           2. named-checkzone lab.test /etc/bind/lab-dns/zones/lab.test.zone       (it names the line and the problem)
           3. Fix the zone, expected data:   ns1 10.0.0.2   www 10.0.0.10   mail 10.0.0.20   MX 10 mail   ftp CNAME www   NS ns1.lab.test.
           4. systemctl restart lab-named   and verify with:  dig @127.0.0.1 -p 5353 www.lab.test +short   (also MX, NS, CNAME)
EXPECTED RESULT   Service running, all five lookups correct."""
add("M14-T1", "BIND: the zone does not load", TXT_D1, s_m14t1, c_m14t1,
    hints=["Names without a final dot are relative: 'ns1.lab.test' becomes ns1.lab.test.lab.test.", "10.0.0.1000 is not a valid IPv4 address (octets max 255).", "named-checkzone must say 'OK' before you restart the service."],
    debrief="FQDNs end with a dot in zone files. named-checkzone/-checkconf are your safety net before every restart.")

# ---------------------------------------------------------------- D2  change records
def s_m14t2(x):
    dns_up(GOOD_ZONE)

def c_m14t2(x):
    q = []
    q.append(R("named-checkzone OK", sh(f"named-checkzone lab.test {DNSD}/zones/lab.test.zone")[0] == 0))
    q.append(R("www.lab.test -> 10.0.0.11 (changed)", dig("www.lab.test") == "10.0.0.11", dig("www.lab.test") or "no answer"))
    q.append(R("shop.lab.test -> 10.0.0.30 (new record)", dig("shop.lab.test") == "10.0.0.30", dig("shop.lab.test") or "no answer"))
    q.append(R("TXT at the apex: \"v=spf1 mx -all\"", dig("lab.test", "TXT").strip('"') == "v=spf1 mx -all", dig("lab.test", "TXT")))
    fs = zone_serial_file()
    soa = dig("lab.test", "SOA").split()
    q.append(R("SOA serial increased (> 2025010101) in the file", fs > 2025010101, f"file serial {fs}"))
    q.append(R("the RUNNING server serves the new serial (service was restarted)", len(soa) > 2 and soa[2] == str(fs), f"server serial {soa[2] if len(soa) > 2 else '?'}"))
    return q

add("M14-T2", "BIND: change a zone the right way",
    lambda x: """\
SCENARIO   The zone lab.test works. A change request arrived:
             - www.lab.test must move to 10.0.0.11
             - new host shop.lab.test -> 10.0.0.30
             - SPF record for the domain: a TXT record at the apex  "v=spf1 mx -all"
TASK       Edit /etc/bind/lab-dns/zones/lab.test.zone, INCREASE THE SOA SERIAL, run named-checkzone, restart lab-named, verify with dig.
EXPECTED RESULT   The running server returns the new data AND the new serial.""",
    s_m14t2, c_m14t2,
    hints=["Serial 2025010101 -> 2025010102 (any larger number).", "@  IN TXT \"v=spf1 mx -all\"", "Without restarting lab-named the old data keeps being served."],
    debrief="Edit -> bump serial -> check -> reload/restart -> verify with dig. Skipping the serial is the classic mistake.")

# ---------------------------------------------------------------- D3  answers by querying
def g_m14t3(x, r):
    ip = f"10.{r.randint(1,9)}.{r.randint(1,9)}.{r.randint(10,99)}"
    ttl = r.choice([60, 120, 300, 900])
    app = f"app-{rnd_word(r, 4)}"
    mx = f"mx-{rnd_word(r, 3)}"
    tok = rnd_word(r, 6) + str(r.randint(100, 999))
    serial = r.randint(2025030100, 2025030999)
    z = f"""$TTL 3600
@    IN SOA ns1.lab.test. admin.lab.test. ( {serial} 3600 600 604800 300 )
@    IN NS  ns1.lab.test.
ns1  IN A   10.9.9.2
www  {ttl} IN A {ip}
{app} IN A 10.9.9.50
blog IN CNAME {app}.lab.test.
{mx} IN A 10.9.9.60
@    IN MX 20 {mx}.lab.test.
@    IN TXT "token={tok}"
"""
    dns_up(z)
    return {"www_ip": (ip, "IPv4 of www.lab.test"),
            "www_ttl": (ttl, "TTL (seconds) of the www.lab.test A record", "int"),
            "blog_target": (f"{app}.lab.test.", "CNAME target of blog.lab.test (with the final dot)"),
            "mx_host": (f"{mx}.lab.test.", "mail server host name of lab.test (the MX target, with the final dot)"),
            "txt_token": (f"token={tok}", "the TXT record value without the quotes"),
            "soa_serial": (serial, "SOA serial", "int")}

answers_task("M14-T3", "Interrogate a DNS server with dig",
    lambda x: """\
SCENARIO   You do not know the zone lab.test. Query the lab server (127.0.0.1 port 5353) like a customer's support engineer would.
           (Do not read the zone file - practice dig.)
USE        dig @127.0.0.1 -p 5353 www.lab.test +noall +answer         dig @127.0.0.1 -p 5353 lab.test MX +short       ... TXT, SOA""",
    g_m14t3,
    hints=["+noall +answer prints: NAME TTL CLASS TYPE DATA", "dig @127.0.0.1 -p 5353 lab.test SOA +short  -> the 3rd field is the serial"],
    debrief="dig with +short for answers, +noall +answer for TTLs - the support engineer's everyday tool.")

# ---------------------------------------------------------------- D4  reverse zone
REV_ZONE_NAME = "0.0.10.in-addr.arpa"

def s_m14t4(x):
    dns_up(GOOD_ZONE)

def reqs_reverse():
    q = []
    rc, out = sh(f"named-checkconf {DNSD}/named.conf")
    q.append(R("named-checkconf reports no errors", rc == 0, out[:100]))
    for ip, name in (("10.0.0.10", "www.lab.test."), ("10.0.0.20", "mail.lab.test."), ("10.0.0.2", "ns1.lab.test.")):
        got = dig(f"-x {ip}", "")
        q.append(R(f"dig -x {ip} -> {name}", got == name, got or "no answer"))
    return q

c_m14t4 = lambda x: reqs_reverse()

TXT_D4 = lambda x: """\
SCENARIO   Mail servers and audits look up PTR records (IP -> name). The server has only the forward zone. Add the REVERSE zone for 10.0.0.0/24.
TASK       1. Create /etc/bind/lab-dns/zones/0.0.10.in-addr.arpa.zone with SOA + NS + PTR records:
                10.0.0.10 -> www.lab.test.     10.0.0.20 -> mail.lab.test.     10.0.0.2 -> ns1.lab.test.
           2. Declare the zone in /etc/bind/lab-dns/named.conf   (zone "0.0.10.in-addr.arpa" { type master; file "..."; };)
           3. named-checkconf, named-checkzone 0.0.10.in-addr.arpa FILE, restart lab-named
           4. Test:  dig @127.0.0.1 -p 5353 -x 10.0.0.10 +short
EXPECTED RESULT   All three reverse lookups answer."""
add("M14-T4", "BIND: add a reverse zone (PTR)", TXT_D4, s_m14t4, c_m14t4,
    hints=["In the reverse zone only the LAST octet is the owner name:  10 IN PTR www.lab.test.", "Copy the SOA/NS lines from the forward zone and keep the final dots."],
    debrief="PTR records live in an in-addr.arpa zone written in reverse octet order.")

# ---------------------------------------------------------------- EXAM: broken forward + missing reverse
add("M14-X1", "BLOCK EXAM: the DNS server", lambda x: "BLOCK EXAM - no hints. TWO jobs on the same server:\n\n" + TXT_D1(x) + "\n\nAND ALSO:\n\n" + TXT_D4(x)
    + report_text(x),
    s_m14t1, lambda x: reqs_forward() + reqs_reverse() + report_reqs(x), no_hints=True,
    debrief="You repaired a broken zone and added a reverse zone on one live DNS server.")
