# Forge — Repo Architecture & Gating Plan

> **Companion to:** BUILD_PLAN.md
> **Purpose:** Defines the repository structure, licensing, gating mechanics, and operational separation between the free CLI, the marketing site, and the paid Business platform.
> **Read this before:** Creating any GitHub repo, writing any license validation code, or building anything that crosses the free/paid line.
> **Last updated:** [date]

---

## TL;DR

You will run **three repos**, not one or two:

| Repo | Visibility | Purpose | Hosts |
|---|---|---|---|
| `forge` | **Public** | The free CLI tool | PyPI, GitHub community |
| `forge-web` | Public | Marketing site + docs source | Vercel + Mintlify |
| `forge-platform` | **Private** | The paid Business web app + license server | Your infra (and customer infra for self-hosted) |

Gating happens in **three layers**:

1. **CLI feature gating** — the public CLI checks for a signed license key before unlocking Business commands
2. **Platform-only features** — web UI, scheduling persistence, audit logs, RBAC live entirely in the private platform repo and are inaccessible to free users by definition
3. **License issuance** — Stripe billing → license server (in platform) → signed JWT delivered to customer

Build them in this order: **`forge` first, `forge-web` in parallel, `forge-platform` LAST** (after CLI demand is validated).

---

## Phase 0 — Decisions to Lock Before Any Code

### 0.1 License Choice for the CLI (MUST-HAVE)

You must pick a license before your first PyPI release. Changing it later is legally and culturally messy.

**Three realistic options:**

| License | What it does | Used by | Verdict for Forge |
|---|---|---|---|
| **MIT / Apache 2.0** | Fully open source. Anyone can use, modify, redistribute, even sell. | Most OSS dev tools | ❌ Too permissive — a competitor could fork and offer a managed Forge |
| **Business Source License (BUSL)** | Source-available now. Commercial use restricted. Auto-converts to Apache 2.0 after N years (typically 4). | Sentry, MariaDB, CockroachDB, Couchbase | ✅ **Recommended** |
| **Elastic License v2 (ELv2)** | Source-available. Can't be offered as a competing managed service. Can't be modified to remove license/auth checks. | Elastic, Redis (post-2024), MinIO | ✅ Acceptable alternative |

**Recommended choice: BUSL with a 4-year change date and Apache 2.0 as the change license.**

This signals "community-friendly but we're a business" — it's the modern default for monetized dev tools. The 4-year auto-conversion is a strong signal of long-term openness without giving away the present.

- [ ] License chosen (recommend BUSL)
- [ ] LICENSE.md added to `forge` repo before first release
- [ ] License documented prominently in README
- [ ] Decision recorded with reasoning (in case you have to defend it later to investors or community)

### 0.2 Repo Naming Convention (MUST-HAVE)

Pick once, stay consistent. Recommended:

```
forge                    ← the CLI (the headline name, no suffix)
forge-web                ← the marketing site + docs
forge-platform           ← the paid Business product
forge-helm               ← (later) Helm chart for self-hosted deploys
forge-docker             ← (later) Docker images for the platform
forge-examples           ← (later) example pipelines and recipes
```

The unsuffixed name (`forge`) belongs to the most important public artifact — the CLI. This is GitHub convention (e.g., `vercel/next.js`, not `vercel/next-js-cli`). When someone hits `github.com/forgeio/forge`, they should land on the thing they install.

- [ ] GitHub org name decided (e.g., `forgeio`, `forgehq`, `getforge`)
- [ ] Repo names confirmed
- [ ] Reserved PyPI name matches CLI repo name

### 0.3 Source-Available vs. Closed Binary (MUST-HAVE)

You have two macro paths. Pick one:

**Path A — Source-available CLI (recommended)**
- Public repo, BUSL license
- Code is readable, forkable for personal/internal use
- Builds trust with technical buyers
- Community can submit PRs for connectors, transforms, bug fixes
- License key prevents unauthorized commercial use

**Path B — Closed binary CLI**
- Private repo
- Ship as compiled wheels or PyInstaller binary only
- No source visibility
- No community contributions
- Smaller surface area for license circumvention

