# lac - Linux Admin Labs

**Small, hands-on break/fix practice labs for people learning Linux system administration on Debian.**

The trainer breaks things on a throw-away VM - a wrong permission, a service that will not start, a full disk, a bad nginx config -
and **you fix them with real commands** in a normal shell. A built-in checker looks at the actual state of the system, counts your
mistakes, and keeps your statistics across lab resets.

> **What this is - and is not.** It is a set of *simple practice exercises* for the first steps of a sysadmin/helpdesk/junior DevOps path.
> It is **not** a DevOps exam, **not** a certification, and **not** a complete DevOps curriculum (no cloud, no Kubernetes, no CI/CD pipelines, no Windows).

---

## Safety first

This tool creates users, installs packages, starts services and edits system files **as root**.

* **Run it only inside a disposable virtual machine** (VirtualBox, KVM, a cloud VM you can delete). Never on your daily machine or a production server.
* Everything it creates is named `lab-*` / `lab_*` or lives in `/opt/linux-lab`, `/mnt/lab-data*` - and is removed on lab reset (`W` in the main menu or `--cleanup`).
* Real system files that a lab edits (`/etc/fstab`, `/etc/aliases`, `/etc/postfix/main.cf`, `/etc/apache2/ports.conf`, `~/.ssh/config`, `~/.ssh/known_hosts`) are backed up first
  and restored on reset; lines a lab adds to `/etc/hosts` are marked and removed. Firewall labs only *plan* `ufw` rules; the trainer never enables a firewall on your VM.
* The SSH lab runs a **second, separate sshd on 127.0.0.1:2222**. Your real SSH service is never touched.

## Requirements

* Targets Debian 12 and 13 (other Debian/Ubuntu releases may work), **systemd**, root via `sudo`.
* Python 3.8+ (standard library only - nothing to `pip install`).
* Internet access for labs that install software (nginx, Apache, MariaDB, PHP-FPM, BIND, Postfix, Docker, Ansible, WordPress download).
* Not meant for proot/Termux/containers (no systemd there). A phone is fine as an SSH client.

## Quick start

```bash
git clone https://github.com/JeriCho1750/lac.git
cd lac
sudo python3 -B run.py --validate    # offline self-check of the lab definitions
sudo python3 -B run.py               # start the trainer
```

Open a **second SSH window** to the VM for your work and keep the trainer in the first one
(or type `sh` inside the trainer to get a subshell).

## How a lab works

1. Pick a module and a lab. The trainer builds the scenario (files, broken services, processes, ...) and prints the task in plain English.
2. Do the work in a normal shell with real Linux commands.
3. For "find the facts" labs, type `a` - the trainer asks for your answers and writes the answer file for you.
4. Type `c` - the checker inspects the real system state and shows every requirement as `[ OK ]` or `[FAIL]`.
5. Mistakes are recorded (failed checks, wrong actions such as killing the wrong process, hints used). Resetting a lab does **not** reset statistics.

Some labs are intentionally strict about *how* you solve them: for example, "stop this process with SIGTERM, leave the other three alone".

### Trainer commands

| Screen | Keys (type, then press Enter) |
|---|---|
| Main menu | module number, `s` statistics, `e` export profile, `i` import profile, `r` resume, `w` wipe lab, `q` quit |
| Module screen | lab number, `b` back, `q` quit |
| Lab screen | `c` check, `a` answer mode, `h` hint, `t` show task, `m` command reference, `r` reset lab, `sh` subshell, `s` stats, `b` back, `q` quit |

The `task>` prompt is **not** a shell - run Linux commands in `sh` or in a second window. A Russian keyboard layout is detected and translated automatically.

## Curriculum

