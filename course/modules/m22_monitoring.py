from course.core import *

# ------------------------------------------------------------------ 14. Monitoring
module(22, "System Monitoring", """\
top / htop (P = sort by CPU, M = sort by memory, q = quit)    ps aux --sort=-%mem | head    ps aux --sort=-%cpu | head
free -h (look at 'available')    uptime / cat /proc/loadavg (load averages 1/5/15 min)    vmstat 1 5    df -h    iostat (package sysstat)
/proc/PID/status -> VmRSS = real memory of a process (kB)    /proc/meminfo -> MemAvailable
Load average > number of CPU cores (nproc) for a long time = overloaded.
Prometheus collects metrics, Grafana draws dashboards; node_exporter exposes CPU/RAM/disk of a host.""", track="Automation & DevOps")

def s_m14t1(x):
    spawn("etl-worker", "--mem", 150); spawn("cache-agent", "--mem", 40)
    spawn("metrics-agent"); spawn("spinner", "--cpu")
    x.own(x.work)

def c_m14t1(x):
    q, a = [], answers(x)
    et = proc("etl-worker")
    rss = 0
    try:
        rss = int(re.search(r"VmRSS:\s+(\d+)", Path(f"/proc/{et.pid}/status").read_text()).group(1)) // 1024
    except Exception:
        pass
    chk(q, a, "top_memory_name", "etl-worker", "process that uses the most memory")
    chk(q, a, "top_memory_pid", et.pid, "PID of that process", "int")
    chk(q, a, "top_memory_rss_mb", rss, "its resident memory in MB (+/- 20)", "int", 20)
    chk(q, a, "top_cpu_name", "spinner", "process that uses the most CPU")
    sp = proc("spinner")
    if not sp.alive and "TERM" not in sp.sigs:
        x.error("spinner was killed without SIGTERM")
    q.append(R("spinner (CPU hog, disposable) stopped with SIGTERM", not sp.alive and "TERM" in sp.sigs))
    for n in ("etl-worker", "cache-agent", "metrics-agent"):
        if not proc(n).alive:
            x.error(f"{n} was killed - only spinner was to be stopped")
    q.append(R("etl-worker, cache-agent, metrics-agent still running", all(proc(n).alive for n in ("etl-worker", "cache-agent", "metrics-agent"))))
    return q

add("M22-T1", "Who eats my RAM and CPU?",
    lambda x: f"""\
INCIDENT #015   Monitoring alerts: high CPU and memory pressure. Helpers running: etl-worker, cache-agent, metrics-agent, spinner.
TASK
  1. Find the process with the highest MEMORY use (ps aux --sort=-%mem | head, or top then M) and the one with the highest CPU.
  2. Write {x.work}/answers.txt :
        top_memory_name=<name>          top_memory_pid=<PID>
        top_memory_rss_mb=<resident memory in MB, within +/-20>      top_cpu_name=<name>
  3. DECISIONS:  spinner = disposable CPU hog -> stop it with SIGTERM.
                 etl-worker = important nightly job (big but legitimate) -> LEAVE RUNNING, only report.
                 cache-agent, metrics-agent -> LEAVE RUNNING.
EXPECTED RESULT   Correct report, only spinner stopped.""",
    s_m14t1, c_m14t1,
    hints=["RSS column in ps is in kB: divide by 1024 for MB. grep VmRSS /proc/PID/status also works.", "kill PID (SIGTERM) for spinner. Verify with top that CPU dropped."],
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="Measure first, then decide per process: stop, limit, or leave. 'Big' is not the same as 'bad'.")

def s_m14t2(x):
    x.work.mkdir(parents=True, exist_ok=True); x.own(x.work)

def c_m14t2(x):
    s, q = x.work / "sysreport.sh", []
    if not s.is_file():
        return [R("sysreport.sh exists", False, str(s))]
    q.append(R("executable with a #! line", os.access(s, os.X_OK) and s.read_text().startswith("#!")))
    rc, out = sh(str(s), timeout=15)
    d = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    q.append(R("exit code 0 and exactly 3 lines of output", rc == 0 and len(out.splitlines()) == 3, f"rc={rc}, lines={len(out.splitlines())}"))
    q.append(R("load1=<number>", re.fullmatch(r"\d+(\.\d+)?", d.get("load1", "")) is not None))
    mem = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1)) // 1024
    try: got = int(d.get("mem_available_mb", ""))
    except ValueError: got = -1
    q.append(R("mem_available_mb within 25% (or 60 MB) of the real value", got >= 0 and abs(got - mem) <= max(60, mem * 0.25), f"you {got}, reality ~{mem}"))
    dp = int(sh("df --output=pcent / | tail -1 | tr -dc 0-9")[1])
    try: g2 = int(d.get("disk_root_used_pct", ""))
    except ValueError: g2 = -1
    q.append(R("disk_root_used_pct within 2 points of df", g2 >= 0 and abs(g2 - dp) <= 2, f"you {g2}, df {dp}"))
    return q

