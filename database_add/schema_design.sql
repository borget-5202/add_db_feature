-- users table: stores user information
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
CREATE TABLE IF NOT EXISTS app.users (
  id                        SERIAL PRIMARY KEY,
  username                  VARCHAR(50)  NOT NULL UNIQUE,
  email                     VARCHAR(100) NOT NULL UNIQUE,
  password_hash             VARCHAR(255) NOT NULL,

  -- meta
  role                      VARCHAR(32),                          -- e.g. 'student' | 'teacher' | 'admin'
  grade_level               SMALLINT,

  -- timestamps (use timestamptz for real-world correctness)
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login                TIMESTAMPTZ,
  is_active                 BOOLEAN     NOT NULL DEFAULT TRUE,

  -- misc profile
  profile_data              JSONB       NOT NULL DEFAULT '{}'::jsonb,

  -- Game24 stats
  game24_total_score        INTEGER     NOT NULL DEFAULT 0,
  game24_total_attempts     INTEGER     NOT NULL DEFAULT 0,
  game24_correct_attempts   INTEGER     NOT NULL DEFAULT 0,
  game24_last_played        TIMESTAMPTZ,
  game24_max_streak         INTEGER     NOT NULL DEFAULT 0,
  game24_total_puzzles_name TEXT,                               -- free-form; make JSONB if you prefer
  game24_total_puzzles      INTEGER     NOT NULL DEFAULT 0,
  game24_correct_puzzles    INTEGER     NOT NULL DEFAULT 0,

);

-- games table: stores different games on your platform
CREATE TABLE IF NOT EXISTS app.games (
  id                          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name                        VARCHAR(100)  NOT NULL UNIQUE,
  display_name                VARCHAR(150)  NOT NULL,
  description                 TEXT,
  category                    VARCHAR(50),
  difficulty_range            TEXT,                 -- e.g., 'elementary,middle,high'
  is_active                   BOOLEAN       NOT NULL DEFAULT TRUE,
  version                     TEXT          NOT NULL DEFAULT '1.0',
  created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  game_metadata               JSONB         DEFAULT '{}'::jsonb
);

-- user_game_sessions table: tracks each play session
CREATE TABLE user_game_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    game_id INTEGER REFERENCES games(id),
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    score INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS app.game_sessions (
  id             INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id        INT REFERENCES app.users(id) ON DELETE SET NULL,
  game_id        INT REFERENCES app.games(id) ON DELETE SET NULL,

  session_uuid   UUID NOT NULL,             -- app should set uuid4(); add a DEFAULT if you have pgcrypto/uuid-ossp
  start_time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  end_time       TIMESTAMPTZ,
  score          INT NOT NULL DEFAULT 0,
  duration    INTERVAL GENERATED ALWAYS AS (end_time - start_time) STORED,
  completed      BOOLEAN NOT NULL DEFAULT FALSE,
  device_info    JSONB DEFAULT '{}'::jsonb
);

-- game24_specific_stats table: specific metrics for 24-point game
CREATE TABLE game24_specific_stats (
    session_id INTEGER REFERENCES user_game_sessions(id),
    puzzles_attempted INTEGER DEFAULT 0,
    puzzles_solved INTEGER DEFAULT 0,
    average_solve_time DECIMAL(10,2),
    max_streak INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- user_achievements table: tracks user achievements
CREATE TABLE user_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    game_id INTEGER REFERENCES games(id),
    achievement_name VARCHAR(100),
    achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, game_id, achievement_name)
);
