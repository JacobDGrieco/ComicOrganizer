PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS comic_runs (
	id TEXT PRIMARY KEY,
	title TEXT NOT NULL,
	volume TEXT,
	years TEXT,
	category TEXT NOT NULL,
	publication_type TEXT,
	universe_hint TEXT,
	lead_characters TEXT,
	priority TEXT NOT NULL,
	marvel_url TEXT,
	marvel_issue_count INTEGER,
	notes TEXT
);

CREATE TABLE IF NOT EXISTS story_arcs (
	id TEXT PRIMARY KEY,
	title TEXT NOT NULL,
	start_date TEXT NOT NULL,
	start_date_precision TEXT NOT NULL,
	end_date TEXT,
	end_date_precision TEXT NOT NULL DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS issues (
	id TEXT PRIMARY KEY,
	cand_id TEXT NOT NULL,
	issue_number TEXT NOT NULL,
	release_date TEXT NOT NULL,
	release_date_precision TEXT NOT NULL,
	story_arc_id TEXT NOT NULL,
	UNIQUE (cand_id, issue_number),
	FOREIGN KEY (cand_id) REFERENCES comic_runs(id) ON DELETE CASCADE,
	FOREIGN KEY (story_arc_id) REFERENCES story_arcs(id)
);

CREATE INDEX IF NOT EXISTS idx_comic_runs_priority ON comic_runs(priority, category, title);
CREATE INDEX IF NOT EXISTS idx_comic_runs_title_volume ON comic_runs(title, volume);
CREATE INDEX IF NOT EXISTS idx_story_arcs_start_date ON story_arcs(start_date, title);
CREATE INDEX IF NOT EXISTS idx_issues_cand_issue_number ON issues(cand_id, issue_number);
CREATE INDEX IF NOT EXISTS idx_issues_release_date ON issues(release_date);
CREATE INDEX IF NOT EXISTS idx_issues_story_arc ON issues(story_arc_id);
