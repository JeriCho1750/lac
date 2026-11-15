from course.core import *

# ------------------------------------------------------------------ 10. DB
module(12, "Databases", """\
sudo mysql  (root via unix socket)    SHOW DATABASES; USE db; SHOW TABLES; DESCRIBE t;
SELECT cols FROM t WHERE cond GROUP BY c ORDER BY x DESC LIMIT n;   COUNT(*) SUM(col) AVG(col)   JOIN t2 ON t1.id=t2.fk
INSERT INTO t(a,b) VALUES(1,'x');  UPDATE t SET a=1 WHERE id=2;  DELETE FROM t WHERE id=2;  (ALWAYS use WHERE!)
CREATE USER 'u'@'localhost' IDENTIFIED BY 'pw';   GRANT SELECT,INSERT,UPDATE ON db.* TO 'u'@'localhost';   SHOW GRANTS FOR 'u'@'localhost';
Backup: mysqldump DB > file.sql     Restore: mysql DB < file.sql     Always verify row counts afterwards.""", track="Hosting & Web")

def s_m10t1(x):
    ensure_mariadb()
    seed_shop()
    x.work.mkdir(parents=True, exist_ok=True); x.own(x.work)

def c_m10t1(x):
    q, a, pw = [], answers(x), "LabApp#2025"
    rc, out = sh(f"mysql -ulab_app -p'{pw}' lab_shop -N -e 'SELECT COUNT(*) FROM orders'")
    q.append(R("user lab_app@localhost can log in with the given password", rc == 0, out[-100:]))
    g = sh("mysql -N -B -e \"SHOW GRANTS FOR 'lab_app'@'localhost'\"")[1]
    privs, extra = set(), False
    for l in g.splitlines():
        m = re.match(r"GRANT (.+) ON (\S+) TO", l)
        if not m: continue
        if "WITH GRANT OPTION" in l: extra = True
        if m.group(2) == "`lab_shop`.*":
            privs = {p.strip() for p in m.group(1).split(",")}
        elif m.group(1).strip() != "USAGE":
            extra = True
    q.append(R("privileges on lab_shop.* are exactly SELECT, INSERT, UPDATE", privs == {"SELECT", "INSERT", "UPDATE"}, f"now {sorted(privs)}"))
    q.append(R("no global privileges / GRANT OPTION", not extra))
    rc, _ = sh(f"mysql -ulab_app -p'{pw}' lab_shop -e 'DELETE FROM orders WHERE id=-1'")
    q.append(R("DELETE is denied for lab_app", rc != 0))
    chk(q, a, "pending_orders", qv("SELECT COUNT(*) FROM orders WHERE status='pending'"), "number of pending orders", "int")
    chk(q, a, "total_paid", qv("SELECT IFNULL(SUM(amount),0) FROM orders WHERE status='paid'"), "sum of amounts of paid orders", "float")
    chk(q, a, "top_customer", qv("SELECT c.name FROM customers c JOIN orders o ON o.customer_id=c.id WHERE o.status='paid' GROUP BY c.id ORDER BY SUM(o.amount) DESC LIMIT 1"), "customer with the highest paid total")
    return q

add("M12-T1", "MariaDB: least-privilege user and first queries",
    lambda x: f"""\
SCENARIO   Database lab_shop (tables customers, orders) exists. A web app needs its own account.
TASK
  1. Create user 'lab_app'@'localhost' with password  LabApp#2025
  2. Give it ONLY SELECT, INSERT, UPDATE on lab_shop.* (no DELETE, no DROP, no GRANT OPTION). FLUSH PRIVILEGES not required but harmless.
  3. Test the login:  mysql -ulab_app -p'LabApp#2025' lab_shop
  4. With SQL answer these, and write them in {x.work}/answers.txt  :
        pending_orders=<how many orders have status 'pending'>
        total_paid=<SUM(amount) of orders with status 'paid', e.g. 1234.56>
        top_customer=<NAME of the customer whose paid orders sum highest>
  Admin access:  sudo mysql   (root uses the unix socket, no password)
EXPECTED RESULT   Account works with minimal rights; three correct answers.""",
    s_m10t1, c_m10t1,
    hints=["CREATE USER 'lab_app'@'localhost' IDENTIFIED BY 'LabApp#2025'; GRANT SELECT, INSERT, UPDATE ON lab_shop.* TO 'lab_app'@'localhost';",
           "SELECT c.name, SUM(o.amount) s FROM customers c JOIN orders o ON o.customer_id=c.id WHERE o.status='paid' GROUP BY c.id ORDER BY s DESC;"],
    debrief="Apps get minimal rights: a SQL-injection through a SELECT/INSERT/UPDATE user cannot DROP your tables.")

