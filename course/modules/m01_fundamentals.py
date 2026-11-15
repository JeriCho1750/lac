from course.core import *

# ------------------------------------------------------------------ 1. Fundamentals
module(1, "Linux Fundamentals", """\
Filesystem map / карта файловой системы: / root, /home users, /etc configs, /var logs+data, /tmp temp, /usr programs, /opt add-ons.
pwd  ls -lah  cd  mkdir -p  touch  cp -a  mv  rm  (rm has NO recycle bin / корзины нет!)
cat  less  head -n  tail -n  tail -f  wc -l   echo "x" > file (overwrite)  echo "x" >> file (append)
find DIR -name "*.txt" -type f     du -ah DIR     ls -lS (sort by size)     ls -A (show hidden)""", track="Foundation")

def s_m01t1(x):
    r = random.Random()
    base = x.work / "srv"
    dirs = ["alpha/2022", "alpha/2023/q1", "beta/archive/old", "beta/tmp", "gamma/docs/final", "gamma/.cache", "delta/misc"]
    names = ["notes.txt", "draft.txt", "todo.txt", "backup.txt", "report.txt", "readme.txt", "incident-notes.txt", "report-final.txt"]
    for d in dirs:
        for n in r.sample(names, 4):
            put(base / d / n, f"{n} in {d}\n" * r.randint(1, 5))
    tdir = r.choice(dirs)
    code = rnd_word(r) + "-" + str(r.randint(100, 999))
    put(base / tdir / "incident-report.txt", f"Incident report\nroot cause code: {code}\n")
    n = r.randint(150, 480)
    put(x.work / "data/inventory.csv", "id,item,qty\n" + "".join(f"{i},item{i},{r.randint(1,99)}\n" for i in range(1, n)))
    sizes = r.sample(range(2, 90), 6)
    fnames = [f"{c}.log" for c in "abcdef"]
    for f, s in zip(fnames, sizes):
        put(x.work / "data/files" / f, b"x" * s * 1024)
    k = r.randint(3, 7)
    for i in range(k):
        put(x.work / "data" / f".hidden{i}", "h\n")
    x.secret = {"path": str(base / tdir / "incident-report.txt"), "code": code, "lines": n,
                "largest": fnames[sizes.index(max(sizes))], "hidden": k}
    x.own(x.work)

def c_m01t1(x):
    a, s, q = answers(x), x.secret, []
    chk(q, a, "incident_report", s["path"], "incident-report.txt location", "path")
    chk(q, a, "code", s["code"], "code word from the report")
    chk(q, a, "inventory_lines", s["lines"], "line count of inventory.csv", "int")
    chk(q, a, "largest_file", s["largest"], "largest file in data/files")
    chk(q, a, "hidden_in_data", s["hidden"], "hidden entries directly in data/", "int")
    return q

add("M01-T1", "Find things in the filesystem",
    lambda x: f"""\
SCENARIO
  A colleague left a messy directory tree and asks you five questions. Do NOT open files one by one -
  use find, wc, ls, grep and friends.

WORKSPACE
  {x.work}/srv     (a tree of folders and many small text files)
  {x.work}/data    (inventory.csv, a files/ folder, some hidden files)

TASK
  Create the file  {x.work}/answers.txt  with exactly these lines (key=value, no spaces around '='):
    incident_report=<FULL path of the single file named incident-report.txt somewhere under srv/>
    code=<the root-cause code written inside that file, after 'root cause code:'>
    inventory_lines=<number of lines in data/inventory.csv, header included>
    largest_file=<name only of the biggest file inside data/files/>
    hidden_in_data=<number of hidden entries (names starting with '.') directly inside data/>

CONSTRAINTS
  Do not modify or delete anything in srv/ or data/.
EXPECTED RESULT
  answers.txt contains five correct lines. Then run `check` in the trainer.""",
    s_m01t1, c_m01t1,
    hints=["find DIR -name incident-report.txt   then  cat the result.",
           "wc -l FILE counts lines. ls -lS DIR sorts by size (biggest first).",
           "ls -A DIR lists hidden entries too (but not . and ..). Count them with wc -l."],
    debrief="You used find/wc/ls to answer questions without reading everything. This is daily sysadmin work.")

