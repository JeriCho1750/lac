from course.core import *


module(17, "Backup and Recovery", """\
tar -czf out.tar.gz [--exclude='cache' --exclude='*.tmp'] -C PARENT DIR     tar -tzf out.tar.gz (list)     tar -xzf out.tar.gz -C DEST
sha256sum FILE > FILE.sha256     sha256sum -c FILE.sha256 (run in the same folder)
rsync -a SRC/ DEST/            (trailing slash on SRC = copy the CONTENTS)     rsync -a --delete SRC/ DEST/ (mirror: removes extras)
rsync -ani --delete SRC/ DEST/   (-n = dry run, -i = itemize: shows what WOULD change - empty output = identical)
DIRECTION MATTERS: rsync SOURCE DESTINATION. A swapped pair overwrites the good data!
A backup is only real after you have tested a restore.""", track="Infrastructure")

def s_m11t1(x):
    s = x.work / "site"
    put(s / "index.php", "<?php echo 'hi'; ?>\n"); put(s / "config.php", "<?php // cfg ?>\n")
    for i in range(3): put(s / f"uploads/p{i}.jpg", os.urandom(20000))
    for i in range(4): put(s / f"cache/c{i}.cache", b"c" * 5000)
    put(s / "logs/trace.tmp", "tmp\n"); put(s / "scripts/deploy.sh", "#!/bin/bash\necho ok\n", 0o755)
    (x.work / "backups").mkdir(exist_ok=True)
    x.own(x.work)

def c_m11t1(x):
    q, arc = [], x.work / "backups/site-backup.tar.gz"
    names, modes = [], {}
    try:
        with tarfile.open(arc) as t:
            for m in t.getmembers():
                names.append(m.name.rstrip("/")); modes[m.name] = m.mode
    except Exception as e:
        q.append(R("backups/site-backup.tar.gz is a valid gzip tar archive", False, str(e)[:80]))
        return q
    q.append(R("archive is valid", True))
    q.append(R("paths are relative and start with site/ (no absolute paths)", names and all(n == "site" or n.startswith("site/") for n in names)))
    for f in ("site/index.php", "site/config.php", "site/uploads/p0.jpg", "site/scripts/deploy.sh"):
        q.append(R(f"contains {f}", f in names))
    q.append(R("cache/ is EXCLUDED", not any("/cache" in n or n.endswith("cache") for n in names)))
    q.append(R("*.tmp files are EXCLUDED", not any(n.endswith(".tmp") for n in names)))
    q.append(R("deploy.sh kept its executable bit", modes.get("site/scripts/deploy.sh", 0) & 0o100 != 0))
    rc, out = sh(f"cd {x.work}/backups && sha256sum -c site-backup.sha256")
    q.append(R("site-backup.sha256 exists and `sha256sum -c` passes", rc == 0, out[-80:]))
    lst = x.work / "backups/listing.txt"
    q.append(R("listing.txt contains the archive listing", lst.is_file() and "site/index.php" in lst.read_text()))
    return q

add("M17-T1", "Create a verified backup with tar",
    lambda x: f"""\
SCENARIO   Back up the website in {x.work}/site before an upgrade.
TASK
  1. Create {x.work}/backups/site-backup.tar.gz containing the folder 'site' - paths inside must start with
     'site/' (use -C {x.work}), EXCLUDING the cache/ directory and every *.tmp file.
  2. Save the listing of the archive:   tar -tzf ... > {x.work}/backups/listing.txt
  3. Create a checksum file {x.work}/backups/site-backup.sha256 so that running
        cd {x.work}/backups && sha256sum -c site-backup.sha256     prints OK.
CONSTRAINTS   Do not modify the site folder.
EXPECTED RESULT   A clean, verifiable archive.""",
    s_m11t1, c_m11t1,
    hints=["tar -czf OUT --exclude='site/cache' --exclude='*.tmp' -C PARENT site", "cd into backups first, then: sha256sum site-backup.tar.gz > site-backup.sha256"],
    debrief="Relative paths, exclusions and a checksum make a backup portable and verifiable.")

def tree_hash(d):
    return {str(p.relative_to(d)): sha(p) for p in sorted(Path(d).rglob("*")) if p.is_file()}

