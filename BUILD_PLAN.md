# Forge — Development Plan

> **Working title:** Forge (find/replace once you pick the real name)
> **What it is:** Free CLI + paid Business platform for data masking and synthetic data generation. Self-hosted. Sanely priced.
> **Origin pitch:** *"We got quoted $40K to mask 3 tables. We built this instead."*
> **Last updated:** [date]

---

## How to Use This Document

- Items tagged **MUST-HAVE** are blockers for v1 launch. Do not skip.
- Items tagged **SHOULD-HAVE** are launch-quality but can be deferred 2–4 weeks if needed.
- Items tagged **NICE-TO-HAVE** are post-launch, month 2+.
- Each section ends with a checklist. Check off as you go.
- Phases are sequential — don't skip ahead. Phase 0 (positioning) is the most-skipped and most-important.

---

## Phase 0 — Positioning & Decisions (Week 0)

You cannot build the site, the CLI UX, or the pricing page without these answers locked. Write them down. Commit them. They will change later, but you need v1 answers now.

### 0.1 Naming (MUST-HAVE)
- [ ] Product name picked
- [ ] Domain bought (`.com` strongly preferred; `.io` and `.dev` acceptable in dev tools)
- [ ] GitHub org created with the name
- [ ] PyPI package name reserved (run `pip search` and check pypi.org — squat the name immediately, even with a placeholder package)
- [ ] Twitter/X handle reserved
- [ ] LinkedIn page reserved

### 0.2 Pricing Locked (MUST-HAVE)
- [ ] CLI tier: $0, free forever
- [ ] Business Trial: 14 days, no credit card, full Business features
- [ ] Business: **$_____/mo flat** (recommended starting range: $499–$1,499/mo, includes up to N seats)
- [ ] Enterprise: Contact sales (no public price)
- [ ] Decided: per-seat caps for Business tier? (recommended: yes, e.g., "up to 25 users included, $X per additional seat")
- [ ] Decided: annual discount? (recommended: 20% off, paid annually)

### 0.3 Feature Gates Defined (MUST-HAVE)
The 3 things that make Business worth paying for:
- [ ] **Web UI** — visual pipeline builder, dashboard, run history
- [ ] **Scheduled runs** — cron, triggers, orchestration
- [ ] **Team features** — audit logs, RBAC, multi-user access
- [ ] (Optional 4th) Hosted runners / managed scheduling
- [ ] (Optional 5th) Premium connectors (Snowflake, Databricks, etc., if you want to gate)

CLI gets *everything else*: all masking transforms, all synthetic generation, all connectors (or most), YAML configs, local runs.

### 0.4 Positioning Statement (MUST-HAVE)
Fill this in. Print it. Tape it to your monitor.

