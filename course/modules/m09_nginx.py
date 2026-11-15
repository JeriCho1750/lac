from course.core import *
from course.modules.m06_networking import net_truth

# ------------------------------------------------------------------ 9. Web
module(9, "Web Server Administration", """\
nginx -t (ALWAYS test before reload)    systemctl reload nginx    systemctl status nginx    journalctl -u nginx
/etc/nginx/nginx.conf, /etc/nginx/conf.d/*.conf, /var/log/nginx/error.log (THE place to look for 403/502/500)
server { listen 8081; server_name x; root /path; index index.html; location / { try_files $uri $uri/ =404; } }
Reverse proxy: location / { proxy_pass http://127.0.0.1:9000; proxy_set_header Host $host; }
403 = permissions (www-data needs r on the file and x on every directory)    404 = path wrong    502 = backend down / wrong port
curl -i http://127.0.0.1:PORT/    ss -tlnp | grep PORT    namei -l /path""", track="Hosting & Web")

def s_m09t1(x):
    ensure_nginx()
    tok = rnd_word(random.Random(), 6).upper()
    www = x.work / "www"
    put(www / "index.html", f"<h1>LAB SITE {tok}</h1>\n", 0o600)
    www.chmod(0o750)
    put("/etc/nginx/conf.d/lab-site.conf", f"""server {{
    listen 8081;
    server_name lab-site.local
    root {x.work}/wwww;
    index index.html;
    location / {{ try_files $uri $uri/ =404; }}
}}
""")
    x.secret = {"tok": tok}

def c_m09t1(x):
    q = []
    rc, out = sh("nginx -t")
    q.append(R("nginx -t passes", rc == 0, out[-150:]))
    q.append(R("nginx is running", svc("nginx.service").get("ActiveState") == "active"))
    code, body = http("http://127.0.0.1:8081/")
    q.append(R("http://127.0.0.1:8081/ returns 200", code == 200, f"status {code}"))
    q.append(R("page contains the site token (correct content served)", x.secret["tok"] in body))
    conf = Path("/etc/nginx/conf.d/lab-site.conf")
    q.append(R("lab-site.conf still listens on 8081", conf.exists() and "listen 8081" in conf.read_text()))
    return q

add("M09-T1", "Nginx site will not load (three layers of faults)",
    lambda x: f"""\
INCIDENT #010
  A new site was configured in /etc/nginx/conf.d/lab-site.conf (port 8081, content in {x.work}/www).
  `curl http://127.0.0.1:8081/` must return the page. It does not.
TASK
  1. nginx -t   (read the message, fix, repeat)         2. systemctl reload nginx
  3. curl -i http://127.0.0.1:8081/                      4. tail /var/log/nginx/error.log  when you get an HTTP error
  There is more than one fault. After one is fixed another one will show up.
  The web server runs as user www-data - think about what it must be allowed to read.
CONSTRAINTS   Do not use chmod 777. Do not edit nginx.conf or the default site.
EXPECTED RESULT   HTTP 200 with the page text.""",
    s_m09t1, c_m09t1,
    hints=["Missing ';' and a mistyped directory name (compare the root path with ls).", "403 + error.log 'Permission denied' -> www-data cannot enter the dir / read the file. namei -l helps.",
           "Fix: chmod o+rx on the directory, chmod o+r on index.html (or chown/chgrp to www-data)."],
    bad=[(r"/etc/nginx/nginx\.conf", "you edited the main nginx.conf - the fault is only in conf.d/lab-site.conf"),
         (r"sites-enabled/default", "do not touch the default site")],
    debrief="nginx -t before every reload; error.log tells you the truth; 403 is nearly always file permissions.")

def s_m09t2(x):
    ensure_nginx()
    pid = spawn("app-backend", "--http", 9102)
    put("/etc/nginx/conf.d/lab-proxy.conf", """server {
    listen 8082;
    location / {
        proxy_pass http://127.0.0.1:9101;
    }
}
""")
    sh("nginx -t && systemctl reload nginx")
    x.secret = {"pid": pid}

