from course.core import *

module(13, "WordPress Hosting", """\
Stack: browser -> nginx -> PHP-FPM (unix socket /run/php/phpX.Y-fpm.sock) -> WordPress PHP files -> MariaDB.
wp-config.php: DB_NAME DB_USER DB_PASSWORD DB_HOST.  'Error establishing a database connection' = wrong credentials/name/host or DB down.
502 Bad Gateway = nginx cannot reach PHP-FPM (wrong socket path, service down).  Blank page / HTTP 500 = PHP error: php -l FILE, tail /var/log/nginx/error.log
php-fpm service name contains the version:  systemctl status php*-fpm       sockets:  ls /run/php/
Permissions (best practice): files owned by root (or deploy user), group www-data; wp-config.php 640; only wp-content/uploads writable by www-data.
Backup = files (tar czf site.tar.gz -C /path/to/site .) + database (mysqldump DB > db.sql).  Restore = extract + mysql DB < db.sql.
Test as the web user:  sudo -u www-data touch /path/file""", track="Hosting & Web")

WPTGZ = CACHE / "wordpress.tar.gz"

def php_fpm_service():
    rc, out = sh("systemctl list-unit-files 'php*-fpm.service' --no-legend | awk '{print $1}' | head -1")
    return out.strip() or "php-fpm"

def php_sock():
    socks = sorted(Path("/run/php").glob("php*-fpm.sock"))
    return str(socks[-1]) if socks else None

def ensure_wp_stack():
    apt_install("nginx", "mariadb-server", "php-fpm", "php-mysql", "php-xml", "php-mbstring", "php-curl", "php-gd", "php-zip", "curl", "tar")
    sh("systemctl enable --now nginx mariadb")
    sh(f"systemctl enable --now {php_fpm_service()}")
    for _ in range(30):
        if php_sock(): break
        time.sleep(0.5)
    if not php_sock():
        raise RuntimeError("php-fpm socket not found in /run/php")
    if not WPTGZ.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(dim("  downloading WordPress (one time) ..."))
        rc, out = sh(f"curl -fsSL -o {WPTGZ} https://wordpress.org/latest.tar.gz", timeout=600)
        if rc:
            WPTGZ.unlink(missing_ok=True)
            raise RuntimeError("cannot download WordPress (internet?): " + out[-150:])

def wp_nginx(port, root, name, sock=None):
    put(f"/etc/nginx/conf.d/{name}", f"""server {{
    listen {port};
    root {root};
    index index.php;
    location / {{ try_files $uri $uri/ /index.php?$args; }}
    location ~ \\.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:{sock or php_sock()};
    }}
}}
""")
    sh("nginx -t && systemctl reload nginx")

def wp_home(port, tok):
    code, body = http(f"http://127.0.0.1:{port}/", t=30)
    return code == 200 and tok in body, code

def deploy_wp(x, n, install=True):
    """Deploy a real WordPress into <work>/wp on port 809<n>, database lab_wp<n>. Returns a dict with the facts."""
    ensure_wp_stack()
    port, db, user = 8090 + n, f"lab_wp{n}", f"lab_wp{n}u"
    pw = "Wp" + rnd_word(random.Random(), 8) + "9!"
    tok = "WP" + rnd_word(random.Random(), 5).upper()
    root = x.work / "wp"
    root.mkdir(parents=True, exist_ok=True)
    for p in (x.work, root):
        p.chmod(0o755)
    sh(f"tar xzf {WPTGZ} -C {root} --strip-components=1")
    mysql_run(f"CREATE DATABASE {db}; CREATE USER '{user}'@'localhost' IDENTIFIED BY '{pw}'; GRANT ALL ON {db}.* TO '{user}'@'localhost';")
    cfg = (root / "wp-config-sample.php").read_text()
    cfg = cfg.replace("database_name_here", db).replace("username_here", user).replace("password_here", pw)
    (root / "wp-config.php").write_text(cfg)
    sh(f"chown -R www-data:www-data {root}")
    wp_nginx(port, root, f"lab-wp{n}.conf")
    if install:
        data = f"weblog_title=Lab+WP+{tok}&user_name=admin&admin_password=Adm1n%21Lab%2129&admin_password2=Adm1n%21Lab%2129&pw_weak=1&admin_email=admin%40lab.test&blog_public=0&Submit=Install+WordPress"
        sh(f"curl -s -m 150 -o /dev/null -d '{data}' 'http://127.0.0.1:{port}/wp-admin/install.php?step=2'", timeout=180)
        ok, code = wp_home(port, tok)
        if not ok:
            raise RuntimeError(f"WordPress did not come up after installation (HTTP {code}); check nginx/php-fpm/mariadb")
    return {"port": port, "db": db, "user": user, "pw": pw, "tok": tok, "root": str(root)}

