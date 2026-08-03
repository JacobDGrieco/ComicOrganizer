# Project Profiles

Create one folder per reading project:

```text
projects/
  spider-man/
    config.json
    database/
      database.db
    character-lists/
      Spider-Man.md
    downloader/
      urls.csv
      downloads/
    logs/
  x-men/
    config.json
    database/
      database.db
    character-lists/
      X-Men.md
    downloader/
      urls.csv
      downloads/
    logs/
```

Inside a project config, relative paths are resolved next to that config file. For example, `"reading_order_path": "database/database.db"` points to that project's SQLite database, and logs are written to that project's `logs` folder by default.

Run a project command with:

```powershell
npm run project:sort:dry -- --project spider-man
npm run project:missing -- --project spider-man
npm run project:list -- --project spider-man
npm run project:reindex:dry -- --project spider-man
npm run project:flatten:dry -- --project spider-man
npm run project:characters -- --project spider-man
```

Project profiles are the recommended layout once you start keeping separate Marvel groups, DC groups, runs, or character ownership lists.
