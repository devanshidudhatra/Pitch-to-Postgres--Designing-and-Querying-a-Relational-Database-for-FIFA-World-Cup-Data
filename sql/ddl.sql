-- =============================================================================
-- Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
-- DS604 Introduction to Data Management - Milestone 2: Schema (DDL)
-- Group: Devanshi Dudhatra (202618027), Pujita Sunapu (202618003), Rahul Saha (202618037)
--
-- Data: Joshua C. Fjelstul, The Fjelstul World Cup Database,
--       https://github.com/jfjelstul/worldcup, CC-BY-SA 4.0.
--       Modifications: the source tables are normalised (copied columns, row numbers and
--       same-row derived columns are removed). Text markers such as 'not available' become NULL.
--       One lookup table (positions) is added. No data values are changed.
--
-- Target: PostgreSQL 12 or later. Standard SQL only, apart from the ~ regex operator in CHECKs.
-- Safe to run more than once: CREATE ... IF NOT EXISTS, and no DROP, TRUNCATE or DELETE.
-- Tables are created in dependency order (parents before children).
-- Tables are created in the current schema (set DB_SCHEMA in .env to choose one).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Reference tables
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS confederations (
    confederation_id             VARCHAR(5)   PRIMARY KEY CHECK (confederation_id ~ '^CF-[0-9]+$'),
    confederation_name           VARCHAR(100) NOT NULL UNIQUE,
    confederation_code           VARCHAR(10)  NOT NULL UNIQUE,
    confederation_wikipedia_link VARCHAR(255)
);
COMMENT ON TABLE confederations IS 'One row per continental confederation (AFC, CAF, CONCACAF, CONMEBOL, OFC, UEFA).';

-- Lookup added by the group: position codes used in squads and player_appearances.
-- Values are exactly the code/name pairs that occur in the source files.
CREATE TABLE IF NOT EXISTS positions (
    position_code VARCHAR(3)  PRIMARY KEY,
    position_name VARCHAR(30) NOT NULL UNIQUE
);
COMMENT ON TABLE positions IS 'Lookup of playing positions (codes and names exactly as in the source files).';

INSERT INTO positions (position_code, position_name) VALUES
    ('GK', 'goal keeper'), ('DF', 'defender'), ('MF', 'midfielder'), ('FW', 'forward'),
    ('SW', 'sweeper'), ('CB', 'center back'), ('LB', 'left back'), ('RB', 'right back'),
    ('LWB', 'left wing back'), ('RWB', 'right wing back'), ('DM', 'defensive midfielder'),
    ('CM', 'center midfielder'), ('LM', 'left midfielder'), ('RM', 'right midfielder'),
    ('AM', 'attacking midfielder'), ('LW', 'left winger'), ('RW', 'right winger'),
    ('SS', 'second striker'), ('CF', 'center forward'), ('LF', 'left forward'), ('RF', 'right forward')
