from flask import Flask, jsonify
import requests
import json
import time
from datetime import datetime
import nfl_data_py as nfl
import pandas as pd

app = Flask(__name__)

def timed_operation(description, func):
"""Helper function to time operations and log them"""
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
"""Combines Vegas team totals with TD boost calculations"""
self.odds_api_key = odds_api_key

# Hardcoded 2024 league averages (never change, massive startup speed improvement)
self.league_averages_2024 = {
'rz_scoring': 59.0,
'rz_allow': 59.0, 
'all_drives_scoring': 23.3,
'all_drives_allow': 23.3
}

# Team name mapping: Full Name -> Abbreviation
self.team_mapping = {
"Arizona Cardinals": "ARI",
"Atlanta Falcons": "ATL", 
"Baltimore Ravens": "BAL",
"Buffalo Bills": "BUF",
"Carolina Panthers": "CAR",
"Chicago Bears": "CHI",
"Cincinnati Bengals": "CIN",
"Cleveland Browns": "CLE",
"Dallas Cowboys": "DAL",
"Denver Broncos": "DEN",
"Detroit Lions": "DET",
"Green Bay Packers": "GB",
"Houston Texans": "HOU",
"Indianapolis Colts": "IND",
"Jacksonville Jaguars": "JAX",
"Kansas City Chiefs": "KC",
"Los Angeles Rams": "LAR",
"Miami Dolphins": "MIA",
"Minnesota Vikings": "MIN",
"New England Patriots": "NE",
"New Orleans Saints": "NO",
"New York Giants": "NYG",
"New York Jets": "NYJ",
"Las Vegas Raiders": "LV",
"Philadelphia Eagles": "PHI",
"Pittsburgh Steelers": "PIT",
"Los Angeles Chargers": "LAC",
"San Francisco 49ers": "SF",
"Seattle Seahawks": "SEA",
"Tampa Bay Buccaneers": "TB",
"Tennessee Titans": "TEN",
"Washington Commanders": "WAS"
}

# Bookmaker priority
self.book_priority = ['fanduel', 'draftkings', 'betmgm', 'caesars', 'betrivers']

# Initialize TD boost calculator after class is defined
self.td_calculator = None

def _ensure_calculator_initialized(self):
"""Initialize the TD calculator on first use"""
if self.td_calculator is None:
self.td_calculator = NFLTDBoostCalculator(service_instance=self)

def get_week_parameters(self, week=None):
"""Get consistent edge weight for all season"""
# Constant 25% weighting to your TD advantage throughout season
w_edge = 0.25
return w_edge

def get_current_week(self):
"""Get current NFL week"""
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
"""Get Vegas-implied team TD totals, filtered to current week games"""
self._ensure_calculator_initialized()

url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?regions=us&markets=totals,spreads&oddsFormat=american&apiKey={self.odds_api_key}"

try:
response = requests.get(url)
response.raise_for_status()
games_data = response.json()
except Exception as e:
print(f"Error fetching odds data: {e}")
return {}

# Get current week matchups to filter games
current_week_matchups = self.td_calculator.get_week_matchups()
if not current_week_matchups:
return {}

# Create expected games set for filtering
expected_games = set()
for matchup in current_week_matchups:
expected_games.add(f"{matchup['away_team']}@{matchup['home_team']}")

vegas_totals = {}

for game in games_data:
home_team = game['home_team']
away_team = game['away_team']

# Map to abbreviations
home_abbr = self.team_mapping.get(home_team)
away_abbr = self.team_mapping.get(away_team)

if not home_abbr or not away_abbr:
continue

game_key = f"{away_abbr}@{home_abbr}"

# Skip games not in current week
if game_key not in expected_games:
continue

# Get bookmaker data
selected_bookmaker = None
for book_key in self.book_priority:
for bookmaker in game['bookmakers']:
if bookmaker['key'] == book_key:
selected_bookmaker = bookmaker
break
if selected_bookmaker:
break

if not selected_bookmaker:
continue

# Extract totals and spreads
totals_market = None
spreads_market = None

for market in selected_bookmaker['markets']:
if market['key'] == 'totals':
totals_market = market
elif market['key'] == 'spreads':
spreads_market = market

