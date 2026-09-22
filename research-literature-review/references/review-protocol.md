# Literature review evidence protocol

## 1. Review question and scope

Record the research topic and question before searching. Scope fields are target task, population/domain when applicable, method family, dataset/domain, publication window, language constraints, and publication-type constraints.

Use `EXPLORATORY` when the search is intended to learn terminology or map a field. Use `SYSTEMATIC` only when databases, dates, queries, filters, deduplication, screening criteria, and coverage limitations are reproducibly recorded. Neither label proves completeness by itself.

## 2. Query strategy and log

Create variants for:

- `EXACT_TERMINOLOGY`
- `SYNONYM`
- `HISTORICAL_TERMINOLOGY`
- `ACRONYM_FULL_NAME`
- `BROADER_METHOD_FAMILY`
- `TASK_SPECIFIC`

Each executed search records the source/database, exact query, date, filters, and result count when the interface supplies one. Browser, web, bibliographic indexes, publisher pages, and future search providers are interchangeable acquisition channels.

## 3. Source hierarchy

1. `PRIMARY_SCHOLARLY_SOURCE`: publisher paper page, DOI record, original arXiv record, DBLP metadata, or official proceedings.
2. `SECONDARY_INDEX`: scholarly search index or literature database used to discover records.
3. `SECONDARY_DISCUSSION`: blog, news item, repository README, or other commentary.

Use secondary sources for discovery and context, but trace paper facts and research conclusions to the paper or official metadata. A secondary discussion alone cannot enter the formal evidence matrix as proof of the reported study result.

## 4. Citation and reading-depth contract

Verify title, authors, year, venue/publication status, and at least one stable identifier or official URL. Use `UNVERIFIED_METADATA` when authoritative confirmation is absent or contradictory.

Reading depth is one of:

- `METADATA_ONLY`
- `ABSTRACT_ONLY`
- `PARTIAL_TEXT`
- `FULL_TEXT`

Record which sections were inspected. Do not infer datasets, baselines, metric definitions, ablations, or detailed results from an abstract when those details are not explicitly present.

Every extracted statement is labeled:

- `AUTHOR_CLAIM`: the authors' interpretation or stated contribution.
- `DIRECT_EVIDENCE`: a directly inspected method, table, figure, result, or limitation.
- `REVIEWER_INFERENCE`: the reviewer's comparison or interpretation.

## 5. Screening and versions

Define inclusion and exclusion criteria before screening. Each record is `INCLUDED`, `EXCLUDED`, `PENDING`, or `DUPLICATE`, with a reason. Outcome direction is never a valid exclusion reason.

Group arXiv, workshop, conference, and journal versions under a shared work identifier. Record `version_relationship`, prefer the formal published version when appropriate, and count one underlying work once unless the versions provide genuinely distinct evidence that is described explicitly.

Classify a paper as `SEMINAL`, `FOUNDATIONAL`, or `RECENT` only when the role is justified in notes. Recency is not a quality score. Preserve important older work even when the main publication window is recent; document why an out-of-window foundational source was retained instead of applying an arbitrary recent-paper quota.

## 6. Matrix schema

The core matrix records:

`paper_id`, `work_id`, `title`, `authors`, `year`, `venue`, `doi`, `url`, `publication_status`, `stable_identifier`, `metadata_status`, `source_tier`, `literature_role`, `research_question`, `proposed_contribution`, `task`, `dataset`, `sample_or_scale`, `method`, `baseline`, `metrics`, `main_results`, `ablations`, `limitations`, `relevance`, `evidence_access`, `screening_status`, `screening_reason`, `version_relationship`, and `notes`.

Empty cells mean not established, not “none.”

## 7. Synthesis and gaps

Synthesis units are themes or research questions, not paper-by-paper summaries. For each theme compare agreement, disagreement, method families, datasets, evaluation protocols, and limitations. Assign `CONSISTENT_EVIDENCE`, `MIXED_EVIDENCE`, or `INSUFFICIENT_EVIDENCE`.

An evidence gap records observed evidence, declared scope, search and access limitations, and confidence. Do not turn “not found in this search” into “never studied.” Claims such as “first,” “no prior work,” or “never studied” require unusually strong, documented systematic coverage and still need carefully bounded wording.

## 8. Blocking risk codes

- `UNVERIFIED_METADATA`
- `INSUFFICIENT_EVIDENCE`
- `DUPLICATE_VERSION`
- `SCREENING_BIAS_RISK`
- `UNSUPPORTED_NOVELTY_CLAIM`
- `SECONDARY_SOURCE_ONLY`
