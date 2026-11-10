# Deployment guide: Docker, API, and how this works in an enterprise

Companion to PROJECT_PLAN.md Phase 13. The plan says *what* to build; this
guide explains *why*, shows what you should see at each step, and maps every
local step to its enterprise equivalent. Type the files yourself rather than
pasting them. The point is to understand each line.

Contents: 1 Mental model · 2 Warm-up · 3 Build the pieces · 4 Run and inspect ·
5 Troubleshooting · 6 The enterprise picture · 7 Exercise ladder · 8 Self-check · 9 Glossary

---

## 1. Mental model

| Term | What it is | Analogy to what you know |
|---|---|---|
| **Image** | A read-only package: OS files, Python, your dependencies, your code. Built from a Dockerfile. | A zip of a fully set-up machine |
| **Container** | A running instance of an image: an isolated process with its own filesystem. Disposable. | A process started from a program file |
| **Layer** | Each Dockerfile instruction adds one cached layer. Unchanged layers are reused. | Incremental build cache |
| **Registry** | A server that stores images (Docker Hub, GitHub Container Registry, a bank's internal Artifactory/ECR/ACR). | PyPI, but for images |
| **Volume / bind mount** | A folder outside the container that survives it being deleted. | An external drive |
| **Port mapping** | `-p 8000:8000` forwards host port 8000 to container port 8000. | |
| **Environment variable** | Configuration passed in at run time. | Your `config.py` already reads these |
| **Compose** | A YAML file describing several containers, volumes and networks together. | A launch script |

Three rules that explain most of what follows:

1. **Containers are disposable.** Anything written inside the container's own
   filesystem is lost when it is removed. Anything you need to keep (case
   store, checkpoints, vector store) must live in a volume.
2. **Build once, configure at run time.** The same image runs in dev, test and
   prod. Only environment variables, secrets and mounted data differ. Never
   bake a key or an environment name into the image.
3. **`localhost` means "this container".** To reach something on your machine
   or in another container you use a different address (section 4).

---

## 2. Warm-up (20 minutes, before touching the project)

Check the install:

```bash
docker --version
docker compose version
docker run --rm hello-world     # pulls an image, runs it, prints a message, deletes it
```

Then learn the vocabulary on a throwaway container:

```bash
docker run -d --name play -p 8080:8000 python:3.12-slim python -m http.server 8000
docker ps                        # running containers
curl localhost:8080              # you are talking to a process inside the container
docker logs play                 # the container's stdout/stderr
docker exec -it play bash        # shell inside it; run `ls`, `whoami`, then `exit`
docker stop play && docker rm play
docker images                    # local images and their sizes
```

You should be able to explain: why `curl localhost:8080` works, what `-d`,
`--rm` and `--name` do, and why `docker logs` is the first thing you reach for
when something fails.

---

## 3. Build the pieces

### 3.1 Service layer (Plan Step 1)

Why: the CLI and the API must behave the same. If each has its own copy of the
"run graph, check pause, save case" logic they will drift. In an enterprise
codebase the transport (CLI, HTTP, a queue consumer) is a thin adapter over a
service function; this is that pattern.

Design points to decide and write down:
- The service takes the compiled graph as an argument (dependency injection),
  so tests can pass a graph built with a fake LLM.
- Errors are exceptions with meaning (`CaseNotFound`, `CaseNotPending`), not
  `sys.exit`. The CLI turns them into exit messages; the API turns them into
  404 and 409.

### 3.2 The API (Plan Step 2)

Why each choice:
- **Build the graph once at startup** (`lifespan`). Compiling it and opening
  the SQLite connection per request is slow and can lock the database.
- **Plain `def` endpoints.** The graph call blocks for seconds or minutes.
  FastAPI runs `def` handlers in a thread pool, so one slow investigation does
  not freeze the others. An `async def` that calls blocking code would freeze
  the whole server.
- **Status codes carry meaning.** 404 unknown case, 409 case is not in the
  state this action needs, 422 invalid input (FastAPI does this for you from
  the Pydantic model), 502 a backend you depend on failed. Callers' code
  branches on these, so they are part of your contract.
- **Pause is a normal outcome, not an error.** `POST /investigations` returns
  200 with `status: "awaiting_review"`. Clients poll or are told later.
- **Pydantic response models** give you the OpenAPI spec at `/docs` for free.
  Enterprise consumers integrate from that spec.

Run it without Docker first: `uv run uvicorn aml_agents.api:app --port 8000`.
Fix problems here, where debugging is easiest, before adding a container.

### 3.3 Dockerfile (Plan Step 3), annotated reference

Write your own, then compare:

```dockerfile
FROM python:3.12-slim                      # small official base; pin the minor version

# uv from its official image: no pip install needed
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 1. Dependencies first. These two files change rarely, so this layer is
#    cached across code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Code last. This layer changes on every commit and is cheap to rebuild.
COPY aml_agents ./aml_agents
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# 3. Do not run as root. If the app is compromised, the attacker is not root.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/data && chown -R appuser /app/data
USER appuser

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "aml_agents.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

Notes:
- `--host 0.0.0.0` is required. With the default `127.0.0.1` the server only
  accepts connections from inside the container, so the port mapping appears
  to do nothing. This is the most common first-time mistake.
- `PYTHONUNBUFFERED=1` makes log lines appear immediately in `docker logs`.
- Order of `COPY` lines is the caching strategy. Swap them and every code edit
  reinstalls PyTorch.
- `latest` for uv is fine for learning; in an enterprise you pin it (section 6).

`.dockerignore` works like `.gitignore` for the build context. Without it,
`docker build` uploads your `.venv`, `.git` and `data/` to the Docker daemon
and may copy `.env` into the image.

Build and measure:

```bash
docker build -t aml-investigator:dev .
docker images aml-investigator        # note the size; expect GBs because of PyTorch
docker history aml-investigator:dev   # size per layer: find the biggest one
```

### 3.4 Compose (Plan Step 4), annotated skeleton

```yaml
services:
  api:
    build: .
    image: aml-investigator:dev
    ports: ["8000:8000"]
    env_file: .env                       # secrets for local use only (section 6)
    environment:
      CASE_STORE_DB_PATH: /app/data/processed/case_store.sqlite
      LANGGRAPH_CHECKPOINT_DB_PATH: /app/data/processed/checkpoints.sqlite
      VECTOR_STORE_DIR: /app/data/processed/chroma
      EVAL_DB_PATH: /app/data/processed/eval_results.sqlite
    volumes:
      - ./data:/app/data                 # state and data live on your disk, not in the container
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health')"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 20s
    restart: unless-stopped
```

Things to understand:
- The `config.py` defaults point at `REPO_ROOT/data/...`. Inside the image
  `REPO_ROOT` is `/app`, so the defaults would also work, but setting the
  variables explicitly makes the contract visible and mirrors how an
  enterprise injects them.
- **File permissions on the bind mount.** The container user (uid 10001) must
  be able to write `./data`. If you see `unable to open database file` or
  `readonly database`, run `chmod -R a+rwX data` for local practice, or set
  `user: "${UID}:${GID}"` in compose. In an enterprise this is solved with
  volumes provisioned with the right ownership.
- **Healthcheck vs restart.** The healthcheck marks the container
  `healthy`/`unhealthy`. `restart` only restarts a container that *exited*.
  Orchestrators (Kubernetes) use health probes to decide to restart or to stop
  sending traffic; compose only reports.
- **Reaching your LLM.** Anthropic: nothing special, outbound HTTPS works.
  Local Ollama on your machine: `LOCAL_LLM_BASE_URL=http://host.docker.internal:11434`;
  on Linux also add `extra_hosts: ["host.docker.internal:host-gateway"]`, and
  make sure Ollama listens on all interfaces (`OLLAMA_HOST=0.0.0.0`). Ollama as
  another compose service: the address is the service name,
  `http://ollama:11434`. Compose gives each service a DNS name on a private network.

---

## 4. Run and inspect

```bash
docker compose build
docker compose run --rm api python scripts/download_public_data.py --all
docker compose run --rm api python scripts/ingest_guidance.py
docker compose up -d
docker compose ps                     # wait until STATUS shows (healthy)
curl localhost:8000/health
```

Then the investigate, pause, decide, read sequence from Plan Step 5. Open
`http://localhost:8000/docs` and try the same calls from the browser.

Learn to look inside; this is the debugging skill that transfers:

```bash
docker compose logs -f api            # live logs
docker compose exec api sh            # shell in the running container
  whoami; ls -la /app/data/processed  # expect appuser and your sqlite files
docker compose exec api env | sort    # what config did the app really get?
docker inspect <container> --format '{{json .State.Health}}'
docker stats                          # CPU and memory while an investigation runs
docker compose restart api            # the pause must survive this
docker compose down                   # removes containers; ./data is untouched
```

Prove the three rules from section 1 yourself:
1. `docker compose down` then `up -d`: your cases are still there (volume).
2. Run `docker compose exec api touch /tmp/x`, then `down` and `up`: the file is
   gone (container filesystem is disposable).
3. Deliberately set a wrong `LOCAL_LLM_BASE_URL=http://localhost:11434` and see
   it fail from inside the container, then fix it.

---

## 5. Troubleshooting

| Symptom | Likely cause | Check or fix |
|---|---|---|
| `curl` gets connection refused / empty reply | Server bound to `127.0.0.1` | Use `--host 0.0.0.0` |
| Container exits immediately | App crashed on startup | `docker compose logs api`; `docker compose run --rm api sh` to poke around |
| `unable to open database file` | Directory missing or not writable by uid 10001 | Create `data/processed`; fix permissions |
| Case disappears after restart | Path points inside the container, not the volume | `docker compose exec api env \| grep DB_PATH` |
| `No such file ... sanctions` | Data jobs not run, or `./data` not mounted | Run the one-off jobs; check `volumes:` |
| LLM calls time out from container | `localhost` used for the host | `host.docker.internal` or service name |
| Build is slow on every change | `COPY . .` before dependency install | Reorder as in 3.3 |
| Image is huge | PyTorch (via sentence-transformers) | CPU-only index; check which package pulls it in |
| First request very slow | Embedding model downloading on first use | Warm up at build time or mount a cache volume |
| `no space left on device` | Old images and build cache | `docker system df`, then `docker system prune` |
| Two requests, second hangs or `database is locked` | More than one worker or process writing SQLite | `--workers 1`; see section 6 |

---

## 6. The enterprise picture

What you do locally is the same shape as an enterprise path. What differs is
that each step is owned by a platform, a pipeline or a control function, and
auditable.

### 6.1 From laptop to production

```
developer commit
   -> pull request (review, required checks)
   -> CI pipeline: lint, unit tests, build image, vulnerability scan, SBOM, sign
   -> push to internal registry, tagged with the git commit SHA
   -> deploy to DEV  (automatic)
   -> deploy to TEST/UAT (automatic or approved; integration and eval suite run)
   -> change approval (change record, risk sign-off for AI/model changes)
   -> deploy to PROD (pipeline, not a person running commands)
   -> monitoring, alerting, audit logs; rollback = redeploy the previous tag
```

You never run `docker run` on a production server. Humans change the
pipeline and the configuration in Git; the pipeline changes production
("GitOps" or "infrastructure as code").

### 6.2 Local step to enterprise equivalent

| Local (this project) | Enterprise equivalent | Why it differs |
|---|---|---|
| `docker build` on your laptop | Built by CI on a build agent from a clean checkout | Reproducible, no "works on my machine" |
| `FROM python:3.12-slim` from Docker Hub | An approved, hardened base image from the internal registry, often rebuilt weekly with patches | Supply-chain control |
| `aml-investigator:dev` / `latest` | Immutable tag = git SHA (and a semantic version). `latest` is banned | You must know exactly what runs and be able to roll back |
| Local image only | Pushed to a private registry (Artifactory, ECR, ACR, GAR, GHCR) with access control | Central, audited storage |
| `uv sync` pulls from PyPI | Dependencies pulled through an internal mirror/proxy; lock file pinned and hash-checked | Build machines usually have no direct internet |
| No scanning | Image scan (Trivy, Grype, Prisma, Snyk) fails the build on critical CVEs; SBOM stored; image signed (cosign) | Vulnerability management and provenance |
| `.env` file with API key | Secrets manager (Vault, AWS Secrets Manager, Azure Key Vault) injected at run time; rotated; never in Git or images | Keys leak; rotation and audit are mandatory |
| `env_file` / `environment:` | Config per environment from ConfigMaps / parameter store, values in a Git repo reviewed like code | Dev, test, prod differ by config only |
| `docker compose up` | Kubernetes (or ECS, Cloud Run, OpenShift): you declare desired state; the platform keeps it true | Scaling, self-healing, rolling updates |
| `ports: 8000:8000` | Service + Ingress / API gateway with TLS, authentication, rate limiting, WAF | Nobody exposes a container directly |
| No authentication | OAuth2/OIDC tokens or mutual TLS via the gateway; roles decide who may call `/decision` | The reviewer's identity must be real, not a free-text field |
| `./data` bind mount | Persistent volume claims for files; a managed database (Postgres) for case store and checkpoints | Containers move between machines; SQLite on one disk cannot be shared |
| `--workers 1`, one container | Several replicas behind a load balancer | Availability and throughput; needs shared state (Postgres), see 6.4 |
| `docker logs` | Logs written as JSON to stdout, collected to Splunk/ELK/Datadog with correlation IDs | Search across replicas and time, retention rules |
| `/health` | Separate liveness and readiness probes; readiness also checks DB and LLM reachability | Platform decides when to restart or route traffic |
| `docker stats` | Metrics (Prometheus/OpenTelemetry), dashboards, alerts on latency, errors, token spend | Operate it without looking at it |
| You run the eval script | Eval suite is a pipeline gate: a prompt or model change that drops metrics blocks the release | Behaviour regressions are release risks |
| Public sanctions CSV in `./data` | Licensed or vendor screening data, refreshed by a scheduled job, with data lineage | Freshness and provenance are regulatory points |
| Anthropic API key in env | Calls go through an approved model gateway or private endpoint; allow-listed egress; prompts and responses logged under data rules | Customer data must not leave approved boundaries |

### 6.3 Kubernetes in ten lines of vocabulary

You do not need it to finish this project, but you will meet it:

| Object | Role | Compose analogue |
|---|---|---|
| **Pod** | One or more containers scheduled together | a service's container |
| **Deployment** | Keeps N replicas of a pod running; does rolling updates and rollbacks | `restart:` plus scaling |
| **Service** | Stable internal address and load balancing for the pods | service-name DNS |
| **Ingress / Gateway** | HTTP routing and TLS from outside | `ports:` |
| **ConfigMap / Secret** | Non-secret and secret configuration | `environment:` / `env_file` |
| **PersistentVolumeClaim** | Request for durable storage | `volumes:` |
| **Liveness / readiness probe** | Restart if dead / send traffic only if ready | `healthcheck:` |
| **Resource requests and limits** | CPU/memory reserved and capped | none |
| **Namespace** | Isolated area per team or environment | none |

### 6.4 Why `--workers 1` is a teaching point

SQLite is a file. Two containers cannot safely share it, and replicas on
different machines cannot see the same file. Our graph also keeps a paused
case in the checkpointer. In an enterprise you would:

- replace both SQLite stores with Postgres (LangGraph has a Postgres
  checkpointer; the case store is a small SQL rewrite),
- then run several stateless API replicas,
- and for long investigations, return `202` and run the graph in a worker
  that reads jobs from a queue (Celery, SQS, Service Bus, Temporal), so an
  HTTP request is never held open for minutes and a restart does not lose a run.

The shape of the final design: **API (stateless) -> queue -> workers ->
Postgres + vector DB**, with the LLM reached through a gateway.

### 6.5 Concerns specific to an AI agent in a regulated setting

- **Audit trail.** Every case needs: inputs, evidence used, prompt and model
  version, memo, human decision and reviewer identity, timestamps. Your trace
  and case store are the seed of this. Records must be append-only or
  versioned, with defined retention.
- **Model risk management.** Changing the model, prompt or scoring policy is a
  controlled change. Record which versions produced which decisions
  (log the model name, a hash of the prompts and the policy version on each case).
- **Human in the loop.** The decision endpoint needs authentication,
  authorisation (maker/checker: the reviewer is not the requester) and an
  immutable record. Free-text `reviewer` is a placeholder.
- **Data protection.** Entity names can be personal data. Decide what is
  logged, what is sent to an external LLM, and where data resides. Logs should
  not contain full memos by default.
- **Non-determinism.** LLM output varies. Store the output, do not
  re-generate it for audit. Pin temperature and model versions.
- **Failure behaviour.** If the LLM or data source is down, the safe answer is
  an explicit error or "awaiting review", never a silent "clear".
- **Cost and rate limits.** Track tokens per case (your trace already has
  them) and set budgets and timeouts.

### 6.6 Environment and release practice

- Dev, test and prod are separate deployments of the **same image**.
- Config is versioned; secrets are not in it.
- Promote by tag. Roll back by redeploying the previous tag.
- Database changes use migrations (Alembic), reviewed and run by the
  pipeline.
- Releases use rolling or blue/green updates so there is no downtime.
- Runbooks and alerts exist before go-live: who is paged if the health check fails at 3am.

---

## 7. Exercise ladder

Do the levels in order. Levels 1 and 2 are the core of Phase 13.

1. **Local container.** Sections 2 to 4. Done when the plan's six acceptance
   criteria pass.
2. **Harden it.** Non-root user verified; add `HEALTHCHECK`; scan the image
   with Trivy (`docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image aml-investigator:dev`)
   and read the findings; tag the image with the git SHA
   (`docker build -t aml-investigator:$(git rev-parse --short HEAD) .`).
3. **Mini CI/CD.** Add a GitHub Actions workflow: on pull request run lint and
   tests; on merge to main build the image and push it to GitHub Container
   Registry tagged with the SHA. This is the enterprise pipeline in
   miniature: you need `permissions: packages: write` and the built-in
   `GITHUB_TOKEN`. Then pull and run the image from the registry on a clean
   checkout to prove it is self-contained.
4. **Orchestrator.** Install `kind` (Kubernetes in Docker). Write a
   Deployment, Service, ConfigMap and Secret for the API; load the image with
   `kind load docker-image`; add liveness and readiness probes; call the API
   with `kubectl port-forward`. Kill the pod (`kubectl delete pod`) and watch
   it come back.
5. **Make it scale.** Add a Postgres container, switch the checkpointer and case
   store to it, then run two API replicas. Start a case on one and resume on
   the other. Add the async `202` pattern with a background worker.
6. **Operate it.** Emit JSON logs with a request ID, add `/metrics`
   (Prometheus), put an API key or OIDC check in front of `/decision`, and
   write a one-page runbook: symptoms, checks, rollback.

---

## 8. Self-check

You understand the topic when you can answer these without notes:

1. Why does the Dockerfile copy `pyproject.toml` and `uv.lock` before the code?
2. What is lost on `docker compose down`, and what survives? Why?
3. Why does `curl localhost:8000` fail if uvicorn binds `127.0.0.1`?
4. Why can't you use `localhost` to reach Ollama from inside the container?
5. Why is an image tag of `latest` a problem in production?
6. Where would a production API key live, and how does it reach the container?
7. Why must this service run one worker today, and what would you change to run ten?
8. Why does `POST /investigations` return 200 with `awaiting_review` instead of an error?
9. What evidence would an auditor need for a decision made in March, and which of it do you currently store?
10. What does CI do that your laptop build does not?

---

## 9. Glossary

- **CI/CD**: automated build/test (continuous integration) and automated release (continuous delivery/deployment).
- **Registry**: image storage and distribution service.
- **SBOM**: software bill of materials, a list of every package in the image.
- **CVE**: a publicly catalogued security vulnerability.
- **Twelve-factor app**: design rules for deployable services (config in env, logs to stdout, stateless processes, disposable containers).
- **Liveness / readiness**: "is the process alive" versus "can it take traffic now".
- **Ingress / API gateway**: the controlled front door that handles TLS, authentication and rate limits.
- **GitOps**: desired state stored in Git; an automated agent applies it.
- **Maker/checker**: the person who proposes an action is not the person who approves it.
