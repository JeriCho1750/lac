from course.core import *

module(11, "SSL/TLS and Certificates", """\
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -keyout k.key -out c.crt -subj "/CN=name" -addext "subjectAltName=DNS:name,DNS:www.name"
openssl x509 -in c.crt -noout -subject -issuer -dates -ext subjectAltName      openssl x509 -in c.crt -noout -checkend 2592000 (expires within 30 d?)
openssl x509 -in c.crt -noout -pubkey | sha256sum   vs   openssl pkey -in k.key -pubout | sha256sum   (same = key matches certificate)
openssl s_client -connect HOST:PORT -servername NAME </dev/null      curl -vk https://HOST:PORT/      curl -sI http://HOST/ (look for 301 + Location)
nginx: listen 443 ssl; ssl_certificate /path/c.crt; ssl_certificate_key /path/k.key; ssl_protocols TLSv1.2 TLSv1.3;
Private keys: chmod 600, owner root.  Redirect HTTP->HTTPS: return 301 https://$host$request_uri;
Let's Encrypt (real servers): certbot --nginx -d example.org   (needs a public DNS name; renewal runs from a systemd timer).""", track="Hosting & Web")

def mkcert(d, name, cn, days, san=None):
    d.mkdir(parents=True, exist_ok=True)
    san_opt = f'-addext "subjectAltName={san}"' if san else ""
    rc, out = sh(f'openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days {days} -keyout {d}/{name}.key -out {d}/{name}.crt -subj "/CN={cn}" {san_opt}')
    if rc: raise RuntimeError("openssl failed: " + out)
    (d / f"{name}.key").chmod(0o600)

def pubhash(cmd):
    return sh(cmd + " | sha256sum")[1].split()[0]

# ---------------------------------------------------------------- T1  create a certificate
def s_m11t1(x):
    apt_install("openssl")
    (x.work / "certs").mkdir(parents=True, exist_ok=True)

def c_m11t1(x):
    d, q = x.work / "certs", []
    crt, key = d / "lab.test.crt", d / "lab.test.key"
    if not crt.is_file() or not key.is_file():
        return [R("certs/lab.test.crt and certs/lab.test.key exist", False)]
    s = sh(f"openssl x509 -in {crt} -noout -subject")[1]
    q.append(R("subject CN is lab.test", re.search(r"CN\s*=\s*lab\.test\b", s) is not None, s))
    san = sh(f"openssl x509 -in {crt} -noout -ext subjectAltName")[1]
    q.append(R("SAN contains DNS:lab.test and DNS:www.lab.test", "DNS:lab.test" in san and "DNS:www.lab.test" in san, san.replace("\n", " ")[:80]))
    q.append(R("valid for at least 365 days from now", sh(f"openssl x509 -in {crt} -noout -checkend {364 * 86400}")[0] == 0))
    q.append(R("valid for at most 825 days", sh(f"openssl x509 -in {crt} -noout -checkend {826 * 86400}")[0] != 0))
    q.append(R("private key matches the certificate", pubhash(f"openssl x509 -in {crt} -noout -pubkey") == pubhash(f"openssl pkey -in {key} -pubout")))
    q.append(R("private key file mode is 600", (key.stat().st_mode & 0o777) == 0o600, oct(key.stat().st_mode & 0o777)))
    return q

add("M11-T1", "Create a self-signed certificate",
    lambda x: f"""\
SCENARIO   An internal test site lab.test needs a certificate (self-signed is fine for the lab).
TASK       In {x.work}/certs create  lab.test.key  and  lab.test.crt  with ONE openssl command:
             - Common Name lab.test, Subject Alternative Names  DNS:lab.test  and  DNS:www.lab.test   (browsers ignore CN without SAN!)
             - valid for 400 days            - no passphrase on the key (-nodes)         - key file mode 600
           Verify:  openssl x509 -in lab.test.crt -noout -subject -dates -ext subjectAltName
EXPECTED RESULT   Certificate and matching key with the right names and lifetime.""",
    s_m11t1, c_m11t1,
    hints=["openssl req -x509 -newkey rsa:2048 -nodes -days 400 -keyout lab.test.key -out lab.test.crt -subj \"/CN=lab.test\" -addext \"subjectAltName=DNS:lab.test,DNS:www.lab.test\"", "chmod 600 lab.test.key"],
    debrief="Modern clients check SAN, not CN. Keep keys at 600. Self-signed = no trusted issuer, fine for tests only.")

