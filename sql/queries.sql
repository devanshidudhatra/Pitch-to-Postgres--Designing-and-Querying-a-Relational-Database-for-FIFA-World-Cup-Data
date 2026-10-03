-- =============================================================================
-- Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
-- DS604 Introduction to Data Management - Milestone 4: Analytical queries
-- Group: Devanshi Dudhatra (202618027), Pujita Sunapu (202618003), Rahul Saha (202618037)
--
-- Data: Joshua C. Fjelstul, The Fjelstul World Cup Database, https://github.com/jfjelstul/worldcup,
--       CC-BY-SA 4.0. Coverage: the 21 men's World Cups 1930-2018.
--
-- Conventions used in every query:
--   * Win / draw / loss come from the score (goals_for vs goals_against). A match decided by a
--     penalty shoot-out therefore counts as a DRAW, as in FIFA's records.
--   * Teams are counted by team_id as recorded: West Germany and Germany (also Soviet Union / Russia,
--     Yugoslavia / Serbia ...) are separate teams unless a query says otherwise.
--   * Cards, line-ups and substitutions exist from 1970; penalty shoot-outs from 1982.
--   * Player display name = given name + family name (players known by one name have only a family name).
-- Standard SQL, PostgreSQL-compatible. No query modifies data.
-- =============================================================================


-- =============================================================================
-- Q01. Most successful teams
-- Business question: Which teams are the most successful, counting titles, final appearances
--   (top two finishes) and top-four finishes?
-- SQL concepts: INNER JOIN, GROUP BY, conditional aggregation SUM(CASE ...), multi-column ORDER BY
-- Expected result: one row per team that ever finished in the top four (25 rows):
--   team_name, titles, runners_up, finals (top two), top_four. Brazil first with 5 titles.
--   Note: 1950 had no final match; its top two (Uruguay, Brazil) come from the final round group.
-- =============================================================================
SELECT t.team_name,
       SUM(CASE WHEN s.position = 1 THEN 1 ELSE 0 END)  AS titles,
       SUM(CASE WHEN s.position = 2 THEN 1 ELSE 0 END)  AS runners_up,
       SUM(CASE WHEN s.position <= 2 THEN 1 ELSE 0 END) AS finals,
       COUNT(*)                                         AS top_four
FROM tournament_standings s
JOIN teams t ON t.team_id = s.team_id
GROUP BY t.team_name
ORDER BY titles DESC, finals DESC, top_four DESC, t.team_name;


-- =============================================================================
-- Q02. All-time team records
-- Business question: What is each team's all-time World Cup record (played, won, drawn, lost,
--   goals, win percentage), for teams with at least 10 matches?
-- SQL concepts: CTE, CASE, GROUP BY with HAVING, arithmetic on aggregates
-- Expected result: one row per team with >= 10 matches (49 rows), ordered by win percentage:
--   team_name, played, won, drawn, lost, goals_for, goals_against, goal_diff, win_pct.
-- =============================================================================
WITH results AS (
    SELECT ta.team_id,
           ta.goals_for,
           ta.goals_against,
           CASE WHEN ta.goals_for > ta.goals_against THEN 1 ELSE 0 END AS won,
           CASE WHEN ta.goals_for = ta.goals_against THEN 1 ELSE 0 END AS drawn,
           CASE WHEN ta.goals_for < ta.goals_against THEN 1 ELSE 0 END AS lost
    FROM team_appearances ta
)
SELECT t.team_name,
       COUNT(*)                                   AS played,
       SUM(r.won)                                 AS won,
       SUM(r.drawn)                               AS drawn,
       SUM(r.lost)                                AS lost,
       SUM(r.goals_for)                           AS goals_for,
       SUM(r.goals_against)                       AS goals_against,
       SUM(r.goals_for) - SUM(r.goals_against)    AS goal_diff,
       ROUND(100.0 * SUM(r.won) / COUNT(*), 1)    AS win_pct
FROM results r
JOIN teams t ON t.team_id = r.team_id
GROUP BY t.team_name
HAVING COUNT(*) >= 10
ORDER BY win_pct DESC, played DESC;


-- =============================================================================
-- Q03. Host-country advantage
-- Business question: Do host nations do better than other teams? Compare win, draw and loss rates
--   and average goal difference, overall and for two eras (1930-1978, 1982-2018).
-- SQL concepts: CTE, LEFT JOIN (to flag hosts), CASE, GROUP BY, UNION ALL, AVG of 0/1 values
-- Expected result: 6 rows: (host | other teams) x (1930-1978 | 1982-2018 | all years):
--   side, era, matches, win_pct, draw_pct, loss_pct, avg_goal_diff.
-- =============================================================================
WITH flagged AS (
    SELECT CASE WHEN h.team_id IS NOT NULL THEN 'host' ELSE 'other teams' END     AS side,
           CASE WHEN tr.year < 1982 THEN '1930-1978' ELSE '1982-2018' END           AS era,
           ta.goals_for - ta.goals_against                                          AS goal_diff,
           CASE WHEN ta.goals_for > ta.goals_against THEN 1.0 ELSE 0.0 END          AS won,
           CASE WHEN ta.goals_for = ta.goals_against THEN 1.0 ELSE 0.0 END          AS drawn,
           CASE WHEN ta.goals_for < ta.goals_against THEN 1.0 ELSE 0.0 END          AS lost
    FROM team_appearances ta
    JOIN tournaments tr ON tr.tournament_id = ta.tournament_id
    LEFT JOIN host_countries h
           ON h.tournament_id = ta.tournament_id AND h.team_id = ta.team_id
)
SELECT side, era, COUNT(*) AS matches,
       ROUND(100 * AVG(won), 1)   AS win_pct,
       ROUND(100 * AVG(drawn), 1) AS draw_pct,
       ROUND(100 * AVG(lost), 1)  AS loss_pct,
       ROUND(AVG(goal_diff), 2)   AS avg_goal_diff
FROM flagged
GROUP BY side, era
UNION ALL
SELECT side, 'all years', COUNT(*),
       ROUND(100 * AVG(won), 1), ROUND(100 * AVG(drawn), 1), ROUND(100 * AVG(lost), 1),
       ROUND(AVG(goal_diff), 2)
FROM flagged
GROUP BY side
ORDER BY side, era;


