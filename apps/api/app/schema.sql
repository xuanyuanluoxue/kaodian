PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subject (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    short         TEXT NOT NULL,
    exam_score    INTEGER NOT NULL,
    exam_minutes  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS outline_node (
    code         TEXT PRIMARY KEY,
    subject_id   TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    section      TEXT,
    title        TEXT NOT NULL,
    requirement  TEXT,
    frequency    TEXT,
    hours        INTEGER,
    stage        TEXT,
    assessment   TEXT,
    kind         TEXT NOT NULL DEFAULT 'point',
    sort         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_outline_subject ON outline_node(subject_id, sort);

CREATE TABLE IF NOT EXISTS question (
    id               TEXT PRIMARY KEY,
    subject_id       TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    outline_code     TEXT NOT NULL REFERENCES outline_node(code) ON DELETE CASCADE,
    type             TEXT NOT NULL,
    stem             TEXT NOT NULL,
    options          TEXT,
    answer           TEXT,
    explanation      TEXT NOT NULL,
    reference_answer TEXT,
    rubric           TEXT,
    score            REAL NOT NULL DEFAULT 1,
    difficulty       INTEGER NOT NULL DEFAULT 2,
    source           TEXT,
    tags             TEXT,
    verified         INTEGER NOT NULL DEFAULT 0,
    fingerprint      TEXT UNIQUE,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_question_code ON question(outline_code);
CREATE INDEX IF NOT EXISTS idx_question_subject ON question(subject_id, type);

CREATE TABLE IF NOT EXISTS quiz (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    mode             TEXT NOT NULL DEFAULT 'practice',
    time_limit       INTEGER,
    agent_session_id TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_item (
    quiz_id     TEXT NOT NULL REFERENCES quiz(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (quiz_id, position)
);

CREATE TABLE IF NOT EXISTS attempt (
    id             TEXT PRIMARY KEY,
    quiz_id        TEXT NOT NULL REFERENCES quiz(id) ON DELETE CASCADE,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    score          REAL,
    max_score      REAL,
    meta           TEXT
);

CREATE INDEX IF NOT EXISTS idx_attempt_started ON attempt(started_at);

CREATE TABLE IF NOT EXISTS answer (
    attempt_id   TEXT NOT NULL REFERENCES attempt(id) ON DELETE CASCADE,
    question_id  TEXT NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    response     TEXT,
    correct      INTEGER,
    score        REAL,
    time_spent   INTEGER NOT NULL DEFAULT 0,
    flagged      INTEGER NOT NULL DEFAULT 0,
    self_grade   TEXT,
    PRIMARY KEY (attempt_id, question_id)
);

CREATE TABLE IF NOT EXISTS event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT,
    kind       TEXT NOT NULL,
    payload    TEXT,
    at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_attempt ON event(attempt_id);

CREATE TABLE IF NOT EXISTS review (
    question_id   TEXT PRIMARY KEY REFERENCES question(id) ON DELETE CASCADE,
    due_date      TEXT NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 0,
    mastery       INTEGER NOT NULL DEFAULT 0,
    streak        INTEGER NOT NULL DEFAULT 0,
    lapses        INTEGER NOT NULL DEFAULT 0,
    last_result   TEXT,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_due ON review(due_date);

-- Agent 协作：会话与事件流。Agent 写 note，Web 写 help，交卷写 submitted。
CREATE TABLE IF NOT EXISTS agent_session (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES agent_session(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'system',
    body       TEXT,
    ref        TEXT,
    created_at TEXT NOT NULL,
    read_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_event_session ON agent_event(session_id, id);