def c_m09t2(x):
    q = []
    code, body = http("http://127.0.0.1:8082/")
    q.append(R("http://127.0.0.1:8082/ returns 200 with the backend answer", code == 200 and "LAB-OK" in body, f"status {code}"))
    conf = Path("/etc/nginx/conf.d/lab-proxy.conf")
    txt = conf.read_text() if conf.exists() else ""
    q.append(R("config forwards the Host header (proxy_set_header Host $host;)", re.search(r"proxy_set_header\s+Host\s+\$host\s*;", txt) is not None))
    b = proc("app-backend")
    if not b.alive or b.pid != x.secret["pid"]:
        x.error("the backend was restarted/killed - the fault is in nginx, not in the backend")
    q.append(R("backend process untouched (same PID, running)", b.alive and b.pid == x.secret["pid"]))
    q.append(R("nginx -t passes", sh("nginx -t")[0] == 0))
    return q

add("M09-T2", "502 Bad Gateway",
    lambda x: """\
INCIDENT #011
  nginx on port 8082 should forward everything to the application backend, but users see '502 Bad Gateway'.
TASK
  1. curl -i http://127.0.0.1:8082/
  2. Read the real reason:  sudo tail -n 5 /var/log/nginx/error.log
  3. Find on which port the backend REALLY listens:  sudo ss -tlnp | grep labproc
  4. Fix /etc/nginx/conf.d/lab-proxy.conf. Also add best practice: proxy_set_header Host $host;
  5. nginx -t && systemctl reload nginx, then test again.
CONSTRAINTS   The backend is correct - do not restart it or change its port. Only nginx config changes.
EXPECTED RESULT   curl returns 200 and 'LAB-OK ...'.""",
    s_m09t2, c_m09t2,
    hints=["error.log says 'connect() failed (111: Connection refused) while connecting to upstream' - nothing listens on that port.", "ss -tlnp shows the true backend port."],
    debrief="502 = nginx cannot talk to the upstream. Compare proxy_pass with what is actually listening.")

# ---------------------------------------------------------------- M09-T3  virtual hosts
def s_m09t3(x):
    ensure_nginx()
    ta, tb = "A" + rnd_word(random.Random(), 5).upper(), "B" + rnd_word(random.Random(), 5).upper()
    for n, t in (("a", ta), ("b", tb)):
        put(x.work / f"site-{n}/index.html", f"<h1>SITE {t}</h1>\n", 0o644)
    for p in (x.work, x.work / "site-a", x.work / "site-b"):
        p.chmod(0o755)
    put("/etc/nginx/conf.d/lab-vhosts.conf", f"""server {{
    listen 8083;
    server_name a.lab.test;
    root {x.work}/site-a;
}}
server {{
    listen 8083;
    server_name a.lab.test;
    root {x.work}/site-b;
}}
""")
    sh("nginx -t && systemctl reload nginx")
    x.secret = {"a": ta, "b": tb}

def c_m09t3(x):
    q = []
    def get(host):
        rc, out = sh(f"curl -s -m 5 -w '\\n%{{http_code}}' -H 'Host: {host}' http://127.0.0.1:8083/")
        body, _, code = out.rpartition("\n")
        return int(code) if code.isdigit() else 0, body
    c, b = get("a.lab.test"); q.append(R("Host a.lab.test -> site A", c == 200 and x.secret["a"] in b, f"{c}"))
    c, b = get("b.lab.test"); q.append(R("Host b.lab.test -> site B", c == 200 and x.secret["b"] in b, f"{c}"))
    c, b = get("unknown.example"); q.append(R("any other Host -> 404 (default_server with 'return 404')", c == 404, f"got {c}"))
    q.append(R("nginx -t passes", sh("nginx -t")[0] == 0))
    return q

