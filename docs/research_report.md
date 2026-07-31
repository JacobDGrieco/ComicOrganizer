# Research Report

Status: Spider-affiliated series shell pass expanded.

Research cutoff: 2026-07-31

## Current State

- SQLite `database.db` is the active source of truth for the research/download queue.
- `comic_runs`, `issues`, and `story_arcs` are the active catalog tables.
- No Excel workbook will be created or maintained.
- Legacy JSON files under `data/` remain transitional/export material only and should not be treated as authoritative.
- First-pass run records have been populated for Amazing Fantasy, core Amazing Spider-Man publication identities, and a broad Marvel-official Spider-affiliated run queue.

## Repository Audit

Existing project files before schema scaffolding included a Python comic organizer, tests, a config file, a sample reading-order JSON file, and an ignored `sort_orders/` folder.

Legacy workbook input exists at `sort_orders/spider-verse.xlsx`. It has three sheets: `Read Me`, `Comic Runs`, and `Issue Release Order`.

Workbook inspection found:

- `Comic Runs`: 198 run rows.
- `Issue Release Order`: 3,757 issue rows.
- Issue rows appear generated from run counts and month ranges, so they are not acceptable as verified issue-level research.

The workbook may be used only as a legacy discovery aid. It is not trusted as final source data.

## Current Counts

- Comic run records: 250
- Issue records: 1,250
- Story arc records: 1,250

## First Category Notes

Created series shell records for:

- Amazing Fantasy in-scope Spider-Man material.
- The Amazing Spider-Man core ongoing volumes from 1963 through the current 2025 series.
- Amazing Spider-Man Annual 1964 series.

Expanded `comic_runs` coverage from Marvel official series pages and the local Marvel-backed research queue for:

- Core Peter Parker titles beyond Amazing Spider-Man, including Spectacular, Web, Friendly Neighborhood, Sensational, Marvel Knights, Tangled Web, Superior, and recent current-era limited series.
- Spider-family and variant-led titles, including Miles Morales, Spider-Gwen / Ghost-Spider, Spider-Man 2099, Scarlet Spider, Silk, Spider-Woman, Spider-Girl, Spider-Boy, Spider-Punk, Spider-Ham, Spider-Man Noir, and Spider-Man: India.
- Spider-centered events and adjacent symbiote lines, including Spider-Verse, Spider-Geddon, Absolute Carnage, Spider-Verse vs. Venomverse, Venom, Carnage, and selected Venomverse/Web of Venom material.
- Black Cat and Mary Jane-affiliated Spider-Man lines, including Black Cat solo series, Amazing Spider-Man Presents: Black Cat, Spider-Man/Black Cat: Evil That Men Do, Mary Jane & Black Cat, Jackpot & Black Cat, Amazing Mary Jane, and Spider-Man Loves Mary Jane.
- Spider-centered What If material, including What If? Spider-Man, What If...? Miles Morales, What If? Spider-Man The Other, What If? Spider-Man: Back in Black, What If? Spider-Man: Grim Hunt, and What If...? Galactus: Galactus Transformed Spider-Gwen?
- Spider-Man limited series around roughly five issues, including Spider-Man '94, Spider-Men, Spider-Men II, Spider-Verse Team-Up, Scarlet Spiders, Spider-Society, Spider-Man & the League of Realms, Spider-Man & the Secret Wars, Spider-Man Fairy Tales, Spider-Man: Blue, Life Story, Reign, Reign 2, Spider's Shadow, Spider-Man 1602, Spider-Man/Doctor Octopus limited series, Symbiote Spider-Man limited series, and Marvel's Spider-Man tie-in limited series.

Created issue, story-arc, and reading-block records for:

- Amazing Fantasy #15.
- The Amazing Spider-Man #1.
- The Amazing Spider-Man #2.
- The Amazing Spider-Man #3.

Most `comic_runs` records intentionally remain run-level records. `marvel_issue_count` stores researched Marvel result counts where the count is sufficiently clear; `issues` rows still need issue-level verification before those counts are treated as final reading-order data.

Several conflicts remain open, including Amazing Fantasy #15 date semantics, early The Amazing Spider-Man date semantics, page-count modeling, The Amazing Spider-Man volume 1 issue-count reconciliation, later annual structure, inconsistent source labels for recent volumes, and bulk-imported run boundaries where Marvel result counts may include collections, variants, or stale present labels.

Wikipedia's `List of Spider-Man comics` has been added as a discovery-only source. It is useful for identifying volume ranges, annuals, and irregular issue numbers, but it is not being used as sole authority for bibliographic facts.

## Next Checkpoint

Continue issue-level research in strict reading/publication order. Resolve base issue lists for the imported series shells before treating `bibliographicIssueCount` as final, starting with high-priority P0/P1 Spider-Man and Spider-family titles.