if not totals_market or not spreads_market:
continue

# Get game total
game_total = None
for outcome in totals_market['outcomes']:
if outcome['name'] == 'Over':
game_total = outcome['point']
break

if game_total is None:
game_total = totals_market['outcomes'][0]['point']

# Get spreads
home_spread = None
away_spread = None

for outcome in spreads_market['outcomes']:
if outcome['name'] == home_team:
home_spread = outcome['point']
elif outcome['name'] == away_team:
away_spread = outcome['point']

if home_spread is None or away_spread is None:
continue

# Calculate implied points
if home_spread < 0:  # Home team favored
home_implied_points = (game_total - home_spread) / 2
away_implied_points = (game_total + home_spread) / 2
else:  # Away team favored
home_implied_points = (game_total + home_spread) / 2
away_implied_points = (game_total - home_spread) / 2

# Apply 25% reduction for field goals (75% of points come from TDs)
fg_penalty = 0.75
home_td_points = home_implied_points * fg_penalty
away_td_points = away_implied_points * fg_penalty

# Convert to TDs (7 points per TD)
home_vegas_tds = round(home_td_points / 7, 2)
away_vegas_tds = round(away_td_points / 7, 2)

vegas_totals[game_key] = {
'home_team': home_abbr,
'away_team': away_abbr,
'home_vegas_tds': home_vegas_tds,
'away_vegas_tds': away_vegas_tds,
'commence_time': game['commence_time'],
'bookmaker': selected_bookmaker['key']
}

return vegas_totals

def get_team_analysis(self, week=None):
"""
       Combine Vegas team totals with TD boost advantages
       Following GPT's exact formula: team_td_proj = vegas_team_tds * (1 + w_edge * advantage_pct)
       """
try:
self._ensure_calculator_initialized()

# Get Vegas totals
vegas_totals = self.get_vegas_team_totals()
if not vegas_totals:
return {"error": "No Vegas data available"}

# Get week parameters
w_edge = self.get_week_parameters(week)

# Get TD boost data for all current week games
td_boost_results = self.td_calculator.analyze_week_matchups(week)
if 'games' not in td_boost_results:
return {"error": "No TD boost data available", "details": td_boost_results}

# Combine Vegas totals with TD advantages
combined_results = {
'week': week or self.get_current_week(),
'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
'w_edge': w_edge,
'games': []
}

for game_data in td_boost_results['games']:
away_team = game_data['away_team']
home_team = game_data['home_team']
game_key = f"{away_team}@{home_team}"

if game_key not in vegas_totals:
continue

vegas_game = vegas_totals[game_key]

# Get TD advantages (convert from percentage to decimal)
away_advantage_raw = game_data['away_offense_vs_home_defense']['combined_team_analysis'].get('total_team_td_advantage_pct', 0)
home_advantage_raw = game_data['home_offense_vs_away_defense']['combined_team_analysis'].get('total_team_td_advantage_pct', 0)

if away_advantage_raw is None:
away_advantage_raw = 0
if home_advantage_raw is None:
home_advantage_raw = 0

# Convert to decimal and cap at ±30% (GPT's formula)
away_advantage_pct = max(-0.30, min(0.30, away_advantage_raw / 100))
home_advantage_pct = max(-0.30, min(0.30, home_advantage_raw / 100))

# Apply GPT's formula: team_td_proj = vegas_team_tds * (1 + w_edge * advantage_pct)
away_projected_tds = vegas_game['away_vegas_tds'] * (1 + w_edge * away_advantage_pct)
home_projected_tds = vegas_game['home_vegas_tds'] * (1 + w_edge * home_advantage_pct)

