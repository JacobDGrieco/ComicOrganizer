# Project Profiles

Create one folder per reading project under `projects/`, and keep the reading-order database for each project in the root `databases/` folder.

```text
projects/
  spider-man/
    config.json
    characters.md
    downloader/
      urls.csv
      downloads/
    logs/
  x-men/
    config.json
    characters.md
    downloader/
      urls.csv
      downloads/
    logs/

databases/
  spider-man.db
  x-men.db
```

Inside a project config, relative paths are resolved next to that config file. When `reading_order_path` is omitted from `projects/<group>/config.json`, commands use `databases/<group>.db`.

Run project commands with:

```powershell
npm run sort:dry -- spider-man
npm run missing -- spider-man
npm run list -- spider-man
npm run reindex:dry -- spider-man
npm run flatten:dry -- spider-man
npm run characters -- spider-man
```

Project profiles are the recommended layout once you start keeping separate Marvel groups, DC groups, runs, or character ownership lists.
