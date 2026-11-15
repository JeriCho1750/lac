from course.core import *

module(10, "Apache HTTP Server", """\
apache2ctl configtest (ALWAYS before reload)    systemctl reload apache2    journalctl -u apache2    /var/log/apache2/error.log
Debian layout: /etc/apache2/sites-available/NAME.conf  ->  a2ensite NAME (symlink into sites-enabled)   a2dissite NAME
Modules: a2enmod rewrite|headers|proxy|proxy_http   a2dismod X   apache2ctl -M (loaded modules)    Config snippets: a2enconf / a2disconf
<VirtualHost *:PORT> ServerName x  DocumentRoot /path  <Directory /path> Require all granted  AllowOverride None|FileInfo|All </Directory> </VirtualHost>
Directories outside /var/www are DENIED by default: 403 + 'client denied by server configuration' = missing 'Require all granted'.
.htaccess only works when AllowOverride allows it and the needed module is loaded.
In this lab Apache listens on 8180-8184 (nginx keeps port 80).""", track="Hosting & Web")

def ensure_apache():
    apt_install("apache2")
    ports = Path("/etc/apache2/ports.conf")
    save_orig(ports)
    txt = ports.read_text()
    if "Listen 8181" not in txt:
        txt = re.sub(r"^Listen 80\s*$", "Listen 8180", txt, flags=re.M)
        txt += "\nListen 8181\nListen 8182\nListen 8183\nListen 8184\n"
        ports.write_text(txt)
    sh("a2dissite 000-default >/dev/null 2>&1; systemctl enable apache2 >/dev/null 2>&1; systemctl restart apache2")

def apache_reload():
    sh("apache2ctl configtest >/dev/null 2>&1 && systemctl reload apache2")

# ---------------------------------------------------------------- A-T1  site enabling and 403
def s_m10t1(x):
    ensure_apache()
    tok = "AP" + rnd_word(random.Random(), 5).upper()
    put(x.work / "www/index.html", f"<h1>APACHE {tok}</h1>\n", 0o644)
    for p in (x.work, x.work / "www"): p.chmod(0o755)
    put("/etc/apache2/sites-available/lab-site.conf", f"""<VirtualHost *:8181>
    ServerName lab-site.local
    DocumentRoot {x.work}/wwww
    <Directory {x.work}/www>
        Options -Indexes
    </Directory>
</VirtualHost>
""")
    x.secret = {"tok": tok}

def c_m10t1(x):
    q = []
    rc, out = sh("apache2ctl configtest")
    q.append(R("apache2ctl configtest: Syntax OK", "Syntax OK" in out, out[-100:]))
    q.append(R("site lab-site is ENABLED (symlink in sites-enabled)", Path("/etc/apache2/sites-enabled/lab-site.conf").exists()))
    code, body = http("http://127.0.0.1:8181/")
    q.append(R("http://127.0.0.1:8181/ returns 200 with the page", code == 200 and x.secret["tok"] in body, f"status {code}"))
    q.append(R("directory listing stays disabled (Options -Indexes kept)", "-Indexes" in Path("/etc/apache2/sites-available/lab-site.conf").read_text()))
    return q

add("M10-T1", "Apache: enable a site, fix 403",
    lambda x: f"""\
INCIDENT   New site on port 8181: config /etc/apache2/sites-available/lab-site.conf, content {x.work}/www.
           `curl -i http://127.0.0.1:8181/` must return the page. It does not.
TASK       1. apache2ctl configtest   2. a2ensite lab-site   3. systemctl reload apache2   4. curl -i ...  5. read /var/log/apache2/error.log
           There are several faults (a path, a missing access rule, a disabled site). Fix them one by one.
CONSTRAINTS   Keep 'Options -Indexes'. No chmod 777.
EXPECTED RESULT   HTTP 200 with the page text.""",
    s_m10t1, c_m10t1,
    hints=["Compare DocumentRoot with the real directory name (ls).", "403 'client denied by server configuration' -> add 'Require all granted' inside <Directory> for the REAL path.", "a2ensite lab-site && systemctl reload apache2"],
    bad=[(r"a2dissite\s+(000-default|default)", "do not touch other sites")],
    debrief="Debian Apache: sites-available is the library, sites-enabled is what runs; directories outside /var/www need an explicit Require.")

