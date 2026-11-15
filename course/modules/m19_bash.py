from course.core import *


module(19, "Bash Scripting and Automation", """\
First line #!/bin/bash, chmod +x script.sh.   $1 $2 = arguments, $# = count, $0 = script name, $? = exit status of the last command
if [ -d "$1" ]; then ... fi     [ "$#" -ne 2 ] && { echo "usage" >&2; exit 2; }     [[ "$x" =~ ^[0-9]+$ ]]     for f in *.log; do ...; done     while read -r line; do ...; done < file
ALWAYS quote variables: "$var".   set -euo pipefail  (stop on errors).   Exit codes: 0 = OK, non-zero = problem (1 generic, 2 usage).
printf, echo, cut, awk, sort, uniq -c, wc -l, date +%Y%m%d, /dev/tcp/HOST/PORT (bash TCP test)
Cron line (in /etc/cron.d/NAME, with user column):  */5 * * * * root /path/script.sh args >> /path/log 2>&1
Debug: bash -x script.sh   (prints every command)    shellcheck (if installed)""", track="Automation & DevOps")
def s_m12t2(x):
    x.work.mkdir(parents=True, exist_ok=True); x.own(x.work)

def c_m12t2(x):
    s, q = x.work / "check-size.sh", []
    if not s.is_file():
        return [R("check-size.sh exists", False, str(s))]
    first = s.read_text().splitlines()[0] if s.read_text() else ""
    q.append(R("script starts with #!/bin/bash (or env bash) and is executable", first.startswith("#!") and "bash" in first and os.access(s, os.X_OK)))
    t = x.work / "_t"
    shutil.rmtree(t, ignore_errors=True)
    put(t / "small/f", b"x" * 10000); put(t / "big/f", b"x" * 300000)
    def run(args): return sh(f"{s} {args}", timeout=10)
    rc, out = run("")
    q.append(R("no arguments -> usage message and exit code 2", rc == 2, f"rc={rc}"))
    rc, out = run(f"{t}/nonexistent 100")
    q.append(R("directory missing -> exit code 2", rc == 2, f"rc={rc}"))
    rc, out = run(f"{t}/small abc")
    q.append(R("limit not a number -> exit code 2", rc == 2, f"rc={rc}"))
    rc, out = run(f"{t}/small 1000")
    q.append(R("small dir, limit 1000 KB -> prints OK..., exit 0", rc == 0 and out.startswith("OK"), f"rc={rc} out={out[:40]!r}"))
    rc, out = run(f"{t}/big 50")
    q.append(R("big dir, limit 50 KB -> prints ALERT..., exit 1", rc == 1 and out.startswith("ALERT"), f"rc={rc} out={out[:40]!r}"))
    shutil.rmtree(t, ignore_errors=True)
    cf = Path("/etc/cron.d/lab-checksize")
    ok = cf.is_file() and re.search(rf"^\*/5\s+\*\s+\*\s+\*\s+\*\s+root\s+{re.escape(str(s))}\s+\S+\s+\d+", cf.read_text(), re.M) is not None
    q.append(R("/etc/cron.d/lab-checksize runs the script every 5 minutes as root", ok))
    return q

add("M19-T1", "Write a monitoring script and schedule it",
    lambda x: f"""\
TASK   Write {x.work}/check-size.sh  (Bash)  - usage:  check-size.sh DIR MAX_KB
    - Compute the size of DIR in KB:  du -sk DIR | cut -f1
    - If size <= MAX_KB : print  "OK: DIR uses N KB"            and exit 0
    - If size >  MAX_KB : print  "ALERT: DIR uses N KB (limit M)" and exit 1
    - Wrong usage (not exactly 2 args, DIR is not a directory, MAX_KB is not a number): print a message to
      stderr and exit 2.
  Then: chmod +x, test all cases and check exit codes with  echo $?
  Finally schedule it with cron: create /etc/cron.d/lab-checksize running every 5 minutes as root:
      */5 * * * * root {x.work}/check-size.sh /var/log 500000 >> {x.work}/checks.log 2>&1
EXPECTED RESULT   The trainer runs your script against several cases and reads your cron file.""",
    s_m12t2, c_m12t2,
    hints=["[ \"$#\" -ne 2 ] && { echo \"usage: $0 DIR MAX_KB\" >&2; exit 2; }", "[[ \"$2\" =~ ^[0-9]+$ ]]  tests for a number;  [ -d \"$1\" ]  tests for a directory."],
    debrief="Argument validation + meaningful exit codes make a script usable by cron and monitoring.")

