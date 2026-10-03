# Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data

## Why every step was taken: the reasoning behind the project

**Group:** Devanshi Dudhatra (202618027), Pujita Sunapu (202618003), Rahul Saha (202618037). DS604 Introduction to Data Management.
**Data:** The Fjelstul World Cup Database by Joshua C. Fjelstul, <https://github.com/jfjelstul/worldcup>, CC-BY-SA 4.0.

This file explains the reasoning behind each step: what we did, why, what we considered instead, and the evidence the decision rests on. The *how-to* is in the main [`README.md`](../README.md); the diagrams are explained in [`README_diagrams.md`](README_diagrams.md), and the reasons for each query in [`README_queries.md`](README_queries.md).

---

## The guiding principles

These five principles drove almost every decision below.

1. **Never assume; verify on the data.** Every key, relationship, column meaning and claimed fact was first checked against the CSV files. The data is the only source, so nothing was invented.
2. **Let the database enforce correctness.** Rules that can be stated as keys, foreign keys or CHECKs were put in the schema, so errors are rejected instead of silently stored.
3. **Make everything rerunnable.** Every step is a script or notebook, so the whole project can be rebuilt from the 27 CSV files, and anyone can repeat it.
4. **Change only `.env` to change databases.** We worked off-campus, so everything was tested locally and written to run unchanged on the course server.
5. **Be safe on a shared server.** Nothing destructive runs outside the local test database.

---

## Step 0: Organising the project

| What we did | Why |
|---|---|
| Moved the 27 CSV files from the project root into `data/` (unchanged) and created `docs/`, `sql/`, `notebooks/`, `diagrams/`, `src/` | The brief prescribed this layout. Keeping the raw data in its own folder, untouched, means the original files are always available to re-check against. |
| Credentials only in `.env`, read through `src/db.py`; `.env.example` with placeholders; `.env` in `.gitignore` | Passwords must never appear in code, notebooks or PDFs. One helper builds the connection for every script, so switching databases means editing one file. `URL.create` escapes special characters in passwords safely. |
| `src/check_connection.py` is read-only | A first test on the course server must not be able to change anything. It also reports whether we may create tables and whether the tables already exist, which are the two things to know before loading. |
| Local PostgreSQL 18 rather than DuckDB | PostgreSQL was already installed and running. Testing on the same engine as the course server is more reliable than testing on a different one, even one with similar SQL. |

## Step 1 (Milestone 0): Understanding the data before designing anything

**What we did.** `src/profile_data.py` profiles all 27 files and writes `docs/dataset_understanding.md`:
- every column's type, meaning, distinct values, nulls and text markers, with sample rows;
- every candidate primary key, checked for uniqueness and missing values;
- every candidate foreign key, including multi-column ones, checked for orphan values, with the cardinality measured;
- data-quality findings, coverage, 36 computed insights and an insights framework.

**Why.** A schema designed from assumptions breaks when the data disagrees, and the brief explicitly said not to invent column names, keys or facts. Profiling first meant every later decision rests on measured evidence. It also produced the insights that the queries were later built on.

**Why every number is computed by the script.** Hand-typed numbers drift and cannot be re-checked. If the data changes, rerunning the script updates the whole document.

**What profiling changed.** These findings shaped the rest of the project:

