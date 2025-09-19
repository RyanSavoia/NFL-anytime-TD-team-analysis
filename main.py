# Add these missing functions to your code:

import time

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

# Also fix your load_data method in NFLTDBoostCalculator class:
def load_data(self):
    """Load only 2025 current data - use hardcoded 2024 baselines"""
    try:
        # Use hardcoded league averages (no 2024 data loading needed)
        self.calculate_league_averages()
        
        # Only load 2025 current data (much faster)
        print("Loading 2025 current data...")
        start_time = time.time()
        
        def load_2025_data():
            try:
                df = nfl.import_pbp_data([2025])
                print(f"Loaded 2025 data: {len(df)} plays")
                if not df.empty:
                    print(f"Teams in 2025 data: {sorted(df['posteam'].dropna().unique())}")
                return df
            except Exception as e:
                print(f"Error loading 2025 NFL data: {str(e)}")
                return pd.DataFrame()
        
        df_2025 = timed_operation("2025 NFL data download", load_2025_data)
        
        # **CRITICAL FIX: Check if we actually have data**
        if df_2025.empty:
            print("ERROR: No 2025 data available!")
            self.current_2025 = {
                'offense_rz': {},
                'defense_rz': {},
                'offense_all': {},
                'defense_all': {}
            }
        else:
            print(f"2025 data loaded successfully: {len(df_2025)} plays")
            
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
            
            # **DEBUG: Print what we actually loaded**
            print(f"Offense RZ teams: {list(off_rz_2025.keys())}")
            print(f"Defense RZ teams: {list(def_rz_2025.keys())}")
            print(f"Offense All teams: {list(off_all_2025.keys())}")
            print(f"Defense All teams: {list(def_all_2025.keys())}")
        
        # Load schedule
        def load_sched():
            return self.load_schedule()
        
        timed_operation("Schedule data loading", load_sched)
        
        print(f"Total 2025 data loading completed in {time.time() - start_time:.2f} seconds")
        print("Data loading complete!")
        
    except Exception as e:
        print(f"Error loading data: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

# And fix the calculate_matchup_boosts method to have proper defensive inversion:
def calculate_matchup_boosts(self, offense_team, defense_team):
    """Calculate TD boost for a specific matchup with percentage changes and detailed labels"""
    if not hasattr(self, 'current_2025') or not self.current_2025:
        print("Loading data because current_2025 not found...")
        self.load_data()
    
    results = {
        'matchup': f"{offense_team} vs {defense_team}",
        'offense_team': offense_team,
        'defense_team': defense_team,
        'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # **DEBUG: Check what teams we have data for**
    print(f"Checking {offense_team} vs {defense_team}")
    print(f"Available offense RZ teams: {list(self.current_2025.get('offense_rz', {}).keys())}")
    print(f"Available defense RZ teams: {list(self.current_2025.get('defense_rz', {}).keys())}")
    
    # Red Zone Analysis - Percentage changes vs league averages
    rz_analysis = {}
    
    # Offense RZ performance vs league average (percentage change)
    if offense_team in self.current_2025.get('offense_rz', {}):
        current_off_rz = self.current_2025['offense_rz'][offense_team]['rz_td_rate']
        league_avg_rz_scoring = self.league_averages['rz_scoring']
        pct_change = ((current_off_rz - league_avg_rz_scoring) / league_avg_rz_scoring * 100) if league_avg_rz_scoring > 0 else 0
        rz_analysis['offense_rz_pct_change_vs_league'] = round(pct_change, 1)
        rz_analysis['offense_2025_rz_td_rate'] = current_off_rz
        rz_analysis['league_2024_rz_scoring_avg'] = league_avg_rz_scoring
        print(f"  {offense_team} RZ offense: {current_off_rz}% (league: {league_avg_rz_scoring}%) = {pct_change:.1f}% change")
    else:
        rz_analysis['offense_rz_pct_change_vs_league'] = None
        rz_analysis['note'] = f"No {offense_team} RZ offense data found"
        print(f"  {offense_team}: NO RZ OFFENSE DATA")
    
    # Defense RZ performance vs league average (percentage change)
    if defense_team in self.current_2025.get('defense_rz', {}):
        current_def_rz = self.current_2025['defense_rz'][defense_team]['rz_td_allow_rate']
        league_avg_rz_allow = self.league_averages['rz_allow']
        pct_change = ((current_def_rz - league_avg_rz_allow) / league_avg_rz_allow * 100) if league_avg_rz_allow > 0 else 0
        rz_analysis['defense_rz_pct_change_vs_league'] = round(pct_change, 1)
        rz_analysis['defense_2025_rz_allow_rate'] = current_def_rz
        rz_analysis['league_2024_rz_allow_avg'] = league_avg_rz_allow
        print(f"  {defense_team} RZ defense: {current_def_rz}% (league: {league_avg_rz_allow}%) = {pct_change:.1f}% change")
    else:
        rz_analysis['defense_rz_pct_change_vs_league'] = None
        print(f"  {defense_team}: NO RZ DEFENSE DATA")
    
    results['red_zone'] = rz_analysis
    
    # All Drives Analysis - Percentage changes vs league averages
    all_drives_analysis = {}
    
    # Offense all drives performance vs league average (percentage change)
    if offense_team in self.current_2025.get('offense_all', {}):
        current_off_all = self.current_2025['offense_all'][offense_team]['total_td_rate']
        league_avg_all_scoring = self.league_averages['all_drives_scoring']
        pct_change = ((current_off_all - league_avg_all_scoring) / league_avg_all_scoring * 100) if league_avg_all_scoring > 0 else 0
        all_drives_analysis['offense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
        all_drives_analysis['offense_2025_all_drives_td_rate'] = current_off_all
        all_drives_analysis['league_2024_all_drives_scoring_avg'] = league_avg_all_scoring
        print(f"  {offense_team} All drives offense: {current_off_all}% (league: {league_avg_all_scoring}%) = {pct_change:.1f}% change")
    else:
        all_drives_analysis['offense_all_drives_pct_change_vs_league'] = None
        print(f"  {offense_team}: NO ALL DRIVES OFFENSE DATA")
    
    # Defense all drives performance vs league average (percentage change)
    if defense_team in self.current_2025.get('defense_all', {}):
        current_def_all = self.current_2025['defense_all'][defense_team]['total_td_allow_rate']
        league_avg_all_allow = self.league_averages['all_drives_allow']
        pct_change = ((current_def_all - league_avg_all_allow) / league_avg_all_allow * 100) if league_avg_all_allow > 0 else 0
        all_drives_analysis['defense_all_drives_pct_change_vs_league'] = round(pct_change, 1)
        all_drives_analysis['defense_2025_all_drives_allow_rate'] = current_def_all
        all_drives_analysis['league_2024_all_drives_allow_avg'] = league_avg_all_allow
        print(f"  {defense_team} All drives defense: {current_def_all}% (league: {league_avg_all_allow}%) = {pct_change:.1f}% change")
    else:
        all_drives_analysis['defense_all_drives_pct_change_vs_league'] = None
        print(f"  {defense_team}: NO ALL DRIVES DEFENSE DATA")
    
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
    
    # **FIXED: Combined defense percentage change (INVERTED - worse defense helps offense)**
    def_rz_pct = rz_analysis.get('defense_rz_pct_change_vs_league')
    def_all_pct = all_drives_analysis.get('defense_all_drives_pct_change_vs_league')
    
    if def_rz_pct is not None and def_all_pct is not None:
        combined_analysis['defense_combined_pct_change'] = round(-(def_rz_pct + def_all_pct) / 2, 1)  # INVERTED
    elif def_rz_pct is not None:
        combined_analysis['defense_combined_pct_change'] = round(-def_rz_pct, 1)  # INVERTED
    elif def_all_pct is not None:
        combined_analysis['defense_combined_pct_change'] = round(-def_all_pct, 1)  # INVERTED
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
        combined_analysis['total_team_td_advantage_pct'] = 0  # Default to 0 instead of None
    
    print(f"  FINAL CALCULATION: off_combined={off_combined}, def_combined={def_combined}, total={combined_analysis['total_team_td_advantage_pct']}")
    
    # Add explanations
    combined_analysis['explanation'] = {
        'offense_combined': f"Average of {offense_team} RZ and all-drives TD rate % change vs 2024 league averages",
        'defense_combined': f"INVERTED average of {defense_team} RZ and all-drives TD allow rate % change (worse defense helps offense)", 
        'total_advantage': f"Overall team TD scoring advantage: average of offense boost and defense vulnerability",
        'calculation_note': "All red zone stats use 2+ plays filter. Defense stats are inverted (higher allow rate = advantage for offense)."
    }
    
    results['combined_team_analysis'] = combined_analysis
    
    return results
