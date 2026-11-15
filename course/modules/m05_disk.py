from course.core import *

# ------------------------------------------------------------------ 5. Disk
module(5, "Disk and Filesystems", """\
df -h (free space per filesystem)    du -ah DIR | sort -h | tail   du -sh DIR/*    lsblk    findmnt    mount / umount
ls -lhS DIR  (biggest first)    find DIR -type f -size +10M    truncate -s 0 FILE (empty a file but keep it)
'df says full but du shows little' = deleted file still held open by a process:  lsof +L1   or   lsof -nP | grep deleted
Space is released only when the LAST process closes the deleted file (stop the process or restart the service).
Never delete files you cannot identify - read the task rules.""", track="Foundation")

def make_disk():
    sh(f"truncate -s 80M {IMG} && mkfs.ext4 -q -F {IMG}")
    MNT.mkdir(parents=True, exist_ok=True)
    rc, out = sh(f"mount -o loop {IMG} {MNT}")
    if rc != 0:
        raise RuntimeError("cannot mount loop image: " + out)

def pct_used():
    s = os.statvfs(MNT)
    return 100 * (1 - s.f_bavail / (s.f_blocks - (s.f_bfree - s.f_bavail)))

def s_m05t1(x):
    make_disk()
    put(MNT / "app.log", "".join(f"2025-01-01 INFO request {i} ok\n" for i in range(150000))[:6_000_000])
    for i in (1, 2, 3):
        put(MNT / f"app.log.{i}", b"old log data\n" * 900000)
    put(MNT / "old-dump-2021.sql", b"-- ancient dump\n" * 1000000)
    put(MNT / "keep/customers.db", os.urandom(2_000_000))
    x.secret = {"app": sha(MNT / "app.log"), "db": sha(MNT / "keep/customers.db")}

def c_m05t1(x):
    q = []
    pu = pct_used() if MNT.exists() else 100
    q.append(R(f"usage of {MNT} is below 60%", pu < 60, f"now {pu:.0f}%"))
    if sha(MNT / "app.log") != x.secret["app"]:
        x.error("app.log (the CURRENT log) was modified or deleted - it had to stay untouched")
    if sha(MNT / "keep/customers.db") != x.secret["db"]:
        x.error("keep/customers.db was modified or deleted - NEVER touch keep/")
    q.append(R("app.log intact", sha(MNT / "app.log") == x.secret["app"]))
    q.append(R("keep/customers.db intact", sha(MNT / "keep/customers.db") == x.secret["db"]))
    q.append(R("rotated logs app.log.N removed", not list(MNT.glob("app.log.*"))))
    q.append(R("old-dump-2021.sql removed", not (MNT / "old-dump-2021.sql").exists()))
    return q

add("M05-T1", "Disk full: find and free space safely",
    lambda x: f"""\
INCIDENT #004
  The application volume {MNT} (a separate 80 MB filesystem) is ~90% full; the app will stop soon.
TASK
  1. Check usage:  df -h {MNT}
  2. Find what uses the space:  du -ah {MNT} | sort -h | tail -15   and  ls -lhS {MNT}
  3. Free space using THESE rules only:
       SAFE TO DELETE : rotated logs  app.log.1 app.log.2 app.log.3   and   old-dump-2021.sql
       DO NOT TOUCH   : app.log (the log being written right now)  and the folder keep/
  4. Verify usage dropped below 60% and the protected files still exist.
EXPECTED RESULT   Space freed, nothing important lost.""",
    s_m05t1, c_m05t1,
    hints=["du -ah /mnt/lab-data | sort -h | tail", "rm app.log.1 app.log.2 app.log.3 old-dump-2021.sql (list them explicitly, no wildcards for keep/)"],
    debrief="Identify -> classify (safe/protected) -> delete -> verify. Never mass-delete on a production volume.")