add("M22-T2", "Write a system report script",
    lambda x: f"""\
TASK   Write {x.work}/sysreport.sh - prints EXACTLY three lines and exits 0:
        load1=<1-minute load average, e.g. 0.15>                (from /proc/loadavg or uptime)
        mem_available_mb=<MemAvailable in whole MB>             (from /proc/meminfo or free -m)
        disk_root_used_pct=<use% of the / filesystem, number only>  (from df)
  Use only standard tools (awk, cut, df, free, tr). Make it executable and test it.
EXPECTED RESULT   The trainer compares your numbers with the real system values.""",
    s_m14t2, c_m14t2,
    hints=["awk '{print $1}' /proc/loadavg", "awk '/MemAvailable/ {printf \"%d\\n\", $2/1024}' /proc/meminfo", "df --output=pcent / | tail -1 | tr -dc '0-9'"],
    debrief="Three numbers a day tell you more than none: you built the seed of a monitoring agent.")

# ---------------------------------------------------------------- M22-T3  metrics csv
def g_m22t3(x, r):
    rows, peak, over, first_disk = [], (-1, None), 0, None
    mem_total = 0
    n = r.randint(180, 260)
    for i in range(n):
        ts = f"2025-03-01 {i // 60:02d}:{i % 60:02d}"
        cpu = r.randint(5, 85)
        if i == r.randint(20, n - 20) or i == 5: cpu = r.randint(86, 99)
        mem = r.randint(30, 80); disk = min(99, 70 + i // 12 + r.randint(0, 2))
        rows.append(f"{ts},{cpu},{mem},{disk}")
        over += cpu > 90
        if cpu > peak[0]: peak = (cpu, ts)
        mem_total += mem
        if disk > 85 and first_disk is None: first_disk = ts
    # make peak unique
    cpus = sorted(int(l.split(",")[1]) for l in rows)
    if cpus[-1] == cpus[-2]:
        return g_m22t3(x, r)
    put(x.work / "metrics.csv", "time,cpu_pct,mem_pct,disk_pct\n" + "\n".join(rows) + "\n")
    return {"peak_cpu_time": (peak[1], "timestamp ('YYYY-MM-DD HH:MM') of the highest cpu_pct"),
            "samples_cpu_over_90": (over, "number of samples with cpu_pct > 90", "int"),
            "avg_mem_pct": (round(mem_total / n), "average mem_pct, rounded to a whole number (+/- 1)", "int", 1),
            "first_disk_over_85": (first_disk, "timestamp of the first sample with disk_pct > 85")}

answers_task("M22-T3", "Read the metrics: find the incident window",
    lambda x: f"""\
SCENARIO   A monitoring agent exported one sample per minute to {x.work}/metrics.csv (time,cpu_pct,mem_pct,disk_pct).
           Management wants the facts for the post-mortem. Skip the header line when calculating!
USE        awk -F, 'NR>1 && $2>90' metrics.csv     sort -t, -k2 -n     awk -F, 'NR>1 {{s+=$3; n++}} END {{print s/n}}' """,
    g_m22t3,
    hints=["sort -t, -k2 -nr metrics.csv | head -2 (field 2 = cpu, numeric reverse)", "awk -F, 'NR>1 && $4>85 {print $1; exit}' metrics.csv"],
    debrief="Averages hide spikes: always look at peaks, counts over a threshold and WHEN things started.")

# ---------------------------------------------------------------- M22-T4  memory leak
def s_m22t4(x):
    spawn("report-gen", "--leak", 3); spawn("cache-agent2", "--mem", 30); spawn("web-sim")
    x.own(x.work)

def c_m22t4(x):
    q, a = [], answers(x)
    rg = proc("report-gen")
    chk(q, a, "leaking_process", "report-gen", "name of the process whose memory keeps growing")
    chk(q, a, "leaking_pid", rg.pid, "its PID", "int")
    if not rg.alive and "TERM" not in rg.sigs:
        x.error("report-gen was SIGKILLed - SIGTERM first")
    q.append(R("report-gen stopped with SIGTERM", not rg.alive and "TERM" in rg.sigs))
    for n in ("cache-agent2", "web-sim"):
        if not proc(n).alive:
            x.error(f"{n} was killed - only the leaking process had to be stopped")
    q.append(R("cache-agent2 and web-sim still running", proc("cache-agent2").alive and proc("web-sim").alive))
    return q

add("M22-T4", "Catch a memory leak",
    lambda x: f"""\
INCIDENT   Free memory shrinks every minute. Helpers: report-gen, cache-agent2, web-sim. Exactly one leaks.
           (A leaking process is not the one with the BIGGEST memory - it is the one whose memory keeps GROWING.)
TASK
  1. Sample RSS twice, 10-15 seconds apart:   ps -eo pid,rss,args | grep -E 'report-gen|cache-agent2|web-sim' | grep -v grep
  2. Write {x.work}/answers.txt :   leaking_process=<name>    leaking_pid=<PID>
  3. The leaker is disposable: stop it with SIGTERM before it eats everything. Leave the others running.
EXPECTED RESULT   Correct diagnosis, clean stop, others untouched.""",
    s_m22t4, c_m22t4,
    hints=["Run the same ps command twice and compare the RSS columns.", "watch -n 5 'ps -eo pid,rss,args | grep labproc | grep -v grep'"],
    bad=[(r"\b(killall|pkill)\b", "killing by name is risky - use the verified PID")],
    debrief="A leak shows as a trend, not as a number: sample, wait, sample again.")

compose("M22-X1", "BLOCK EXAM: monitoring", "Resource problems everywhere.", ["M22-T1", "M22-T2", "M22-T3", "M22-T4"])
