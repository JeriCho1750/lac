from course.core import *


module(20, "Git and GitHub", """\
git clone URL DIR    git status    git switch -c fix/name    git diff    git add FILE    git commit -m "Fix: message"    git push -u origin BRANCH
git log --oneline -8    git log -S'text'    git show HASH    git revert HASH    git commit --amend    git merge BRANCH    git stash / git stash pop
git config user.name "Your Name"; git config user.email you@example.com   (set once, tells Git who you are)
Conflict markers: <<<<<<< ======= >>>>>>>  - edit the file, remove the markers, git add FILE, git commit.
Never push straight to main - work on a branch and open a Pull Request.   Commit message convention here:  "Fix: <what and why>"
git bisect start; git bisect bad; git bisect good HASH; git bisect run ./test.sh   (finds the commit that broke something)""", track="Automation & DevOps")
def s_m12t1(x):
    ensure_pkgs("git")
    rem, tmp = x.work / "remote.git", x.work / "_seed"
    sh(f"git init -q --bare -b main {rem}")
    sh(f"git clone -q {rem} {tmp} 2>/dev/null")
    put(tmp / "README.md", "# Lab project\n\nWellcome to the Lab project.\n")
    sh(f"cd {tmp} && git add . && git -c user.name=Seed -c user.email=seed@lab commit -qm 'Initial commit' && git push -q origin HEAD:main")
    shutil.rmtree(tmp)
    x.secret = {"main": sh(f"git -c safe.directory='*' -C {rem} rev-parse refs/heads/main")[1]}
    x.own(x.work)

def c_m12t1(x):
    rem, proj, q = x.work / "remote.git", x.work / "project", []
    g = lambda c, d=rem: sh(f"git -c safe.directory='*' -C {d} {c}")
    br = "refs/heads/fix/readme-typo"
    q.append(R("branch fix/readme-typo exists on the remote (pushed)", g(f"rev-parse --verify -q {br}")[0] == 0))
    mainsha = g("rev-parse refs/heads/main")[1]
    if mainsha != x.secret["main"]:
        x.error("you pushed to main! Changes must go to a branch and be merged via Pull Request")
    q.append(R("main branch on the remote is untouched", mainsha == x.secret["main"]))
    q.append(R("the branch changes ONLY README.md", g(f"diff --name-only main {br}")[1].split() == ["README.md"]))
    txt = g(f"show {br}:README.md")[1]
    q.append(R("README.md now says 'Welcome' (typo fixed)", "Welcome" in txt and "Wellcome" not in txt))
    q.append(R("commit message starts with 'Fix: '", g(f"log -1 --format=%s {br}")[1].startswith("Fix: ")))
    q.append(R("local clone exists in project/ and its working tree is clean", (proj / ".git").exists() and g("status --porcelain", proj)[1] == ""))
    q.append(R("your Git identity (user.name) is configured", g("config user.name", proj)[0] == 0))
    return q

add("M20-T1", "Fix a typo the team way (branch, commit, push)",
    lambda x: f"""\
ISSUE #7   README.md says "Wellcome to the Lab project." - fix the typo.
TEAM RULES  - never commit to main      - branch name: fix/readme-typo
            - commit message starts with "Fix: "   - set your git identity before the first commit
SHARED REPO   {x.work}/remote.git   (acts as GitHub)
TASK
  1. git clone {x.work}/remote.git {x.work}/project
  2. Set user.name and user.email inside the clone.
  3. git switch -c fix/readme-typo
  4. Fix the typo, check with  git diff , then git add + git commit -m "Fix: ..."
  5. git push -u origin fix/readme-typo
  6. git status must be clean afterwards; main on the remote must stay unchanged.
EXPECTED RESULT   One-file change on the branch, ready for a Pull Request.""",
    s_m12t1, c_m12t1,
    hints=["sed -i 's/Wellcome/Welcome/' README.md   or edit with nano.", "git push -u origin fix/readme-typo"],
    debrief="Branch -> small focused commit -> push -> PR. Main stays releasable.")

