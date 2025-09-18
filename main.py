from flask import Flask, jsonify, request
import nfl_data_py as nfl
import pandas as pd
import json
import time
from datetime import datetime

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

class PlayerUsageService:
    def __init__(self):
        """Service to calculate player red zone usage and TD shares"""
        self.pbp_data = None
        self.data_loaded = False
        
    def load_nfl_data(self):
        """Load current NFL play-by-play data"""
        if not self.data_loaded:
            def load_data():
                try:
                    return nfl.import_pbp_data([2025])
                except Exception as e:
                    print(f"Error loading NFL data: {str(e)}")
                    return pd.DataFrame()
            
            self.pbp_data = timed_operation("2025 NFL play-by-play data loading", load_data)
            self.data_loaded = True
            print(f"Loaded {len(self.pbp_data)} total plays")
    
    def get_player_rz_usage_share(self, team):
        """
        Get player red zone usage shares with 2+ plays filter and no 2-pt conversions
        Following GPT's exact specifications
        """
        self.load_nfl_data()
        
        # Filter for red zone plays, excluding 2-point conversions
        rz_data = self.pbp_data[
            (self.pbp_data['posteam'] == team) & 
            (self.pbp_data['yardline_100'] <= 20) & 
            ((self.pbp_data['rush'] == 1) | (self.pbp_data['pass'] == 1)) &
            (self.pbp_data['two_point_attempt'] != 1)  # Exclude 2-pt attempts
        ].copy()
        
        if rz_data.empty:
            return {}
        
        # Apply 2+ plays filter per drive (GPT's requirement)
        filtered_plays = []
        for game_id in rz_data['game_id'].unique():
            game_data = rz_data[rz_data['game_id'] == game_id]
            for drive_id in game_data['fixed_drive'].unique():
                drive_plays = game_data[game_data['fixed_drive'] == drive_id]
                if len(drive_plays) >= 2:  # 2+ plays filter
                    filtered_plays.append(drive_plays)
        
        if not filtered_plays:
            return {}
        
        rz_filtered = pd.concat(filtered_plays, ignore_index=True)
        total_rz_plays = len(rz_filtered)
        usage_shares = {}
        
        # Accumulate rushing usage by player_id then add names (GPT's approach)
        rush_data = rz_filtered[rz_filtered['rush'] == 1]
        if not rush_data.empty:
            rush_counts = rush_data['rusher_player_id'].value_counts()
            for player_id, count in rush_counts.items():
                if pd.notna(player_id):
                    share = count / total_rz_plays
                    # Get player name
                    player_name_series = rush_data[rush_data['rusher_player_id'] == player_id]['rusher_player_name']
                    if not player_name_series.empty:
                        player_name = player_name_series.iloc[0]
                        if pd.notna(player_name):
                            if player_name in usage_shares:
                                usage_shares[player_name] += share
                            else:
                                usage_shares[player_name] = share
        
        # Accumulate receiving usage by player_id then add names
        pass_data = rz_filtered[rz_filtered['pass'] == 1]
        if not pass_data.empty:
            target_counts = pass_data['receiver_player_id'].value_counts()
            for player_id, count in target_counts.items():
                if pd.notna(player_id):
                    share = count / total_rz_plays
                    # Get player name
                    player_name_series = pass_data[pass_data['receiver_player_id'] == player_id]['receiver_player_name']
                    if not player_name_series.empty:
                        player_name = player_name_series.iloc[0]
                        if pd.notna(player_name):
                            if player_name in usage_shares:
                                usage_shares[player_name] += share
                            else:
                                usage_shares[player_name] = share
        
        return usage_shares
    
    def get_player_td_share(self, team):
        """Get player TD shares (accumulating rush + receiving TDs)"""
        self.load_nfl_data()
        
        td_data = self.pbp_data[
            (self.pbp_data['posteam'] == team) & 
            (self.pbp_data['touchdown'] == 1)
        ].copy()
        
        if td_data.empty:
            return {}
        
        total_tds = len(td_data)
        td_shares = {}
        
        # Accumulate rushing TDs by player_id then add names (GPT's approach)
        rush_tds = td_data[td_data['rush'] == 1]
        if not rush_tds.empty:
            rush_td_counts = rush_tds['rusher_player_id'].value_counts()
            for player_id, count in rush_td_counts.items():
                if pd.notna(player_id):
                    share = count / total_tds
                    # Get player name
                    player_name_series = rush_tds[rush_tds['rusher_player_id'] == player_id]['rusher_player_name']
                    if not player_name_series.empty:
                        player_name = player_name_series.iloc[0]
                        if pd.notna(player_name):
                            if player_name in td_shares:
                                td_shares[player_name] += share
                            else:
                                td_shares[player_name] = share
        
        # Accumulate receiving TDs by player_id then add names
        pass_tds = td_data[td_data['pass'] == 1]
        if not pass_tds.empty:
            rec_td_counts = pass_tds['receiver_player_id'].value_counts()
            for player_id, count in rec_td_counts.items():
                if pd.notna(player_id):
                    share = count / total_tds
                    # Get player name
                    player_name_series = pass_tds[pass_tds['receiver_player_id'] == player_id]['receiver_player_name']
                    if not player_name_series.empty:
                        player_name = player_name_series.iloc[0]
                        if pd.notna(player_name):
                            if player_name in td_shares:
                                td_shares[player_name] += share
                            else:
                                td_shares[player_name] = share
        
        return td_shares
    
    def get_team_player_usage(self, team):
        """Get combined player usage data for a team"""
        rz_usage = self.get_player_rz_usage_share(team)
        td_shares = self.get_player_td_share(team)
        
        # Combine all players mentioned in either metric
        all_players = set(rz_usage.keys()) | set(td_shares.keys())
        
        team_data = {
            'team': team,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'players': {}
        }
        
        for player in all_players:
            rz_share = rz_usage.get(player, 0.0)
            td_share = td_shares.get(player, 0.0)
            
            team_data['players'][player] = {
                'rz_usage_share': round(rz_share, 4),
                'td_share': round(td_share, 4)
            }
        
        return team_data
    
    def get_all_teams_usage(self):
        """Get player usage data for all 32 NFL teams"""
        self.load_nfl_data()
        
        # Get all unique teams from current season
        teams = sorted(self.pbp_data['posteam'].dropna().unique())
        
        all_teams_data = {
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'methodology': {
                'rz_usage_share': 'Player share of team red zone opportunities (rush attempts + targets) with 2+ plays filter, excluding 2-pt conversions',
                'td_share': 'Player share of team touchdowns (rushing + receiving)',
                'calculation': 'Uses player IDs to avoid name collisions, accumulates across rush and receiving'
            },
            'teams': {}
        }
        
        for team in teams:
            print(f"Processing {team}...")
            team_data = self.get_team_player_usage(team)
            all_teams_data['teams'][team] = team_data
        
        print(f"Completed analysis for {len(teams)} teams")
        return all_teams_data

    def refresh_data(self):
        """Refresh data method for manual refresh endpoint"""
        try:
            self.pbp_data = None
            self.data_loaded = False
            self.load_nfl_data()
            return True
        except Exception as e:
            print(f"Error refreshing data: {str(e)}")
            raise