# ---------------------------------------------------------------- T2  nginx HTTPS + redirect
def s_m11t2(x):
    ensure_nginx(); apt_install("openssl")
    tok = "TLS" + rnd_word(random.Random(), 5).upper()
    mkcert(x.work / "certs", "site", "lab.test", 365, "DNS:lab.test")
    put(x.work / "www/index.html", f"<h1>SECURE {tok}</h1>\n", 0o644)
    for p in (x.work, x.work / "www"): p.chmod(0o755)
    put("/etc/nginx/conf.d/lab-tls.conf", f"""server {{
    listen 8443;
    root {x.work}/www;
    ssl_certificate {x.work}/certs/site.cert;
    ssl_certificate_key {x.work}/certs/site.key;
    ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;
}}
server {{
    listen 8085;
    root {x.work}/www;
}}
""")
    x.secret = {"tok": tok}

def c_m11t2(x):
    q = []
    q.append(R("nginx -t passes", sh("nginx -t")[0] == 0))
    rc, out = sh("curl -sk -m 5 https://127.0.0.1:8443/")
    q.append(R("https://127.0.0.1:8443/ serves the page (curl -k)", x.secret["tok"] in out, out[:60]))
    rc, hdr = sh("curl -sI -m 5 http://127.0.0.1:8085/")
    q.append(R("http://127.0.0.1:8085/ answers 301", hdr.splitlines()[0].split()[1:2] == ["301"] if hdr else False, hdr.splitlines()[0] if hdr else "no answer"))
    q.append(R("Location header starts with https://", re.search(r"^Location:\s*https://", hdr, re.M | re.I) is not None))
    conf = Path("/etc/nginx/conf.d/lab-tls.conf").read_text()
    m = re.search(r"ssl_protocols\s+([^;]+);", conf)
    prot = m.group(1).split() if m else []
    q.append(R("ssl_protocols allows only TLSv1.2 and TLSv1.3", bool(prot) and set(prot) <= {"TLSv1.2", "TLSv1.3"}, " ".join(prot)))
    return q

add("M11-T2", "HTTPS with nginx and an HTTP->HTTPS redirect",
    lambda x: f"""\
INCIDENT   /etc/nginx/conf.d/lab-tls.conf should serve {x.work}/www over HTTPS on port 8443 (certificate and key are in {x.work}/certs)
           and redirect plain HTTP on port 8085 to HTTPS. Currently HTTPS does not work and old TLS versions are enabled.
TASK       1. nginx -t   (read the error, fix the file names)     2. enable TLS on the 8443 listener   (listen 8443 ssl;)
           3. allow only TLSv1.2 and TLSv1.3        4. make port 8085 answer  return 301 https://127.0.0.1:8443$request_uri;
           5. reload and test:  curl -k https://127.0.0.1:8443/   and   curl -sI http://127.0.0.1:8085/
EXPECTED RESULT   HTTPS page OK, HTTP gives 301 -> https://.""",
    s_m11t2, c_m11t2,
    hints=["ls certs - the config says site.cert but the file is site.crt.", "listen 8443 ssl;  (without 'ssl' nginx speaks plain HTTP on that port)", "return 301 https://127.0.0.1:8443$request_uri;"],
    debrief="'listen ... ssl' turns on TLS, protocols must be limited, and a 301 moves HTTP users to HTTPS.")