# ---------------------------------------------------------------- helpers
def git_run(cmd, d, user=None):
    return sh(f"git -c safe.directory='*' -C {shlex.quote(str(d))} {cmd}")

def mk_repo(d):
    d.mkdir(parents=True, exist_ok=True)
    sh(f"git init -q -b main {d}")
    git_run("config user.name Student", d); git_run("config user.email student@lab.test", d)

def commit(d, msg, files):
    for n, t in files.items():
        put(d / n, t)
    git_run("add -A", d); git_run(f"commit -q -m {shlex.quote(msg)}", d)

# ---------------------------------------------------------------- M20-T2  merge conflict
def s_m20t2(x):
    d = x.work / "repo"; mk_repo(d)
    commit(d, "Initial config", {"config.ini": "[net]\ntimeout=10\nname=lab\n"})
    git_run("switch -q -c feature", d)
    commit(d, "Raise timeout, add retries", {"config.ini": "[net]\ntimeout=60\nretries=3\nname=lab\n"})
    git_run("switch -q main", d)
    commit(d, "Set timeout for slow links", {"config.ini": "[net]\ntimeout=30\nname=lab\n"})
    x.own(x.work)

def c_m20t2(x):
    d, q = x.work / "repo", []
    txt = (d / "config.ini").read_text() if (d / "config.ini").exists() else ""
    q.append(R("no conflict markers left in config.ini", "<<<<<<<" not in txt and ">>>>>>>" not in txt and "=======" not in txt))
    q.append(R("config.ini has timeout=45", re.search(r"^timeout=45$", txt, re.M) is not None))
    q.append(R("config.ini keeps retries=3 from the feature branch", re.search(r"^retries=3$", txt, re.M) is not None))
    q.append(R("current branch is main", git_run("rev-parse --abbrev-ref HEAD", d)[1] == "main"))
    q.append(R("feature is merged into main (merge commit with two parents)", git_run("rev-list --merges --count HEAD", d)[1] != "0" and git_run("merge-base --is-ancestor feature HEAD", d)[0] == 0))
    q.append(R("working tree clean (merge committed)", git_run("status --porcelain", d)[1] == ""))
    return q

add("M20-T2", "Resolve a merge conflict",
    lambda x: f"""\
SCENARIO   Repo {x.work}/repo: branch 'feature' raised the timeout to 60 and added retries=3; main set timeout=30 meanwhile.
TASK       On branch main run:  git merge feature   -> CONFLICT in config.ini.
           Resolve it by hand: final file must keep retries=3 and use timeout=45 (a compromise agreed in the meeting).
           Remove ALL conflict markers (<<<<<<<  =======  >>>>>>>), git add config.ini, git commit (the merge commit).
EXPECTED RESULT   Clean tree, merge commit on main, config as agreed.""",
    s_m20t2, c_m20t2,
    hints=["git status shows 'both modified'. Open config.ini: everything between <<<<<<< and >>>>>>> is yours to rewrite.", "After editing: git add config.ini && git commit  (accept the default merge message)."],
    debrief="A conflict is just git asking a human to decide. Edit, remove markers, add, commit.")

# ---------------------------------------------------------------- M20-T3  undo mistakes
def s_m20t3(x):
    d = x.work / "repo"; mk_repo(d)
    commit(d, "Add app", {"app.sh": "#!/bin/bash\necho app running\n", "README.md": "# app\n"})
    commit(d, "Add secrets file by mistake", {"secrets.env": "DB_PASSWORD=hunter2\n"})
    commit(d, "Refactor startup", {"app.sh": "#!/bin/bash\nexit 1\n"})
    x.secret = {"good": "echo app running"}
    x.own(x.work)

def c_m20t3(x):
    d, q = x.work / "repo", []
    app = (d / "app.sh").read_text() if (d / "app.sh").exists() else ""
    q.append(R("app.sh works again (content restored)", "echo app running" in app))
    log = git_run("log --format=%s", d)[1]
    q.append(R("the bad commit was UNDONE with `git revert` (a 'Revert ...' commit exists, history kept)", "Revert" in log and "Refactor startup" in log))
    q.append(R("secrets.env is no longer tracked by git", "secrets.env" not in git_run("ls-files", d)[1]))
    q.append(R("secrets.env still exists on disk (not deleted)", (d / "secrets.env").exists()))
    gi = (d / ".gitignore").read_text() if (d / ".gitignore").exists() else ""
    q.append(R(".gitignore lists secrets.env", "secrets.env" in gi.split()))
    q.append(R("working tree is clean", git_run("status --porcelain", d)[1] == ""))
    return q

