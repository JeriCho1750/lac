from course.core import *

# ------------------------------------------------------------------ 13. Docker
def ensure_docker():
    if not have("docker"):
        print(dim("  installing docker.io (needs internet) ..."))
        ensure_pkgs("docker.io")
    sh("systemctl enable --now docker")
    for img in ("nginx:alpine", "alpine:3.19"):
        if sh(f"docker image inspect {img}")[0] != 0:
            print(dim(f"  pulling {img} ..."))
            rc, out = sh(f"docker pull -q {img}", timeout=600)
            if rc != 0:
                raise RuntimeError("docker pull failed (internet?): " + out[-200:])

def compose_cmd():
    if sh("docker compose version")[0] == 0: return "docker compose"
    if have("docker-compose"): return "docker-compose"
    for pkg in ("docker-compose-v2", "docker-compose-plugin", "docker-compose"):
        sh(f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {pkg}", timeout=600)
        if sh("docker compose version")[0] == 0: return "docker compose"
        if have("docker-compose"): return "docker-compose"
    raise RuntimeError("could not install docker compose")

def dinspect(name):
    rc, out = sh(f"docker inspect {name}")
    try: return json.loads(out)[0]
    except Exception: return None

module(21, "Docker", """\
docker ps -a    docker images    docker pull IMG    docker run -d --name N -p HOST:CONTAINER -v /host/path:/in/container:ro --restart unless-stopped IMG
docker logs N (READ THIS FIRST for a crashing container)    docker exec -it N sh    docker inspect N    docker rm -f N
Restart policy: unless-stopped | always | on-failure.   Environment: -e KEY=value.   Containers are disposable: to change settings -> remove and run again.
Compose: docker compose -f FILE config (validate)    docker compose up -d    docker compose ps    docker compose logs    docker compose down
YAML: indentation with SPACES only, siblings must align.""", track="Automation & DevOps")

def s_m13t1(x):
    ensure_docker()
    tok = rnd_word(random.Random(), 6).upper()
    put(x.work / "www/index.html", f"<h1>DOCKER {tok}</h1>\n", 0o644)
    x.secret = {"tok": tok}

def c_m13t1(x):
    q, d = [], dinspect("lab-web")
    if not d:
        return [R("container named lab-web exists", False)]
    www = str(x.work / "www")
    q.append(R("lab-web is running", d["State"]["Running"]))
    q.append(R("image is nginx:alpine", d["Config"]["Image"] == "nginx:alpine"))
    pb = d["HostConfig"]["PortBindings"].get("80/tcp") or [{}]
    q.append(R("host port 8088 -> container port 80", pb[0].get("HostPort") == "8088"))
    q.append(R("volume: www -> /usr/share/nginx/html READ-ONLY", any(m["Destination"] == "/usr/share/nginx/html" and os.path.realpath(m["Source"]) == os.path.realpath(www) and not m["RW"] for m in d["Mounts"])))
    q.append(R("restart policy unless-stopped", d["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"))
    code, body = http("http://127.0.0.1:8088/")
    q.append(R("http://127.0.0.1:8088/ serves the page", code == 200 and x.secret["tok"] in body))
    return q

add("M21-T1", "Run a web server in a container",
    lambda x: f"""\
TASK   Using image nginx:alpine (already pulled), start a container:
    - name: lab-web          - detached (-d)
    - publish host port 8088 to container port 80
    - mount {x.work}/www to /usr/share/nginx/html as READ-ONLY (:ro)
    - restart policy: unless-stopped
  Verify:  docker ps ; curl http://127.0.0.1:8088/ ; docker logs lab-web
EXPECTED RESULT   curl shows the page from {x.work}/www/index.html.""",
    s_m13t1, c_m13t1,
    hints=["docker run -d --name lab-web -p 8088:80 -v HOST:/usr/share/nginx/html:ro --restart unless-stopped nginx:alpine"],
    debrief="Port publishing, bind mounts and restart policies - the three flags you use daily.")

CRASHY = ('case "$LAB_MODE" in production|staging) echo "mode=$LAB_MODE running"; while true; do sleep 5; done;; '
          '*) echo "FATAL: LAB_MODE is required (allowed: production|staging)" >&2; exit 3;; esac')

def s_m13t2(x):
    ensure_docker()
    subprocess.run(["docker", "run", "-d", "--name", "lab-crashy", "--restart=always", "alpine:3.19", "sh", "-c", CRASHY], capture_output=True)

def c_m13t2(x):
    q, d = [], dinspect("lab-crashy")
    if not d:
        return [R("container lab-crashy exists", False, "do not just delete it - recreate it")]
    time.sleep(3)
    d = dinspect("lab-crashy")
    q.append(R("lab-crashy is running (not restarting)", d["State"]["Running"] and not d["State"].get("Restarting")))
    q.append(R("environment LAB_MODE=production", "LAB_MODE=production" in d["Config"]["Env"]))
    q.append(R("restart policy unless-stopped", d["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"))
    q.append(R("logs show 'mode=production running'", "mode=production running" in sh("docker logs lab-crashy 2>&1")[1]))
    q.append(R("read the logs with docker logs", x.used(r"docker\s+logs") is not False))
    return q

add("M21-T2", "A container in a restart loop",
    lambda x: """\
INCIDENT #013
  Container 'lab-crashy' (image alpine:3.19) keeps restarting: `docker ps` shows 'Restarting'.
TASK
  1. docker ps -a  and  docker logs lab-crashy   - read the error.
  2. Containers are immutable: remove it and run it again with the SAME name, the SAME image (alpine:3.19),
     the missing environment variable set to the PRODUCTION value, and restart policy unless-stopped.
     (the command to run inside is the image default for this lab - you can read it with docker inspect:
      docker inspect lab-crashy --format '{{json .Config.Cmd}}'  - reuse exactly that command.)
  3. Verify it stays 'Up' and logs 'mode=production running'.
EXPECTED RESULT   Stable container, correct env.""",
    s_m13t2, c_m13t2,
    hints=["docker inspect lab-crashy --format '{{json .Config.Cmd}}' prints the command array (sh, -c, '...').", "docker rm -f lab-crashy ; docker run -d --name lab-crashy --restart unless-stopped -e LAB_MODE=production alpine:3.19 sh -c '<the script>'"],
    debrief="logs -> cause -> recreate with the right config. Containers are cattle, not pets.")

def s_m13t3(x):
    ensure_docker()
    cc = compose_cmd()
    tok = rnd_word(random.Random(), 6).upper()
    put(x.work / "stack/html/index.html", f"<h1>COMPOSE {tok}</h1>\n")
    put(x.work / "stack/compose.yml", """services:
  web:
    image: nginx:alpin
    container_name: lab-compose-web
    ports:
      - "8089:80"
    volumes:
      - ./htm:/usr/share/nginx/html:ro
 cache:
    image: alpine:3.19
    container_name: lab-compose-cache
    command: ["sleep", "infinity"]
""")
    x.secret = {"tok": tok, "cc": cc}
    x.own(x.work)

def c_m13t3(x):
    q = []
    for n in ("lab-compose-web", "lab-compose-cache"):
        d = dinspect(n)
        q.append(R(f"container {n} is running", bool(d) and d["State"]["Running"]))
    code, body = http("http://127.0.0.1:8089/")
    q.append(R("http://127.0.0.1:8089/ serves the page from ./html", code == 200 and x.secret["tok"] in body, f"status {code}"))
    q.append(R("compose.yml validates", sh(f"cd {x.work}/stack && {x.secret['cc']} -f compose.yml config -q")[0] == 0))
    return q

add("M21-T3", "Repair a Docker Compose stack",
    lambda x: f"""\
INCIDENT #014   The stack in {x.work}/stack/compose.yml (web + cache) will not start.
TASK
  cd {x.work}/stack ; {x.secret['cc']} config   ->  fix what it reports, repeat, then  {x.secret['cc']} up -d
  Several independent faults exist (YAML structure, image name, volume path). The page text lives in ./html/index.html.
  Verify:  {x.secret['cc']} ps ; curl http://127.0.0.1:8089/
EXPECTED RESULT   Both containers running, page served.""",
    s_m13t3, c_m13t3,
    hints=["'config' reports the YAML error line. All service names must have the same indentation.", "nginx:alpin does not exist - the real tag is in the previous task. Check ls for the real folder name."],
    debrief="Validate -> fix -> up -d -> verify. Compose files are just YAML: indentation is syntax.")

# ---------------------------------------------------------------- M21-T4  volumes
def s_m21t4(x):
    ensure_docker()
    x.secret = {"tok": "persisted-" + rnd_word(random.Random(), 6)}

def c_m21t4(x):
    q, tok = [], x.secret["tok"]
    q.append(R("named volume lab-data exists", sh("docker volume inspect lab-data")[0] == 0))
    q.append(R("container lab-writer no longer exists (it was removed)", sh("docker inspect lab-writer")[0] != 0))
    d = dinspect("lab-reader")
    q.append(R("container lab-reader exists and mounts volume lab-data", bool(d) and any(m.get("Name") == "lab-data" for m in d["Mounts"])))
    q.append(R(f"lab-reader's output shows '{tok}' (data survived the container)", bool(d) and tok in sh("docker logs lab-reader 2>&1")[1]))
    return q

add("M21-T4", "Data that survives containers (volumes)",
    lambda x: f"""\
SCENARIO   Containers are disposable, data is not. Prove that a named volume keeps data after its container is deleted.
TASK
  1. docker volume create lab-data
  2. Run a container named lab-writer (image alpine:3.19) with that volume mounted at /data that writes the text
        {x.secret['tok']}
     into /data/note.txt and exits.
  3. REMOVE lab-writer (docker rm).
  4. Run a NEW container named lab-reader (alpine:3.19) with the same volume that prints /data/note.txt (look at it with docker logs lab-reader).
EXPECTED RESULT   The reader shows the text written by a container that no longer exists.""",
    s_m21t4, c_m21t4,
    hints=["docker run --name lab-writer -v lab-data:/data alpine:3.19 sh -c 'echo TEXT > /data/note.txt'", "docker rm lab-writer ; docker run --name lab-reader -v lab-data:/data alpine:3.19 cat /data/note.txt ; docker logs lab-reader"],
    debrief="Volumes live outside the container's writable layer - that is where databases and uploads belong.")

# ---------------------------------------------------------------- M21-T5  Dockerfile
def s_m21t5(x):
    ensure_docker()
    tok = rnd_word(random.Random(), 6)
    put(x.work / "app/hello.sh", f'#!/bin/sh\necho "Hello from {tok}"\n', 0o644)
    x.secret = {"tok": tok}
    x.own(x.work)

def c_m21t5(x):
    q, tok = [], x.secret["tok"]
    df = x.work / "app/Dockerfile"
    txt = df.read_text() if df.is_file() else ""
    q.append(R("Dockerfile exists with FROM alpine:<fixed tag> (no :latest, no missing tag)", re.search(r"^FROM\s+alpine:(?!latest)\S+", txt, re.M) is not None))
    q.append(R("Dockerfile copies hello.sh and uses CMD or ENTRYPOINT", "hello.sh" in txt and re.search(r"^(CMD|ENTRYPOINT)", txt, re.M) is not None))
    q.append(R("image lab-hello:1.0 exists", sh("docker image inspect lab-hello:1.0")[0] == 0))
    rc, out = sh("docker run --rm lab-hello:1.0")
    q.append(R(f"`docker run --rm lab-hello:1.0` prints 'Hello from {tok}'", rc == 0 and f"Hello from {tok}" in out, out[-80:]))
    return q

add("M21-T5", "Build your own image (Dockerfile)",
    lambda x: f"""\
SCENARIO   {x.work}/app/hello.sh is a tiny script (note: it is NOT executable). Package it as an image.
TASK
  1. Write {x.work}/app/Dockerfile: base image alpine:3.19 (pin the tag!), copy hello.sh into the image, make it executable, run it by default (CMD or ENTRYPOINT).
  2. Build:  docker build -t lab-hello:1.0 {x.work}/app
  3. Test:   docker run --rm lab-hello:1.0     -> Hello from {x.secret['tok']}
EXPECTED RESULT   Image lab-hello:1.0 prints the greeting.""",
    s_m21t5, c_m21t5,
    hints=["FROM alpine:3.19 / COPY hello.sh /hello.sh / RUN chmod +x /hello.sh / CMD [\"/hello.sh\"]", "docker build -t NAME:TAG DIRECTORY"],
    debrief="Pinned base image + COPY + RUN + CMD: the skeleton of every Dockerfile. 'latest' makes builds unrepeatable.")

compose("M21-X1", "BLOCK EXAM: containers", "Run, repair, persist and build.", ["M21-T1", "M21-T2", "M21-T4", "M21-T5"])