def s_m10t2(x):
    ensure_mariadb()
    seed_shop()
    b = x.work / "backups"
    b.mkdir(parents=True, exist_ok=True)
    sh(f"mysqldump lab_shop > {b}/lab_shop-2025-06-01.sql")
    for _ in range(15):
        qv(f"INSERT INTO orders(customer_id,amount,status) VALUES({random.randint(1,8)},{random.randint(500,9000)/100},'paid')")
    sh(f"mysqldump lab_shop > {b}/lab_shop-2025-06-02.sql")
    x.secret = {"orders": int(qv("SELECT COUNT(*) FROM orders")), "sum": qv("SELECT SUM(amount) FROM orders"), "cust": int(qv("SELECT COUNT(*) FROM customers"))}
    mysql_run("DROP TABLE orders; DELETE FROM customers WHERE id%2=0;", "lab_shop")
    x.own(x.work)

def c_m10t2(x):
    q, s = [], x.secret
    try:
        n = int(qv("SELECT COUNT(*) FROM orders")); sm = qv("SELECT SUM(amount) FROM orders"); cu = int(qv("SELECT COUNT(*) FROM customers"))
    except (ValueError, TypeError):
        n, sm, cu = -1, "", -1
    q.append(R("orders table restored with the correct number of rows", n == s["orders"], f"now {n}"))
    q.append(R("orders total amount matches the latest dump", sm == s["sum"], f"now {sm}"))
    q.append(R("customers table complete again", cu == s["cust"], f"now {cu}"))
    pre = x.work / "backups/pre-restore.sql"
    q.append(R("backups/pre-restore.sql (dump of the DAMAGED state) exists", pre.is_file() and pre.stat().st_size > 200))
    return q

add("M12-T2", "Restore a database from a dump",
    lambda x: f"""\
INCIDENT #012
  Someone dropped table `orders` and deleted half of the customers in database lab_shop.
  Backups are in {x.work}/backups/ (named by date).
TASK
  1. Look at the damage:  sudo mysql lab_shop -e 'SHOW TABLES; SELECT COUNT(*) FROM customers;'
  2. SAFETY FIRST: dump the current damaged state to {x.work}/backups/pre-restore.sql  (mysqldump lab_shop > ...)
  3. Pick the MOST RECENT backup and restore it:  sudo mysql lab_shop < FILE
  4. Verify row counts afterwards (orders should have 75 rows, customers 8).
EXPECTED RESULT   Data identical to the latest backup; the pre-restore dump exists.""",
    s_m10t2, c_m10t2,
    hints=["ls -l backups ; the file with the later date is the newest.", "sudo mysqldump lab_shop > /path/pre-restore.sql  (redirect output into your file)."],
    debrief="Before a restore, snapshot the current state - you may need it. Then restore and verify counts.")

# ---------------------------------------------------------------- M12-T3  application cannot connect
def s_m12t3(x):
    ensure_mariadb()
    mysql_run("CREATE DATABASE lab_app_db; CREATE USER 'lab_appu'@'localhost' IDENTIFIED BY 'S3cret!x'; "
              "GRANT ALL ON lab_app_db.* TO 'lab_appu'@'localhost'; USE lab_app_db; CREATE TABLE t(id INT); INSERT INTO t VALUES(1);")
    put(x.work / "app.conf", "DB_HOST=localhost\nDB_NAME=lab_appdb\nDB_USER=lab_appu\nDB_PASS=S3cret!y\n")
    put(x.work / "dbcheck.sh", """#!/bin/bash
# Reads app.conf and tries to connect like the application would.
source "$(dirname "$0")/app.conf"
if out=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e 'SELECT COUNT(*) FROM t' 2>&1); then echo "DB OK"; else echo "DB ERROR: $out"; exit 1; fi
""", 0o755)
    x.own(x.work)

