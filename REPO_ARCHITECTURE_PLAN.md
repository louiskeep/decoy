# Forge â€” Repo Architecture & Gating Plan

> **Companion to:** BUILD_PLAN.md
> **Purpose:** Defines the repository structure, licensing, gating mechanics, and operational separation between the free CLI, the marketing site, and the paid Business platform.
> **Read this before:** Creating any GitHub repo, writing any license validation code, or building anything that crosses the free/paid line.
> **Last updated:** [date]

---

## TL;DR

You will run **three repos**, not one or two:

| Repo | Visibility | Purpose | Hosts |
|---|---|---|---|
| `decoy` | **Public** | The free CLI tool | PyPI, GitHub community |
| `decoy-web` | Public | Marketing site + docs source | Vercel + Mintlify |
| `decoy-platform` | **Private** | The paid Business web app + license server | Your infra (and customer infra for self-hosted) |

Gating happens in **three layers**:

1. **CLI feature gating** â€” the public CLI checks for a signed license key before unlocking Business commands
2. **Platform-only features** â€” web UI, scheduling persistence, audit logs, RBAC live entirely in the private platform repo and are inaccessible to free users by definition
3. **License issuance** â€” Stripe billing â†’ license server (in platform) â†’ signed JWT delivered to customer

Build them in this order: **`decoy` first, `decoy-web` in parallel, `decoy-platform` LAST** (after CLI demand is validated).

---

## Phase 0 â€” Decisions to Lock Before Any Code

### 0.1 License Choice for the CLI (MUST-HAVE)

You must pick a license before your first PyPI release. Changing it later is legally and culturally messy.

**Three realistic options:**

| License | What it does | Used by | Verdict for Forge |
|---|---|---|---|
| **MIT / Apache 2.0** | Fully open source. Anyone can use, modify, redistribute, even sell. | Most OSS dev tools | âŒ Too permissive â€” a competitor could fork and offer a managed Forge |
| **Business Source License (BUSL)** | Source-available now. Commercial use restricted. Auto-converts to Apache 2.0 after N years (typically 4). | Sentry, MariaDB, CockroachDB, Couchbase | âœ… **Recommended** |
| **Elastic License v2 (ELv2)** | Source-available. Can't be offered as a competing managed service. Can't be modified to remove license/auth checks. | Elastic, Redis (post-2024), MinIO | âœ… Acceptable alternative |

**Recommended choice: BUSL with a 4-year change date and Apache 2.0 as the change license.**

This signals "community-friendly but we're a business" â€” it's the modern default for monetized dev tools. The 4-year auto-conversion is a strong signal of long-term openness without giving away the present.

- [ ] License chosen (recommend BUSL)
- [ ] LICENSE.md added to `decoy` repo before first release
- [ ] License documented prominently in README
- [ ] Decision recorded with reasoning (in case you have to defend it later to investors or community)

### 0.2 Repo Naming Convention (MUST-HAVE)

Pick once, stay consistent. Recommended:

```
forge                    â† the CLI (the headline name, no suffix)
forge-web                â† the marketing site + docs
forge-platform           â† the paid Business product
forge-helm               â† (later) Helm chart for self-hosted deploys
forge-docker             â† (later) Docker images for the platform
forge-examples           â† (later) example pipelines and recipes
```

The unsuffixed name (`decoy`) belongs to the most important public artifact â€” the CLI. This is GitHub convention (e.g., `vercel/next.js`, not `vercel/next-js-cli`). When someone hits `github.com/forgeio/forge`, they should land on the thing they install.

- [ ] GitHub org name decided (e.g., `forgeio`, `forgehq`, `getforge`)
- [ ] Repo names confirmed
- [ ] Reserved PyPI name matches CLI repo name

### 0.3 Source-Available vs. Closed Binary (MUST-HAVE)

You have two macro paths. Pick one:

**Path A â€” Source-available CLI (recommended)**
- Public repo, BUSL license
- Code is readable, forkable for personal/internal use
- Builds trust with technical buyers
- Community can submit PRs for connectors, transforms, bug fixes
- License key prevents unauthorized commercial use

**Path B â€” Closed binary CLI**
- Private repo
- Ship as compiled wheels or PyInstaller binary only
- No source visibility
- No community contributions
- Smaller surface area for license circumvention

