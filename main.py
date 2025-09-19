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
        """Initialize the TD Boost Calculator - minimal setup"""
        self.baselines = {}
        self.pbp_data = None
        self.schedule_data = None
        self.data_loaded = False
        
        # Don't load anything heavy in __init__
        
    def load_schedule(self):
        """Load NFL schedule data"""
        try:
            logger.info("Loading 2025 NFL schedule...")
            self.schedule_data = nfl.import_schedules([2025])
            
            if self.schedule_data.empty:
                raise ValueError("No schedule data available for 2025")
            
            self.schedule_data['gameday'] = pd.to_datetime(self.schedule_data['gameday'])
            logger.info(f"Schedule loaded: {len(self.schedule_data)} games")
            
        except Exception as e:
            logger.error(f"Failed to load schedule: {str(e)}")
            raise
    
    def get_current_week(self):
        """Determine current NFL week"""
        try:
            today = datetime.now().date()
            future_games = self.schedule_data[
                self.schedule_data['gameday'].dt.date >= today
            ].sort_values('gameday')
            
            if not future_games.empty:
                next_week = future_games['week'].iloc[0]
                logger.info(f"Current week determined: {next_week}")
                return int(next_week)
            else:
                return 2
                
        except Exception as e:
            logger.warning(f"Could not determine current week: {str(e)}")
            return 2
    
    def get_week_matchups(self, week_num=None):
        """Get actual matchups for a specific week"""
        try:
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
                    'gameday': game['gameday'].strftime('%Y-%m-%d'),
                    'week': int(game['week'])
                })
            
            logger.info(f"Found {len(matchups)} games for week {week_num}")
            return matchups
            
        except Exception as e:
            logger.error(f"Error getting week {week_num} matchups: {str(e)}")
            return []
    
    def calculate_matchup_summary(self, offense_team, defense_team):
        """Calculate basic matchup summary"""
        return {
            "offense_team": offense_team,
            "defense_team": defense_team,
            "total_td_advantage": 0.0
        }
    
    def analyze_week_matchups(self, week_num=None):
        """Analyze all matchups for a specific week"""
        try:
            # Load schedule if needed
            if self.schedule_data is None:
                self.load_schedule()
                self.data_loaded = True
            
            matchups = self.get_week_matchups(week_num)
            if not matchups:
                return []
            
            results = []
            
            logger.info(f"Analyzing {len(matchups)} games...")
            
            for matchup in matchups:
                away_team = matchup['away_team']
                home_team = matchup['home_team']
                
                try:
                    away_analysis = self.calculate_matchup_summary(away_team, home_team)
                    home_analysis = self.calculate_matchup_summary(home_team, away_team)
                    
                    game_result = {
                        'game': f"{away_team} @ {home_team}",
                        'gameday': matchup['gameday'],
                        'week': matchup['week'],
                        'away_team': away_team,
                        'home_team': home_team,
                        'away_analysis': away_analysis,
                        'home_analysis': home_analysis
                    }
                    
                    results.append(game_result)
                    
                except Exception as e:
                    logger.warning(f"Error analyzing {away_team} @ {home_team}: {str(e)}")
                    continue
            
            logger.info(f"Successfully analyzed {len(results)} games")
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing matchups: {str(e)}")
            return []
    
    def generate_json_output(self, results, include_metadata=True):
        """Generate JSON output"""
        try:
            output = {
                "games": results,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "total_games": len(results),
                    "data_loaded": self.data_loaded,
                    "disclaimer": "For educational analysis only."
                } if include_metadata else None
            }
            
            if not include_metadata:
                output = {"games": results}
                
            return json.dumps(output, indent=2)
            
        except Exception as e:
            logger.error(f"Error generating JSON output: {str(e)}")
            return json.dumps({"error": "Failed to generate output", "message": str(e)})

def run_analysis():
    """Run analysis function"""
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
    
    return results

# Flask Integration
try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app)
    
    @app.route('/dashboard')
    def dashboard():
        return '''<!DOCTYPE html>
<html>
<head>
    <title>NFL TD Boost Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .title { font-size: 2.5rem; margin-bottom: 10px; }
        .subtitle { color: #60a5fa; }
        .btn { background: #1e3a8a; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .loading { text-align: center; padding: 50px; }
        .error { background: #dc2626; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .game-card { background: rgba(255,255,255,0.1); padding: 20px; margin: 10px 0; border-radius: 10px; }
        .game-title { font-size: 1.2rem; font-weight: bold; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">NFL TD Boost</h1>
            <p class="subtitle">Touchdown Advantage Analysis</p>
            <button class="btn" onclick="loadData()">Refresh Analysis</button>
        </div>
        <div id="loading" class="loading">Loading analysis...</div>
        <div id="error" class="error" style="display: none;"></div>
        <div id="content"></div>
    </div>

    <script>
        async function loadData() {
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const content = document.getElementById('content');
            
            loading.style.display = 'block';
            error.style.display = 'none';
            content.innerHTML = '';
            
            try {
                const response = await fetch('/analyze');
                const data = await response.json();
                
                if (data.games && data.games.length > 0) {
                    const html = data.games.map(game => 
                        `<div class="game-card">
                            <div class="game-title">${game.game}</div>
                            <div>Date: ${game.gameday}</div>
                        </div>`
                    ).join('');
                    content.innerHTML = html;
                } else {
                    content.innerHTML = '<div class="error">No games found</div>';
                }
                
                loading.style.display = 'none';
                
            } catch (err) {
                error.textContent = `Error: ${err.message}`;
                error.style.display = 'block';
                loading.style.display = 'none';
            }
        }
        
        document.addEventListener('DOMContentLoaded', loadData);
    </script>
</body>
</html>'''
    
    @app.route('/analyze', methods=['GET'])
    def analyze():
        """Main endpoint"""
        try:
            target_week = request.args.get('week')
            
            if target_week:
                os.environ['TARGET_WEEK'] = target_week
            
            analysis_data = run_analysis()
            
            if not analysis_data:
                return jsonify({
                    "error": "Analysis failed",
                    "timestamp": datetime.now().isoformat()
                }), 500
            
            results = analysis_data['results']
            calculator = analysis_data['calculator']
            json_output = calculator.generate_json_output(results)
            
            return jsonify(json.loads(json_output))
        
        except Exception as e:
            logger.error(f"Error in Flask endpoint: {str(e)}")
            return jsonify({
                "error": "Unexpected error",
                "message": str(e)
            }), 500
    
    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "healthy"})
    
    @app.route('/', methods=['GET'])
    def root():
        return jsonify({
            "service": "NFL TD Boost Calculator API",
            "version": "1.0"
        })
    
    def run_flask_app():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port, debug=False)

except ImportError:
    app = None
    def run_flask_app():
        logger.error("Flask not installed")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--flask':
        if app is not None:
            run_flask_app()
        else:
            logger.error("Flask not available")
            sys.exit(1)
    else:
        main()
