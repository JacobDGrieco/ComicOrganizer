# Coverage Audit

Research cutoff: 2026-07-31

Sources:
- Stored `comic_runs.marvel_url` and `comic_runs.marvel_issue_count` values from official Marvel research.
- Marvel Fandom issue-list pages when `--fandom` is enabled.
- Marvel metadata series index discovery when `--discover-marvel-series` is enabled.

## Summary

- `P0`: 46 runs, 2158 issue rows, 2224 stored Marvel-count issues.
- `P1`: 151 runs, 1176 issue rows, 1180 stored Marvel-count issues.
- `P2`: 60 runs, 424 issue rows, 428 stored Marvel-count issues.
- `P3`: 44 runs, 76 issue rows, 76 stored Marvel-count issues.

## Stored Marvel Count Gaps

- `P0` `CAND-000011` Peter Parker, the Spectacular Spider-Man vol. 1 (1976-1998) [Ongoing]: DB 206 vs Marvel 263 (delta -57)
- `P0` `CAND-000025` Sensational Spider-Man vol. 1 (1996-1998) [Ongoing]: DB 35 vs Marvel 33 (delta +2)
- `P0` `CAND-000010` Spectacular Spider-Man vol. 1 (1968) [Magazine]: DB 2 vs Marvel 3 (delta -1)
- `P0` `CAND-000023` Spider-Man Unlimited vol. 1 (1993-1998) [Ongoing]: DB 22 vs Marvel 10 (delta +12)
- `P0` `CAND-000007` The Amazing Spider-Man vol. 5 (2018-2022) [Ongoing]: DB 106 vs Marvel 105 (delta +1)
- `P0` `CAND-000019` Web of Spider-Man Annual vol. 1 (1985-1994) [Annual]: DB 10 vs Marvel 8 (delta +2)
- `P0` `CAND-000115` Amazing Spider-Man: Spider-Versity vol. 1 (2026-) [Limited Series]: DB 4 vs Marvel 5 (delta -1)
- `P0` `CAND-000050` Ultimate Spider-Man vol. 2 (2024-) [Ongoing]: DB 24 vs Marvel 48 (delta -24)
- `P1` `CAND-000144` Black Cat vol. 3 (2025-) [Ongoing]: DB 12 vs Marvel 13 (delta -1)
- `P1` `CAND-000191` Giant-Size Spider-Man vol. 1 (1974-1975) [Giant-Size]: DB 6 vs Marvel 5 (delta +1)
- `P1` `CAND-000032` Untold Tales of Spider-Man vol. 1 (1995-1997) [Ongoing]: DB 26 vs Marvel 25 (delta +1)
- `P1` `CAND-000135` Queen in Black vol. 1 (2026-) [Event]: DB 1 vs Marvel 5 (delta -4)
- `P1` `CAND-000132` Venom vol. 6 (2025-) [Ongoing]: DB 10 vs Marvel 11 (delta -1)
- `P2` `CAND-000137` Godzilla Conquers the Multiverse vol. 1 (2026-) [Limited Series]: DB 1 vs Marvel 5 (delta -4)

## Annual/Special/Giant/Event Watchlist