**Strong recommendation: Path A.** Your buyers (senior data engineers) trust tools whose code they can read. Closed binaries trigger "what is this thing actually doing to my data?" alarms — which is the *opposite* of what you want for a data masking tool. The trust signal of source-availability is worth more than the marginal protection of a closed binary, and BUSL gives you adequate commercial protection.

- [ ] Path chosen (recommend A)

---

## Repo 1 — `forge` (Public CLI)

### Purpose

The free Python CLI tool. This is what `pip install forge` installs. This is what data engineers fall in love with at 11pm on a Tuesday.

### Visibility

**Public from day one.** Even before launch. Even with rough code. The GitHub stars and traffic that accumulate during development are real signal and free marketing.

### What Lives Here

- All CLI command code (Typer-based)
- All masking transforms
- All synthetic data generation logic
- All connectors (source/destination implementations)
- YAML schema definitions and validation
- License *verification* code (NOT issuance — see below)
- CLI tests
- CHANGELOG.md
- CONTRIBUTING.md
- Issue templates and PR templates
- Documentation source (only the parts that document the CLI itself; marketing copy lives in `forge-web`)

### What Does NOT Live Here

- License *signing/issuance* code (lives in `forge-platform`)
- Web UI code
- Scheduler/orchestration backend
- Billing/Stripe integration
- Auth/RBAC for the web app
- Customer database schema
- Marketing site code or copy

### Repo Skeleton

```
forge/
├── .github/
│   ├── workflows/
│   │   ├── test.yml              # multi-OS, multi-Python CI
│   │   ├── release.yml           # publishes to PyPI on tag
│   │   └── lint.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── connector_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── src/
│   └── forge/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli/                  # Typer commands
│       ├── transforms/           # masking transforms
│       ├── generators/           # synthetic data
│       ├── connectors/           # source/dest plugins
│       ├── schema/               # Pydantic YAML models
│       ├── license/              # JWT verification only
│       ├── telemetry/            # opt-in usage events
│       └── ui/                   # Rich-based output formatting
├── tests/
├── examples/                     # sample YAML pipelines
├── docs/                         # if any docs are repo-local; main docs live in forge-web/Mintlify
├── pyproject.toml
├── README.md
├── LICENSE.md                    # BUSL
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── CODE_OF_CONDUCT.md
```

### CI/CD