**Strong recommendation: Path A.** Your buyers (senior data engineers) trust tools whose code they can read. Closed binaries trigger "what is this thing actually doing to my data?" alarms â€” which is the *opposite* of what you want for a data masking tool. The trust signal of source-availability is worth more than the marginal protection of a closed binary, and BUSL gives you adequate commercial protection.

- [ ] Path chosen (recommend A)

---

## Repo 1 â€” `decoy` (Public CLI)

### Purpose

The free Python CLI tool. This is what `pip install decoy` installs. This is what data engineers fall in love with at 11pm on a Tuesday.

### Visibility

**Public from day one.** Even before launch. Even with rough code. The GitHub stars and traffic that accumulate during development are real signal and free marketing.

### What Lives Here

- All CLI command code (Typer-based)
- All masking transforms
- All synthetic data generation logic
- All connectors (source/destination implementations)
- YAML schema definitions and validation
- License *verification* code (NOT issuance â€” see below)
- CLI tests
- CHANGELOG.md
- CONTRIBUTING.md
- Issue templates and PR templates
- Documentation source (only the parts that document the CLI itself; marketing copy lives in `decoy-web`)

### What Does NOT Live Here

- License *signing/issuance* code (lives in `decoy-platform`)
- Web UI code
- Scheduler/orchestration backend
- Billing/Stripe integration
- Auth/RBAC for the web app
- Customer database schema
- Marketing site code or copy

### Repo Skeleton

```
forge/
â”œâ”€â”€ .github/
â”‚   â”œâ”€â”€ workflows/
â”‚   â”‚   â”œâ”€â”€ test.yml              # multi-OS, multi-Python CI
â”‚   â”‚   â”œâ”€â”€ release.yml           # publishes to PyPI on tag
â”‚   â”‚   â””â”€â”€ lint.yml
â”‚   â”œâ”€â”€ ISSUE_TEMPLATE/
â”‚   â”‚   â”œâ”€â”€ bug_report.md
â”‚   â”‚   â”œâ”€â”€ feature_request.md
â”‚   â”‚   â””â”€â”€ connector_request.md
â”‚   â””â”€â”€ PULL_REQUEST_TEMPLATE.md
â”œâ”€â”€ src/
â”‚   â””â”€â”€ forge/
â”‚       â”œâ”€â”€ __init__.py
â”‚       â”œâ”€â”€ __main__.py
â”‚       â”œâ”€â”€ cli/                  # Typer commands
â”‚       â”œâ”€â”€ transforms/           # masking transforms
â”‚       â”œâ”€â”€ generators/           # synthetic data
â”‚       â”œâ”€â”€ connectors/           # source/dest plugins
â”‚       â”œâ”€â”€ schema/               # Pydantic YAML models
â”‚       â”œâ”€â”€ license/              # JWT verification only
â”‚       â”œâ”€â”€ telemetry/            # opt-in usage events
â”‚       â””â”€â”€ ui/                   # Rich-based output formatting
â”œâ”€â”€ tests/
â”œâ”€â”€ examples/                     # sample YAML pipelines
â”œâ”€â”€ docs/                         # if any docs are repo-local; main docs live in forge-web/Mintlify
â”œâ”€â”€ pyproject.toml
â”œâ”€â”€ README.md
â”œâ”€â”€ LICENSE.md                    # BUSL
â”œâ”€â”€ CHANGELOG.md
â”œâ”€â”€ CONTRIBUTING.md
â”œâ”€â”€ SECURITY.md
â””â”€â”€ CODE_OF_CONDUCT.md
```

### CI/CD