def edit_cfg(root, a, b):
    f = Path(root) / "wp-config.php"
    t = f.read_text()
    assert a in t, a
    f.write_text(t.replace(a, b, 1))

# ---------------------------------------------------------------- W1  database connection error
def s_m13t1(x):
    d = deploy_wp(x, 1)
    edit_cfg(d["root"], f"'{d['pw']}'", f"'{d['pw']}x'")
    edit_cfg(d["root"], f"'{d['db']}'", f"'{d['db']}_old'")
    x.secret = d

def c_m13t1(x):
    d, q = x.secret, []
    ok, code = wp_home(d["port"], d["tok"])
    q.append(R(f"http://127.0.0.1:{d['port']}/ shows the site again (HTTP 200 with the site title)", ok, f"HTTP {code}"))
    rc, _ = sh(f"mysql -u{d['user']} -p'{d['pw']}' {d['db']} -e 'SELECT 1'")
    q.append(R("the database account was not changed (original password still works)", rc == 0))
    cfg = (Path(d["root"]) / "wp-config.php").read_text()
    q.append(R("wp-config.php uses the real DB_NAME and DB_USER", f"'{d['db']}'" in cfg and f"'{d['user']}'" in cfg))
    return q

add("M13-T1", "WordPress: 'Error establishing a database connection'",
    lambda x: f"""\
INCIDENT   After a 'config cleanup' the WordPress site {x.work}/wp on http://127.0.0.1:{x.secret['port']}/ shows
           'Error establishing a database connection'.  The database side is healthy and must NOT be changed:
           database {x.secret['db']}, user {x.secret['user']}, password {x.secret['pw']}   (from the password vault)
TASK       1. curl -i http://127.0.0.1:{x.secret['port']}/       2. Look at the DB settings in {x.work}/wp/wp-config.php
           3. List the real database names (read only):  sudo mysql -e 'SHOW DATABASES'
           4. Test the vault credentials from the command line:    mysql -u USER -p DBNAME
           5. Fix wp-config.php (two faults) - not the database!
EXPECTED RESULT   The home page loads again.""",
    s_m13t1, c_m13t1,
    hints=["DB_NAME must match 'SHOW DATABASES' exactly.", "Compare DB_PASSWORD in wp-config.php character by character with the vault password.", "If mysql -u USER -p DBNAME works, the same values must be in wp-config.php."],
    debrief="That WordPress error always means: WordPress could not log in to MariaDB - check name, user, password, host, and that MariaDB runs.")

# ---------------------------------------------------------------- W2  502 and white page
def s_m13t2(x):
    d = deploy_wp(x, 2)
    wp_nginx(d["port"], d["root"], "lab-wp2.conf", sock="/run/php/php7.4-fpm.sock")
    edit_cfg(d["root"], "define( 'DB_HOST', 'localhost' );", "define( 'DB_HOST', 'localhost' )")
    x.secret = d

def c_m13t2(x):
    d, q = x.secret, []
    ok, code = wp_home(d["port"], d["tok"])
    q.append(R("the site loads (HTTP 200 + title)", ok, f"HTTP {code}"))
    rc, out = sh(f"php -l {d['root']}/wp-config.php")
    q.append(R("php -l wp-config.php: no syntax errors", rc == 0, out[:80]))
    conf = Path("/etc/nginx/conf.d/lab-wp2.conf").read_text()
    m = re.search(r"fastcgi_pass\s+unix:(\S+);", conf)
    q.append(R("fastcgi_pass points to an EXISTING php-fpm socket", bool(m) and Path(m.group(1)).exists(), m.group(1) if m else "no fastcgi_pass"))
    return q

add("M13-T2", "WordPress: 502 and then a blank page",
    lambda x: f"""\
INCIDENT   http://127.0.0.1:{x.secret['port']}/ answers '502 Bad Gateway'.  (site files: {x.work}/wp, nginx vhost /etc/nginx/conf.d/lab-wp2.conf)
TASK       1. curl -i the site; read  sudo tail /var/log/nginx/error.log   (what does nginx say about the socket?)
           2. ls /run/php/   shows the REAL PHP-FPM socket; fix fastcgi_pass; nginx -t && systemctl reload nginx
           3. A second fault will appear (blank page / HTTP 500). Find it:  php -l {x.work}/wp/wp-config.php   and the nginx error log.
EXPECTED RESULT   The WordPress site loads.""",
    s_m13t2, c_m13t2,
    hints=["error.log: 'connect() to unix:/run/php/php7.4-fpm.sock failed (2: No such file or directory)'", "php -l prints 'PHP Parse error ... on line N' - look at that line (a missing ;)."],
    debrief="502 = nginx cannot reach PHP-FPM; a blank 500 page = PHP itself crashed. Different layers, different logs.")

# ---------------------------------------------------------------- W3  permissions
def s_m13t3(x):
    d = deploy_wp(x, 3)
    sh(f"chown -R root:root {d['root']}; chmod 644 {d['root']}/wp-config.php; rm -rf {d['root']}/wp-content/uploads")
    x.secret = d

