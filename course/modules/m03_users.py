from course.core import *
import datetime

# ------------------------------------------------------------------ 3. Users
module(3, "Users and Groups", """\
useradd -m -s /bin/bash -c "Comment" NAME      passwd NAME      id NAME      groups NAME
groupadd G    usermod -aG G USER (ADD to group - without -a you REPLACE all groups!)    gpasswd -d USER G (remove)
usermod -L USER / passwd -l USER (lock)    userdel -r USER (delete + home)    getent passwd|group|shadow NAME
Shell /usr/sbin/nologin = account cannot log in interactively (service accounts)
sudo: never edit /etc/sudoers directly; put files in /etc/sudoers.d/ and validate with  visudo -cf FILE
Files in sudoers.d must NOT contain a dot or end with ~ (they are silently ignored), mode 0440.""", track="Foundation")

def s_m03t1(x):
    sh("useradd -m -s /bin/sh lab_bob")
    sh("useradd -m -s /bin/bash lab_old && echo 'lab_old:Old#Pass1' | chpasswd && usermod -aG sudo lab_old")
    sh("useradd -m -s /bin/bash lab_temp")
    put("/home/lab_temp/data.txt", "temporary data\n")

def c_m03t1(x):
    q = []
    a = getuser("lab_alice")
    q.append(R("user lab_alice exists", a is not None))
    q.append(R("lab_alice: home /home/lab_alice exists, shell /bin/bash, comment 'Alice Admin'",
               a is not None and a.pw_dir == "/home/lab_alice" and Path(a.pw_dir).is_dir() and a.pw_shell == "/bin/bash" and "Alice Admin" in a.pw_gecos))
    m = group_members("lab_team") or []
    q.append(R("group lab_team exists with members lab_alice AND lab_bob", group_members("lab_team") is not None and {"lab_alice", "lab_bob"} <= set(m)))
    b = getuser("lab_bob")
    if b is None:
        x.error("lab_bob was deleted - you only had to add him to a group")
    q.append(R("lab_bob still exists with his original shell /bin/sh", b is not None and b.pw_shell == "/bin/sh"))
    s = getuser("lab_svc")
    sp = sh("getent shadow lab_svc")[1].split(":")
    q.append(R("lab_svc: shell nologin/false", s is not None and s.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false")))
    q.append(R("lab_svc has no usable password", s is not None and len(sp) > 1 and (sp[1] == "" or sp[1][0] in "!*")))
    o = getuser("lab_old")
    if o is None:
        x.error("lab_old was deleted - the task said LOCK it, not delete")
    spo = sh("getent shadow lab_old")[1].split(":")
    q.append(R("lab_old exists and its password is LOCKED", o is not None and len(spo) > 1 and spo[1].startswith("!")))
    q.append(R("lab_old is no longer in group sudo", o is not None and "lab_old" not in (group_members("sudo") or [])))
    q.append(R("lab_temp deleted together with /home/lab_temp", getuser("lab_temp") is None and not Path("/home/lab_temp").exists()))
    return q

add("M03-T1", "Onboarding and offboarding users",
    lambda x: """\
SCENARIO   HR sends you a list of account changes. Do all of them.
TASK
  1. Create user lab_alice: home /home/lab_alice, login shell /bin/bash, full name (comment) "Alice Admin".
  2. Create group lab_team. Add lab_alice AND the existing user lab_bob to it as a SUPPLEMENTARY group
     (do not change lab_bob's primary group, shell, or anything else).
  3. Create service account lab_svc: it must NOT be able to log in (nologin shell) and has no password.
  4. Employee lab_old left the company. Do NOT delete the account (audit!). LOCK its password and
     remove it from the 'sudo' group.
  5. lab_temp is a finished contractor: delete the user AND the home directory.
CONSTRAINTS   Do not delete lab_bob or lab_old.
EXPECTED RESULT   `id`, `getent passwd`, `getent group lab_team` confirm every point.""",
    s_m03t1, c_m03t1,
    hints=["usermod -aG lab_team lab_bob  (note -a!).", "passwd -l lab_old (or usermod -L); gpasswd -d lab_old sudo.", "userdel -r lab_temp removes the home too."],
    debrief="Lock instead of delete keeps ownership/audit trail; usermod -aG without -a would have wiped group memberships.")

def s_m03t2(x):
    sh("useradd -m -s /bin/bash lab_carol")
    put(BIN / "lab-restart-demo.sh", "#!/bin/bash\necho 'demo service restarted'\n", 0o755)

def c_m03t2(x):
    q, f = [], Path("/etc/sudoers.d/lab-ops")
    q.append(R("group lab_ops exists and contains lab_carol", "lab_carol" in (group_members("lab_ops") or [])))
    q.append(R("file /etc/sudoers.d/lab-ops exists with mode 0440", f.is_file() and (f.stat().st_mode & 0o7777) == 0o440))
    q.append(R("visudo -cf says the file is valid", f.is_file() and sh(f"visudo -cf {f}")[0] == 0))
    rc, out = sh(f"runuser -u lab_carol -- sudo -n {BIN}/lab-restart-demo.sh")
    q.append(R("lab_carol can run lab-restart-demo.sh via sudo without password", rc == 0 and "restarted" in out, out[:100]))
    rc, _ = sh("runuser -u lab_carol -- sudo -n /usr/bin/id")
    q.append(R("lab_carol can NOT run any other command via sudo", rc != 0))
    return q

add("M03-T2", "Delegate ONE command with sudo",
    lambda x: f"""\
SCENARIO
  Support engineer lab_carol must restart the demo app, but must not get full root.
  The 'restart' is represented by the script  {BIN}/lab-restart-demo.sh

TASK
  1. Create group lab_ops and add lab_carol to it.
  2. Create /etc/sudoers.d/lab-ops (exactly this name, mode 0440) that lets members of lab_ops run ONLY
     {BIN}/lab-restart-demo.sh as root, WITHOUT a password.
  3. Validate the file with visudo -cf BEFORE you rely on it.
  4. Test as lab_carol:  sudo -u lab_carol sudo -n {BIN}/lab-restart-demo.sh   -> works
                         sudo -u lab_carol sudo -n id                           -> must be refused
CONSTRAINTS   Do not edit /etc/sudoers itself. Never grant ALL commands.
EXPECTED RESULT   Exactly one command is delegated.""",
    s_m03t2, c_m03t2,
    hints=["Rule syntax:  %GROUP ALL=(root) NOPASSWD: /full/path/to/command", "Use  sudo visudo -f /etc/sudoers.d/lab-ops  - it checks syntax when you save.",
           "Use full absolute paths in sudoers rules."],
    bad=[(r"/etc/sudoers(\s|$)", "do not edit /etc/sudoers directly - use /etc/sudoers.d/ + visudo")],
    debrief="Least privilege for sudo: list exact commands, validate with visudo. A syntax error in sudoers can lock you out of root.")

# ---------------------------------------------------------------- M03-T3  password aging
def s_m03t3(x):
    for u in ("lab_u1", "lab_u2"):
        sh(f"useradd -m -s /bin/bash {u} && echo '{u}:Start#Pass1' | chpasswd")

def c_m03t3(x):
    q = []
    def shadow(u):
        p = sh(f"getent shadow {u}")[1].split(":")
        return p + [""] * (9 - len(p))
    s1, s2 = shadow("lab_u1"), shadow("lab_u2")
    q.append(R("lab_u1 must change password at next login (last change = 0)", s1[2] == "0", f"lastchg={s1[2]}"))
    q.append(R("lab_u1: minimum age 1 day", s1[3] == "1", f"min={s1[3]}"))
    q.append(R("lab_u1: maximum age 90 days", s1[4] == "90", f"max={s1[4]}"))
    q.append(R("lab_u1: warning 7 days", s1[5] == "7", f"warn={s1[5]}"))
    days = (datetime.date(2030, 1, 1) - datetime.date(1970, 1, 1)).days
    q.append(R("lab_u2: account expires 2030-01-01", s2[7] == str(days), f"expire={s2[7]}"))
    q.append(R("lab_u2: password itself untouched (not locked)", not s2[1].startswith("!")))
    return q

add("M03-T3", "Password policy with chage",
    lambda x: """\
SCENARIO   Security policy update for two existing accounts.
TASK
  lab_u1 : password must be changed at the NEXT login, minimum age 1 day, maximum age 90 days, warning 7 days before expiry.
  lab_u2 : a contractor - the account must EXPIRE on 2030-01-01 (do not lock the password).
  Verify with:  chage -l lab_u1  and  chage -l lab_u2
EXPECTED RESULT   chage -l shows exactly these values.""",
    s_m03t3, c_m03t3,
    hints=["chage -M 90 -m 1 -W 7 lab_u1 ; chage -d 0 lab_u1", "chage -E 2030-01-01 lab_u2"],
    debrief="chage manages ageing and expiry; -d 0 forces a password change at next login.")

# ---------------------------------------------------------------- M03-T4  who did what (auth log)
def g_m03t4(x, r):
    users = ["alice", "bob", "carol", "dave"]
    lines, sudo_ok, failed = [], set(), None
    files = ["/etc/hosts", "/etc/nginx/nginx.conf", "/etc/fstab"]
    edited = r.choice(files)
    t = 8 * 3600
    new_users = 0
    for i in range(r.randint(60, 90)):
        t += r.randint(20, 400)
        ts = time.strftime("%b %e %H:%M:%S", time.gmtime(t))
        kind = r.choice(["ok", "ssh", "ssh", "useradd", "ok"])
        u = r.choice(users)
        if kind == "ok":
            cmd = r.choice(["/usr/bin/apt update", "/usr/bin/systemctl status ssh", "/usr/bin/less /var/log/syslog"])
            lines.append(f"{ts} vm sudo:  {u} : TTY=pts/0 ; PWD=/home/{u} ; USER=root ; COMMAND={cmd}")
            sudo_ok.add(u)
        elif kind == "ssh":
            lines.append(f"{ts} vm sshd[{r.randint(1000,9999)}]: Accepted publickey for {u} from 192.168.56.{r.randint(2,50)} port 5{r.randint(1000,9999)} ssh2")
        else:
            lines.append(f"{ts} vm useradd[{r.randint(1000,9999)}]: new user: name=tmp{r.randint(1,99)}, UID={r.randint(1000,2000)}")
            new_users += 1
    failed = r.choice(users)
    t += 100
    lines.append(f"{time.strftime('%b %e %H:%M:%S', time.gmtime(t))} vm sudo:  {failed} : 3 incorrect password attempts ; TTY=pts/1 ; PWD=/home/{failed} ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow")
    t += 50
    editor = r.choice([u for u in users if u != failed])
    lines.append(f"{time.strftime('%b %e %H:%M:%S', time.gmtime(t))} vm sudo:  {editor} : TTY=pts/2 ; PWD=/home/{editor} ; USER=root ; COMMAND=/usr/bin/nano {edited}")
    sudo_ok.add(editor)
    put(x.work / "auth.log", "\n".join(lines) + "\n")
    return {"failed_sudo_user": (failed, "user with '3 incorrect password attempts'"),
            "edited_file": (edited, "file edited with nano via sudo (full path)"),
            "editor_user": (editor, "user who edited that file"),
            "new_users_created": (new_users, "number of 'useradd ... new user' lines", "int"),
            "sudo_users": (len(sudo_ok), "how many DIFFERENT users ran a sudo command successfully (lines with COMMAND= and no 'incorrect')", "int")}

answers_task("M03-T4", "Who did what? sudo and login audit",
    lambda x: f"""\
INCIDENT   /etc/ changed unexpectedly. Investigate the auth log excerpt {x.work}/auth.log.
           Note: a line with 'incorrect password attempts' is a FAILED sudo, it still contains COMMAND=.""",
    g_m03t4,
    hints=["grep 'incorrect' auth.log", "grep 'COMMAND=/usr/bin/nano' auth.log", "grep 'sudo:' auth.log | grep -v incorrect | awk '{print $6}' | sort -u | wc -l (check which field holds the user name)"],
    debrief="The sudo log is an audit trail: who, from where, which command, success or failure.")

compose("M03-X1", "BLOCK EXAM: users and accounts", "Onboarding, delegation, policy and an audit - all at once.",
        ["M03-T1", "M03-T2", "M03-T3", "M03-T4"])