ON CONFLICT (position_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS awards (
    award_id          VARCHAR(5)   PRIMARY KEY CHECK (award_id ~ '^A-[0-9]+$'),
    award_name        VARCHAR(50)  NOT NULL UNIQUE,
    award_description VARCHAR(100) NOT NULL,
    year_introduced   SMALLINT     NOT NULL CHECK (year_introduced BETWEEN 1930 AND 2100)
);
COMMENT ON TABLE awards IS 'One row per individual award type (Golden Ball, Golden Boot, ...).';

CREATE TABLE IF NOT EXISTS stadiums (
    stadium_id             VARCHAR(5)   PRIMARY KEY CHECK (stadium_id ~ '^S-[0-9]{3}$'),
    stadium_name           VARCHAR(100) NOT NULL,
    city_name              VARCHAR(60)  NOT NULL,
    country_name           VARCHAR(60)  NOT NULL,
    stadium_capacity       INTEGER      NOT NULL CHECK (stadium_capacity > 0),
    stadium_wikipedia_link VARCHAR(255),
    city_wikipedia_link    VARCHAR(255),
    CONSTRAINT uq_stadium_name_city UNIQUE (stadium_name, city_name)   -- two 'Olympiastadion's exist (Berlin, Munich)
);
COMMENT ON TABLE stadiums IS 'One row per stadium that hosted a World Cup match.';

CREATE TABLE IF NOT EXISTS teams (
    team_id                   VARCHAR(4)   PRIMARY KEY CHECK (team_id ~ '^T-[0-9]{2}$'),
    team_name                 VARCHAR(60)  NOT NULL UNIQUE,
    team_code                 CHAR(3)      NOT NULL CHECK (team_code ~ '^[A-Z]{3}$'),  -- NOT unique: Germany and West Germany share DEU
    federation_name           VARCHAR(100) NOT NULL,
    region_name               VARCHAR(40)  NOT NULL,
    confederation_id          VARCHAR(5)   NOT NULL REFERENCES confederations (confederation_id),
    team_wikipedia_link       VARCHAR(255),
    federation_wikipedia_link VARCHAR(255)
);
COMMENT ON TABLE teams IS 'One row per national team, including historical teams (West Germany, Soviet Union, ...). confederation_id is the current confederation.';

-- -----------------------------------------------------------------------------
-- 2. People
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS players (
    player_id             VARCHAR(7)   PRIMARY KEY CHECK (player_id ~ '^P-[0-9]{5}$'),
    family_name           VARCHAR(60)  NOT NULL,
    given_name            VARCHAR(60),                    -- NULL for players known by one name (e.g. Pele)
    birth_date            DATE CHECK (birth_date >= DATE '1880-01-01'),   -- NULL when unknown (78 players)
    player_wikipedia_link VARCHAR(255)
);
COMMENT ON TABLE players IS 'One row per player named in any World Cup squad.';

CREATE TABLE IF NOT EXISTS managers (
    manager_id             VARCHAR(5)  PRIMARY KEY CHECK (manager_id ~ '^M-[0-9]{3}$'),
    family_name            VARCHAR(60) NOT NULL,
    given_name             VARCHAR(60),
    country_name           VARCHAR(60) NOT NULL,          -- nationality
    manager_wikipedia_link VARCHAR(255)
);
COMMENT ON TABLE managers IS 'One row per manager (head coach).';

CREATE TABLE IF NOT EXISTS referees (
    referee_id             VARCHAR(5)  PRIMARY KEY CHECK (referee_id ~ '^R-[0-9]{3}$'),
    family_name            VARCHAR(60) NOT NULL,
    given_name             VARCHAR(60),
    country_name           VARCHAR(60) NOT NULL,          -- nationality
    confederation_id       VARCHAR(5)  NOT NULL REFERENCES confederations (confederation_id),
    referee_wikipedia_link VARCHAR(255)
);
COMMENT ON TABLE referees IS 'One row per referee appointed to a World Cup.';

-- -----------------------------------------------------------------------------
-- 3. Tournament structure
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id   VARCHAR(7)  PRIMARY KEY CHECK (tournament_id ~ '^WC-[0-9]{4}$'),
    tournament_name VARCHAR(40) NOT NULL UNIQUE,
    year            SMALLINT    NOT NULL UNIQUE CHECK (year BETWEEN 1930 AND 2100),
    start_date      DATE        NOT NULL,
    end_date        DATE        NOT NULL,
    CONSTRAINT ck_tournament_dates CHECK (end_date >= start_date),
    CONSTRAINT ck_tournament_id_year CHECK (tournament_id = 'WC-' || CAST(year AS VARCHAR(4))),
    CONSTRAINT ck_tournament_start_year CHECK (EXTRACT(YEAR FROM start_date) = year)
);
COMMENT ON TABLE tournaments IS 'One row per men''s World Cup final tournament. Host, winner and format flags are derived (see views).';

