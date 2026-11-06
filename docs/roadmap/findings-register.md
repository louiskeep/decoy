# Review notes and the findings register

Status: record

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Rule: fixes ride features. A review finding becomes an acceptance criterion only for a wrong-value
bug, a confidentiality bug or an R1 blocker; everything else is listed here with no dispatch order.

**Hardening notes.** 20.1 ML-pack "fail-open" is overstated: `load_with_fallback`
(`profiling/model_pack/loader.py:151-166`) falls back to the regex baseline, untrusted packs need a
verifiable signature before `joblib.load`, and `trusted=True` applies only to the wheel-shipped default
pack, whose digest is self-attested. 12.2 is closed on the full-frame path only.

**After V1.** No login rate limit or lockout and no password policy (F45). CLI `scan` uses
`pd.read_fwf`; divergence from the engine reader is untested (H-1 G5). Native-kernel fallback
telemetry beyond a warning; GCS and S3 conditional writes; SFTP fingerprint pinning; the
data_discovery keyword denylist; multi-process API support.

**Findings register** (from the archived 2026-10-30 reconciliation and its review; "FRAME finding"
means unverified until that item's FRAME):

| Finding | Summary | Home | State |
|---|---|---|---|
| G1 | CLI `resolve_substrate` ImportError | R1-a | CLOSED (CLI #71) |
| G2 | Four engine version truths; CLI `--version` literal | D-4 | engine CLOSED; CLI literal OPEN |
| G3 | No recorded smoke runs; release docs are templates | R1 gate | OPEN |
| G4 | CLI chunked output bypasses `TransactionalSink` | CLI delivery | verified by reading 2026-10-30 |
| G5 | CLI scan parses fixed width with `pd.read_fwf` | H-1 FRAME; after V1 | verified by reading |
| G6 | Plaintext spill under three temp roots | F25, F26 FRAME | UNVERIFIED |
| G7 | Cloud sources read the whole object into RAM | F25 FRAME | UNVERIFIED |
| G8 | Post-mask leak helper fails open | F34 FRAME | UNVERIFIED |
| G9 | CLI token vault cleartext, unauthenticated (11.8) | F09 FRAME; R2 11.8 | UNVERIFIED |
| G10 | License placeholders; per-repo licenses | R1-c | OPEN |
| G11 | Native kernels fall back silently | F29 FRAME (if free) | UNVERIFIED |
| G12 | Engine dependency floors too wide | F10 FRAME; D-4 | UNVERIFIED |
| G13 | Startup DDL beside Alembic in production | F44 platform FRAME | UNVERIFIED |
| G14 | SMTP password in plaintext | F45 criterion; F14 FRAME | verified by reading |
| G15 | No login limit or password policy, cookie without `Secure`, wide CORS | F45 | `Secure` verified; rest UNVERIFIED |
| G16 | Graceful shutdown mismatch in the inline topology | F23 FRAME | UNVERIFIED |
| G17 | Single-process state unenforced | F45 FRAME | UNVERIFIED |
| G18 | Python 3.10 image, no platform lockfile, python-jose | F44 platform; R2 | jose CLOSED (#136); rest OPEN |
| G19 | Security scanning has no local equivalent | R2 AUDIT | OPEN |
| G20 | Local ci-mirror is prose | R1 gate | CLOSED (platform #156) |
| G21 | AUDIT undefined; packets 11 to 20 not on disk | R2 AUDIT | packets CLOSED (#125); definition OPEN |
| G22 | Passport signing key outside the backup set | F33, F14 FRAME | UNVERIFIED |
| G23 | Silent key generation when a key is missing | F14 FRAME | UNVERIFIED |
| G24 | Small platform items (SSO fetch, pool timeouts, body cap, forwarded IPs, `/health`, scheduler package) | F45 FRAME (if free) | UNVERIFIED; scheduler deletion not taken |
| D-row 1 to 2 | F29 engine half and F43 already merged | F29, F43 | CLOSED (#336, CLI #69) |
| D-row 3 | `pk_uniqueness` exists, not catalog-level or OOC safe | F36 | as stated |
| D-row 4 | F23 engine half is NEW | F23 FRAME | UNVERIFIED |
| D-row 5 to 6 | Engine pins disagree; 12.2 likely closed | D-4; notes | CLOSED; full-frame only |
| D-row 7 | Shipped log stale (gap 2026-10-27 to 2026-10-30) | process | OPEN |
| Slice 0 | 14.1 closed (#360); cross-column read handled by `order_work`; 11.1 + 12.3 and 12.1 rows 11, 13; 20.1 overstated | slice 0 | as stated |
