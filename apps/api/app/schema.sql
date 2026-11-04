PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subject (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    short         TEXT NOT NULL,
    exam_score    INTEGER NOT NULL,
    exam_minutes  INTEGER NOT NULL,
    color         TEXT,
    icon          TEXT,
    sort          INTEGER NOT NULL DEFAULT 0,
    code_language TEXT,
    pack_id       TEXT,
    source_key    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subject_pack_source
    ON subject(pack_id, source_key) WHERE pack_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS content_pack (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    version    TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    path       TEXT,
    synced_at  TEXT NOT NULL
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
    sort         INTEGER NOT NULL DEFAULT 0,
    parent_code  TEXT,
    depth        INTEGER NOT NULL DEFAULT 0,
    pack_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_outline_subject ON outline_node(subject_id, sort);
CREATE INDEX IF NOT EXISTS idx_outline_pack ON outline_node(pack_id);


-- 材料题 / 一拖多：一段材料（可含媒体）下挂多道小题。
CREATE TABLE IF NOT EXISTS question_group (
    id          TEXT PRIMARY KEY,
    subject_id  TEXT REFERENCES subject(id) ON DELETE CASCADE,
    title       TEXT,
    material    TEXT NOT NULL DEFAULT '',
    media       TEXT,
    source_key  TEXT,
    created_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_question_group_source
    ON question_group(subject_id, source_key);

CREATE TABLE IF NOT EXISTS question (
    id               TEXT PRIMARY KEY,
    subject_id       TEXT NOT NULL REFERENCES subject(id) ON DELETE CASCADE,
    outline_code     TEXT NOT NULL REFERENCES outline_node(code) ON DELETE CASCADE,
    group_id         TEXT REFERENCES question_group(id) ON DELETE SET NULL,
    group_position   INTEGER NOT NULL DEFAULT 0,
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
    language         TEXT,
    media            TEXT,
    status           TEXT NOT NULL DEFAULT 'approved',
    reviewed_at      TEXT,
    review_note      TEXT,
    fingerprint      TEXT UNIQUE,
    pack_id          TEXT,
    source_key       TEXT,
    created_at       TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_question_pack_source
    ON question(pack_id, source_key) WHERE pack_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_question_code ON question(outline_code);
CREATE INDEX IF NOT EXISTS idx_question_subject ON question(subject_id, type);
CREATE INDEX IF NOT EXISTS idx_question_group ON question(group_id, group_position);

-- 一题多考点：outline_code 仍是主考点，这里保存全部关联（含主考点）。
CREATE TABLE IF NOT EXISTS question_outline (
    question_id  TEXT NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    outline_code TEXT NOT NULL REFERENCES outline_node(code) ON DELETE CASCADE,
    weight       REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (question_id, outline_code)
);

CREATE INDEX IF NOT EXISTS idx_question_outline_code
    ON question_outline(outline_code, question_id);

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
    grading_status TEXT NOT NULL DEFAULT 'none',
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
    graded_by    TEXT,
    feedback     TEXT,
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


-- Agent 写入的学习页：大纲、讲义、每日任务
CREATE TABLE IF NOT EXISTS page (
    id            TEXT PRIMARY KEY,
    subject_id    TEXT REFERENCES subject(id) ON DELETE SET NULL,
    title         TEXT NOT NULL,
    summary       TEXT,
    body          TEXT NOT NULL,
    blocks        TEXT,
    layout        TEXT NOT NULL DEFAULT 'article',
    theme         TEXT,
    format        TEXT NOT NULL DEFAULT 'markdown',
    lesson_key    TEXT,
    outline_codes TEXT,
    kind          TEXT NOT NULL DEFAULT 'lesson',
    status        TEXT NOT NULL DEFAULT 'published',
    sort_order    INTEGER NOT NULL DEFAULT 1000,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    pack_id       TEXT,
    source_key    TEXT,
    file          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_page_pack_source
    ON page(pack_id, source_key) WHERE pack_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_page_subject ON page(subject_id, sort_order, created_at);
CREATE INDEX IF NOT EXISTS idx_page_status ON page(status, subject_id);


-- 网页编辑草稿：只保存未发布的修改，发布后删除。version 用于并发冲突检测。
CREATE TABLE IF NOT EXISTS page_draft (
    page_id    TEXT PRIMARY KEY REFERENCES page(id) ON DELETE CASCADE,
    body       TEXT,
    blocks     TEXT,
    layout     TEXT,
    theme      TEXT,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS page_progress (
    page_id      TEXT PRIMARY KEY REFERENCES page(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL,
    xp           INTEGER NOT NULL DEFAULT 10
);


-- 阅读/代码终端的投入时间。按天 + 来源 + 对象累加，和 attempt.active_seconds 分开记。
CREATE TABLE IF NOT EXISTS study_time (
    day        TEXT NOT NULL,
    source     TEXT NOT NULL,
    ref        TEXT NOT NULL DEFAULT '',
    seconds    INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (day, source, ref)
);


-- 学习画像：静态目标只存这一行，动态学情实时查询、不落库。
CREATE TABLE IF NOT EXISTS profile (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    target_exam        TEXT,
    target_date        TEXT,
    target_score       REAL,
    target_school      TEXT,
    target_major       TEXT,
    target_region      TEXT,
    backup_school      TEXT,
    backup_major       TEXT,
    exam_type          TEXT,
    current_education  TEXT,
    graduation_year    INTEGER,
    daily_minutes      INTEGER NOT NULL DEFAULT 30,
    subjects           TEXT NOT NULL DEFAULT '[]',
    study_window       TEXT,
    constraints        TEXT,
    strengths          TEXT,
    weaknesses         TEXT,
    motivation         TEXT,
    notes              TEXT NOT NULL DEFAULT '',
    ai_summary         TEXT,
    preferred_tone     TEXT NOT NULL DEFAULT '',
    preferred_examples TEXT NOT NULL DEFAULT '',
    updated_by         TEXT NOT NULL DEFAULT 'user',
    updated_at         TEXT
);