# ---------------------------------------------------------------- A-T2  .htaccess + rewrite
def s_m10t2(x):
    ensure_apache()
    tok = "RW" + rnd_word(random.Random(), 5).upper()
    put(x.work / "www/new.html", f"<h1>NEW PAGE {tok}</h1>\n", 0o644)
    put(x.work / "www/.htaccess", "RewriteEngine On\nRewriteRule ^old$ /new.html [R=301,L]\n", 0o644)
    for p in (x.work, x.work / "www"): p.chmod(0o755)
    sh("a2dismod rewrite >/dev/null 2>&1")
    put("/etc/apache2/sites-available/lab-rewrite.conf", f"""<VirtualHost *:8182>
    DocumentRoot {x.work}/www
    <Directory {x.work}/www>
        Require all granted
        AllowOverride None
    </Directory>
</VirtualHost>
""")
    sh("a2ensite lab-rewrite >/dev/null 2>&1"); apache_reload()
    x.secret = {"tok": tok}

def c_m10t2(x):
    q = []
    rc, hdr = sh("curl -sI -m 5 http://127.0.0.1:8182/old")
    q.append(R("/old answers 301", " 301 " in hdr.splitlines()[0] if hdr else False, hdr.splitlines()[0] if hdr else "no answer"))
    q.append(R("Location points to /new.html", re.search(r"^Location:.*?/new\.html", hdr, re.M | re.I) is not None))
    code, body = http("http://127.0.0.1:8182/new.html")
    q.append(R("/new.html returns 200", code == 200 and x.secret["tok"] in body))
    q.append(R("mod_rewrite is loaded", "rewrite_module" in sh("apache2ctl -M")[1]))
    q.append(R(".htaccess itself unchanged (fix the server, not the file)", "RewriteRule ^old$ /new.html [R=301,L]" in (x.work / "www/.htaccess").read_text()))
    return q

add("M10-T2", ".htaccess and mod_rewrite",
    lambda x: f"""\
INCIDENT   {x.work}/www/.htaccess redirects /old to /new.html, but http://127.0.0.1:8182/old gives 404.
TASK       Find out why the rule is ignored (two independent reasons: a module and an override setting), fix the SERVER side
           (vhost /etc/apache2/sites-available/lab-rewrite.conf + modules), do NOT edit .htaccess.
           Test:  curl -sI http://127.0.0.1:8182/old    -> 301 + Location: /new.html
EXPECTED RESULT   301 redirect works.""",
    s_m10t2, c_m10t2,
    hints=["apache2ctl -M | grep rewrite  (empty = module not loaded) -> a2enmod rewrite", "AllowOverride None makes Apache ignore .htaccess. FileInfo is enough for rewrite rules."],
    debrief="Two switches must be on for .htaccess rewrites: the module and AllowOverride.")

# ---------------------------------------------------------------- A-T3  security headers
def s_m10t3(x):
    ensure_apache()
    put(x.work / "www/index.html", "<h1>headers</h1>\n", 0o644)
    for p in (x.work, x.work / "www"): p.chmod(0o755)
    sh("a2dismod headers >/dev/null 2>&1")
    put("/etc/apache2/sites-available/lab-headers.conf", f"""<VirtualHost *:8183>
    DocumentRoot {x.work}/www
    <Directory {x.work}/www>
        Require all granted
    </Directory>
</VirtualHost>
""")
    sh("a2ensite lab-headers >/dev/null 2>&1"); apache_reload()

