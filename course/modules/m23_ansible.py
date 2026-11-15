from course.core import *

module(23, "Ansible Automation", """\
Inventory (INI):   [lab]  node1 ansible_host=127.0.0.1 ansible_connection=local   ansible_python_interpreter=/usr/bin/python3
Ad-hoc:  ansible -i inventory.ini lab -m ping      ansible -i inv lab -m command -a "id -un"      ansible-inventory -i inv --list
Playbook (YAML, 2-space indentation, lists start with '- '):  - hosts: lab / tasks: / - name: ... / ansible.builtin.user: {name: x, shell: /bin/bash}
Run:  ansible-playbook -i inv play.yml      --syntax-check (YAML+structure)    --check --diff (dry run)    -v (more detail)
IDEMPOTENCE: running a correct playbook a second time reports changed=0.   Never use shell/command when a module exists (user, file, copy, template, lineinfile, apt, service).
Template: ansible.builtin.template: {src: x.j2, dest: /path}   Jinja2:  {{ var }}   {% for v in vhosts %} ... {% endfor %}
Handlers run only when a task that 'notify:'ies them CHANGED something.     Recap line:  ok=3 changed=1 failed=0
In this lab everything targets THIS machine (connection=local).""", track="Automation & DevOps")

ANS_ENV = "ANSIBLE_NOCOWS=1 ANSIBLE_LOCALHOST_WARNING=False ANSIBLE_INVENTORY_UNPARSED_WARNING=False ANSIBLE_DEPRECATION_WARNINGS=False ANSIBLE_HOME=/tmp/ansible-lab HOME=/root"

def ensure_ansible():
    if not have("ansible-playbook"):
        try:
            apt_install("ansible-core")
        except RuntimeError:
            apt_install("ansible")
    if not have("ansible-playbook"):
        raise RuntimeError("ansible-playbook is not available after installation")

def ans(cmd, cwd, timeout=180):
    return sh(f"cd {shlex.quote(str(cwd))} && {ANS_ENV} {cmd}", timeout=timeout)

def recap_ok(out, need_zero_changed=True):
    rows = re.findall(r"ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)", out)
    if not rows: return False
    return all(int(f) == 0 and int(u) == 0 and (int(c) == 0 or not need_zero_changed) for _, c, u, f in rows)

INV_GOOD = "[lab]\nnode1 ansible_host=127.0.0.1 ansible_connection=local ansible_python_interpreter=/usr/bin/python3\nnode2 ansible_host=127.0.0.1 ansible_connection=local ansible_python_interpreter=/usr/bin/python3\n"

# ---------------------------------------------------------------- A1  inventory
def s_m23t1(x):
    ensure_ansible(); x.own(x.work)

def c_m23t1(x):
    q, inv = [], x.work / "inventory.ini"
    if not inv.is_file():
        return [R("inventory.ini exists", False, str(inv))]
    rc, out = ans(f"ansible-inventory -i inventory.ini --list", x.work)
    try:
        data = json.loads(out[out.index("{"):])
    except Exception:
        return [R("ansible-inventory can parse inventory.ini", False, out[:100])]
    hosts = data.get("lab", {}).get("hosts", [])
    hv = data.get("_meta", {}).get("hostvars", {})
    q.append(R("group [lab] contains 2 hosts", len(hosts) == 2, f"found {hosts}"))
    q.append(R("both hosts use ansible_connection=local", len(hosts) == 2 and all(hv.get(h, {}).get("ansible_connection") == "local" for h in hosts)))
    rc, out = ans("ansible -i inventory.ini lab -m ping", x.work)
    q.append(R("`ansible lab -m ping` succeeds on both hosts (2 x pong)", rc == 0 and out.count("pong") == 2, out[-100:]))
    q.append(R("you ran ansible yourself (command history)", x.used(r"\bansible\b") is not False))
    return q