CREATE TABLE IF NOT EXISTS tournament_stages (
    tournament_id   VARCHAR(7)  NOT NULL REFERENCES tournaments (tournament_id),
    stage_number    SMALLINT    NOT NULL CHECK (stage_number >= 1),
    stage_name      VARCHAR(20) NOT NULL CHECK (stage_name IN (
                        'group stage', 'second group stage', 'final round', 'round of 16',
                        'quarter-finals', 'semi-finals', 'third-place match', 'final')),
    start_date      DATE        NOT NULL,
    end_date        DATE        NOT NULL,
    count_teams     SMALLINT    NOT NULL CHECK (count_teams > 0),     -- kept: not derivable (1938 walkover)
    count_scheduled SMALLINT    NOT NULL CHECK (count_scheduled >= 0),
    count_playoffs  SMALLINT    NOT NULL CHECK (count_playoffs >= 0),
    count_walkovers SMALLINT    NOT NULL CHECK (count_walkovers >= 0),
    PRIMARY KEY (tournament_id, stage_number),
    CONSTRAINT uq_stage_name UNIQUE (tournament_id, stage_name),
    CONSTRAINT ck_stage_dates CHECK (end_date >= start_date)
);
COMMENT ON TABLE tournament_stages IS 'One row per stage of a tournament. stage_name is stored only here.';

CREATE TABLE IF NOT EXISTS groups (
    tournament_id VARCHAR(7)  NOT NULL,
    stage_number  SMALLINT    NOT NULL,
    group_name    VARCHAR(10) NOT NULL,
    PRIMARY KEY (tournament_id, stage_number, group_name),
    FOREIGN KEY (tournament_id, stage_number) REFERENCES tournament_stages (tournament_id, stage_number)
);
COMMENT ON TABLE groups IS 'One row per group within a group stage. Group names repeat across stages, so stage_number is part of the key.';

-- -----------------------------------------------------------------------------
-- 4. Participation
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS qualified_teams (
    tournament_id VARCHAR(7)  NOT NULL REFERENCES tournaments (tournament_id),
    team_id       VARCHAR(4)  NOT NULL REFERENCES teams (team_id),
    performance   VARCHAR(20) NOT NULL CHECK (performance IN (
                      'group stage', 'second group stage', 'final round', 'round of 16',
                      'quarter-finals', 'semi-finals', 'third-place match', 'final')),
    PRIMARY KEY (tournament_id, team_id)
);
COMMENT ON TABLE qualified_teams IS 'Bridge tournaments M:N teams. performance = furthest stage reached (final = winner or runner-up).';