def s_m11t2(x):
    live, mir = x.work / "live", x.work / "mirror"
    put(live / "a.txt", "alpha v2 (current)\n"); put(live / "b.txt", "bravo\n")
    put(live / "conf/app.conf", "secret=1\n", 0o600); put(live / "data/big.bin", os.urandom(200000))
    sh(f"cp -a {live} {mir}")
    time.sleep(1.1)
    put(mir / "a.txt", "alpha v1 (OLD)\n"); (mir / "b.txt").unlink()
    put(mir / "old.txt", "stale file\n"); (mir / "conf/app.conf").chmod(0o644)
    x.secret = {"live": tree_hash(live)}
    x.own(x.work)

def c_m11t2(x):
    live, mir, q = x.work / "live", x.work / "mirror", []
    intact = tree_hash(live) == x.secret["live"]
    if not intact:
        x.error("the SOURCE directory 'live' was changed/damaged - did you swap source and destination?")
    q.append(R("live/ is unchanged (your source data is safe)", intact))
    q.append(R("mirror/ is missing nothing and has no stale files (old.txt gone)", not (mir / "old.txt").exists() and (mir / "b.txt").exists()))
    rc, out = sh(f"rsync -ani --delete {live}/ {mir}/")
    q.append(R("`rsync -ani --delete live/ mirror/` shows NO differences (content, permissions, times)", rc == 0 and out == "", out[:100]))
    q.append(R("mirror/conf/app.conf kept mode 600", (mir / "conf/app.conf").exists() and ((mir / "conf/app.conf").stat().st_mode & 0o777) == 0o600))
    return q

add("M17-T2", "Mirror with rsync (mind the direction!)",
    lambda x: f"""\
SCENARIO   {x.work}/live is production data. {x.work}/mirror is an OUTDATED copy (old a.txt, missing b.txt,
           stale old.txt, wrong permissions).
TASK
  1. Preview first (dry run, no changes):  rsync -ani --delete SRC/ DEST/   - read what it would do.
  2. Make mirror/ an exact copy of live/ - same content, permissions and timestamps, stale files removed.
  3. Prove it: the dry run must now print nothing.
CONSTRAINTS   NEVER change live/. SOURCE comes first, DESTINATION second. Mind the trailing slashes.
EXPECTED RESULT   mirror == live; live untouched.""",
    s_m11t2, c_m11t2,
    hints=["rsync -a --delete live/ mirror/   (use full paths or cd into the folder first)", "-a keeps permissions and times, --delete removes files that no longer exist in the source."],
    debrief="Dry-run first, source before destination. A swapped pair would have destroyed the good data.")

# ---------------------------------------------------------------- M17-T3  rotation script
def s_m17t3(x):
    x.work.mkdir(parents=True, exist_ok=True); x.own(x.work)

def c_m17t3(x):
    s, q = x.work / "backup.sh", []
    if not s.is_file():
        return [R("backup.sh exists", False, str(s))]
    q.append(R("executable, starts with #!/bin/bash", os.access(s, os.X_OK) and s.read_text().startswith("#!")))
    t = x.work / "_t"; shutil.rmtree(t, ignore_errors=True)
    put(t / "src/a.txt", "alpha\n"); put(t / "src/sub/b.txt", "beta\n"); (t / "dest").mkdir()
    rc, _ = sh(f"{s}", timeout=10); q.append(R("no arguments -> exit 2", rc == 2, f"rc={rc}"))
    rc, _ = sh(f"{s} {t}/nodir {t}/dest 3", timeout=10); q.append(R("missing source dir -> exit 2", rc == 2, f"rc={rc}"))
    rc, _ = sh(f"{s} {t}/src {t}/dest abc", timeout=10); q.append(R("KEEP not a number -> exit 2", rc == 2, f"rc={rc}"))
    for i in range(1, 6):
        rc, out = sh(f"BACKUP_TS=20250101-00000{i} {s} {t}/src {t}/dest 3", timeout=20)
    q.append(R("normal run exits 0", rc == 0, f"rc={rc} {out[-60:]}"))
    names = sorted(p.name for p in (t / "dest").glob("*"))
    want = [f"backup-20250101-00000{i}.tar.gz" for i in (3, 4, 5)]
    q.append(R("after 5 runs with KEEP=3 exactly the 3 NEWEST archives remain (backup-<TS>.tar.gz)", names == want, f"found {names}"))
    ok = bool(names)
    for n in names:
        try:
            with tarfile.open(t / "dest" / n) as tf:
                ok &= any(m.name.endswith("a.txt") for m in tf.getmembers())
        except Exception:
            ok = False
    q.append(R("every archive is a valid tar.gz that contains the source files", ok))
    shutil.rmtree(t, ignore_errors=True)
    return q