# Initialize service
player_service = PlayerUsageService()

@app.route('/player-usage', methods=['GET'])
def get_player_usage():
    """Get player usage data for all teams or specific team"""
    try:
        team = request.args.get('team')  # Optional team parameter
        
        if team:
            # Get data for specific team
            team_data = player_service.get_team_player_usage(team.upper())
            return jsonify(team_data)
        else:
            # Get data for all teams
            all_data = player_service.get_all_teams_usage()
            return jsonify(all_data)
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/player-usage/<team>', methods=['GET'])
def get_team_player_usage(team):
    """Get player usage data for a specific team"""
    try:
        team_data = player_service.get_team_player_usage(team.upper())
        return jsonify(team_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/refresh', methods=['POST'])
def refresh_data_endpoint():
    """Manual data refresh endpoint"""
    try:
        player_service.refresh_data()
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
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Player Usage Service",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/', methods=['GET'])
def root():
    """API documentation"""
    return jsonify({
        "service": "Player Usage Service",
        "description": "Calculates player red zone usage shares and TD shares following GPT guidelines",
        "endpoints": {
            "/player-usage": {
                "method": "GET",
                "description": "Get all teams player usage data",
                "parameters": {
                    "team": "Optional - get data for specific team (e.g., ?team=KC)"
                }
            },
            "/player-usage/<team>": {
                "method": "GET",
                "description": "Get player usage data for specific team",
                "example": "/player-usage/KC"
            },
            "/health": {
                "method": "GET",
                "description": "Health check"
            },
            "/refresh": {
                "method": "POST", 
                "description": "Manual data refresh"
            }
        },
        "methodology": {
            "rz_usage_share": "Player share of team RZ opportunities with 2+ plays filter, no 2-pt conversions",
            "td_share": "Player share of team TDs (rush + receiving)",
            "notes": "Uses player IDs to avoid name collisions, accumulates across position types"
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