# ---------------------------------------------------------------- M19-T2  top IPs script
def s_m19t2(x):
    r = random.Random()
    ips = [f"10.1.{r.randint(0,9)}.{r.randint(1,250)}" for _ in range(12)]
    w = [r.randint(1, 30) for _ in ips]
    while sorted(w)[-1] == sorted(w)[-2] or sorted(w)[-2] == sorted(w)[-3] or sorted(w)[-3] == sorted(w)[-4]:
        w = [r.randint(1, 60) for _ in ips]
    lines = []
    for ip, n in zip(ips, w):
        lines += [f'{ip} - - [03/Mar/2025:10:00:00 +0000] "GET / HTTP/1.1" 200 100'] * n
    r.shuffle(lines)
    put(x.work / "access.log", "\n".join(lines) + "\n")
    x.secret = {"top": sorted(zip(w, ips), reverse=True)}
    x.own(x.work)

def c_m19t2(x):
    s, q = x.work / "topips.sh", []
    if not s.is_file():
        return [R("topips.sh exists", False, str(s))]
    q.append(R("executable with #! line", os.access(s, os.X_OK) and s.read_text().startswith("#!")))
    top = x.secret["top"]
    rc, out = sh(f"{s} {x.work}/access.log 2", timeout=10)
    want = "\n".join(f"{n} {ip}" for n, ip in top[:2])
    got = "\n".join(" ".join(l.split()) for l in out.splitlines())
    q.append(R("`topips.sh LOG 2` prints the 2 busiest IPs as 'COUNT IP', busiest first", rc == 0 and got == want, f"got: {got[:60]!r}"))
    rc, out = sh(f"{s} {x.work}/access.log", timeout=10)
    q.append(R("default N is 3 lines", rc == 0 and len(out.splitlines()) == 3, f"{len(out.splitlines())} lines"))
    rc, _ = sh(f"{s} {x.work}/missing.log", timeout=10)
    q.append(R("missing file -> exit code 2", rc == 2, f"rc={rc}"))
    rc, _ = sh(f"{s}", timeout=10)
    q.append(R("no argument -> exit code 2", rc == 2, f"rc={rc}"))
    return q

add("M19-T2", "Script: top talkers from an access log",
    lambda x: f"""\
TASK   Write {x.work}/topips.sh   usage:  topips.sh LOGFILE [N]
   - Print the N (default 3) client IPs with the most requests, busiest first, format:  COUNT IP   (one per line)
   - LOGFILE is an access log whose FIRST field is the client IP (see {x.work}/access.log).
   - Missing argument or unreadable file: message to stderr, exit code 2.
   Hint of the pipeline idea: cut/awk the IP | sort | uniq -c | sort -rn | head -n N""",
    s_m19t2, c_m19t2,
    hints=["N=${2:-3}", "awk '{print $1}' \"$1\" | sort | uniq -c | sort -rn | head -n \"$N\"", "[ -r \"$1\" ] || { echo ... >&2; exit 2; }"],
    debrief="Defaults ('${2:-3}'), validation and a clean pipeline: the shape of most admin scripts.")

# ---------------------------------------------------------------- M19-T3  port checker
def s_m19t3(x):
    ports = random.sample(range(20000, 40000), 4)
    spawn("pc-up1", "--http", ports[0]); spawn("pc-up2", "--http", ports[1])
    put(x.work / "hosts.txt", f"web1 127.0.0.1 {ports[0]}\ndb1 127.0.0.1 {ports[2]}\nweb2 127.0.0.1 {ports[1]}\ncache1 127.0.0.1 {ports[3]}\n")
    x.own(x.work)

def c_m19t3(x):
    s, q = x.work / "portcheck.sh", []
    if not s.is_file():
        return [R("portcheck.sh exists", False, str(s))]
    q.append(R("executable with #! line", os.access(s, os.X_OK) and s.read_text().startswith("#!")))
    rc, out = sh(f"{s} {x.work}/hosts.txt", timeout=30)
    want = ["web1 UP", "db1 DOWN", "web2 UP", "cache1 DOWN"]
    q.append(R("prints 'NAME UP' / 'NAME DOWN' for every line, in file order", out.split("\n") == want, f"got {out.splitlines()}"))
    q.append(R("exit code = number of DOWN services (here 2)", rc == 2, f"rc={rc}"))
    rc, _ = sh(f"{s} /nonexistent/hosts.txt", timeout=10)
    q.append(R("unreadable file -> exit code 99", rc == 99, f"rc={rc}"))
    return q