add("M23-T1", "Ansible: inventory and ad-hoc commands",
    lambda x: f"""\
SCENARIO   First step of any automation: tell Ansible WHICH machines to manage. We use two logical hosts that both point to this VM.
TASK       1. Create {x.work}/inventory.ini with a group [lab] and two hosts node1 and node2:
                 ansible_host=127.0.0.1   ansible_connection=local   ansible_python_interpreter=/usr/bin/python3
           2. Check it:   ansible-inventory -i inventory.ini --list
           3. Ping all hosts:   ansible -i inventory.ini lab -m ping           (expect 'pong' twice)
           4. Run an ad-hoc command:   ansible -i inventory.ini lab -m command -a "id -un"
EXPECTED RESULT   Valid inventory, successful ping.""",
    s_m23t1, c_m23t1,
    hints=["Install check:  ansible --version   (installed for you)", "One line per host:  node1 ansible_host=127.0.0.1 ansible_connection=local"],
    debrief="Inventory = who, connection variables = how. 'ping' is Ansible's connectivity test (not ICMP).")

# ---------------------------------------------------------------- A2  idempotent playbook
def s_m23t2(x):
    ensure_ansible()
    put(x.work / "inventory.ini", INV_GOOD)
    x.own(x.work)

def c_m23t2(x):
    q = []
    pb = x.work / "site.yml"
    site = x.work / "site"
    q.append(R("site.yml exists", pb.is_file()))
    u = getuser("lab_ans")
    q.append(R("user lab_ans exists with shell /bin/bash", bool(u) and u.pw_shell == "/bin/bash"))
    q.append(R("directory site/ exists with mode 755", site.is_dir() and (site.stat().st_mode & 0o777) == 0o755))
    idx = site / "index.txt"
    q.append(R("site/index.txt contains exactly 'Managed by Ansible env=lab'", idx.is_file() and idx.read_text().strip() == "Managed by Ansible env=lab"))
    ac = site / "app.conf"
    q.append(R("site/app.conf contains the line max_conn=100 (exactly once)", ac.is_file() and ac.read_text().splitlines().count("max_conn=100") == 1))
    q.append(R("you ran ansible-playbook yourself (command history)", x.used(r"ansible-playbook") is not False))
    if pb.is_file():
        rc, out = ans("ansible-playbook -i inventory.ini site.yml", x.work)
        q.append(R("IDEMPOTENT: a run now reports changed=0 and failed=0 for every host", rc == 0 and recap_ok(out), out[-200:].replace("\n", " ")))
    return q

add("M23-T2", "Ansible: your first idempotent playbook",
    lambda x: f"""\
SCENARIO   Prepare an application directory the same way on every server. Inventory (group lab) is ready: {x.work}/inventory.ini.
TASK       Write {x.work}/site.yml (hosts: lab) that guarantees, using MODULES (no shell/command):
             - user  lab_ans  exists, shell /bin/bash
             - directory  {x.work}/site  exists, mode 0755
             - file  {x.work}/site/index.txt  with the content   Managed by Ansible env=lab   (use a variable env_name: lab in vars)
             - the line  max_conn=100  is present exactly once in  {x.work}/site/app.conf  (file may not exist yet: create it)
           Run it:  ansible-playbook -i inventory.ini site.yml   -> the 2nd run must show changed=0.
EXPECTED RESULT   Correct end state and idempotence (the trainer runs your playbook once more).""",
    s_m23t2, c_m23t2,
    hints=["ansible.builtin.user / ansible.builtin.file / ansible.builtin.copy (content: ...) / ansible.builtin.lineinfile (create: true)", "ansible-playbook --syntax-check site.yml ; --check --diff shows what WOULD change."],
    debrief="Modules describe the DESIRED STATE, so re-running changes nothing: that is idempotence.")

# ---------------------------------------------------------------- A3  fix a broken playbook
BROKEN_PB = '''- hosts: localhost
  connection: local
  gather_facts: false
  vars:
    out_dir: "{{ playbook_dir }}/out"
  tasks:
  - name: create output directory
    ansible.builtin.file:
      path: "{{ out_dir }}"
      state: directory
      mode: "0755"
   - name: write the result file
     ansible.builtin.copy:
       desc: "{{ out_dir }}/result.txt"
       content: "deployed {{ app_name }}\\n"
'''

def s_m23t3(x):
    ensure_ansible()
    put(x.work / "broken.yml", BROKEN_PB)
    x.own(x.work)

