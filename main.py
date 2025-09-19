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
    def __init__(self, performance_year=2025):
        """
        Initialize TD Boost Calculator with the same pattern as working tools
        """
        # Explicitly prevent 2024 data usage for performance year
        if performance_year == 2024:
            raise ValueError("2024 data is not allowed as performance year - this tool only works with 2025+ data")
        
        self.performance_year = performance_year
        self.baselines_2024 = {}
        self.current_data = {}
        self.schedule_data = None
        self.league_averages = {}
        self.data_loaded = False
        
        try:
            logger.info(f"Successfully initialized TD boost calculator: {performance_year} analysis")
        except Exception as e:
            logger.error(f"Failed to initialize calculator: {str(e)}")
            self.data_loaded = False
    
    def load_data(self):
        """Load NFL data with error handling"""
        try:
            # Double-check we're not using 2024 as performance year
            if self.performance_year == 2024:
                raise ValueError("2024 data is explicitly blocked as performance year - this tool only works with 2025+ data")
            
            logger.info(f"Loading NFL data for TD boost analysis...")
            self.calculate_league_averages()
            
            # Load 2024 baseline data
            logger.info("Loading 2024 baseline data...")
            df_2024 = nfl.import_pbp_data([2024])
            if df_2024.empty:
                raise ValueError("No 2024 baseline data available")
            
            off_rz_2024, def_rz_2024 = self.calculate_rz_stats_with_filter(df_2024, "2024")
            off_all_2024, def_all_2024 = self.calculate_all_drives_stats(df_2024, "2024")
            
            self.baselines_2024 = {
                'offense_rz': off_rz_2024,
                'defense_rz': def_rz_2024,
                'offense_all': off_all_2024,
                'defense_all': def_all_2024
            }
            
            # Load current year data
            logger.info(f"Loading {self.performance_year} current data...")
            df_current = nfl.import_pbp_data([self.performance_year])
            if df_current.empty:
                raise ValueError(f"No data available for {self.performance_year}")
            
            off_rz_current, def_rz_current = self.calculate_rz_stats_with_filter(df_current, str(self.performance_year))
            off_all_current, def_all_current = self.calculate_all_drives_stats(df_current, str(self.performance_year))
            
            self.current_data = {
                'offense_rz': off_rz_current,
                'defense_rz': def_rz_current,
                'offense_all': off_all_current,
                'defense_all': def_all_current
            }
            
            # Load schedule
            self.load_schedule()
            
            logger.info(f"Data loaded successfully for TD boost analysis")
            
        except Exception as e:
            logger.error(f"Failed to load data: {str(e)}")
            raise
    
    def calculate_league_averages(self):
        """Calculate 2024 league-wide averages for boost comparisons"""
        try:
            logger.info("Calculating 2024 league averages...")
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
            
            logger.info(f"League averages calculated successfully")
            
        except Exception as e:
            logger.error(f"Error calculating league averages: {str(e)}")
            raise
    
    def calculate_rz_stats_with_filter(self, df, year_label=""):
        """Calculate red zone stats with 2+ plays filter for consistent methodology"""
        try:
            logger.info(f"Calculating {year_label} red zone stats with 2+ plays filter...")
            
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
            
        except Exception as e:
            logger.error(f"Error calculating RZ stats for {year_label}: {str(e)}")
            return {}, {}
    
    def calculate_all_drives_stats(self, df, year_label=""):
        """Calculate all drives TD stats"""
        try:
            logger.info(f"Calculating {year_label} all drives stats...")
            
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
            
        except Exception as e:
            logger.error(f"Error calculating all drives stats for {year_label}: {str(e)}")
            return {}, {}
    
    def load_schedule(self):
        """Load NFL schedule data"""
        try:
            logger.info("Loading NFL schedule...")
            self.schedule_data = nfl.import_schedules([self.performance_year])
            
            if self.schedule_data.empty:
                logger.warning(f"No schedule data available for {self.performance_year}")
                return False
            
            # Convert game_id to ensure proper formatting
            self.schedule_data['gameday'] = pd.to_datetime(self.schedule_data['gameday'])
            logger.info(f"Schedule loaded: {len(self.schedule_data)} games")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load schedule: {str(e)}")
            self.schedule_data = None
            return False
    
    def get_current_week(self):
        """Determine current NFL week based on date and available data"""
        try:
            # Get current play-by-play data to see what's been completed
            df_current = nfl.import_pbp_data([self.performance_year])
            if not df_current.empty:
                max_completed_week = df_current['week'].max()
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
                    logger.info(f"Current week determined: {next_week} (max completed: {max_completed_week})")
                    return int(next_week)
            
            # Fallback to max completed week + 1
            return int(max_completed_week) + 1
                
        except Exception as e:
            logger.error(f"Could not determine current week: {str(e)}")
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
                logger.warning(f"No games found for week {week_num}")
                return []
            
            matchups = []
            for _, game in week_games.iterrows():
                matchups.append({
                    'away_team': game['away_team'],
                    'home_team': game['home_team'],
                    'gameday': game['gameday'].strftime('%Y-%m-%d') if pd.notna(game['gameday']) else 'TBD',
                    'week': int(game['week'])
                })
            
            logger.info(f"Found {len(matchups)} games for week {week_num}")
            return matchups
            
        except Exception as e:
            logger.error(f"Error getting week {week_num} matchups: {str(e)}")
            return []
    
    def calculate_matchup_boosts(self, offense_team, defense_team):
        """Calculate TD boost for a specific matchup with percentage changes and detailed labels"""
        try:
            if not self.data_loaded:
                self.load_data()
                self.data_loaded = True
            
            results = {
                'matchup': f"{offense_team} vs {defense_team}",
                'offense_team': offense_team,
                'defense_team': defense_team,
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Red Zone Analysis - Percentage changes vs league averages
            rz_analysis = {}
            
            # Offense RZ performance vs league average (percentage change)
            if offense_team in self.current_data['offense_rz']:
                current_off_rz = self.current_data['offense_rz'][offense_team]['rz_td_rate']
                league_avg_rz_scoring = self.league_averages['rz_scoring']
                pct_change = ((current_off_rz - league_avg_rz_scoring) / league_avg_rz_scoring * 100) if league_avg_rz_scoring > 0 else 0
                rz_analysis['offense_rz_pct_change_vs_league'] = round(pct_change, 1)
                rz_analysis['offense_current_rz_td_rate'] = current_off_rz
                rz_analysis['league_2024_rz_scoring_avg'] = league_avg_rz_scoring
            else:
                rz_analysis['offense_rz_pct_change_vs_league'] = None
                rz_analysis['note'] = f"Insufficient {offense_team} RZ data"
            
            # Defense RZ performance vs league average (percentage change)
            if defense_team in self.current_data['defense_rz']:
                current_def_rz = self.current_data['defense_rz'][defense_team]['rz_td_allow_rate']
                league_avg_rz_allow = self.league_averages['rz_allow']
                pct_change = ((current_def_rz - league_avg_rz_allow) / league_avg_rz_allow * 100) if league_avg_rz_allow > 0 else 0
                rz_analysis['defense_rz_pct_change_vs_league'] = round(pct_change, 1)
                rz_analysis['defense_current_rz_allow_rate'] = current_def_rz
                rz_analysis['league_2024_rz_allow_avg'] = league_avg_rz_allow
            else:
                rz_analysis['defense_rz_pct_change_vs_league'] = None
            
            results['red_zone'] = rz_analysis
            
            # All Drives Analysis - Percentage changes vs league averages
            all_drives_analysis = {}
            
            # Offense all drives performance vs league average (percentage change)
            if offense_team in self.current_data['offense_all']:
                current_off_all = self.current_data['offense_all'][offense_team]['total_td_rate']
                league_avg_all_scoring = self.league_averages['all_drives_scoring']
                pct_change = ((current_off_all - league_avg_all_scoring) / league_avg_all_scoring * 100) if league_avg_all_scoring > 0 else 0
                all_drives_analysis['offense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
                all_drives_analysis['offense_current_all_drives_td_rate'] = current_off_all
                all_drives_analysis['league_2024_all_drives_scoring_avg'] = league_avg_all_scoring
            else:
                all_drives_analysis['offense_all_drives_pct_change_vs_league'] = None
            
            # Defense all drives performance vs league average (percentage change)
            if defense_team in self.current_data['defense_all']:
                current_def_all = self.current_data['defense_all'][defense_team]['total_td_allow_rate']
                league_avg_all_allow = self.league_averages['all_drives_allow']
                pct_change = ((current_def_all - league_avg_all_allow) / league_avg_all_allow * 100) if league_avg_all_allow > 0 else 0
                all_drives_analysis['defense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
                all_drives_analysis['defense_current_all_drives_allow_rate'] = current_def_all
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
            
        except Exception as e:
            logger.error(f"Error calculating matchup boosts for {offense_team} vs {defense_team}: {str(e)}")
            return {
                'matchup': f"{offense_team} vs {defense_team}",
                'error': f"Analysis failed: {str(e)}",
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def analyze_week_matchups(self, week_num=None):
        """Analyze all matchups for a specific week"""
        try:
            if not self.data_loaded:
                self.load_data()
                self.data_loaded = True
            
            # Get current week matchups
            matchups = self.get_week_matchups(week_num)
            if not matchups:
                return {"error": "No matchups found", "week": week_num or self.get_current_week()}
            
            results = {
                'week': week_num or self.get_current_week(),
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance_year': self.performance_year,
                'methodology': {
                    'rz_td_rate': 'Team RZ touchdown rate with 2+ plays filter, excluding 2-pt conversions',
                    'all_drives_td_rate': 'Team touchdown rate on all drives',
                    'calculation': 'Percentage changes vs 2024 league averages, combined offense and defense analysis'
                },
                'games': []
            }
            
            logger.info(f"Analyzing {len(matchups)} games for week {results['week']}...")
            
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
                    logger.error(f"Error analyzing {away_team} @ {home_team}: {str(e)}")
                    continue
            
            # Sort by highest total team advantages
            def get_sort_key(game):
                away_adv = game['away_offense_vs_home_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                home_adv = game['home_offense_vs_away_defense'].get('combined_team_analysis', {}).get('total_team_td_advantage_pct', -999)
                return max(away_adv or -999, home_adv or -999)
            
            results['games'].sort(key=get_sort_key, reverse=True)
            
            logger.info(f"Week {results['week']} analysis complete!")
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing week matchups: {str(e)}")
            return {"error": f"Week analysis failed: {str(e)}", "week": week_num}
    
    def get_team_summary(self, team):
        """Get a team's current vs 2024 performance summary"""
        try:
            if not self.data_loaded:
                self.load_data()
                self.data_loaded = True
            
            summary = {
                'team': team,
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance_year': self.performance_year
            }
            
            # Offensive performance
            offense = {}
            if team in self.current_data['offense_rz'] and team in self.baselines_2024['offense_rz']:
                current_rz = self.current_data['offense_rz'][team]['rz_td_rate']
                baseline_rz = self.baselines_2024['offense_rz'][team]['rz_td_rate']
                offense['rz_improvement'] = round(current_rz - baseline_rz, 1)
                offense[f'rz_{self.performance_year}'] = current_rz
                offense['rz_2024'] = baseline_rz
            
            if team in self.current_data['offense_all'] and team in self.baselines_2024['offense_all']:
                current_all = self.current_data['offense_all'][team]['total_td_rate']
                baseline_all = self.baselines_2024['offense_all'][team]['total_td_rate']
                offense['all_drives_improvement'] = round(current_all - baseline_all, 1)
                offense[f'all_drives_{self.performance_year}'] = current_all
                offense['all_drives_2024'] = baseline_all
            
            summary['offense'] = offense
            
            # Defensive performance
            defense = {}
            if team in self.current_data['defense_rz'] and team in self.baselines_2024['defense_rz']:
                current_rz = self.current_data['defense_rz'][team]['rz_td_allow_rate']
                baseline_rz = self.baselines_2024['defense_rz'][team]['rz_td_allow_rate']
                defense['rz_change'] = round(current_rz - baseline_rz, 1)
                defense[f'rz_{self.performance_year}'] = current_rz
                defense['rz_2024'] = baseline_rz
            
            if team in self.current_data['defense_all'] and team in self.baselines_2024['defense_all']:
                current_all = self.current_data['defense_all'][team]['total_td_allow_rate']
                baseline_all = self.baselines_2024['defense_all'][team]['total_td_allow_rate']
                defense['all_drives_change'] = round(current_all - baseline_all, 1)
                defense[f'all_drives_{self.performance_year}'] = current_all
                defense['all_drives_2024'] = baseline_all
            
            summary['defense'] = defense
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting team summary for {team}: {str(e)}")
            return {
                'team': team,
                'error': f"Summary failed: {str(e)}",
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def generate_json_output(self, results, include_metadata=True):
        """Generate JSON output for API consumption"""
        try:
            output = {
                "results": results,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "performance_year": self.performance_year,
                    "data_loaded": self.data_loaded,
                    "disclaimer": "For educational analysis only. TD boost calculated with 2+ plays filter for red zone drives."
                } if include_metadata else None
            }
            
            if not include_metadata:
                output = {"results": results}
                
            return json.dumps(output, indent=2)
            
        except Exception as e:
            logger.error(f"Error generating JSON output: {str(e)}")
            return json.dumps({"error": "Failed to generate output", "message": str(e)})

def run_analysis():
    """Run analysis function - separates logic from main() for flask integration"""
    try:
        # Configuration - can be set via environment variables
        performance_year = int(os.getenv('PERFORMANCE_YEAR', 2025))
        target_week = os.getenv('TARGET_WEEK')  # Optional specific week
        target_team = os.getenv('TARGET_TEAM')  # Optional specific team
        analysis_type = os.getenv('ANALYSIS_TYPE', 'week')  # week, team, or matchup
        
        calculator = NFLTDBoostCalculator(performance_year=performance_year)
        
        if not calculator.data_loaded:
            logger.error("Failed to load data")
            return None
        
        # Analyze based on type
        if analysis_type == 'team' and target_team:
            results = calculator.get_team_summary(target_team.upper())
        elif analysis_type == 'week':
            week_num = int(target_week) if target_week else None
            results = calculator.analyze_week_matchups(week_num)
        else:
            # Default to current week analysis
            results = calculator.analyze_week_matchups()
        
        if not results:
            logger.error("No valid results found")
            return None
        
        return {
            'results': results,
            'calculator': calculator
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
    
    # Output JSON for API consumption
    json_output = calculator.generate_json_output(results)
    print(json_output)
    
    # Human-readable summary to stderr for logging
    print(f"\n=== NFL TD BOOST ANALYSIS ===", file=sys.stderr)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
    print("="*50, file=sys.stderr)
    
    return results

# Flask Integration
try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    
    @app.route('/td-boost', methods=['GET'])
    def get_td_boost():
        """Get TD boost analysis for all games or specific parameters"""
        try:
            week = request.args.get('week')
            team = request.args.get('team')
            performance_year = request.args.get('performance_year', '2025')
            analysis_type = request.args.get('type', 'week')
            
            # Set environment variables temporarily
            original_env = {}
            env_vars = {
                'PERFORMANCE_YEAR': performance_year,
                'ANALYSIS_TYPE': analysis_type
            }
            if week:
                env_vars['TARGET_WEEK'] = week
            if team:
                env_vars['TARGET_TEAM'] = team.upper()
            
            # Store original values and set new ones
            for key, value in env_vars.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
            
            try:
                # Run analysis
                analysis_data = run_analysis()
                
                if not analysis_data:
                    return jsonify({
                        "error": "Analysis failed",
                        "message": "Could not complete TD boost analysis",
                        "timestamp": datetime.now().isoformat()
                    }), 500
                
                # Return results
                results = analysis_data['results']
                return jsonify(results)
                
            finally:
                # Restore original environment variables
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
    
    @app.route('/td-boost/week/<int:week_num>', methods=['GET'])
    def get_week_td_boost(week_num):
        """Get TD boost analysis for a specific week"""
        try:
            performance_year = request.args.get('performance_year', '2025')
            
            # Set environment variables temporarily
            original_env = {}
            env_vars = {
                'PERFORMANCE_YEAR': performance_year,
                'TARGET_WEEK': str(week_num),
                'ANALYSIS_TYPE': 'week'
            }
            
            # Store original values and set new ones
            for key, value in env_vars.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
            
            try:
                # Run analysis
                analysis_data = run_analysis()
                
                if not analysis_data:
                    return jsonify({
                        "error": "Analysis failed",
                        "message": f"Could not analyze week {week_num}",
                        "timestamp": datetime.now().isoformat()
                    }), 500
                
                # Return results
                results = analysis_data['results']
                return jsonify(results)
                
            finally:
                # Restore original environment variables
                for key, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = original_value
        
        except Exception as e:
            logger.error(f"Error in week Flask endpoint: {str(e)}")
            return jsonify({
                "error": "Unexpected error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
    
    @app.route('/td-boost/team/<team>', methods=['GET'])
    def get_team_td_boost(team):
        """Get TD boost team summary"""
        try:
            performance_year = request.args.get('performance_year', '2025')
            
            # Set environment variables temporarily
            original_env = {}
            env_vars = {
                'PERFORMANCE_YEAR': performance_year,
                'TARGET_TEAM': team.upper(),
                'ANALYSIS_TYPE': 'team'
            }
            
            # Store original values and set new ones
            for key, value in env_vars.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value
            
            try:
                # Run analysis
                analysis_data = run_analysis()
                
                if not analysis_data:
                    return jsonify({
                        "error": "Analysis failed",
                        "message": f"Could not analyze team {team}",
                        "timestamp": datetime.now().isoformat()
                    }), 500
                
                # Return results
                results = analysis_data['results']
                return jsonify(results)
                
            finally:
                # Restore original environment variables
                for key, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = original_value
        
        except Exception as e:
            logger.error(f"Error in team Flask endpoint: {str(e)}")
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
                "/td-boost": {
                    "method": "GET",
                    "description": "Get TD boost analysis",
                    "parameters": {
                        "week": "Optional - analyze specific week (e.g., ?week=3)",
                        "team": "Optional - get team summary (e.g., ?team=KC&type=team)",
                        "type": "Analysis type: 'week' or 'team' (default: week)",
                        "performance_year": "Year to analyze (default: 2025)"
                    },
                    "example": "/td-boost?week=3&performance_year=2025"
                },
                "/td-boost/week/<week_num>": {
                    "method": "GET",
                    "description": "Get TD boost analysis for specific week",
                    "parameters": {
                        "performance_year": "Year to analyze (default: 2025)"
                    },
                    "example": "/td-boost/week/3?performance_year=2025"
                },
                "/td-boost/team/<team>": {
                    "method": "GET",
                    "description": "Get team TD performance summary",
                    "parameters": {
                        "performance_year": "Year to analyze (default: 2025)"
                    },
                    "example": "/td-boost/team/KC?performance_year=2025"
                },
                "/health": {
                    "method": "GET", 
                    "description": "Health check endpoint"
                }
            },
            "methodology": {
                "rz_td_rate": "Team RZ touchdown rate with 2+ plays filter, no 2-pt conversions",
                "all_drives_td_rate": "Team touchdown rate on all drives",
                "boost_calculation": "Percentage changes vs 2024 league averages, combined offense and defense analysis",
                "notes": "Uses 2024 baseline data for comparison with current year performance"
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
    # Check if Flask mode is requested
    if len(sys.argv) > 1 and sys.argv[1] == '--flask':
        if app is not None:
            run_flask_app()
        else:
            logger.error("Flask not available. Install with: pip install flask")
            sys.exit(1)
    else:
        main()
