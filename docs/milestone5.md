<div class="titlepage" markdown="1">

# Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data

<div class="sub">DS604 Introduction to Data Management<br>Milestone 5: Views</div>

| Group member | Student ID |
|---|---|
| Devanshi Dudhatra | 202618027 |
| Pujita Sunapu | 202618003 |
| Rahul Saha | 202618037 |

<div class="meta">Due 6 November 2026<br>
Data: The Fjelstul World Cup Database by Joshua C. Fjelstul (CC-BY-SA 4.0)</div>

</div>

## 1. The seven views

`sql/views.sql` defines seven views, built from the strongest Milestone 4 queries. A view stores no data: it is a named `SELECT` that PostgreSQL runs against the current tables every time it is queried. The executed notebook `notebooks/05_views.ipynb` (with `05_views.pdf`) shows `SELECT * ... LIMIT 10` and an example query for each view.

| View | Rows | One row per | Built from | What it gives the user |
|---|---:|---|---|---|
| `v_match_results` | 900 | match | joins of Q07, Q12, Q18 | Readable match list with team names, score text (with shoot-out score), result, winner including shoot-outs, and whether the match went to extra time or penalties |
| `v_top_scorers` | 1,297 | goal scorer | Q10 | All-time ranking counted **per person**, so goals for West Germany and Germany are combined |
| `v_tournament_summary` | 21 | tournament | Q01, Q11, Q17, Q23 | Fact sheet: hosts, format (stage sequence), teams, final four, whether the host won, goals, top scorer(s), extra time, shoot-outs, cards |
| `v_team_performance` | 84 | team | Q01, Q02 | Participation span, W/D/L, goals, win %, titles, finals, top-four finishes, best finish |
| `v_referee_discipline` | 380 | referee | Q22 | Matches, tournaments, and, since 1970, cards, sendings-off and cards per match |
| `v_host_performance` | 22 | host per tournament | Q03 | Each host's record and finish in its own tournament |
| `v_head_to_head` | 1,230 | (team, opponent) pair | Q07 | Any head-to-head in one `WHERE` clause |

`v_match_results` and `v_tournament_summary` also rebuild the readable columns that the normalised schema deliberately does not store (Milestone 2, Section 3.2): score text, result labels, hosts, champion and format flags.

## 2. Testing (local PostgreSQL 18)

| Test | Result |
|---|---|
| `views.sql` runs without errors, and running it again changes nothing | Yes (`CREATE OR REPLACE VIEW`, no DROP) |
| Row counts as expected | 900 / 1,297 / 21 / 84 / 380 / 22 / 1,230 |
| Each view agrees with the query it was built from | 8 / 8 checks pass. Examples: `v_team_performance` = Q02 for all 49 teams, `v_referee_discipline` = Q22, `v_tournament_summary` goals = Q17 for every year, `v_head_to_head` Brazil v Sweden = Q07 |

**A bug found by testing the views.** Comparing `v_top_scorers` with Q10 exposed an error in three Milestone 4 queries (Q10, Q26, Q27). `FETCH FIRST 10 ROWS WITH TIES` only keeps rows tied on the *entire* ORDER BY, and we had added a name as a tie-breaker, so tied rows were cut off. Q10 had dropped three players who also scored 10 goals (Helmut Rahn, Teófilo Cubillas, Thomas Müller), and Q26 had dropped eight stadiums with 9 matches. The queries now rank in a derived table and filter on `rank <= 10`, which keeps all ties. The Milestone 4 notebook was re-run with the corrected queries.

**A practical note.** `CREATE OR REPLACE VIEW` can add columns to a view but cannot change an existing column's data type. If a view definition is later changed in that way, the old view must be dropped first. That needs the right permissions on the course server, so agree it in the group first.

## 3. Why views, and when a table would be better

- **One definition, many users.** Analysts, broadcasters and the final report can query `v_team_performance` instead of copying a 40-line query, and everyone gets the same conventions (for example, a shoot-out counts as a draw).
- **Normalised storage, readable results.** Facts are stored once in the tables; the views present them joined and labelled.
- **Never out of date.** A view is recomputed on every query. A summary *table* would have to be rebuilt after every data change, and could silently disagree with the tables if someone forgot.
- **When a table is better.** If a summary were expensive and read very often on a large database, a `MATERIALIZED VIEW` (results stored and refreshed on demand) or a summary table would be faster. With 57,269 rows every view here answers in milliseconds, so plain views are the right choice.

## 4. View definitions (`sql/views.sql`)

<!-- include: ../sql/views.sql -->

---

*Data: Joshua C. Fjelstul, The Fjelstul World Cup Database, <https://github.com/jfjelstul/worldcup>, CC-BY-SA 4.0. No data values were modified. This document is a derived work under the same licence.*