add("M09-T3", "Name-based virtual hosts",
    lambda x: f"""\
SCENARIO   Two sites share port 8083: a.lab.test (root {x.work}/site-a) and b.lab.test (root {x.work}/site-b).
           Today BOTH names show the same site, and unknown host names must not leak a real site.
TASK
  1. Reproduce:  curl -H 'Host: a.lab.test' http://127.0.0.1:8083/   and the same with b.lab.test (and a made-up host).
  2. Fix /etc/nginx/conf.d/lab-vhosts.conf: every site gets its OWN server_name; add a catch-all
     server block marked default_server that answers  return 404;  for every other Host.
  3. nginx -t && systemctl reload nginx, then test all three requests again.
EXPECTED RESULT   a -> A page, b -> B page, anything else -> 404.""",
    s_m09t3, c_m09t3,
    hints=["Two server blocks with the same listen+server_name: the first wins, the second is ignored (nginx -t even warns about it).", "listen 8083 default_server; server_name _; return 404;"],
    debrief="nginx picks the server block by listen port, then by Host header; default_server catches the rest.")

# ---------------------------------------------------------------- M09-T4  access control + hardening
def s_m09t4(x):
    ensure_nginx()
    put(x.work / "www/index.html", "<h1>front</h1>\n", 0o644)
    put(x.work / "www/admin/index.html", "<h1>admin</h1>\n", 0o644)
    for p in (x.work, x.work / "www", x.work / "www/admin"): p.chmod(0o755)
    put("/etc/nginx/conf.d/lab-secure.conf", f"""server {{
    listen 8084;
    root {x.work}/www;
}}
""")
    sh("nginx -t && systemctl reload nginx")

def c_m09t4(x):
    q = []
    code, _ = http("http://127.0.0.1:8084/admin/")
    q.append(R("/admin/ is reachable from 127.0.0.1", code == 200, f"got {code}"))
    gw, ip, ns, ssh = net_truth() if "net_truth" in globals() else (None, None, None, None)
    if ip:
        rc, out = sh(f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' --interface {ip} http://{ip}:8084/admin/")
        q.append(R("/admin/ is FORBIDDEN (403) from any other address", out.strip() == "403", f"got {out.strip()}"))
    else:
        q.append(R("(no non-loopback address in this VM - external test skipped)", True))
    code, body = http("http://127.0.0.1:8084/health")
    q.append(R("/health returns 200 and 'ok'", code == 200 and "ok" in body, f"got {code}"))
    rc, hdr = sh("curl -sI -m 5 http://127.0.0.1:8084/")
    srv = re.search(r"^Server:\s*(.+)$", hdr, re.M | re.I)
    q.append(R("Server header does not reveal the nginx version (server_tokens off)", bool(srv) and "/" not in srv.group(1), srv.group(1) if srv else hdr[:60]))
    q.append(R("nginx -t passes", sh("nginx -t")[0] == 0))
    return q

add("M09-T4", "Restrict access and stop leaking information",
    lambda x: f"""\
SCENARIO   Site on port 8084 (config /etc/nginx/conf.d/lab-secure.conf, content {x.work}/www). Security review demands:
  1. /admin/ only from 127.0.0.1 - everybody else gets 403   (allow / deny inside a location block)
  2. /health must answer 200 with the text 'ok' (exact match location, no access log)
  3. The Server response header must not show the nginx version   (server_tokens off)
  Test the 403 case from your own non-loopback address:  curl --interface $(hostname -I | awk '{{print $1}}') http://$(hostname -I | awk '{{print $1}}'):8084/admin/
EXPECTED RESULT   All three requirements verified with curl.""",
    s_m09t4, c_m09t4,
    hints=["location /admin/ { allow 127.0.0.1; deny all; }", "location = /health { access_log off; return 200 \"ok\\n\"; }", "server_tokens off;  (in the server block)"],
    debrief="allow/deny, exact-match locations and server_tokens are the first hardening steps for any nginx site.")

compose("M09-X1", "BLOCK EXAM: web server incidents", "Four sites on one nginx are misbehaving.", ["M09-T1", "M09-T2", "M09-T3", "M09-T4"])