- [ ] **Test workflow:** runs on every PR, matrix of Python 3.10–3.13 × Mac/Linux/Windows
- [ ] **Lint workflow:** ruff + mypy on every PR
- [ ] **Release workflow:** triggered on tag push (e.g., `v1.2.3`), builds wheel, publishes to PyPI, creates GitHub Release with changelog
- [ ] **Branch protection:** require passing CI + 1 review for `main` (even if you're solo, this prevents accidental direct pushes)

### Release Process

1. Update CHANGELOG.md with new version notes
2. Bump version in `pyproject.toml`
3. PR, merge
4. Tag the merge commit with `vX.Y.Z`
5. Push tag → release workflow auto-publishes to PyPI

### License Verification (Critical Section)

This is the trickiest part of the public repo. You need code that can *verify* a license without enabling anyone to *issue* a fake one.

**How it works:**

1. **You generate an asymmetric keypair** (e.g., RSA or Ed25519). The private key lives in `forge-platform` and *never* leaves your platform's secret store. The public key is embedded in the `forge` CLI repo.
2. **When a customer subscribes,** your platform issues them a signed JWT containing:
   - `customer_id` (opaque)
   - `tier` (e.g., `business`, `enterprise`)
   - `seats` (e.g., 25)
   - `issued_at`
   - `expires_at`
   - `features` (array of feature flags they're entitled to)
3. **The CLI verifies the JWT** using the embedded public key. Verification only confirms the signature is valid and the token hasn't expired. It does *not* require a network call.
4. **Cached result is fine for offline use.** The CLI caches the verified license at `~/.forge/license.json` after first verification.
5. **Periodic re-validation** (e.g., every 7 days) calls back to the platform to confirm the license is still active (covers cancellations, fraud). If offline, the CLI grants access until the JWT's own expiration.

**Why this works in public code:**

- Anyone can read the verification code. That's fine — it's just signature verification.
- Generating a fake license requires the private key, which is never in this repo.
- An attacker would have to either steal your private key (defended by normal opsec) or modify the CLI to skip verification (which violates BUSL — and at that point they're not your customer anyway).

**Example pseudocode for the CLI:**

```python
# src/forge/license/verify.py
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
- [ ] `forge login` command implemented (accepts license key, validates, caches)
- [ ] `forge license` command implemented (shows current license status)
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

## Repo 2 — `forge-web` (Marketing Site + Docs Source)

### Purpose

The website at `forge.dev`. Includes the marketing pages and the Mintlify docs source.

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
├── .github/workflows/
│   └── lint.yml
├── app/                          # Next.js app router pages
│   ├── page.tsx                  # home
│   ├── pricing/page.tsx
│   ├── product/
│   │   ├── masking/page.tsx
│   │   ├── synthetic-data/page.tsx
│   │   ├── transforms/page.tsx
│   │   └── analytics/page.tsx
│   ├── compare/
│   │   ├── tonic/page.tsx
│   │   ├── delphix/page.tsx
│   │   └── informatica/page.tsx
│   ├── solutions/
│   │   ├── dev-test-data/page.tsx
│   │   ├── compliance/page.tsx
│   │   └── ai-training/page.tsx
│   ├── security/page.tsx
│   ├── self-hosting/page.tsx
│   ├── about/page.tsx
│   ├── blog/
│   ├── changelog/page.tsx
│   └── (legal)/
│       ├── privacy/
│       └── terms/
├── components/                   # shadcn/ui components
├── content/
│   ├── blog/                     # MDX blog posts
│   └── changelog/
├── docs/                         # Mintlify source — separate deployment
│   ├── mint.json                 # Mintlify config
│   ├── getting-started/
│   ├── concepts/
│   ├── cli-reference/
│   ├── yaml-reference/
│   ├── connectors/
│   ├── transforms/
│   ├── recipes/
│   ├── business-tier/
│   ├── self-hosting/
│   └── security/
├── public/                       # static assets
├── next.config.js                # includes /docs → Mintlify rewrite
├── tailwind.config.ts
├── package.json
└── README.md
```

### Deployment

- [ ] **Marketing site:** deploys to Vercel from `main` automatically
- [ ] **Docs:** Mintlify pulls from `forge-web/docs` directory automatically on push
- [ ] **Domain:** `forge.dev` (Vercel), `forge.dev/docs` (Mintlify rewrite)
- [ ] **Preview deploys:** every PR gets a Vercel preview URL — useful for reviewing copy changes

### What Connects to Where

The site has these outbound links:

- Hero install command → copy to clipboard, no link
- "GitHub" / "Star us" → `github.com/forgeio/forge` (the CLI repo)
- "Docs" → `forge.dev/docs` (same domain via rewrite)
- "Start free trial" → `app.forge.dev/signup` (the platform)
- "Login" → `app.forge.dev/login` (the platform)

The site itself never embeds product UI. It links to it.

---

## Repo 3 — `forge-platform` (Private Business Product)

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

- Public CLI code (lives in `forge`)
- Marketing pages (live in `forge-web`)
- Anything a free user would ever execute on their machine

### Repo Skeleton

```
forge-platform/
├── .github/workflows/
│   ├── test.yml
│   ├── docker-publish.yml
│   └── helm-publish.yml
├── api/                          # FastAPI backend
│   ├── main.py
│   ├── auth/
│   ├── billing/                  # Stripe webhooks, subscription mgmt
│   ├── licenses/                 # JWT issuance
│   ├── pipelines/
│   ├── runs/
│   ├── audit/
│   └── teams/
├── web/                          # Next.js Business app
│   ├── app/
│   │   ├── dashboard/
│   │   ├── pipelines/
│   │   ├── runs/
│   │   ├── audit/
│   │   ├── team/
│   │   ├── billing/
│   │   └── settings/
│   └── components/
├── scheduler/                    # background job runner
├── deploy/
│   ├── docker-compose.yml        # for single-node self-hosted
│   ├── helm/                     # for k8s self-hosted
│   └── terraform/                # your hosted version
├── secrets/                      # gitignored, references only
└── README.md
```

### License Issuance Flow

1. Customer signs up at `app.forge.dev/signup`
2. Selects Business tier, enters payment info (Stripe Checkout)
3. Stripe webhook → `forge-platform` billing service
4. Billing service calls license issuance service
5. License service signs a JWT with the private key, including tier/seats/expiration
6. JWT is delivered to customer:
   - In the web UI (copy/paste)
   - Via email
   - Via `forge login --sso` flow (CLI opens browser, authenticates, downloads license automatically)
7. CLI stores license at `~/.forge/license.json`
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
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   github.com/forgeio/forge          (PUBLIC, BUSL)          │
│   ├─ pip install forge                                      │
│   ├─ contains: CLI, transforms, connectors, JWT verifier    │
│   └─ embedded: PUBLIC KEY for license verification          │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │  reads license JWT
                           │  (offline-capable)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   github.com/forgeio/forge-platform     (PRIVATE)           │
│   ├─ deploys to: app.forge.dev                              │
│   ├─ contains: web UI, scheduler, billing, license signer   │
│   └─ secret: PRIVATE KEY (never leaves platform)            │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │  links to PyPI, GitHub
                           │  (no shared code, just URLs)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   github.com/forgeio/forge-web          (PUBLIC)            │
│   ├─ deploys to: forge.dev (Vercel)                         │
│   ├─ contains: marketing pages, blog, MDX docs              │
│   └─ links out to: github.com/forgeio/forge,                │
│                    pypi.org/project/forge,                  │
│                    app.forge.dev                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**No shared code between repos.** Each repo is self-contained. The "shared interface" is the JWT format (defined once, documented, never changed casually) and the URL conventions (`forge.dev`, `app.forge.dev`).

---

## The Three Layers of Gating, Concretely

### Layer 1: CLI Feature Gating

The CLI knows which commands require Business. The decorator pattern handles this cleanly:

```python
# Free commands — anyone can run
@app.command()
def run(pipeline: Path):
    ...

@app.command()
def validate(pipeline: Path):
    ...

# Business commands — gated
@app.command()
@require_business
def schedule(pipeline: Path, cron: str):
    ...

@app.command()
@require_business
def push(pipeline: Path):
    ...
```

When someone runs `forge schedule` without a license:

```
✗ This command requires a Business license.

  Scheduling is part of the Business tier, along with the web UI,
  audit logs, and team collaboration features.

  → Start a free 14-day trial: https://forge.dev/trial
  → Already have a license? Run `forge login`

  Free CLI users can still run pipelines locally with `forge run`.
```

This message is critical UX. It must be **helpful, not pushy**. The last line is intentional — it confirms what they *can* still do, so the upgrade prompt feels like an offer, not a wall.

### Layer 2: Platform-Only Features

The web UI, persistent run history, audit logs, RBAC, and scheduling backend all live in `forge-platform`. Free CLI users have no way to access them — not because they're locked, but because they're hosted on infrastructure those users don't have credentials for.

This is the cleanest gate possible: features that aren't in the free product can't be unlocked even theoretically.

### Layer 3: License Issuance

Stripe → webhook → license service → signed JWT → customer. The customer never sees or handles the private key. The CLI never communicates with Stripe. License lifecycle (renewal, cancellation, seat changes) is handled in the platform and propagates to the CLI on next sync.

---

## Operational Concerns

### Branding and Account Convention

Pick one and stay consistent:

- GitHub org: `forgeio` (or whatever)
- npm scope (if you ever publish JS packages): `@forgeio`
- Docker Hub / GHCR org: `forgeio`
- PyPI: `forge` (no scope on PyPI; squat the name)
- Domain: `forge.dev` (apex), `app.forge.dev` (platform), `docs.forge.dev` *or* `forge.dev/docs` (pick one and stick)

### Secrets Management

| Secret | Lives in | Never in |
|---|---|---|
| License signing private key | Platform secret store (AWS Secrets Manager, Vault, Doppler) | Any repo, ever |
| License verification public key | `forge` CLI source code (embedded constant) | — (this is meant to be public) |
| Stripe API keys | Platform env vars | Any repo |
| Customer DB credentials | Platform env vars | Any repo |
| PyPI publish token | GitHub Actions secret on `forge` repo | Any committed file |
| Vercel deploy token | Vercel-managed | — |

### Versioning

- **CLI (`forge`):** SemVer. Major version bumps for breaking YAML schema changes only.
- **Platform (`forge-platform`):** Internal version for SaaS-hosted (continuous deploy). For self-hosted, customers pin to a release version (e.g., `v2024.05`).
- **Web (`forge-web`):** No versioning. Continuous deploy.

### Cross-Repo Coordination

Some changes affect multiple repos:

- **YAML schema change** → CLI version bump → docs update in `forge-web/docs` → if it affects pipeline storage, platform migration needed
- **New feature gated to Business** → CLI adds `@require_business` → platform adds the backend support → web updates pricing page
- **New connector** → CLI adds connector code → docs page added in `forge-web` → integrations grid updated in `forge-web`

Keep a `CHANGELOG.md` in each repo. For cross-repo changes, the CLI changelog references the docs PR and platform release notes. This sounds like overhead but it'll save you when a customer reports a bug spanning two repos.

---

## Pre-Code Setup Checklist

Before you write a single line of code, do this admin work in one half-day session:

- [ ] Buy domain (`forge.dev` or whatever)
- [ ] Create GitHub org
- [ ] Create `forge` repo (public, BUSL license, README placeholder)
- [ ] Create `forge-web` repo (public, README placeholder)
- [ ] Reserve PyPI package name (publish a 0.0.1 placeholder that just prints "coming soon")
- [ ] Reserve npm scope if you might use one later
- [ ] Reserve Docker Hub / GHCR org names
- [ ] Reserve Twitter/X, LinkedIn, BlueSky handles
- [ ] Reserve Discord server name (or Slack workspace)
- [ ] Set up Vercel account, point `forge.dev` at it
- [ ] Set up Mintlify account
- [ ] Set up PostHog or Plausible account for analytics
- [ ] Set up email forwarding for `support@`, `hello@`, `security@`
- [ ] Set up password manager (1Password / Bitwarden) entry for the project
- [ ] Generate the license signing keypair (store private key in 1Password for now; move to proper secret store when platform exists)

**Do not** create `forge-platform` yet. You don't need it. Resist.

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

The CLI README should be technical: install, quick start, link to full docs, link to website. The marketing copy lives at `forge.dev`. Keeping them separate prevents the README from becoming a sales page (which technical buyers find off-putting on GitHub).

### Mistake 6: "I'll make `forge-platform` public to simplify CI"

It's tempting. Don't. The moment you take payments, your platform repo contains code paths that handle billing, license issuance, and customer data. Public visibility creates legal exposure and weakens your moat.

### Mistake 7: "I'll skip the public/private split and use a monorepo"

Monorepos work for unified teams shipping to one customer. They don't work for "free OSS-adjacent CLI + private SaaS platform" because the visibility requirements are *opposite*. You'd either expose platform code or hide CLI code — both are wrong.

---

## When to Re-Evaluate This Architecture

This three-repo structure works for:

- Solo founders to ~10-person teams
- Free OSS-adjacent CLI + paid platform model
- Pre-Series-A through early Series B

You should consider reorganizing when:

- **You add a second paid product.** Might want a fourth repo (`forge-data-quality` etc.) or migrate the platform repo into a monorepo internally.
- **You hire an OSS community team.** Might want to split connectors into their own public repos so community can own them.
- **You IPO or get acquired.** Whoever acquires you will reorganize anyway.

For the first 2 years, this structure is correct. Don't over-engineer.

---

## Critical Path Summary

1. **Phase 0:** Lock license, naming, and secrets management (1 day of admin)
2. **Day 1:** Create `forge` and `forge-web` repos, both public
3. **Weeks 1–4:** Build CLI in `forge`, with license verification baked in from the start
4. **Weeks 3–6:** Build site in `forge-web` in parallel
5. **Week 8:** Launch CLI to PyPI, post to HN, validate demand
6. **Months 3–4:** *If demand is real,* create `forge-platform` (private) and start building the Business web app
7. **Month 6:** Launch Business tier with license issuance flow

Three repos, three jobs, three lifecycles. Keep them clean from day one.

---

*End of architecture plan. This doc is a living standard — update it when the architecture evolves.*