add("M17-T3", "Backup script with rotation",
    lambda x: f"""\
TASK   Write {x.work}/backup.sh  (Bash)   usage:   backup.sh SRC_DIR DEST_DIR KEEP
   - Create  DEST_DIR/backup-<TS>.tar.gz  from SRC_DIR, where TS = ${{BACKUP_TS:-$(date +%Y%m%d-%H%M%S)}}
     (the BACKUP_TS variable lets the trainer test it deterministically).
   - Afterwards keep only the KEEP newest archives in DEST_DIR (delete older backup-*.tar.gz).
   - Wrong usage (not 3 args, SRC missing, KEEP not a number) -> message on stderr, exit code 2. Success -> exit 0.
   Use  ls -1 backup-*.tar.gz | sort | head -n -KEEP | xargs -r rm   or a loop - but never delete anything else.
EXPECTED RESULT   The trainer runs your script 5 times and inspects DEST_DIR.""",
    s_m17t3, c_m17t3,
    hints=["tar -czf \"$DEST/backup-$TS.tar.gz\" -C \"$(dirname \"$SRC\")\" \"$(basename \"$SRC\")\"", "ls -1 \"$DEST\"/backup-*.tar.gz | sort | head -n -\"$KEEP\" | xargs -r rm -f"],
    debrief="Retention (rotation) is half of a backup: without it the backup disk fills up and backups stop.")

# ---------------------------------------------------------------- M17-T4  restore drill
def s_m17t4(x):
    r = random.Random()
    src, bk = x.work / "build", x.work / "backups"
    bk.mkdir(parents=True, exist_ok=True)
    good_names = {}
    for day in range(1, 6):
        d = x.work / f"_s{day}"
        put(d / "site/index.html", f"<h1>version of day {day}</h1>\n"); put(d / "site/data.db", os.urandom(5000))
        arc = bk / f"site-2025-06-0{day}.tar.gz"
        sh(f"tar -czf {arc} -C {d} site && cd {bk} && sha256sum {arc.name} > {arc.name}.sha256")
        good_names[arc.name] = tree_hash(d / "site")
        shutil.rmtree(d)
    bad = r.sample(["site-2025-06-05.tar.gz", "site-2025-06-04.tar.gz", "site-2025-06-02.tar.gz"], 2)
    for n in bad:
        with open(bk / n, "r+b") as f:
            f.seek(100); f.write(b"CORRUPTED!")
    valid = sorted(n for n in good_names if n not in bad)
    x.secret = {"latest": valid[-1], "tree": good_names[valid[-1]], "bad": bad}
    x.own(x.work)

def c_m17t4(x):
    q, a = [], answers(x)
    chk(q, a, "latest_valid", x.secret["latest"], "newest archive whose checksum still verifies")
    got = tree_hash(x.work / "restore/site") if (x.work / "restore/site").is_dir() else {}
    q.append(R("restore/site/ contains exactly the files of that archive", got == x.secret["tree"]))
    q.append(R("the corrupted archives were left untouched (not deleted)", all((x.work / "backups" / n).exists() for n in x.secret["bad"])))
    return q

add("M17-T4", "Restore drill: which backup can be trusted?",
    lambda x: f"""\
INCIDENT   The website must be restored NOW. Five daily archives with SHA-256 files are in {x.work}/backups/ - but some are damaged.
TASK
  1. Verify every archive:  cd {x.work}/backups && sha256sum -c *.sha256      (FAILED = corrupted)
  2. Find the NEWEST archive that verifies OK.
  3. Extract it into  {x.work}/restore/  (so that {x.work}/restore/site/index.html exists).
  4. Write {x.work}/answers.txt :   latest_valid=<archive file name>
CONSTRAINTS   Do not delete or modify the backups.
EXPECTED RESULT   The right archive restored.""",
    s_m17t4, c_m17t4,
    hints=["sha256sum -c *.sha256 2>&1 | grep -v ': OK'", "mkdir -p restore && tar -xzf backups/ARCHIVE -C restore"],
    debrief="A backup you have never verified or restored is only a hope. Checksums tell you which copy to trust.")

compose("M17-X1", "BLOCK EXAM: backup and recovery", "Back up, mirror, rotate and restore under time pressure.", ["M17-T1", "M17-T2", "M17-T3", "M17-T4"])