> For **[senior data engineers and data eng managers at mid-market regulated companies]** who **[need to mask production data or generate synthetic data without paying enterprise consulting prices]**, **Forge** is a **[self-hosted data masking and synthetic data platform]** that **[gives you a free CLI to start and a team platform when you're ready]**. Unlike **[Tonic, Delphix, Informatica TDM]** which **[require five-figure quotes and consulting engagements]**, we **[charge a flat monthly fee, run on your infrastructure, and let you start in 5 minutes from the command line]**.

### 0.5 Wedge Use Case (MUST-HAVE)
Pick ONE primary use case for the homepage. The others become solution pages.
- [ ] **Recommended primary:** "Safe dev/test data for engineering teams"
- [ ] Secondary: "Compliance-ready masking for regulated industries"
- [ ] Tertiary: "Synthetic data for AI/ML training"

### 0.6 Top 5 Connectors (MUST-HAVE)
Be excellent at 5, not mediocre at 50. Recommended:
- [ ] PostgreSQL
- [ ] MySQL
- [ ] CSV / Parquet files (local + S3)
- [ ] Snowflake
- [ ] [your 5th — pick based on your existing customers/network]

Everything else is "coming soon" or "request a connector."

---

## Phase 1 — The CLI Tool (Weeks 1–4)

This is your product. The website sells it; the docs explain it; but **the CLI itself is what determines whether you have a business**. Spend disproportionate time here.

### 1.1 Core Architecture (MUST-HAVE)

**Stack recommendation:**
- **Language:** Python 3.10+ (matches your stack, matches data engineering ecosystem)
- **CLI framework:** [Typer](https://typer.tiangolo.com/) (built on Click, modern, type-hinted, autocompletes)
- **Output formatting:** [Rich](https://rich.readthedocs.io/) (the de facto standard for beautiful Python CLI output — tables, progress bars, color, syntax highlighting, all of it)
- **YAML parsing:** PyYAML or ruamel.yaml (ruamel preserves comments — better for round-tripping)
- **Config schema validation:** Pydantic v2 (forces clear errors when YAML is malformed — critical UX)
- **Packaging:** Hatch or Poetry (Hatch is becoming the modern default; Poetry is fine)
- **Distribution:** PyPI primary, with a `curl ... | sh` script as secondary
- **Single-binary build (NICE-TO-HAVE):** PyInstaller or [shiv](https://github.com/linkedin/shiv) for environments without Python

**Why this stack:** Typer + Rich is what every modern Python CLI uses now (e.g., FastAPI's CLI, Modal, Prefect, Dagster, even pip itself uses Rich for output). Your buyer expects this aesthetic.

### 1.2 Command Structure (MUST-HAVE)

Design the command surface *before* writing code. Here's a recommended structure — adjust to your domain:

```
forge --help
forge --version

forge init                          # scaffold a new project (creates forge.yaml)
forge demo                          # run a bundled end-to-end demo with sample data
forge validate <file.yaml>          # validate a pipeline YAML without running
forge run <file.yaml>               # execute a masking/generation pipeline
forge run <file.yaml> --dry-run     # show what would happen without executing
forge connectors list               # list available source/destination connectors
forge connectors test <name>        # test a connector's connection
forge transforms list               # list available masking transforms
forge generate schema <source>      # introspect a source and generate a starter YAML
forge schema validate <file.yaml>   # validate just the schema portion
forge upgrade                       # check for and install updates
forge login                         # (Business tier) authenticate to web UI
forge push <file.yaml>              # (Business tier) push pipeline to web UI
```

The `forge generate schema <source>` command is huge — it removes the blank-page problem. Run it against a Postgres DB, get a starter YAML with all tables/columns and a suggested mask for each PII-looking field. **This single command might be your biggest "wow" moment.**

### 1.3 CLI UX Standards (MUST-HAVE)

These are the things that separate an "okay" CLI from a *loved* one. Most are 1–2 hours of work each. Skip none.

- [ ] **Color is intentional.** Errors red, warnings yellow, success green, info dim. Use Rich's theme system. Don't over-color.
- [ ] **Detect non-TTY environments and disable color** (CI logs, pipes). Rich does this automatically — verify it.
- [ ] **Respect `NO_COLOR` env variable.** [no-color.org](https://no-color.org/) — accessibility and convention.
- [ ] **Show progress for any operation > 2 seconds.** Spinners for indeterminate, progress bars for known totals. Rich has both.
- [ ] **Every error message has 3 parts:** what went wrong, why, what to do next. Example:

  ```
  ✗ Connection to Postgres failed.

    Reason: Authentication failed for user 'forge'.
    Fix:    Check that POSTGRES_PASSWORD is set in your environment,
            or update the password in forge.yaml line 12.

    Run `forge connectors test postgres-prod` to retry.
  ```

- [ ] **YAML errors point to the exact line and column.** Pydantic v2 + a custom error formatter. Never just dump a stack trace.
- [ ] **First-run experience.** When someone runs `forge` with no args, show a friendly welcome with the 3 most common next commands. Not a full help dump.
- [ ] **`forge --version` is verbose by default.** Show version, Python version, install location, and "✓ latest" or "→ update available."
- [ ] **Update check runs in background once per day.** If a new version exists, show a one-line note at the bottom of any command output. Never block.
- [ ] **`forge demo` works in 30 seconds.** Bundled SQLite or CSV data, runs a real masking pipeline, outputs to a local file. This is the "hello world" that decides if someone keeps using your tool.
- [ ] **Output is parseable when piped.** `forge connectors list --format json` for scripting.
- [ ] **Quiet mode.** `--quiet` flag suppresses all non-essential output. `-v`, `-vv`, `-vvv` for increasing verbosity.
- [ ] **Help text is well-written.** Read every `--help` output as if you were a new user. Rewrite anything that's terse or jargon-heavy.
- [ ] **Tab completion.** Typer supports this via `forge --install-completion`. Document it.

### 1.4 YAML Pipeline Format (MUST-HAVE)

Design this carefully — your YAML schema is part of your public API. Breaking changes hurt.

Example shape (riff and adjust):

```yaml
# forge.yaml
version: 1

source:
  type: postgres
  connection: ${POSTGRES_URL}    # env var interpolation
  tables:
    - users
    - orders

destination:
  type: postgres
  connection: ${POSTGRES_DEST_URL}
  mode: replace                  # replace | append | upsert

masks:
  - table: users
    column: email
    transform: faker.email
    preserve_uniqueness: true

  - table: users
    column: ssn
    transform: format_preserving_encryption
    seed: ${MASK_SEED}

  - table: users
    column: dob
    transform: date_shift
    range_days: 30

referential_integrity:
  - parent: users.id
    children:
      - orders.user_id

options:
  parallelism: 4
  on_error: fail                 # fail | skip | log
```

**MUST-HAVE design principles:**
- [ ] Versioned schema (`version: 1`) so you can evolve without breaking
- [ ] Environment variable interpolation (`${VAR}`) for secrets — never hardcode
- [ ] Sensible defaults so simple cases stay simple
- [ ] Validation errors that point to the exact YAML line
- [ ] Schema documented in `/docs/yaml-reference` with every field

### 1.5 Masking Transform Library (MUST-HAVE)

Ship with a strong default library. These are table stakes:

- [ ] **Faker-based:** name, email, phone, address, company, IP, credit card
- [ ] **Format-preserving encryption** (FPE) — keeps format but encrypts value, deterministic with a seed
- [ ] **Hashing** — SHA256 with optional salt
- [ ] **Redaction** — replace with a fixed string or pattern
- [ ] **Date shift** — move dates by a random amount within a range, preserving relative order
- [ ] **Numeric jitter** — add noise to numbers within a range
- [ ] **Categorical shuffle** — shuffle values within a column (preserves distribution)
- [ ] **Null** — replace with NULL
- [ ] **Conditional masking** — mask only when a condition is met
- [ ] **Custom Python function** — escape hatch for users to write their own

### 1.6 Synthetic Data Generation (MUST-HAVE)

- [ ] **Schema introspection** — point at a DB or file, get a schema model
- [ ] **Statistical fidelity options:** simple (Faker-based per column) and advanced (preserve distributions, correlations)
- [ ] **Volume control** — "generate N rows" or "match source row count" or "10x source"
- [ ] **Referential integrity preservation** across generated tables
- [ ] **Constraint awareness** — respect NOT NULL, UNIQUE, CHECK constraints

### 1.7 Connectors (MUST-HAVE for top 5)

Each connector needs:
- [ ] Read support
- [ ] Write support
- [ ] Connection test command
- [ ] Schema introspection
- [ ] Streaming for large tables (don't load everything into memory)
- [ ] Documented YAML config
- [ ] Docs page with examples

### 1.8 CLI Polish (SHOULD-HAVE)

- [ ] **`forge init` is interactive.** Prompts for source type, destination, asks if you want a sample masks block. Outputs a working starter YAML.
- [ ] **Diff mode.** `forge run --diff` shows before/after for a sample of rows without writing.
- [ ] **Profile output.** `--profile` shows time spent per stage. Good for performance debugging and good for marketing screenshots.
- [ ] **Telemetry (opt-in).** Anonymous usage stats so you know what features are used. Make it dead-easy to opt out. Document it transparently.
- [ ] **Logo/banner on `forge --help`.** ASCII art. Yes, really. Practitioners notice.

### 1.9 CLI Distribution (MUST-HAVE)

- [ ] PyPI release pipeline (GitHub Actions → PyPI)
- [ ] Versioning scheme picked (recommend [Semantic Versioning](https://semver.org/))
- [ ] CHANGELOG.md format picked (recommend [Keep a Changelog](https://keepachangelog.com/))
- [ ] `curl -fsSL install.forge.dev | sh` script hosted (it should `pip install` under the hood)
- [ ] Install verification: after install, `forge --version` works on Mac, Linux, Windows
- [ ] Tested on Python 3.10, 3.11, 3.12, 3.13

### 1.10 CLI Testing (MUST-HAVE)

- [ ] Unit tests for every transform
- [ ] Integration tests for every connector (use Testcontainers for DBs)
- [ ] E2E test: `forge demo` runs cleanly on every supported Python version, every supported OS
- [ ] CI matrix: Python 3.10–3.13 × Mac/Linux/Windows

---

## Phase 2 — Documentation (Weeks 3–5, parallel with CLI)

### 2.1 Mintlify Setup (MUST-HAVE)
- [ ] Mintlify account, fork starter template
- [ ] Theme matches site brand (color, font, logo)
- [ ] Deployed at `forge.dev/docs` via Vercel rewrite (keep on apex domain)
- [ ] Search works
- [ ] Dark mode default

### 2.2 Docs Information Architecture (MUST-HAVE)

```
Getting Started
├── Install
├── Your first masking pipeline (5 min)
├── Your first synthetic dataset (5 min)
└── Concepts overview

Concepts
├── How masking works
├── How synthetic generation works
├── Pipeline anatomy
├── Referential integrity
└── Determinism & reproducibility

CLI Reference
├── Global flags
├── forge init
├── forge run
├── ... (every command)

YAML Reference
├── Schema overview
├── Sources
├── Destinations
├── Masks
├── Generators
└── Options

Connectors
├── PostgreSQL
├── MySQL
├── CSV / Parquet
├── S3
├── Snowflake
└── (one page each)

Transforms
├── Faker-based
├── FPE
├── Hashing
├── Date shift
├── ... (one page each, with YAML examples)

Recipes (HIGH SEO VALUE)
├── Mask a Postgres table preserving referential integrity
├── Generate 1M synthetic rows from a schema
├── Mask CSVs in an S3 bucket
├── Sync a masked subset of prod to staging
├── Generate test data for a multi-table schema
└── (10–20 of these — invest here)

Business Tier
├── Web UI overview
├── Scheduling pipelines
├── Audit logs
├── RBAC
└── Migrating from CLI to Business

Self-Hosting
├── Deployment options
├── Docker
├── Kubernetes
├── AWS / Azure / GCP
└── System requirements

Security
├── Data handling
├── Encryption
├── Compliance
└── Reporting issues
```

### 2.3 Docs Quality Bar (MUST-HAVE)
- [ ] Every page has a "what you'll learn" intro and a "next steps" outro
- [ ] Every code block is copy-pasteable and tested (literally run them)
- [ ] No "TODO" or "Coming soon" pages — either ship the page or hide the link
- [ ] Search-optimized titles (people search "postgres data masking python," not "PG mask")
- [ ] Every connector page follows the same template
- [ ] Every transform page follows the same template

### 2.4 Recipes (SHOULD-HAVE for launch, MUST-HAVE within month 2)
- [ ] Write 5 recipes for launch
- [ ] Write 5 more in month 2
- [ ] Write 10 more in month 3 (target: 20 total)

---

## Phase 3 — Marketing Site (Weeks 4–6)

### 3.1 v0 Generation (MUST-HAVE)
- [ ] v0 account, paid tier
- [ ] Initial generation using the prompt in Appendix A
- [ ] Iterate to 80% in v0
- [ ] Export to GitHub
- [ ] Clone to local VS Code

### 3.2 Customization (MUST-HAVE)
- [ ] Real copy in every section (no lorem ipsum)
- [ ] Origin story written and placed on homepage
- [ ] Install command (`pip install forge`) prominent in hero
- [ ] Animated terminal/code section showing CLI usage
- [ ] Feature blocks: Masking, Synthetic Data, Transforms, Analytics
- [ ] Comparison table: Forge vs. Tonic / Delphix / Informatica
- [ ] Public pricing page with 3 tiers
- [ ] Customer logo placeholders ready to swap when you have logos
- [ ] Final CTA repeating install command

### 3.3 Pages Required (MUST-HAVE)
- [ ] `/` (home)
- [ ] `/product/masking`
- [ ] `/product/synthetic-data`
- [ ] `/product/transforms`
- [ ] `/product/analytics`
- [ ] `/pricing`
- [ ] `/security`
- [ ] `/self-hosting`
- [ ] `/about` (with your full origin story)
- [ ] `/blog` (index, even if empty at launch)
- [ ] `/changelog`
- [ ] Legal: `/privacy`, `/terms`

### 3.4 Pages Required (SHOULD-HAVE)
- [ ] `/compare/tonic`
- [ ] `/compare/delphix`
- [ ] `/compare/informatica`
- [ ] `/solutions/dev-test-data`
- [ ] `/solutions/compliance`
- [ ] `/solutions/ai-training`

### 3.5 SEO Foundations (MUST-HAVE)
- [ ] Sitemap.xml generated and submitted to Google Search Console
- [ ] Robots.txt
- [ ] OG images on every page (v0 handles most of this, verify)
- [ ] Meta titles and descriptions on every page (manual review, don't trust v0 defaults)
- [ ] Schema.org markup for SoftwareApplication
- [ ] Page speed: 90+ on Lighthouse mobile

### 3.6 Analytics & Tracking (MUST-HAVE)
- [ ] Plausible or PostHog installed
- [ ] Conversion events defined: install command copy, trial signup click, GitHub click, docs click
- [ ] Goals tracked in analytics

### 3.7 Hosting & Deployment (MUST-HAVE)
- [ ] Deployed on Vercel
- [ ] Custom domain pointed
- [ ] HTTPS enforced
- [ ] `/docs` rewrite to Mintlify configured
- [ ] Preview deploys on every PR

---

## Phase 4 — Business Tier Web App (Weeks 6–12)

This is post-CLI-launch. **Do not build this before the CLI ships.** Validate demand with the CLI first.

### 4.1 Stack (DECIDE BEFORE BUILDING)
- [ ] **Backend:** FastAPI (matches Python ecosystem) or Django (more batteries-included)
- [ ] **Frontend:** Next.js + shadcn/ui (matches v0 site, easy to share components)
- [ ] **DB:** Postgres (your customers will run this — don't pick something exotic)
- [ ] **Auth:** Clerk or Auth.js (don't roll your own auth)
- [ ] **Job runner:** Celery + Redis, or Prefect, or Dagster
- [ ] **Deployment for SaaS-hosted version:** Render, Fly.io, or AWS
- [ ] **Self-hosted distribution:** Docker Compose for simple installs, Helm chart for k8s

### 4.2 MVP Features (MUST-HAVE for Business Tier launch)
- [ ] User authentication (signup, login, password reset)
- [ ] Organization/team model with RBAC
- [ ] Pipeline list view (all YAML pipelines pushed from CLI)
- [ ] Pipeline detail view (YAML viewer, run history, logs)
- [ ] Manual run trigger from UI
- [ ] Scheduled runs (cron syntax)
- [ ] Run logs and output viewer
- [ ] Audit log (who did what when)
- [ ] Billing integration (Stripe)
- [ ] Trial countdown UI

### 4.3 Self-Hosted Distribution (MUST-HAVE for Enterprise)
- [ ] Docker Compose file for single-node deployments
- [ ] Helm chart for Kubernetes
- [ ] Documentation: hardware requirements, network requirements, upgrade path
- [ ] License key system (so you can charge for self-hosted Business/Enterprise)

---

## Phase 5 — Support Infrastructure (Week 5+)

### 5.1 Free Tier Support (MUST-HAVE)
- [ ] GitHub Issues enabled with templates (bug, feature request, question)
- [ ] Discord or Slack community server set up
- [ ] CONTRIBUTING.md with guidelines
- [ ] Issue triage SLA defined (e.g., respond within 48 hours during launch)

### 5.2 Paid Tier Support (MUST-HAVE for Business launch)
- [ ] support@forge.dev email
- [ ] Plain or Pylon for ticket management (defer until volume justifies — start with email + Notion)
- [ ] Status page (status.forge.dev) — Statuspage, Instatus, or BetterStack
- [ ] SLA defined for Business tier (e.g., 24-hour response, business days)

### 5.3 Knowledge Base (SHOULD-HAVE)
- [ ] FAQ page in docs
- [ ] Troubleshooting page in docs
- [ ] "Common errors" page with searchable error codes

---

## Phase 6 — Launch (Week 8 for CLI, Week 14 for Business)

### 6.1 Pre-Launch Checklist (MUST-HAVE)
- [ ] Site live on production domain
- [ ] CLI installable from PyPI
- [ ] Docs live and complete for shipping features
- [ ] At least 5 recipes published
- [ ] Origin story polished
- [ ] At least 3 internal team members have run through the install + demo flow blind
- [ ] Analytics confirmed working
- [ ] Monitoring confirmed working

### 6.2 Launch Channels (MUST-HAVE)
- [ ] **Hacker News "Show HN"** post — your single most important launch channel for a dev tool
- [ ] **r/dataengineering** post (read the rules, don't be salesy, lead with the origin story)
- [ ] **Twitter/X launch thread** (with terminal video/GIF)
- [ ] **LinkedIn post** (different angle: aimed at managers/leaders)
- [ ] **Product Hunt** (less critical for dev tools but still worth it)
- [ ] **dev.to** post — tutorial-style, "How I built X with Forge"

### 6.3 Launch Channels (SHOULD-HAVE)
- [ ] Personal email to your network (50–100 people)
- [ ] Outreach to data engineering podcasts (DataEngineering Podcast, etc.) — 30 days ahead
- [ ] Outreach to data eng newsletters (Data Engineering Weekly, SeattleDataGuy, etc.)
- [ ] Reach out to 5 friendly data engineers for early testimonials *before* launch

### 6.4 Launch Day Operations (MUST-HAVE)
- [ ] You're at your desk, fully focused, the whole day
- [ ] Discord/Slack monitored continuously
- [ ] HN post made at the right time (~9am Eastern Tuesday-Thursday is conventional wisdom)
- [ ] Reply to every comment within 30 minutes for the first 6 hours
- [ ] Bug fixes / docs fixes shipped same-day if needed

---

## Phase 7 — Post-Launch (Months 2–6)

### 7.1 Content Engine (SHOULD-HAVE)
- [ ] One blog post per week (alternating: technical deep-dive, customer story, comparison)
- [ ] One new recipe per week
- [ ] Monthly changelog post
- [ ] Engage on Reddit / Twitter / HN for relevant threads (don't spam — be helpful first)

### 7.2 Customer Development (MUST-HAVE)
- [ ] First 10 paid customers — interview each one personally (30 min calls)
- [ ] Every churn — exit interview, document why
- [ ] Every "considered and chose not to buy" — find out why
- [ ] Track NPS quarterly once you have 25+ customers

### 7.3 Compliance (MUST-HAVE for Enterprise sales)
- [ ] SOC 2 Type 1 process started (Vanta, Drata, or Secureframe — month 2)
- [ ] SOC 2 Type 2 (6 months after Type 1)
- [ ] Privacy policy reviewed by lawyer
- [ ] DPA template ready for enterprise customers
- [ ] HIPAA BAA template (if targeting healthcare)

### 7.4 Connector Expansion (NICE-TO-HAVE, demand-driven)
- [ ] Snowflake, Databricks, BigQuery — based on customer asks
- [ ] MongoDB, DynamoDB
- [ ] Kafka, Kinesis (streaming masking is a hot topic)

---

## Appendix A — v0 Prompt for the Marketing Site

> Modern dev-tool marketing site for **Forge**, a free CLI plus paid Business platform for data masking and synthetic data generation. Self-hosted, sanely priced. Buyers are senior data engineers (free CLI) and data engineering managers (Business tier). Reference aesthetic: Supabase, Resend, PostHog, Bun, Linear. Use shadcn/ui, Tailwind, Geist font, dark mode default, single confident accent color (electric blue). Hero must include a copy-pastable install command (`pip install forge`) as the visual centerpiece, with a secondary "Start free Business trial" CTA. Sections required:
>
> 1. Hero with install command and tension headline about test data quality vs compliance risk
> 2. Origin story section: "We got quoted $40K to mask 3 tables. So we built this."
> 3. Animated terminal showing CLI usage (init → run → masked output)
> 4. Four feature blocks: Masking, Synthetic Data, Transforms, Analytics — each with a YAML code example
> 5. "CLI vs Business" comparison table (4–5 rows)
> 6. Integrations grid (Postgres, MySQL, S3, Snowflake, plus 10+ logo placeholders)
> 7. Self-hosting architecture diagram with "Your data never leaves your network" copy
> 8. Public pricing with 3 tiers (CLI Free, Business $X/mo, Enterprise Custom)
> 9. Customer logo placeholders (6 slots)
> 10. FAQ (8 items)
> 11. Final CTA repeating the install command
>
> Sticky top nav with: Product (dropdown), Pricing, Docs, Blog, GitHub icon, "Start trial" button. No "Book a demo" as primary CTA anywhere. Tone: technical, direct, slightly anti-enterprise-pricing. Include a comparison page template at `/compare/[competitor]`.

---

## Appendix B — Naming Hints

If you haven't picked a name yet:
- Short (1–2 syllables ideal)
- Pronounceable on a podcast without spelling
- `.com` or `.dev` available
- Not a verb you'll fight Google for
- Doesn't end in "ly," "ify," or "ai" (oversaturated)
- Avoid "data" prefix (every competitor has it)
- Strong-feeling words work in this category: Forge, Anvil, Mask, Veil, Cipher, Keep, Vault, Shroud, Cipher, Glass, Mirror, Mock, Echo, Render, Shape

---

## Appendix C — Key Metrics to Track from Day 1

- **Top of funnel:** site visitors, install command copies, GitHub stars, docs page views
- **Activation:** PyPI downloads, `forge demo` runs (telemetry, opt-in)
- **Conversion:** Business trial signups, trial → paid conversion rate
- **Retention:** monthly active CLI users (telemetry), monthly logins to Business UI
- **Revenue:** MRR, ARR, ARPU, expansion revenue, churn rate
- **Community:** Discord/Slack members, GitHub issues opened, PRs merged

---

## Critical Path Summary

If you only do these things, in this order, you'll have a viable launch:

1. **Lock pricing, name, positioning** (Phase 0) — 1 week
2. **Build the CLI to MUST-HAVE quality** (Phase 1) — 4 weeks
3. **Write Getting Started + 5 connector pages + 5 recipes in Mintlify** (Phase 2) — 2 weeks (parallel)
4. **Generate site in v0, customize, deploy** (Phase 3) — 2 weeks (parallel)
5. **Launch the CLI on HN/Reddit/Twitter** (Phase 6) — 1 day
6. **Talk to every user, fix what's broken** (Phase 7) — ongoing
7. **Build the Business web app** (Phase 4) — 6 weeks, AFTER you've validated CLI demand

**Total time to CLI launch: ~8 weeks of focused solo work.** Faster with a co-founder. Slower if you don't lock Phase 0.

---

## What Could Kill This

Risks I'd actively manage:

- **Building the Business web app before validating CLI demand.** This is the #1 way to waste 3 months. CLI first, always.
- **Free tier too generous.** If the CLI does literally everything, no one upgrades. Gate scheduling, the web UI, and team features.
- **Free tier too stingy.** If the CLI is obviously crippled, no one adopts. Single-engineer, single-machine workflows must be fully functional and unlimited.
- **Pricing too low.** $99/mo positions you as a toy. $499–$1,499/mo positions you as a serious tool that's still 10–40x cheaper than Tonic.
- **Trying to support too many connectors at launch.** 5 excellent connectors > 30 mediocre ones. Mediocre connectors create support burden.
- **Skipping the origin story.** It's your best marketing asset and it's free to write.
- **No SOC 2.** Enterprise will not buy without it. Start the process in month 2, not month 12.

---

*End of plan. Treat this as a living doc — update it as you learn.*
