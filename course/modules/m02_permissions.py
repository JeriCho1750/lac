from course.core import *

# ------------------------------------------------------------------ 2. Permissions
module(2, "Files and Permissions", """\
ls -l shows  -rwxr-x---  = type | owner rwx | group r-x | others ---.   r=4 w=2 x=1  => rwx=7 r-x=5 r--=4
chmod 750 FILE   chmod u+x,g-w,o-rwx FILE   chmod -R only when you really mean it
chown user:group FILE   chgrp GROUP FILE   chmod 2770 DIR (setgid: new files inherit the directory's group)
Directories need x to be entered! To open /a/b/c you need x on /a and /a/b.
namei -l /full/path   (shows permissions of every path component - the best tool for 'Permission denied')
sudo -u USER cmd   (run a command as another user to TEST access)""", track="Foundation")

def s_m02t1(x):
    sh("getent group lab_devs >/dev/null || groupadd lab_devs")
    w = x.work / "webapp"
    put(w / "deploy.sh", "#!/bin/bash\necho deploying\n", 0o777)
    put(w / "secrets.env", "DB_PASSWORD=hunter2\n", 0o644)
    put(w / "public/index.html", "<h1>Hello</h1>\n", 0o600)
    put(w / "public/style.css", "body{}\n", 0o600)
    (w / "public").chmod(0o700)
    (w / "shared").mkdir(exist_ok=True); (w / "shared").chmod(0o755)

def c_m02t1(x):
    w, q = x.work / "webapp", []
    def st(p):
        try: return os.stat(p)
        except OSError: return None
    def mode(p): s = st(p); return None if s is None else s.st_mode & 0o7777
    def gname(p):
        s = st(p)
        try: return grp.getgrgid(s.st_gid).gr_name
        except Exception: return "?"
    q.append(R("deploy.sh = rwxr-x--- (750)", mode(w / "deploy.sh") == 0o750, f"now {oct(mode(w/'deploy.sh') or 0)}"))
    q.append(R("deploy.sh group is lab_devs", gname(w / "deploy.sh") == "lab_devs"))
    q.append(R("secrets.env = rw------- (600)", mode(w / "secrets.env") == 0o600, f"now {oct(mode(w/'secrets.env') or 0)}"))
    q.append(R("public/ = rwxr-xr-x (755)", mode(w / "public") == 0o755))
    q.append(R("public/index.html and style.css = rw-r--r-- (644)",
               mode(w / "public/index.html") == 0o644 and mode(w / "public/style.css") == 0o644))
    q.append(R("shared/ = rwxrws--- (2770) with group lab_devs", mode(w / "shared") == 0o2770 and gname(w / "shared") == "lab_devs",
               f"now {oct(mode(w/'shared') or 0)} group {gname(w/'shared')}"))
    return q

add("M02-T1", "Fix wrong permissions on a web application",
    lambda x: f"""\
SCENARIO
  A developer uploaded a web app with careless permissions. Harden it according to the policy below.
  Group 'lab_devs' already exists.

WORKSPACE   {x.work}/webapp   (owned by root - use sudo)

POLICY
  deploy.sh           owner: rwx   group lab_devs: r-x   others: nothing      (group must be lab_devs)
  secrets.env         owner: rw    group: nothing        others: nothing
  public/             directory rwxr-xr-x
  public/index.html   rw-r--r--   and   public/style.css  rw-r--r--
  shared/             owner rwx, group lab_devs rwx, others nothing,
                      and the SETGID bit so new files inherit group lab_devs

CONSTRAINTS
  Never use chmod 777. Do not change anything outside webapp/.
EXPECTED RESULT   `ls -lR {x.work}/webapp` shows exactly this policy.""",
    s_m02t1, c_m02t1,
    hints=["chmod 750 deploy.sh ; chgrp lab_devs deploy.sh   (or chown :lab_devs).", "For files inside public/ do not use chmod -R on the directory (files and dirs need different modes).",
           "setgid on a directory: chmod 2770 shared  (the leading 2)."],
    debrief="Least privilege: only the access that is really needed. Setgid directories keep team files in one group.")

def s_m02t2(x):
    sh("useradd -m -s /bin/bash lab_reader")
    put(x.work / "reports/q3.txt", "Q3 revenue summary: OK\n", 0o640)
    put(x.work / "reports/payroll.txt", "CONFIDENTIAL payroll\n", 0o640)
    (x.work / "reports").chmod(0o750)

def c_m02t2(x):
    f, p, q = x.work / "reports/q3.txt", x.work / "reports/payroll.txt", []
    rc, out = sh(f"cat {f}", user="lab_reader")
    q.append(R("lab_reader CAN read reports/q3.txt", rc == 0 and "Q3" in out, out[:80] if rc else ""))
    rc, _ = sh(f"cat {p}", user="lab_reader")
    q.append(R("lab_reader can NOT read reports/payroll.txt (confidential!)", rc != 0))
    rc, _ = sh(f"touch {x.work}/reports/x_test", user="lab_reader")
    sh(f"rm -f {x.work}/reports/x_test")
    q.append(R("lab_reader can NOT create files in reports/", rc != 0))
    ww = [str(z) for z in (x.work, x.work / "reports", f, p) if z.exists() and z.stat().st_mode & 0o002]
    q.append(R("nothing is world-writable", not ww, ", ".join(ww)))
    return q

