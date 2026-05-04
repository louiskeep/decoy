# Forge â€” Development Plan

> **Working title:** Forge (find/replace once you pick the real name)
> **What it is:** Free CLI + paid Business platform for data masking and synthetic data generation. Self-hosted. Sanely priced.
> **Origin pitch:** *"We got quoted $40K to mask 3 tables. We built this instead."*
> **Last updated:** [date]

---

## How to Use This Document

- Items tagged **MUST-HAVE** are blockers for v1 launch. Do not skip.
- Items tagged **SHOULD-HAVE** are launch-quality but can be deferred 2â€“4 weeks if needed.
- Items tagged **NICE-TO-HAVE** are post-launch, month 2+.
- Each section ends with a checklist. Check off as you go.
- Phases are sequential â€” don't skip ahead. Phase 0 (positioning) is the most-skipped and most-important.

---

## Phase 0 â€” Positioning & Decisions (Week 0)

You cannot build the site, the CLI UX, or the pricing page without these answers locked. Write them down. Commit them. They will change later, but you need v1 answers now.

### 0.1 Naming (MUST-HAVE)
- [ ] Product name picked
- [ ] Domain bought (`.com` strongly preferred; `.io` and `.dev` acceptable in dev tools)
- [ ] GitHub org created with the name
- [ ] PyPI package name reserved (run `pip search` and check pypi.org â€” squat the name immediately, even with a placeholder package)
- [ ] Twitter/X handle reserved
- [ ] LinkedIn page reserved

### 0.2 Pricing Locked (MUST-HAVE)
- [ ] CLI tier: $0, free forever
- [ ] Business Trial: 14 days, no credit card, full Business features
- [ ] Business: **$_____/mo flat** (recommended starting range: $499â€“$1,499/mo, includes up to N seats)
- [ ] Enterprise: Contact sales (no public price)
- [ ] Decided: per-seat caps for Business tier? (recommended: yes, e.g., "up to 25 users included, $X per additional seat")
- [ ] Decided: annual discount? (recommended: 20% off, paid annually)

### 0.3 Feature Gates Defined (MUST-HAVE)
The 3 things that make Business worth paying for:
- [ ] **Web UI** â€” visual pipeline builder, dashboard, run history
- [ ] **Scheduled runs** â€” cron, triggers, orchestration
- [ ] **Team features** â€” audit logs, RBAC, multi-user access
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
- [ ] [your 5th â€” pick based on your existing customers/network]

Everything else is "coming soon" or "request a connector."

---

## Phase 1 â€” The CLI Tool (Weeks 1â€“4)

This is your product. The website sells it; the docs explain it; but **the CLI itself is what determines whether you have a business**. Spend disproportionate time here.

### 1.1 Core Architecture (MUST-HAVE)