def s_m05t2(x):
    make_disk()
    put(MNT / "data/small.dat", b"s" * 5_000_000)
    q = MNT / "spool/queue.dat"
    put(q, b"q" * 30_000_000)
    spawn("spool-writer", "--hold", q)
    spawn("metrics-agent")
    q.unlink()
    x.secret = {"base": pct_used()}

def c_m05t2(x):
    q, w, m = [], proc("spool-writer"), proc("metrics-agent")
    gh = deleted_open_on(MNT)
    q.append(R("no deleted-but-open files remain on the volume", not gh, str(gh[:2])))
    q.append(R("spool-writer stopped with SIGTERM", not w.alive and "TERM" in w.sigs))
    if not w.alive and "TERM" not in w.sigs:
        x.error("spool-writer was SIGKILLed - use SIGTERM")
    if not m.alive:
        x.error("metrics-agent was killed - it is unrelated and had to stay running")
    q.append(R("metrics-agent still running", m.alive))
    q.append(R("volume usage below 25%", pct_used() < 25, f"now {pct_used():.0f}%"))
    return q

add("M05-T2", "df says full, du says empty",
    lambda x: f"""\
INCIDENT #005
  `df -h {MNT}` shows the volume about 40% used, but `du -sh {MNT}` shows only ~5 MB.
  Someone deleted a big file while a process was still using it.
TASK
  1. Prove the mismatch with df and du.
  2. Find the process holding a DELETED file:  sudo lsof +L1   (or: sudo lsof | grep deleted)
  3. Identify it by PID + command line. Two helpers run: spool-writer (disposable, the culprit)
     and metrics-agent (important, unrelated - LEAVE IT).
  4. Stop the culprit with SIGTERM, then confirm the space came back with df -h.
EXPECTED RESULT   Space released, metrics-agent untouched.""",
    s_m05t2, c_m05t2,
    hints=["lsof +L1 lists open files with link count 0 (deleted).", "kill PID (SIGTERM). Then df -h again."],
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="Space is freed only when the last holder closes the file - a classic cause of 'phantom' full disks.")

# ---------------------------------------------------------------- M05-T3  fstab
def s_m05t3(x):
    img = LAB / "disk2.img"
    sh(f"truncate -s 30M {img} && mkfs.ext4 -q -F {img}")
    tmp = Path("/mnt/lab-tmpmount"); tmp.mkdir(exist_ok=True)
    sh(f"mount -o loop {img} {tmp}")
    put(tmp / "test.sh", "#!/bin/sh\necho script-ran\n", 0o755)
    put(tmp / "data.txt", "payload\n")
    sh(f"umount {tmp}; rmdir {tmp}")
    save_orig("/etc/fstab")

def c_m05t3(x):
    q, mp = [], Path("/mnt/lab-data2")
    ft = Path("/etc/fstab").read_text()
    line = next((l for l in ft.splitlines() if "disk2.img" in l and not l.strip().startswith("#")), "")
    f = line.split()
    q.append(R("/etc/fstab has an entry for disk2.img -> /mnt/lab-data2 (ext4)", len(f) >= 4 and f[1] == "/mnt/lab-data2" and f[2] == "ext4", line or "no entry"))
    opts = f[3].split(",") if len(f) > 3 else []
    for o in ("loop", "noexec", "nosuid", "nofail"):
        q.append(R(f"fstab option '{o}'", o in opts))
    q.append(R("the filesystem is mounted at /mnt/lab-data2 now", sh("mountpoint -q /mnt/lab-data2")[0] == 0))
    rc, out = sh("/mnt/lab-data2/test.sh")
    q.append(R("noexec really works (the script on the volume cannot be executed)", rc != 0 and "script-ran" not in out))
    q.append(R("data.txt readable on the volume", (mp / "data.txt").exists()))
    return q