def s_m01t2(x):
    d = x.work / "server-docs"
    put(d / "logs/app.log", "".join(f"2025-01-01 line {i}\n" for i in range(50)))
    for i in range(1, 6):
        put(d / f"logs/junk-{i}.tmp", "junk\n")
    x.secret = {"applog": sha(d / "logs/app.log")}
    x.own(x.work)

def c_m01t2(x):
    d, q = x.work / "server-docs", []
    for s in ("docs", "backups", "scripts", "logs"):
        q.append(R(f"directory {s}/ exists", (d / s).is_dir()))
    rd = d / "docs/README.txt"
    txt = rd.read_text() if rd.is_file() else None
    q.append(R("docs/README.txt has exactly: 'Server documentation' / 'Owner: admin'",
               txt is not None and txt.strip().splitlines() == ["Server documentation", "Owner: admin"]))
    q.append(R("docs/notes.txt is gone (RENAMED with mv, not just copied)", rd.exists() and not (d / "docs/notes.txt").exists()))
    bak = d / "backups/notes.bak"
    q.append(R("backups/notes.bak is an identical copy of README.txt", bak.is_file() and txt is not None and bak.read_text() == txt))
    q.append(R("scripts/backup.sh exists", (d / "scripts/backup.sh").is_file()))
    q.append(R("logs/*.tmp all removed", (d / "logs").is_dir() and not list((d / "logs").glob("*.tmp"))))
    q.append(R("logs/app.log still exists, unchanged", sha(d / "logs/app.log") == x.secret["applog"]))
    t = x.work / "tree.txt"
    tt = t.read_text() if t.is_file() else ""
    q.append(R("tree.txt lists the structure (output of find)", "server-docs/docs/README.txt" in tt and "server-docs/backups/notes.bak" in tt))
    return q

add("M01-T2", "Build a documentation structure",
    lambda x: f"""\
SCENARIO
  You must prepare a folder structure for server documentation and backups, and clean old junk.

WORKSPACE   {x.work}/server-docs   (only logs/ exists so far)

TASK  (all paths relative to server-docs/)
  1. Create directories: docs, backups, scripts  (logs already exists).
  2. Create docs/notes.txt using echo. Line 1: Server documentation  Line 2: Owner: admin
     (first line with '>' , second with '>>').
  3. Copy docs/notes.txt to backups/notes.bak.
  4. RENAME docs/notes.txt to docs/README.txt (use mv).
  5. Create an empty file scripts/backup.sh (touch).
  6. Delete ALL *.tmp files in logs/ with ONE command (use a wildcard), but keep logs/app.log.
  7. Save the structure listing:  find {x.work}/server-docs > {x.work}/tree.txt

EXPECTED RESULT
  Final tree matches the steps. Be careful with rm: never use rm -rf, never leave server-docs.""",
    s_m01t2, c_m01t2,
    hints=["mkdir docs backups scripts   (several at once).", "rm logs/*.tmp  - the * wildcard matches every .tmp file.",
           "echo 'Owner: admin' >> docs/notes.txt appends a line."],
    bad=[(r"rm\s+-\w*r", "recursive rm is not needed here - be careful")],
    debrief="Create/copy/move/delete with wildcards - the core of file work. Remember: rm is permanent.")