| Finding | Consequence |
|---|---|
| The files are dated July 2022 but contain **1930-2018 only** | Every document states the real coverage; nothing claims to include 2022. |
| Missing values are written as text ("not available", "not applicable") and shirt number 0 means unknown | Read with `keep_default_na=False` and convert explicitly to NULL (Step 4). |
| Shoot-out matches have a level score, but `result` says "home/away team win" | All win/draw/loss figures are derived from the score, so a shoot-out is a draw (FIFA's convention). |
| Germany and West Germany share team code DEU | team_code cannot be a key; historical teams stay separate (Step 3). |
| Line-ups, cards and substitutions start in 1970; shoot-outs in 1982 | Queries on these topics are restricted to those years and say so. |
| `groups` uses different stage names from `matches` | Link tables through `stage_number`, not `stage_name` (Step 3). |
| Joint managers exist | Manager tables need `manager_id` in their keys. |
| All foreign keys have 0 orphans; goals add up exactly to the scores | The data is trustworthy enough for strict constraints. |

## Step 2 (Milestone 1): Choosing the questions

**What we did.** We described the dataset, grouped the 27 tables into 8 themes, listed the expected relationships, and wrote 30 tentative queries grouped by theme and SQL concept.

**Why we changed the starting list.** We kept all 16 suggested queries but adjusted those the data could not support as written:
- **Finals.** 1950 had no final, so finals are counted as finishing positions 1-2.
- **"Never left the group stage".** 1934 and 1938 had no group stage, so we use "never got past the opening round", based on stage order.
- **In-match penalty conversion.** Missed in-match penalties are not recorded, so this was split into penalty-goal share and shoot-out conversion.
- **Line-up and card queries.** These were restricted to 1970 onwards.

**Why we added 13 more.** The 16 suggestions became 17 queries (the penalty question was split in two); the 13 extra queries come from the insights framework and fill gaps in themes (managers, awards, data quality) and in SQL concepts the list did not yet exercise (EXCEPT, ROW_NUMBER, self-join, integrity checks). The detailed reasoning per query is in [`README_queries.md`](README_queries.md).

**Why drop some ideas entirely.** Assists, attendance, possession, fastest goals in seconds and in-match penalty conversion are not in the data. Writing such queries would mean inventing data.

## Step 3 (Milestone 2): Designing the schema

### Why normalise at all

The CSV files are heavily denormalised: team names appear in 16 tables, and tournament names in almost all of them. Storing a fact in many places invites update anomalies: renaming a team would mean changing 16 tables, and missing one makes the database contradict itself. We normalised to **third normal form**:

- **1NF.** `players.list_tournaments` held lists like "1998, 2002, 2006", so it was removed; `squads` holds the same information properly.
- **2NF/3NF.** Copies of other tables' attributes were removed (names, codes, stadium location, confederation), together with values derived from other columns of the same row (score text, margins, result labels, win flags, minute labels, points, `sending_off`, `going_off`, `substitute`).

**Why we were confident dropping columns.** For every dropped column, `clean.verify_dropped_columns()` proves on the real data that it can be recomputed exactly from what we keep: 33 checks, all passing. Nothing was lost, and the views of Step 6 rebuild the readable versions.

### Why the dataset's own ids are the primary keys

| Option | Why we did or did not choose it |
|---|---|
| **Natural ids from the source** (`T-03`, `M-1930-01`) | **Chosen.** Verified unique and never missing; stable; meaningful when checking results; and child tables can be appended directly with `to_sql`. |
| Surrogate integer keys (`SERIAL`) | Would force us to look up and replace every foreign key in 20 child tables during loading. More work and more room for error, with no benefit here. |
| `key_id` (in every CSV) | Rejected: it is only the row position in each file and identifies nothing real. |
| Names or codes | Rejected: not unique (two "Olympiastadion"s, DEU shared by two teams, 711 distinct match names for 900 matches). |

### Why composite keys

Bridge tables (`qualified_teams`, `squads`, `manager_appointments`, ...) and weak entities (`tournament_stages`, `groups`) are identified by a combination of their parents. A squad entry *is* "this player, in this team, at this tournament". Joint managers (12 cases) force `manager_id` into the manager keys, and group names repeating across stages force `stage_number` into the group key.

### Why we deliberately kept one redundancy

Strict 3NF would remove `tournament_id` from `goals`, `bookings` and the other event tables, because it follows from `match_id`. We kept it because it makes a much stronger rule enforceable: the foreign key `(tournament_id, team_id, player_id) -> squads` guarantees that **every scorer, booked player, substitute and shoot-out taker was in that team's squad for that tournament**. A second foreign key, `(match_id, tournament_id) -> matches`, makes it impossible for the extra column to disagree with the match. The redundancy is enforced, not trusted.

`team_appearances` is likewise a derived, team-centred copy of `matches`. We kept it because per-team questions become simple, and constrained it:
- each team must have qualified for that tournament;
- a self-referencing foreign key requires the opponent's row to exist for the same match.

That self-reference is **deferred to COMMIT**, because the two rows of a match are inserted together and neither can exist first.

### Why stages are linked by number

`groups` and `group_standings` call the first stage "first round" (1950) or "first group stage" (1974-1982), where `tournament_stages` and `matches` say "group stage". Joining on the name would silently lose those groups. So `stage_name` is stored only in `tournament_stages`, and everything else links through `(tournament_id, stage_number)`.

### Why historical teams stay separate

West Germany, the Soviet Union, Yugoslavia and others are kept as recorded. Merging them (for example, crediting Germany with West Germany's titles) is FIFA's convention, not something in the dataset. Adding a lineage table would mean importing outside knowledge, so queries state the convention where it matters instead. The same reasoning applies to the confederation column, which is each team's *current* confederation.

### Why NULL instead of placeholder values

Text markers, shirt number 0, and 0-0 shoot-out scores for matches without a shoot-out all look like real values. As NULL:
- AVG and COUNT(column) skip them correctly;
- DATE and SMALLINT types are possible;
- CHECKs such as "shoot-out scores exist exactly when there was a shoot-out" can be written.

### Why so many CHECK and UNIQUE constraints

They encode football rules the data must obey:
- a shoot-out implies extra time and a level score;
- a replayed match was drawn;
- an own goal is exactly the case where the credited team differs from the scorer's team;
- shirt numbers are unique in a squad;
- ids agree with their year.

Each was tested: the real data passes all of them, and 14 deliberately invalid changes were all rejected.

### Why these indexes

PostgreSQL indexes primary and unique keys automatically, but not foreign keys. We added 21 indexes on foreign-key columns that the queries join or filter on and that are not already the first column of an index. The dataset is small, so the gain is modest, but the choice follows standard practice and scales.

### Why the DDL never drops anything

`ddl.sql` uses `CREATE TABLE IF NOT EXISTS` and contains no DROP, TRUNCATE or DELETE, so running it on the shared course server cannot destroy anything. Resetting is a separate file, `reset_local.sql`, which the scripts refuse to run unless the host is local.

### Why the diagrams are generated from the database

Hand-drawn diagrams drift from the DDL. `src/make_diagrams.py` reads tables, columns and foreign keys from the live database catalog and **measures** each relationship's cardinality on the loaded data, so the diagrams always match what was built. See [`README_diagrams.md`](README_diagrams.md).

## Step 4 (Milestone 3): Cleaning and loading

**Why `pd.read_csv` → clean → `to_sql(if_exists="append")`.** This is the course rule. It also has a sound reason: appending into tables created by our DDL forces the data to fit *our* types, keys and constraints. If pandas created the tables itself, it would guess the types and add no keys at all.

**Why the DDL runs first, and why the load order matters.** Append mode needs existing tables. Foreign keys need parent rows first: tournaments before stages, before groups, before matches, before goals.

**Why each cleaning step:**

| Step | Count | Reason |
|---|---:|---|
| Text markers → NULL | 11,891 cells | They mean "missing"; as text they would break types and averages |
| Shirt 0 → NULL | 1,188 | 0 means unknown, and the DDL allows only 1-99 |
| Look up `matches.stage_number` | 900 rows | The schema links matches to stages and groups by number (see Step 3) |
| Align group names | 18 matches | Two source inconsistencies (1982 "Group 1-4" vs "Group A-D"; 1950 final-round matches with no group name). **Matched by the teams involved, never assumed**, and only unique matches are accepted |
| NULL shoot-out scores without a shoot-out | 5,220 cells | A stored 0-0 would look like a real shoot-out |
| Keep normalised columns | 243 columns dropped | Step 3; all proven redundant |
| Convert types | 31 columns | BOOLEAN, DATE and TIME allow CHECKs and date arithmetic (ages) |

**Why one transaction.** On a shared server, a load that fails halfway would leave a partly filled database, and rerunning it would fail on duplicate keys. Loading all 27 tables in one transaction means everything is committed or nothing is.

**Why the loader refuses non-empty tables.** Appending twice would duplicate data. Refusing is safer than deleting, because deleting on the server is forbidden.

**Why integrity checks after loading.** Constraints cannot express everything, for example "goals add up to the score". Seven SQL checks confirm the loaded database is consistent, and one of them found the 1950 group-name gap.

## Step 5 (Milestone 4): Writing and validating the queries

**Why each query has a comment block.** The business question, SQL concepts and expected result shape are stated *before* the SQL. That makes the intent reviewable and a wrong result easy to spot.

**Why two global conventions.**
- **A shoot-out counts as a draw.** This matches FIFA's records. Using the source's `result` column would give Brazil 76 wins instead of 73.
- **Historical teams are separate.** This is consistent with the schema; queries say when this affects a result.

**Why validate against pandas on the raw CSVs.** A check that goes through the same database and cleaning code would repeat any error in them. Computing the same figure directly from the original files, and comparing with well-known facts (Klose 16 goals, 2,548 goals in total, Hungary 10-1 El Salvador), is independent. The 18 checks gave 16 matches and 2 documented differences.

**Why the notebook is generated from `queries.sql`.** The SQL exists in one place. The notebook, the final report and the views' cross-checks all read the same file, so they cannot drift apart.

## Step 6 (Milestone 5): Views

**Why views.** Several queries answer questions people ask repeatedly, such as a team's record, a tournament's facts or a head-to-head. A view saves the definition once:
- every user gets the same conventions;
- there is no copying of 40-line queries;
- because views store no data, they can never fall out of date.

**Why these seven.**
- **The five requested themes:** top scorers, tournament summary, team performance, referee discipline, head-to-head and host performance.
- **`v_match_results`:** puts back the readable columns the normalised schema deliberately does not store (score text, result labels).
- **Person-level scorers:** `v_top_scorers` counts per *person*, which addresses the historical-team split (a player who scored for West Germany and Germany gets one row).

**Why `CREATE OR REPLACE VIEW` and no ORDER BY inside views.** The views can be re-run safely on the server, and the user chooses the order when querying.

**Why we compared each view with its source query.** It is a second independent check, and it found a real bug. `FETCH FIRST 10 ROWS WITH TIES` with a name tie-breaker had silently dropped tied rows in Q10, Q26 and Q27. The fix ranks first and keeps every row with `rank <= 10`.

## Step 7: Documentation and the final package

| What | Why |
|---|---|
| PDFs produced with headless Chrome; diagrams with Mermaid | LaTeX and Graphviz were not installed; Chrome was. This avoided heavy installs while giving clean, reproducible output. |
| `final_report.pdf` built by a script from a source file plus live query results | The report always shows the current results; nothing is pasted by hand. |
| Interpretations stored once (`src/report_content.py`) | The notebook and the report share the same text. |
| Every document carries the title and the CC-BY-SA attribution with the list of modifications | The brief required it, and the licence requires attribution, a statement of changes and sharing under the same licence. |
| `university_server_guide` | We could not test on the course server, so a precise, safe procedure for doing it later was the next best thing. |
| Secret scan of all files and PDFs | To confirm the password appears nowhere before anything is submitted. |

---

## What we would do differently or next

- **Confirm two source quirks with outside sources.** The 1998 joint-manager nationalities and the one ambiguous booking would need checking against an external source before changing anything; until then they are reported, not "fixed".
- **Add an optional lineage table.** A clearly labelled lineage table (West Germany → Germany, ...) would let users choose FIFA's successor convention explicitly.
- **Enforce cross-table rules with triggers.** Rules such as "match date within tournament dates" are currently checked by queries; triggers would enforce them on insert.
- **Re-run everything on the course server** once on the university network. Only `.env` changes.
