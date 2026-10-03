"""
Pitch to Postgres: Designing and Querying a Relational Database for FIFA World Cup Data
Cleaning and shaping of the 27 source CSV files into the normalised schema of sql/ddl.sql.

Used by notebooks/03_load_data.ipynb. Every transformation is listed in CLEANING_LOG.
Nothing here changes a data value; it only:
  * converts the text markers 'not available' / 'not applicable' (and shirt number 0) to NULL,
  * converts 0/1 flags to booleans, and text dates/times to date/time values,
  * keeps only the columns of the normalised table (copied, same-row-derived and row-number
    columns are dropped; verify_dropped_columns() proves each dropped column is redundant),
  * looks up stage_number for matches (matches only has stage_name),
  * sets shoot-out scores to NULL when there was no shoot-out (the source uses 0 / '0-0').
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SENTINELS = ["not available", "not applicable"]

# Parents before children (foreign-key dependency order). positions is seeded by ddl.sql.
LOAD_ORDER = [
    "confederations", "awards", "stadiums", "teams", "players", "managers", "referees",
    "tournaments", "tournament_stages", "groups", "qualified_teams", "host_countries",
    "tournament_standings", "group_standings", "squads", "manager_appointments", "referee_appointments",
    "matches", "team_appearances", "referee_appearances", "manager_appearances", "player_appearances",
    "goals", "bookings", "substitutions", "penalty_kicks", "award_winners",
]

# Columns kept in each normalised table (same names as the CSV, so the mapping is transparent).
COLUMNS = {
    "confederations": ["confederation_id", "confederation_name", "confederation_code", "confederation_wikipedia_link"],
    "awards": ["award_id", "award_name", "award_description", "year_introduced"],
    "stadiums": ["stadium_id", "stadium_name", "city_name", "country_name", "stadium_capacity",
                 "stadium_wikipedia_link", "city_wikipedia_link"],
    "teams": ["team_id", "team_name", "team_code", "federation_name", "region_name", "confederation_id",
              "team_wikipedia_link", "federation_wikipedia_link"],
    "players": ["player_id", "family_name", "given_name", "birth_date", "player_wikipedia_link"],
    "managers": ["manager_id", "family_name", "given_name", "country_name", "manager_wikipedia_link"],
    "referees": ["referee_id", "family_name", "given_name", "country_name", "confederation_id", "referee_wikipedia_link"],
    "tournaments": ["tournament_id", "tournament_name", "year", "start_date", "end_date"],
    "tournament_stages": ["tournament_id", "stage_number", "stage_name", "start_date", "end_date",
                          "count_teams", "count_scheduled", "count_playoffs", "count_walkovers"],
    "groups": ["tournament_id", "stage_number", "group_name"],
    "qualified_teams": ["tournament_id", "team_id", "performance"],
    "host_countries": ["tournament_id", "team_id"],
    "tournament_standings": ["tournament_id", "position", "team_id"],
    "group_standings": ["tournament_id", "stage_number", "group_name", "position", "team_id",
                        "wins", "draws", "losses", "goals_for", "goals_against", "advanced"],
    "squads": ["tournament_id", "team_id", "player_id", "shirt_number", "position_code"],
    "manager_appointments": ["tournament_id", "team_id", "manager_id"],
    "referee_appointments": ["tournament_id", "referee_id"],
    "matches": ["match_id", "tournament_id", "stage_number", "group_name", "replayed", "replay", "match_date",
                "match_time", "stadium_id", "home_team_id", "away_team_id", "home_team_score", "away_team_score",
                "extra_time", "penalty_shootout", "home_team_score_penalties", "away_team_score_penalties"],
    "team_appearances": ["match_id", "team_id", "tournament_id", "opponent_id", "home_team", "goals_for",
                         "goals_against", "penalties_for", "penalties_against"],
    "referee_appearances": ["match_id", "tournament_id", "referee_id"],
    "manager_appearances": ["match_id", "team_id", "manager_id", "tournament_id"],
    "player_appearances": ["match_id", "player_id", "tournament_id", "team_id", "position_code", "starter", "captain"],
    "goals": ["goal_id", "match_id", "tournament_id", "team_id", "player_id", "player_team_id",
              "minute_regulation", "minute_stoppage", "own_goal", "penalty"],
    "bookings": ["booking_id", "match_id", "tournament_id", "team_id", "player_id", "minute_regulation",
                 "minute_stoppage", "yellow_card", "red_card", "second_yellow_card"],
    "substitutions": ["substitution_id", "match_id", "tournament_id", "team_id", "player_id",
                      "minute_regulation", "minute_stoppage", "coming_on"],
    "penalty_kicks": ["penalty_kick_id", "match_id", "tournament_id", "team_id", "player_id", "converted"],
    "award_winners": ["tournament_id", "award_id", "player_id", "team_id"],
}

BOOL_COLUMNS = {"replayed", "replay", "extra_time", "penalty_shootout", "home_team", "advanced", "starter",
                "captain", "own_goal", "penalty", "yellow_card", "red_card", "second_yellow_card", "coming_on",
                "converted"}
DATE_COLUMNS = {"birth_date", "start_date", "end_date", "match_date"}
NULLABLE_INT_COLUMNS = {"shirt_number", "home_team_score_penalties", "away_team_score_penalties",
                        "penalties_for", "penalties_against"}

CLEANING_LOG = [
    ("All tables", "Text 'not available' / 'not applicable' -> NULL",
     "Missing values were coded as text (group_name outside groups, given_name of one-name players, birth_date, wikipedia links)."),
    ("players.birth_date", "One empty cell and 77 'not available' -> NULL; other values -> DATE", "Unknown birth dates."),
    ("squads.shirt_number", "0 -> NULL", "0 means unknown (1930-1950 squads)."),
    ("All 0/1 flag columns", "-> BOOLEAN", "Typed flags; enables CHECK constraints such as own_goal = (team_id <> player_team_id)."),
    ("Date / time columns", "'YYYY-MM-DD' -> DATE, 'HH:MM' -> TIME", "Real types allow date arithmetic (ages, durations)."),
    ("matches.home/away_team_score_penalties, team_appearances.penalties_for/against", "0 -> NULL when there was no shoot-out",
     "The source stores 0 (and '0-0') for 870 matches without a shoot-out, which looks like a real 0-0 shoot-out."),
    ("matches.stage_number", "Looked up from tournament_stages by (tournament_id, stage_name)",
     "Needed for the FK to groups; group names repeat across stages, and groups use different stage names."),
    ("matches.group_name (1982 second group stage)", "'Group 1'-'Group 4' -> 'Group A'-'Group D' (12 matches)",
     "matches and groups/group_standings name these four groups differently. Each group is matched by its identical set of "
     "three teams (computed by group_name_fixes(), which accepts only unique matches)."),
    ("matches.group_name (1950 final round)", "'not applicable' -> 'Group 1' (6 matches)",
     "groups/group_standings record the 1950 final round as one group, 'Group 1', of the four teams that played these "
     "6 matches, but matches has no group name. Matched by the two teams of each match."),
    ("All tables", "Dropped key_id and columns copied from parent tables",
     "key_id is a row number; copies (names, codes, dates, stadium location, confederation, ...) are stored once in their own table."),
    ("Several tables", "Dropped columns derived from other columns of the same row",
     "e.g. score text, margins, result/win flags, minute_label, match_period, going_off, substitute, sending_off, played, goal_difference, points. "
     "verify_dropped_columns() proves each can be recomputed exactly."),
    ("players, tournaments, qualified_teams, groups, tournament_stages, award_winners", "Dropped summary columns derivable from other tables",
     "count_tournaments, list_tournaments (non-atomic), position flags, host/winner text, format flags, count_teams/count_matches/count_replays, unbalanced_groups, shared."),
    ("goals, bookings, substitutions, penalty_kicks, player_appearances, squads", "Dropped shirt_number / position_name copies",
     "Shirt numbers are kept in squads (more complete: goals has 0 for 444 goals whose squad number is known); position names live in positions."),
]


def read_raw(name: str) -> pd.DataFrame:
    """pd.read_csv as required by the course: keep text markers so they can be handled explicitly."""
    return pd.read_csv(DATA / f"{name}.csv", keep_default_na=False, na_values=[""], encoding="utf-8")


def read_all_raw() -> dict[str, pd.DataFrame]:
    return {n: read_raw(n) for n in LOAD_ORDER}


def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%Y-%m-%d", errors="raise").dt.date.astype(object).where(s.notna(), None)


def group_name_fixes(raw: dict[str, pd.DataFrame]) -> dict[str, tuple[str | None, str]]:
    """
    Align matches.group_name with the groups table. Returns {match_id: (old group name, new group name)}.

    Two source inconsistencies are handled, both by matching TEAMS, never by assumption:
      a) a match's group name does not exist in groups for that stage (1982 second stage:
         matches say 'Group 1'-'Group 4', groups/group_standings say 'Group A'-'Group D');
         the group whose team set equals the teams of all matches with that name is used;
      b) a match in a stage that has groups has no group name (1950 final round: 'not applicable',
         while groups/group_standings have 'Group 1'); the group containing both teams is used.
    Every mapping must be unique, otherwise an error is raised.
    """
    m, ts, grp, gs = raw["matches"], raw["tournament_stages"], raw["groups"], raw["group_standings"]
    mm = m.merge(ts[["tournament_id", "stage_name", "stage_number"]], on=["tournament_id", "stage_name"])
    has_name = mm.group_name.notna() & ~mm.group_name.isin(SENTINELS)
    known = set(map(tuple, grp[["tournament_id", "stage_number", "group_name"]].values))
    stages_with_groups = set(map(tuple, grp[["tournament_id", "stage_number"]].values))
    team_sets = {(t, s, g): frozenset(x.team_id) for (t, s, g), x in gs.groupby(["tournament_id", "stage_number", "group_name"])}
    fixes = {}
    # a) unknown group names
    for (t, s, gname), d in mm[has_name].groupby(["tournament_id", "stage_number", "group_name"]):
        if (t, s, gname) in known:
            continue
        teams = frozenset(d.home_team_id) | frozenset(d.away_team_id)
        cands = [g for (t2, s2, g), ts_ in team_sets.items() if (t2, s2) == (t, s) and ts_ == teams]
        assert len(cands) == 1, f"no unique group for {t} stage {s} {gname}"
        for mid in d.match_id:
            fixes[mid] = (gname, cands[0])
    # b) missing group names in stages that have groups
    for r in mm[~has_name].itertuples():
        if (r.tournament_id, r.stage_number) not in stages_with_groups:
            continue
        cands = [g for (t2, s2, g), ts_ in team_sets.items()
                 if (t2, s2) == (r.tournament_id, r.stage_number) and {r.home_team_id, r.away_team_id} <= ts_]
        assert len(cands) == 1, f"no unique group for {r.match_id}"
        fixes[r.match_id] = (None, cands[0])
    return fixes


# ---------------------------------------------------------------------------
# Cleaning steps. Each step takes (table name, DataFrame, all raw tables) and returns
# (cleaned DataFrame, number of values/rows/columns it changed), so the notebook can report every fix.
# ---------------------------------------------------------------------------

def step_sentinels(name, df, raw):
    """Text markers 'not available' / 'not applicable' -> NULL (cells changed)."""
    n = 0
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            hit = df[c].isin(SENTINELS)
            n += int(hit.sum())
            df[c] = df[c].mask(hit)
    return df, n


def step_shirt_zero(name, df, raw):
    """squads.shirt_number 0 (unknown) -> NULL (cells changed)."""
    if name != "squads":
        return df, 0
    hit = df["shirt_number"] == 0
    df["shirt_number"] = df["shirt_number"].mask(hit)
    return df, int(hit.sum())


def step_stage_number(name, df, raw):
    """matches: look up stage_number from tournament_stages by (tournament_id, stage_name) (rows mapped)."""
    if name != "matches":
        return df, 0
    stages = raw["tournament_stages"][["tournament_id", "stage_name", "stage_number"]]
    df = df.merge(stages, on=["tournament_id", "stage_name"], how="left", validate="many_to_one")
    assert df["stage_number"].notna().all(), "every match must map to a stage"
    return df, len(df)


def step_group_names(name, df, raw):
    """matches: align group names with groups (1982 second stage, 1950 final round) (rows changed)."""
    if name != "matches":
        return df, 0
    fixes = group_name_fixes(raw)
    df["group_name"] = [fixes[mid][1] if mid in fixes else g for mid, g in zip(df.match_id, df.group_name)]
    return df, len(fixes)


def step_shootout_nulls(name, df, raw):
    """Shoot-out scores of 0 -> NULL when there was no shoot-out (cells changed)."""
    cols = {"matches": ["home_team_score_penalties", "away_team_score_penalties"],
            "team_appearances": ["penalties_for", "penalties_against"]}.get(name)
    if not cols:
        return df, 0
    no_so = df["penalty_shootout"] == 0
    for c in cols:
        df[c] = df[c].mask(no_so)
    return df, int(no_so.sum()) * len(cols)


def step_select_columns(name, df, raw):
    """Keep only the columns of the normalised table (columns dropped)."""
    n = df.shape[1] - len(COLUMNS[name])
    return df[COLUMNS[name]].copy(), n


def step_types(name, df, raw):
    """0/1 -> BOOLEAN, text -> DATE / TIME, nullable integers; NULL as None (columns converted)."""
    n = 0
    for c in df.columns:
        if c in BOOL_COLUMNS:
            assert set(df[c].unique()) <= {0, 1}, f"{name}.{c} is not 0/1"
            df[c] = df[c].astype(bool)
            n += 1
        elif c in DATE_COLUMNS:
            df[c] = _to_date(df[c])
            n += 1
        elif c == "match_time":
            df[c] = df[c].map(lambda t: dt.datetime.strptime(t, "%H:%M").time())
            n += 1
        elif c in NULLABLE_INT_COLUMNS or c == "stage_number":
            df[c] = df[c].astype("Int64")
            n += 1
    for c in df.columns:   # text columns: plain Python objects with None for NULL
        if pd.api.types.is_string_dtype(df[c]) and c not in DATE_COLUMNS:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df, n


CLEANING_STEPS = [
    ("1. Text markers -> NULL", step_sentinels),
    ("2. Shirt number 0 -> NULL", step_shirt_zero),
    ("3. Look up matches.stage_number", step_stage_number),
    ("4. Align group names with groups", step_group_names),
    ("5. No shoot-out -> NULL shoot-out scores", step_shootout_nulls),
    ("6. Keep normalised columns only", step_select_columns),
    ("7. Convert types (bool/date/time/int)", step_types),
]


def clean_table(name: str, raw: dict[str, pd.DataFrame], log: list | None = None) -> pd.DataFrame:
    """Apply all cleaning steps to one table. If log is a list, append (table, step, count) for each change."""
    df = raw[name].copy()
    for label, fn in CLEANING_STEPS:
        df, n = fn(name, df, raw)
        if log is not None and n:
            log.append((name, label, n))
    return df


def clean_all(raw: dict[str, pd.DataFrame] | None = None, log: list | None = None) -> dict[str, pd.DataFrame]:
    raw = raw or read_all_raw()
    return {n: clean_table(n, raw, log) for n in LOAD_ORDER}


def verify_dropped_columns(raw: dict[str, pd.DataFrame] | None = None) -> list[tuple[str, bool]]:
    """Prove that each dropped derived column can be recomputed from the columns we keep."""
    r = raw or read_all_raw()
    m, ta, g, b, s, pa = r["matches"], r["team_appearances"], r["goals"], r["bookings"], r["substitutions"], r["player_appearances"]
    sq, gs, aw, ts, qt, grp = r["squads"], r["group_standings"], r["award_winners"], r["tournament_stages"], r["qualified_teams"], r["groups"]
    t, p = r["tournaments"], r["players"]
    checks = []

    def ok(label, cond):
        checks.append((label, bool(cond)))

    ok("matches margins = score difference", ((m.home_team_score_margin == m.home_team_score - m.away_team_score)
                                              & (m.away_team_score_margin == -m.home_team_score_margin)).all())
    res = pd.Series("draw", index=m.index)
    hw = (m.home_team_score > m.away_team_score) | ((m.home_team_score == m.away_team_score) & (m.home_team_score_penalties > m.away_team_score_penalties))
    aw_ = (m.home_team_score < m.away_team_score) | ((m.home_team_score == m.away_team_score) & (m.home_team_score_penalties < m.away_team_score_penalties))
    res[hw], res[aw_] = "home team win", "away team win"
    ok("matches.result / win flags from scores and shoot-out scores", (res == m.result).all()
       and (m.home_team_win == hw.astype(int)).all() and (m.away_team_win == aw_.astype(int)).all())
    ok("matches.score text = scores", (m.score.str.replace("-", "–") == m.home_team_score.astype(str) + "–" + m.away_team_score.astype(str)).all())
    st = ts.set_index(["tournament_id", "stage_name"])
    ok("matches.group_stage/knockout_stage depend only on the stage",
       (m.groupby(["tournament_id", "stage_name"])[["group_stage", "knockout_stage"]].nunique() == 1).all().all())
    ok("tournament_stages flags depend only on stage_name", (ts.groupby("stage_name")[["group_stage", "knockout_stage"]].nunique() == 1).all().all())
    ok("team_appearances = matches seen from each side",
       len(ta) == 2 * len(m) and (ta.goal_differential == ta.goals_for - ta.goals_against).all()
       and (ta.away_team == 1 - ta.home_team).all())
    for name, df in [("goals", g), ("bookings", b), ("substitutions", s)]:
        lab = df.minute_regulation.astype(str) + "'" + df.minute_stoppage.map(lambda x: f"+{x}'" if x else "")
        per = pd.cut(df.minute_regulation, [0, 45, 90, 105, 120], labels=["first half", "second half",
                     "extra time, first half", "extra time, second half"]).astype(str)
        per = per + df.minute_stoppage.map(lambda x: ", stoppage time" if x else "")
        ok(f"{name}.minute_label and match_period from minutes", (lab == df.minute_label).all() and (per == df.match_period).all())
    ok("substitutions.going_off = NOT coming_on", (s.going_off == 1 - s.coming_on).all())
    ok("player_appearances.substitute = NOT starter", (pa.substitute == 1 - pa.starter).all())
    ok("bookings.sending_off = red_card OR second_yellow_card", (b.sending_off == (b.red_card | b.second_yellow_card)).all())
    ok("group_standings played/goal_difference = W+D+L / GF-GA",
       (gs.played == gs.wins + gs.draws + gs.losses).all() and (gs.goal_difference == gs.goals_for - gs.goals_against).all())
    yr = gs.tournament_id.str[3:].astype(int)
    ok("group_standings.points from wins/draws (2 per win to 1990, 3 from 1994)",
       (gs.points == gs.wins * yr.map(lambda y: 2 if y <= 1990 else 3) + gs.draws).all())
    for tname in ["goals", "bookings", "substitutions", "penalty_kicks", "player_appearances"]:
        df = r[tname]
        tc = "player_team_id" if tname == "goals" else "team_id"
        z = df.merge(sq[["tournament_id", "team_id", "player_id", "shirt_number"]], left_on=["tournament_id", tc, "player_id"],
                     right_on=["tournament_id", "team_id", "player_id"], suffixes=("", "_sq"))
        ok(f"{tname}.shirt_number agrees with squads (0 = unknown)",
           len(z) == len(df) and ((z.shirt_number == z.shirt_number_sq) | (z.shirt_number == 0)).all())
    ok("award_winners.shared = more than one winner", ((aw.groupby(["tournament_id", "award_id"]).player_id.transform("size") > 1).astype(int) == aw.shared).all())
    flags = sq.assign(v=1).pivot_table(index="player_id", columns="position_code", values="v", aggfunc="max", fill_value=0)
    x = p.set_index("player_id").join(flags)
    ok("players position flags = positions in squads", ((x.goal_keeper == x.GK) & (x.defender == x.DF) & (x.midfielder == x.MF) & (x.forward == x.FW)).all())
    ok("players.count_tournaments = squads per player", (sq.groupby("player_id").tournament_id.nunique().reindex(p.player_id).values == p.count_tournaments.values).all())
    ok("qualified_teams.count_matches = matches played", (ta.groupby(["tournament_id", "team_id"]).size().reindex(pd.MultiIndex.from_frame(qt[["tournament_id", "team_id"]])).values == qt.count_matches.values).all())
    ok("groups.count_teams = teams in group_standings", (gs.groupby(["tournament_id", "stage_number", "group_name"]).size().reindex(pd.MultiIndex.from_frame(grp[["tournament_id", "stage_number", "group_name"]])).values == grp.count_teams.values).all())
    ok("tournaments.count_teams = qualified teams", (qt.groupby("tournament_id").size().reindex(t.tournament_id).values == t.count_teams.values).all())
    cm = m.groupby(["tournament_id", "stage_name"]).agg(n=("match_id", "size"), rp=("replay", "sum"))
    z = ts.join(cm, on=["tournament_id", "stage_name"])
    ok("tournament_stages.count_matches / count_replays from matches", (z.n == z.count_matches).all() and (z.rp == z.count_replays).all())
    ub = grp.groupby(["tournament_id", "stage_number"]).count_teams.nunique().gt(1).astype(int)
    z = ts.join(ub.rename("u"), on=["tournament_id", "stage_number"]).fillna({"u": 0})
    ok("tournament_stages.unbalanced_groups from group sizes", (z.u == z.unbalanced_groups).all())
    has = lambda n: t.tournament_id.isin(ts[ts.stage_name == n].tournament_id).astype(int)
    ok("tournaments format flags from tournament_stages", all((has(n) == t[c]).all() for c, n in [
        ("group_stage", "group stage"), ("second_group_stage", "second group stage"), ("final_round", "final round"),
        ("round_of_16", "round of 16"), ("quarter_finals", "quarter-finals"), ("semi_finals", "semi-finals"),
        ("third_place_match", "third-place match"), ("final", "final")]))
    hc, ts4 = r["host_countries"], r["tournament_standings"]
    champ = ts4[ts4.position == 1].set_index("tournament_id").team_name
    ok("tournaments.winner / host_won from standings and hosts",
       (t.set_index("tournament_id").winner == champ).all()
       and (t.set_index("tournament_id").host_won == hc.merge(ts4[ts4.position == 1], on=["tournament_id", "team_id"]).groupby("tournament_id").size().reindex(t.tournament_id).fillna(0).astype(int).values).all())
    for tname, idc, cols in [("referee_appointments", "referee_id", ["country_name", "confederation_id"]),
                             ("referee_appearances", "referee_id", ["country_name", "confederation_id"]),
                             ("manager_appointments", "manager_id", ["country_name"]),
                             ("manager_appearances", "manager_id", ["country_name"])]:
        master = r["referees" if "referee" in tname else "managers"]
        z = r[tname].merge(master[[idc] + cols], on=idc, suffixes=("", "_m"))
        ok(f"{tname} person attributes = master table", all((z[c] == z[c + "_m"]).all() for c in cols))
    return checks
