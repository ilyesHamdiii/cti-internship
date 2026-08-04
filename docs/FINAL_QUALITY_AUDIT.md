# Final Quality Audit

Date: 2026-07-27

This document describes the current implementation state as a production-style demonstration platform. It is intentionally honest: the system is credible for an internship, portfolio, or technical interview demo, but it is not production-ready for an enterprise SOC without additional durability, security, and operational hardening.

## Executive Summary

The platform demonstrates a complete CTI-to-detection workflow:

```text
MISP Event
  -> CTI normalization
  -> LangGraph workflow
  -> behavior extraction
  -> ATT&CK verification
  -> coverage and telemetry analysis
  -> policy decision
  -> Sigma generation or terminal route
  -> pySigma validation and Splunk compilation
  -> analyst review
  -> request changes / approve / reject
  -> deployment artifact
  -> Detection Catalog publication
```

The strongest parts are the deterministic detection engineering gates, review workflow, pySigma compilation, MISP integration, and the honest fixture/live AI provider split. The weakest parts are native LangGraph checkpoint durability, production security controls, frontend test coverage, and operational observability outside the database.

## Architecture Diagram

```text
               +----------------+
               | Official MISP  |
               | https://:8443  |
               +-------+--------+
                       |
                       | MISP REST API
                       v
+----------+    +------+-------+      +------------+
| Scheduler| -> | Backend API  | <--> | PostgreSQL |
+----------+    +------+-------+      +------------+
                       |
                       | Celery task
                       v
                 +-----+------+
                 |  Worker    |
                 | LangGraph  |
                 +-----+------+
                       |
        +--------------+----------------+
        |                               |
        v                               v
 +------+-------+                +------+------+
 | AI Provider  |                | pySigma     |
 | Fixture/Live |                | Splunk      |
 +--------------+                +-------------+
                       |
                       v
                 +-----+------+
                 | Frontend   |
                 | Review UI  |
                 +------------+
```

## LangGraph Flow

```text
consume_cti
  -> extract_behaviors
  -> verify_attack_mapping
  -> coverage_analysis
  -> visibility_analysis
  -> policy_decision
       -> terminal_covered
       -> terminal_visibility_gap
       -> terminal_insufficient_evidence
       -> generate_candidate
            -> validate_candidate
                 -> queue_review
                 -> repair_candidate
                 -> terminal_failed

Review resume:
approved
  -> deployment
  -> terminal_rejected
  -> repair_candidate
```

## Review Lifecycle

```text
Proposal revision 1
  -> ready_review
  -> analyst approve
      -> deployment artifact
      -> active catalog detection

Proposal revision N
  -> request changes
  -> repair_candidate
  -> validate_candidate
  -> proposal revision N+1

Proposal
  -> reject
  -> terminal rejected
```

## Component Audit

| Component | Purpose | Strengths | Weaknesses | Risk | Confidence |
|---|---|---|---|---|---|
| Docker stack | Local runnable demo with backend, frontend, nginx, Postgres, Redis, Celery, MISP | Official MISP profile, persistent volumes, documented ports | Local secrets and TLS are demo-grade | Medium | High |
| Backend API | Exposes CTI, graph, review, catalog, health, and settings | Clear route coverage, auth gates, enriched workspace payloads | Limited pagination/filtering and limited conflict recovery | Medium | High |
| LangGraph runner | Orchestrates detection engineering workflow | Real conditional routing, node audit records, resume paths | No native persistent LangGraph checkpointer yet | High | Medium |
| AI provider | Fixture/live abstraction for behavior extraction, Sigma generation, repair | Fixture is input-sensitive and honest; live provider has mocked retry tests | Live DeepSeek not proven without credentials | Medium | Medium |
| Semantic repair | Interprets analyst intent before candidate mutation | Blocks ordinary prose copy; supports quoted technical literals and recognized download patterns | Planner is deterministic and intentionally narrow | Medium | High |
| pySigma pipeline | Validates Sigma and compiles Splunk query | Uses real pySigma backend, blocks unsupported logsources/fields | Supports a limited Windows-focused field set | Medium | High |
| ATT&CK verification | Verifies candidate mappings | Checks existence, revoked/deprecated, tactic, platform, evidence, confidence | Uses seeded dataset rather than full upstream ATT&CK bundle | Medium | High |
| Duplicate detection | Identifies duplicate/overlap lifecycle state | Six deterministic statuses with recommended actions | Similarity is lightweight, not a semantic rule engine | Medium | Medium |
| Review workflow | Human gate before deployment | Revision history, request changes, approval, rejection | DB constraints exist, but concurrent conflict UX is still basic | Medium | High |
| Detection Catalog | Stores approved detections | Preserves Sigma, compiled query, lineage, deployment artifact | Version history presentation is still compact | Low | Medium |
| Frontend UX | Analyst-facing demonstration UI | Clearer wording, graph route visibility, review workbench, health cards | No browser screenshots captured in current environment; no frontend tests | Medium | Medium |
| Observability | Audit trail for graph/node/AI decisions | Graph node records, AI metadata, timings, costs, health checks | No centralized structured log aggregation | Medium | Medium |
| Security | Local auth and role checks | JWT auth, seeded admin, protected API routes | Local defaults, no secret manager, no production TLS/OIDC/RBAC depth | High | Medium |