- [ ] **Test workflow:** runs on every PR, matrix of Python 3.10â€“3.13 Ã— Mac/Linux/Windows
- [ ] **Lint workflow:** ruff + mypy on every PR
- [ ] **Release workflow:** triggered on tag push (e.g., `v1.2.3`), builds wheel, publishes to PyPI, creates GitHub Release with changelog
- [ ] **Branch protection:** require passing CI + 1 review for `main` (even if you're solo, this prevents accidental direct pushes)

### Release Process

1. Update CHANGELOG.md with new version notes
2. Bump version in `pyproject.toml`
3. PR, merge
4. Tag the merge commit with `vX.Y.Z`
5. Push tag â†’ release workflow auto-publishes to PyPI

### License Verification (Critical Section)

This is the trickiest part of the public repo. You need code that can *verify* a license without enabling anyone to *issue* a fake one.

**How it works:**

1. **You generate an asymmetric keypair** (e.g., RSA or Ed25519). The private key lives in `decoy-platform` and *never* leaves your platform's secret store. The public key is embedded in the `decoy` CLI repo.
2. **When a customer subscribes,** your platform issues them a signed JWT containing:
   - `customer_id` (opaque)
   - `tier` (e.g., `business`, `enterprise`)
   - `seats` (e.g., 25)
   - `issued_at`
   - `expires_at`
   - `features` (array of feature flags they're entitled to)
3. **The CLI verifies the JWT** using the embedded public key. Verification only confirms the signature is valid and the token hasn't expired. It does *not* require a network call.
4. **Cached result is fine for offline use.** The CLI caches the verified license at `~/.decoy/license.json` after first verification.
5. **Periodic re-validation** (e.g., every 7 days) calls back to the platform to confirm the license is still active (covers cancellations, fraud). If offline, the CLI grants access until the JWT's own expiration.

**Why this works in public code:**

- Anyone can read the verification code. That's fine â€” it's just signature verification.
- Generating a fake license requires the private key, which is never in this repo.
- An attacker would have to either steal your private key (defended by normal opsec) or modify the CLI to skip verification (which violates BUSL â€” and at that point they're not your customer anyway).

**Example pseudocode for the CLI:**

```python
# src/decoy/license/verify.py
from jose import jwt
from pathlib import Path

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
... your public key ...
-----END PUBLIC KEY-----"""

def verify_license(license_token: str) -> dict | None:
    try:
        claims = jwt.decode(
            license_token,
            PUBLIC_KEY,
            algorithms=["RS256"],
        )
        return claims
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None

def require_business(func):
    def wrapper(*args, **kwargs):
        license_path = Path.home() / ".forge" / "license.json"
        if not license_path.exists():
            print_upgrade_message("This command requires a Business license.")
            raise SystemExit(1)

        token = license_path.read_text().strip()
        claims = verify_license(token)
        if claims is None or claims.get("tier") not in ("business", "enterprise"):
            print_upgrade_message("Your license has expired or is invalid.")
            raise SystemExit(1)
        return func(*args, **kwargs)
    return wrapper
```

- [ ] Asymmetric keypair generated; private key in platform secret store; public key embedded in CLI
- [ ] JWT structure designed and documented
- [ ] `decoy login` command implemented (accepts license key, validates, caches)
- [ ] `decoy license` command implemented (shows current license status)
- [ ] `@require_business` decorator implemented for gated commands
- [ ] Friendly upgrade message component built (the messaging when someone hits a paid feature)

### Community Posture

- [ ] Issues enabled with templates
- [ ] Discussions enabled
- [ ] CONTRIBUTING.md welcomes connector PRs and transform PRs
- [ ] Discord or Slack invite linked from README
- [ ] Code of Conduct (Contributor Covenant is the standard)
- [ ] Security policy: SECURITY.md with disclosure process

---

## Repo 2 â€” `decoy-web` (Marketing Site + Docs Source)

### Purpose

The website at `decoy.dev`. Includes the marketing pages and the Mintlify docs source.

### Visibility

**Public** by default. This is the modern convention (Resend, PostHog, Supabase all do this) and it lets the community submit doc improvements via PR. Private is also acceptable if you want commit history to stay private.

### What Lives Here

- Next.js marketing site (exported from v0)
- Mintlify docs source (MDX files)
- Site assets (logos, OG images, blog post images)
- Blog post content (MDX or Markdown)
- Comparison page content
- Marketing copy
- SEO config (sitemap generation, robots.txt)

### What Does NOT Live Here

- Anything that needs runtime secrets (those live in Vercel env vars, not the repo)
- Customer data or auth tokens
- Platform code
- CLI code

### Repo Skeleton

```
forge-web/
â”œâ”€â”€ .github/workflows/
â”‚   â””â”€â”€ lint.yml
â”œâ”€â”€ app/                          # Next.js app router pages
â”‚   â”œâ”€â”€ page.tsx                  # home
â”‚   â”œâ”€â”€ pricing/page.tsx
â”‚   â”œâ”€â”€ product/
â”‚   â”‚   â”œâ”€â”€ masking/page.tsx
â”‚   â”‚   â”œâ”€â”€ synthetic-data/page.tsx
â”‚   â”‚   â”œâ”€â”€ transforms/page.tsx
â”‚   â”‚   â””â”€â”€ analytics/page.tsx
â”‚   â”œâ”€â”€ compare/
â”‚   â”‚   â”œâ”€â”€ tonic/page.tsx
â”‚   â”‚   â”œâ”€â”€ delphix/page.tsx
â”‚   â”‚   â””â”€â”€ informatica/page.tsx
â”‚   â”œâ”€â”€ solutions/
â”‚   â”‚   â”œâ”€â”€ dev-test-data/page.tsx
â”‚   â”‚   â”œâ”€â”€ compliance/page.tsx
â”‚   â”‚   â””â”€â”€ ai-training/page.tsx
â”‚   â”œâ”€â”€ security/page.tsx
â”‚   â”œâ”€â”€ self-hosting/page.tsx
â”‚   â”œâ”€â”€ about/page.tsx
â”‚   â”œâ”€â”€ blog/
â”‚   â”œâ”€â”€ changelog/page.tsx
â”‚   â””â”€â”€ (legal)/
â”‚       â”œâ”€â”€ privacy/
â”‚       â””â”€â”€ terms/
â”œâ”€â”€ components/                   # shadcn/ui components
â”œâ”€â”€ content/
â”‚   â”œâ”€â”€ blog/                     # MDX blog posts
â”‚   â””â”€â”€ changelog/
â”œâ”€â”€ docs/                         # Mintlify source â€” separate deployment
â”‚   â”œâ”€â”€ mint.json                 # Mintlify config
â”‚   â”œâ”€â”€ getting-started/
â”‚   â”œâ”€â”€ concepts/
â”‚   â”œâ”€â”€ cli-reference/
â”‚   â”œâ”€â”€ yaml-reference/
â”‚   â”œâ”€â”€ connectors/
â”‚   â”œâ”€â”€ transforms/
â”‚   â”œâ”€â”€ recipes/
â”‚   â”œâ”€â”€ business-tier/
â”‚   â”œâ”€â”€ self-hosting/
â”‚   â””â”€â”€ security/
â”œâ”€â”€ public/                       # static assets
â”œâ”€â”€ next.config.js                # includes /docs â†’ Mintlify rewrite
â”œâ”€â”€ tailwind.config.ts
â”œâ”€â”€ package.json
â””â”€â”€ README.md
```

### Deployment

- [ ] **Marketing site:** deploys to Vercel from `main` automatically
- [ ] **Docs:** Mintlify pulls from `decoy-web/docs` directory automatically on push
- [ ] **Domain:** `decoy.dev` (Vercel), `decoy.dev/docs` (Mintlify rewrite)
- [ ] **Preview deploys:** every PR gets a Vercel preview URL â€” useful for reviewing copy changes

### What Connects to Where

The site has these outbound links:

- Hero install command â†’ copy to clipboard, no link
- "GitHub" / "Star us" â†’ `github.com/forgeio/forge` (the CLI repo)
- "Docs" â†’ `decoy.dev/docs` (same domain via rewrite)
- "Start free trial" â†’ `app.forge.dev/signup` (the platform)
- "Login" â†’ `app.forge.dev/login` (the platform)

The site itself never embeds product UI. It links to it.

---

## Repo 3 â€” `decoy-platform` (Private Business Product)

### Purpose

The paid product. Web UI, scheduler backend, license issuance, billing, RBAC, audit logs.

### Visibility

**Private. Always. Forever.**

### Build It LAST

Do not create this repo until:

- [ ] CLI has shipped to PyPI
- [ ] You have at least 100 PyPI installs (any installs, real signal)
- [ ] You have at least 5 conversations with users asking for team features
- [ ] You have a clear list of which 3 features will gate Business

This discipline is critical. The single biggest way solo founders torch their first 6 months is building the platform before validating CLI demand. Resist.

### What Lives Here

- Backend API (FastAPI)
- Web UI (Next.js, separate from marketing site)
- License issuance service (signs JWTs with the private key)
- Scheduler / job runner
- Audit log system
- RBAC and team management
- Stripe integration
- Customer dashboard
- Pipeline storage and run history
- Helm chart and Docker images for self-hosted deployment
- Database migrations
- Admin tools (for support)

### What Does NOT Live Here

- Public CLI code (lives in `decoy`)
- Marketing pages (live in `decoy-web`)
- Anything a free user would ever execute on their machine

### Repo Skeleton

```
forge-platform/
â”œâ”€â”€ .github/workflows/
â”‚   â”œâ”€â”€ test.yml
â”‚   â”œâ”€â”€ docker-publish.yml
â”‚   â””â”€â”€ helm-publish.yml
â”œâ”€â”€ api/                          # FastAPI backend
â”‚   â”œâ”€â”€ main.py
â”‚   â”œâ”€â”€ auth/
â”‚   â”œâ”€â”€ billing/                  # Stripe webhooks, subscription mgmt
â”‚   â”œâ”€â”€ licenses/                 # JWT issuance
â”‚   â”œâ”€â”€ pipelines/
â”‚   â”œâ”€â”€ runs/
â”‚   â”œâ”€â”€ audit/
â”‚   â””â”€â”€ teams/
â”œâ”€â”€ web/                          # Next.js Business app
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ dashboard/
â”‚   â”‚   â”œâ”€â”€ pipelines/
â”‚   â”‚   â”œâ”€â”€ runs/
â”‚   â”‚   â”œâ”€â”€ audit/
â”‚   â”‚   â”œâ”€â”€ team/
â”‚   â”‚   â”œâ”€â”€ billing/
â”‚   â”‚   â””â”€â”€ settings/
â”‚   â””â”€â”€ components/
â”œâ”€â”€ scheduler/                    # background job runner
â”œâ”€â”€ deploy/
â”‚   â”œâ”€â”€ docker-compose.yml        # for single-node self-hosted
â”‚   â”œâ”€â”€ helm/                     # for k8s self-hosted
â”‚   â””â”€â”€ terraform/                # your hosted version
â”œâ”€â”€ secrets/                      # gitignored, references only
â””â”€â”€ README.md
```

### License Issuance Flow

1. Customer signs up at `app.forge.dev/signup`
2. Selects Business tier, enters payment info (Stripe Checkout)
3. Stripe webhook â†’ `decoy-platform` billing service
4. Billing service calls license issuance service
5. License service signs a JWT with the private key, including tier/seats/expiration
6. JWT is delivered to customer:
   - In the web UI (copy/paste)
   - Via email
   - Via `decoy login --sso` flow (CLI opens browser, authenticates, downloads license automatically)
7. CLI stores license at `~/.decoy/license.json`
8. Gated commands now work

### Self-Hosted Distribution

For Enterprise customers who run the platform on their own infra:

- [ ] Helm chart published to a private Helm registry
- [ ] Docker images published to a private registry (GHCR with tokens, or AWS ECR)
- [ ] Customer receives access tokens with their license
- [ ] License key validates the deployment itself (the platform checks its own license on startup)
- [ ] Air-gapped deployment supported (long-lived offline licenses for true air-gap customers)

---

## How the Three Repos Talk to Each Other

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                                             â”‚
â”‚   github.com/forgeio/forge          (PUBLIC, BUSL)          â”‚
â”‚   â”œâ”€ pip install decoy                                      â”‚
â”‚   â”œâ”€ contains: CLI, transforms, connectors, JWT verifier    â”‚
â”‚   â””â”€ embedded: PUBLIC KEY for license verification          â”‚
â”‚                                                             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                           â”‚
                           â”‚  reads license JWT
                           â”‚  (offline-capable)
                           â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                                             â”‚
â”‚   github.com/forgeio/forge-platform     (PRIVATE)           â”‚
â”‚   â”œâ”€ deploys to: app.forge.dev                              â”‚
â”‚   â”œâ”€ contains: web UI, scheduler, billing, license signer   â”‚
â”‚   â””â”€ secret: PRIVATE KEY (never leaves platform)            â”‚
â”‚                                                             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                           â”‚
                           â”‚  links to PyPI, GitHub
                           â”‚  (no shared code, just URLs)
                           â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                                             â”‚
â”‚   github.com/forgeio/forge-web          (PUBLIC)            â”‚
â”‚   â”œâ”€ deploys to: forge.dev (Vercel)                         â”‚
â”‚   â”œâ”€ contains: marketing pages, blog, MDX docs              â”‚
â”‚   â””â”€ links out to: github.com/forgeio/forge,                â”‚
â”‚                    pypi.org/project/forge,                  â”‚
â”‚                    app.forge.dev                            â”‚
â”‚                                                             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

**No shared code between repos.** Each repo is self-contained. The "shared interface" is the JWT format (defined once, documented, never changed casually) and the URL conventions (`decoy.dev`, `app.forge.dev`).

---

## The Three Layers of Gating, Concretely

### Layer 1: CLI Feature Gating

The CLI knows which commands require Business. The decorator pattern handles this cleanly:

```python
# Free commands â€” anyone can run
@app.command()
def run(pipeline: Path):
    ...

@app.command()
def validate(pipeline: Path):
    ...

# Business commands â€” gated
@app.command()
@require_business
def schedule(pipeline: Path, cron: str):
    ...

@app.command()
@require_business
def push(pipeline: Path):
    ...
```

When someone runs `decoy schedule` without a license:

```
âœ— This command requires a Business license.

  Scheduling is part of the Business tier, along with the web UI,
  audit logs, and team collaboration features.

  â†’ Start a free 14-day trial: https://forge.dev/trial
  â†’ Already have a license? Run `decoy login`

  Free CLI users can still run pipelines locally with `decoy run`.
```

This message is critical UX. It must be **helpful, not pushy**. The last line is intentional â€” it confirms what they *can* still do, so the upgrade prompt feels like an offer, not a wall.

### Layer 2: Platform-Only Features

The web UI, persistent run history, audit logs, RBAC, and scheduling backend all live in `decoy-platform`. Free CLI users have no way to access them â€” not because they're locked, but because they're hosted on infrastructure those users don't have credentials for.

This is the cleanest gate possible: features that aren't in the free product can't be unlocked even theoretically.

### Layer 3: License Issuance

Stripe â†’ webhook â†’ license service â†’ signed JWT â†’ customer. The customer never sees or handles the private key. The CLI never communicates with Stripe. License lifecycle (renewal, cancellation, seat changes) is handled in the platform and propagates to the CLI on next sync.

---

## Operational Concerns

### Branding and Account Convention

Pick one and stay consistent:

- GitHub org: `forgeio` (or whatever)
- npm scope (if you ever publish JS packages): `@forgeio`
- Docker Hub / GHCR org: `forgeio`
- PyPI: `decoy` (no scope on PyPI; squat the name)
- Domain: `decoy.dev` (apex), `app.forge.dev` (platform), `docs.forge.dev` *or* `decoy.dev/docs` (pick one and stick)

### Secrets Management

| Secret | Lives in | Never in |
|---|---|---|
| License signing private key | Platform secret store (AWS Secrets Manager, Vault, Doppler) | Any repo, ever |
| License verification public key | `decoy` CLI source code (embedded constant) | â€” (this is meant to be public) |
| Stripe API keys | Platform env vars | Any repo |
| Customer DB credentials | Platform env vars | Any repo |
| PyPI publish token | GitHub Actions secret on `decoy` repo | Any committed file |
| Vercel deploy token | Vercel-managed | â€” |

### Versioning

- **CLI (`decoy`):** SemVer. Major version bumps for breaking YAML schema changes only.
- **Platform (`decoy-platform`):** Internal version for SaaS-hosted (continuous deploy). For self-hosted, customers pin to a release version (e.g., `v2024.05`).
- **Web (`decoy-web`):** No versioning. Continuous deploy.

### Cross-Repo Coordination

Some changes affect multiple repos:

- **YAML schema change** â†’ CLI version bump â†’ docs update in `decoy-web/docs` â†’ if it affects pipeline storage, platform migration needed
- **New feature gated to Business** â†’ CLI adds `@require_business` â†’ platform adds the backend support â†’ web updates pricing page
- **New connector** â†’ CLI adds connector code â†’ docs page added in `decoy-web` â†’ integrations grid updated in `decoy-web`

Keep a `CHANGELOG.md` in each repo. For cross-repo changes, the CLI changelog references the docs PR and platform release notes. This sounds like overhead but it'll save you when a customer reports a bug spanning two repos.

---

## Pre-Code Setup Checklist

Before you write a single line of code, do this admin work in one half-day session:

- [ ] Buy domain (`decoy.dev` or whatever)
- [ ] Create GitHub org
- [ ] Create `decoy` repo (public, BUSL license, README placeholder)
- [ ] Create `decoy-web` repo (public, README placeholder)
- [ ] Reserve PyPI package name (publish a 0.0.1 placeholder that just prints "coming soon")
- [ ] Reserve npm scope if you might use one later
- [ ] Reserve Docker Hub / GHCR org names
- [ ] Reserve Twitter/X, LinkedIn, BlueSky handles
- [ ] Reserve Discord server name (or Slack workspace)
- [ ] Set up Vercel account, point `decoy.dev` at it
- [ ] Set up Mintlify account
- [ ] Set up PostHog or Plausible account for analytics
- [ ] Set up email forwarding for `support@`, `hello@`, `security@`
- [ ] Set up password manager (1Password / Bitwarden) entry for the project
- [ ] Generate the license signing keypair (store private key in 1Password for now; move to proper secret store when platform exists)

**Do not** create `decoy-platform` yet. You don't need it. Resist.

---

## Common Mistakes to Avoid

### Mistake 1: "I'll keep platform code in the CLI repo for now"

This is the #1 architecture sin. Platform code creeping into the public CLI repo because "it's easier." Then six months later you have to do a painful repo split with git-filter-repo, broken history, and a privacy review of every commit you ever made.

**Rule:** if it's not something a free CLI user runs on their machine, it doesn't belong in the CLI repo. No exceptions. Not even for "just a stub."

### Mistake 2: "I'll figure out licensing later"

Licensing is a Phase 0 decision. You cannot launch a paid tier without it, and changing licenses later (especially relicensing the CLI from MIT to BUSL) generates community backlash. Decide before code.

### Mistake 3: "I'll embed the private key in the CLI"

Sounds obvious but I've seen it. The private key signs licenses; if it's in the CLI, anyone can sign their own licenses. Always asymmetric: private key in platform only, public key embedded in CLI for verification.

### Mistake 4: "I'll build the platform before launching the CLI"

You'll spend 3 months building a web UI for a tool no one uses. Launch the CLI first. If 100 people install it, build the platform. If they don't, you've saved yourself 3 months.

### Mistake 5: "Marketing copy goes in the CLI README"

The CLI README should be technical: install, quick start, link to full docs, link to website. The marketing copy lives at `decoy.dev`. Keeping them separate prevents the README from becoming a sales page (which technical buyers find off-putting on GitHub).

### Mistake 6: "I'll make `decoy-platform` public to simplify CI"

It's tempting. Don't. The moment you take payments, your platform repo contains code paths that handle billing, license issuance, and customer data. Public visibility creates legal exposure and weakens your moat.

### Mistake 7: "I'll skip the public/private split and use a monorepo"

Monorepos work for unified teams shipping to one customer. They don't work for "free OSS-adjacent CLI + private SaaS platform" because the visibility requirements are *opposite*. You'd either expose platform code or hide CLI code â€” both are wrong.

---

## When to Re-Evaluate This Architecture

This three-repo structure works for:

- Solo founders to ~10-person teams
- Free OSS-adjacent CLI + paid platform model
- Pre-Series-A through early Series B

You should consider reorganizing when:

- **You add a second paid product.** Might want a fourth repo (`decoy-data-quality` etc.) or migrate the platform repo into a monorepo internally.
- **You hire an OSS community team.** Might want to split connectors into their own public repos so community can own them.
- **You IPO or get acquired.** Whoever acquires you will reorganize anyway.

For the first 2 years, this structure is correct. Don't over-engineer.

---

## Critical Path Summary

1. **Phase 0:** Lock license, naming, and secrets management (1 day of admin)
2. **Day 1:** Create `decoy` and `decoy-web` repos, both public
3. **Weeks 1â€“4:** Build CLI in `decoy`, with license verification baked in from the start
4. **Weeks 3â€“6:** Build site in `decoy-web` in parallel
5. **Week 8:** Launch CLI to PyPI, post to HN, validate demand
6. **Months 3â€“4:** *If demand is real,* create `decoy-platform` (private) and start building the Business web app
7. **Month 6:** Launch Business tier with license issuance flow

Three repos, three jobs, three lifecycles. Keep them clean from day one.

---

*End of architecture plan. This doc is a living standard â€” update it when the architecture evolves.*