add("M19-T3", "Script: is the service port open? (loops and /dev/tcp)",
    lambda x: f"""\
TASK   Write {x.work}/portcheck.sh   usage:  portcheck.sh HOSTFILE
   HOSTFILE has lines  NAME HOST PORT  (see {x.work}/hosts.txt).  For every line test the TCP connection and print  'NAME UP'  or  'NAME DOWN'.
   - Use a  while read -r name host port; do ... done < "$1"  loop.
   - Pure Bash test (no nc needed):  timeout 2 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null
   - Exit code = number of services that are DOWN.  If the file cannot be read: print an error to stderr and exit 99.
EXPECTED RESULT   Two helper servers are up, two ports are closed.""",
    s_m19t3, c_m19t3,
    hints=["down=0 ; ... if timeout 2 bash -c \"exec 3<>/dev/tcp/$host/$port\" 2>/dev/null; then echo \"$name UP\"; else echo \"$name DOWN\"; down=$((down+1)); fi ; exit $down", "[ -r \"$1\" ] || exit 99 (after printing the error)"],
    debrief="A loop + a connection test + a meaningful exit code = a monitoring check you can plug into cron or Nagios.")

# ---------------------------------------------------------------- M19-T4  debug a broken script
BROKEN = '''#!/bin/bash
# wordstat.sh FILE  -> prints: lines=N words=N longest=WORD
file=$1
if [ -z $file ]; then echo "usage: $0 FILE" >&2; exit 2
if [ ! -f "$file" ]; then echo "no such file: $file" >&2; exit 2; fi
lines=$(wc -l $file | cut -d' ' -f1)
words=$(wc -w < "$file")
longest=""
for w in $(cat "$file"); do
  if [ ${#w} -gt ${#longest} ]; then longest=$w; fi
echo "lines=$lines words=$words longest=$longest"
'''

def s_m19t4(x):
    put(x.work / "wordstat.sh", BROKEN, 0o755)
    x.own(x.work)

def c_m19t4(x):
    s, q = x.work / "wordstat.sh", []
    t = x.work / "_t"; shutil.rmtree(t, ignore_errors=True)
    put(t / "my file.txt", "one two\nthree extraordinary four\nfive\n"); put(t / "one.txt", "a bb ccc\n")
    rc, out = sh(f'bash -n {s}'); q.append(R("`bash -n` finds no syntax errors", rc == 0, out[:100]))
    rc, out = sh(f'{s} "{t}/my file.txt"', timeout=10)
    q.append(R("works with a file name that contains a space", out == "lines=3 words=6 longest=extraordinary", f"got {out!r}"))
    rc, out = sh(f'{s} "{t}/one.txt"', timeout=10)
    q.append(R("correct numbers for a second file", out == "lines=1 words=3 longest=ccc", f"got {out!r}"))
    rc, _ = sh(f"{s}", timeout=10); q.append(R("no argument -> exit 2", rc == 2, f"rc={rc}"))
    rc, _ = sh(f'{s} "{t}/nonexistent"', timeout=10); q.append(R("missing file -> exit 2", rc == 2, f"rc={rc}"))
    shutil.rmtree(t, ignore_errors=True)
    return q

add("M19-T4", "Debug a broken script",
    lambda x: f"""\
INCIDENT   A colleague's script {x.work}/wordstat.sh does not work. Spec:  wordstat.sh FILE  prints exactly
               lines=<n> words=<n> longest=<first longest word>
           exit code 2 with a message on stderr if FILE is missing/not given. It must also work for file names with SPACES.
TASK       Find and fix ALL bugs.   Tools:  bash -n script (syntax check),  bash -x script FILE (trace every command),  quoting rules.
EXPECTED RESULT   The trainer runs it with several files.""",
    s_m19t4, c_m19t4,
    hints=["bash -n wordstat.sh tells you which 'fi'/'done' is missing.", "Quote every variable: \"$file\" - unquoted ones break on spaces. [ -z \"$file\" ] too."],
    debrief="Syntax check (bash -n), trace (bash -x) and always-quote: the three debugging reflexes.")

compose("M19-X1", "BLOCK EXAM: Bash scripting", "Four scripts are needed by tomorrow's shift.", ["M19-T1", "M19-T2", "M19-T3", "M19-T4"])
