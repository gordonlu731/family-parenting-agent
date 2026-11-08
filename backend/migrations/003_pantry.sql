CREATE TABLE pantry (
    id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES families(id),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    quantity TEXT,
    unit TEXT NOT NULL,
    amount_note TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '未说明',
    kind TEXT NOT NULL DEFAULT 'raw' CHECK(kind IN ('raw','cooked')),
    status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','used_up')),
    version INTEGER NOT NULL DEFAULT 1,
    confirmed_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES members(id),
    UNIQUE(family_id,name_key,location,kind)
);
CREATE INDEX pantry_family ON pantry(family_id,status);
CREATE TABLE pantry_revisions (family_id TEXT PRIMARY KEY REFERENCES families(id), version INTEGER NOT NULL);
ALTER TABLE proposals ADD COLUMN context_snapshot TEXT NOT NULL DEFAULT '{}';