# ---------------------------------------------------------------- M01-T3  text processing
def g_m01t3(x, r):
    depts = ["ops", "dev", "hr", "sales"]
    rows, tot = [], {d: 0 for d in depts}
    cnt = {d: 0 for d in depts}
    for i in range(1, r.randint(70, 130)):
        d, sal = r.choice(depts), r.randint(30, 90) * 1000
        rows.append(f"{i},{rnd_word(r, 6)},{d},{sal}")
        tot[d] += sal; cnt[d] += 1
    put(x.work / "staff.csv", "id,name,dept,salary\n" + "\n".join(rows) + "\n")
    lines, errs, svcs = [], 0, set()
    first = None
    for i in range(1, r.randint(200, 320)):
        lvl = r.choice(["INFO", "INFO", "INFO", "WARN", "ERROR"] if i > 7 else ["INFO"])
        svc_n = f"svc{r.randint(1, 5)}"
        lines.append(f"2025-03-01 {i // 60 % 24:02d}:{i % 60:02d} {lvl} {svc_n} message number {i}")
        if lvl == "ERROR":
            errs += 1; svcs.add(svc_n)
            first = first or i
    put(x.work / "app.log", "\n".join(lines) + "\n")
    return {"ops_employees": (cnt["ops"], "number of employees in dept ops", "int"),
            "dev_salary_total": (tot["dev"], "sum of the salary column for dept dev", "int"),
            "error_lines": (errs, "number of lines in app.log containing ERROR", "int"),
            "services_with_errors": (len(svcs), "how many DIFFERENT services (svcN) logged an ERROR", "int"),
            "first_error_line": (first, "line NUMBER of the first ERROR in app.log", "int")}

answers_task("M01-T3", "Text processing: grep, cut, awk, sort",
    lambda x: f"""\
SCENARIO   Two data files need quick answers for a manager: {x.work}/staff.csv (id,name,dept,salary) and
           {x.work}/app.log (date time LEVEL service message).
USE        grep -c, grep -n, cut -d, awk -F, sort -u, uniq, wc -l   (no spreadsheet, no manual counting!)""",
    g_m01t3,
    hints=["grep -c ERROR app.log ; grep -n ERROR app.log | head -1", "awk -F, '$3==\"dev\" {s+=$4} END {print s}' staff.csv",
           "grep ERROR app.log | awk '{print $4}' | sort -u | wc -l"],
    debrief="Pipelines turn files into answers in seconds: grep to select, cut/awk to pick fields, sort/uniq to summarize.")

# ---------------------------------------------------------------- M01-T4  find / du / mtime
def g_m01t4(x, r):
    base = x.work / "data"
    now = time.time()
    big = empty = 0
    newest = None
    for i in range(r.randint(25, 45)):
        kind = r.choice(["big", "small", "empty"])
        size = {"big": r.randint(20, 60) * 1024, "small": r.randint(1, 8) * 1024, "empty": 0}[kind]
        f = put(base / r.choice(["a", "b", "c/d", "e/f/g"]) / f"file{i}.dat", b"x" * size)
        age = now - (i + 1) * 3600
        os.utime(f, (age, age))
        big += kind == "big"; empty += kind == "empty"
    files = [p for p in base.rglob("*.dat")]
    newest = max(files, key=lambda p: p.stat().st_mtime).name
    tgt = r.choice(files)
    (base / "current").symlink_to(tgt)
    kb = int(sh(f"du -sk {base}")[1].split()[0])
    x.secret_extra = None
    return {"files_over_10k": (big, "number of regular files larger than 10 KB (find -size +10k)", "int"),
            "empty_files": (empty, "number of empty (0 byte) files", "int"),
            "newest_file": (newest, "NAME of the most recently modified *.dat file"),
            "symlink_target": (tgt.name, "file NAME the symlink 'current' points to (readlink)"),
            "data_size_kb": (kb, "total size of the data directory in KB (du -sk), +/- 8", "int", 8)}

answers_task("M01-T4", "find, du and symlinks",
    lambda x: f"""\
SCENARIO   Housekeeping before an audit. The tree {x.work}/data contains many *.dat files and one symlink named 'current'.
USE        find -type f -size +10k, find -empty, ls -lt (newest first), readlink, du -sk""",
    g_m01t4,
    hints=["find data -type f -size +10k | wc -l   and   find data -type f -empty | wc -l", "ls -t data/*/*.dat | head -1 is not enough (nested dirs): use find data -name '*.dat' -printf '%T@ %f\\n' | sort -n | tail -1",
           "readlink data/current gives the target path - answer with the file name only."],
    debrief="find + size/time/type filters replace endless clicking through folders.")

compose("M01-X1", "BLOCK EXAM: Linux fundamentals", "A colleague left four messy tasks on the server. Do them without hints.",
        ["M01-T1", "M01-T2", "M01-T3", "M01-T4"])