**Stack recommendation:**
- **Language:** Python 3.10+ (matches your stack, matches data engineering ecosystem)
- **CLI framework:** [Typer](https://typer.tiangolo.com/) (built on Click, modern, type-hinted, autocompletes)
- **Output formatting:** [Rich](https://rich.readthedocs.io/) (the de facto standard for beautiful Python CLI output â€” tables, progress bars, color, syntax highlighting, all of it)
- **YAML parsing:** PyYAML or ruamel.yaml (ruamel preserves comments â€” better for round-tripping)
- **Config schema validation:** Pydantic v2 (forces clear errors when YAML is malformed â€” critical UX)
- **Packaging:** Hatch or Poetry (Hatch is becoming the modern default; Poetry is fine)
- **Distribution:** PyPI primary, with a `curl ... | sh` script as secondary
- **Single-binary build (NICE-TO-HAVE):** PyInstaller or [shiv](https://github.com/linkedin/shiv) for environments without Python

**Why this stack:** Typer + Rich is what every modern Python CLI uses now (e.g., FastAPI's CLI, Modal, Prefect, Dagster, even pip itself uses Rich for output). Your buyer expects this aesthetic.

### 1.2 Command Structure (MUST-HAVE)

Design the command surface *before* writing code. Here's a recommended structure â€” adjust to your domain:

```
forge --help
forge --version

decoy init                          # scaffold a new project (creates forge.yaml)
decoy demo                          # run a bundled end-to-end demo with sample data
decoy validate <file.yaml>          # validate a pipeline YAML without running
decoy run <file.yaml>               # execute a masking/generation pipeline
decoy run <file.yaml> --dry-run     # show what would happen without executing
forge connectors list               # list available source/destination connectors
forge connectors test <name>        # test a connector's connection
forge transforms list               # list available masking transforms
forge generate schema <source>      # introspect a source and generate a starter YAML
forge schema validate <file.yaml>   # validate just the schema portion
forge upgrade                       # check for and install updates
decoy login                         # (Business tier) authenticate to web UI
forge push <file.yaml>              # (Business tier) push pipeline to web UI
```

The `decoy generate schema <source>` command is huge â€” it removes the blank-page problem. Run it against a Postgres DB, get a starter YAML with all tables/columns and a suggested mask for each PII-looking field. **This single command might be your biggest "wow" moment.**

### 1.3 CLI UX Standards (MUST-HAVE)

These are the things that separate an "okay" CLI from a *loved* one. Most are 1â€“2 hours of work each. Skip none.

- [ ] **Color is intentional.** Errors red, warnings yellow, success green, info dim. Use Rich's theme system. Don't over-color.
- [ ] **Detect non-TTY environments and disable color** (CI logs, pipes). Rich does this automatically â€” verify it.
- [ ] **Respect `NO_COLOR` env variable.** [no-color.org](https://no-color.org/) â€” accessibility and convention.
- [ ] **Show progress for any operation > 2 seconds.** Spinners for indeterminate, progress bars for known totals. Rich has both.
- [ ] **Every error message has 3 parts:** what went wrong, why, what to do next. Example:

  ```
  âœ— Connection to Postgres failed.

    Reason: Authentication failed for user 'forge'.
    Fix:    Check that POSTGRES_PASSWORD is set in your environment,
            or update the password in forge.yaml line 12.

    Run `decoy connectors test postgres-prod` to retry.
  ```

- [ ] **YAML errors point to the exact line and column.** Pydantic v2 + a custom error formatter. Never just dump a stack trace.
- [ ] **First-run experience.** When someone runs `decoy` with no args, show a friendly welcome with the 3 most common next commands. Not a full help dump.
- [ ] **`decoy --version` is verbose by default.** Show version, Python version, install location, and "âœ“ latest" or "â†’ update available."
- [ ] **Update check runs in background once per day.** If a new version exists, show a one-line note at the bottom of any command output. Never block.
- [ ] **`decoy demo` works in 30 seconds.** Bundled SQLite or CSV data, runs a real masking pipeline, outputs to a local file. This is the "hello world" that decides if someone keeps using your tool.
- [ ] **Output is parseable when piped.** `decoy connectors list --format json` for scripting.
- [ ] **Quiet mode.** `--quiet` flag suppresses all non-essential output. `-v`, `-vv`, `-vvv` for increasing verbosity.
- [ ] **Help text is well-written.** Read every `--help` output as if you were a new user. Rewrite anything that's terse or jargon-heavy.
- [ ] **Tab completion.** Typer supports this via `decoy --install-completion`. Document it.

### 1.4 YAML Pipeline Format (MUST-HAVE)

Design this carefully â€” your YAML schema is part of your public API. Breaking changes hurt.

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
- [ ] Environment variable interpolation (`${VAR}`) for secrets â€” never hardcode
- [ ] Sensible defaults so simple cases stay simple
- [ ] Validation errors that point to the exact YAML line
- [ ] Schema documented in `/docs/yaml-reference` with every field

### 1.5 Masking Transform Library (MUST-HAVE)

Ship with a strong default library. These are table stakes:

- [ ] **Faker-based:** name, email, phone, address, company, IP, credit card
- [ ] **Format-preserving encryption** (FPE) â€” keeps format but encrypts value, deterministic with a seed
- [ ] **Hashing** â€” SHA256 with optional salt
- [ ] **Redaction** â€” replace with a fixed string or pattern
- [ ] **Date shift** â€” move dates by a random amount within a range, preserving relative order
- [ ] **Numeric jitter** â€” add noise to numbers within a range
- [ ] **Categorical shuffle** â€” shuffle values within a column (preserves distribution)
- [ ] **Null** â€” replace with NULL
- [ ] **Conditional masking** â€” mask only when a condition is met
- [ ] **Custom Python function** â€” escape hatch for users to write their own

### 1.6 Synthetic Data Generation (MUST-HAVE)

- [ ] **Schema introspection** â€” point at a DB or file, get a schema model
- [ ] **Statistical fidelity options:** simple (Faker-based per column) and advanced (preserve distributions, correlations)
- [ ] **Volume control** â€” "generate N rows" or "match source row count" or "10x source"
- [ ] **Referential integrity preservation** across generated tables
- [ ] **Constraint awareness** â€” respect NOT NULL, UNIQUE, CHECK constraints

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

- [ ] **`decoy init` is interactive.** Prompts for source type, destination, asks if you want a sample masks block. Outputs a working starter YAML.
- [ ] **Diff mode.** `decoy run --diff` shows before/after for a sample of rows without writing.
- [ ] **Profile output.** `--profile` shows time spent per stage. Good for performance debugging and good for marketing screenshots.
- [ ] **Telemetry (opt-in).** Anonymous usage stats so you know what features are used. Make it dead-easy to opt out. Document it transparently.
- [ ] **Logo/banner on `decoy --help`.** ASCII art. Yes, really. Practitioners notice.

### 1.9 CLI Distribution (MUST-HAVE)

- [ ] PyPI release pipeline (GitHub Actions â†’ PyPI)
- [ ] Versioning scheme picked (recommend [Semantic Versioning](https://semver.org/))
- [ ] CHANGELOG.md format picked (recommend [Keep a Changelog](https://keepachangelog.com/))
- [ ] `curl -fsSL install.forge.dev | sh` script hosted (it should `pip install` under the hood)
- [ ] Install verification: after install, `decoy --version` works on Mac, Linux, Windows
- [ ] Tested on Python 3.10, 3.11, 3.12, 3.13

### 1.10 CLI Testing (MUST-HAVE)

- [ ] Unit tests for every transform
- [ ] Integration tests for every connector (use Testcontainers for DBs)
- [ ] E2E test: `decoy demo` runs cleanly on every supported Python version, every supported OS
- [ ] CI matrix: Python 3.10â€“3.13 Ã— Mac/Linux/Windows

---

## Phase 2 â€” Documentation (Weeks 3â€“5, parallel with CLI)

### 2.1 Mintlify Setup (MUST-HAVE)
- [ ] Mintlify account, fork starter template
- [ ] Theme matches site brand (color, font, logo)
- [ ] Deployed at `decoy.dev/docs` via Vercel rewrite (keep on apex domain)
- [ ] Search works
- [ ] Dark mode default

### 2.2 Docs Information Architecture (MUST-HAVE)

```
Getting Started
â”œâ”€â”€ Install
â”œâ”€â”€ Your first masking pipeline (5 min)
â”œâ”€â”€ Your first synthetic dataset (5 min)
â””â”€â”€ Concepts overview

Concepts
â”œâ”€â”€ How masking works
â”œâ”€â”€ How synthetic generation works
â”œâ”€â”€ Pipeline anatomy
â”œâ”€â”€ Referential integrity
â””â”€â”€ Determinism & reproducibility

CLI Reference
â”œâ”€â”€ Global flags
â”œâ”€â”€ decoy init
â”œâ”€â”€ forge run
â”œâ”€â”€ ... (every command)

YAML Reference
â”œâ”€â”€ Schema overview
â”œâ”€â”€ Sources
â”œâ”€â”€ Destinations
â”œâ”€â”€ Masks
â”œâ”€â”€ Generators
â””â”€â”€ Options

Connectors
â”œâ”€â”€ PostgreSQL
â”œâ”€â”€ MySQL
â”œâ”€â”€ CSV / Parquet
â”œâ”€â”€ S3
â”œâ”€â”€ Snowflake
â””â”€â”€ (one page each)

Transforms
â”œâ”€â”€ Faker-based
â”œâ”€â”€ FPE
â”œâ”€â”€ Hashing
â”œâ”€â”€ Date shift
â”œâ”€â”€ ... (one page each, with YAML examples)

Recipes (HIGH SEO VALUE)
â”œâ”€â”€ Mask a Postgres table preserving referential integrity
â”œâ”€â”€ Generate 1M synthetic rows from a schema
â”œâ”€â”€ Mask CSVs in an S3 bucket
â”œâ”€â”€ Sync a masked subset of prod to staging
â”œâ”€â”€ Generate test data for a multi-table schema
â””â”€â”€ (10â€“20 of these â€” invest here)

Business Tier
â”œâ”€â”€ Web UI overview
â”œâ”€â”€ Scheduling pipelines
â”œâ”€â”€ Audit logs
â”œâ”€â”€ RBAC
â””â”€â”€ Migrating from CLI to Business

Self-Hosting
â”œâ”€â”€ Deployment options
â”œâ”€â”€ Docker
â”œâ”€â”€ Kubernetes
â”œâ”€â”€ AWS / Azure / GCP
â””â”€â”€ System requirements

Security
â”œâ”€â”€ Data handling
â”œâ”€â”€ Encryption
â”œâ”€â”€ Compliance
â””â”€â”€ Reporting issues
```

### 2.3 Docs Quality Bar (MUST-HAVE)
- [ ] Every page has a "what you'll learn" intro and a "next steps" outro
- [ ] Every code block is copy-pasteable and tested (literally run them)
- [ ] No "TODO" or "Coming soon" pages â€” either ship the page or hide the link
- [ ] Search-optimized titles (people search "postgres data masking python," not "PG mask")
- [ ] Every connector page follows the same template
- [ ] Every transform page follows the same template

### 2.4 Recipes (SHOULD-HAVE for launch, MUST-HAVE within month 2)
- [ ] Write 5 recipes for launch
- [ ] Write 5 more in month 2
- [ ] Write 10 more in month 3 (target: 20 total)

---

## Phase 3 â€” Marketing Site (Weeks 4â€“6)

### 3.1 v0 Generation (MUST-HAVE)
- [ ] v0 account, paid tier
- [ ] Initial generation using the prompt in Appendix A
- [ ] Iterate to 80% in v0
- [ ] Export to GitHub
- [ ] Clone to local VS Code

### 3.2 Customization (MUST-HAVE)
- [ ] Real copy in every section (no lorem ipsum)
- [ ] Origin story written and placed on homepage
- [ ] Install command (`pip install decoy`) prominent in hero
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

## Phase 4 â€” Business Tier Web App (Weeks 6â€“12)

This is post-CLI-launch. **Do not build this before the CLI ships.** Validate demand with the CLI first.

### 4.1 Stack (DECIDE BEFORE BUILDING)
- [ ] **Backend:** FastAPI (matches Python ecosystem) or Django (more batteries-included)
- [ ] **Frontend:** Next.js + shadcn/ui (matches v0 site, easy to share components)
- [ ] **DB:** Postgres (your customers will run this â€” don't pick something exotic)
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

## Phase 5 â€” Support Infrastructure (Week 5+)

### 5.1 Free Tier Support (MUST-HAVE)
- [ ] GitHub Issues enabled with templates (bug, feature request, question)
- [ ] Discord or Slack community server set up
- [ ] CONTRIBUTING.md with guidelines
- [ ] Issue triage SLA defined (e.g., respond within 48 hours during launch)

### 5.2 Paid Tier Support (MUST-HAVE for Business launch)
- [ ] support@forge.dev email
- [ ] Plain or Pylon for ticket management (defer until volume justifies â€” start with email + Notion)
- [ ] Status page (status.forge.dev) â€” Statuspage, Instatus, or BetterStack
- [ ] SLA defined for Business tier (e.g., 24-hour response, business days)

### 5.3 Knowledge Base (SHOULD-HAVE)
- [ ] FAQ page in docs
- [ ] Troubleshooting page in docs
- [ ] "Common errors" page with searchable error codes

---

## Phase 6 â€” Launch (Week 8 for CLI, Week 14 for Business)

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
- [ ] **Hacker News "Show HN"** post â€” your single most important launch channel for a dev tool
- [ ] **r/dataengineering** post (read the rules, don't be salesy, lead with the origin story)
- [ ] **Twitter/X launch thread** (with terminal video/GIF)
- [ ] **LinkedIn post** (different angle: aimed at managers/leaders)
- [ ] **Product Hunt** (less critical for dev tools but still worth it)
- [ ] **dev.to** post â€” tutorial-style, "How I built X with Forge"

### 6.3 Launch Channels (SHOULD-HAVE)
- [ ] Personal email to your network (50â€“100 people)
- [ ] Outreach to data engineering podcasts (DataEngineering Podcast, etc.) â€” 30 days ahead
- [ ] Outreach to data eng newsletters (Data Engineering Weekly, SeattleDataGuy, etc.)
- [ ] Reach out to 5 friendly data engineers for early testimonials *before* launch

### 6.4 Launch Day Operations (MUST-HAVE)
- [ ] You're at your desk, fully focused, the whole day
- [ ] Discord/Slack monitored continuously
- [ ] HN post made at the right time (~9am Eastern Tuesday-Thursday is conventional wisdom)
- [ ] Reply to every comment within 30 minutes for the first 6 hours
- [ ] Bug fixes / docs fixes shipped same-day if needed

---

## Phase 7 â€” Post-Launch (Months 2â€“6)

### 7.1 Content Engine (SHOULD-HAVE)
- [ ] One blog post per week (alternating: technical deep-dive, customer story, comparison)
- [ ] One new recipe per week
- [ ] Monthly changelog post
- [ ] Engage on Reddit / Twitter / HN for relevant threads (don't spam â€” be helpful first)

### 7.2 Customer Development (MUST-HAVE)
- [ ] First 10 paid customers â€” interview each one personally (30 min calls)
- [ ] Every churn â€” exit interview, document why
- [ ] Every "considered and chose not to buy" â€” find out why
- [ ] Track NPS quarterly once you have 25+ customers

### 7.3 Compliance (MUST-HAVE for Enterprise sales)
- [ ] SOC 2 Type 1 process started (Vanta, Drata, or Secureframe â€” month 2)
- [ ] SOC 2 Type 2 (6 months after Type 1)
- [ ] Privacy policy reviewed by lawyer
- [ ] DPA template ready for enterprise customers
- [ ] HIPAA BAA template (if targeting healthcare)

### 7.4 Connector Expansion (NICE-TO-HAVE, demand-driven)
- [ ] Snowflake, Databricks, BigQuery â€” based on customer asks
- [ ] MongoDB, DynamoDB
- [ ] Kafka, Kinesis (streaming masking is a hot topic)

---

## Appendix A â€” v0 Prompt for the Marketing Site

> Modern dev-tool marketing site for **Forge**, a free CLI plus paid Business platform for data masking and synthetic data generation. Self-hosted, sanely priced. Buyers are senior data engineers (free CLI) and data engineering managers (Business tier). Reference aesthetic: Supabase, Resend, PostHog, Bun, Linear. Use shadcn/ui, Tailwind, Geist font, dark mode default, single confident accent color (electric blue). Hero must include a copy-pastable install command (`pip install decoy`) as the visual centerpiece, with a secondary "Start free Business trial" CTA. Sections required:
>
> 1. Hero with install command and tension headline about test data quality vs compliance risk
> 2. Origin story section: "We got quoted $40K to mask 3 tables. So we built this."
> 3. Animated terminal showing CLI usage (init â†’ run â†’ masked output)
> 4. Four feature blocks: Masking, Synthetic Data, Transforms, Analytics â€” each with a YAML code example
> 5. "CLI vs Business" comparison table (4â€“5 rows)
> 6. Integrations grid (Postgres, MySQL, S3, Snowflake, plus 10+ logo placeholders)
> 7. Self-hosting architecture diagram with "Your data never leaves your network" copy
> 8. Public pricing with 3 tiers (CLI Free, Business $X/mo, Enterprise Custom)
> 9. Customer logo placeholders (6 slots)
> 10. FAQ (8 items)
> 11. Final CTA repeating the install command
>
> Sticky top nav with: Product (dropdown), Pricing, Docs, Blog, GitHub icon, "Start trial" button. No "Book a demo" as primary CTA anywhere. Tone: technical, direct, slightly anti-enterprise-pricing. Include a comparison page template at `/compare/[competitor]`.

---

## Appendix B â€” Naming Hints

If you haven't picked a name yet:
- Short (1â€“2 syllables ideal)
- Pronounceable on a podcast without spelling
- `.com` or `.dev` available
- Not a verb you'll fight Google for
- Doesn't end in "ly," "ify," or "ai" (oversaturated)
- Avoid "data" prefix (every competitor has it)
- Strong-feeling words work in this category: Forge, Anvil, Mask, Veil, Cipher, Keep, Vault, Shroud, Cipher, Glass, Mirror, Mock, Echo, Render, Shape

---

## Appendix C â€” Key Metrics to Track from Day 1

- **Top of funnel:** site visitors, install command copies, GitHub stars, docs page views
- **Activation:** PyPI downloads, `decoy demo` runs (telemetry, opt-in)
- **Conversion:** Business trial signups, trial â†’ paid conversion rate
- **Retention:** monthly active CLI users (telemetry), monthly logins to Business UI
- **Revenue:** MRR, ARR, ARPU, expansion revenue, churn rate
- **Community:** Discord/Slack members, GitHub issues opened, PRs merged

---

## Critical Path Summary

If you only do these things, in this order, you'll have a viable launch:

1. **Lock pricing, name, positioning** (Phase 0) â€” 1 week
2. **Build the CLI to MUST-HAVE quality** (Phase 1) â€” 4 weeks
3. **Write Getting Started + 5 connector pages + 5 recipes in Mintlify** (Phase 2) â€” 2 weeks (parallel)
4. **Generate site in v0, customize, deploy** (Phase 3) â€” 2 weeks (parallel)
5. **Launch the CLI on HN/Reddit/Twitter** (Phase 6) â€” 1 day
6. **Talk to every user, fix what's broken** (Phase 7) â€” ongoing
7. **Build the Business web app** (Phase 4) â€” 6 weeks, AFTER you've validated CLI demand

**Total time to CLI launch: ~8 weeks of focused solo work.** Faster with a co-founder. Slower if you don't lock Phase 0.

---

## What Could Kill This

Risks I'd actively manage:

- **Building the Business web app before validating CLI demand.** This is the #1 way to waste 3 months. CLI first, always.
- **Free tier too generous.** If the CLI does literally everything, no one upgrades. Gate scheduling, the web UI, and team features.
- **Free tier too stingy.** If the CLI is obviously crippled, no one adopts. Single-engineer, single-machine workflows must be fully functional and unlimited.
- **Pricing too low.** $99/mo positions you as a toy. $499â€“$1,499/mo positions you as a serious tool that's still 10â€“40x cheaper than Tonic.
- **Trying to support too many connectors at launch.** 5 excellent connectors > 30 mediocre ones. Mediocre connectors create support burden.
- **Skipping the origin story.** It's your best marketing asset and it's free to write.
- **No SOC 2.** Enterprise will not buy without it. Start the process in month 2, not month 12.

---

*End of plan. Treat this as a living doc â€” update it as you learn.*