| # | Module | Practice topics | Labs | Exams |
|---|---|---|---:|---:|
| 1 | Linux Fundamentals | navigation, `find`, text processing with `grep`/`awk` | 4 | 1 |
| 2 | Files and Permissions | `chmod`/`chown`, ACLs, permission audits | 4 | 1 |
| 3 | Users and Groups | accounts, `sudo` rules, password policy, auth-log audit | 4 | 1 |
| 4 | Processes and Services | signals, systemd units, dependencies, the journal | 6 | 1 |
| 5 | Disk and Filesystems | full disks, deleted-but-open files, `fstab`, inodes | 4 | 1 |
| 6 | Networking and DNS | addresses, ports, `/etc/hosts`, subnet arithmetic | 4 | 1 |
| 7 | SSH and Server Security | sshd hardening, client config, `scp`, brute-force analysis | 4 | 1 |
| 8 | Logs and Troubleshooting | log analysis, failing services, `logrotate` | 4 | 1 |
| 9 | Web Server Administration | nginx sites, 403/502 faults, virtual hosts, access control | 4 | 1 |
| 10 | Apache HTTP Server | vhosts, `.htaccess`/rewrite, security headers, reverse proxy | 4 | 1 |
| 11 | SSL/TLS and Certificates | `openssl`, HTTPS with nginx, certificate audit | 4 | 1 |
| 12 | Databases | MariaDB users/grants, SQL, restore, indexes | 4 | 1 |
| 13 | WordPress Hosting | nginx + PHP-FPM + MariaDB faults, permissions, restore | 4 | 1 |
| 14 | DNS Server (BIND9) | zones, records, reverse zone, `dig` | 4 | 1 |
| 15 | Mail Server (Postfix) | local delivery, aliases, queue, mail DNS records | 4 | 1 |
| 16 | Firewall and Hardening | exposure audit, `ufw` plans (linted, never enabled), log analysis | 3 | 1 |
| 17 | Backup and Recovery | `tar`, `rsync`, rotation script, restore drill | 4 | 1 |
| 18 | Cron, Timers and Boot Behaviour | cron faults, systemd timers, boot state, failed units | 4 | 1 |
| 19 | Bash Scripting and Automation | arguments, exit codes, loops, debugging | 4 | 1 |
| 20 | Git and GitHub | branches, conflicts, undo, `git bisect` | 4 | 1 |
| 21 | Docker | run, repair, persist, build, Compose | 5 | 1 |
| 22 | System Monitoring | resource hogs, leaks, reading metrics | 4 | 1 |
| 23 | Ansible Automation | inventory, idempotent playbooks, templates, handlers | 4 | 1 |
| 24 | Support, Tickets and Documentation | triage, customer replies, runbooks, shift handover | 4 | 1 |
| 25 | Final Practical Exam | four mixed multi-incident exams | 0 | 4 |
| | **Total** | | **98** | **28** |

*Labs* are single scenarios. *Exams* are block exams: several incidents at once, no hints, plus a short written incident report.

## Statistics and profiles

Your progress lives **outside** the lab, in `/var/lib/linux-admin-course/profile.json`, so resets and lab cleanups never erase it.
Before you destroy the VM:

```bash
sudo python3 run.py --export            # writes ~/linux-course-profile-<date>.json
sudo python3 run.py --import FILE       # merge it into a fresh VM
sudo python3 run.py --stats             # print the statistics table
```

Every command you type in an SSH session is also logged to `/var/log/linux-lab-commands.log` (a small `/etc/profile.d` hook, active in *new* sessions).
The checker uses it to look at *how* you solved a task, e.g. whether you inspected a process before killing it.

## Project layout

```
run.py                     launcher (sudo python3 run.py)
course/core.py             engine: profile/statistics, checks, lab cleanup, menus, helper DSL
course/modules/mNN_*.py    one file per module; each lab = setup() + check() + task text
```

## Adding a lab

A lab is a task text, a `setup(x)` that creates the scenario and a `check(x)` that returns requirements.
Labs whose result is a set of facts need even less code:

```python
from course.core import *

def gen(x, r):                              # r = random.Random()
    n = r.randint(20, 50)
    put(x.work / "data.txt", "line\n" * n)
    return {"line_count": (n, "number of lines in data.txt", "int")}

answers_task("M01-T9", "Count the lines",
             lambda x: f"Count the lines of {x.work}/data.txt.",
             gen, hints=["wc -l FILE"])
```

Helpers: `answers_task` (facts), `mk_service` (broken systemd unit), `svc_reqs` (service checks), `compose` (block exam from existing labs), `save_orig` (back up a system file).
Run `python3 run.py --validate` after any change (it does not need root and is what CI runs).

## Status

Early and experimental. The foundation modules (1-8) are the most exercised. Modules that install and configure services
(web, mail, DNS, WordPress, Docker, Ansible) depend on your Debian release and package versions and have had less real-world testing -
please open an issue with the lab id and the trainer's output if one misbehaves.

## Troubleshooting

* *Nothing happens when I press a key* - type the letter and press **Enter**; use the **English** layout (a Russian layout is auto-translated).
* *`unknown command` at `task>`* - that prompt is not a Linux shell; type `sh` or use a second SSH window.
* *`rm: cannot remove ... __pycache__`* - run with `python3 -B` or delete with `sudo rm -rf`.
* *Lab did not change after updating the trainer* - choose **n** (new start) when asked about a lab that is already in progress.

## License

MIT - see [LICENSE](LICENSE).