-- =============================================================================
-- Q04. Confederation performance by decade
-- Business question: How does each confederation perform, decade by decade (win percentage of
--   its teams' matches)?
-- SQL concepts: 3-table JOIN, GROUP BY on an expression (decade), conditional aggregation into
--   columns (pivot), AVG ignores NULLs
-- Expected result: one row per decade with a World Cup (8 rows: 1930s, then 1950s-2010s): decade, matches, then win_pct for
--   UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC (NULL when the confederation had no team that decade).
--   Caveat: confederation is each team's CURRENT one (e.g. Australia counts as AFC throughout).
-- =============================================================================
WITH res AS (
    SELECT (tr.year / 10) * 10 AS decade,
           c.confederation_code AS conf,
           CASE WHEN ta.goals_for > ta.goals_against THEN 100.0 ELSE 0.0 END AS win
    FROM team_appearances ta
    JOIN tournaments tr    ON tr.tournament_id = ta.tournament_id
    JOIN teams t           ON t.team_id = ta.team_id
    JOIN confederations c  ON c.confederation_id = t.confederation_id
)
SELECT decade,
       COUNT(*) / 2 AS matches,
       ROUND(AVG(CASE WHEN conf = 'UEFA'     THEN win END), 1) AS uefa_win_pct,
       ROUND(AVG(CASE WHEN conf = 'CONMEBOL' THEN win END), 1) AS conmebol_win_pct,
       ROUND(AVG(CASE WHEN conf = 'CONCACAF' THEN win END), 1) AS concacaf_win_pct,
       ROUND(AVG(CASE WHEN conf = 'CAF'      THEN win END), 1) AS caf_win_pct,
       ROUND(AVG(CASE WHEN conf = 'AFC'      THEN win END), 1) AS afc_win_pct,
       ROUND(AVG(CASE WHEN conf = 'OFC'      THEN win END), 1) AS ofc_win_pct
FROM res
GROUP BY decade
ORDER BY decade;


-- =============================================================================
-- Q05. Teams that never got past the opening round
-- Business question: Which teams have never progressed beyond the opening round (stage 1) of any
--   World Cup they played in?
-- SQL concepts: correlated NOT EXISTS subquery, JOIN, GROUP BY, MIN/MAX
-- Expected result: one row per such team (30 rows): team_name, appearances, matches, first_year,
--   last_year; most appearances first. Stage order (stage_number) is used rather than the label
--   'group stage', so the knockout-only tournaments of 1934 and 1938 are handled correctly.
-- =============================================================================
SELECT t.team_name,
       COUNT(DISTINCT q.tournament_id) AS appearances,
       (SELECT COUNT(*) FROM team_appearances x WHERE x.team_id = t.team_id) AS matches,
       MIN(tr.year) AS first_year,
       MAX(tr.year) AS last_year
FROM qualified_teams q
JOIN teams t        ON t.team_id = q.team_id
JOIN tournaments tr ON tr.tournament_id = q.tournament_id
WHERE NOT EXISTS (
        SELECT 1
        FROM team_appearances ta
        JOIN matches m ON m.match_id = ta.match_id
        WHERE ta.team_id = q.team_id
          AND m.stage_number > 1)
GROUP BY t.team_id, t.team_name
ORDER BY appearances DESC, matches DESC, t.team_name;


-- =============================================================================
-- Q06. Top-four finishers that never won the title
-- Business question: Which teams have finished in the top four but never won the World Cup, and
--   what was their best finish?
-- SQL concepts: set operation EXCEPT inside a CTE, JOIN, GROUP BY, STRING_AGG with ORDER BY
-- Expected result: one row per team (16 rows): team_name, best_finish, top_four_finishes,
--   years; best finish first (runners-up: Netherlands, Czechoslovakia, Hungary, Sweden, Croatia).
-- =============================================================================
WITH never_won AS (
    SELECT team_id FROM tournament_standings
    EXCEPT
    SELECT team_id FROM tournament_standings WHERE position = 1
)
SELECT t.team_name,
       MIN(s.position) AS best_finish,
       COUNT(*)        AS top_four_finishes,
       STRING_AGG(CAST(tr.year AS VARCHAR(4)) || ' (' || CAST(s.position AS VARCHAR(1)) || ')', ', '
                  ORDER BY tr.year) AS years_and_positions
FROM never_won n
JOIN tournament_standings s ON s.team_id = n.team_id
JOIN teams t                ON t.team_id = n.team_id
JOIN tournaments tr         ON tr.tournament_id = s.tournament_id
GROUP BY t.team_name
ORDER BY best_finish, top_four_finishes DESC, t.team_name;


-- =============================================================================
-- Q07. Head-to-head record between two teams (example: Brazil v Sweden)
-- Business question: What is the complete World Cup head-to-head record between two chosen teams?
--   (Change the two names in the params CTE to compare any pair.)
-- SQL concepts: SELF-JOIN of team_appearances (a team's row paired with its opponent's row in the
--   same match), parameter CTE, CASE, running totals with window SUM() OVER
-- Expected result: one row per meeting in date order (7 rows for Brazil v Sweden): year, stage,
--   score from team A's view, result, and running wins/draws for each side.
-- =============================================================================
WITH params AS (
    SELECT 'Brazil' AS team_a, 'Sweden' AS team_b
),
h2h AS (
    SELECT m.match_date, tr.year, st.stage_name,
           a.goals_for AS a_goals, b.goals_for AS b_goals,
           CASE WHEN a.goals_for > b.goals_for THEN 1 ELSE 0 END AS a_win,
           CASE WHEN a.goals_for = b.goals_for THEN 1 ELSE 0 END AS draw,
           CASE WHEN a.goals_for < b.goals_for THEN 1 ELSE 0 END AS b_win
    FROM team_appearances a
    JOIN team_appearances b      ON b.match_id = a.match_id AND b.team_id <> a.team_id   -- self-join
    JOIN teams ta                ON ta.team_id = a.team_id
    JOIN teams tb                ON tb.team_id = b.team_id
    JOIN params p                ON ta.team_name = p.team_a AND tb.team_name = p.team_b
    JOIN matches m               ON m.match_id = a.match_id
    JOIN tournaments tr          ON tr.tournament_id = m.tournament_id
    JOIN tournament_stages st    ON st.tournament_id = m.tournament_id AND st.stage_number = m.stage_number
)
SELECT year, stage_name,
       CAST(a_goals AS VARCHAR(2)) || '-' || CAST(b_goals AS VARCHAR(2)) AS score_a_b,
       CASE WHEN a_win = 1 THEN 'team A win' WHEN draw = 1 THEN 'draw' ELSE 'team B win' END AS result,
       SUM(a_win) OVER (ORDER BY match_date) AS a_wins_so_far,
       SUM(draw)  OVER (ORDER BY match_date) AS draws_so_far,
       SUM(b_win) OVER (ORDER BY match_date) AS b_wins_so_far
FROM h2h
ORDER BY match_date;


-- =============================================================================
-- Q08. Cumulative titles over time
-- Business question: How did each country's title count build up over time, and who led the
--   all-time table after each tournament?
-- SQL concepts: window functions - running total COUNT(*) OVER (PARTITION BY ... ORDER BY ...),
--   correlated subquery for the leader
-- Expected result: one row per tournament (21 rows): year, champion, champion_titles_so_far,
--   most_titles_after (the team(s) with most titles after that tournament).
-- =============================================================================
WITH champs AS (
    SELECT tr.year, s.team_id, t.team_name,
           COUNT(*) OVER (PARTITION BY s.team_id ORDER BY tr.year
                          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS titles_so_far
    FROM tournament_standings s
    JOIN tournaments tr ON tr.tournament_id = s.tournament_id
    JOIN teams t        ON t.team_id = s.team_id
    WHERE s.position = 1
)
SELECT c.year,
       c.team_name     AS champion,
       c.titles_so_far AS champion_titles_so_far,
       (SELECT STRING_AGG(x.team_name || ' ' || CAST(x.n AS VARCHAR(2)), ', ' ORDER BY x.team_name)
        FROM (SELECT team_name, COUNT(*) AS n FROM champs c2 WHERE c2.year <= c.year GROUP BY team_name) x
        WHERE x.n = (SELECT MAX(n2) FROM (SELECT COUNT(*) AS n2 FROM champs c3
                                          WHERE c3.year <= c.year GROUP BY team_name) y)
       ) AS most_titles_after
FROM champs c
ORDER BY c.year;


-- =============================================================================
-- Q09. Comebacks: winning after conceding the first goal
-- Business question: Which teams most often won a match after conceding the first goal, and how
--   often do they manage it?
-- SQL concepts: CTE, window function ROW_NUMBER() OVER (PARTITION BY match ORDER BY minute) to find
--   each match's first goal, JOIN, conditional aggregation, HAVING
-- Expected result: one row per team that conceded first at least 5 times (55 rows): team_name,
--   conceded_first, comeback_wins, comeback_draws, comeback_win_pct; most comeback wins first.
-- =============================================================================
WITH ordered_goals AS (
    SELECT g.match_id, g.team_id,
           ROW_NUMBER() OVER (PARTITION BY g.match_id
                              ORDER BY g.minute_regulation, g.minute_stoppage, g.goal_id) AS rn
    FROM goals g
),
first_goal AS (
    SELECT match_id, team_id AS first_scoring_team FROM ordered_goals WHERE rn = 1
)
SELECT t.team_name,
       COUNT(*) AS conceded_first,
       SUM(CASE WHEN ta.goals_for > ta.goals_against THEN 1 ELSE 0 END) AS comeback_wins,
       SUM(CASE WHEN ta.goals_for = ta.goals_against THEN 1 ELSE 0 END) AS comeback_draws,
       ROUND(100.0 * SUM(CASE WHEN ta.goals_for > ta.goals_against THEN 1 ELSE 0 END) / COUNT(*), 1)
           AS comeback_win_pct
FROM team_appearances ta
JOIN first_goal f ON f.match_id = ta.match_id AND f.first_scoring_team <> ta.team_id
JOIN teams t      ON t.team_id = ta.team_id
GROUP BY t.team_name
HAVING COUNT(*) >= 5
ORDER BY comeback_wins DESC, comeback_win_pct DESC, t.team_name;


-- =============================================================================
-- Q10. All-time top 10 goal scorers (own goals excluded)
-- Business question: Who are the World Cup's all-time top 10 goal scorers?
-- SQL concepts: JOIN, WHERE filter, GROUP BY, window function RANK() in a derived table, filtering
--   on the rank (so players tied for a place are all kept), STRING_AGG(DISTINCT ...)
-- Expected result: every player ranked 10th or better, ties included: rank, player, team, goals,
--   penalties, tournaments, matches_scored_in. Miroslav Klose first with 16.
-- =============================================================================
SELECT *
FROM (
SELECT RANK() OVER (ORDER BY COUNT(*) DESC)                  AS rank,
       COALESCE(p.given_name || ' ', '') || p.family_name    AS player,
       STRING_AGG(DISTINCT t.team_name, ' / ')               AS team,
       COUNT(*)                                              AS goals,
       SUM(CASE WHEN g.penalty THEN 1 ELSE 0 END)            AS penalties,
       COUNT(DISTINCT g.tournament_id)                       AS tournaments,
       COUNT(DISTINCT g.match_id)                            AS matches_scored_in
FROM goals g
JOIN players p ON p.player_id = g.player_id
JOIN teams t   ON t.team_id = g.player_team_id
WHERE NOT g.own_goal
GROUP BY p.player_id, p.given_name, p.family_name
) ranked
WHERE rank <= 10
ORDER BY rank, player;


-- =============================================================================
-- Q11. Top scorer of each tournament vs the official Golden Boot
-- Business question: Who scored the most goals at each tournament, and does that agree with the
--   official Golden Boot award?
-- SQL concepts: CTEs, window function RANK() OVER (PARTITION BY tournament ORDER BY goals DESC),
--   correlated scalar subqueries, set comparison with EXCEPT inside NOT EXISTS
-- Expected result: one row per tournament (21 rows, newest first): year, top_scorers (ties listed),
--   goals, golden_boot (official winner(s)), agreement ('same' / 'different').
-- =============================================================================
WITH tally AS (
    SELECT tournament_id, player_id, COUNT(*) AS goals
    FROM goals
    WHERE NOT own_goal
    GROUP BY tournament_id, player_id
),
top_scorers AS (
    SELECT tournament_id, player_id, goals
    FROM (SELECT tally.*, RANK() OVER (PARTITION BY tournament_id ORDER BY goals DESC) AS rnk
          FROM tally) r
    WHERE rnk = 1
),
golden_boot AS (
    SELECT aw.tournament_id, aw.player_id
    FROM award_winners aw
    JOIN awards a ON a.award_id = aw.award_id
    WHERE a.award_name = 'Golden Boot'
)
SELECT tr.year,
       (SELECT STRING_AGG(COALESCE(p.given_name || ' ', '') || p.family_name, ', '
                          ORDER BY p.family_name)
        FROM top_scorers ts JOIN players p ON p.player_id = ts.player_id
        WHERE ts.tournament_id = tr.tournament_id)                        AS top_scorers,
       (SELECT MAX(goals) FROM top_scorers ts WHERE ts.tournament_id = tr.tournament_id) AS goals,
       (SELECT STRING_AGG(COALESCE(p.given_name || ' ', '') || p.family_name, ', '
                          ORDER BY p.family_name)
        FROM golden_boot gb JOIN players p ON p.player_id = gb.player_id
        WHERE gb.tournament_id = tr.tournament_id)                        AS golden_boot,
       CASE WHEN NOT EXISTS (SELECT player_id FROM top_scorers WHERE tournament_id = tr.tournament_id
                             EXCEPT
                             SELECT player_id FROM golden_boot WHERE tournament_id = tr.tournament_id)
             AND NOT EXISTS (SELECT player_id FROM golden_boot WHERE tournament_id = tr.tournament_id
                             EXCEPT
                             SELECT player_id FROM top_scorers WHERE tournament_id = tr.tournament_id)
            THEN 'same' ELSE 'different' END                               AS agreement
FROM tournaments tr
ORDER BY tr.year DESC;


-- =============================================================================
-- Q12. Hat-tricks
-- Business question: Which players scored three or more goals in a single match, and who holds the
--   record for most goals in one match?
-- SQL concepts: multi-table JOIN, GROUP BY, HAVING COUNT(*) >= 3
-- Expected result: one row per hat-trick (52 rows), most goals first: year, player, team, opponent,
--   final score, stage, goals. Oleg Salenko's 5 goals (1994) first.
-- =============================================================================
SELECT tr.year,
       COALESCE(p.given_name || ' ', '') || p.family_name               AS player,
       t.team_name                                                      AS team,
       o.team_name                                                      AS opponent,
       CAST(ta.goals_for AS VARCHAR(2)) || '-' || CAST(ta.goals_against AS VARCHAR(2)) AS final_score,
       st.stage_name,
       COUNT(*)                                                         AS goals
FROM goals g
JOIN players p             ON p.player_id = g.player_id
JOIN team_appearances ta   ON ta.match_id = g.match_id AND ta.team_id = g.player_team_id
JOIN teams t               ON t.team_id = ta.team_id
JOIN teams o               ON o.team_id = ta.opponent_id
JOIN matches m             ON m.match_id = g.match_id
JOIN tournament_stages st  ON st.tournament_id = m.tournament_id AND st.stage_number = m.stage_number
JOIN tournaments tr        ON tr.tournament_id = m.tournament_id
WHERE NOT g.own_goal
GROUP BY tr.year, m.match_id, p.player_id, p.given_name, p.family_name, t.team_name, o.team_name,
         ta.goals_for, ta.goals_against, st.stage_name
HAVING COUNT(*) >= 3
ORDER BY goals DESC, tr.year, player;


-- =============================================================================
-- Q13. Goals scored by substitutes (1970 onwards)
-- Business question: How many goals were scored by substitutes at each tournament since 1970, and
--   what share of all goals is that?
-- SQL concepts: JOIN on a composite key (match_id, player_id), CASE, GROUP BY, ratio
-- Expected result: one row per tournament 1970-2018 (13 rows, newest first): year, goals,
--   substitute_goals, substitute_pct. Line-ups exist only from 1970, so earlier years cannot appear.
-- =============================================================================
SELECT tr.year,
       COUNT(*)                                                       AS goals,
       SUM(CASE WHEN NOT pa.starter THEN 1 ELSE 0 END)                AS substitute_goals,
       ROUND(100.0 * SUM(CASE WHEN NOT pa.starter THEN 1 ELSE 0 END) / COUNT(*), 1) AS substitute_pct
FROM goals g
JOIN player_appearances pa ON pa.match_id = g.match_id AND pa.player_id = g.player_id
JOIN tournaments tr        ON tr.tournament_id = g.tournament_id
WHERE NOT g.own_goal
GROUP BY tr.year
ORDER BY tr.year DESC;


-- =============================================================================
-- Q14. Average squad age by position and tournament
-- Business question: How old are World Cup squads, by position, and how has that changed?
-- SQL concepts: date arithmetic (date - date = days), conditional aggregation pivot, AVG ignoring
--   NULLs, COUNT(*) vs COUNT(column) to report missing birth dates
-- Expected result: one row per tournament (21 rows, newest first): year, avg age of GK, DF, MF,
--   FW and all players at the tournament's start date, and players_without_birth_date.
-- =============================================================================
WITH ages AS (
    SELECT tr.year, s.position_code,
           (tr.start_date - p.birth_date) / 365.25 AS age     -- NULL when the birth date is unknown
    FROM squads s
    JOIN players p      ON p.player_id = s.player_id
    JOIN tournaments tr ON tr.tournament_id = s.tournament_id
)
SELECT year,
       ROUND(AVG(CASE WHEN position_code = 'GK' THEN age END), 1) AS gk_avg_age,
       ROUND(AVG(CASE WHEN position_code = 'DF' THEN age END), 1) AS df_avg_age,
       ROUND(AVG(CASE WHEN position_code = 'MF' THEN age END), 1) AS mf_avg_age,
       ROUND(AVG(CASE WHEN position_code = 'FW' THEN age END), 1) AS fw_avg_age,
       ROUND(AVG(age), 1)                                         AS all_avg_age,
       COUNT(*) - COUNT(age)                                      AS players_without_birth_date
FROM ages
GROUP BY year
ORDER BY year DESC;


-- =============================================================================
-- Q15. Most World Cup appearances for each nation (1970 onwards)
-- Business question: Who has made the most World Cup appearances for each national team?
-- SQL concepts: CTE, window function ROW_NUMBER() OVER (PARTITION BY team ORDER BY ...), filter on
--   the row number, JOIN
-- Expected result: one row per team that played from 1970 on (81 rows), most appearances first:
--   team_name, player, appearances, tournaments, as_starter. Miroslav Klose first (24 for Germany).
--   Ties are broken by tournaments, then player id. Note: the overall record holder Lothar Matthaeus
--   (25) does not appear, because his matches are split between West Germany and Germany.
-- =============================================================================
WITH apps AS (
    SELECT team_id, player_id,
           COUNT(*)                                        AS appearances,
           COUNT(DISTINCT tournament_id)                   AS tournaments,
           SUM(CASE WHEN starter THEN 1 ELSE 0 END)        AS as_starter
    FROM player_appearances
    GROUP BY team_id, player_id
),
ranked AS (
    SELECT apps.*,
           ROW_NUMBER() OVER (PARTITION BY team_id
                              ORDER BY appearances DESC, tournaments DESC, player_id) AS rn
    FROM apps
)
SELECT t.team_name,
       COALESCE(p.given_name || ' ', '') || p.family_name AS player,
       r.appearances, r.tournaments, r.as_starter
FROM ranked r
JOIN teams t   ON t.team_id = r.team_id
JOIN players p ON p.player_id = r.player_id
WHERE r.rn = 1
ORDER BY r.appearances DESC, t.team_name;


-- =============================================================================
-- Q16. Players who represented more than one national team
-- Business question: Which players were in World Cup squads for more than one national team?
-- SQL concepts: GROUP BY, HAVING COUNT(DISTINCT ...) > 1, STRING_AGG with ORDER BY
-- Expected result: one row per player (34 rows): player, teams, squads (team (year) list).
--   Most are "renamed state" cases (West Germany -> Germany, Yugoslavia -> Croatia, ...); a few
--   are genuine switches of nationality from the 1930s-1960s.
-- =============================================================================
SELECT COALESCE(p.given_name || ' ', '') || p.family_name                 AS player,
       COUNT(DISTINCT s.team_id)                                          AS teams,
       STRING_AGG(t.team_name || ' (' || CAST(tr.year AS VARCHAR(4)) || ')', ', ' ORDER BY tr.year) AS squads
FROM squads s
JOIN players p      ON p.player_id = s.player_id
JOIN teams t        ON t.team_id = s.team_id
JOIN tournaments tr ON tr.tournament_id = s.tournament_id
GROUP BY p.player_id, p.given_name, p.family_name
HAVING COUNT(DISTINCT s.team_id) > 1
ORDER BY teams DESC, MIN(tr.year), player;


-- =============================================================================
-- Q17. Goals per match by tournament, with change from the previous edition
-- Business question: How many goals per match were scored at each tournament, and how did that
--   change from the previous World Cup?
-- SQL concepts: CTE, GROUP BY, window function LAG() OVER (ORDER BY year)
-- Expected result: one row per tournament (21 rows, oldest first): year, matches, goals,
--   goals_per_match, previous_goals_per_match, change (NULL for 1930). Peak 5.38 in 1954.
-- =============================================================================
WITH per_tournament AS (
    SELECT tr.year,
           COUNT(*)                                       AS matches,
           SUM(m.home_team_score + m.away_team_score)     AS goals,
           ROUND(1.0 * SUM(m.home_team_score + m.away_team_score) / COUNT(*), 2) AS goals_per_match
    FROM matches m
    JOIN tournaments tr ON tr.tournament_id = m.tournament_id
    GROUP BY tr.year
)
SELECT year, matches, goals, goals_per_match,
       LAG(goals_per_match) OVER (ORDER BY year)                    AS previous_goals_per_match,
       goals_per_match - LAG(goals_per_match) OVER (ORDER BY year)  AS change
FROM per_tournament
ORDER BY year;


-- =============================================================================
-- Q18. Biggest winning margins and highest-scoring matches
-- Business question: Which matches had the biggest winning margins, and which had the most goals?
-- SQL concepts: derived table, window function DENSE_RANK() (two different rankings), filtering on
--   window results in an outer query, ABS, string concatenation
-- Expected result: every match ranked in the top 2 for margin OR total goals (9 rows):
--   margin_rank, goals_rank, year, stage, match (home score-score away), margin, total_goals.
-- =============================================================================
SELECT margin_rank, goals_rank, year, stage_name, match, margin, total_goals
FROM (
    SELECT DENSE_RANK() OVER (ORDER BY ABS(m.home_team_score - m.away_team_score) DESC) AS margin_rank,
           DENSE_RANK() OVER (ORDER BY m.home_team_score + m.away_team_score DESC)       AS goals_rank,
           tr.year, st.stage_name,
           h.team_name || ' ' || CAST(m.home_team_score AS VARCHAR(2)) || '-'
               || CAST(m.away_team_score AS VARCHAR(2)) || ' ' || a.team_name             AS match,
           ABS(m.home_team_score - m.away_team_score)                                    AS margin,
           m.home_team_score + m.away_team_score                                         AS total_goals
    FROM matches m
    JOIN teams h               ON h.team_id = m.home_team_id
    JOIN teams a               ON a.team_id = m.away_team_id
    JOIN tournaments tr        ON tr.tournament_id = m.tournament_id
    JOIN tournament_stages st  ON st.tournament_id = m.tournament_id AND st.stage_number = m.stage_number
) ranked
WHERE margin_rank <= 2 OR goals_rank <= 2
ORDER BY margin DESC, total_goals DESC, year;


-- =============================================================================
-- Q19. When are goals scored?
-- Business question: In which periods of a match are goals scored (15-minute bands, stoppage time,
--   extra time)?
-- SQL concepts: CASE bucketing, GROUP BY, window function SUM() OVER () for the share of the total
-- Expected result: 10 rows in match order: period, goals, pct_of_all_goals, own_goals, penalties.
--   Stoppage-time goals are listed separately from the band they follow.
-- =============================================================================
WITH banded AS (
    SELECT CASE
             WHEN minute_regulation <= 45 AND minute_stoppage > 0 THEN '04 first-half stoppage time'
             WHEN minute_regulation <= 15                         THEN '01 minutes 1-15'
             WHEN minute_regulation <= 30                         THEN '02 minutes 16-30'
             WHEN minute_regulation <= 45                         THEN '03 minutes 31-45'
             WHEN minute_regulation <= 90 AND minute_stoppage > 0 THEN '08 second-half stoppage time'
             WHEN minute_regulation <= 60                         THEN '05 minutes 46-60'
             WHEN minute_regulation <= 75                         THEN '06 minutes 61-75'
             WHEN minute_regulation <= 90                         THEN '07 minutes 76-90'
             WHEN minute_regulation <= 105                        THEN '09 extra time, first half'
             ELSE                                                      '10 extra time, second half'
           END AS period,
           own_goal, penalty
    FROM goals
)
SELECT period,
       COUNT(*)                                                    AS goals,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)          AS pct_of_all_goals,
       SUM(CASE WHEN own_goal THEN 1 ELSE 0 END)                   AS own_goals,
       SUM(CASE WHEN penalty THEN 1 ELSE 0 END)                    AS penalties
FROM banded
GROUP BY period
ORDER BY period;


-- =============================================================================
-- Q20. Penalty goals and own goals over time (VAR in 2018)
-- Business question: How have the shares of goals from in-match penalties and own goals changed over
--   time, and was 2018 (the first World Cup with VAR) different?
-- SQL concepts: conditional aggregation SUM(CASE ...), GROUP BY, CASE labelling, window AVG() OVER
--   with a frame to compare with the average of all earlier tournaments
-- Expected result: one row per tournament (21 rows, newest first): year, goals, penalty_goals,
--   penalty_pct, own_goals, own_goal_pct, avg_penalty_pct_before (mean of all earlier editions), era.
-- =============================================================================
WITH per AS (
    SELECT tr.year,
           COUNT(*)                                          AS goals,
           SUM(CASE WHEN g.penalty THEN 1 ELSE 0 END)        AS penalty_goals,
           SUM(CASE WHEN g.own_goal THEN 1 ELSE 0 END)       AS own_goals
    FROM goals g
    JOIN tournaments tr ON tr.tournament_id = g.tournament_id
    GROUP BY tr.year
)
SELECT year, goals,
       penalty_goals, ROUND(100.0 * penalty_goals / goals, 1) AS penalty_pct,
       own_goals,     ROUND(100.0 * own_goals / goals, 1)     AS own_goal_pct,
       ROUND(AVG(100.0 * penalty_goals / goals) OVER (ORDER BY year
             ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 1) AS avg_penalty_pct_before,
       CASE WHEN year >= 2018 THEN 'VAR' ELSE 'before VAR' END   AS era
FROM per
ORDER BY year DESC;


-- =============================================================================
-- Q21. Penalty shoot-out records
-- Business question: Which teams win penalty shoot-outs, and how reliably do their players score
--   their kicks?
-- SQL concepts: two CTEs (shoot-out results, kick statistics), JOIN, GROUP BY, HAVING
-- Expected result: one row per team with at least 2 shoot-outs (14 rows): team_name, shootouts, won, lost,
--   kicks, scored, conversion_pct; most wins first. (West Germany and Germany are separate teams.)
-- =============================================================================
WITH shootouts AS (
    SELECT team_id,
           COUNT(*)                                                           AS shootouts,
           SUM(CASE WHEN penalties_for > penalties_against THEN 1 ELSE 0 END) AS won
    FROM team_appearances
    WHERE penalties_for IS NOT NULL
    GROUP BY team_id
),
kicks AS (
    SELECT team_id,
           COUNT(*)                                     AS kicks,
           SUM(CASE WHEN converted THEN 1 ELSE 0 END)   AS scored
    FROM penalty_kicks
    GROUP BY team_id
)
SELECT t.team_name,
       s.shootouts, s.won, s.shootouts - s.won AS lost,
       k.kicks, k.scored,
       ROUND(100.0 * k.scored / k.kicks, 1)    AS conversion_pct
FROM shootouts s
JOIN kicks k ON k.team_id = s.team_id
JOIN teams t ON t.team_id = s.team_id
WHERE s.shootouts >= 2
ORDER BY s.won DESC, conversion_pct DESC, t.team_name;


-- =============================================================================
-- Q22. Strictest referees (1970 onwards)
-- Business question: Which referees show the most cards per match (minimum five matches), and how
--   far above the overall average are they?
-- SQL concepts: CTE, LEFT JOIN (so card-free matches count as 0), GROUP BY, HAVING, scalar
--   subquery for the overall average
-- Expected result: one row per referee with >= 5 matches since 1970 (34 rows), strictest first: referee,
--   country, matches, cards, sendings_off, cards_per_match, above_average.
-- =============================================================================
WITH ref_matches AS (
    SELECT ra.referee_id, ra.match_id,
           COUNT(b.booking_id)                                                    AS cards,
           SUM(CASE WHEN b.red_card OR b.second_yellow_card THEN 1 ELSE 0 END)    AS sendings_off
    FROM referee_appearances ra
    JOIN tournaments tr  ON tr.tournament_id = ra.tournament_id
    LEFT JOIN bookings b ON b.match_id = ra.match_id
    WHERE tr.year >= 1970
    GROUP BY ra.referee_id, ra.match_id
)
SELECT COALESCE(r.given_name || ' ', '') || r.family_name               AS referee,
       r.country_name                                                   AS country,
       COUNT(*)                                                         AS matches,
       CAST(SUM(rm.cards) AS INTEGER)                                   AS cards,
       CAST(COALESCE(SUM(rm.sendings_off), 0) AS INTEGER)               AS sendings_off,
       ROUND(AVG(rm.cards), 2)                                          AS cards_per_match,
       ROUND(AVG(rm.cards) - (SELECT AVG(cards) FROM ref_matches), 2)   AS above_average
FROM ref_matches rm
JOIN referees r ON r.referee_id = rm.referee_id
GROUP BY r.referee_id, r.given_name, r.family_name, r.country_name
HAVING COUNT(*) >= 5
ORDER BY cards_per_match DESC, matches DESC, referee;


-- =============================================================================
-- Q23. Cards per match over time, with a moving average
-- Business question: How has the number of cards per match changed since cards were introduced in
--   1970? Smooth the trend with a three-tournament moving average.
-- SQL concepts: CTE, LEFT JOIN, COUNT(DISTINCT ...), window function
--   AVG() OVER (ORDER BY year ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
-- Expected result: one row per tournament 1970-2018 (13 rows, oldest first): year, matches, cards,
--   sendings_off, cards_per_match, moving_avg_3. Peak in 2006.
-- =============================================================================
WITH per AS (
    SELECT tr.year,
           COUNT(DISTINCT m.match_id)                                            AS matches,
           COUNT(b.booking_id)                                                   AS cards,
           SUM(CASE WHEN b.red_card OR b.second_yellow_card THEN 1 ELSE 0 END)   AS sendings_off
    FROM matches m
    JOIN tournaments tr  ON tr.tournament_id = m.tournament_id
    LEFT JOIN bookings b ON b.match_id = m.match_id
    WHERE tr.year >= 1970
    GROUP BY tr.year
)
SELECT year, matches, cards, sendings_off,
       ROUND(1.0 * cards / matches, 2) AS cards_per_match,
       ROUND(AVG(1.0 * cards / matches) OVER (ORDER BY year
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_3
FROM per
ORDER BY year;


-- =============================================================================
-- Q24. Discipline by stage: group matches vs knockout matches (1970 onwards)
-- Business question: Are knockout matches more ill-tempered than group matches? Compare cards and
--   sendings-off per match by stage.
-- SQL concepts: CTE, LEFT JOIN (matches without cards count as 0), CASE classification, GROUP BY
-- Expected result: one row per stage played since 1970 (7 rows): phase (group/knockout), stage_name,
--   matches, cards_per_match, sendings_off_per_match, pct_matches_with_sending_off.
-- =============================================================================
WITH per_match AS (
    SELECT m.match_id, st.stage_name,
           CASE WHEN st.stage_name IN ('group stage', 'second group stage', 'final round')
                THEN 'group' ELSE 'knockout' END                                  AS phase,
           COUNT(b.booking_id)                                                   AS cards,
           SUM(CASE WHEN b.red_card OR b.second_yellow_card THEN 1 ELSE 0 END)   AS sendings_off
    FROM matches m
    JOIN tournaments tr       ON tr.tournament_id = m.tournament_id
    JOIN tournament_stages st ON st.tournament_id = m.tournament_id AND st.stage_number = m.stage_number
    LEFT JOIN bookings b      ON b.match_id = m.match_id
    WHERE tr.year >= 1970
    GROUP BY m.match_id, st.stage_name
)
SELECT phase, stage_name,
       COUNT(*)                                        AS matches,
       ROUND(AVG(cards), 2)                            AS cards_per_match,
       ROUND(AVG(COALESCE(sendings_off, 0)), 3)        AS sendings_off_per_match,
       ROUND(100.0 * SUM(CASE WHEN sendings_off > 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                       AS pct_matches_with_sending_off
FROM per_match
GROUP BY phase, stage_name
ORDER BY phase, cards_per_match DESC;


-- =============================================================================
-- Q25. Most-carded teams (1970 onwards)
-- Business question: Which teams have received the most cards and sendings-off, relative to how
--   many matches they played?
-- SQL concepts: JOIN, GROUP BY, HAVING, correlated scalar subquery for matches played since 1970
-- Expected result: one row per team with at least 30 cards (33 rows), most cards first: team_name, matches,
--   cards, yellow_only, sendings_off, cards_per_match.
-- =============================================================================
SELECT t.team_name,
       (SELECT COUNT(*) FROM team_appearances ta
        JOIN tournaments tr ON tr.tournament_id = ta.tournament_id
        WHERE ta.team_id = t.team_id AND tr.year >= 1970)                                 AS matches,
       COUNT(*)                                                                         AS cards,
       SUM(CASE WHEN NOT b.red_card AND NOT b.second_yellow_card THEN 1 ELSE 0 END)     AS yellow_only,
       SUM(CASE WHEN b.red_card OR b.second_yellow_card THEN 1 ELSE 0 END)              AS sendings_off,
       ROUND(1.0 * COUNT(*) / (SELECT COUNT(*) FROM team_appearances ta
                               JOIN tournaments tr ON tr.tournament_id = ta.tournament_id
                               WHERE ta.team_id = t.team_id AND tr.year >= 1970), 2)    AS cards_per_match
FROM bookings b
JOIN teams t ON t.team_id = b.team_id
GROUP BY t.team_id, t.team_name
HAVING COUNT(*) >= 30
ORDER BY cards DESC;


-- =============================================================================
-- Q26. Busiest stadiums
-- Business question: Which stadiums have hosted the most World Cup matches, and how many finals?
-- SQL concepts: multi-table JOIN, GROUP BY, window function RANK() in a derived table, filtering on
--   the rank (ties kept), conditional aggregation
-- Expected result: every stadium ranked 10th or better by matches, ties included: rank, stadium,
--   city, country, capacity, matches, tournaments, finals, first_year, last_year. Estadio Azteca first
--   with 19 matches.
-- =============================================================================
SELECT *
FROM (
SELECT RANK() OVER (ORDER BY COUNT(*) DESC)                      AS rank,
       s.stadium_name, s.city_name, s.country_name,
       s.stadium_capacity                                       AS capacity,
       COUNT(*)                                                 AS matches,
       COUNT(DISTINCT m.tournament_id)                          AS tournaments,
       SUM(CASE WHEN st.stage_name = 'final' THEN 1 ELSE 0 END) AS finals,
       MIN(tr.year)                                             AS first_year,
       MAX(tr.year)                                             AS last_year
FROM matches m
JOIN stadiums s            ON s.stadium_id = m.stadium_id
JOIN tournaments tr        ON tr.tournament_id = m.tournament_id
JOIN tournament_stages st  ON st.tournament_id = m.tournament_id AND st.stage_number = m.stage_number
GROUP BY s.stadium_id, s.stadium_name, s.city_name, s.country_name, s.stadium_capacity
) ranked
WHERE rank <= 10
ORDER BY rank, finals DESC, stadium_name;


-- =============================================================================
-- Q27. Most experienced and most successful managers
-- Business question: Which managers have managed the most World Cup matches, and how many did
--   they win?
-- SQL concepts: JOIN on a composite key (match_id, team_id), multi-table JOIN, GROUP BY,
--   STRING_AGG(DISTINCT ...), conditional aggregation, RANK() in a derived table (ties kept)
-- Expected result: every manager ranked 10th or better by matches, ties included: manager,
--   nationality, teams, tournaments, matches, won, drawn, lost, win_pct. Helmut Schoen first
--   (25 matches, 16 wins).
-- =============================================================================
SELECT manager, nationality, teams, tournaments, matches, won, drawn, lost, win_pct
FROM (
SELECT RANK() OVER (ORDER BY COUNT(*) DESC)                                 AS rank,
       COALESCE(mg.given_name || ' ', '') || mg.family_name                 AS manager,
       mg.country_name                                                      AS nationality,
       STRING_AGG(DISTINCT t.team_name, ', ')                               AS teams,
       COUNT(DISTINCT ma.tournament_id)                                     AS tournaments,
       COUNT(*)                                                             AS matches,
       SUM(CASE WHEN ta.goals_for > ta.goals_against THEN 1 ELSE 0 END)     AS won,
       SUM(CASE WHEN ta.goals_for = ta.goals_against THEN 1 ELSE 0 END)     AS drawn,
       SUM(CASE WHEN ta.goals_for < ta.goals_against THEN 1 ELSE 0 END)     AS lost,
       ROUND(100.0 * SUM(CASE WHEN ta.goals_for > ta.goals_against THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                            AS win_pct
FROM manager_appearances ma
JOIN team_appearances ta ON ta.match_id = ma.match_id AND ta.team_id = ma.team_id
JOIN managers mg         ON mg.manager_id = ma.manager_id
JOIN teams t             ON t.team_id = ma.team_id
GROUP BY mg.manager_id, mg.given_name, mg.family_name, mg.country_name
) ranked
WHERE rank <= 10
ORDER BY matches DESC, won DESC, manager;


-- =============================================================================
-- Q28. Foreign managers vs home-nation managers
-- Business question: Do teams led by a foreign manager go further than teams led by a manager of
--   their own nationality?
-- SQL concepts: CTEs, CASE (classification, including a historical-name rule), MIN/MAX of a flag to
--   classify joint managers, LEFT JOIN, correlated subquery, AVG
-- Expected result: one row per manager type (2 rows on this data: home-nation, foreign): manager_type,
--   team_tournaments, avg_matches_per_tournament, pct_reached_top_four, titles. A 'mixed' type
--   appears only if joint managers differ in nationality; in the source every joint pair shares one
--   nationality (even 1998 Saudi Arabia and Tunisia, where both managers are listed as Brazil / Poland).
--   Rule: a manager counts as home-nation when nationality = team name, or for West Germany when
--   nationality = 'Germany' (the source lists West German managers as 'Germany').
-- =============================================================================
WITH appointment_flags AS (
    SELECT a.tournament_id, a.team_id,
           CASE WHEN m.country_name = t.team_name
                  OR (t.team_name = 'West Germany' AND m.country_name = 'Germany')
                THEN 0 ELSE 1 END AS is_foreign
    FROM manager_appointments a
    JOIN managers m ON m.manager_id = a.manager_id
    JOIN teams t    ON t.team_id = a.team_id
),
team_tournaments AS (
    SELECT tournament_id, team_id,
           CASE WHEN MIN(is_foreign) = 1 THEN 'foreign'
                WHEN MAX(is_foreign) = 0 THEN 'home-nation'
                ELSE 'mixed (joint managers)' END AS manager_type
    FROM appointment_flags
    GROUP BY tournament_id, team_id
)
SELECT tt.manager_type,
       COUNT(*)                                                                  AS team_tournaments,
       ROUND(AVG((SELECT COUNT(*) FROM team_appearances ta
                  WHERE ta.tournament_id = tt.tournament_id AND ta.team_id = tt.team_id)), 2)
                                                                                 AS avg_matches_per_tournament,
       ROUND(100.0 * SUM(CASE WHEN s.position IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                                 AS pct_reached_top_four,
       SUM(CASE WHEN s.position = 1 THEN 1 ELSE 0 END)                           AS titles
FROM team_tournaments tt
LEFT JOIN tournament_standings s
       ON s.tournament_id = tt.tournament_id AND s.team_id = tt.team_id
GROUP BY tt.manager_type
ORDER BY team_tournaments DESC;


-- =============================================================================
-- Q29. Does the best player (Golden Ball) come from the champion team?
-- Business question: How often does the Golden Ball go to a player from the team that won the
--   tournament, and how did the winners' teams finish?
-- SQL concepts: multi-table JOIN, LEFT JOIN with IS NULL handling, CASE
-- Expected result: one row per Golden Ball winner (11 rows, 1978-2018, newest first): year,
--   player, team, team_finish ('champion', 'runner-up', '3rd', '4th' or 'outside top four').
-- =============================================================================
SELECT tr.year,
       COALESCE(p.given_name || ' ', '') || p.family_name AS player,
       t.team_name                                        AS team,
       CASE s.position
            WHEN 1 THEN 'champion'
            WHEN 2 THEN 'runner-up'
            WHEN 3 THEN '3rd'
            WHEN 4 THEN '4th'
            ELSE 'outside top four'
       END                                                AS team_finish
FROM award_winners aw
JOIN awards a       ON a.award_id = aw.award_id
JOIN players p      ON p.player_id = aw.player_id
JOIN teams t        ON t.team_id = aw.team_id
JOIN tournaments tr ON tr.tournament_id = aw.tournament_id
LEFT JOIN tournament_standings s
       ON s.tournament_id = aw.tournament_id AND s.team_id = aw.team_id
WHERE a.award_name = 'Golden Ball'
ORDER BY tr.year DESC;


-- =============================================================================
-- Q30. Data integrity: do the goal records match the scores?
-- Business question: Does every goal in the goals table agree with the match scores? (A check that
--   the database is complete and consistent after loading.)
-- SQL concepts: CTEs, LEFT JOIN with COALESCE (team-matches without goals count 0), set comparison
--   with EXCEPT, NOT EXISTS anti-join, scalar subqueries
-- Expected result: exactly 1 summary row: team_matches_checked (1800), goals_in_scores (2548),
--   goal_rows (2548), mismatched_team_matches (0), goal_groups_without_match_team (0).
-- =============================================================================
WITH goal_rows AS (
    SELECT match_id, team_id, COUNT(*) AS goals
    FROM goals
    GROUP BY match_id, team_id
),
compared AS (
    SELECT ta.match_id, ta.team_id,
           ta.goals_for               AS goals_in_score,
           COALESCE(g.goals, 0)       AS goals_in_goal_rows
    FROM team_appearances ta
    LEFT JOIN goal_rows g ON g.match_id = ta.match_id AND g.team_id = ta.team_id
),
mismatches AS (
    SELECT match_id, team_id, goals_in_goal_rows FROM compared
    EXCEPT
    SELECT match_id, team_id, goals_in_score     FROM compared
)
SELECT (SELECT COUNT(*) FROM compared)                       AS team_matches_checked,
       (SELECT CAST(SUM(goals_in_score) AS INTEGER) FROM compared)     AS goals_in_scores,
       (SELECT CAST(SUM(goals_in_goal_rows) AS INTEGER) FROM compared) AS goal_rows,
       (SELECT COUNT(*) FROM mismatches)                     AS mismatched_team_matches,
       (SELECT COUNT(*) FROM goal_rows g
        WHERE NOT EXISTS (SELECT 1 FROM team_appearances ta
                          WHERE ta.match_id = g.match_id AND ta.team_id = g.team_id))
                                                             AS goal_groups_without_match_team;