add("M20-T3", "Undo mistakes safely (revert, untrack, .gitignore)",
    lambda x: f"""\
SCENARIO   Repo {x.work}/repo (local only, nothing pushed). Two mistakes in the history:
             - commit 'Refactor startup' broke app.sh (it now just exits 1)
             - commit 'Add secrets file by mistake' put secrets.env under version control
TASK
  1. Undo the BAD REFACTOR without rewriting history:  git log --oneline ; git revert <hash>
  2. Stop tracking secrets.env but KEEP the file on disk:  git rm --cached secrets.env
  3. Prevent a repeat: add secrets.env to .gitignore and commit both changes.
  (In real life a leaked password must also be CHANGED - history still contains it.)
EXPECTED RESULT   app.sh works, secrets.env untracked + ignored, clean tree.""",
    s_m20t3, c_m20t3,
    hints=["git log --oneline   then   git revert HASH_OF_REFACTOR --no-edit", "git rm --cached secrets.env ; echo secrets.env >> .gitignore ; git add .gitignore ; git commit -m 'Stop tracking secrets.env'"],
    debrief="revert = safe undo that keeps history; rm --cached + .gitignore stops tracking without deleting the file.")

# ---------------------------------------------------------------- M20-T4  bisect
def g_m20t4(x, r):
    d = x.work / "repo"; mk_repo(d)
    n, badk = r.randint(10, 16), None
    badk = r.randint(4, n - 2)
    put(d / "test.sh", '#!/bin/bash\n[ "$(bash "$(dirname "$0")/calc.sh" 2 3)" = "5" ]\n', 0o755)
    msgs = ["Tidy comments", "Add usage text", "Rename variables", "Update README", "Format code", "Add logging", "Refactor parser", "Speed up loop", "Fix typo", "Bump version", "Cleanup", "Add tests", "Minor change", "Docs", "Style", "Lint"]
    bad_hash = bad_msg = None
    for i in range(1, n + 1):
        op = "-" if i >= badk else "+"
        body = f'#!/bin/bash\n# revision {i}\na=$1; b=$2\necho $((a {op} b))\n'
        msg = msgs[i % len(msgs)] + f" (#{i})"
        commit(d, msg, {"calc.sh": body, "test.sh": (d / "test.sh").read_text()})
        if i == badk:
            bad_hash = git_run("rev-parse --short=7 HEAD", d)[1]; bad_msg = msg
    return {"first_bad_commit": (bad_hash, "first 7 characters of the hash of the commit that BROKE calc.sh"),
            "first_bad_message": (bad_msg, "the commit message (subject) of that commit")}

answers_task("M20-T4", "Find the commit that broke it (git bisect)",
    lambda x: f"""\
INCIDENT   In repo {x.work}/repo  `./test.sh` used to pass (calc.sh adds two numbers) and now FAILS. Some commit in the history broke it.
TASK       Find the FIRST bad commit.   Manual:  git log --oneline ; git checkout HASH ; ./test.sh ; echo $?
           Automatic:  git bisect start ; git bisect bad HEAD ; git bisect good <first commit> ; git bisect run ./test.sh
           ... then  git bisect reset  to get back to the latest commit.""",
    g_m20t4,
    hints=["git log --oneline | tail -1 is the oldest commit (it passes).", "git bisect run ./test.sh prints 'xxxxxxx is the first bad commit'."],
    debrief="Bisect finds the guilty commit in log2(N) steps - automatic with a test script.")

compose("M20-X1", "BLOCK EXAM: Git workflow", "A messy repository, a conflict, a leaked file and a regression.", ["M20-T1", "M20-T2", "M20-T3", "M20-T4"])
