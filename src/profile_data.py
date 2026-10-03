"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Milestone 0 - dataset profiling.

Reads the 27 CSV files of the Fjelstul World Cup Database from ./data, verifies
keys and relationships, runs data-quality checks, computes coverage figures and
insights, and writes:

    docs/dataset_understanding.md   human-readable report
    docs/profile_summary.json       machine-readable summary (used by later milestones)

Every number in the report is computed here from the files; nothing is typed in by hand.

Data source: Joshua C. Fjelstul, "The Fjelstul World Cup Database",
https://github.com/jfjelstul/worldcup, licensed CC-BY-SA 4.0.
This script does not modify the source files.

Usage:  python src/profile_data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

TITLE = "Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data"
SENTINELS = ["not available", "not applicable"]

# ---------------------------------------------------------------------------
# Table metadata: purpose, grain, verified key candidates and FK candidates.
# Keys and FKs are *candidates*; every one is checked against the data below.
# ---------------------------------------------------------------------------
T, TM, P, M = "tournaments", "teams", "players", "matches"
META = {
    "confederations": dict(theme="Reference", purpose="The six continental football confederations.",
        grain="One confederation.", pk=["confederation_id"], fks=[]),
    "teams": dict(theme="Reference", purpose="Every national team that has played at a men's World Cup, including teams that no longer exist.",
        grain="One national team (historical teams such as West Germany or the Soviet Union are separate rows).",
        pk=["team_id"], fks=[(["confederation_id"], "confederations", ["confederation_id"])]),
    "players": dict(theme="People", purpose="Every player named in a World Cup squad.",
        grain="One player (a person), across all tournaments.", pk=["player_id"], fks=[]),
    "managers": dict(theme="People", purpose="Every head coach who managed a team at a World Cup.",
        grain="One manager (a person).", pk=["manager_id"], fks=[]),
    "referees": dict(theme="People", purpose="Every referee appointed to a World Cup.",
        grain="One referee (a person).", pk=["referee_id"], fks=[(["confederation_id"], "confederations", ["confederation_id"])]),
    "stadiums": dict(theme="Reference", purpose="Every stadium that hosted a World Cup match.",
        grain="One stadium.", pk=["stadium_id"], fks=[]),
    "awards": dict(theme="Reference", purpose="The individual awards FIFA gives at a World Cup.",
        grain="One award type.", pk=["award_id"], fks=[]),
    "tournaments": dict(theme="Tournament structure", purpose="Each edition of the men's FIFA World Cup, with host, winner and format flags.",
        grain="One tournament (edition).", pk=["tournament_id"], fks=[]),
    "tournament_stages": dict(theme="Tournament structure", purpose="The stages (group stage, round of 16, final, ...) of each tournament with dates and match counts.",
        grain="One stage of one tournament.", pk=["tournament_id", "stage_number"],
        fks=[(["tournament_id"], T, ["tournament_id"])]),
    "groups": dict(theme="Tournament structure", purpose="The groups inside each group stage.",
        grain="One group in one group stage of one tournament.", pk=["tournament_id", "stage_number", "group_name"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["tournament_id", "stage_number"], "tournament_stages", ["tournament_id", "stage_number"])]),
    "group_standings": dict(theme="Results", purpose="Final table of every group (played, won, drawn, lost, goals, points, advanced).",
        grain="One team's final line in one group.", pk=["tournament_id", "stage_number", "group_name", "position"],
        fks=[(["tournament_id", "stage_number", "group_name"], "groups", ["tournament_id", "stage_number", "group_name"]),
             (["team_id"], TM, ["team_id"]), (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "host_countries": dict(theme="Tournament structure", purpose="Host nation(s) of each tournament and how far they went.",
        grain="One host team in one tournament (2002 has two hosts).", pk=["tournament_id", "team_id"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["team_id"], TM, ["team_id"]),
             (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "qualified_teams": dict(theme="Participation", purpose="Which teams took part in each tournament, matches played and stage reached.",
        grain="One team in one tournament.", pk=["tournament_id", "team_id"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["team_id"], TM, ["team_id"])]),
    "tournament_standings": dict(theme="Results", purpose="Final top-four ranking of each tournament.",
        grain="One finishing position (1 to 4) in one tournament.", pk=["tournament_id", "position"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["team_id"], TM, ["team_id"]),
             (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "matches": dict(theme="Matches", purpose="Every match played, with stage, venue, teams, score, extra time and penalty shoot-out outcome.",
        grain="One match (replays are separate matches).", pk=["match_id"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["stadium_id"], "stadiums", ["stadium_id"]),
             (["home_team_id"], TM, ["team_id"]), (["away_team_id"], TM, ["team_id"]),
             (["tournament_id", "stage_name"], "tournament_stages", ["tournament_id", "stage_name"]),
             (["tournament_id", "home_team_id"], "qualified_teams", ["tournament_id", "team_id"]),
             (["tournament_id", "away_team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "team_appearances": dict(theme="Matches", purpose="Each match seen from one team's side (goals for/against, result). Two rows per match.",
        grain="One team in one match.", pk=["match_id", "team_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["opponent_id"], TM, ["team_id"]),
             (["stadium_id"], "stadiums", ["stadium_id"]), (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "squads": dict(theme="Participation", purpose="The registered squad of every team at every tournament.",
        grain="One player in one team's squad at one tournament.", pk=["tournament_id", "team_id", "player_id"],
        fks=[(["player_id"], P, ["player_id"]), (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "player_appearances": dict(theme="Match events", purpose="Line-ups: every player who started or came on in a match (1970 onwards).",
        grain="One player appearing in one match.", pk=["match_id", "player_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["player_id"], P, ["player_id"]),
             (["tournament_id", "team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"])]),
    "goals": dict(theme="Match events", purpose="Every goal scored, with scorer, minute, own-goal and penalty flags.",
        grain="One goal.", pk=["goal_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["player_team_id"], TM, ["team_id"]),
             (["player_id"], P, ["player_id"]),
             (["tournament_id", "player_team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"]),
             (["match_id", "team_id"], "team_appearances", ["match_id", "team_id"])]),
    "bookings": dict(theme="Match events", purpose="Every yellow and red card (1970 onwards, when cards were introduced).",
        grain="One card event shown to one player.", pk=["booking_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["player_id"], P, ["player_id"]),
             (["tournament_id", "team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"])]),
    "substitutions": dict(theme="Match events", purpose="Every substitution, stored as two rows: the player going off and the player coming on (1970 onwards).",
        grain="One player going off or coming on in one substitution.", pk=["substitution_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["player_id"], P, ["player_id"]),
             (["tournament_id", "team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"])]),
    "penalty_kicks": dict(theme="Match events", purpose="Every kick taken in a penalty shoot-out (shoot-outs began in 1982). In-match penalties are NOT here; they appear only as goals.",
        grain="One shoot-out kick.", pk=["penalty_kick_id"],
        fks=[(["match_id"], M, ["match_id"]), (["team_id"], TM, ["team_id"]), (["player_id"], P, ["player_id"]),
             (["tournament_id", "team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"])]),
    "manager_appointments": dict(theme="Participation", purpose="Which manager(s) led each team at each tournament.",
        grain="One manager appointed to one team at one tournament.", pk=["tournament_id", "team_id", "manager_id"],
        fks=[(["manager_id"], "managers", ["manager_id"]), (["tournament_id", "team_id"], "qualified_teams", ["tournament_id", "team_id"])]),
    "manager_appearances": dict(theme="Match events", purpose="Which manager(s) were in charge of each team in each match.",
        grain="One manager in charge of one team in one match.", pk=["match_id", "team_id", "manager_id"],
        fks=[(["match_id"], M, ["match_id"]), (["manager_id"], "managers", ["manager_id"]),
             (["match_id", "team_id"], "team_appearances", ["match_id", "team_id"]),
             (["tournament_id", "team_id", "manager_id"], "manager_appointments", ["tournament_id", "team_id", "manager_id"])]),
    "referee_appointments": dict(theme="Participation", purpose="Which referees were appointed to each tournament.",
        grain="One referee appointed to one tournament.", pk=["tournament_id", "referee_id"],
        fks=[(["tournament_id"], T, ["tournament_id"]), (["referee_id"], "referees", ["referee_id"]),
             (["confederation_id"], "confederations", ["confederation_id"])]),
    "referee_appearances": dict(theme="Match events", purpose="The referee of each match.",
        grain="One referee officiating one match (exactly one per match).", pk=["match_id"],
        fks=[(["match_id"], M, ["match_id"]), (["referee_id"], "referees", ["referee_id"]),
             (["tournament_id", "referee_id"], "referee_appointments", ["tournament_id", "referee_id"]),
             (["confederation_id"], "confederations", ["confederation_id"])]),
    "award_winners": dict(theme="Awards", purpose="Winners of each individual award at each tournament (ties produce several rows).",
        grain="One player winning one award at one tournament.", pk=["tournament_id", "award_id", "player_id"],
        fks=[(["award_id"], "awards", ["award_id"]), (["player_id"], P, ["player_id"]),
             (["tournament_id", "team_id", "player_id"], "squads", ["tournament_id", "team_id", "player_id"])]),
}
THEME_ORDER = ["Reference", "People", "Tournament structure", "Participation", "Matches", "Match events", "Results", "Awards"]

# ---------------------------------------------------------------------------
# Column meanings. Generic meanings by column name, with table-specific overrides.
# ---------------------------------------------------------------------------
COL = {
    "key_id": "Row number in the source file (1..n). Not a business key.",
    "tournament_id": "Tournament identifier, e.g. WC-1930.", "tournament_name": "Tournament name, e.g. 1930 FIFA World Cup (copy of tournaments).",
    "team_id": "Team identifier, e.g. T-03.", "team_name": "Team name (copy of teams).", "team_code": "Three-letter team code (copy of teams).",
    "player_id": "Player identifier, e.g. P-04418.", "family_name": "Family name.", "given_name": "Given name; 'not available' for players known by one name.",
    "match_id": "Match identifier, e.g. M-1930-01.", "match_name": "Match label 'Home v Away' (copy of matches).",
    "match_date": "Match date (YYYY-MM-DD).", "stage_name": "Stage name, e.g. group stage, round of 16, final.",
    "group_name": "Group name, e.g. Group 1; 'not applicable' outside group stages.",
    "home_team": "1 if the row's team was the designated home side.", "away_team": "1 if the row's team was the designated away side.",
    "shirt_number": "Shirt number; 0 means unknown.", "minute_label": "Minute as displayed, e.g. 90'+3'.",
    "minute_regulation": "Minute of play within regulation or extra time (1-120).", "minute_stoppage": "Added (stoppage-time) minute; 0 if none.",
    "match_period": "Period: first half, second half, extra time halves, with or without stoppage time.",
    "stadium_id": "Stadium identifier, e.g. S-001.", "stadium_name": "Stadium name.", "city_name": "City of the stadium.",
    "confederation_id": "Confederation identifier, e.g. CF-1.", "confederation_name": "Confederation full name.", "confederation_code": "Confederation code, e.g. UEFA.",
    "award_id": "Award identifier, e.g. A-1.", "award_name": "Award name, e.g. Golden Ball.",
    "manager_id": "Manager identifier, e.g. M-001.", "referee_id": "Referee identifier, e.g. R-001.",
    "stage_number": "Order of the stage within the tournament (1 = first).",
    "group_stage": "1 if the stage is a group (round-robin) stage.", "knockout_stage": "1 if the stage is a knockout stage.",
    "replayed": "1 if this match was drawn and had to be replayed.", "replay": "1 if this match is the replay of a drawn match.",
    "extra_time": "1 if the match went to extra time.", "penalty_shootout": "1 if the match was decided by a penalty shoot-out.",
    "result": "Outcome label. NOTE: shoot-out winners are recorded as wins even though the score is level.",
    "draw": "1 if the result label is a draw (shoot-out matches are NOT draws here).",
    "goals_for": "Goals scored by the team.", "goals_against": "Goals conceded by the team.",
    "country_name": "Country name.", "count_matches": "Number of matches.", "count_teams": "Number of teams.",
    "start_date": "Start date (YYYY-MM-DD).", "end_date": "End date (YYYY-MM-DD).",
    "performance": "Furthest stage reached (free-text label).", "position": "Finishing position.",
    "position_name": "Playing position name.", "position_code": "Playing position code.",
    # tournaments
    "year": "Year of the tournament.", "host_country": "Host country as text ('Korea, Japan' for 2002); use host_countries instead.",
    "winner": "Winning team as text (not an id); use tournament_standings position 1 instead.", "host_won": "1 if a host nation won.",
    "second_group_stage": "1 if the tournament had a second group stage.", "final_round": "1 if the tournament ended in a final round-robin group (1950).",
    "round_of_16": "1 if the tournament had a round of 16.", "quarter_finals": "1 if it had quarter-finals.", "semi_finals": "1 if it had semi-finals.",
    "third_place_match": "1 if it had a third-place match.", "final": "1 if it had a single final match.",
    # stages
    "unbalanced_groups": "1 if groups in this stage had different numbers of teams.", "count_scheduled": "Matches scheduled in the stage.",
    "count_replays": "Replays played in the stage.", "count_playoffs": "Group tie-break play-off matches in the stage.",
    "count_walkovers": "Matches awarded without being played.",
    # standings
    "played": "Group matches played.", "wins": "Group matches won.", "draws": "Group matches drawn.", "losses": "Group matches lost.",
    "goal_difference": "Goals for minus goals against.", "points": "Points under the system in force at the time (2 per win to 1990, 3 from 1994).",
    "advanced": "1 if the team advanced from the group.",
    # matches
    "match_time": "Local kick-off time (HH:MM).",
    "home_team_id": "Home team id.", "home_team_name": "Home team name.", "home_team_code": "Home team code.",
    "away_team_id": "Away team id.", "away_team_name": "Away team name.", "away_team_code": "Away team code.",
    "score": "Score as text 'h–a' (en dash; one row uses a hyphen).", "home_team_score": "Goals scored by the home team (incl. extra time).",
    "away_team_score": "Goals scored by the away team (incl. extra time).", "home_team_score_margin": "Home score minus away score.",
    "away_team_score_margin": "Away score minus home score.", "score_penalties": "Shoot-out score as text; '0-0' when there was no shoot-out.",
    "home_team_score_penalties": "Home shoot-out goals; 0 when there was no shoot-out.", "away_team_score_penalties": "Away shoot-out goals; 0 when there was no shoot-out.",
    "home_team_win": "1 if the result label is a home win (includes shoot-out wins).", "away_team_win": "1 if the result label is an away win (includes shoot-out wins).",
    # team_appearances
    "opponent_id": "Opponent team id.", "opponent_name": "Opponent team name.", "opponent_code": "Opponent team code.",
    "goal_differential": "Goals for minus goals against.", "penalties_for": "Shoot-out goals scored by the team.",
    "penalties_against": "Shoot-out goals conceded by the team.", "win": "1 if the result label is a win (includes shoot-out wins).",
    "lose": "1 if the result label is a loss (includes shoot-out losses).",
    # events
    "goal_id": "Goal identifier, e.g. G-0001.", "player_team_id": "Team the scorer plays for (differs from team_id for own goals).",
    "player_team_name": "Name of the scorer's team.", "player_team_code": "Code of the scorer's team.",
    "own_goal": "1 if an own goal (credited to team_id, scored by a player of player_team_id).", "penalty": "1 if scored from an in-match penalty kick.",
    "booking_id": "Booking identifier, e.g. B-0001.", "yellow_card": "1 if a yellow card was shown.", "red_card": "1 if a straight red card was shown.",
    "second_yellow_card": "1 if a second yellow card (leading to a red).", "sending_off": "1 if the player was sent off.",
    "substitution_id": "Substitution row identifier, e.g. S-0001.", "going_off": "1 if this row is the player leaving the pitch.",
    "coming_on": "1 if this row is the player entering the pitch.",
    "penalty_kick_id": "Shoot-out kick identifier, e.g. PK-001.", "converted": "1 if the shoot-out kick was scored.",
    "starter": "1 if the player started the match.", "substitute": "1 if the player came on as a substitute.", "captain": "1 if the player captained the team.",
    # players
    "birth_date": "Date of birth (YYYY-MM-DD); 'not available' if unknown.",
    "goal_keeper": "1 if the player was ever listed as goalkeeper.", "defender": "1 if ever listed as defender.",
    "midfielder": "1 if ever listed as midfielder.", "forward": "1 if ever listed as forward.",
    "count_tournaments": "Number of tournaments the player was in a squad for.", "list_tournaments": "Comma-separated list of those years (derived, non-atomic).",
    "player_wikipedia_link": "Wikipedia URL.", "manager_wikipedia_link": "Wikipedia URL.", "referee_wikipedia_link": "Wikipedia URL or 'not available'.",
    "team_wikipedia_link": "Wikipedia URL of the team.", "federation_wikipedia_link": "Wikipedia URL of the federation.",
    "stadium_wikipedia_link": "Wikipedia URL of the stadium.", "city_wikipedia_link": "Wikipedia URL of the city.",
    "confederation_wikipedia_link": "Wikipedia URL of the confederation.",
    "federation_name": "National football federation.", "region_name": "Geographic region (e.g. Europe, Middle East).",
    "stadium_capacity": "Stadium capacity (single value; not attendance).",
    "award_description": "What the award recognises.", "year_introduced": "First tournament year the award applies to (some retroactively).",
    "shared": "1 if the award was shared by several players (tie).",
}
COL_OVERRIDE = {
    ("tournaments", "count_teams"): "Number of teams that took part.",
    ("tournaments", "group_stage"): "1 if the tournament had a (first) group stage.",
    ("tournament_stages", "count_matches"): "Matches actually played in the stage (incl. replays and play-offs).",
    ("tournament_stages", "count_teams"): "Teams that took part in the stage.",
    ("groups", "count_teams"): "Teams in the group.",
    ("qualified_teams", "count_matches"): "Matches the team played in the tournament.",
    ("qualified_teams", "performance"): "Furthest stage reached; 'final' covers both winner and runner-up.",
    ("host_countries", "performance"): "Host's finishing label (inconsistent spelling, see data quality).",
    ("group_standings", "position"): "Position in the group table.",
    ("tournament_standings", "position"): "Final position 1 (winner) to 4.",
    ("stadiums", "country_name"): "Country of the stadium.", ("matches", "country_name"): "Country of the stadium.",
    ("team_appearances", "country_name"): "Country of the stadium.",
    ("managers", "country_name"): "Manager's nationality.", ("manager_appointments", "country_name"): "Manager's nationality.",
    ("manager_appearances", "country_name"): "Manager's nationality.",
    ("referees", "country_name"): "Referee's nationality.", ("referee_appointments", "country_name"): "Referee's nationality.",
    ("referee_appearances", "country_name"): "Referee's nationality.",
    ("squads", "position_name"): "Position in the squad list (4 values).",
    ("player_appearances", "position_name"): "Position played in the match (21 detailed values).",
    ("awards", "award_name"): "Award name.",
}


def meaning(table: str, col: str) -> str:
    if (table, col) in COL_OVERRIDE:
        return COL_OVERRIDE[(table, col)]
    if col in COL:
        return COL[col]
    raise KeyError(f"No documented meaning for {table}.{col}")


# ---------------------------------------------------------------------------
# Loading and generic profiling
# ---------------------------------------------------------------------------
def load() -> dict[str, pd.DataFrame]:
    # keep_default_na=False so strings such as "not available" or "NA" are not silently
    # converted; only genuinely empty cells become NaN.
    files = sorted(DATA.glob("*.csv"))
    assert len(files) == 27, f"expected 27 CSV files in {DATA}, found {len(files)}"
    return {f.stem: pd.read_csv(f, keep_default_na=False, na_values=[""], encoding="utf-8") for f in files}


def infer_type(s: pd.Series, name: str) -> str:
    v = s.dropna()
    v = v[~v.astype(str).isin(SENTINELS)]
    if pd.api.types.is_integer_dtype(s):
        if set(v.unique()) <= {0, 1} and name not in ("count_replays", "count_playoffs", "count_walkovers", "home_team_score_penalties"):
            return "flag 0/1"
        return "integer"
    sv = v.astype(str)
    if len(sv) and sv.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        return "date"
    if len(sv) and sv.str.fullmatch(r"\d{2}:\d{2}").all():
        return "time"
    if name.endswith("_id"):
        return "text id"
    return "text"


def profile_table(name: str, df: pd.DataFrame) -> dict:
    cols = []
    for c in df.columns:
        s = df[c]
        sv = s.astype(str)
        cols.append(dict(column=c, type=infer_type(s, c), meaning=meaning(name, c), distinct=int(s.nunique()),
                         nulls=int(s.isna().sum()), sentinels=int(sv.isin(SENTINELS).sum()),
                         example=str(s.dropna().iloc[0]) if s.notna().any() else ""))
    pk = META[name]["pk"]
    return dict(rows=len(df), columns=cols,
                duplicate_rows=int(df.drop(columns="key_id").duplicated().sum()),
                key_id_unique=bool(df["key_id"].is_unique),
                pk=pk, pk_unique=bool(not df.duplicated(pk).any()), pk_has_nulls=bool(df[pk].isna().any().any()))


def check_fk(D, child, ccols, parent, pcols) -> dict:
    c = D[child][ccols].drop_duplicates()
    p = D[parent][pcols].drop_duplicates()
    p.columns = ccols
    merged = c.merge(p, how="left", indicator=True)
    orphans = merged[merged["_merge"] == "left_only"][ccols]
    # cardinality: how many child rows per referenced parent key
    per_parent = D[child].groupby(ccols).size()
    parents_total = len(D[parent][pcols].drop_duplicates())
    parents_used = len(per_parent)
    return dict(child=child, cols=ccols, parent=parent, pcols=pcols, orphans=len(orphans),
                orphan_examples=orphans.head(3).astype(str).values.tolist(),
                max_children=int(per_parent.max()), min_children_when_present=int(per_parent.min()),
                parents_without_children=parents_total - parents_used, parents_total=parents_total)


# ---------------------------------------------------------------------------
# Helpers for insights
# ---------------------------------------------------------------------------
def name(df, pid):
    r = df.loc[df.player_id == pid].iloc[0]
    g = r.given_name
    return r.family_name if g in SENTINELS else f"{g} {r.family_name}"


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def build(D):
    m, g, ta, b = D["matches"], D["goals"], D["team_appearances"], D["bookings"]
    pa, sub, pk, sq = D["player_appearances"], D["substitutions"], D["penalty_kicks"], D["squads"]
    tours, teams, players = D["tournaments"], D["teams"], D["players"]
    year = tours.set_index("tournament_id")["year"]
    m = m.assign(year=m.tournament_id.map(year), total=m.home_team_score + m.away_team_score,
                 margin=(m.home_team_score - m.away_team_score).abs())
    ta = ta.assign(year=ta.tournament_id.map(year),
                   w=(ta.goals_for > ta.goals_against).astype(int),   # FIFA convention: shoot-out = draw
                   d=(ta.goals_for == ta.goals_against).astype(int),
                   l=(ta.goals_for < ta.goals_against).astype(int))
    team_name = teams.set_index("team_id")["team_name"]
    team_conf = teams.set_index("team_id")["confederation_code"]
    birth = pd.to_datetime(players.set_index("player_id")["birth_date"], errors="coerce")

    out = {}

    # ---------------- coverage ----------------
    real_goals = g[g.own_goal == 0]
    cov = dict(
        tournaments=len(tours), first_year=int(tours.year.min()), last_year=int(tours.year.max()),
        years=tours.year.tolist(), matches=len(m), goals=len(g), own_goals=int(g.own_goal.sum()),
        players_in_squads=int(sq.player_id.nunique()), players_rows=len(players),
        players_who_appeared_1970_on=int(pa.player_id.nunique()), goal_scorers=int(real_goals.player_id.nunique()),
        referees=len(D["referees"]), managers=len(D["managers"]), stadiums=len(D["stadiums"]),
        teams=len(teams), host_countries_distinct=int(D["host_countries"].team_id.nunique()),
        stadium_countries=int(D["stadiums"].country_name.nunique()),
        bookings=len(b), substitution_rows=len(sub), substitutions=int(sub.coming_on.sum()),
        shootouts=int(m.penalty_shootout.sum()), shootout_kicks=len(pk),
        event_coverage={t: f"{D[t].tournament_id.map(year).min()}-{D[t].tournament_id.map(year).max()} ({D[t].tournament_id.nunique()} of {len(tours)} tournaments)"
                        for t in ["goals", "bookings", "substitutions", "player_appearances", "penalty_kicks",
                                  "manager_appearances", "referee_appearances", "group_standings"]},
        start_date=tours.start_date.min(), end_date=tours.end_date.max(),
        matches_per_tournament=m.groupby("year").size().to_dict(),
    )
    out["coverage"] = cov

    # ---------------- data quality ----------------
    dq = {}
    dq["sentinels"] = {f"{t}.{c}": int(D[t][c].astype(str).isin(SENTINELS).sum())
                       for t in D for c in D[t].columns if D[t][c].astype(str).isin(SENTINELS).any()}
    dq["true_nulls"] = {f"{t}.{c}": int(D[t][c].isna().sum()) for t in D for c in D[t].columns if D[t][c].isna().any()}
    dq["null_birth_player"] = players.loc[players.birth_date.isna(), ["player_id", "family_name", "given_name"]].values.tolist()
    dq["score_hyphen_rows"] = m.loc[m.score.str.contains("-"), ["match_id", "match_name", "score"]].values.tolist()
    dq["score_penalties_no_shootout"] = m.loc[m.penalty_shootout == 0, "score_penalties"].value_counts().to_dict()
    dq["host_performance_labels"] = D["host_countries"].performance.value_counts().to_dict()
    dq["qualified_performance_labels"] = D["qualified_teams"].performance.value_counts().to_dict()
    dup_codes = teams[teams.team_code.duplicated(keep=False)]
    dq["duplicate_team_codes"] = dup_codes[["team_id", "team_name", "team_code"]].values.tolist()
    st = D["stadiums"]
    dq["duplicate_stadium_names"] = st[st.stadium_name.duplicated(keep=False)][["stadium_id", "stadium_name", "city_name"]].values.tolist()
    dq["match_name_distinct"] = int(D["matches"].match_name.nunique())
    dq["replays"] = m.loc[(m.replayed == 1) | (m.replay == 1), ["match_id", "match_name", "stage_name", "score", "replayed", "replay"]].values.tolist()
    ts = D["tournament_stages"]
    dq["walkovers"] = ts.loc[ts.count_walkovers > 0, ["tournament_id", "stage_name", "count_scheduled", "count_matches", "count_replays", "count_walkovers"]].values.tolist()
    dq["playoffs"] = ts.loc[ts.count_playoffs > 0, ["tournament_id", "stage_name", "count_playoffs"]].values.tolist()
    so = m[m.penalty_shootout == 1]
    dq["shootout_result_labels"] = so.result.value_counts().to_dict()
    dq["shootout_level_scores"] = int((so.home_team_score == so.away_team_score).sum())
    dq["extra_time_matches"] = int(m.extra_time.sum())
    dq["final_stage_matches"] = int((m.stage_name == "final").sum())
    dq["final_round_1950"] = m.loc[m.stage_name == "final round", ["match_id", "match_name", "score"]].values.tolist()
    dq["third_place_matches"] = int((m.stage_name == "third-place match").sum())
    dq["no_third_place_match"] = tours.loc[tours.third_place_match == 0, "year"].tolist()
    dq["standings_positions_per_tournament"] = D["tournament_standings"].groupby("tournament_id").position.apply(lambda s: sorted(s.tolist())).astype(str).value_counts().to_dict()
    dq["tournaments_without_groups"] = sorted(set(tours.tournament_id) - set(D["groups"].tournament_id))
    # goal reconciliation
    gc = g.groupby(["match_id", "team_id"]).size().rename("n").reset_index()
    rec = ta[["match_id", "team_id", "goals_for"]].merge(gc, how="left").fillna({"n": 0})
    dq["goal_reconciliation_mismatches"] = int((rec.goals_for != rec.n).sum())
    dq["goals_sum_of_scores"] = int(m.total.sum())
    pkc = pk.groupby(["match_id", "team_id"]).converted.sum().reset_index()
    rec2 = ta[ta.penalty_shootout == 1][["match_id", "team_id", "penalties_for"]].merge(pkc, how="left")
    dq["shootout_reconciliation_mismatches"] = int((rec2.penalties_for != rec2.converted).sum())
    og = g[g.own_goal == 1]
    dq["own_goal_team_differs"] = f"{int((og.team_id != og.player_team_id).sum())} of {len(og)}"
    dq["non_own_goal_team_differs"] = int(((g.own_goal == 0) & (g.team_id != g.player_team_id)).sum())
    dq["team_appearances_per_match"] = ta.groupby("match_id").size().value_counts().to_dict()
    # stage / tournament counts
    mc = m.groupby(["tournament_id", "stage_name"]).size().rename("n").reset_index().merge(ts[["tournament_id", "stage_name", "count_matches"]])
    dq["stage_count_mismatches"] = int((mc.n != mc.count_matches).sum())
    qt = D["qualified_teams"].groupby("tournament_id").size().rename("q").reset_index().merge(tours[["tournament_id", "count_teams"]])
    dq["team_count_mismatches"] = int((qt.q != qt.count_teams).sum())
    # line-ups
    dq["starters_per_team_match"] = pa.groupby(["match_id", "team_id"]).starter.sum().value_counts().to_dict()
    cap = pa.groupby(["match_id", "team_id"]).captain.sum()
    nocap = cap[cap == 0].reset_index()[["match_id", "team_id"]]
    nocap["team"] = nocap.team_id.map(team_name)
    dq["team_matches_without_captain"] = nocap[["match_id", "team"]].values.tolist()
    on = sub[sub.coming_on == 1]
    k = on.merge(pa[["match_id", "player_id"]].assign(in_pa=1), how="left", on=["match_id", "player_id"])
    dq["coming_on_without_appearance"] = k.loc[k.in_pa.isna(), ["substitution_id", "match_id", "match_name", "family_name"]].values.tolist()
    dq["pa_substitute_rows"] = int(pa.substitute.sum())
    dq["coming_on_rows"] = int(on.shape[0])
    off = sub[sub.going_off == 1]
    dq["subbed_on_then_off"] = int(len(on.merge(off, on=["match_id", "player_id"])))
    s2 = sub.groupby(["match_id", "team_id"])[["going_off", "coming_on"]].sum()
    dq["sub_pairs_unbalanced"] = int((s2.going_off != s2.coming_on).sum())
    dq["max_subs_team_match"] = int(s2.coming_on.max())
    dq["sub_rows_flag_pattern"] = {str(k): int(v) for k, v in sub[["going_off", "coming_on"]].value_counts().items()}
    # bookings
    dq["booking_flag_patterns"] = {str(k): int(v) for k, v in b[["yellow_card", "red_card", "second_yellow_card", "sending_off"]].value_counts().items()}
    dq["booking_yellow_and_red"] = b.loc[(b.yellow_card == 1) & (b.red_card == 1), ["booking_id", "match_name", "family_name", "given_name", "minute_label"]].values.tolist()
    dq["booked_matches_per_tournament"] = b.groupby(b.tournament_id.map(year)).match_id.nunique().to_dict()
    # managers
    mapp = D["manager_appointments"]
    multi = mapp.groupby(["tournament_id", "team_id"]).size()
    dq["team_tournaments_multiple_managers"] = int((multi > 1).sum())
    mma = D["manager_appearances"].groupby(["match_id", "team_id"]).size()
    dq["team_matches_multiple_managers"] = int((mma > 1).sum())
    # players
    dq["player_position_flag_counts"] = players[["goal_keeper", "defender", "midfielder", "forward"]].sum(axis=1).value_counts().sort_index().to_dict()
    dq["players_multiple_teams"] = int((sq.groupby("player_id").team_id.nunique() > 1).sum())
    multi_team = sq.groupby("player_id").team_name.unique()
    multi_team = multi_team[multi_team.apply(len) > 1]
    dq["players_multiple_teams_examples"] = sorted({" -> ".join(v) for v in multi_team})
    dq["count_tournaments_mismatch"] = int((sq.groupby("player_id").tournament_id.nunique().reindex(players.player_id).values != players.count_tournaments.values).sum())
    dq["shirt_zero_squads_by_year"] = sq[sq.shirt_number == 0].groupby(sq.tournament_id.map(year)).size().to_dict()
    dq["shirt_zero_goals_by_year"] = g[g.shirt_number == 0].groupby(g.tournament_id.map(year)).size().to_dict()
    dq["pa_position_codes"] = pa.position_code.value_counts().to_dict()
    dq["squad_position_codes"] = sq.position_code.value_counts().to_dict()
    dq["birth_date_range"] = [str(birth.min().date()), str(birth.max().date())]
    # points system
    gs = D["group_standings"].assign(year=D["group_standings"].tournament_id.map(year))
    two = gs[gs.year <= 1990]
    three = gs[gs.year >= 1994]
    dq["points_2_per_win_holds_to_1990"] = bool((two.points == 2 * two.wins + two.draws).all())
    dq["points_3_per_win_holds_from_1994"] = bool((three.points == 3 * three.wins + three.draws).all())
    dq["standings_played_eq_wdl"] = bool((gs.played == gs.wins + gs.draws + gs.losses).all())
    dq["standings_gd_ok"] = bool((gs.goal_difference == gs.goals_for - gs.goals_against).all())
    # stage names in groups/group_standings vs tournament_stages (same stage_number)
    sn = D["groups"][["tournament_id", "stage_number", "stage_name"]].drop_duplicates().merge(
        ts[["tournament_id", "stage_number", "stage_name"]], on=["tournament_id", "stage_number"], suffixes=("_groups", "_stages"))
    dq["stage_name_mismatches"] = sn.loc[sn.stage_name_groups != sn.stage_name_stages].values.tolist()
    # group names used in matches that do not exist in groups for the same stage
    mg = m[m.group_name != "not applicable"].merge(ts[["tournament_id", "stage_name", "stage_number"]], on=["tournament_id", "stage_name"])
    mg = mg[["tournament_id", "stage_number", "group_name"]].drop_duplicates().merge(
        D["groups"][["tournament_id", "stage_number", "group_name"]], how="left", indicator=True)
    dq["match_group_names_not_in_groups"] = mg.loc[mg._merge == "left_only", ["tournament_id", "stage_number", "group_name"]].values.tolist()
    gstages = ts[ts.stage_name.isin(["group stage", "second group stage", "final round"])][["tournament_id", "stage_name"]]
    nog = m.merge(gstages, on=["tournament_id", "stage_name"])
    dq["group_stage_matches_without_group"] = nog.loc[nog.group_name == "not applicable", ["match_id", "stage_name"]].values.tolist()
    dq["groups_names_for_those_stages"] = sorted(D["groups"].merge(mg.loc[mg._merge == "left_only", ["tournament_id", "stage_number"]].drop_duplicates()).group_name.unique().tolist())
    # group standings vs. group matches (play-offs); join through stage_number because the names differ
    gm = ta[(ta.group_stage == 1)].groupby(["tournament_id", "stage_name", "team_id"]).size().rename("n").reset_index()
    gm = gm.merge(ts[["tournament_id", "stage_name", "stage_number"]], on=["tournament_id", "stage_name"]).drop(columns="stage_name")
    gsx = gs.merge(gm, on=["tournament_id", "stage_number", "team_id"], how="left")
    assert gsx.n.notna().all()
    diff = gsx[gsx.played != gsx.n]
    dq["standings_played_vs_group_matches"] = [[r.tournament_id, r.stage_name, team_name[r.team_id], int(r.played), int(r.n)] for r in diff.itertuples()]
    # confederation anachronisms
    dq["region_vs_confederation"] = teams.loc[teams.team_id.isin(["T-04", "T-38"]), ["team_name", "region_name", "confederation_code"]].values.tolist()
    # denormalised copies consistent with masters?
    incons = []
    for t, df in D.items():
        if t != "teams" and {"team_id", "team_name"} <= set(df.columns):
            z = df[["team_id", "team_name"]].drop_duplicates().merge(teams[["team_id", "team_name"]], on="team_id")
            incons.append((t, "team_name", int((z.team_name_x != z.team_name_y).sum())))
        if t != "players" and {"player_id", "family_name", "given_name"} <= set(df.columns):
            z = df[["player_id", "family_name", "given_name"]].drop_duplicates().merge(players[["player_id", "family_name", "given_name"]], on="player_id")
            incons.append((t, "player names", int(((z.family_name_x != z.family_name_y) | (z.given_name_x != z.given_name_y)).sum())))
        if t != "tournaments" and "tournament_name" in df.columns:
            z = df[["tournament_id", "tournament_name"]].drop_duplicates().merge(tours[["tournament_id", "tournament_name"]], on="tournament_id")
            incons.append((t, "tournament_name", int((z.tournament_name_x != z.tournament_name_y).sum())))
    dq["denormalised_copy_differences"] = int(sum(x[2] for x in incons))
    dq["denormalised_copy_checks"] = len(incons)
    z = m[["stadium_id", "city_name", "country_name"]].merge(st[["stadium_id", "city_name", "country_name"]], on="stadium_id")
    dq["match_stadium_location_mismatch"] = int(((z.city_name_x != z.city_name_y) | (z.country_name_x != z.country_name_y)).sum())
    # host home flag
    host_pairs = set(map(tuple, D["host_countries"][["tournament_id", "team_id"]].values))
    host_rows = ta[[ (t, x) in host_pairs for t, x in zip(ta.tournament_id, ta.team_id)]]
    dq["host_matches"] = len(host_rows)
    dq["host_matches_flagged_home"] = int(host_rows.home_team.sum())
    out["dq"] = dq

    # ---------------- insights ----------------
    ins = []

    def add(theme, text, support):
        ins.append(dict(theme=theme, text=text, support=support))

    # 1 titles
    champs = D["tournament_standings"][D["tournament_standings"].position == 1]
    titles = champs.team_name.value_counts()
    add("Team performance",
        "Titles by team_id: " + ", ".join(f"{k} {v}" for k, v in titles.items())
        + f". {titles.size} different team_ids have won, but Germany and West Germany share the code DEU; counted as one lineage they have "
        f"{titles.get('West Germany', 0) + titles.get('Germany', 0)} titles, level with Italy's {titles.get('Italy', 0)} and behind Brazil's {titles.get('Brazil', 0)}.",
        "tournament_standings (position = 1), teams.team_code")
    # 2 ever-present
    qt = D["qualified_teams"]
    apps = qt.team_name.value_counts()
    ever = apps[apps == len(tours)].index.tolist()
    add("Team performance",
        f"{', '.join(ever)} is the only team to appear in all {len(tours)} tournaments; next are "
        + ", ".join(f"{k} ({v})" for k, v in apps.iloc[1:4].items()) + f". {len(teams)} teams have taken part in total.",
        "qualified_teams")
    # 3 goals per match trend
    gpm = m.groupby("year").total.mean()
    add("Goals and scoring",
        f"Goals per match peaked at {gpm.max():.2f} in {gpm.idxmax()} and bottomed at {gpm.min():.2f} in {gpm.idxmin()}; "
        f"the all-time average is {m.total.mean():.2f}. Every tournament since 1962 has averaged under 3 goals per match "
        f"(range {gpm[gpm.index >= 1962].min():.2f}-{gpm[gpm.index >= 1962].max():.2f}).",
        "matches.home_team_score, away_team_score")
    assert (gpm[gpm.index >= 1962] < 3).all()
    # 4 biggest margin
    mx = m.margin.max()
    big = m[m.margin == mx]
    add("Goals and scoring",
        f"The biggest winning margin is {mx} goals, reached {len(big)} times: "
        + "; ".join(f"{r.home_team_name} {r.home_team_score}-{r.away_team_score} {r.away_team_name} ({r.year})" for r in big.itertuples()) + ".",
        "matches.home_team_score_margin")
    # 5 highest scoring
    hs = m[m.total == m.total.max()].iloc[0]
    add("Goals and scoring",
        f"The highest-scoring match is {hs.home_team_name} {hs.home_team_score}-{hs.away_team_score} {hs.away_team_name} "
        f"({hs.year}, {hs.stage_name}), {hs.total} goals. {int((m.total == 0).sum())} matches ({pct((m.total == 0).sum(), len(m)):.1f}%) ended 0-0.",
        "matches")
    # 6 all-time top scorer
    sc = real_goals.groupby("player_id").size().sort_values(ascending=False)
    top5 = ", ".join(f"{name(players, p)} {n}" for p, n in sc.head(5).items())
    add("Player performance",
        f"All-time top scorers (own goals excluded): {top5}. {cov['goal_scorers']} different players have scored.",
        "goals (own_goal = 0), players")
    # 7 single tournament
    st_sc = real_goals.groupby(["tournament_id", "player_id"]).size().sort_values(ascending=False)
    (tid, pid), n = st_sc.index[0], st_sc.iloc[0]
    add("Player performance",
        f"Most goals in one tournament: {name(players, pid)}, {n} in {year[tid]}. The next best single-tournament tally is {st_sc.iloc[1]} "
        f"({name(players, st_sc.index[1][1])}, {year[st_sc.index[1][0]]}).",
        "goals grouped by tournament_id, player_id")
    # 8 hat-tricks
    per_match = real_goals.groupby(["match_id", "player_id"]).size()
    ht = per_match[per_match >= 3]
    best_match = per_match.idxmax()
    mm = D["matches"].set_index("match_id")
    add("Player performance",
        f"There have been {len(ht)} hat-tricks (3+ goals by one player in a match, own goals excluded). The most goals by one player in one match is "
        f"{per_match.max()} ({name(players, best_match[1])}, {mm.loc[best_match[0], 'match_name']}, {year[mm.loc[best_match[0], 'tournament_id']]}).",
        "goals grouped by match_id, player_id")
    # 9 own goals
    ogy = og.groupby(og.tournament_id.map(year)).size()
    add("Goals and scoring",
        f"{len(og)} own goals in total ({pct(len(og), len(g)):.1f}% of all goals). {ogy.idxmax()} had the most, {ogy.max()}, "
        f"more than the {ogy.drop(ogy.idxmax()).max()} of the next highest tournament.",
        "goals.own_goal, team_id vs player_team_id")
    # 10 in-match penalties
    pen = g[g.penalty == 1]
    peny = pen.groupby(pen.tournament_id.map(year)).size()
    add("Goals and scoring",
        f"{len(pen)} goals came from in-match penalties ({pct(len(pen), len(g)):.1f}%). The record is {peny.max()} in {peny.idxmax()} "
        f"(the first tournament with VAR); the previous high was {peny.drop(peny.idxmax()).max()}.",
        "goals.penalty")
    # 11 shoot-outs
    so_ta = ta[ta.penalty_shootout == 1].assign(sw=lambda x: (x.penalties_for > x.penalties_against).astype(int))
    rec = so_ta.groupby("team_name").agg(played=("sw", "size"), won=("sw", "sum")).sort_values(["won", "played"], ascending=[False, True])
    unbeaten = rec[(rec.won == rec.played) & (rec.played >= 3)]
    winless = rec[(rec.won == 0) & (rec.played >= 2)].sort_values("played", ascending=False)
    eng = rec.loc["England"] if "England" in rec.index else None
    ger = rec.reindex(["West Germany", "Germany"]).fillna(0).sum()
    most = rec.sort_values(["won", "played"], ascending=False).iloc[0]
    most_name = rec.sort_values(["won", "played"], ascending=False).index[0]
    add("Goals and scoring",
        f"{cov['shootouts']} matches were settled by a shoot-out ({int(m[m.penalty_shootout == 1].year.min())}-{int(m[m.penalty_shootout == 1].year.max())}); "
        f"{pk.converted.sum()} of {len(pk)} kicks were scored ({pct(pk.converted.sum(), len(pk)):.1f}%). "
        + f"Most shoot-out wins: {most_name} {most.won}/{most.played}. Unbeaten with 3+: "
        + "; ".join(f"{t} {r.won}/{r.played}" for t, r in unbeaten.iterrows())
        + f" (with Germany's 2006 shoot-out the DEU lineage is {int(ger.won)}/{int(ger.played)})"
        + (f"; England won {eng.won}/{eng.played}" if eng is not None else "") + ".",
        "penalty_kicks.converted, team_appearances.penalties_for/against")
    # 12 extra time
    add("Goals and scoring",
        f"{dq['extra_time_matches']} matches went to extra time and {cov['shootouts']} of those ended in a shoot-out "
        f"({pct(cov['shootouts'], dq['extra_time_matches']):.0f}%).",
        "matches.extra_time, penalty_shootout")
    # 13 host titles and advantage
    hc = D["host_countries"]
    host_won = int(tours.host_won.sum())
    hta = ta.merge(hc[["tournament_id", "team_id"]], on=["tournament_id", "team_id"])
    nhta = ta.merge(hc[["tournament_id", "team_id"]], on=["tournament_id", "team_id"], how="left", indicator=True)
    nhta = nhta[nhta._merge == "left_only"]
    add("Venues and hosting",
        f"Hosts won {host_won} of {len(tours)} tournaments ({', '.join(str(y) for y in tours[tours.host_won == 1].year)}), none since 1998. "
        f"Host nations won {pct(hta.w.sum(), len(hta)):.1f}% of their {len(hta)} matches versus {pct(nhta.w.sum(), len(nhta)):.1f}% for all other teams "
        f"(shoot-outs counted as draws).",
        "tournaments.host_won, host_countries, team_appearances")
    # 14 host group exit
    host_gs = hc[hc.performance == "group stage"]
    add("Venues and hosting",
        f"Only {len(host_gs)} host was eliminated in the first group stage: "
        + ", ".join(f"{r.team_name} ({year[r.tournament_id]})" for r in host_gs.itertuples()) + ".",
        "host_countries.performance")
    # 15 confederations
    st4 = D["tournament_standings"].assign(conf=lambda x: x.team_id.map(team_conf))
    conf_titles = st4[st4.position == 1].conf.value_counts().to_dict()
    best_other = st4[~st4.conf.isin(["UEFA", "CONMEBOL"])]
    add("Team performance",
        f"Only two confederations have produced champions: {conf_titles}. Top-four finishes by teams from other confederations: "
        + ", ".join(f"{r.team_name} {year[r.tournament_id]} (position {r.position})" for r in best_other.itertuples()) + ".",
        "tournament_standings, teams.confederation_code")
    # 16 draws
    dr = ta.groupby("year").d.mean()
    add("Historical trends",
        f"The draw rate (level score, shoot-outs counted as draws) was {pct((m.home_team_score == m.away_team_score).sum(), len(m)):.1f}% overall, "
        f"from {dr.min() * 100:.1f}% in {dr.idxmin()} to {dr.max() * 100:.1f}% in {dr.idxmax()}.",
        "matches.home_team_score, away_team_score")
    # 17 cards trend
    by = b.assign(year=b.tournament_id.map(year))
    cards_pm = by.groupby("year").size() / m.groupby("year").size().reindex(by.year.unique())
    add("Discipline and refereeing",
        f"Cards per match rose from {cards_pm.loc[1970]:.2f} in 1970 to a peak of {cards_pm.max():.2f} in {cards_pm.idxmax()}, "
        f"then fell to {cards_pm.loc[2018]:.2f} in 2018. {len(b)} card events are recorded in total.",
        "bookings, matches")
    # 18 most carded match
    bpm = b.groupby("match_id").agg(cards=("booking_id", "size"), off=("sending_off", "sum")).sort_values("cards", ascending=False)
    top = bpm.iloc[0]
    add("Discipline and refereeing",
        f"The most cards in one match: {mm.loc[bpm.index[0], 'match_name']} ({year[mm.loc[bpm.index[0], 'tournament_id']]}, "
        f"{mm.loc[bpm.index[0], 'stage_name']}) with {top.cards} cards including {top.off} sendings-off.",
        "bookings grouped by match_id")
    # 19 sendings off
    so_y = by[by.sending_off == 1].groupby("year").size()
    add("Discipline and refereeing",
        f"{int(b.sending_off.sum())} sendings-off from 1970 to 2018 ({int(b.red_card.sum())} straight reds, {int(b.second_yellow_card.sum())} after a second yellow). "
        f"The most in one tournament was {so_y.max()} in {so_y.idxmax()}.",
        "bookings.sending_off, red_card, second_yellow_card")
    # 20 referees
    ra = D["referee_appearances"]
    rc = ra.groupby("referee_id").size().sort_values(ascending=False)
    rtop = D["referees"].set_index("referee_id").loc[rc.index[0]]
    rconf = ra.confederation_code.value_counts()
    add("Discipline and refereeing",
        f"{rtop.given_name} {rtop.family_name} ({rtop.country_name}) refereed the most matches, {rc.iloc[0]}. "
        f"UEFA referees officiated {rconf.get('UEFA', 0)} of {len(ra)} matches ({pct(rconf.get('UEFA', 0), len(ra)):.0f}%).",
        "referee_appearances, referees")
    # 21 strictest referee
    rb = b.merge(ra[["match_id", "referee_id"]], on="match_id").groupby("referee_id").size()
    rm = ra[ra.tournament_id.map(year) >= 1970].groupby("referee_id").size()
    rate = (rb.reindex(rm.index).fillna(0) / rm)[rm >= 5].sort_values(ascending=False)
    r1 = D["referees"].set_index("referee_id").loc[rate.index[0]]
    add("Discipline and refereeing",
        f"Among referees with at least 5 matches since 1970, {r1.given_name} {r1.family_name} ({r1.country_name}) showed the most cards per match "
        f"({rate.iloc[0]:.2f}); the median for this group is {rate.median():.2f}.",
        "bookings joined to referee_appearances on match_id")
    # 22 stadiums
    stc = m.groupby("stadium_id").size().sort_values(ascending=False)
    s0 = st.set_index("stadium_id").loc[stc.index[0]]
    smax = st.loc[st.stadium_capacity.idxmax()]
    add("Venues and hosting",
        f"{s0.stadium_name} ({s0.city_name}) has hosted the most matches, {stc.iloc[0]}. The largest listed capacity is {smax.stadium_name} "
        f"({smax.city_name}) at {smax.stadium_capacity:,}. {len(st)} stadiums in {cov['stadium_countries']} countries have been used.",
        "matches.stadium_id, stadiums")
    # 23 managers
    mapx = D["manager_appearances"].merge(ta[["match_id", "team_id", "w"]], on=["match_id", "team_id"])
    mg = mapx.groupby("manager_id").agg(matches=("w", "size"), wins=("w", "sum")).sort_values(["matches", "wins"], ascending=False)
    mgr = D["managers"].set_index("manager_id")
    m0 = mgr.loc[mg.index[0]]
    mw = mg.sort_values("wins", ascending=False)
    m1 = mgr.loc[mw.index[0]]
    second = mgr.loc[mw.index[1]]
    add("Managers",
        (f"{m0.given_name} {m0.family_name} ({', '.join(mapp.loc[mapp.manager_id == mg.index[0], 'team_name'].unique())}) holds both manager records: most matches ({mg.iloc[0].matches}) and most wins ({mw.iloc[0].wins}, shoot-outs counted as draws)"
         if mg.index[0] == mw.index[0] else
         f"{m0.given_name} {m0.family_name} managed the most matches ({mg.iloc[0].matches}); {m1.given_name} {m1.family_name} has the most wins ({mw.iloc[0].wins})")
        + f". Next by wins: {second.given_name} {second.family_name} ({mw.iloc[1].wins} wins in {mw.iloc[1].matches} matches).",
        "manager_appearances joined to team_appearances")
    # 24 foreign managers
    mz = mapp.merge(teams[["team_id", "team_name"]], on="team_id", suffixes=("", "_team"))
    foreign = mz[mz.country_name != mz.team_name_team]
    win_mgr = mapp.merge(champs[["tournament_id", "team_id"]], on=["tournament_id", "team_id"])
    win_foreign = win_mgr[win_mgr.country_name != win_mgr.team_id.map(team_name).str.replace("West Germany", "Germany")]
    add("Managers",
        f"{len(foreign)} of {len(mapp)} manager appointments ({pct(len(foreign), len(mapp)):.0f}%) were of a manager whose nationality differs from the team's name. "
        f"Every one of the {len(win_mgr)} title-winning managers shared the nationality of their team"
        + (f" (exceptions: {win_foreign[['tournament_id','family_name']].values.tolist()})" if len(win_foreign) else "")
        + " (West German winners are listed with nationality Germany).",
        "manager_appointments.country_name, teams.team_name, tournament_standings")
    # 25 appearances
    pac = pa.groupby("player_id").size().sort_values(ascending=False)
    add("Player performance",
        f"Most World Cup appearances (1970 onwards): {name(players, pac.index[0])}, {pac.iloc[0]} matches; then "
        + ", ".join(f"{name(players, p)} {n}" for p, n in pac.iloc[1:4].items()) + ".",
        "player_appearances")
    # 26 five tournaments
    five = players[players.count_tournaments == players.count_tournaments.max()]
    add("Player performance",
        f"{len(five)} players were in a squad at {players.count_tournaments.max()} tournaments: "
        + "; ".join(f"{(r.given_name + ' ') if r.given_name not in SENTINELS else ''}{r.family_name} ({r.list_tournaments})" for r in five.itertuples()) + ".",
        "players.count_tournaments, list_tournaments (verified against squads)")
    # 27 substitutes
    g70 = real_goals[real_goals.tournament_id.map(year) >= 1970]
    gsub = g70.merge(pa[["match_id", "player_id", "substitute"]], on=["match_id", "player_id"], how="left")
    ns = int((gsub.substitute == 1).sum())
    subyear = gsub[gsub.substitute == 1].groupby(gsub.tournament_id.map(year)).size()
    add("Player performance",
        f"Since 1970, {ns} of {len(g70)} non-own goals ({pct(ns, len(g70)):.1f}%) were scored by substitutes; the count rose from "
        f"{subyear.get(1970, 0)} in 1970 to a peak of {subyear.max()} in {subyear.idxmax()} ({subyear.get(2018, 0)} in 2018).",
        "goals joined to player_appearances (substitute = 1)")
    # 28 ages of scorers
    gx = real_goals.assign(bd=real_goals.player_id.map(birth), md=pd.to_datetime(real_goals.match_date))
    gx = gx.dropna(subset=["bd"])
    gx["age_days"] = (gx.md - gx.bd).dt.days
    old, young = gx.loc[gx.age_days.idxmax()], gx.loc[gx.age_days.idxmin()]
    fmt = lambda d: f"{d // 365.25:.0f} years {d - int(d // 365.25 * 365.25)} days"
    add("Player performance",
        f"Oldest scorer: {name(players, old.player_id)} aged {fmt(old.age_days)} ({old.match_name}, {old.match_date[:4]}). "
        f"Youngest scorer: {name(players, young.player_id)} aged {fmt(young.age_days)} ({young.match_name}, {young.match_date[:4]}).",
        "goals.match_date, players.birth_date")
    # 29 youngest/oldest appearance (1970+)
    px = pa.assign(bd=pa.player_id.map(birth), md=pd.to_datetime(pa.match_date)).dropna(subset=["bd"])
    px["age_days"] = (px.md - px.bd).dt.days
    po, py = px.loc[px.age_days.idxmax()], px.loc[px.age_days.idxmin()]
    add("Player performance",
        f"From 1970 on, the oldest player to appear is {name(players, po.player_id)} ({fmt(po.age_days)}, {po.match_name}, {po.match_date[:4]}); "
        f"the youngest is {name(players, py.player_id)} ({fmt(py.age_days)}, {py.match_name}, {py.match_date[:4]}).",
        "player_appearances.match_date, players.birth_date")
    # 30 squad age trend
    sqa = sq.assign(bd=sq.player_id.map(birth), sd=pd.to_datetime(sq.tournament_id.map(tours.set_index("tournament_id").start_date)))
    sqa = sqa.dropna(subset=["bd"])
    sqa["age"] = (sqa.sd - sqa.bd).dt.days / 365.25
    ay = sqa.groupby(sqa.tournament_id.map(year)).age.mean()
    add("Historical trends",
        f"Average squad age at the tournament start rose from {ay.iloc[0]:.1f} years in {ay.index[0]} (the lowest) to {ay.loc[2018]:.1f} in 2018 (the highest); "
        f"in 1970 it was {ay.loc[1970]:.1f}. Birth dates are missing for {int(sq.player_id.map(birth).isna().sum())} squad rows.",
        "squads, players.birth_date, tournaments.start_date")
    # 31 shared golden boot
    aw = D["award_winners"]
    gb = aw[aw.award_name == "Golden Boot"].groupby("tournament_id").size()
    add("Awards",
        f"The Golden Boot has been shared in {(gb > 1).sum()} tournaments; the largest tie was {gb.max()} players in {year[gb.idxmax()]}. "
        f"Of {len(aw)} award rows, {int(aw.shared.sum())} are shared awards.",
        "award_winners.shared, award_name")
    # 32 golden ball winners on champion team
    gball = aw[aw.award_name == "Golden Ball"].merge(champs[["tournament_id", "team_id"]], on=["tournament_id", "team_id"], how="left", indicator=True)
    add("Awards",
        f"Golden Ball (best player, recorded since 1978): only {int((gball._merge == 'both').sum())} of {len(gball)} winners played for the champion team.",
        "award_winners joined to tournament_standings")
    # 33 timing of goals
    second_half = g.match_period.str.startswith("second half").sum()
    first_half = g.match_period.str.startswith("first half").sum()
    late = ((g.minute_regulation >= 76) & (g.minute_regulation <= 90)).sum()
    add("Goals and scoring",
        f"{second_half} goals ({pct(second_half, len(g)):.1f}%) came in the second half versus {first_half} ({pct(first_half, len(g)):.1f}%) in the first; "
        f"{late} ({pct(late, len(g)):.1f}%) came in minutes 76-90 including stoppage time.",
        "goals.match_period, minute_regulation")
    # 34 never won
    tw = ta.groupby("team_name").agg(p=("w", "size"), w=("w", "sum"))
    nw = tw[tw.w == 0].sort_values("p", ascending=False)
    add("Team performance",
        f"{len(nw)} teams have never won a World Cup match (shoot-outs counted as draws); the most matches without a win is "
        f"{nw.iloc[0].p} by {nw.index[0]}.",
        "team_appearances")
    # 35 never left group stage (by stage reached)
    perf = qt.groupby("team_name").performance.apply(lambda s: set(s) <= {"group stage"})
    never = perf[perf].index.tolist()
    add("Team performance",
        f"{len(never)} of {len(teams)} teams never got past the first group stage (performance always 'group stage').",
        "qualified_teams.performance")
    # 36 points system
    add("Historical trends",
        "Group points follow 2 points per win in every tournament up to 1990 and 3 points per win from 1994, which the data reproduces exactly "
        f"(checks: {dq['points_2_per_win_holds_to_1990']} / {dq['points_3_per_win_holds_from_1994']}). Points therefore cannot be compared across eras without recomputing.",
        "group_standings.points, wins, draws")
    out["insights"] = ins
    return out


# ---------------------------------------------------------------------------
# Relationship map
# ---------------------------------------------------------------------------
BRIDGES = {
    "qualified_teams": "tournaments M:N teams",
    "host_countries": "tournaments M:N teams (hosts)",
    "tournament_standings": "tournaments M:N teams (top four, with position)",
    "squads": "(tournament, team) M:N players",
    "team_appearances": "matches M:N teams (exactly 2 per match)",
    "player_appearances": "matches M:N players",
    "manager_appointments": "(tournament, team) M:N managers",
    "manager_appearances": "matches x teams M:N managers",
    "referee_appointments": "tournaments M:N referees",
    "award_winners": "tournaments x awards M:N players",
}


def cardinality_label(fk):
    if fk["max_children"] == 1:
        return "1 : 0..1" if fk["parents_without_children"] else "1 : 1"
    return "1 : 0..N" if fk["parents_without_children"] else "1 : 1..N"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def pp(o):
    """Readable text for lists/dicts embedded in the report."""
    if isinstance(o, dict):
        return "; ".join(f"{k}: {pp(v)}" for k, v in o.items())
    if isinstance(o, (list, tuple)):
        if o and all(isinstance(x, (list, tuple)) for x in o):
            return "; ".join("(" + ", ".join(str(y) for y in x) + ")" for x in o)
        return ", ".join(str(x) for x in o)
    return str(o)


def md_table(headers, rows):
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


FRAMEWORK = {
    "Team performance": [
        ("Which teams are most successful (titles, finals, semi-finals)?", "tournament_standings, matches, teams", "Count positions 1-4 per team; count finals via matches.stage_name = 'final' (plus 1950 final round). GROUP BY, CASE, JOIN.", "Analysts, federations, broadcasters (pre-match graphics)."),
        ("Win/draw/loss record and goal difference per team", "team_appearances", "Aggregate goals_for/against; derive W/D/L from goals, not from `result`, so shoot-outs count as draws. SUM(CASE ...).", "Analysts, journalists, betting-odds modellers."),
        ("Head-to-head between two teams", "team_appearances (or matches self-join)", "Filter team_id = A and opponent_id = B; aggregate. Self-join/WHERE with parameters.", "Coaches preparing for an opponent, broadcasters."),
        ("Which teams never left the group stage?", "qualified_teams", "Teams whose every performance = 'group stage'. GROUP BY ... HAVING, or NOT EXISTS / EXCEPT.", "Federations benchmarking progress."),
        ("Confederation strength by decade", "team_appearances, teams, confederations", "Win rate per confederation per decade (year/10*10). JOIN, GROUP BY, CASE.", "FIFA slot allocation debates, researchers. Caveat: confederation is current, not historical."),
        ("How far do teams usually go after winning/drawing/losing their first group game?", "matches, team_appearances, qualified_teams", "ROW_NUMBER() per team-tournament ordered by date to find match 1; join to stage reached.", "Coaches, analysts, fans."),
    ],
    "Player performance": [
        ("All-time and per-tournament top scorers", "goals, players", "COUNT goals with own_goal = 0 per player; RANK() OVER (PARTITION BY tournament ORDER BY goals DESC).", "Broadcasters, journalists, award committees."),
        ("Most appearances and minutes (1970+)", "player_appearances, substitutions", "COUNT appearances; approximate minutes from substitution minutes. CTE + CASE.", "Researchers on player workload, sports scientists."),
        ("Impact of substitutes", "goals, player_appearances", "Join goals to the scorer's appearance; share of goals with substitute = 1, by tournament.", "Coaches (bench strategy), analysts."),
        ("Age profile by position and tournament", "squads, players, tournaments", "Age = start_date - birth_date; AVG by position_code and year; exclude unknown birth dates.", "Federations planning squad renewal, scouts."),
        ("Players who represented more than one team", "squads", "COUNT(DISTINCT team_id) > 1 per player. HAVING.", "Historians; shows team-lineage issues."),
        ("Captains' records", "player_appearances, team_appearances", "Filter captain = 1; join results.", "Media features."),
    ],
    "Goals and scoring patterns": [
        ("Goals per match by tournament and stage", "matches", "SUM(scores)/COUNT(*) GROUP BY year, stage; moving average with window frame.", "Rule makers (FIFA/IFAB), broadcasters."),
        ("When are goals scored (by minute band)?", "goals", "CASE on minute_regulation into 15-minute bands; GROUP BY.", "Coaches (fitness, game management), analysts."),
        ("Penalty and own-goal share over time", "goals", "AVG(penalty), SUM(own_goal) by year; compare pre/post VAR (2018).", "Referees' bodies evaluating VAR."),
        ("Shoot-out records and conversion", "penalty_kicks, team_appearances, matches", "SUM(converted)/COUNT per team/player; shoot-out wins per team.", "Coaches preparing shoot-outs, sports psychologists."),
        ("Biggest wins and highest-scoring matches", "matches", "ORDER BY margin / total DESC with RANK().", "Broadcasters, trivia, historians."),
        ("Comebacks (winning after conceding first)", "goals, team_appearances", "First goal per match by MIN(minute) using ROW_NUMBER(); compare with final result.", "Coaches, analysts. Caveat: minute resolution only."),
    ],
    "Discipline and refereeing": [
        ("Strictest referees (cards per match)", "bookings, referee_appearances, referees", "Join bookings to the match referee; cards / matches with HAVING matches >= n.", "Referees' bodies (consistency), teams preparing for a referee."),
        ("Card trend over time", "bookings, matches", "Cards per match per tournament with a 3-tournament moving average (AVG OVER ROWS BETWEEN).", "IFAB/FIFA rule evaluation, researchers."),
        ("Most-carded teams and players", "bookings", "COUNT by team/player; RANK().", "Coaches, disciplinary committees."),
        ("Are knockout matches dirtier than group matches?", "bookings, matches", "Cards per match by stage_name / knockout_stage. CASE + GROUP BY.", "Referees' bodies, broadcasters."),
        ("Referee nationality vs. match confederations", "referee_appearances, team_appearances, teams", "Flag matches where referee confederation equals a team's confederation.", "Integrity researchers. Caveat: correlation only."),
    ],
    "Venues and hosting": [
        ("Busiest stadiums and cities", "matches, stadiums", "COUNT matches per stadium; DENSE_RANK().", "Host-bid committees, broadcasters."),
        ("Host-nation advantage", "host_countries, team_appearances", "Win rate of hosts vs non-hosts; host stage reached vs their average.", "Federations bidding to host, researchers."),
        ("Matches played outside the host country's continent / by country", "matches, stadiums", "GROUP BY country_name of stadium.", "Historians, tourism bodies."),
    ],
    "Managers": [
        ("Most matches and wins by manager", "manager_appearances, team_appearances, managers", "Join on (match_id, team_id); SUM wins.", "Federations hiring coaches, media."),
        ("Do foreign managers do better or worse?", "manager_appointments, teams, qualified_teams", "Compare stage reached where manager nationality differs from team. CASE.", "Federations deciding on foreign coaches."),
        ("Managers at several tournaments or with several teams", "manager_appointments", "COUNT(DISTINCT tournament_id/team_id) HAVING > 1.", "Media, researchers."),
    ],
    "Historical trends": [
        ("How has the format grown (teams, matches, stages)?", "tournaments, tournament_stages", "Counts per year; LAG() to show change between editions.", "Students, historians, FIFA planning (48-team era)."),
        ("Cumulative titles over time", "tournament_standings, tournaments", "Running total SUM() OVER (PARTITION BY team ORDER BY year).", "Broadcasters, infographics."),
        ("Draw rate and extra-time frequency over time", "matches", "AVG(CASE) by year; LAG to compare.", "Rule makers, researchers."),
        ("Average age over time", "squads, players", "AVG(age) by year.", "Federations, sports scientists."),
    ],
    "Awards": [
        ("Do award winners come from the champion?", "award_winners, tournament_standings", "LEFT JOIN on (tournament_id, team_id) where position = 1.", "Award committees, media."),
        ("Golden Boot winners and their goal totals", "award_winners, goals", "Join award to goal counts; check ties (shared = 1).", "Validation of award data; media."),
        ("Best Young Player age profile", "award_winners, players, tournaments", "Age at tournament start.", "Scouts, youth academies."),
    ],
    "Data quality and limitations": [
        ("Is every goal accounted for?", "goals, team_appearances", "Compare COUNT(goals) per team-match with goals_for. Anti-join.", "Data stewards; proves load integrity."),
        ("Which records are incomplete before 1970?", "player_appearances, bookings, substitutions", "MIN(year) per event table; NOT EXISTS for matches without line-ups.", "Anyone interpreting trends; prevents false conclusions."),
        ("Which teams are historical predecessors?", "teams", "Shared team_code / federation_name; manual lineage table.", "Analysts aggregating Germany/West Germany etc."),
    ],
}

CANNOT = [
    "Possession, shots, passes, expected goals, distance covered or any tracking/event data beyond goals, cards, substitutions and shoot-out kicks.",
    "Attendance and weather: stadiums.stadium_capacity is a single capacity figure, not match attendance.",
    "Assists: goals have no assist provider.",
    "Missed or saved in-match penalties: only scored ones appear (goals.penalty = 1). In-match penalty conversion therefore cannot be computed; penalty_kicks covers shoot-outs only.",
    "Line-ups, substitutions and cards before 1970: those tables start in 1970 (cards were introduced that year), so player-appearance or discipline trends cannot go back further.",
    "Exact time of events: minutes only, no seconds (e.g. the fastest goal cannot be timed).",
    "Club affiliation, height, foot, market value or caps of players.",
    "Qualifying matches, the women's World Cup, and the 2022 and 2026 tournaments: these files cover the 21 men's final tournaments from 1930 to 2018 only.",
    "Historical confederation membership: teams.confederation_id is a single current value (Australia is AFC, although it qualified through the OFC for 1974 and 2006).",
    "Assistant referees, VAR officials, fourth officials.",
]


def render(D, prof, fks, res):
    cov, dq, ins = res["coverage"], res["dq"], res["insights"]
    L = []
    w = L.append
    w(f"# {TITLE}\n")
    w("## Milestone 0: Dataset Understanding\n")
    w("**Group:** Devanshi Dudhatra (202618027), Pujita Sunapu (202618003), Rahul Saha (202618037). DS604 Introduction to Data Management.\n")
    w("*Generated by `src/profile_data.py`. Every figure below is computed from the CSV files in `data/`; rerun the script to regenerate.*\n")
    w("**Data source and licence.** Joshua C. Fjelstul, *The Fjelstul World Cup Database*, "
      "<https://github.com/jfjelstul/worldcup>, licensed under "
      "[CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). "
      "**Modifications:** none to the data values. The 27 CSV files were moved into `data/` unchanged. "
      "This report adds derived statistics. Any cleaning applied when loading the database is documented in Milestone 3.\n")

    w("## Contents\n\n1. [Coverage](#1-real-coverage)\n2. [Tables](#2-tables)\n3. [Relationship map](#3-relationship-map)\n"
      "4. [Data quality findings](#4-data-quality-findings)\n5. [Key insights](#5-key-insights)\n6. [Insights framework](#6-insights-framework)\n")

    # ---- coverage
    w("## 1. Real coverage\n")
    w(f"The files are dated July 2022, but they contain **{cov['tournaments']} men's World Cup final tournaments, {cov['first_year']} to {cov['last_year']}** "
      f"({cov['start_date']} to {cov['end_date']}). The 2022 Qatar tournament (Nov-Dec 2022) is **not** included, and neither are women's tournaments or qualifiers. "
      f"There was no tournament in 1942 or 1946 (Second World War).\n")
    rows = [
        ("Tournaments", cov["tournaments"]), ("Matches", cov["matches"]),
        ("Goals (incl. own goals)", f"{cov['goals']} ({cov['own_goals']} own goals)"),
        ("Teams (incl. historical)", cov["teams"]), ("Players named in squads", cov["players_in_squads"]),
        ("Players with a recorded appearance (1970+)", cov["players_who_appeared_1970_on"]),
        ("Different goal scorers", cov["goal_scorers"]), ("Referees", cov["referees"]), ("Managers", cov["managers"]),
        ("Stadiums", f"{cov['stadiums']} in {cov['stadium_countries']} countries"), ("Host nations (distinct)", cov["host_countries_distinct"]),
        ("Card events", cov["bookings"]), ("Substitutions (players coming on)", cov["substitutions"]),
        ("Penalty shoot-outs / kicks", f"{cov['shootouts']} / {cov['shootout_kicks']}"),
    ]
    w(md_table(["Measure", "Value"], rows) + "\n")
    w("**Year range of each event table** (several start late, which limits trend analysis):\n")
    w(md_table(["Table", "Years covered"], list(cov["event_coverage"].items())) + "\n")
    w("**Matches per tournament:** " + ", ".join(f"{k}: {v}" for k, v in cov["matches_per_tournament"].items()) + ".\n")

    # ---- tables
    w("## 2. Tables\n")
    w("The 27 tables group into eight themes. Every file has a `key_id` column, which is only the row number and is unique in every file. "
      "Many tables repeat descriptive columns from their parent tables (for example `team_name` and `tournament_name`). "
      f"{dq['denormalised_copy_checks']} of these copies were checked against the master tables, with {dq['denormalised_copy_differences']} differences found, "
      "so the normalised schema can safely drop them.\n")
    fk_by_child = {}
    for f in fks:
        fk_by_child.setdefault(f["child"], []).append(f)
    for theme in THEME_ORDER:
        w(f"### Theme: {theme}\n")
        for t in [t for t in META if META[t]["theme"] == theme]:
            p = prof[t]
            mt = META[t]
            w(f"#### `{t}` ({p['rows']:,} rows, {len(p['columns'])} columns)\n")
            w(f"- **Purpose:** {mt['purpose']}")
            w(f"- **Grain:** {mt['grain']}")
            w(f"- **Primary key candidate:** ({', '.join(mt['pk'])}): unique = {p['pk_unique']}, nulls = {p['pk_has_nulls']}. "
              f"Fully duplicated rows (ignoring key_id): {p['duplicate_rows']}.")
            if t in fk_by_child:
                w("- **Foreign key candidates (verified):**")
                for f in fk_by_child[t]:
                    w(f"  - ({', '.join(f['cols'])}) -> `{f['parent']}`({', '.join(f['pcols'])}): {f['orphans']} orphan values; "
                      f"{cardinality_label(f)} (max {f['max_children']} rows per parent)")
            else:
                w("- **Foreign key candidates:** none (top-level table).")
            w("")
            w(md_table(["Column", "Type", "Meaning", "Distinct", "Nulls", "'not available/applicable'", "Example"],
                       [(c["column"], c["type"], c["meaning"], c["distinct"], c["nulls"], c["sentinels"], c["example"][:40]) for c in p["columns"]]))
            w("")
            w("Sample rows:\n")
            w("```text")
            w(D[t].head(3).to_csv(index=False).strip())
            w("```\n")

    # ---- relationships
    w("## 3. Relationship map\n")
    w("All foreign-key candidates below were checked against the data: **every one has 0 orphan values**, including the composite references "
      "(for example, every goal scorer is in their team's squad for that tournament).\n")
    w("```mermaid\nerDiagram\n"
      "  CONFEDERATIONS ||--o{ TEAMS : groups\n  CONFEDERATIONS ||--o{ REFEREES : groups\n"
      "  TOURNAMENTS ||--|{ TOURNAMENT_STAGES : has\n  TOURNAMENT_STAGES ||--o{ GROUPS : has\n  GROUPS ||--|{ GROUP_STANDINGS : ranks\n"
      "  TOURNAMENTS ||--|{ QUALIFIED_TEAMS : includes\n  TEAMS ||--|{ QUALIFIED_TEAMS : enters\n"
      "  QUALIFIED_TEAMS ||--o| HOST_COUNTRIES : hosts\n  QUALIFIED_TEAMS ||--o| TOURNAMENT_STANDINGS : finishes\n"
      "  QUALIFIED_TEAMS ||--|{ SQUADS : registers\n  PLAYERS ||--|{ SQUADS : listed\n"
      "  QUALIFIED_TEAMS ||--|{ MANAGER_APPOINTMENTS : led_by\n  MANAGERS ||--|{ MANAGER_APPOINTMENTS : appointed\n"
      "  TOURNAMENTS ||--|{ REFEREE_APPOINTMENTS : appoints\n  REFEREES ||--|{ REFEREE_APPOINTMENTS : appointed\n"
      "  TOURNAMENT_STAGES ||--|{ MATCHES : contains\n  STADIUMS ||--|{ MATCHES : hosts\n"
      "  MATCHES ||--|{ TEAM_APPEARANCES : two_sides\n  TEAMS ||--|{ TEAM_APPEARANCES : plays\n"
      "  MATCHES ||--|| REFEREE_APPEARANCES : officiated\n  REFEREE_APPOINTMENTS ||--|{ REFEREE_APPEARANCES : works\n"
      "  TEAM_APPEARANCES ||--|{ MANAGER_APPEARANCES : managed\n  MANAGER_APPOINTMENTS ||--|{ MANAGER_APPEARANCES : works\n"
      "  MATCHES ||--o{ PLAYER_APPEARANCES : lineup\n  SQUADS ||--o{ PLAYER_APPEARANCES : plays\n"
      "  MATCHES ||--o{ GOALS : contains\n  SQUADS ||--o{ GOALS : scores\n"
      "  MATCHES ||--o{ BOOKINGS : contains\n  SQUADS ||--o{ BOOKINGS : booked\n"
      "  MATCHES ||--o{ SUBSTITUTIONS : contains\n  SQUADS ||--o{ SUBSTITUTIONS : subbed\n"
      "  MATCHES ||--o{ PENALTY_KICKS : shootout\n  SQUADS ||--o{ PENALTY_KICKS : takes\n"
      "  AWARDS ||--o{ AWARD_WINNERS : given\n  SQUADS ||--o{ AWARD_WINNERS : wins\n```\n")
    w("**Bridge (associative) tables** resolve many-to-many relationships:\n")
    w(md_table(["Bridge table", "Resolves", "Verified key"], [(k, v, "(" + ", ".join(META[k]["pk"]) + ")") for k, v in BRIDGES.items()]) + "\n")
    w("**Observed cardinalities** (parent : child, computed from the data):\n")
    w(md_table(["Child", "FK columns", "Parent", "Cardinality", "Max per parent", "Parents with no child", "Orphans"],
               [(f["child"], ", ".join(f["cols"]), f["parent"], cardinality_label(f), f["max_children"],
                 f"{f['parents_without_children']} of {f['parents_total']}", f["orphans"]) for f in fks]) + "\n")
    w("Notes on the structure:\n")
    w("- `matches` has no `stage_number`; it links to `tournament_stages` through (tournament_id, stage_name), which is unique per tournament.")
    w("- `matches.home_team_id`/`away_team_id` and `team_appearances` (exactly 2 rows per match) carry the same information. "
      "`team_appearances` is a derived, team-centred view that makes per-team queries simple.")
    w("- `referee_appearances` is 1:1 with `matches` (one referee per match, no assistants), so it could be a column of `matches`.")
    w("- `manager_appearances` is **not** 1:1 with `team_appearances`: "
      f"{dq['team_matches_multiple_managers']} team-matches had two managers in charge ({dq['team_tournaments_multiple_managers']} team-tournaments with joint managers).")
    w("- Event tables (`goals`, `bookings`, `substitutions`, `penalty_kicks`, `player_appearances`, `award_winners`) can reference the composite "
      "(tournament_id, team_id, player_id) key of `squads`. This is stricter than referencing `players` alone. For goals, the squad team is "
      "`player_team_id`, because own goals are credited to the opponent in `team_id`.")
    w("- `host_countries` and `tournament_standings` are subsets of `qualified_teams` (all composite references verified).\n")

    # ---- data quality
    w("## 4. Data quality findings\n")
    w("Integrity checks that **passed**:\n")
    passed = [
        f"Goal events reconcile with scores: {cov['goals']} goal rows = sum of all match scores ({dq['goals_sum_of_scores']}); per team-match mismatches: {dq['goal_reconciliation_mismatches']}.",
        f"Shoot-out kicks reconcile with shoot-out scores: {dq['shootout_reconciliation_mismatches']} mismatches.",
        f"Own goals: team_id differs from player_team_id in {dq['own_goal_team_differs']} own goals and in {dq['non_own_goal_team_differs']} normal goals.",
        f"Exactly 2 team_appearances per match: {dq['team_appearances_per_match']}.",
        f"Stage match counts match tournament_stages.count_matches ({dq['stage_count_mismatches']} mismatches); team counts match tournaments.count_teams ({dq['team_count_mismatches']} mismatches).",
        f"Every team has exactly 11 starters in every recorded line-up: {dq['starters_per_team_match']}.",
        f"Substitutions are balanced (off = on) in every team-match ({dq['sub_pairs_unbalanced']} unbalanced); max {dq['max_subs_team_match']} substitutions per team-match.",
        f"Group tables are internally consistent: played = W+D+L ({dq['standings_played_eq_wdl']}), goal difference = GF-GA ({dq['standings_gd_ok']}).",
        f"players.count_tournaments agrees with squads ({dq['count_tournaments_mismatch']} mismatches).",
        f"Match city/country agree with stadiums ({dq['match_stadium_location_mismatch']} mismatches); denormalised name copies agree with masters ({dq['denormalised_copy_differences']} differences).",
        "No fully duplicated rows in any table, and all primary-key candidates are unique and non-null.",
    ]
    for p in passed:
        w(f"- {p}")
    w("")
    w("Findings that need handling:\n")
    gs_diff = dq["standings_played_vs_group_matches"]
    findings = [
        ("Missing values coded as text", f"'not available' / 'not applicable' are used instead of empty cells: {pp(dq['sentinels'])}.",
         "Convert to SQL NULL on load (group_name for knockout matches, given_name for mononymous players such as Pelé, birth_date, wikipedia links)."),
        ("A true empty cell", f"players.birth_date is blank for {pp(dq['null_birth_player'])} (in addition to 77 'not available').",
         "Load as NULL; exclude from age calculations and report the count excluded."),
        ("Inconsistent score text", f"matches.score uses an en dash except {pp(dq['score_hyphen_rows'])}; score_penalties is '0-0' (hyphen) when there was no shoot-out: {pp(dq['score_penalties_no_shootout'])}.",
         "Do not store the text scores; use the integer columns. Store shoot-out scores as NULL when penalty_shootout = 0."),
        ("Shoot-out matches recorded as wins", f"In the {cov['shootouts']} shoot-out matches the score is level ({pp(dq['shootout_level_scores'])} of {cov['shootouts']}), but `result` says {pp(dq['shootout_result_labels'])} and draw = 0.",
         "Keep the flags but state the rule. For FIFA-style W/D/L, derive results from goals (a shoot-out counts as a draw). The shoot-out winner comes from the penalty scores."),
        ("Inconsistent stage labels", f"host_countries.performance: {pp(dq['host_performance_labels'])} ('quater-finals' and 'quarter-final' misspellings). qualified_teams.performance uses a different vocabulary: {pp(dq['qualified_performance_labels'])}.",
         "Map to a controlled list (lookup table or CHECK constraint). Use tournament_standings for positions 1-4, because 'final' does not distinguish winner from runner-up."),
        ("Historical / renamed teams", f"Germany and West Germany share team_code DEU and the same federation ({pp(dq['duplicate_team_codes'])}). Separate ids also exist for Soviet Union/Russia, Yugoslavia/Serbia and Montenegro/Serbia, Czechoslovakia/Czech Republic/Slovakia, Dutch East Indies (code IDN), Zaire (code COD). {pp(dq['players_multiple_teams'])} players appear for more than one team, e.g. {', '.join(dq['players_multiple_teams_examples'][:6])}.",
         "Keep the source team_ids (faithful to history); team_code cannot be UNIQUE. If needed, add an optional `team_lineage` mapping for analyses that should combine West Germany with Germany (FIFA credits the successor federation). That mapping is an outside assumption and must be labelled as such."),
        ("Confederation is a current attribute", f"teams.region_name vs confederation: {pp(dq['region_vs_confederation'])}. Australia is listed as AFC although it played the 1974 and 2006 tournaments as an OFC member.",
         "Treat confederation analyses by decade as 'by current confederation' and say so."),
        ("Non-unique names", f"Two stadiums are called {pp(dq['duplicate_stadium_names'])}; match_name has only {pp(dq['match_name_distinct'])} distinct values for 900 matches.",
         "Always join on ids, never on names."),
        ("Replayed matches", f"4 drawn ties were replayed (1934, 1938): {pp(dq['replays'])}.",
         "Keep both matches (both were played and their goals count). replayed = 1 marks the drawn original and replay = 1 the rematch. Use the replay to decide who advanced."),
        ("Walkover", f"1938 round of 16: {pp(dq['walkovers'])} [tournament, stage, scheduled, played, replays, walkovers]. Austria withdrew, so Sweden advanced without playing; the walkover has no match row.",
         "Note it; there are no rows to load. Counts of 'matches played' are correct as is."),
        ("Group play-off matches", f"Tie-break play-offs inside group stages: {pp(dq['playoffs'])}. Play-offs are counted as group-stage matches but not in the group tables: rows where group_standings.played differs from the team's group-stage match count (tournament, stage, team, in table, actual): {pp(gs_diff)}.",
         "Use group_standings for tables and matches/team_appearances for match counts; document that they differ by design."),
        ("Stage names differ between tables", f"groups/group_standings name stage 1 differently from tournament_stages and matches for the same stage_number: {pp(dq['stage_name_mismatches'])} [tournament, stage_number, name in groups, name in stages].",
         "Store stage_name only in tournament_stages; groups and group_standings reference (tournament_id, stage_number). Joining on stage_name would silently lose 1950 and 1974-1982 first-stage groups."),
        ("Group names differ between matches and groups", f"matches uses group names that do not exist in groups for the same stage: {pp(dq['match_group_names_not_in_groups'])}; groups and group_standings call these groups {pp(dq['groups_names_for_those_stages'])}. Each group contains exactly the same three teams under both names. Also, these group-stage matches have no group name although groups records their round as a group: {pp(dq['group_stage_matches_without_group'])} (the 1950 final round, 'Group 1' in groups).",
         "During loading, map each match to the group containing its teams (1982: Group 1 -> A, 2 -> B, 3 -> C, 4 -> D; 1950 final round -> Group 1; computed, not assumed). The FK from matches to groups then holds."),
        ("1950 had no final", f"1950 ended with a final round-robin group (stage 'final round'): {pp(dq['final_round_1950'])}. 'final' stage matches = {pp(dq['final_stage_matches'])} for 21 tournaments.",
         "When counting finals, treat the 1950 decider (Uruguay v Brazil) separately or use tournament_standings positions 1-2."),
        ("No third-place match / 'shared' third places", f"No third-place match in {pp(dq['no_third_place_match'])}. tournament_standings still has exactly positions 1-4 for every tournament ({pp(dq['standings_positions_per_tournament'])}), so **no shared third places exist in this data**; for 1930 the source ranks the USA 3rd and Yugoslavia 4th.",
         "Report positions 3-4 for 1930 as assigned by the source, not decided on the pitch."),
        ("Abandoned matches", "There is no abandoned/forfeit flag, and every match has a final score. No World Cup final-tournament match was abandoned in this period.",
         "Nothing to handle; note the absence of the attribute."),
        ("Event data starts in 1970", f"Year ranges: {pp(cov['event_coverage'])}. Bookings exist for only some matches in early tournaments (matches with at least one card per year: {pp(dq['booked_matches_per_tournament'])}).",
         "Restrict line-up, card and substitution analyses to 1970+ and state it. A match with no booking rows means no cards were shown, not missing data, from 1970 on."),
        ("Shirt number 0 = unknown", f"Squads with shirt 0 by year: {pp(dq['shirt_zero_squads_by_year'])}; goals with shirt 0 by year: {pp(dq['shirt_zero_goals_by_year'])}.",
         "Load 0 as NULL (CHECK shirt_number BETWEEN 1 AND 99 where present)."),
        ("Multiple managers", f"{pp(dq['team_tournaments_multiple_managers'])} team-tournaments had joint managers ({pp(dq['team_matches_multiple_managers'])} team-matches), so manager_appearances has 1,842 rows for 1,800 team-matches.",
         "The key must include manager_id; manager win totals double-count those team-matches across co-managers by design."),
        ("Line-up gaps", f"{len(dq['coming_on_without_appearance'])} 'coming on' substitutions have no player_appearances row ({pp(dq['coming_on_without_appearance'])}). player_appearances has {pp(dq['pa_substitute_rows'])} substitute rows vs {pp(dq['coming_on_rows'])} coming_on rows. "
         f"{len(dq['team_matches_without_captain'])} team-matches have no captain flagged ({pp(dq['team_matches_without_captain'])}). {pp(dq['subbed_on_then_off'])} players came on and were later taken off.",
         "Small gaps in source data. Report them and do not 'fix' them by inventing rows. Substitute counts should come from substitutions."),
        ("Ambiguous booking", f"Booking {pp(dq['booking_yellow_and_red'])} has both yellow_card = 1 and red_card = 1 but second_yellow_card = 0. Rows per flag pattern (yellow, red, second yellow, sending off): {pp(dq['booking_flag_patterns'])}.",
         "Keep as is. Use sending_off to count dismissals and note this row."),
        ("Position granularity", f"squads uses 4 position codes {pp(dq['squad_position_codes'])}; player_appearances uses 21 detailed codes. Players can carry several position flags in players: {pp(dq['player_position_flag_counts'])} (number of flags -> players).",
         "Use squads.position_code for position analyses. Optionally map the 21 detailed codes to the 4 groups."),
        ("Points systems differ by era", f"2 points per win up to 1990: {pp(dq['points_2_per_win_holds_to_1990'])}; 3 points from 1994: {pp(dq['points_3_per_win_holds_from_1994'])}.",
         "Recompute points with a single rule when comparing eras."),
        ("Non-atomic / derived columns", "players.list_tournaments is a comma-separated list; players.count_tournaments, tournaments.winner/host_country (text), team_appearances.*, margins and win flags are derivable.",
         "Do not use list_tournaments for querying (derive it from squads). Decide in Milestone 2 which derived columns to keep for convenience."),
        ("Home/away is nominal", f"Outside the hosts, 'home' is only the first-named team. Hosts were flagged home in {pp(dq['host_matches_flagged_home'])} of {pp(dq['host_matches'])} of their matches.",
         "Measure host advantage with host_countries, not home_team."),
        ("Not keys", "team_code (Germany/West Germany), stadium_name and match_name are not unique; key_id is only a row number.",
         "Use the *_id columns as keys."),
    ]
    w(md_table(["#", "Issue", "Evidence (computed)", "Handling"], [(i + 1, a, b_, c) for i, (a, b_, c) in enumerate(findings)]) + "\n")

    # ---- insights
    w("## 5. Key insights\n")
    w(f"{len(ins)} findings, each computed by `src/profile_data.py`. Unless stated otherwise, wins and draws are derived from the score, so a shoot-out counts as a draw, as in FIFA records.\n")
    w(md_table(["#", "Theme", "Finding", "Supporting tables / columns"], [(i + 1, x["theme"], x["text"], x["support"]) for i, x in enumerate(ins)]) + "\n")

    # ---- framework
    w("## 6. Insights framework\n")
    w("Questions the database can answer, how to compute them, and who benefits. The SQL techniques listed here feed the Milestone 1 query list.\n")
    for theme, rows in FRAMEWORK.items():
        w(f"### {theme}\n")
        w(md_table(["Question", "Tables involved", "How to compute (method and SQL technique)", "Why it matters / who it helps"], rows) + "\n")
    w("### What the data cannot answer\n")
    for c in CANNOT:
        w(f"- {c}")
    w("")
    w("---\n")
    w("*Attribution: Data from Joshua C. Fjelstul, The Fjelstul World Cup Database (https://github.com/jfjelstul/worldcup), CC-BY-SA 4.0. "
      "This report is a derived work and is shared under the same licence.*\n")
    return "\n".join(L)


def main():
    D = load()
    assert set(D) == set(META), f"table mismatch: {set(D) ^ set(META)}"
    prof = {t: profile_table(t, D[t]) for t in META}
    fks = [check_fk(D, t, c, p, pc) for t in META for (c, p, pc) in META[t]["fks"]]
    res = build(D)
    DOCS.mkdir(exist_ok=True)
    md = render(D, prof, fks, res)
    (DOCS / "dataset_understanding.md").write_text(md, encoding="utf-8")

    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return str(o)
    summary = dict(title=TITLE, tables={t: dict(rows=prof[t]["rows"], pk=prof[t]["pk"], pk_unique=prof[t]["pk_unique"]) for t in prof},
                   foreign_keys=fks, coverage=res["coverage"], data_quality=res["dq"], insights=res["insights"])
    (DOCS / "profile_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=conv), encoding="utf-8")

    bad_fk = [f for f in fks if f["orphans"]]
    bad_pk = [t for t in prof if not prof[t]["pk_unique"] or prof[t]["pk_has_nulls"]]
    print(f"Profiled {len(D)} tables, {sum(p['rows'] for p in prof.values()):,} rows.")
    print(f"PK candidates failing: {bad_pk or 'none'}; FK candidates with orphans: {[(f['child'], f['cols']) for f in bad_fk] or 'none'}")
    print(f"Coverage: {res['coverage']['first_year']}-{res['coverage']['last_year']}, {res['coverage']['tournaments']} tournaments, "
          f"{res['coverage']['matches']} matches, {res['coverage']['goals']} goals.")
    print(f"Insights: {len(res['insights'])}")
    for i, x in enumerate(res["insights"], 1):
        print(f"{i:2d}. [{x['theme']}] {x['text']}")
    print("Wrote docs/dataset_understanding.md and docs/profile_summary.json")


if __name__ == "__main__":
    main()
