import nfl_data_py as nfl
import pandas as pd
import json
from datetime import datetime, timedelta
import logging
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NFLTDBoostCalculator:
    def __init__(self):
        """Initialize the TD Boost Calculator with consistent methodology"""
        self.baselines_2024 = {}
        self.current_2025 = {}
        self.schedule_data = None
        self.data_loaded = False
        
        # Don't load anything in __init__ - exactly like your local version
        
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
            
        rz_drives = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]
        
        # Offensive stats
        offense_results = {}
        for team in rz_drives['posteam'].unique():
            if pd.isna(team):
                continue
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
        
        # Defensive stats
        defense_results = {}
        for team in rz_drives['defteam'].unique():
            if pd.isna(team):
                continue
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
        
        return offense_results, defense_results
    
    def calculate_all_drives_stats(self, df, year_label=""):
        """Calculate all drives TD stats"""
        print(f"Calculating {year_label} all drives stats...")
        
        # Filter for regular season only
        if 'week' in df.columns:
            reg_season = df[df['week'] <= 18] if year_label == "2024" else df
        else:
            reg_season = df
        
        all_drives = reg_season.groupby(['game_id', 'posteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
        
        # Offensive stats
        offense_all = all_drives.groupby('posteam').apply(
            lambda x: {
                'total_drives': len(x),
                'total_tds': float(x['touchdown'].sum()),
                'total_td_rate': round(float(x['touchdown'].sum()) / len(x) * 100, 1)
            }, include_groups=False
        ).to_dict()
        
        # Defensive stats  
        all_drives_def = reg_season.groupby(['game_id', 'defteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
        defense_all = all_drives_def.groupby('defteam').apply(
            lambda x: {
                'total_drives_faced': len(x),
                'total_tds_allowed': float(x['touchdown'].sum()),
                'total_td_allow_rate': round(float(x['touchdown'].sum()) / len(x) * 100, 1)
            }, include_groups=False
        ).to_dict()
        
        return offense_all, defense_all
    
    def calculate_league_averages(self):
        """Calculate 2024 league-wide averages for boost comparisons"""
        print("Calculating 2024 league averages...")
        df_2024 = nfl.import_pbp_data([2024])
        reg_season = df_2024[df_2024['week'] <= 18]
        
        # Red Zone league averages (with 2+ plays filter)
        rz_drives = reg_season[(reg_season['yardline_100'] <= 20) & (reg_season['fixed_drive'].notna())]
        
        # Filter to drives with 2+ plays for consistency
        all_rz_drives = []
        for game_id in rz_drives['game_id'].unique():
            for team in rz_drives[rz_drives['game_id'] == game_id]['posteam'].unique():
                if pd.isna(team):
                    continue
                team_rz = rz_drives[(rz_drives['game_id'] == game_id) & (rz_drives['posteam'] == team)]
                for drive_id in team_rz['fixed_drive'].unique():
                    drive_plays = team_rz[team_rz['fixed_drive'] == drive_id]
                    if len(drive_plays) >= 2:  # 2+ plays filter
                        td_scored = drive_plays['touchdown'].max()
                        all_rz_drives.append({'scored_td': td_scored, 'is_offense': True})
                
                # Same for defense
                team_rz_def = rz_drives[(rz_drives['game_id'] == game_id) & (rz_drives['defteam'] == team)]
                for drive_id in team_rz_def['fixed_drive'].unique():
                    drive_plays = team_rz_def[team_rz_def['fixed_drive'] == drive_id]
                    if len(drive_plays) >= 2:  # 2+ plays filter
                        td_allowed = drive_plays['touchdown'].max()
                        all_rz_drives.append({'scored_td': td_allowed, 'is_offense': False})
        
        rz_df = pd.DataFrame(all_rz_drives)
        
        # Calculate averages
        league_rz_scoring_avg = (rz_df[rz_df['is_offense']]['scored_td'].sum() / 
                                len(rz_df[rz_df['is_offense']]) * 100) if len(rz_df[rz_df['is_offense']]) > 0 else 0
        
        league_rz_allow_avg = (rz_df[~rz_df['is_offense']]['scored_td'].sum() / 
                              len(rz_df[~rz_df['is_offense']]) * 100) if len(rz_df[~rz_df['is_offense']]) > 0 else 0
        
        # All drives league averages
        all_drives = reg_season.groupby(['game_id', 'posteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
        league_all_scoring_avg = (all_drives['touchdown'].sum() / len(all_drives) * 100)
        
        all_drives_def = reg_season.groupby(['game_id', 'defteam', 'fixed_drive']).agg({'touchdown': 'max'}).reset_index()
        league_all_allow_avg = (all_drives_def['touchdown'].sum() / len(all_drives_def) * 100)
        
        self.league_averages = {
            'rz_scoring': round(float(league_rz_scoring_avg), 1),
            'rz_allow': round(float(league_rz_allow_avg), 1), 
            'all_drives_scoring': round(float(league_all_scoring_avg), 1),
            'all_drives_allow': round(float(league_all_allow_avg), 1)
        }
        
        print(f"League averages - RZ scoring: {self.league_averages['rz_scoring']}%, RZ allow: {self.league_averages['rz_allow']}%")
        print(f"All drives - Scoring: {self.league_averages['all_drives_scoring']}%, Allow: {self.league_averages['all_drives_allow']}%")
        
    def load_data(self):
        """Load both 2024 baseline and 2025 current data"""
        # Calculate league averages first
        self.calculate_league_averages()
        
        # Load 2024 baseline data
        print("Loading 2024 baseline data...")
        df_2024 = nfl.import_pbp_data([2024])
        off_rz_2024, def_rz_2024 = self.calculate_rz_stats_with_filter(df_2024, "2024")
        off_all_2024, def_all_2024 = self.calculate_all_drives_stats(df_2024, "2024")
        
        self.baselines_2024 = {
            'offense_rz': off_rz_2024,
            'defense_rz': def_rz_2024,
            'offense_all': off_all_2024,
            'defense_all': def_all_2024
        }
        
        # Load 2025 current data
        print("Loading 2025 current data...")
        df_2025 = nfl.import_pbp_data([2025])
        off_rz_2025, def_rz_2025 = self.calculate_rz_stats_with_filter(df_2025, "2025")
        off_all_2025, def_all_2025 = self.calculate_all_drives_stats(df_2025, "2025")
        
        self.current_2025 = {
            'offense_rz': off_rz_2025,
            'defense_rz': def_rz_2025,
            'offense_all': off_all_2025,
            'defense_all': def_all_2025
        }
        
        # Load schedule
        self.load_schedule()
        
        print("Data loading complete!")
        self.data_loaded = True
    
    def get_current_week(self):
        """Determine current NFL week based on date and available data"""
        try:
            # Get current play-by-play data to see what's been completed
            df_2025 = nfl.import_pbp_data([2025])
            if not df_2025.empty:
                max_completed_week = df_2025['week'].max()
            else:
                max_completed_week = 0
            
            # Find the next upcoming games from schedule
            if self.schedule_data is not None:
                today = datetime.now().date()
                future_games = self.schedule_data[
                    self.schedule_data['gameday'].dt.date >= today
                ].sort_values('gameday')
                
                if not future_games.empty:
                    next_week = future_games['week'].iloc[0]
                    print(f"Current week determined: {next_week} (max completed: {max_completed_week})")
                    return int(next_week)
            
            # Fallback to max completed week + 1
            return int(max_completed_week) + 1
                
        except Exception as e:
            print(f"Could not determine current week: {str(e)}")
            return 2  # Default fallback
    
    def get_week_matchups(self, week_num=None):
        """Get actual matchups for a specific week from schedule data"""
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
                    'away_team': game['away_team'],
                    'home_team': game['home_team'],
                    'gameday': game['gameday'].strftime('%Y-%m-%d') if pd.notna(game['gameday']) else 'TBD',
                    'week': int(game['week'])
                })
            
            print(f"Found {len(matchups)} games for week {week_num}")
            return matchups
            
        except Exception as e:
            print(f"Error getting week {week_num} matchups: {str(e)}")
            return []
    
    def calculate_matchup_boosts(self, offense_team, defense_team):
        """Calculate TD boost for a specific matchup with percentage changes and detailed labels"""
        if not self.baselines_2024 or not self.current_2025:
            self.load_data()
        
        results = {
            'matchup': f"{offense_team} vs {defense_team}",
            'offense_team': offense_team,
            'defense_team': defense_team,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Red Zone Analysis - Percentage changes vs league averages
        rz_analysis = {}
        
        # Offense RZ performance vs league average (percentage change)
        if offense_team in self.current_2025['offense_rz']:
            current_off_rz = self.current_2025['offense_rz'][offense_team]['rz_td_rate']
            league_avg_rz_scoring = self.league_averages['rz_scoring']
            pct_change = ((current_off_rz - league_avg_rz_scoring) / league_avg_rz_scoring * 100) if league_avg_rz_scoring > 0 else 0
            rz_analysis['offense_rz_pct_change_vs_league'] = round(pct_change, 1)
            rz_analysis['offense_2025_rz_td_rate'] = current_off_rz
            rz_analysis['league_2024_rz_scoring_avg'] = league_avg_rz_scoring
        else:
            rz_analysis['offense_rz_pct_change_vs_league'] = None
            rz_analysis['note'] = f"Insufficient {offense_team} RZ data"
        
        # Defense RZ performance vs league average (percentage change)
        if defense_team in self.current_2025['defense_rz']:
            current_def_rz = self.current_2025['defense_rz'][defense_team]['rz_td_allow_rate']
            league_avg_rz_allow = self.league_averages['rz_allow']
            pct_change = ((current_def_rz - league_avg_rz_allow) / league_avg_rz_allow * 100) if league_avg_rz_allow > 0 else 0
            rz_analysis['defense_rz_pct_change_vs_league'] = round(pct_change, 1)
            rz_analysis['defense_2025_rz_allow_rate'] = current_def_rz
            rz_analysis['league_2024_rz_allow_avg'] = league_avg_rz_allow
        else:
            rz_analysis['defense_rz_pct_change_vs_league'] = None
        
        results['red_zone'] = rz_analysis
        
        # All Drives Analysis - Percentage changes vs league averages
        all_drives_analysis = {}
        
        # Offense all drives performance vs league average (percentage change)
        if offense_team in self.current_2025['offense_all']:
            current_off_all = self.current_2025['offense_all'][offense_team]['total_td_rate']
            league_avg_all_scoring = self.league_averages['all_drives_scoring']
            pct_change = ((current_off_all - league_avg_all_scoring) / league_avg_all_scoring * 100) if league_avg_all_scoring > 0 else 0
            all_drives_analysis['offense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
            all_drives_analysis['offense_2025_all_drives_td_rate'] = current_off_all
            all_drives_analysis['league_2024_all_drives_scoring_avg'] = league_avg_all_scoring
        else:
            all_drives_analysis['offense_all_drives_pct_change_vs_league'] = None
        
        # Defense all drives performance vs league average (percentage change)
        if defense_team in self.current_2025['defense_all']:
            current_def_all = self.current_2025['defense_all'][defense_team]['total_td_allow_rate']
            league_avg_all_allow = self.league_averages['all_drives_allow']
            pct_change = ((current_def_all - league_avg_all_allow) / league_avg_all_allow * 100) if league_avg_all_allow > 0 else 0
            all_drives_analysis['defense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
            all_drives_analysis['defense_2025_all_drives_allow_rate'] = current_def_all
            all_drives_analysis['league_2024_all_drives_allow_avg'] = league_avg_all_allow
        else:
            all_drives_analysis['defense_all_drives_pct_change_vs_league'] = None
        
        results['all_drives'] = all_drives_analysis
        
        # Combined Team Analysis - Average RZ and All Drives percentage changes
        combined_analysis = {}
        
        # Combined offense percentage change (average of RZ and all drives)
        off_rz_pct = rz_analysis.get('offense_rz_pct_change_vs_league')
        off_all_pct = all_drives_analysis.get('offense_all_drives_pct_change_vs_league')
        
        if off_rz_pct is not None and off_all_pct is not None:
            combined_analysis['offense_combined_pct_change'] = round((off_rz_pct + off_all_pct) / 2, 1)
        elif off_rz_pct is not None:
            combined_analysis['offense_combined_pct_change'] = off_rz_pct
        elif off_all_pct is not None:
            combined_analysis['offense_combined_pct_change'] = off_all_pct
        else:
            combined_analysis['offense_combined_pct_change'] = None
        
        # Combined defense percentage change (average of RZ and all drives)
        def_rz_pct = rz_analysis.get('defense_rz_pct_change_vs_league')
        def_all_pct = all_drives_analysis.get('defense_all_drives_pct_change_vs_league')
        
        if def_rz_pct is not None and def_all_pct is not None:
            combined_analysis['defense_combined_pct_change'] = round((def_rz_pct + def_all_pct) / 2, 1)
        elif def_rz_pct is not None:
            combined_analysis['defense_combined_pct_change'] = def_rz_pct
        elif def_all_pct is not None:
            combined_analysis['defense_combined_pct_change'] = def_all_pct
        else:
            combined_analysis['defense_combined_pct_change'] = None
        
        # Total team matchup advantage (average of offense and defense combined changes)
        off_combined = combined_analysis.get('offense_combined_pct_change')
        def_combined = combined_analysis.get('defense_combined_pct_change')
        
        if off_combined is not None and def_combined is not None:
            combined_analysis['total_team_td_advantage_pct'] = round((off_combined + def_combined) / 2, 1)
        elif off_combined is not None:
            combined_analysis['total_team_td_advantage_pct'] = round(off_combined / 2, 1)
        elif def_combined is not None:
            combined_analysis['total_team_td_advantage_pct'] = round(def_combined / 2, 1)
        else:
            combined_analysis['total_team_td_advantage_pct'] = None
        
        # Add explanations
        combined_analysis['explanation'] = {
            'offense_combined': f"Average of {offense_team} RZ and all-drives TD rate % change vs 2024 league averages",
            'defense_combined': f"Average of {defense_team} RZ and all-drives TD allow rate % change vs 2024 league averages", 
            'total_advantage': f"Overall team TD scoring advantage: average of offense boost and defense vulnerability",
            'calculation_note': "All red zone stats use 2+ plays filter for consistency with industry standards"
        }
        
        results['combined_team_analysis'] = combined_analysis
        
        return results
    
    def analyze_week_matchups(self, week_num=None):
        """Analyze all matchups for a specific week"""
        if not self.baselines_2024 or not self.current_2025:
            self.load_data()
        
        # Get current week matchups
        matchups = self.get_week_matchups(week_num)
        if not matchups:
            return {"error": "No matchups found", "week": week_num or self.get_current_week()}
        
        results = {
            'week': week_num or self.get_current_week(),
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'games': []
        }
        
        print(f"Analyzing {len(matchups)} games for week {results['week']}...")
        
        for matchup in matchups:
            away_team = matchup['away_team']
            home_team = matchup['home_team']
            
            try:
                # Analyze away team offense vs home team defense
                away_offense_analysis = self.calculate_matchup_boosts(away_team, home_team)
                
                # Analyze home team offense vs away team defense  
                home_offense_analysis = self.calculate_matchup_boosts(home_team, away_team)
                
                game_result = {
                    'game': f"{away_team} @ {home_team}",
                    'gameday': matchup['gameday'],
                    'week': matchup['week'],
                    'away_team': away_team,
                    'home_team': home_team,
                    'away_offense_vs_home_defense': away_offense_analysis,
                    'home_offense_vs_away_defense': home_offense_analysis
                }
                
                results['games'].append(game_result)
                
            except Exception as e:
                print(f"Error analyzing {away_team} @ {home_team}: {str(e)}")
                continue
        
        # Sort by highest total team advantages
        def get_sort_key(game):
            away_adv = game['away_offense_vs_home_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
            home_adv = game['home_offense_vs_away_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
            return max(away_adv or -999, home_adv or -999)
        
        results['games'].sort(key=get_sort_key, reverse=True)
        
        print(f"Week {results['week']} analysis complete!")
        return results
    
    def generate_json_output(self, results, include_metadata=True):
        """Generate JSON output for API consumption"""
        try:
            output = {
                "games": results,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "total_games": len(results.get('games', [])) if isinstance(results, dict) else len(results),
                    "data_loaded": self.data_loaded,
                    "disclaimer": "For educational analysis only. Small sample sizes in early season may produce unreliable results. Past performance does not guarantee future results."
                } if include_metadata else None
            }
            
            if not include_metadata:
                output = {"games": results}
                
            return json.dumps(output, indent=2)
            
        except Exception as e:
            logger.error(f"Error generating JSON output: {str(e)}")
            return json.dumps({"error": "Failed to generate output", "message": str(e)})

def run_analysis():
    """Run analysis function - separates logic from main() for flask integration"""
    try:
        target_week = os.getenv('TARGET_WEEK')
        
        calculator = NFLTDBoostCalculator()
        
        week_num = int(target_week) if target_week else None
        results = calculator.analyze_week_matchups(week_num)
        
        if not results:
            logger.error("No valid games found")
            return None
        
        return {
            'results': results,
            'calculator': calculator,
            'week_num': week_num or calculator.get_current_week()
        }
        
    except Exception as e:
        logger.error(f"Analysis execution failed: {str(e)}")
        return None

def main():
    """Main function for command-line execution"""
    analysis_data = run_analysis()
    
    if not analysis_data:
        sys.exit(1)
    
    results = analysis_data['results']
    calculator = analysis_data['calculator']
    current_week = analysis_data['week_num']
    
    json_output = calculator.generate_json_output(results)
    print(json_output)
    
    print(f"\n=== WEEK {current_week} NFL TD BOOST ANALYSIS ===", file=sys.stderr)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
    print("="*50, file=sys.stderr)
    
    if isinstance(results, dict) and 'games' in results:
        for game in results['games'][:5]:  # Top 5 games
            print(f"\n{game['game']} ({game['gameday']})", file=sys.stderr)
            
            away_adv = game['away_offense_vs_home_defense']['combined_team_analysis'].get('total_team_td_advantage_pct')
            home_adv = game['home_offense_vs_away_defense']['combined_team_analysis'].get('total_team_td_advantage_pct')
            
            if away_adv is not None:
                print(f"  {game['away_team']} offense: {away_adv:+.1f}% total TD advantage", file=sys.stderr)
            if home_adv is not None:
                print(f"  {game['home_team']} offense: {home_adv:+.1f}% total TD advantage", file=sys.stderr)
    
    return results

# Flask Integration - exactly like your working blueprint
try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app)
    
    @app.route('/dashboard')
    def dashboard():
        """Serve the premium NFL TD boost dashboard"""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NFL TD Boost Dashboard</title>
    <style>
        .webflow-betting-embed {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(180deg, #334155 0%, #1f2937 15%, #1f2937 100%);
            color: #ffffff;
            min-height: 100vh;
            margin: 0;
            padding: 0;
        }

        .component-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }

        .component-header {
            text-align: center;
            margin-bottom: 4rem;
            padding: 2rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .component-title {
            font-size: clamp(2rem, 5vw, 4rem);
            font-weight: 800;
            background: linear-gradient(135deg, #9ca3af, #ffffff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.02em;
            line-height: 1.1;
            margin-bottom: 1rem;
        }

        .component-subtitle {
            font-size: 0.875rem;
            font-weight: 600;
            color: #60a5fa;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 1rem;
        }

        .refresh-section {
            display: flex;
            justify-content: center;
            margin-bottom: 3rem;
        }

        .refresh-btn {
            background: linear-gradient(135deg, #1e3a8a, #60a5fa);
            color: #ffffff;
            border: none;
            padding: 1rem 2rem;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .loading-state, .error-state {
            text-align: center;
            padding: 3rem;
            font-size: 1.125rem;
            color: #d1d5db;
        }

        .error-state {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px;
            color: #fca5a5;
            margin-bottom: 2rem;
        }

        .component-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
            gap: 3rem;
            margin-bottom: 4rem;
        }

        .component-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 3rem;
            transition: all 0.3s ease;
        }

        .game-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .game-title {
            font-size: 1.75rem;
            font-weight: 700;
            color: #ffffff;
        }

        .game-date {
            color: #9ca3af;
            font-size: 0.875rem;
        }
    </style>
</head>
<body>
    <div class="webflow-betting-embed">
        <div class="component-container">
            <div class="component-header">
                <h1 class="component-title">NFL TD Boost</h1>
                <p class="component-subtitle">Touchdown Advantage Analysis</p>
            </div>

            <div class="refresh-section">
                <button class="refresh-btn" onclick="loadData()">Refresh Analysis</button>
            </div>

            <div id="loading" class="loading-state">Loading NFL TD boost analysis...</div>
            <div id="error" class="error-state" style="display: none;"></div>
            <div id="content"></div>
        </div>
    </div>

    <script>
        async function loadData() {
            const loadingEl = document.getElementById('loading');
            const errorEl = document.getElementById('error');
            const contentEl = document.getElementById('content');
            
            loadingEl.style.display = 'block';
            errorEl.style.display = 'none';
            contentEl.innerHTML = '';
            
            try {
                const response = await fetch('/analyze');
                const data = await response.json();
                
                if (data.games && data.games.games && data.games.games.length > 0) {
                    const games = data.games.games;
                    const gamesHtml = games.map(game => 
                        `<div class="component-card">
                            <div class="game-header">
                                <div class="game-title">${game.game}</div>
                                <div class="game-date">${new Date(game.gameday).toLocaleDateString('en-US', { 
                                    weekday: 'short', 
                                    month: 'short', 
                                    day: 'numeric' 
                                })}</div>
                            </div>
                        </div>`
                    ).join('');
                    
                    contentEl.innerHTML = `<div class="component-grid">${gamesHtml}</div>`;
                } else {
                    contentEl.innerHTML = '<div class="error-state">No game analysis available</div>';
                }
                
                loadingEl.style.display = 'none';
                
            } catch (error) {
                errorEl.textContent = `Analysis temporarily unavailable: ${error.message}`;
                errorEl.style.display = 'block';
                loadingEl.style.display = 'none';
            }
        }
        
        window.loadData = loadData;
        document.addEventListener('DOMContentLoaded', loadData);
    </script>
</body>
</html>'''
    
    @app.route('/analyze', methods=['GET'])
    def analyze():
        """Main endpoint to analyze current week's NFL TD boost matchups"""
        try:
            target_week = request.args.get('week')
            
            original_env = {}
            env_vars = {}
            if target_week:
                env_vars['TARGET_WEEK'] = target_week
            
            for key, value in env_vars.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
            
            try:
                analysis_data = run_analysis()
                
                if not analysis_data:
                    return jsonify({
                        "error": "Analysis failed",
                        "message": "Could not complete analysis",
                        "timestamp": datetime.now().isoformat()
                    }), 500
                
                results = analysis_data['results']
                calculator = analysis_data['calculator']
                json_output = calculator.generate_json_output(results)
                
                return jsonify(json.loads(json_output))
                
            finally:
                for key, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = original_value
        
        except Exception as e:
            logger.error(f"Error in Flask endpoint: {str(e)}")
            return jsonify({
                "error": "Unexpected error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "NFL TD Boost Calculator"
        })
    
    @app.route('/', methods=['GET'])
    def root():
        """Root endpoint with API documentation"""
        return jsonify({
            "service": "NFL TD Boost Calculator API",
            "version": "1.0",
            "endpoints": {
                "/dashboard": {
                    "method": "GET",
                    "description": "Premium NFL TD boost dashboard"
                },
                "/analyze": {
                    "method": "GET",
                    "description": "Analyze current week's NFL TD boost matchups"
                },
                "/health": {
                    "method": "GET", 
                    "description": "Health check endpoint"
                }
            },
            "timestamp": datetime.now().isoformat()
        })
    
    def run_flask_app():
        """Run Flask application"""
        port = int(os.environ.get('PORT', 10000))
        debug = os.environ.get('DEBUG', 'False').lower() == 'true'
        
        logger.info(f"Starting NFL TD Boost Calculator API on port {port}")
        app.run(host='0.0.0.0', port=port, debug=debug)

except ImportError:
    logger.info("Flask not available - running in CLI mode only")
    app = None
    def run_flask_app():
        logger.error("Flask not installed. Install with: pip install flask")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--flask':
        if app is not None:
            run_flask_app()
        else:
            logger.error("Flask not available. Install with: pip install flask")
            sys.exit(1)
    else:
        main()
