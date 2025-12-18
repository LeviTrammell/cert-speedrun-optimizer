-- Cert Speedrun Optimizer Database Schema

-- Core entities
CREATE TABLE IF NOT EXISTS exams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    vendor TEXT,
    exam_code TEXT,
    passing_score INTEGER,
    time_limit_minutes INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    weight_percent REAL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(exam_id, name)
);

CREATE TABLE IF NOT EXISTS question_types (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    question_type_id INTEGER NOT NULL REFERENCES question_types(id),
    question_text TEXT NOT NULL,
    explanation TEXT,
    difficulty TEXT DEFAULT 'medium',
    choose_n INTEGER,
    pattern_tags TEXT,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS answer_options (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    distractor_reason TEXT
);

CREATE TABLE IF NOT EXISTS question_topics (
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, topic_id)
);

-- Performance tracking (single anonymous user)
CREATE TABLE IF NOT EXISTS practice_sessions (
    id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL REFERENCES exams(id),
    session_type TEXT DEFAULT 'practice',
    question_ids TEXT,  -- JSON array of question IDs for session recovery
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS question_attempts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES questions(id),
    is_correct INTEGER NOT NULL,
    time_taken_seconds INTEGER,
    attempted_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS question_stats (
    question_id TEXT PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    attempt_count INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    last_attempted_at TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions(exam_id);
CREATE INDEX IF NOT EXISTS idx_answer_options_question ON answer_options(question_id);
CREATE INDEX IF NOT EXISTS idx_question_topics_topic ON question_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_question_topics_question ON question_topics(question_id);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON question_attempts(question_id);
CREATE INDEX IF NOT EXISTS idx_attempts_session ON question_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_topics_exam ON topics(exam_id);

-- Seed question types
INSERT OR IGNORE INTO question_types (id, code, name) VALUES
    (1, 'SINGLE', 'Multiple Choice'),
    (2, 'CHOOSE_N', 'Choose N'),
    (3, 'SELECT_ALL', 'Select All That Apply');