add("M02-T2", "'Permission denied' investigation",
    lambda x: f"""\
SCENARIO
  User 'lab_reader' reports:  cat: {x.work}/reports/q3.txt: Permission denied
  He must read q3.txt. He must NOT be able to read payroll.txt (same folder, confidential).
  He must not be able to create or change anything there.

TASK
  1. Reproduce the problem:  sudo -u lab_reader cat {x.work}/reports/q3.txt
  2. Find WHICH path component blocks him (use namei -l and ls -ld).
  3. Fix it with the MINIMUM change. Any correct method is fine (permissions or ACLs).
  4. Re-test as lab_reader: q3.txt readable, payroll.txt still denied.

CONSTRAINTS   No chmod 777, no chmod -R, do not make payroll.txt readable.
EXPECTED RESULT   Only q3.txt becomes accessible for lab_reader.""",
    s_m02t2, c_m02t2,
    hints=["namei -l /full/path/to/q3.txt shows every component and its permissions.",
           "A directory needs the x bit for 'others' (or a group) before anyone can reach files inside.",
           "chmod o+x on the directory + chmod o+r on q3.txt only. Then test payroll.txt again - it must still fail."],
    debrief="Directory x-bit = permission to pass through. Always test fixes as the affected user.")

# ---------------------------------------------------------------- M02-T3  ACL
def s_m02t3(x):
    apt_install("acl")
    sh("useradd -m -s /bin/bash lab_reader; useradd -m -s /bin/bash lab_writer")
    put(x.work / "shared/budget.txt", "Budget 2025: confidential\n", 0o600)
    put(x.work / "shared/readme.txt", "Public readme\n", 0o644)

def c_m02t3(x):
    f, q = x.work / "shared/budget.txt", []
    st = f.stat()
    q.append(R("owner/group/others bits unchanged for others (no access for others)", st.st_mode & 0o007 == 0, oct(st.st_mode & 0o777)))
    acl = sh(f"getfacl -p {f}")[1]
    q.append(R("ACL entry user:lab_reader:r--", re.search(r"^user:lab_reader:r--$", acl, re.M) is not None))
    q.append(R("ACL entry user:lab_writer:rw-", re.search(r"^user:lab_writer:rw-$", acl, re.M) is not None))
    q.append(R("lab_reader can read budget.txt", sh(f"cat {f}", user="lab_reader")[0] == 0))
    q.append(R("lab_reader can NOT write budget.txt", sh(f"echo x >> {f}", user="lab_reader")[0] != 0))
    rc = sh(f"echo '-- edit' >> {f}", user="lab_writer")[0]
    q.append(R("lab_writer CAN write budget.txt", rc == 0))
    q.append(R("owner is still root:root", st.st_uid == 0 and st.st_gid == 0))
    return q

add("M02-T3", "ACLs: give two users different rights on ONE file",
    lambda x: f"""\
SCENARIO   File {x.work}/shared/budget.txt (root:root, mode 600) must be READ by lab_reader and READ+WRITTEN by lab_writer.
           Nobody else gets access. You may NOT change the owner/group of the file and may not open it to 'others'.
TASK       Use ACLs:  setfacl -m u:USER:perm FILE   then verify with getfacl FILE and test with sudo -u USER ...
           (the 'acl' package is installed for you; the directory path must also be reachable - it already is).
EXPECTED RESULT   Exact rights as above, mode bits for others still empty.""",
    s_m02t3, c_m02t3,
    hints=["sudo setfacl -m u:lab_reader:r,u:lab_writer:rw budget.txt", "getfacl budget.txt shows the entries; 'ls -l' now shows a + at the end of the mode."],
    debrief="ACLs give per-user exceptions without changing owner, group or the 'others' bits.")

# ---------------------------------------------------------------- M02-T4  permission audit
def g_m02t4(x, r):
    base = x.work / "audit"
    ww = suid = ox = 0
    for i in range(r.randint(30, 50)):
        m = r.choice([0o644, 0o640, 0o600, 0o755, 0o666, 0o777, 0o4755, 0o750, 0o664])
        f = put(base / r.choice(["bin", "etc", "var/tmp", "srv/app"]) / f"f{i}", "x\n", m)
        mode = f.stat().st_mode
        mode = f.stat().st_mode
        ww += bool(mode & 0o002); suid += bool(mode & 0o4000); ox += bool(mode & 0o001)
    return {"world_writable_files": (ww, "regular files writable by 'others' (find -type f -perm -0002)", "int"),
            "suid_files": (suid, "regular files with the SETUID bit (find -type f -perm -4000)", "int"),
            "executable_by_others": (ox, "regular files executable by 'others' (-perm -0001)", "int")}

answers_task("M02-T4", "Security audit with find -perm",
    lambda x: f"""\
SCENARIO   Security review of {x.work}/audit. Count dangerous permission patterns. Do NOT fix anything - only report.
USE        find DIR -type f -perm -0002 | wc -l    (-perm -MODE = 'at least these bits are set')""",
    g_m02t4, keep_modes=True,
    hints=["find audit -type f -perm -0002 | wc -l", "SUID is mode 4000: find audit -type f -perm -4000"],
    debrief="World-writable and SUID files are the first things an auditor (or attacker) looks for.")

compose("M02-X1", "BLOCK EXAM: permissions", "A new colleague changed permissions all over the place. Fix and audit.",
        ["M02-T1", "M02-T2", "M02-T3", "M02-T4"])