def c_m13t3(x):
    d, q = x.secret, []
    root = Path(d["root"])
    up = root / "wp-content/uploads"
    q.append(R("wp-content/uploads exists", up.is_dir()))
    q.append(R("www-data CAN write into wp-content/uploads", up.is_dir() and sh(f"touch {up}/_t && rm {up}/_t", user="www-data")[0] == 0))
    q.append(R("www-data can NOT modify core files (wp-includes is read-only for the web user)", sh(f"touch {root}/wp-includes/_t", user="www-data")[0] != 0))
    q.append(R("www-data can still READ wp-config.php", sh(f"cat {root}/wp-config.php >/dev/null", user="www-data")[0] == 0))
    q.append(R("other users can NOT read wp-config.php (no world-read bit)", sh(f"cat {root}/wp-config.php", user="nobody")[0] != 0))
    ok, code = wp_home(d["port"], d["tok"])
    q.append(R("the site still loads", ok, f"HTTP {code}"))
    return q

add("M13-T3", "WordPress: secure file permissions",
    lambda x: f"""\
SCENARIO   Security audit of {x.work}/wp: everything is owned by root, wp-config.php (it contains the DB password!) is world-readable and
           media uploads fail because wp-content/uploads does not exist / is not writable for the web server user (www-data).
POLICY     - wp-content/uploads exists and is writable by www-data
           - wp-config.php: readable by www-data (group), NOT readable by anybody else
           - the web user must NOT be able to modify WordPress core files (e.g. wp-includes/)
           - the site must keep working
TEST       sudo -u www-data touch FILE   (try the places above)     namei -l PATH
EXPECTED RESULT   Least privilege for the web server.""",
    s_m13t3, c_m13t3,
    hints=["chgrp www-data wp-config.php && chmod 640 wp-config.php", "mkdir wp-content/uploads && chown www-data:www-data wp-content/uploads (and chmod 755/775)", "Do NOT chown -R the whole tree to www-data - that lets a hacked plugin rewrite core files."],
    debrief="Only uploads (and cache) need to be writable by the web user. Everything else read-only.")

# ---------------------------------------------------------------- W4  backup restore
def s_m13t4(x):
    d = deploy_wp(x, 4)
    bk = x.work / "backups"; bk.mkdir(exist_ok=True)
    sh(f"tar czf {bk}/wp-files.tar.gz -C {d['root']} .")
    sh(f"mysqldump {d['db']} > {bk}/wp-db.sql")
    d["posts"] = int(qv("SELECT COUNT(*) FROM wp_posts", d["db"]))
    sh(f"rm -rf {d['root']}/wp-includes {d['root']}/wp-config.php")
    mysql_run("DROP TABLE wp_options, wp_posts;", d["db"])
    x.secret = d
    x.own(bk)

def c_m13t4(x):
    d, q = x.secret, []
    root = Path(d["root"])
    q.append(R("wp-config.php and wp-includes/ are back", (root / "wp-config.php").is_file() and (root / "wp-includes").is_dir()))
    try: n = int(qv("SELECT COUNT(*) FROM wp_posts", d["db"]))
    except ValueError: n = -1
    q.append(R(f"database restored: wp_posts has {d['posts']} rows again", n == d["posts"], f"now {n}"))
    ok, code = wp_home(d["port"], d["tok"])
    q.append(R("the original site (with its title) loads again", ok, f"HTTP {code}"))
    return q

add("M13-T4", "WordPress disaster recovery from backups",
    lambda x: f"""\
INCIDENT   The site on http://127.0.0.1:{x.secret['port']}/ is gone: core files were deleted ({x.work}/wp) and two database tables were dropped.
           Yesterday's backups: {x.work}/backups/wp-files.tar.gz (the whole site directory) and wp-db.sql (dump of database {x.secret['db']}).
TASK       1. Document what is broken (curl -i, ls, sudo mysql {x.secret['db']} -e 'SHOW TABLES').
           2. Restore the files:   tar -xzf ...  into {x.work}/wp   (it overwrites missing/changed files; keep ownership www-data)
           3. Restore the database:   sudo mysql {x.secret['db']} < wp-db.sql
           4. Verify in the browser/curl and with a row count.
EXPECTED RESULT   The original site with its content.""",
    s_m13t4, c_m13t4,
    hints=["sudo tar -xzf backups/wp-files.tar.gz -C wp   (run as root so that ownership is preserved)", "sudo mysql lab_wp4 < backups/wp-db.sql"],
    debrief="Files + database = a WordPress backup. Restore both, then verify with the real site.")

compose("M13-X1", "BLOCK EXAM: WordPress hosting (takes a few minutes to prepare)",
        "Three customer sites on one server, three different problems.", ["M13-T1", "M13-T2", "M13-T4"])
