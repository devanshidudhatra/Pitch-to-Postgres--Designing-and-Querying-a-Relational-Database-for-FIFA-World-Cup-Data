-- =============================================================================
-- Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
-- Data: Joshua C. Fjelstul, The Fjelstul World Cup Database, https://github.com/jfjelstul/worldcup, CC-BY-SA 4.0.
-- LOCAL TEST DATABASE ONLY. Drops all project views and tables so that ddl.sql can be rerun cleanly.
-- Never run this on the course server (src/apply_ddl.py refuses unless DB_HOST is local).
-- =============================================================================

DROP VIEW IF EXISTS v_top_scorers, v_tournament_summary, v_team_performance, v_referee_discipline,
                    v_host_performance, v_head_to_head, v_match_results CASCADE;

DROP TABLE IF EXISTS
    award_winners, penalty_kicks, substitutions, bookings, goals, player_appearances,
    manager_appearances, referee_appearances, team_appearances, matches,
    referee_appointments, manager_appointments, squads, group_standings, tournament_standings,
    host_countries, qualified_teams, groups, tournament_stages, tournaments,
    referees, managers, players, teams, stadiums, awards, positions, confederations
CASCADE;