combined_game = {
'game': f"{away_team} @ {home_team}",
'commence_time': vegas_game['commence_time'],
'bookmaker': vegas_game['bookmaker'],
'away_team': away_team,
'home_team': home_team,

# Vegas baseline
'away_vegas_tds': vegas_game['away_vegas_tds'],
'home_vegas_tds': vegas_game['home_vegas_tds'],

# TD advantages
'away_td_advantage_pct': round(away_advantage_raw, 1),
'home_td_advantage_pct': round(home_advantage_raw, 1),

# Final projected TDs (GPT's formula applied)
'away_projected_tds': round(away_projected_tds, 2),
'home_projected_tds': round(home_projected_tds, 2),

# Show the calculation
'calculation': {
'w_edge': w_edge,
'away_calc': f"{vegas_game['away_vegas_tds']} * (1 + {w_edge} * {away_advantage_pct:.3f}) = {away_projected_tds:.2f}",
'home_calc': f"{vegas_game['home_vegas_tds']} * (1 + {w_edge} * {home_advantage_pct:.3f}) = {home_projected_tds:.2f}"
}
}

combined_results['games'].append(combined_game)

return combined_results

except Exception as e:
print(f"Error in get_team_analysis: {str(e)}")
return {"error": f"Analysis failed: {str(e)}"}

def refresh_data(self):
"""Refresh data method for manual refresh endpoint"""
try:
if self.td_calculator:
self.td_calculator.load_data()
return True
except Exception as e:
print(f"Error refreshing data: {str(e)}")
raise

# Copy your exact NFLTDBoostCalculator class here (keeping all logic unchanged)
class NFLTDBoostCalculator:
def __init__(self, service_instance=None):
"""Initialize the TD Boost Calculator with consistent methodology"""
self.service_instance = service_instance
self.baselines_2024 = {}
self.current_2025 = {}
self.schedule_data = None
self.league_averages = {}

def load_schedule(self):
"""Load NFL schedule data"""
try:
print("Loading 2025 NFL schedule...")
self.schedule_data = nfl.import_schedules([2025])

if self.schedule_data.empty:
raise ValueError("No schedule data available for 2025")

# Convert game_id to ensure proper formatting
self.schedule_data['gameday'] = pd.to_datetime(self.schedule_data['gameday'])
print(f"Schedule loaded: {len(self.schedule_data)} games")
return True

except Exception as e:
print(f"Failed to load schedule: {str(e)}")
self.schedule_data = None
return False

