from flask import Flask, jsonify
import requests
import json
import time
from datetime import datetime
import nfl_data_py as nfl
import pandas as pd

app = Flask(__name__)

def timed_operation(description, func):
    print(f"Starting {description}...")
    start_time = time.time()
    try:
        result = func()
        duration = time.time() - start_time
        print(f"{description} completed in {duration:.2f} seconds")
        return result
    except Exception as e:
        duration = time.time() - start_time
        print(f"{description} failed after {duration:.2f} seconds: {str(e)}")
        raise

class TeamAnalysisService:
    def __init__(self, odds_api_key="d8ba5d45eca27e710d7ef2680d8cb452"):
        self.odds_api_key = odds_api_key

        self.team_mapping = {
            "Arizona Cardinals": "ARI","Atlanta Falcons": "ATL","Baltimore Ravens": "BAL","Buffalo Bills": "BUF",
            "Carolina Panthers": "CAR","Chicago Bears": "CHI","Cincinnati Bengals": "CIN","Cleveland Browns": "CLE",
            "Dallas Cowboys": "DAL","Denver Broncos": "DEN","Detroit Lions": "DET","Green Bay Packers": "GB",
            "Houston Texans": "HOU","Indianapolis Colts": "IND","Jacksonville Jaguars": "JAX","Kansas City Chiefs": "KC",
            "Los Angeles Rams": "LAR","Miami Dolphins": "MIA","Minnesota Vikings": "MIN","New England Patriots": "NE",
            "New Orleans Saints": "NO","New York Giants": "NYG","New York Jets": "NYJ","Las Vegas Raiders": "LV",
            "Philadelphia Eagles": "PHI","Pittsburgh Steelers": "PIT","Los Angeles Chargers": "LAC",
            "San Francisco 49ers": "SF","Seattle Seahawks": "SEA","Tampa Bay Buccaneers": "TB",
            "Tennessee Titans": "TEN","Washington Commanders": "WAS"
        }

        self.book_priority = ['fanduel', 'draftkings', 'betmgm', 'caesars', 'betrivers']
        self.td_calculator = None

    def _ensure_calculator_initialized(self):
        if self.td_calculator is None:
            self.td_calculator = NFLTDBoostCalculator(service_instance=self)

    def get_week_parameters(self, week=None):
        return 0.25  # 25% weight

    def get_current_week(self):
        try:
            df_2025 = nfl.import_pbp_data([2025])
            if not df_2025.empty:
                max_week = df_2025['week'].max()
                return int(max_week) + 1
            return 3
        except Exception as e:
            print(f"Error getting current week: {str(e)}")
            return 3

    def get_vegas_team_totals(self):
        self._ensure_calculator_initialized()
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?regions=us&markets=totals,spreads&oddsFormat=american&apiKey={self.odds_api_key}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            games_data = response.json()
        except Exception as e:
            print(f"Error fetching odds data: {e}")
            return {}

        current_week_matchups = self.td_calculator.get_week_matchups()
        if not current_week_matchups:
            return {}

        expected_games = {f"{m['away_team']}@{m['home_team']}" for m in current_week_matchups}
        vegas_totals = {}

        for game in games_data:
            home_team = game['home_team']; away_team = game['away_team']
            home_abbr = self.team_mapping.get(home_team); away_abbr = self.team_mapping.get(away_team)
            if not home_abbr or not away_abbr:
                continue
            game_key = f"{away_abbr}@{home_abbr}"
            if game_key not in expected_games:
                continue

            selected_bookmaker = None
            for book_key in self.book_priority:
                for bookmaker in game.get('bookmakers', []):
                    if bookmaker.get('key') == book_key:
                        selected_bookmaker = bookmaker; break
                if selected_bookmaker: break
            if not selected_bookmaker:
                continue

            totals_market = None; spreads_market = None
            for market in selected_bookmaker.get('markets', []):
                if market.get('key') == 'totals': totals_market = market
                elif market.get('key') == 'spreads': spreads_market = market
            if not totals_market or not spreads_market:
                continue

            game_total = None
            for outcome in totals_market.get('outcomes', []):
                if outcome.get('name') == 'Over':
                    game_total = outcome.get('point'); break
            if game_total is None and totals_market.get('outcomes'):
                game_total = totals_market['outcomes'][0].get('point')
            if game_total is None:
                continue

            home_spread = None; away_spread = None
            for outcome in spreads_market.get('outcomes', []):
                if outcome.get('name') == home_team: home_spread = outcome.get('point')
                elif outcome.get('name') == away_team: away_spread = outcome.get('point')
            if home_spread is None or away_spread is None:
                continue

            if home_spread < 0:
                home_implied_points = (game_total - home_spread) / 2
                away_implied_points = (game_total + home_spread) / 2
            else:
                home_implied_points = (game_total + home_spread) / 2
                away_implied_points = (game_total - home_spread) / 2

            fg_penalty = 0.75
            home_td_points = home_implied_points * fg_penalty
            away_td_points = away_implied_points * fg_penalty

            vegas_totals[game_key] = {
                'home_team': home_abbr,
                'away_team': away_abbr,
                'home_vegas_tds': round(home_td_points / 7, 2),
                'away_vegas_tds': round(away_td_points / 7, 2),
                'commence_time': game.get('commence_time'),
                'bookmaker': selected_bookmaker.get('key')
            }

        return vegas_totals

    def get_team_analysis(self, week=None):
        try:
            self._ensure_calculator_initialized()
            vegas_totals = self.get_vegas_team_totals()
            if not vegas_totals:
                return {"error": "No Vegas data available"}

            w_edge = self.get_week_parameters(week)
            td_boost_results = self.td_calculator.analyze_week_matchups(week)
            if 'games' not in td_boost_results:
                return {"error": "No TD boost data available", "details": td_boost_results}

            combined_results = {
                'week': week or self.get_current_week(),
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'w_edge': w_edge,
                'games': []
            }

            for game_data in td_boost_results['games']:
                away_team = game_data['away_team']; home_team = game_data['home_team']
                game_key = f"{away_team}@{home_team}"
                if game_key not in vegas_totals:
                    continue
                vegas_game = vegas_totals[game_key]

                away_advantage_raw = game_data['away_offense_vs_home_defense']['combined_team_analysis'].get('total_team_td_advantage_pct', 0) or 0
                home_advantage_raw = game_data['home_offense_vs_away_defense']['combined_team_analysis'].get('total_team_td_advantage_pct', 0) or 0

                away_advantage_pct = max(-0.30, min(0.30, away_advantage_raw / 100))
                home_advantage_pct = max(-0.30, min(0.30, home_advantage_raw / 100))

                away_projected_tds = vegas_game['away_vegas_tds'] * (1 + w_edge * away_advantage_pct)
                home_projected_tds = vegas_game['home_vegas_tds'] * (1 + w_edge * home_advantage_pct)

                combined_results['games'].append({
                    'game': f"{away_team} @ {home_team}",
                    'commence_time': vegas_game['commence_time'],
                    'bookmaker': vegas_game['bookmaker'],
                    'away_team': away_team,
                    'home_team': home_team,
                    'away_vegas_tds': vegas_game['away_vegas_tds'],
                    'home_vegas_tds': vegas_game['home_vegas_tds'],
                    'away_td_advantage_pct': round(away_advantage_raw, 1),
                    'home_td_advantage_pct': round(home_advantage_raw, 1),
                    'away_projected_tds': round(away_projected_tds, 2),
                    'home_projected_tds': round(home_projected_tds, 2),
                    'calculation': {
                        'w_edge': w_edge,
                        'away_calc': f"{vegas_game['away_vegas_tds']} * (1 + {w_edge} * {away_advantage_pct:.3f}) = {away_projected_tds:.2f}",
                        'home_calc': f"{vegas_game['home_vegas_tds']} * (1 + {w_edge} * {home_advantage_pct:.3f}) = {home_projected_tds:.2f}"
                    }
                })

            return combined_results

        except Exception as e:
            print(f"Error in get_team_analysis: {str(e)}")
            return {"error": f"Analysis failed: {str(e)}"}

    def refresh_data(self):
        try:
            if self.td_calculator:
                self.td_calculator.load_data()
            return True
        except Exception as e:
            print(f"Error refreshing data: {str(e)}")
            raise