def c_m12t3(x):
    q = []
    rc, out = sh(f"{x.work}/dbcheck.sh")
    q.append(R("dbcheck.sh prints 'DB OK'", rc == 0 and "DB OK" in out, out[-120:]))
    rc, _ = sh("mysql -ulab_appu -p'S3cret!x' lab_app_db -e 'SELECT 1'")
    q.append(R("database account was NOT changed (old password still valid)", rc == 0))
    q.append(R("app.conf uses the real database name lab_app_db", "DB_NAME=lab_app_db" in (x.work / "app.conf").read_text()))
    return q

add("M12-T3", "The application cannot reach its database",
    lambda x: f"""\
INCIDENT   The web app reports 'database unavailable'. Its settings are in {x.work}/app.conf and the helper {x.work}/dbcheck.sh
           tries to connect exactly like the app. The DATABASE side is correct: database lab_app_db, user lab_appu,
           password S3cret!x  - do NOT change anything inside MariaDB.
TASK       Run dbcheck.sh, read the exact error, fix app.conf, repeat until it prints DB OK.
           (Each run reveals the next problem: unknown database -> access denied -> ...)
EXPECTED RESULT   DB OK.""",
    s_m12t3, c_m12t3,
    hints=["'Unknown database' = wrong DB_NAME.  'Access denied for user' = wrong user/password/host.", "sudo mysql -e 'SHOW DATABASES' tells you the real names (read only!)."],
    debrief="Connection problems are almost always one of: host, port, database name, user, password. The error text names which.")

# ---------------------------------------------------------------- M12-T4  slow query / index
def s_m12t4(x):
    ensure_mariadb()
    mysql_run("CREATE DATABASE lab_perf; USE lab_perf; CREATE TABLE events(id INT PRIMARY KEY, user_id INT, kind VARCHAR(10));"
              "INSERT INTO events SELECT seq, seq % 5000, 'click' FROM seq_1_to_80000;")

def c_m12t4(x):
    q = []
    idx = qv("SELECT column_name FROM information_schema.statistics WHERE table_schema='lab_perf' AND table_name='events' AND seq_in_index=1 AND index_name<>'PRIMARY'", "lab_perf")
    q.append(R("an index exists on events(user_id)", "user_id" in idx.split()))
    ex = qv("EXPLAIN SELECT COUNT(*) FROM events WHERE user_id=4242", "lab_perf")
    cols = ex.split("\t")
    q.append(R("EXPLAIN of the slow query now uses an index (key column is not NULL)", len(cols) > 5 and cols[5] not in ("NULL", ""), ex[:100]))
    q.append(R("table still has all 80000 rows", qv("SELECT COUNT(*) FROM events", "lab_perf") == "80000"))
    return q

add("M12-T4", "Slow query: add the right index",
    lambda x: """\
INCIDENT   Database lab_perf, table events (80 000 rows). This query is slow and scans the whole table:
               SELECT COUNT(*) FROM events WHERE user_id = 4242;
TASK
  1. Look at the plan:  sudo mysql lab_perf -e 'EXPLAIN SELECT COUNT(*) FROM events WHERE user_id=4242\\G'   (type: ALL = full scan, key: NULL)
  2. Add an index on user_id  (CREATE INDEX idx_user ON events(user_id);)
  3. EXPLAIN again: the key column must show your index and 'rows' must drop dramatically.
CONSTRAINTS   Do not delete or change rows.
EXPECTED RESULT   Index in place, query plan uses it.""",
    s_m12t4, c_m12t4,
    hints=["CREATE INDEX idx_user ON events(user_id);", "SHOW INDEX FROM events;"],
    debrief="EXPLAIN shows how a query runs; an index on the filtered column turns a table scan into a lookup.")

compose("M12-X1", "BLOCK EXAM: databases", "Three database problems at once.", ["M12-T2", "M12-T3", "M12-T4"])