def calculate_rz_stats_with_filter(self, df, year_label=""):
"""Calculate red zone stats with 2+ plays filter for consistent methodology"""
        print(f"Calculating {year_label} red zone stats with 2+ plays filter...")
        
        # Filter for regular season only
        if 'week' in df.columns:
            reg_season = df[df['week'] <= 18] if year_label == "2024" else df
        else:
            reg_season = df
        try:
            print(f"Calculating {year_label} red zone stats with 2+ plays filter...")

        rz_drives = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]
        
        # Offensive stats
        offense_results = {}
        for team in rz_drives['posteam'].unique():
            if pd.isna(team):
                continue
            team_rz = rz_drives[rz_drives['posteam'] == team]
            play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
            multi_play_drives = play_counts[play_counts > 1]  # 2+ plays filter
            if df.empty:
                print(f"No data available for {year_label} red zone stats")
                return {}, {}

            if len(multi_play_drives) > 0:
                filtered_drives = team_rz[team_rz.set_index(['game_id', 'fixed_drive']).index.isin(multi_play_drives.index)]
                drive_summary = filtered_drives.groupby(['game_id', 'posteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
            # Filter for regular season only
            if 'week' in df.columns:
                reg_season = df[df['week'] <= 18] if year_label == "2024" else df
            else:
                reg_season = df

                drives = len(drive_summary)
                tds = float(drive_summary['touchdown'].sum())
                rate = round(tds/drives*100, 1) if drives > 0 else 0
                offense_results[team] = {
                    'rz_drives': drives,
                    'rz_tds': tds,
                    'rz_td_rate': float(rate)
                }
        
        # Defensive stats
        defense_results = {}
        for team in rz_drives['defteam'].unique():
            if pd.isna(team):
                continue
            team_rz = rz_drives[rz_drives['defteam'] == team]
            play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
            multi_play_drives = play_counts[play_counts > 1]  # Same 2+ plays filter
            rz_drives = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]

            if len(multi_play_drives) > 0:
                filtered_drives = team_rz[team_rz.set_index(['game_id', 'fixed_drive']).index.isin(multi_play_drives.index)]
                drive_summary = filtered_drives.groupby(['game_id', 'defteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
                
                drives = len(drive_summary)
                tds = float(drive_summary['touchdown'].sum())
                rate = round(tds/drives*100, 1) if drives > 0 else 0
                defense_results[team] = {
                    'rz_drives_faced': drives,
                    'rz_tds_allowed': tds,
                    'rz_td_allow_rate': float(rate)
                }
        
        return offense_results, defense_results
            if rz_drives.empty:
                print(f"No red zone drives found for {year_label}")
                return {}, {}
            
            # Offensive stats
            offense_results = {}
            for team in rz_drives['posteam'].unique():
                if pd.isna(team):
                    continue
                try:
                    team_rz = rz_drives[rz_drives['posteam'] == team]
                    play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
                    multi_play_drives = play_counts[play_counts > 1]  # 2+ plays filter
                    
                    if len(multi_play_drives) > 0:
                        filtered_drives = team_rz[team_rz.set_index(['game_id', 'fixed_drive']).index.isin(multi_play_drives.index)]
                        drive_summary = filtered_drives.groupby(['game_id', 'posteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
                        
                        drives = len(drive_summary)
                        tds = float(drive_summary['touchdown'].sum())
                        rate = round(tds/drives*100, 1) if drives > 0 else 0
                        offense_results[team] = {
                            'rz_drives': drives,
                            'rz_tds': tds,
                            'rz_td_rate': float(rate)
                        }
                except Exception as e:
                    print(f"Error calculating offensive RZ stats for {team}: {str(e)}")
                    continue
            
            # Defensive stats
            defense_results = {}
            for team in rz_drives['defteam'].unique():
                if pd.isna(team):
                    continue
                try:
                    team_rz = rz_drives[rz_drives['defteam'] == team]
                    play_counts = team_rz.groupby(['game_id', 'fixed_drive']).size()
                    multi_play_drives = play_counts[play_counts > 1]  # Same 2+ plays filter
                    
                    if len(multi_play_drives) > 0:
                        filtered_drives = team_rz[team_rz.set_index(['game_id', 'fixed_drive']).index.isin(multi_play_drives.index)]
                        drive_summary = filtered_drives.groupby(['game_id', 'defteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
                        
                        drives = len(drive_summary)
                        tds = float(drive_summary['touchdown'].sum())
                        rate = round(tds/drives*100, 1) if drives > 0 else 0
                        defense_results[team] = {
                            'rz_drives_faced': drives,
                            'rz_tds_allowed': tds,
                            'rz_td_allow_rate': float(rate)
                        }
                except Exception as e:
                    print(f"Error calculating defensive RZ stats for {team}: {str(e)}")
                    continue
            
            print(f"RZ stats calculated: {len(offense_results)} offensive teams, {len(defense_results)} defensive teams")
            return offense_results, defense_results
            
        except Exception as e:
            print(f"Error in calculate_rz_stats_with_filter: {str(e)}")
            return {}, {}

def calculate_all_drives_stats(self, df, year_label=""):
"""Calculate all drives TD stats"""
@@ -458,29 +480,56 @@
start_time = time.time()

def load_2025_data():
                return nfl.import_pbp_data([2025])
                try:
                    return nfl.import_pbp_data([2025])
                except Exception as e:
                    print(f"Error loading 2025 NFL data: {str(e)}")
                    # Return empty DataFrame on error
                    return pd.DataFrame()

df_2025 = timed_operation("2025 NFL data download", load_2025_data)

            def calculate_rz_stats():
                return self.calculate_rz_stats_with_filter(df_2025, "2025")
            
            def calculate_all_drives():
                return self.calculate_all_drives_stats(df_2025, "2025")
            
            off_rz_2025, def_rz_2025 = timed_operation("2025 RZ stats calculation", calculate_rz_stats)
            off_all_2025, def_all_2025 = timed_operation("2025 all drives calculation", calculate_all_drives)
            
            self.current_2025 = {
                'offense_rz': off_rz_2025,
                'defense_rz': def_rz_2025,
                'offense_all': off_all_2025,
                'defense_all': def_all_2025
            }
            # Only proceed if we have data
            if df_2025.empty:
                print("No 2025 data available, using empty datasets")
                self.current_2025 = {
                    'offense_rz': {},
                    'defense_rz': {},
                    'offense_all': {},
                    'defense_all': {}
                }
            else:
                def calculate_rz_stats():
                    try:
                        return self.calculate_rz_stats_with_filter(df_2025, "2025")
                    except Exception as e:
                        print(f"Error calculating RZ stats: {str(e)}")
                        return {}, {}
                
                def calculate_all_drives():
                    try:
                        return self.calculate_all_drives_stats(df_2025, "2025")
                    except Exception as e:
                        print(f"Error calculating all drives stats: {str(e)}")
                        return {}, {}
                
                off_rz_2025, def_rz_2025 = timed_operation("2025 RZ stats calculation", calculate_rz_stats)
                off_all_2025, def_all_2025 = timed_operation("2025 all drives calculation", calculate_all_drives)
                
                self.current_2025 = {
                    'offense_rz': off_rz_2025,
                    'defense_rz': def_rz_2025,
                    'offense_all': off_all_2025,
                    'defense_all': def_all_2025
                }

# Load schedule
def load_sched():
                return self.load_schedule()
                try:
                    return self.load_schedule()
                except Exception as e:
                    print(f"Error loading schedule: {str(e)}")
                    return False

timed_operation("Schedule data loading", load_sched)

@@ -707,13 +756,21 @@
def analyze_week_matchups(self, week_num=None):
"""Analyze all matchups for a specific week"""
try:
            print(f"Starting analyze_week_matchups with week_num: {week_num}")
            
if not self.current_2025:
                print("No current_2025 data, loading...")
self.load_data()

            print("Getting week matchups...")
# Get current week matchups
matchups = self.get_week_matchups(week_num)
if not matchups:
                return {"error": "No matchups found", "week": week_num or self.get_current_week()}
                error_msg = f"No matchups found for week {week_num or self.get_current_week()}"
                print(error_msg)
                return {"error": error_msg, "week": week_num or self.get_current_week()}
            
            print(f"Found {len(matchups)} matchups")

results = {
'week': week_num or self.get_current_week(),
@@ -723,15 +780,19 @@

print(f"Analyzing {len(matchups)} games for week {results['week']}...")

            for matchup in matchups:
            for i, matchup in enumerate(matchups):
away_team = matchup['away_team']
home_team = matchup['home_team']

try:
                    print(f"Analyzing game {i+1}/{len(matchups)}: {away_team} @ {home_team}")
                    
# Analyze away team offense vs home team defense
                    print(f"  - Analyzing {away_team} offense vs {home_team} defense")
away_offense_analysis = self.calculate_matchup_boosts(away_team, home_team)

# Analyze home team offense vs away team defense  
                    print(f"  - Analyzing {home_team} offense vs {away_team} defense")
home_offense_analysis = self.calculate_matchup_boosts(home_team, away_team)

game_result = {
@@ -745,16 +806,27 @@
}

results['games'].append(game_result)
                    print(f"  - Game {i+1} analysis complete")

except Exception as e:
print(f"Error analyzing {away_team} @ {home_team}: {str(e)}")
                    print(f"Error type: {type(e).__name__}")
                    import traceback
                    traceback.print_exc()
continue

            if not results['games']:
                return {"error": "No games could be analyzed", "week": results['week']}
            
# Sort by highest total team advantages
def get_sort_key(game):
                away_adv = game['away_offense_vs_home_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                home_adv = game['home_offense_vs_away_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                return max(away_adv or -999, home_adv or -999)
                try:
                    away_adv = game['away_offense_vs_home_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                    home_adv = game['home_offense_vs_away_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                    return max(away_adv or -999, home_adv or -999)
                except Exception as e:
                    print(f"Error in sort key: {str(e)}")
                    return -999

results['games'].sort(key=get_sort_key, reverse=True)

@@ -763,8 +835,12 @@

except Exception as e:
print(f"Error in analyze_week_matchups: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
return {"error": f"Matchup analysis failed: {str(e)}"}


# Initialize the service
team_service = TeamAnalysisService()