def c_m23t3(x):
    q, pb = [], x.work / "broken.yml"
    rc, out = ans("ansible-playbook --syntax-check broken.yml", x.work)
    q.append(R("--syntax-check passes", rc == 0, out[-150:].replace("\n", " ")))
    rc, out = ans("ansible-playbook broken.yml", x.work)
    q.append(R("the playbook runs without failures", rc == 0 and "failed=0" in out, out[-150:].replace("\n", " ")))
    res = x.work / "out/result.txt"
    q.append(R("out/result.txt contains 'deployed lab-app'", res.is_file() and res.read_text().strip() == "deployed lab-app"))
    q.append(R("you used ansible-playbook yourself", x.used(r"ansible-playbook") is not False))
    return q

add("M23-T3", "Ansible: repair a broken playbook",
    lambda x: f"""\
INCIDENT   A colleague's playbook {x.work}/broken.yml does not run. It should create {x.work}/out/ and write  out/result.txt  containing  'deployed lab-app'.
TASK       Run:  ansible-playbook --syntax-check broken.yml    then   ansible-playbook broken.yml   - fix what each error message says, repeat.
           (Three independent faults: YAML structure, a wrong module option, a missing variable - define app_name: lab-app.)
EXPECTED RESULT   The playbook succeeds and the file has the right content.""",
    s_m23t3, c_m23t3,
    hints=["YAML: all items of a list must have the SAME indentation; the second '- name' is indented one space too far.", "The copy module's option for the target path is 'dest', not 'desc'.", "Undefined variable errors: add a vars: entry."],
    debrief="Ansible errors point at the exact line/option. Fix one error at a time and re-run --syntax-check.")

# ---------------------------------------------------------------- A4  template + handler
def s_m23t4(x):
    ensure_ansible(); x.own(x.work)

def c_m23t4(x):
    q, pb = [], x.work / "render.yml"
    if not pb.is_file():
        return [R("render.yml exists", False, str(pb))]
    flag, out_f = RUN / "ansible-handler.flag", x.work / "rendered/lab.conf"
    flag.unlink(missing_ok=True); out_f.unlink(missing_ok=True)
    rc, out = ans("ansible-playbook render.yml", x.work)
    q.append(R("playbook runs without failures", rc == 0 and "failed=0" in out, out[-150:].replace("\n", " ")))
    txt = out_f.read_text() if out_f.is_file() else ""
    q.append(R("rendered/lab.conf has a line 'server a port 8081' and 'server b port 8082'", "server a port 8081" in txt.splitlines() and "server b port 8082" in txt.splitlines(), txt[:80]))
    q.append(R("the handler ran because the file CHANGED (flag file created)", flag.exists()))
    flag.unlink(missing_ok=True)
    rc, out = ans("ansible-playbook render.yml", x.work)
    q.append(R("second run: changed=0 and the handler does NOT run", rc == 0 and recap_ok(out) and not flag.exists(), out[-150:].replace("\n", " ")))
    pbt = pb.read_text()
    q.append(R("uses the template module, a Jinja2 loop and a handler", "template" in pbt and "handlers" in pbt and "notify" in pbt and any(x.work.glob("**/*.j2"))))
    return q

add("M23-T4", "Ansible: templates, loops and handlers",
    lambda x: f"""\
SCENARIO   Config files are generated from data. Write {x.work}/render.yml (hosts: localhost, connection: local) and a Jinja2 template (*.j2 somewhere under {x.work}) that
           renders {x.work}/rendered/lab.conf  from the variable
                 vhosts:  [ {{name: a, port: 8081}}, {{name: b, port: 8082}} ]
           with ONE line per vhost in the form:      server a port 8081
           (use  {{% for v in vhosts %}} ... {{% endfor %}}). The rendered/ directory must be created by the playbook too.
           HANDLER: when - and only when - the rendered file changes, a handler must create the file {RUN}/ansible-handler.flag (module file, state: touch).
EXPECTED RESULT   The trainer deletes the output, runs your playbook twice: the first run creates file + flag, the second changes nothing.""",
    s_m23t4, c_m23t4,
    hints=["tasks: file (directory) -> template (notify: touch flag) ;  handlers: - name: touch flag  ansible.builtin.file: path=... state=touch", "In the template:  {% for v in vhosts %}server {{ v.name }} port {{ v.port }}\n{% endfor %}"],
    debrief="Templates + variables + handlers = configuration management: change the data, Ansible reloads only what changed.")

compose("M23-X1", "BLOCK EXAM: Ansible", "Inventory, an idempotent playbook, a repair job and templating.", ["M23-T1", "M23-T2", "M23-T3", "M23-T4"])