- `P0` `CAND-000001` Amazing Fantasy vol. 1 (1962) [Anthology]: DB 1 / Marvel 1
- `P0` `CAND-000003` Amazing Spider-Man Annual vol. 1 (1964-1996) [Annual]: DB 29 / Marvel 29
- `P0` `CAND-000300` Amazing Spider-Man Annual vol. 3 (2014) [annual]: DB 1 / Marvel 1
- `P0` `CAND-000301` Amazing Spider-Man Annual vol. 4 (2016-2018) [annual]: DB 2 / Marvel 2
- `P0` `CAND-000302` Amazing Spider-Man Annual vol. 5 (2018-2021) [annual]: DB 2 / Marvel 2
- `P0` `CAND-000303` Amazing Spider-Man Annual vol. 6 (2023) [annual]: DB 1 / Marvel 1
- `P0` `CAND-000304` Amazing Spider-Man Annual vol. 8 (2026) [annual]: DB 1 / Marvel 1
- `P0` `CAND-000012` Peter Parker, the Spectacular Spider-Man Annual vol. 1 (1979-1994) [Annual]: DB 11 / Marvel 11
- `P0` `CAND-000023` Spider-Man Unlimited vol. 1 (1993-1998) [Ongoing]: DB 22 / Marvel 10
- `P0` `CAND-000019` Web of Spider-Man Annual vol. 1 (1985-1994) [Annual]: DB 10 / Marvel 8
- `P0` `CAND-000116` Amazing Spider-Man/Venom: Death Spiral vol. 1 (2026) [One-Shot]: DB 1 / Marvel 1
- `P0` `CAND-000117` Amazing Spider-Man/Venom: Death Spiral - Body Count vol. 1 (2026) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000162` What If...? Dark: Spider-Gwen vol. 1 (2023) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000163` What If...? Galactus: Galactus Transformed Spider-Gwen? vol. 1 (2025-) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000119` What If...? Spider-Man vol. 1 (2026-) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000156` What If? Spider-Man vol. 1 (2018) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000158` What If? Spider-Man The Other vol. 1 (2006) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000159` What If? Spider-Man: Back in Black vol. 1 (2008) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000161` What If? Spider-Man: Grim Hunt vol. 1 (2010) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000160` What If? Spider-Man: House of M vol. 1 (2009) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000153` Mary Jane & Black Cat: Beyond vol. 1 (2022) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000191` Giant-Size Spider-Man vol. 1 (1974-1975) [Giant-Size]: DB 6 / Marvel 5
- `P1` `CAND-000016` Peter Parker: The Spectacular Spider-Man Annual vol. 2 (2018) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000027` Sensational Spider-Man Annual vol. 1 (2007) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000014` Spectacular Spider-Man vol. 3 (2011) [Special]: DB 1 / Marvel 1
- `P1` `CAND-000031` Spider-Man's Tangled Web vol. 1 (2001-2003) [Anthology]: DB 22 / Marvel 22
- `P1` `CAND-000017` The Spectacular Spider-Man Super Special vol. 1 (1995) [Special]: DB 1 / Marvel 1
- `P1` `CAND-000020` Web of Spider-Man vol. 2 (2009-2010) [Anthology]: DB 12 / Marvel 12
- `P1` `CAND-000021` Web of Spider-Man vol. 3 (2024) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000130` Web of Spider-Verse: New Blood vol. 1 (2025) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000131` Web of Venomverse: Fresh Brains vol. 1 (2025) [One-Shot]: DB 1 / Marvel 1
- `P1` `CAND-000127` Miles Morales: Spider-Man - Brooklyn's Finest Infinity Comic vol. 1 (2026-) [Infinity Comic]: DB 20 / Marvel 20
- `P1` `CAND-000048` Miles Morales: Spider-Man Annual vol. 1 (2021) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000049` Miles Morales: Spider-Man Annual vol. 2 (2024-) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000053` Spider-Gwen Annual vol. 1 (2016) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000124` Spider-Gwen Annual vol. 1 (2023) [Annual]: DB 1 / Marvel 1
- `P1` `CAND-000133` Web of Venom vol. 1 (2026-) [One-Shot]: DB 1 / Marvel 1
- `P2` `CAND-000192` Godzilla Vs. Spider-Man vol. 1 (2025) [One-Shot]: DB 1 / Marvel 1
- `P2` `CAND-000164` Marvel & Disney: What If...? Goofy Became Spider-Man vol. 1 (2025-) [One-Shot]: DB 1 / Marvel 1
- `P2` `CAND-000138` Marvel/DC: Spider-Man/Superman vol. 1 (2026) [One-Shot]: DB 1 / Marvel 1
- `P2` `CAND-000141` Black Cat Annual vol. 1 (2019) [Annual]: DB 1 / Marvel 1
- `P2` `CAND-000143` Black Cat Annual vol. 2 (2021) [Annual]: DB 1 / Marvel 1
- `P2` `CAND-000205` Spider-Man/Punisher: Family Plot vol. 1 (1996) [Limited Series]: DB 2 / Marvel 2
- `P2` `CAND-000139` Spider-Man: Meals to Astonish vol. 1 (2025-) [One-Shot]: DB 1 / Marvel 1
- `P2` `CAND-000251` Amazing Spider-Man Family vol. 1 (2008-2009) [Limited Series]: DB 8 / Marvel 8
- `P2` `CAND-000136` Symbie Infinity Comic vol. 1 (2026-) [Infinity Comic]: DB 6 / Marvel 6
- `P3` `CAND-000254` Amazing Spider-Man: Cinematic Infinite Comic vol. 1 (2014) [Digital Comic]: DB 1 / Marvel 1
- `P3` `CAND-000252` Amazing Spider-Man Special vol. 1 (2015) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000253` Amazing Spider-Man Super Special vol. 1 (1995) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000255` Amazing Spider-Man: Ends of the Earth vol. 1 (2012) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000256` Amazing Spider-Man: Family Business vol. 1 (2013-2014) [Graphic Novel]: DB 1 / Marvel 1
- `P3` `CAND-000257` Amazing Spider-Man: Full Circle vol. 1 (2019) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000258` Amazing Spider-Man: Gang War First Strike vol. 1 (2023) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000259` Amazing Spider-Man: Going Big vol. 1 (2019) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000261` Amazing Spider-Man: Infested vol. 1 (2011) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000262` Amazing Spider-Man: Sins Rising Prelude vol. 1 (2020) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000265` Amazing Spider-Man: The Sins of Norman Osborn vol. 1 (2020) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000269` Amazing Spider-Man: Wakanda Forever vol. 1 (2018) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000280` Dark Reign - The List: Amazing Spider-Man One-Shot vol. 1 (2009) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000281` Giant-Size Amazing Spider-Man: Chameleon Conspiracy vol. 1 (2021) [Giant-Size]: DB 1 / Marvel 1
- `P3` `CAND-000282` Giant-Size Amazing Spider-Man: King's Ransom vol. 1 (2021) [Giant-Size]: DB 1 / Marvel 1
- `P3` `CAND-000286` Spider-Man: 101 Ways to End the Clone Saga vol. 1 (1997) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000295` Spider-Man: Curse of the Man-Thing vol. 1 (2021) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000291` Spider-Man: Dead Man's Hand vol. 1 (1997) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000294` Spider-Man: Marvels Snapshots vol. 1 (2020) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000290` Spider-Man: The Osborn Journal vol. 1 (1996) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000287` Spider-Man: The Parker Years vol. 1 (1995) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000288` Spider-Man: The Short Halloween vol. 1 (2009) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000289` Spider-Man: Unforgiven vol. 1 (2023) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000271` The Amazing Spider-Man: Soul Of The Hunter vol. 1 (1992) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000299` The Many Loves of the Amazing Spider-Man vol. 1 (2010) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000296` Spider-Man: Enter the Spider-Verse vol. 1 (2018) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000266` Amazing Spider-Man: Venom 3D vol. 1 (2019) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000267` Amazing Spider-Man: Venom Inc. Alpha vol. 1 (2017) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000268` Amazing Spider-Man: Venom Inc. Omega vol. 1 (2018) [One-Shot]: DB 1 / Marvel 1
- `P3` `CAND-000292` Spider-Man: The Venom Agenda vol. 1 (1998) [One-Shot]: DB 1 / Marvel 1