def c_m10t3(x):
    q = []
    rc, hdr = sh("curl -sI -m 5 http://127.0.0.1:8183/")
    q.append(R("X-Frame-Options: DENY is sent", re.search(r"^X-Frame-Options:\s*DENY\s*$", hdr, re.M | re.I) is not None))
    q.append(R("X-Content-Type-Options: nosniff is sent", re.search(r"^X-Content-Type-Options:\s*nosniff\s*$", hdr, re.M | re.I) is not None))
    srv = re.search(r"^Server:\s*(.+?)\s*$", hdr, re.M | re.I)
    q.append(R("Server header is just 'Apache' (ServerTokens Prod)", bool(srv) and srv.group(1) == "Apache", srv.group(1) if srv else "no Server header"))
    q.append(R("changes live in a conf-enabled snippet named lab-security", Path("/etc/apache2/conf-enabled/lab-security.conf").exists()))
    q.append(R("apache2ctl configtest OK", "Syntax OK" in sh("apache2ctl configtest")[1]))
    return q

add("M10-T3", "Apache hardening: headers and version hiding",
    lambda x: """\
SCENARIO   Penetration-test finding: the site on port 8183 reveals the Apache version and lacks basic security headers.
TASK       Create the snippet /etc/apache2/conf-available/lab-security.conf and enable it (a2enconf lab-security) so that every response has
              X-Frame-Options: DENY     X-Content-Type-Options: nosniff     and the Server header shows only 'Apache'
           (ServerTokens Prod, ServerSignature Off). The headers need mod_headers (a2enmod headers).
           Verify:  curl -sI http://127.0.0.1:8183/
EXPECTED RESULT   All three points visible in the response headers.""",
    s_m10t3, c_m10t3,
    hints=["Header always set X-Frame-Options \"DENY\"", "a2enmod headers ; a2enconf lab-security ; apache2ctl configtest ; systemctl reload apache2"],
    debrief="Small config snippets (conf-available/conf-enabled) keep global settings tidy and reversible.")

# ---------------------------------------------------------------- A-T4  reverse proxy
def s_m10t4(x):
    ensure_apache()
    pid = spawn("ap-backend", "--http", 9301)
    sh("a2enmod proxy proxy_http >/dev/null 2>&1")
    put("/etc/apache2/sites-available/lab-proxy.conf", """<VirtualHost *:8184>
    ProxyPass / http://127.0.0.1:9300/
    ProxyPassReverse / http://127.0.0.1:9300/
</VirtualHost>
""")
    sh("a2ensite lab-proxy >/dev/null 2>&1"); apache_reload()
    x.secret = {"pid": pid}

def c_m10t4(x):
    q = []
    code, body = http("http://127.0.0.1:8184/")
    q.append(R("http://127.0.0.1:8184/ returns the backend answer (200, LAB-OK)", code == 200 and "LAB-OK" in body, f"status {code}"))
    txt = Path("/etc/apache2/sites-available/lab-proxy.conf").read_text()
    q.append(R("ProxyPreserveHost On is set", re.search(r"^\s*ProxyPreserveHost\s+On\s*$", txt, re.M | re.I) is not None))
    b = proc("ap-backend")
    if not b.alive or b.pid != x.secret["pid"]:
        x.error("the backend was restarted/killed - the fault is in the Apache config")
    q.append(R("backend untouched", b.alive and b.pid == x.secret["pid"]))
    return q

add("M10-T4", "Apache as reverse proxy: 503 Service Unavailable",
    lambda x: """\
INCIDENT   Apache on port 8184 should forward to the application backend but answers '503 Service Unavailable'.
TASK       curl -i http://127.0.0.1:8184/  ;  sudo tail /var/log/apache2/error.log  ;  sudo ss -tlnp | grep labproc
           Fix /etc/apache2/sites-available/lab-proxy.conf (wrong backend port) and add  ProxyPreserveHost On.
           apache2ctl configtest && systemctl reload apache2.   The backend is fine - do not touch it.
EXPECTED RESULT   200 and 'LAB-OK ...'.""",
    s_m10t4, c_m10t4,
    hints=["error.log: 'AH00957: HTTP: attempt to connect to 127.0.0.1:9300 failed'.", "ss -tlnp shows the real backend port."],
    debrief="Proxy faults are almost always 'wrong upstream address'. The error log names it.")

compose("M10-X1", "BLOCK EXAM: Apache incidents", "Four Apache vhosts are broken.", ["M10-T1", "M10-T2", "M10-T3", "M10-T4"])