# --------------------------
# Calculator (with safe 2025 loader for nfl_data_py 0.3.2)
# --------------------------
class NFLTDBoostCalculator:
    def __init__(self, service_instance=None):
        self.service_instance = service_instance
        self.baselines_2024 = {}
        self.current_2025 = {}
        self.schedule_data = None
        self.league_averages = {}

    # --- helper: robust 2025 PBP import to dodge NameError path in nfl_data_py 0.3.2 ---
    def _import_pbp_2025_safe(self):
        """
        Work around nfl_data_py 0.3.2 NameError('Error') for current-season pulls.
        Try a couple of signatures/paths so we still get data on Railway.
        """
        cols = ['game_id','posteam','defteam','fixed_drive','touchdown','yardline_100','week']
        last_err = None
        # 1) Try with downcast=False and trimmed columns (skips the downcast branch)
        try:
            return nfl.import_pbp_data([2025], downcast=False, columns=cols)
        except Exception as e:
            last_err = e
            print(f"_import_pbp_2025_safe attempt A failed: {e}")
        # 2) Try default downcast but with trimmed columns
        try:
            return nfl.import_pbp_data([2025], columns=cols)
        except Exception as e:
            last_err = e
            print(f"_import_pbp_2025_safe attempt B failed: {e}")
        # 3) Final fallback: default call (may hit NameError in lib)
        try:
            return nfl.import_pbp_data([2025])
        except Exception as e:
            last_err = e
            print(f"_import_pbp_2025_safe attempt C failed: {e}")
            raise last_err

    def load_schedule(self):
        try:
            print("Loading 2025 NFL schedule...")
            self.schedule_data = nfl.import_schedules([2025])
            if self.schedule_data.empty:
                raise ValueError("No schedule data available for 2025")
            self.schedule_data['gameday'] = pd.to_datetime(self.schedule_data['gameday'])
            print(f"Schedule loaded: {len(self.schedule_data)} games")
            return True
        except Exception as e:
            print(f"Failed to load schedule: {str(e)}")
            self.schedule_data = None
            return False

    def calculate_rz_stats_with_filter(self, df, year_label=""):
        print(f"Calculating {year_label} red zone stats with 2+ plays filter...")
        if 'week' in df.columns:
            reg_season = df[df['week'] <= 18] if year_label == "2024" else df
        else:
            reg_season = df

        rz_drives = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]

        offense_results = {}
        for team in rz_drives['posteam'].dropna().unique():
            team_rz = rz_drives[rz_drives['posteam'] == team]
            play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
            multi_play_drives = play_counts[play_counts > 1]
            if len(multi_play_drives) > 0:
                filtered = team_rz[team_rz.set_index(['game_id','fixed_drive']).index.isin(multi_play_drives.index)]
                summary = filtered.groupby(['game_id','posteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()
                drives = len(summary); tds = float(summary['touchdown'].sum())
                rate = round(tds/drives*100,1) if drives>0 else 0
                offense_results[team] = {'rz_drives':drives,'rz_tds':tds,'rz_td_rate':float(rate)}

        defense_results = {}
        for team in rz_drives['defteam'].dropna().unique():
            team_rz = rz_drives[rz_drives['defteam'] == team]
            play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
            multi_play_drives = play_counts[play_counts > 1]
            if len(multi_play_drives) > 0:
                filtered = team_rz[team_rz.set_index(['game_id','fixed_drive']).index.isin(multi_play_drives.index)]
                summary = filtered.groupby(['game_id','defteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()
                drives = len(summary); tds = float(summary['touchdown'].sum())
                rate = round(tds/drives*100,1) if drives>0 else 0
                defense_results[team] = {'rz_drives_faced':drives,'rz_tds_allowed':tds,'rz_td_allow_rate':float(rate)}

        return offense_results, defense_results

    def calculate_all_drives_stats(self, df, year_label=""):
        print(f"Calculating {year_label} all drives stats...")
        if 'week' in df.columns:
            reg_season = df[df['week'] <= 18] if year_label == "2024" else df
        else:
            reg_season = df

        all_drives = reg_season.groupby(['game_id','posteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()

        offense_all = all_drives.groupby('posteam').apply(
            lambda x: {
                'total_drives': len(x),
                'total_tds': float(x['touchdown'].sum()),
                'total_td_rate': round(float(x['touchdown'].sum())/len(x)*100, 1)
            }
        ).to_dict()

        all_drives_def = reg_season.groupby(['game_id','defteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()
        defense_all = all_drives_def.groupby('defteam').apply(
            lambda x: {
                'total_drives_faced': len(x),
                'total_tds_allowed': float(x['touchdown'].sum()),
                'total_td_allow_rate': round(float(x['touchdown'].sum())/len(x)*100, 1)
            }
        ).to_dict()

        return offense_all, defense_all

    def calculate_league_averages(self):
        print("Calculating 2024 league averages...")
        df_2024 = nfl.import_pbp_data([2024])
        # nfl_data_py==0.3.2 prints "2024 done. Downcasting floats." internally.
        reg_season = df_2024[df_2024['week'] <= 18] if 'week' in df_2024.columns else df_2024

        rz = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]
        all_rz_rows = []
        for (game_id, team), g in rz.groupby(['game_id','posteam'], dropna=False):
            if pd.isna(team): continue
            for d_id, d in g.groupby('fixed_drive'):
                if len(d) >= 2: all_rz_rows.append({'side':'off','td': int(d['touchdown'].max())})
        for (game_id, team), g in rz.groupby(['game_id','defteam'], dropna=False):
            if pd.isna(team): continue
            for d_id, d in g.groupby('fixed_drive'):
                if len(d) >= 2: all_rz_rows.append({'side':'def','td': int(d['touchdown'].max())})

        rz_df = pd.DataFrame(all_rz_rows)
        if rz_df.empty:
            off_rz_avg = def_rz_avg = 0.0
        else:
            off_rz = rz_df[rz_df['side']=='off']; def_rz = rz_df[rz_df['side']=='def']
            off_rz_avg = (float(off_rz['td'].sum())/max(len(off_rz),1))*100 if not off_rz.empty else 0.0
            def_rz_avg = (float(def_rz['td'].sum())/max(len(def_rz),1))*100 if not def_rz.empty else 0.0

        all_off = reg_season.groupby(['game_id','posteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()
        all_def = reg_season.groupby(['game_id','defteam','fixed_drive']).agg({'touchdown':'max'}).reset_index()
        all_off_avg = (float(all_off['touchdown'].sum())/max(len(all_off),1))*100 if not all_off.empty else 0.0
        all_def_avg = (float(all_def['touchdown'].sum())/max(len(all_def),1))*100 if not all_def.empty else 0.0

        self.league_averages = {
            'rz_scoring': round(off_rz_avg,1),
            'rz_allow': round(def_rz_avg,1),
            'all_drives_scoring': round(all_off_avg,1),
            'all_drives_allow': round(all_def_avg,1),
        }
        print(f"League averages - RZ scoring: {self.league_averages['rz_scoring']}%, "
              f"RZ allow: {self.league_averages['rz_allow']}%")
        print(f"All drives - Scoring: {self.league_averages['all_drives_scoring']}%, "
              f"Allow: {self.league_averages['all_drives_allow']}%")

    def load_data(self):
        try:
            self.calculate_league_averages()

            print("Loading 2024 baseline data...")
            df_2024 = nfl.import_pbp_data([2024])
            off_rz_2024, def_rz_2024 = self.calculate_rz_stats_with_filter(df_2024, "2024")
            off_all_2024, def_all_2024 = self.calculate_all_drives_stats(df_2024, "2024")
            self.baselines_2024 = {
                'offense_rz': off_rz_2024, 'defense_rz': def_rz_2024,
                'offense_all': off_all_2024, 'defense_all': def_all_2024
            }

            print("Loading 2025 current data...")
            # >>> use safe import to avoid NameError path in nfl_data_py 0.3.2
            df_2025 = self._import_pbp_2025_safe()

            off_rz_2025, def_rz_2025 = self.calculate_rz_stats_with_filter(df_2025, "2025")
            off_all_2025, def_all_2025 = self.calculate_all_drives_stats(df_2025, "2025")
            self.current_2025 = {
                'offense_rz': off_rz_2025, 'defense_rz': def_rz_2025,
                'offense_all': off_all_2025, 'defense_all': def_all_2025
            }

            self.load_schedule()
            print("Data loading complete! (2024 baselines + 2025 current)")
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            raise

    def get_current_week(self):
        try:
            try:
                df_2025 = self._import_pbp_2025_safe()
                max_completed_week = df_2025['week'].max() if not df_2025.empty else 0
            except Exception as e:
                print(f"Error loading 2025 play-by-play data: {str(e)}")
                max_completed_week = 0

            if self.schedule_data is not None:
                try:
                    from datetime import timezone, timedelta
                    est = timezone(timedelta(hours=-5))
                    today = datetime.now(est).date()
                    upcoming = self.schedule_data[self.schedule_data['gameday'].dt.date >= today].sort_values('gameday')
                    if not upcoming.empty:
                        next_week = upcoming['week'].iloc[0]
                        print(f"Current week determined: {next_week} (max completed: {max_completed_week}, today: {today})")
                        return int(next_week)
                except Exception as e:
                    print(f"Error determining week from schedule: {str(e)}")

            fallback_week = int(max_completed_week) + 1
            print(f"Using fallback week: {fallback_week} (max completed: {max_completed_week})")
            return fallback_week
        except Exception as e:
            print(f"Could not determine current week: {str(e)}")
            return 3

    def get_week_matchups(self, week_num=None):
        try:
            if self.schedule_data is None:
                if not self.load_schedule():
                    return []
            if week_num is None:
                week_num = self.get_current_week()

            week_games = self.schedule_data[self.schedule_data['week'] == week_num].copy()
            if week_games.empty:
                print(f"No games found for week {week_num}")
                return []

            matchups = []
            for _, game in week_games.iterrows():
                matchups.append({
                    'away_team': game['away_team'], 'home_team': game['home_team'],
                    'gameday': game['gameday'].strftime('%Y-%m-%d') if pd.notna(game['gameday']) else 'TBD',
                    'week': int(game['week'])
                })
            print(f"Found {len(matchups)} games for week {week_num}")
            return matchups
        except Exception as e:
            print(f"Error getting week {week_num} matchups: {str(e)}")
            return []

    def calculate_matchup_boosts(self, offense_team, defense_team):
        if not self.baselines_2024 or not self.current_2025:
            self.load_data()

        results = {
            'matchup': f"{offense_team} vs {defense_team}",
            'offense_team': offense_team, 'defense_team': defense_team,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        rz_analysis = {}
        if offense_team in self.current_2025['offense_rz']:
            current_off_rz = self.current_2025['offense_rz'][offense_team]['rz_td_rate']
            league_avg_rz_scoring = self.league_averages['rz_scoring']
            pct_change = ((current_off_rz - league_avg_rz_scoring)/league_avg_rz_scoring*100) if league_avg_rz_scoring>0 else 0
            rz_analysis['offense_rz_pct_change_vs_league'] = round(pct_change,1)
            rz_analysis['offense_2025_rz_td_rate'] = current_off_rz
            rz_analysis['league_2024_rz_scoring_avg'] = league_avg_rz_scoring
        else:
            rz_analysis['offense_rz_pct_change_vs_league'] = None
            rz_analysis['note'] = f"Insufficient {offense_team} RZ data"

        if defense_team in self.current_2025['defense_rz']:
            current_def_rz = self.current_2025['defense_rz'][defense_team]['rz_td_allow_rate']
            league_avg_rz_allow = self.league_averages['rz_allow']
            pct_change = ((current_def_rz - league_avg_rz_allow)/league_avg_rz_allow*100) if league_avg_rz_allow>0 else 0
            rz_analysis['defense_rz_pct_change_vs_league'] = round(pct_change,1)
            rz_analysis['defense_2025_rz_allow_rate'] = current_def_rz
            rz_analysis['league_2024_rz_allow_avg'] = league_avg_rz_allow
        else:
            rz_analysis['defense_rz_pct_change_vs_league'] = None

        results['red_zone'] = rz_analysis

        all_drives_analysis = {}
        if offense_team in self.current_2025['offense_all']:
            current_off_all = self.current_2025['offense_all'][offense_team]['total_td_rate']
            league_avg_all_scoring = self.league_averages['all_drives_scoring']
            pct_change = ((current_off_all - league_avg_all_scoring)/league_avg_all_scoring*100) if league_avg_all_scoring>0 else 0
            all_drives_analysis['offense_all_drives_pct_change_vs_league'] = round(pct_change,1)
            all_drives_analysis['offense_2025_all_drives_td_rate'] = current_off_all
            all_drives_analysis['league_2024_all_drives_scoring_avg'] = league_avg_all_scoring
        else:
            all_drives_analysis['offense_all_drives_pct_change_vs_league'] = None

        if defense_team in self.current_2025['defense_all']:
            current_def_all = self.current_2025['defense_all'][defense_team]['total_td_allow_rate']
            league_avg_all_allow = self.league_averages['all_drives_allow']
            pct_change = ((current_def_all - league_avg_all_allow)/league_avg_all_allow*100) if league_avg_all_allow>0 else 0
            all_drives_analysis['defense_all_drives_pct_change_vs_league'] = round(pct_change,1)
            all_drives_analysis['defense_2025_all_drives_allow_rate'] = current_def_all
            all_drives_analysis['league_2024_all_drives_allow_avg'] = league_avg_all_allow
        else:
            all_drives_analysis['defense_all_drives_pct_change_vs_league'] = None

        results['all_drives'] = all_drives_analysis

        combined = {}
        off_rz_pct = rz_analysis.get('offense_rz_pct_change_vs_league')
        off_all_pct = all_drives_analysis.get('offense_all_drives_pct_change_vs_league')
        if off_rz_pct is not None and off_all_pct is not None:
            combined['offense_combined_pct_change'] = round((off_rz_pct + off_all_pct)/2, 1)
        elif off_rz_pct is not None:
            combined['offense_combined_pct_change'] = off_rz_pct
        elif off_all_pct is not None:
            combined['offense_combined_pct_change'] = off_all_pct
        else:
            combined['offense_combined_pct_change'] = None

        def_rz_pct = rz_analysis.get('defense_rz_pct_change_vs_league')
        def_all_pct = all_drives_analysis.get('defense_all_drives_pct_change_vs_league')
        if def_rz_pct is not None and def_all_pct is not None:
            combined['defense_combined_pct_change'] = round((def_rz_pct + def_all_pct)/2, 1)
        elif def_rz_pct is not None:
            combined['defense_combined_pct_change'] = def_rz_pct
        elif def_all_pct is not None:
            combined['defense_combined_pct_change'] = def_all_pct
        else:
            combined['defense_combined_pct_change'] = None

        off_combined = combined.get('offense_combined_pct_change')
        def_combined = combined.get('defense_combined_pct_change')
        if off_combined is not None and def_combined is not None:
            combined['total_team_td_advantage_pct'] = round((off_combined + def_combined)/2, 1)
        elif off_combined is not None:
            combined['total_team_td_advantage_pct'] = round(off_combined/2, 1)
        elif def_combined is not None:
            combined['total_team_td_advantage_pct'] = round(def_combined/2, 1)
        else:
            combined['total_team_td_advantage_pct'] = None

        combined['explanation'] = {
            'offense_combined': f"Average of {offense_team} RZ and all-drives TD rate % change vs 2024 league averages",
            'defense_combined': f"Average of {defense_team} RZ and all-drives TD allow rate % change vs 2024 league averages",
            'total_advantage': "Average of offense boost and defense vulnerability",
            'calculation_note': "RZ stats apply 2+ plays filter"
        }

        results['combined_team_analysis'] = combined
        return results

    def analyze_week_matchups(self, week_num=None):
        try:
            if not self.baselines_2024 or not self.current_2025:
                self.load_data()
            matchups = self.get_week_matchups(week_num)
            if not matchups:
                return {"error": "No matchups found", "week": week_num or self.get_current_week()}

            results = {
                'week': week_num or self.get_current_week(),
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'games': []
            }

            print(f"Analyzing {len(matchups)} games for week {results['week']}...")
            for m in matchups:
                away = m['away_team']; home = m['home_team']
                try:
                    away_off = self.calculate_matchup_boosts(away, home)
                    home_off = self.calculate_matchup_boosts(home, away)
                    results['games'].append({
                        'game': f"{away} @ {home}",
                        'gameday': m['gameday'],
                        'week': m['week'],
                        'away_team': away,
                        'home_team': home,
                        'away_offense_vs_home_defense': away_off,
                        'home_offense_vs_away_defense': home_off
                    })
                except Exception as e:
                    print(f"Error analyzing {away} @ {home}: {str(e)}")
                    continue

            def sort_key(g):
                away_adv = g['away_offense_vs_home_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                home_adv = g['home_offense_vs_away_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                return max(away_adv or -999, home_adv or -999)

            results['games'].sort(key=sort_key, reverse=True)
            print(f"Week {results['week']} analysis complete!")
            return results
        except Exception as e:
            print(f"Error in analyze_week_matchups: {str(e)}")
            return {"error": f"Matchup analysis failed: {str(e)}"}

# Initialize the service
team_service = TeamAnalysisService()

@app.route('/')
def home():
    return jsonify({
        "service": "NFL Team Analysis Service",
        "status": "running",
        "endpoints": [
            "/team-analysis - Get combined Vegas totals + TD boost analysis",
            "/health - Health check",
            "/refresh - Manual data refresh"
        ]
    })

@app.route('/team-analysis', methods=['GET'])
def get_team_analysis():
    try:
        results = team_service.get_team_analysis()
        return jsonify(results)
    except Exception as e:
        print(f"Error in team analysis endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/refresh', methods=['POST'])
def refresh_data_endpoint():
    try:
        team_service.refresh_data()
        return jsonify({
            "status": "success",
            "message": "Data refreshed successfully",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Team Analysis Service",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "next_refresh": "Daily at 6:00 AM UTC"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
