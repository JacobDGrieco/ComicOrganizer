# Unresolved Questions

Status: schema phase.

## Open

- Confirm whether `leadCharacterIds` should remain as plain stable string IDs without a dedicated `characters.json` file, or whether a character authority file should be added later.
- Confirm whether `publicationOrder` and `recommendedReadingOrder` should be stored directly on issue records, derived by script, or both.
- Confirm whether the existing organizer should eventually read `data/issues.json` and `data/readingBlocks.json` instead of the simpler `sort_orders/spider-verse.json`.
- Confirm whether legacy workbook rows should be imported into `review.json` as unverified discovery candidates or left outside the JSON source of truth.
- Resolve `REV-000001`: Amazing Fantasy #15 on-sale/published/cover-date treatment.
- Resolve `REV-000002`: The Amazing Spider-Man (1963 series) issue-count conflict between Marvel and GCD.
- Resolve `REV-000003`: later Amazing Spider-Man annual structure after the 1964 #1-#28 series.
- Resolve `REV-000004`: end-date semantics for Amazing Spider-Man (1999 series).
- Resolve `REV-000005`: The Amazing Spider-Man (2018 series) issue-count conflict between Marvel and GCD.
- Resolve `REV-000006`: The Amazing Spider-Man (2022 series) completion status despite Marvel's stale Present label.
- Resolve `REV-000007`: Amazing Fantasy #15 page-count/content page modeling.
- Resolve `REV-000008`: The Amazing Spider-Man #1 on-sale/published/cover-date treatment.
- Resolve `REV-000009`: The Amazing Spider-Man #1 page-count modeling.
- Resolve `REV-000010`: general page-count data model for physical issue, story, and digital page counts.
- Resolve `REV-000011`: The Amazing Spider-Man #2 on-sale/published/cover-date treatment.
- Resolve `REV-000012`: The Amazing Spider-Man #3 on-sale/published/cover-date treatment.

## Resolved

- JSON is the final source of truth.
- No Excel workbook will be produced.
- Research must proceed one category at a time.
