# Implementation status

Section-by-section map from the blueprint (`EAIRN_Blueprint_Detailed.docx`) to this repository, with
what is deliberately not built yet and why.

Legend: **Built** — implemented and covered by tests · **Partial** — the contract and data are in place,
one part deferred · **Roadmap** — specified, scheduled per the blueprint's phase plan.

| § | Blueprint section | Status | Where |
|---|---|---|---|
| 1–3 | Executive summary, business problem, vision | Built | The five design principles are enforced mechanically — see README table |
| 4 | Reference architecture | Built | `docs/architecture.md`; all seven services exist as modules |
| 5 | Assessment pillars | Built | 8 pillars, 53 criteria in `rubric_v2.0.yaml`; 53 registered checks. `/pillars` publishes the rationale, failure modes, cost of omission and references for each, from `pillar_guide_v1.yaml` |
| 6 | Snowflake module | Built | `connectors/snowflake.py` — ACCOUNT_USAGE query catalog, live + fixture modes, one normaliser |
| 7 | Databricks module | Partial | Permission manifest + system-table catalog published; canonical-bundle harvest works today, live driver is P2 |
| 8 | Microsoft Fabric module | Partial | Manifest + Admin/Purview API catalog; bundle harvest today, live driver P2 |
| 9 | BigQuery module | Partial | Manifest + INFORMATION_SCHEMA/Dataplex/lineage catalog; bundle harvest today, live driver P3 |
| 10 | Oracle Exadata module | Partial | Manifest + data-dictionary catalog; bundle harvest today, live driver P4 |
| 11 | Governance tool integrations | Partial | Collibra, Alation, Purview, Atlan, Informatica: manifests + API catalogs + canonical import. Cross-tool consistency checks (`GV-005` classification agreement, `GV-006` glossary liveness, `GV-003` workflow throughput) are built and scored |
| 12 | Data quality tool integrations | Partial | Monte Carlo, Great Expectations, Soda, Ataccama: manifests + API catalogs + canonical import. Coverage / effectiveness / response scoring (`DQ-001`…`DQ-007`) built |
| 13 | Scoring framework | Built | `scoring/engine.py`; rubric-as-data, confidence gating, tier weighting, hard-blocker overrides, snapshot hashing |
| 14 | Agent Readiness Index | Built | `checks/agent.py` (`AG-001`…`AG-007`) + ARI dimensions in the rubric, including compositional entitlement reconciliation |
| 15 | RAG Readiness Index | Built | `checks/rag.py` (`RG-001`…`RG-006`) + RRI dimensions, with the ACL hard blocker |
| 16 | Executive dashboard | Partial | Three role-scoped views per estate with full evidence traceability and cohort definitions displayed; the portal opens on a multi-industry portfolio and each estate has its own page. `/methodology` works the whole calculation through one estate's evidence — provenance, per-pillar arithmetic recomputed and reconciled against the engine, caps, indices, confidence tiers, and every coverage gap classified by kind. PPTX/PDF board-pack export is not built. `/demo` runs a configurable live assessment and `/estates/{id}/actions` carries the architect/steward action plan |
| 17 | Claude Code build plan | Built | Build sequence followed: canonical model + rubric → Snowflake reference connector → scoring engine with golden tests → Portal MVP → remaining connectors + recommendation engine + advisor |
| 18 | Product roadmap | n/a | Phase labels are carried on each connector (`roadmap_phase`) and surfaced in the Portal |
| 19 | Commercialization | n/a | Rubric-as-data and the canonical-bundle import are the two engineering enablers for partner delivery and white-labelled weighting profiles |
| 20 | Sample questionnaire | Built | `questionnaire.py`, `POST /api/questionnaire`; contradictions scored by `GV-009` |

## Non-negotiable engineering constraints (§17)

| Constraint | Status |
|---|---|
| Least-privilege service accounts with a published permission manifest | Built — every connector; rendered at `/connectors` |
| CI kill test asserting connectors cannot write to customer platforms | Built — `tests/test_connector_kill_test.py` |
| No row-data access paths in the default build; optional sampling is a separate, permission-gated package with per-dataset authorisation logging | Built — `SamplingAuthorization` + `POST /api/sampling-authorizations`; the sampling module itself is intentionally absent |
| Every LLM-generated recommendation stores its prompt, evidence citations, confidence and reviewer decision | Built — `Recommendation` and `AdvisorNarrative` rows; everything lands in `draft` |
| Golden-test fixtures asserting byte-identical re-scores | Built — `tests/test_scoring_golden.py` |

## Deliberately not built

- **Board-pack export (PPTX/PDF).** The snapshot API returns everything an exporter needs; the renderer
  is a separate deliverable and would otherwise ship untested against real templates.
- **Live drivers for Databricks / Fabric / BigQuery / Oracle.** Their permission manifests and statement
  catalogs are published and their normalisation path (canonical bundle) is exercised, but a driver
  written against credentials nobody can test is a liability, not a feature. Each raises a clear error
  naming its roadmap phase and the bundle alternative rather than returning an empty estate — an empty
  estate would score as "nothing to see" instead of "not measured".
- **The row-sampling module.** By design: the default build has no code path that can read row data.
- **Continuous monitoring scheduler (P4).** Re-scoring on a schedule needs a job runner; today an
  assessment is triggered by API call, and the trend view already renders multiple snapshots.
- **Anonymised cohort ingestion (P2).** Seed distributions ship with their definitions and cohort sizes;
  contributing a real assessment into the cohort requires the consent and anonymisation pipeline the
  blueprint makes contractual.