# ---------------------------------------------------------------- T3  certificate audit
def g_m11t3(x, r):
    d = x.work / "pki"
    specs = {"alpha": r.choice([5, 8]), "bravo": 200, "charlie": r.choice([18, 25]), "delta": 700}
    cns = {}
    for n, days in specs.items():
        cns[n] = f"{n}-{rnd_word(r, 3)}.lab.test"
        mkcert(d, n, cns[n], days)
    mkcert(d, "_other", "other.lab.test", 100)
    sh(f"mv {d}/_other.key {d}/charlie.key")           # charlie's key no longer matches its certificate
    sh(f"rm -f {d}/_other.crt")
    soon = sorted(n for n, dd in specs.items() if dd <= 30)
    return {"expiring_within_30d": (",".join(soon), "certificate names (alpha..delta) expiring within 30 days, sorted, comma separated, no spaces"),
            "longest_valid": (max(specs, key=specs.get), "name of the certificate with the LATEST expiry"),
            "cn_of_bravo": (cns["bravo"], "Common Name of bravo.crt"),
            "mismatched_key": ("charlie", "name whose .key does NOT match its .crt")}

answers_task("M11-T3", "Certificate audit",
    lambda x: f"""\
SCENARIO   {x.work}/pki holds four certificates (alpha, bravo, charlie, delta: NAME.crt + NAME.key). Report on them for the renewal planning.
USE        openssl x509 -in F -noout -enddate | -subject | -checkend SECONDS     (30 days = 2592000 s)
           key vs certificate:  openssl x509 -in c.crt -noout -pubkey | sha256sum    openssl pkey -in k.key -pubout | sha256sum""",
    g_m11t3,
    hints=["for n in alpha bravo charlie delta; do openssl x509 -in $n.crt -noout -enddate; done", "-checkend 2592000 returns exit code 1 when the cert expires within 30 days."],
    debrief="Expiry dates and key/certificate mismatches cause outages. Audit them regularly (or automate with monitoring).")

# ---------------------------------------------------------------- T4  s_client inspection
def g_m11t4(x, r):
    ensure_nginx(); apt_install("openssl")
    days, cn = r.randint(90, 300), f"shop-{rnd_word(r, 4)}.lab.test"
    mkcert(x.work / "certs", "srv", cn, days, f"DNS:{cn}")
    put(x.work / "www/index.html", "<h1>x</h1>\n", 0o644)
    for p in (x.work, x.work / "www"): p.chmod(0o755)
    put("/etc/nginx/conf.d/lab-tls2.conf", f"""server {{
    listen 8444 ssl;
    root {x.work}/www;
    ssl_certificate {x.work}/certs/srv.crt;
    ssl_certificate_key {x.work}/certs/srv.key;
}}
""")
    sh("nginx -t && systemctl reload nginx")
    (x.work / "certs/srv.key").unlink()                 # the student only sees what the SERVER presents
    return {"served_cn": (cn, "Common Name of the certificate the server presents on port 8444"),
            "days_left": (days, "days until it expires (+/- 2)", "int", 2),
            "self_signed": ("yes", "is the certificate self-signed (issuer = subject)? yes/no")}

answers_task("M11-T4", "Inspect a live TLS endpoint",
    lambda x: """\
SCENARIO   Something is listening for HTTPS on 127.0.0.1:8444. You do not have its files - only the network. Find out what certificate it presents.
USE        echo | openssl s_client -connect 127.0.0.1:8444 -servername test 2>/dev/null | openssl x509 -noout -subject -issuer -dates
           (date -d 'DATE' +%s gives epoch seconds for day arithmetic)""",
    g_m11t4,
    hints=["openssl s_client ... | openssl x509 -noout -enddate  prints notAfter=...", "days left = (enddate - today) in days; round to the nearest day."],
    debrief="s_client shows exactly what clients see: names, issuer, expiry - the fastest TLS troubleshooting tool.")

compose("M11-X1", "BLOCK EXAM: certificates and HTTPS", "Create, serve, audit and inspect.", ["M11-T1", "M11-T2", "M11-T3", "M11-T4"])