## Scorecard

| Area | Score | Rationale |
|---|---:|---|
| Architecture | 8/10 | Coherent services and workflow boundaries; no major rewrite needed. |
| Backend | 8/10 | Strong deterministic services and API coverage; conflict handling still needs polish. |
| AI | 7/10 | Honest provider split, repair loop, schemas, mocked hardening; live DeepSeek unproven. |
| Detection Engineering | 8/10 | MISP, ATT&CK, telemetry, coverage, pySigma, review, catalog all represented credibly. |
| UX | 7/10 | Much clearer analyst flow; still needs visual screenshot QA and more detail-page refinement. |
| Frontend | 7/10 | Builds successfully and exposes engine state; lacks automated UI tests. |
| Observability | 6/10 | Good database audit trail; missing centralized logs/traces/metrics. |
| Documentation | 7/10 | Core docs exist and this audit explains tradeoffs; screenshots still missing. |
| Testing | 7/10 | Backend tests cover core services; missing worker-restart and browser tests. |
| Maintainability | 7/10 | Small service boundaries; migrations need long-term cleanup discipline. |
| Security | 5/10 | Appropriate for local demo, not enterprise deployment. |
| Production readiness | 5/10 | Demo-ready, not SOC-production-ready. |

## Would I Merge This Into Production?

No, not yet.

I would merge it into an internal demo, internship showcase, or prototype branch. I would not merge it into a production SOC environment until the blockers below are resolved.

## Production Blockers

- Add native LangGraph checkpoint persistence or a formally documented equivalent with restart tests.
- Add worker-restart, duplicate-delivery, and concurrent-review integration tests.
- Replace local seeded credentials with production identity controls.
- Add centralized structured logging and correlation IDs across API, Celery, graph, MISP polling, and deployment.
- Replace local TLS exceptions and demo secrets with managed production secrets and certificate handling.
- Expand ATT&CK data management to a versioned upstream dataset.
- Add frontend integration tests and screenshot regression checks.
- Add production monitoring for scheduler freshness, worker liveness, queue depth, and MISP poll success.

## Known Demo Limitations

- Fixture mode is deterministic by design and must not be described as live AI.
- Live DeepSeek execution is only valid when `CTI_AI_FIXTURE_MODE=false`, `CTI_DEEPSEEK_API_KEY` is set, and live tests are explicitly enabled.
- pySigma support is focused on Windows process-style detections and Splunk output.
- Duplicate detection is deterministic and useful for demo review, but not equivalent to deep semantic rule equivalence.
- Screenshots were not captured in the current Codex browser environment because the browser connector reported no available browser.

## Current Demo Narrative

1. Open the landing page and explain the workflow.
2. Log in with the seeded local admin.
3. Open System Health and confirm MISP, pySigma, database, Redis, and provider mode.
4. Open Threat Queue and ingest or inspect MISP-backed CTI.
5. Open Workflow Graph and explain conditional routing.
6. Open Review Queue and inspect behavior evidence, ATT&CK mapping, Sigma YAML, compiled SPL, duplicate analysis, and repair history.
7. Request changes with a technical instruction and show a new revision.
8. Approve a validated proposal and show the deployment artifact and Detection Catalog entry.

