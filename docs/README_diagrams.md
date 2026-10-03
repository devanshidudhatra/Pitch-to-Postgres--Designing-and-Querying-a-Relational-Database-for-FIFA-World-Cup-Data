# Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data

## The ER diagrams and relational schema diagrams explained

**Group:** Devanshi Dudhatra (202618027), Pujita Sunapu (202618003), Rahul Saha (202618037). DS604 Introduction to Data Management.
**Data:** The Fjelstul World Cup Database by Joshua C. Fjelstul, <https://github.com/jfjelstul/worldcup>, CC-BY-SA 4.0.

All diagrams are in [`diagrams/`](../diagrams), as PNG images plus their Mermaid source (`.mmd`). There are seven sheets:

| File | Type | Covers |
|---|---|---|
| `er_diagram_1_tournaments_people.png` | ER diagram 1/2 | Tournaments, structure, participation, people, awards |
| `er_diagram_2_matches_events.png` | ER diagram 2/2 | Matches and everything that happens in them |
| `schema_1_reference_structure.png` | Relational schema 1/5 | Reference tables, people, tournament structure |
| `schema_2_participation.png` | Relational schema 2/5 | Who took part: qualified teams, squads, appointments, standings |
| `schema_3_matches.png` | Relational schema 3/5 | Matches, team/referee/manager appearances |
| `schema_4_goals_cards_shootouts.png` | Relational schema 4/5 | Goals, bookings, shoot-out kicks |
| `schema_5_lineups_subs_awards.png` | Relational schema 5/5 | Line-ups, substitutions, award winners |

---

## 1. How the diagrams were made, and why that matters

The diagrams are **not drawn by hand**. `src/make_diagrams.py` reads the tables, columns, primary keys, unique keys and foreign keys from the **live PostgreSQL catalog** after `sql/ddl.sql` has run. It then **measures each relationship's cardinality on the loaded data**: it counts how many child rows each parent has, and how many parents have none. So:

- every box, column and line exists in the real database; nothing was drawn that the DDL does not contain;
- every crow's-foot symbol reflects the actual data, not an assumption;
- if the schema changes, `python src/make_diagrams.py` redraws everything.

There are 28 tables, too many to read on one page, so the diagrams are split by theme. Tables that link two sheets appear on both.

## 2. How to read the notation (crow's foot)

Each line joins a **parent** (left end, the table being referenced) to a **child** (right end, the table holding the foreign key). Read each end as "how many of *this* table for one row of the *other* table":