CREATE TABLE IF NOT EXISTS host_countries (
    tournament_id VARCHAR(7) NOT NULL,
    team_id       VARCHAR(4) NOT NULL,
    PRIMARY KEY (tournament_id, team_id),
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE host_countries IS 'Host team(s) of each tournament (2002 has two). The host''s finish is in qualified_teams/tournament_standings.';

CREATE TABLE IF NOT EXISTS tournament_standings (
    tournament_id VARCHAR(7) NOT NULL,
    position      SMALLINT   NOT NULL CHECK (position BETWEEN 1 AND 4),
    team_id       VARCHAR(4) NOT NULL,
    PRIMARY KEY (tournament_id, position),
    CONSTRAINT uq_standing_team UNIQUE (tournament_id, team_id),
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE tournament_standings IS 'Final top-four positions of each tournament (1 = champion).';

CREATE TABLE IF NOT EXISTS group_standings (
    tournament_id VARCHAR(7)  NOT NULL,
    stage_number  SMALLINT    NOT NULL,
    group_name    VARCHAR(10) NOT NULL,
    position      SMALLINT    NOT NULL CHECK (position >= 1),
    team_id       VARCHAR(4)  NOT NULL,
    wins          SMALLINT    NOT NULL CHECK (wins >= 0),
    draws         SMALLINT    NOT NULL CHECK (draws >= 0),
    losses        SMALLINT    NOT NULL CHECK (losses >= 0),
    goals_for     SMALLINT    NOT NULL CHECK (goals_for >= 0),
    goals_against SMALLINT    NOT NULL CHECK (goals_against >= 0),
    advanced      BOOLEAN     NOT NULL,
    PRIMARY KEY (tournament_id, stage_number, group_name, position),
    CONSTRAINT uq_group_team UNIQUE (tournament_id, stage_number, team_id),
    FOREIGN KEY (tournament_id, stage_number, group_name) REFERENCES groups (tournament_id, stage_number, group_name),
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE group_standings IS 'Final group tables. played, goal difference and points are derived (points rule changed in 1994).';

CREATE TABLE IF NOT EXISTS squads (
    tournament_id VARCHAR(7) NOT NULL,
    team_id       VARCHAR(4) NOT NULL,
    player_id     VARCHAR(7) NOT NULL REFERENCES players (player_id),
    shirt_number  SMALLINT   CHECK (shirt_number BETWEEN 1 AND 99),     -- NULL = unknown (source used 0)
    position_code VARCHAR(3) NOT NULL REFERENCES positions (position_code)
                             CHECK (position_code IN ('GK', 'DF', 'MF', 'FW')),
    PRIMARY KEY (tournament_id, team_id, player_id),
    CONSTRAINT uq_squad_player UNIQUE (tournament_id, player_id),        -- a player is in one squad per tournament
    CONSTRAINT uq_squad_shirt UNIQUE (tournament_id, team_id, shirt_number),
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE squads IS 'Bridge (tournament, team) M:N players. Event tables reference this composite key.';

CREATE TABLE IF NOT EXISTS manager_appointments (
    tournament_id VARCHAR(7) NOT NULL,
    team_id       VARCHAR(4) NOT NULL,
    manager_id    VARCHAR(5) NOT NULL REFERENCES managers (manager_id),
    PRIMARY KEY (tournament_id, team_id, manager_id),                    -- joint managers exist
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE manager_appointments IS 'Bridge (tournament, team) M:N managers.';

CREATE TABLE IF NOT EXISTS referee_appointments (
    tournament_id VARCHAR(7) NOT NULL REFERENCES tournaments (tournament_id),
    referee_id    VARCHAR(5) NOT NULL REFERENCES referees (referee_id),
    PRIMARY KEY (tournament_id, referee_id)
);
COMMENT ON TABLE referee_appointments IS 'Bridge tournaments M:N referees.';

-- -----------------------------------------------------------------------------
-- 5. Matches
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS matches (
    match_id                  VARCHAR(10) PRIMARY KEY CHECK (match_id ~ '^M-[0-9]{4}-[0-9]{2}$'),
    tournament_id             VARCHAR(7)  NOT NULL,
    stage_number              SMALLINT    NOT NULL,
    group_name                VARCHAR(10),                                 -- NULL outside group stages
    replayed                  BOOLEAN     NOT NULL,                        -- drawn and replayed later
    replay                    BOOLEAN     NOT NULL,                        -- this match is the replay
    match_date                DATE        NOT NULL,
    match_time                TIME        NOT NULL,                        -- local kick-off time
    stadium_id                VARCHAR(5)  NOT NULL REFERENCES stadiums (stadium_id),
    home_team_id              VARCHAR(4)  NOT NULL,
    away_team_id              VARCHAR(4)  NOT NULL,
    home_team_score           SMALLINT    NOT NULL CHECK (home_team_score >= 0),
    away_team_score           SMALLINT    NOT NULL CHECK (away_team_score >= 0),
    extra_time                BOOLEAN     NOT NULL,
    penalty_shootout          BOOLEAN     NOT NULL,
    home_team_score_penalties SMALLINT    CHECK (home_team_score_penalties >= 0),   -- NULL when no shoot-out
    away_team_score_penalties SMALLINT    CHECK (away_team_score_penalties >= 0),
    CONSTRAINT uq_match_tournament UNIQUE (match_id, tournament_id),     -- target for composite FKs below
    CONSTRAINT ck_match_id_year CHECK (SUBSTRING(match_id FROM 3 FOR 4) = SUBSTRING(tournament_id FROM 4 FOR 4)),
    CONSTRAINT ck_match_teams_differ CHECK (home_team_id <> away_team_id),
    CONSTRAINT ck_match_replay CHECK (NOT (replayed AND replay)),
    CONSTRAINT ck_match_replayed_draw CHECK (NOT replayed OR home_team_score = away_team_score),
    CONSTRAINT ck_match_shootout CHECK (
        (penalty_shootout AND extra_time
             AND home_team_score = away_team_score
             AND home_team_score_penalties IS NOT NULL AND away_team_score_penalties IS NOT NULL
             AND home_team_score_penalties <> away_team_score_penalties)
        OR (NOT penalty_shootout AND home_team_score_penalties IS NULL AND away_team_score_penalties IS NULL)),
    FOREIGN KEY (tournament_id, stage_number) REFERENCES tournament_stages (tournament_id, stage_number),
    FOREIGN KEY (tournament_id, stage_number, group_name) REFERENCES groups (tournament_id, stage_number, group_name),
    FOREIGN KEY (tournament_id, home_team_id) REFERENCES qualified_teams (tournament_id, team_id),
    FOREIGN KEY (tournament_id, away_team_id) REFERENCES qualified_teams (tournament_id, team_id)
);
COMMENT ON TABLE matches IS 'One row per match (replays are separate matches). Result, margins and score text are derived.';

CREATE TABLE IF NOT EXISTS team_appearances (
    match_id          VARCHAR(10) NOT NULL,
    team_id           VARCHAR(4)  NOT NULL,
    tournament_id     VARCHAR(7)  NOT NULL,
    opponent_id       VARCHAR(4)  NOT NULL,
    home_team         BOOLEAN     NOT NULL,
    goals_for         SMALLINT    NOT NULL CHECK (goals_for >= 0),
    goals_against     SMALLINT    NOT NULL CHECK (goals_against >= 0),
    penalties_for     SMALLINT    CHECK (penalties_for >= 0),             -- NULL when no shoot-out
    penalties_against SMALLINT    CHECK (penalties_against >= 0),
    PRIMARY KEY (match_id, team_id),
    CONSTRAINT ck_ta_opponent CHECK (team_id <> opponent_id),
    CONSTRAINT ck_ta_penalties CHECK ((penalties_for IS NULL) = (penalties_against IS NULL)),
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (tournament_id, team_id) REFERENCES qualified_teams (tournament_id, team_id),
    -- the opponent must have its own row for the same match; checked at COMMIT so both rows can be inserted together
    CONSTRAINT fk_ta_opponent FOREIGN KEY (match_id, opponent_id) REFERENCES team_appearances (match_id, team_id)
        DEFERRABLE INITIALLY DEFERRED
);
COMMENT ON TABLE team_appearances IS 'Each match seen from one team (2 rows per match). Kept as a team-centred view of matches for simpler queries.';

CREATE TABLE IF NOT EXISTS referee_appearances (
    match_id      VARCHAR(10) PRIMARY KEY,                                 -- one referee per match
    tournament_id VARCHAR(7)  NOT NULL,
    referee_id    VARCHAR(5)  NOT NULL,
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (tournament_id, referee_id) REFERENCES referee_appointments (tournament_id, referee_id)
);
COMMENT ON TABLE referee_appearances IS 'The referee of each match (1:1 with matches).';

CREATE TABLE IF NOT EXISTS manager_appearances (
    match_id      VARCHAR(10) NOT NULL,
    team_id       VARCHAR(4)  NOT NULL,
    manager_id    VARCHAR(5)  NOT NULL,
    tournament_id VARCHAR(7)  NOT NULL,
    PRIMARY KEY (match_id, team_id, manager_id),
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, team_id, manager_id) REFERENCES manager_appointments (tournament_id, team_id, manager_id)
);
COMMENT ON TABLE manager_appearances IS 'Manager(s) in charge of a team in a match.';

-- -----------------------------------------------------------------------------
-- 6. Match events
-- tournament_id is kept in event tables on purpose: it lets the composite FK to squads check that
-- the player was in that team's squad for that tournament. The FK (match_id, tournament_id) -> matches
-- guarantees it always agrees with the match, so the extra column cannot become inconsistent.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS player_appearances (
    match_id      VARCHAR(10) NOT NULL,
    player_id     VARCHAR(7)  NOT NULL,
    tournament_id VARCHAR(7)  NOT NULL,
    team_id       VARCHAR(4)  NOT NULL,
    position_code VARCHAR(3)  NOT NULL REFERENCES positions (position_code),
    starter       BOOLEAN     NOT NULL,                                    -- FALSE = came on as a substitute
    captain       BOOLEAN     NOT NULL,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE player_appearances IS 'Line-ups from 1970: one row per player who played in a match.';

CREATE TABLE IF NOT EXISTS goals (
    goal_id           VARCHAR(6)  PRIMARY KEY CHECK (goal_id ~ '^G-[0-9]{4}$'),
    match_id          VARCHAR(10) NOT NULL,
    tournament_id     VARCHAR(7)  NOT NULL,
    team_id           VARCHAR(4)  NOT NULL,                                -- team credited with the goal
    player_id         VARCHAR(7)  NOT NULL,
    player_team_id    VARCHAR(4)  NOT NULL,                                -- scorer's own team
    minute_regulation SMALLINT    NOT NULL CHECK (minute_regulation BETWEEN 1 AND 120),
    minute_stoppage   SMALLINT    NOT NULL DEFAULT 0 CHECK (minute_stoppage >= 0),
    own_goal          BOOLEAN     NOT NULL,
    penalty           BOOLEAN     NOT NULL,                                -- in-match penalty (not shoot-out)
    CONSTRAINT ck_goal_own_goal CHECK (own_goal = (team_id <> player_team_id)),
    CONSTRAINT ck_goal_not_both CHECK (NOT (own_goal AND penalty)),
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (match_id, player_team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, player_team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE goals IS 'One row per goal. Own goals: credited to team_id, scored by a player of player_team_id.';

CREATE TABLE IF NOT EXISTS bookings (
    booking_id         VARCHAR(6)  PRIMARY KEY CHECK (booking_id ~ '^B-[0-9]{4}$'),
    match_id           VARCHAR(10) NOT NULL,
    tournament_id      VARCHAR(7)  NOT NULL,
    team_id            VARCHAR(4)  NOT NULL,
    player_id          VARCHAR(7)  NOT NULL,
    minute_regulation  SMALLINT    NOT NULL CHECK (minute_regulation BETWEEN 1 AND 120),
    minute_stoppage    SMALLINT    NOT NULL DEFAULT 0 CHECK (minute_stoppage >= 0),
    yellow_card        BOOLEAN     NOT NULL,
    red_card           BOOLEAN     NOT NULL,                               -- straight red
    second_yellow_card BOOLEAN     NOT NULL,                               -- second yellow -> sent off
    CONSTRAINT ck_booking_some_card CHECK (yellow_card OR red_card),
    CONSTRAINT ck_booking_second_yellow CHECK (NOT second_yellow_card OR yellow_card),
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE bookings IS 'Cards from 1970. Sent off = red_card OR second_yellow_card.';

CREATE TABLE IF NOT EXISTS substitutions (
    substitution_id   VARCHAR(6)  PRIMARY KEY CHECK (substitution_id ~ '^S-[0-9]{4}$'),
    match_id          VARCHAR(10) NOT NULL,
    tournament_id     VARCHAR(7)  NOT NULL,
    team_id           VARCHAR(4)  NOT NULL,
    player_id         VARCHAR(7)  NOT NULL,
    minute_regulation SMALLINT    NOT NULL CHECK (minute_regulation BETWEEN 1 AND 120),
    minute_stoppage   SMALLINT    NOT NULL DEFAULT 0 CHECK (minute_stoppage >= 0),
    coming_on         BOOLEAN     NOT NULL,                                -- FALSE = going off
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE substitutions IS 'Substitutions from 1970: two rows per substitution (one going off, one coming on).';

CREATE TABLE IF NOT EXISTS penalty_kicks (
    penalty_kick_id VARCHAR(6)  PRIMARY KEY CHECK (penalty_kick_id ~ '^PK-[0-9]{3}$'),
    match_id        VARCHAR(10) NOT NULL,
    tournament_id   VARCHAR(7)  NOT NULL,
    team_id         VARCHAR(4)  NOT NULL,
    player_id       VARCHAR(7)  NOT NULL,
    converted       BOOLEAN     NOT NULL,
    FOREIGN KEY (match_id, tournament_id) REFERENCES matches (match_id, tournament_id),
    FOREIGN KEY (match_id, team_id) REFERENCES team_appearances (match_id, team_id),
    FOREIGN KEY (tournament_id, team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE penalty_kicks IS 'Penalty shoot-out kicks (1982+). In-match penalties are in goals (penalty = TRUE).';

-- -----------------------------------------------------------------------------
-- 7. Awards
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS award_winners (
    tournament_id VARCHAR(7) NOT NULL,
    award_id      VARCHAR(5) NOT NULL REFERENCES awards (award_id),
    player_id     VARCHAR(7) NOT NULL,
    team_id       VARCHAR(4) NOT NULL,
    PRIMARY KEY (tournament_id, award_id, player_id),                    -- ties give several winners
    FOREIGN KEY (tournament_id, team_id, player_id) REFERENCES squads (tournament_id, team_id, player_id)
);
COMMENT ON TABLE award_winners IS 'Award winners per tournament. Shared = more than one winner for the same award and tournament.';

-- -----------------------------------------------------------------------------
-- 8. Indexes
-- Primary keys and UNIQUE constraints are indexed automatically. These extra indexes cover
-- foreign-key columns that are not the leading column of an existing index and that the
-- analytical queries join or filter on.
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS ix_teams_confederation        ON teams (confederation_id);
CREATE INDEX IF NOT EXISTS ix_referees_confederation     ON referees (confederation_id);
CREATE INDEX IF NOT EXISTS ix_qualified_teams_team       ON qualified_teams (team_id);
CREATE INDEX IF NOT EXISTS ix_squads_player              ON squads (player_id);
CREATE INDEX IF NOT EXISTS ix_manager_appointments_mgr   ON manager_appointments (manager_id);
CREATE INDEX IF NOT EXISTS ix_referee_appointments_ref   ON referee_appointments (referee_id);
CREATE INDEX IF NOT EXISTS ix_matches_stage              ON matches (tournament_id, stage_number);
CREATE INDEX IF NOT EXISTS ix_matches_stadium            ON matches (stadium_id);
CREATE INDEX IF NOT EXISTS ix_matches_home_team          ON matches (home_team_id);
CREATE INDEX IF NOT EXISTS ix_matches_away_team          ON matches (away_team_id);
CREATE INDEX IF NOT EXISTS ix_team_appearances_team      ON team_appearances (team_id, opponent_id);
CREATE INDEX IF NOT EXISTS ix_referee_appearances_ref    ON referee_appearances (referee_id);
CREATE INDEX IF NOT EXISTS ix_manager_appearances_mgr    ON manager_appearances (manager_id);
CREATE INDEX IF NOT EXISTS ix_player_appearances_player  ON player_appearances (player_id);
CREATE INDEX IF NOT EXISTS ix_goals_match_team           ON goals (match_id, team_id);
CREATE INDEX IF NOT EXISTS ix_goals_player               ON goals (player_id);
CREATE INDEX IF NOT EXISTS ix_bookings_match             ON bookings (match_id, team_id);
CREATE INDEX IF NOT EXISTS ix_bookings_player            ON bookings (player_id);
CREATE INDEX IF NOT EXISTS ix_substitutions_match        ON substitutions (match_id, team_id);
CREATE INDEX IF NOT EXISTS ix_penalty_kicks_match        ON penalty_kicks (match_id, team_id);
CREATE INDEX IF NOT EXISTS ix_award_winners_player       ON award_winners (player_id);

-- End of DDL: 28 tables (27 from the dataset + positions lookup), 21 secondary indexes.