add("M05-T3", "Mount a filesystem permanently (fstab)",
    lambda x: f"""\
SCENARIO   A new 30 MB disk image  {LAB}/disk2.img  (ext4) must be available at  /mnt/lab-data2  after every reboot.
           It is a data volume: nothing on it may ever be executed, and set-uid bits must be ignored.
TASK
  1. mkdir -p /mnt/lab-data2
  2. cp /etc/fstab /etc/fstab.bak   (always back up first!)
  3. Add ONE line to /etc/fstab: file system = the image, mount point, type ext4, options: loop,noexec,nosuid,nofail  dump 0, pass 2
  4. Test WITHOUT rebooting:  mount -a  (a mistake here would break the real boot!) ;  findmnt /mnt/lab-data2
  5. Prove noexec: /mnt/lab-data2/test.sh must fail with 'Permission denied'.
EXPECTED RESULT   Volume mounted by 'mount -a', safe options active.""",
    s_m05t3, c_m05t3,
    hints=["/opt/linux-lab/disk2.img /mnt/lab-data2 ext4 loop,noexec,nosuid,nofail 0 2", "findmnt -o TARGET,OPTIONS /mnt/lab-data2 shows active options."],
    bad=[(r">\s*/etc/fstab(\s|$)", "'>' OVERWRITES /etc/fstab! Use >> or an editor")],
    debrief="Test fstab with mount -a before rebooting; nofail keeps a bad disk from blocking the boot.")

# ---------------------------------------------------------------- M05-T4  inode exhaustion
def s_m05t4(x):
    sh(f"truncate -s 40M {IMG} && mkfs.ext4 -q -F -N 1400 {IMG}")
    MNT.mkdir(parents=True, exist_ok=True)
    rc, out = sh(f"mount -o loop {IMG} {MNT}")
    if rc: raise RuntimeError(out)
    for d, n in (("spool-a", 600), ("spool-b", 540), ("queue", 150)):
        (MNT / d).mkdir()
        for i in range(n):
            (MNT / d / f"m{i}.msg").touch()
    put(MNT / "keep/important.txt", "do not delete\n")
    sh(f"chmod -R a+rwX {MNT}")
    x.secret = {"q": sha(MNT / "keep/important.txt")}

def c_m05t4(x):
    s = os.statvfs(MNT)
    used = 100 * (s.f_files - s.f_ffree) / s.f_files
    q = [R("inode usage of /mnt/lab-data below 60%", used < 60, f"now {used:.0f}%")]
    qn = len(list((MNT / "queue").glob("*.msg"))) if (MNT / "queue").is_dir() else 0
    if qn != 150:
        x.error("files in queue/ were deleted - queue/ holds LIVE mail, only spool-a and spool-b are junk")
    q.append(R("queue/ still has all 150 live messages", qn == 150))
    q.append(R("keep/important.txt intact", sha(MNT / "keep/important.txt") == x.secret["q"]))
    return q

add("M05-T4", "Disk 'full' but df -h shows free space (inodes)",
    lambda x: f"""\
INCIDENT   Applications on {MNT} fail with 'No space left on device', yet `df -h {MNT}` shows plenty of free space.
TASK
  1. Check inodes:  df -i {MNT}    (IUse% 100% = no more files can be created, even if bytes are free)
  2. Find which directory holds the most files:  for d in {MNT}/*; do echo "$(find $d -type f | wc -l) $d"; done | sort -rn
  3. RULES   spool-a and spool-b contain junk -> delete their contents.   queue/ = live mail, keep/ = important: DO NOT TOUCH.
  4. Verify IUse% fell below 60%.
EXPECTED RESULT   Inodes freed, protected data intact.""",
    s_m05t4, c_m05t4,
    hints=["df -i shows IUse%.", "rm /mnt/lab-data/spool-a/* may say 'argument list too long' for huge dirs: find DIR -type f -delete"],
    debrief="A filesystem can run out of inodes before it runs out of bytes - millions of tiny files do that.")

compose("M05-X1", "BLOCK EXAM: disks and mounts", "A data volume is full and a new volume must be mounted safely.", ["M05-T1", "M05-T3"])