| Symbol at an end | Meaning |
|---|---|
| `||` (two bars) | exactly one |
| `|o` / `o|` (bar and circle) | zero or one |
| `|{` / `}|` (bar and crow's foot) | one or more |
| `o{` / `}o` (circle and crow's foot) | zero or more |

**Example.** `TOURNAMENTS ||--|{ QUALIFIED_TEAMS` reads: each qualified-team row belongs to **exactly one** tournament, and each tournament has **one or more** qualified teams.

- **The circle (optional) side** means that some parents have no children *in the data*. For example, a tournament stage that is a knockout round has **zero** groups.
- **A circle on the parent side** (`|o`) appears where the foreign key may be NULL. The only case is `matches.group_name`, which is NULL for knockout matches.

## 3. ER diagrams versus relational schema diagrams

| | ER diagrams (2 sheets) | Relational schema diagrams (5 sheets) |
|---|---|---|
| Level | **Conceptual**: what the entities are and how they relate | **Logical/physical**: the actual tables as built |
| Boxes show | Entity names only | Every column with its type, plus PK / FK / UK markers and "nullable" |
| Line labels | A verb describing the relationship ("takes part", "scores", "booked in") | The foreign-key columns that implement it, e.g. `tournament_id, team_id` |
| Lines drawn | One line per meaningful relationship | **Every** foreign key, including the consistency ones |

**Why the ER diagrams leave some foreign keys out.** A few foreign keys exist only to keep a deliberately repeated column consistent:
- `(match_id, tournament_id) -> matches` in each event table;
- the second `goals -> team_appearances` key on `player_team_id`;
- the separate home and away keys from `matches` to `qualified_teams`.

Drawing them in a conceptual diagram would add lines without adding meaning, so the ER sheets show one line per real relationship, and the schema sheets show every key.

**Why some tables show only a few columns.** On a schema sheet, a table whose "home" is another sheet (a context table) is shown with only its primary key and the columns referenced from the current sheet. Its full column list is on its own sheet.

---

## 4. ER diagram 1/2: tournaments, teams, people and awards

This sheet answers: **who took part in which tournament, in what role, and how did they finish?**

**The central idea.** `QUALIFIED_TEAMS` sits in the middle, and nearly everything hangs off it. A team on its own is not very interesting; *a team at a particular tournament* is the thing that has a squad, a manager, a host role, a group position and a final position.

| Relationship (parent → child) | Cardinality | Meaning and why |
|---|---|---|
| CONFEDERATIONS → TEAMS ("belongs to") | 1 : 1..N | Each team belongs to exactly one (current) confederation; every confederation has teams. |
| CONFEDERATIONS → REFEREES ("belongs to") | 1 : 1..N | Referees are also grouped by confederation. |
| TOURNAMENTS → TOURNAMENT_STAGES ("has stage") | 1 : 1..N | Every tournament has at least one stage (1930: group stage, semi-finals, final). A stage cannot exist without its tournament, so it is a **weak entity** (key: tournament_id + stage_number). |
| TOURNAMENT_STAGES → GROUPS ("has group") | 1 : 0..N | Group stages have groups; knockout stages have **none**, hence the circle. |
| GROUPS → GROUP_STANDINGS ("ranks") | 1 : 1..N | Every group has a final table with one line per team. |
| TOURNAMENTS → QUALIFIED_TEAMS ("includes") and TEAMS → QUALIFIED_TEAMS ("takes part") | 1 : 1..N each | The **many-to-many** "teams take part in tournaments" is resolved by the bridge table `QUALIFIED_TEAMS` (457 rows). |
| QUALIFIED_TEAMS → HOST_COUNTRIES ("hosts") | 1 : 0..1 | A team at a tournament is either the host or not: 22 of 457 are hosts. 2002 has two hosts. |
| QUALIFIED_TEAMS → TOURNAMENT_STANDINGS ("finishes top 4") | 1 : 0..1 | Only 84 of 457 team-tournaments finish in the top four, and each at most once. |
| QUALIFIED_TEAMS → GROUP_STANDINGS ("placed") | 1 : 0..N | Zero for the knockout-only tournaments of 1934 and 1938; two when a tournament had two group stages. |
| QUALIFIED_TEAMS → SQUADS ("registers") and PLAYERS → SQUADS ("listed in") | 1 : 1..N each | The many-to-many "players are in teams' squads at tournaments" is resolved by `SQUADS`. Every player appears in at least one squad. |
| POSITIONS → SQUADS ("position") | 1 : 0..N | Squads use only GK/DF/MF/FW, so the 17 detailed position codes have no squad rows. |
| QUALIFIED_TEAMS → MANAGER_APPOINTMENTS ("led by") and MANAGERS → MANAGER_APPOINTMENTS ("appointed") | 1 : 1..N each | Many-to-many between team-tournaments and managers: a manager can lead several teams over the years, and a team can have joint managers (12 cases). |
| TOURNAMENTS → REFEREE_APPOINTMENTS and REFEREES → REFEREE_APPOINTMENTS | 1 : 1..N each | Many-to-many: referees are appointed to tournaments. |
| AWARDS → AWARD_WINNERS ("given") and SQUADS → AWARD_WINNERS ("wins") | 1 : 1..N and 1 : 0..N | Every award was given at least once, but most squad members never win one. The winner references `SQUADS`, not just `PLAYERS`, so the database guarantees the winner was actually in that team's squad at that tournament. |

## 5. ER diagram 2/2: matches and match events

This sheet answers: **what happened in each match, and who did it?**

**The central idea.** `TEAM_APPEARANCES` is "one team in one match" (two rows per match). Most events are tied to it, because a goal, a card, a substitution or a shoot-out kick always belongs to **a team in a match**. Each event *also* points to `SQUADS`, because the person involved must be a registered squad member.

| Relationship (parent → child) | Cardinality | Meaning and why |
|---|---|---|
| TOURNAMENT_STAGES → MATCHES ("contains") | 1 : 1..N | Every stage has matches; each match belongs to one stage. |
| GROUPS → MATCHES ("group match") | **0..1** : 0..N | The only optional parent in the database. A group-stage match belongs to one group, but a knockout match belongs to none, because `group_name` is NULL. |
| STADIUMS → MATCHES ("hosts") | 1 : 1..N | Every stadium in the data hosted at least one match. |
| QUALIFIED_TEAMS → MATCHES ("plays") | 1 : 0..N | Home and away teams must be qualified for that tournament. Drawn once here; the schema has two foreign keys (home, away). |
| MATCHES → TEAM_APPEARANCES ("has two sides") | 1 : 1..N | Every match has exactly two rows, one per team (measured: always 2). |
| TEAM_APPEARANCES → TEAM_APPEARANCES ("opponent") | 1 : 1 | A **self-relationship**: each team's row points to its opponent's row in the same match. The constraint is checked at the end of the transaction, because the two rows are inserted together. |
| QUALIFIED_TEAMS → TEAM_APPEARANCES ("plays") | 1 : 1..N | Every qualified team played at least one match. Austria, which withdrew in 1938 and gave Sweden a walkover, has no 1938 row in `qualified_teams`. |
| MATCHES → REFEREE_APPEARANCES ("officiated") | **1 : 1** | Exactly one referee per match, measured on all 900 matches. |
| REFEREE_APPOINTMENTS → REFEREE_APPEARANCES ("referees") | 1 : 1..N | A referee can only officiate at a tournament they were appointed to, and every appointed referee officiated at least one match. |
| TEAM_APPEARANCES → MANAGER_APPEARANCES ("managed") and MANAGER_APPOINTMENTS → MANAGER_APPEARANCES ("manages") | 1 : 1..N each | Every team in every match had at least one manager (two in 42 cases), and only an appointed manager can appear. |
| TEAM_APPEARANCES → PLAYER_APPEARANCES ("lines up") and SQUADS → PLAYER_APPEARANCES ("plays") | 1 : 0..N each | Optional because line-ups exist only from 1970, and unused squad players have no appearances. |
| POSITIONS → PLAYER_APPEARANCES ("position") | 1 : 1..N | Line-ups use all 21 detailed position codes. |
| TEAM_APPEARANCES / SQUADS → GOALS ("scored in" / "scores") | 1 : 0..N | Optional: 71 matches ended 0-0, and most players never score. |
| TEAM_APPEARANCES / SQUADS → BOOKINGS ("booked in" / "booked") | 1 : 0..N | Optional: no cards before 1970, and many matches and players without cards since. |
| TEAM_APPEARANCES / SQUADS → SUBSTITUTIONS ("made in" / "subbed") | 1 : 0..N | Optional: substitutions are recorded from 1970. |
| TEAM_APPEARANCES / SQUADS → PENALTY_KICKS ("shoot-out" / "takes kick") | 1 : 0..N | Optional: only 30 matches had a shoot-out. |

`SQUADS`, `QUALIFIED_TEAMS`, `TOURNAMENT_STAGES`, `GROUPS`, `POSITIONS` and the two appointment tables appear on **both** ER sheets. They are the links between "who took part" (sheet 1) and "what happened" (sheet 2).

---

## 6. The relational schema diagrams

Each box is a real table. Each row inside shows the **type**, **column name**, key markers and "nullable" where NULL is allowed.

- **PK** = part of the primary key.
- **FK** = part of a foreign key.
- **UK** = a single-column UNIQUE key; multi-column UNIQUE keys are listed in the DDL.

Line labels give the **foreign-key columns**, which is how the relationship is implemented.

### Schema 1/5: reference data, people and tournament structure

- **Tables:** `teams`, `confederations`, `referees`, `tournaments`, `tournament_stages`, `groups`, `players`, `managers`, `stadiums`, `awards`, `positions`.
- **Unconnected boxes:** `players`, `managers`, `stadiums`, `awards` and `positions` have no lines on this sheet because they are **top-level tables** (they reference nothing). Their relationships to other tables are drawn on sheets 2-5.
- **Alternate keys (UK):** `team_name`, `confederation_name` and `code`, `tournament_name`, `year`, `award_name`, `position_name`. Each also uniquely identifies its row.
- **`team_code` has no UK** because Germany and West Germany share DEU.
- **Weak entities:** `tournament_stages` has a composite PK (tournament_id, stage_number), and `groups` has (tournament_id, stage_number, group_name). Group names repeat across stages, so the stage must be in the key.
- **Nullable columns** are exactly where the source had missing values: `given_name` for one-name players, `birth_date` when unknown, and Wikipedia links.

### Schema 2/5: participation and standings

- **Tables:** `qualified_teams`, `host_countries`, `tournament_standings`, `group_standings`, `squads`, `manager_appointments`, `referee_appointments`.
- **Composite keys:** every table here has a composite primary key made of its parents' keys, the classic shape of a **bridge (associative) table**.
- **References through `qualified_teams`:** `host_countries`, `tournament_standings`, `group_standings`, `squads` and `manager_appointments` all reference `qualified_teams` on `(tournament_id, team_id)`, not `teams` alone. The database therefore guarantees, for example, that a host or a squad belongs to a team that actually took part in that tournament.
- **`squads.shirt_number` is nullable:** shirt numbers were unknown (0) for 1930-1950.

### Schema 3/5: matches and appearances

- **`matches`** has 17 columns:
  - `stage_number`, which replaces the source's stage name;
  - `group_name`, nullable for knockout matches;
  - the shoot-out score columns, nullable when there was no shoot-out.
- **Two keys from `matches` to `qualified_teams`:** labelled `tournament_id, home_team_id` and `tournament_id, away_team_id`.
- **`team_appearances` self-loop:** the loop labelled `match_id, opponent_id` is the deferred self-reference.
- **`match_id, tournament_id` lines:** these run from `matches` to `team_appearances`, `referee_appearances` and `manager_appearances`. They keep each table's copy of `tournament_id` consistent with its match.
- **`manager_appearances`** has three incoming lines: the match, the team-in-match, and the appointment. Together they ensure a manager only appears for a team they were appointed to, in a match that team played.

### Schema 4/5: goals, cards and shoot-out kicks

Each event table (`goals`, `bookings`, `penalty_kicks`) has the same three kinds of foreign key:

1. `match_id, tournament_id -> matches`: the event's tournament agrees with its match;
2. `match_id, team_id -> team_appearances`: the team really played in that match;
3. `tournament_id, team_id, player_id -> squads`: the player was in that team's squad for that tournament.

`goals` has **two** lines to `team_appearances`:
- `team_id` is the team **credited** with the goal;
- `player_team_id` is the **scorer's own** team.

They differ only for own goals, and a CHECK in the DDL enforces exactly that. The squad reference uses `player_team_id`, because an own-goal scorer is in their own team's squad.

### Schema 5/5: line-ups, substitutions and awards

- **`player_appearances` and `substitutions`** follow the same three-foreign-key pattern as sheet 4. `player_appearances` also references `positions` (21 detailed codes).
- **`award_winners`** references `awards` and `squads`: an award winner must have been in that team's squad for that tournament.

---

## 7. Patterns to recognise across all sheets

| Pattern | Where | Why it was designed this way |
|---|---|---|
| **Bridge tables** resolving many-to-many | qualified_teams, squads, manager_appointments, referee_appointments, team_appearances, player_appearances, manager_appearances, award_winners | Relational tables cannot store a list in one cell; each pairing becomes a row. |
| **Weak entities** (key includes the parent's key) | tournament_stages, groups | A stage or group only exists within its tournament. |
| **One-to-one** | matches ↔ referee_appearances; team_appearances ↔ its opponent row | One referee per match; exactly one opponent. |
| **Optional parent** (nullable FK) | groups → matches | Knockout matches belong to no group. |
| **Composite foreign keys to bridge tables** | events → squads; hosts/standings → qualified_teams | A stronger rule than referencing `players` or `teams` alone: the person or team must have taken part *in that tournament*. |
| **Controlled redundancy** | `tournament_id` in event tables, kept consistent by `(match_id, tournament_id) -> matches` | Makes the squad rule possible without risking inconsistency. |
| **Lookup table** | positions | Removes the dependency position_code → position_name from two tables (3NF). |

The full DDL behind every diagram is in [`sql/ddl.sql`](../sql/ddl.sql). The design reasoning is in [`README_reasoning.md`](README_reasoning.md) and in `docs/milestone2.pdf`.
