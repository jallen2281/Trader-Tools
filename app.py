"""Flask web application for financial chart analysis with local LLM."""

# Fix UTF-8 encoding for Windows PowerShell
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import login_required, current_user
from data_fetcher import FinancialDataFetcher
from chart_generator import ChartGenerator
from pattern_recognizer import PatternRecognizer
from llm_analyzer import LLMAnalyzer
from config import Config
from datetime import datetime
import json
import traceback
import pandas as pd
import os

# Phase 2: Database and Authentication
try:
    from models import db, User, Watchlist, Alert, Portfolio, Transaction, OptionsPosition, AnalysisHistory, MLPattern, MLPrediction
    from db_config import init_database
    from auth import init_auth, get_auth_routes, require_api_auth
    from monitoring_service import init_monitoring_service, get_monitoring_service
    from ml_pattern_detector import MLPatternDetector
    PHASE2_ENABLED = True
except ImportError as e:
    print(f"⚠ Phase 2 features not available: {e}")
    print("ℹ Run 'install_phase2.bat' to enable database and authentication")
    PHASE2_ENABLED = False

# Phase 3: Advanced Trading Intelligence
try:
    from options_analyzer import OptionsAnalyzer
    from trading_time_analyzer import TradingTimeAnalyzer
    from sentiment_analyzer import SentimentAnalyzer
    from risk_analyzer import RiskAnalyzer
    PHASE3_ENABLED = True
except ImportError as e:
    print(f"⚠ Phase 3 features not available: {e}")
    print("ℹ Run 'install_phase3.bat' to enable advanced analysis")
    PHASE3_ENABLED = False

# Phase 4: Portfolio Management & Real-Time Intelligence
try:
    from volatility_monitor import VolatilityMonitor
    from portfolio_analyzer import PortfolioAnalyzer
    from smart_alerts import SmartAlertsEngine
    from alert_suggestions import AlertSuggestionEngine
    from news_fetcher import NewsFetcher
    from correlation_analyzer import CorrelationAnalyzer
    from trade_journal import TradeJournal
    from politician_trades import PoliticianTradeTracker
    PHASE4_ENABLED = True
except ImportError as e:
    print(f"⚠ Phase 4 features not available: {e}")
    print("ℹ Phase 4 requires Phase 2 database and Phase 3 analyzers")
    PHASE4_ENABLED = False


app = Flask(__name__)
app.config.from_object(Config)

# Add logging for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Phase 2: Initialize database and authentication
if PHASE2_ENABLED:
    try:
        # Initialize database
        database = init_database(app)
        logger.info("✓ Database initialized")
        
        # Initialize authentication
        login_manager, google_oauth = init_auth(app)
        logger.info("✓ Authentication system initialized")
        
        # Initialize ML pattern detector
        ml_detector = MLPatternDetector()
        logger.info("✓ ML Pattern Detector initialized")
        
        # Initialize monitoring service
        monitoring_svc = init_monitoring_service(app, check_interval=60)
        logger.info("✓ Real-time Monitoring Service initialized")
        
        # Register authentication routes
        auth_routes = get_auth_routes(google_oauth)
        
        @app.route('/login')
        def login():
            return auth_routes['login']()
        
        @app.route('/authorize')
        def authorize():
            return auth_routes['authorize']()
        
        @app.route('/logout')
        def logout():
            return auth_routes['logout']()
        
        logger.info("✓ Authentication routes registered")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize Phase 2 features: {e}")
        PHASE2_ENABLED = False
else:
    logger.info("ℹ Running in Phase 1 mode (no authentication)")

# Phase 3: Initialize advanced analyzers
if PHASE3_ENABLED:
    try:
        options_analyzer = OptionsAnalyzer()
        logger.info("✓ Options Analyzer initialized")
        
        trading_time_analyzer = TradingTimeAnalyzer()
        logger.info("✓ Trading Time Analyzer initialized")
        
        sentiment_analyzer = SentimentAnalyzer()
        logger.info("✓ Sentiment Analyzer initialized")
        
        risk_analyzer = RiskAnalyzer()
        logger.info("✓ Risk Analyzer initialized")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize Phase 3 features: {e}")
        PHASE3_ENABLED = False
else:
    logger.info("ℹ Phase 3 features not available")

# Phase 4: Initialize portfolio management & volatility monitoring
if PHASE4_ENABLED and PHASE2_ENABLED:
    try:
        volatility_monitor = VolatilityMonitor()
        logger.info("✓ Volatility Monitor initialized")
        
        portfolio_analyzer = PortfolioAnalyzer()
        logger.info("✓ Portfolio Analyzer initialized")
        
        smart_alerts = SmartAlertsEngine()
        logger.info("✓ Smart Alerts Engine initialized")
        
        # Initialize alert suggestions engine with other analyzers
        pattern_rec = PatternRecognizer() if 'PatternRecognizer' in dir() else None
        sentiment_an = sentiment_analyzer if PHASE3_ENABLED else None
        alert_suggestions = AlertSuggestionEngine(
            pattern_recognizer=pattern_rec,
            sentiment_analyzer=sentiment_an,
            volatility_monitor=volatility_monitor,
            portfolio_analyzer=portfolio_analyzer
        )
        logger.info("✓ AI Alert Suggestion Engine initialized")
        
        # Initialize news fetcher
        news_fetcher = NewsFetcher()
        logger.info("✓ News Fetcher initialized")
        
        # Initialize correlation analyzer
        correlation_analyzer = CorrelationAnalyzer()
        logger.info("✓ Correlation Analyzer initialized")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize Phase 4 features: {e}")
        PHASE4_ENABLED = False
else:
    if not PHASE2_ENABLED:
        logger.info("ℹ Phase 4 requires Phase 2 (database)")
    else:
        logger.info("ℹ Phase 4 features not available")

# Initialize components
try:
    data_fetcher = FinancialDataFetcher()
    logger.info("✓ FinancialDataFetcher initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize FinancialDataFetcher: {e}")
    raise

try:
    chart_generator = ChartGenerator()
    logger.info("✓ ChartGenerator initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize ChartGenerator: {e}")
    raise

try:
    pattern_recognizer = PatternRecognizer()
    logger.info("✓ PatternRecognizer initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize PatternRecognizer: {e}")
    raise

try:
    llm_analyzer = LLMAnalyzer()
    logger.info("✓ LLMAnalyzer initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize LLMAnalyzer: {e}")
    raise

# Initialize Trade Journal after LLM Analyzer (Feature #5)
if PHASE4_ENABLED and PHASE2_ENABLED:
    try:
        trade_journal = TradeJournal(llm_analyzer)
        logger.info("✓ Trade Journal initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize Trade Journal: {e}")


@app.before_request
def log_request():
    """Log all incoming requests."""
    logger.info(f"→ {request.method} {request.path}")


@app.after_request
def log_response(response):
    """Log all responses."""
    logger.info(f"← {request.method} {request.path} → {response.status_code}")
    return response


@app.route('/')
def index():
    """Render the main dashboard."""
    logger.debug("Rendering dashboard.html as main page")
    if PHASE2_ENABLED:
        # Require login for Phase 2
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/dashboard')
def dashboard():
    """Render the enhanced dashboard with watchlist, alerts, and comparison features."""
    logger.debug("Rendering dashboard.html")
    if PHASE2_ENABLED:
        # Require login for Phase 2
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/simple')
def simple():
    """Render the simple/classic interface."""
    logger.debug("Rendering index.html (simple interface)")
    return render_template('index.html')


@app.route('/portfolio')
@login_required
def portfolio():
    """Render the portfolio analytics dashboard (Phase 4)."""
    logger.debug("Rendering portfolio.html")
    if not PHASE4_ENABLED:
        return "Portfolio features are not enabled", 503
    return render_template('portfolio.html')


@app.route('/copytrading')
@login_required
def copytrading():
    """Render the copy trading research page."""
    logger.debug("Rendering copytrading.html")
    return render_template('copytrading.html')


@app.route('/api/analyze', methods=['POST'])
def analyze_stock():
    """Analyze a stock symbol and return comprehensive results."""
    logger.info("Starting stock analysis...")
    try:
        data = request.get_json()
        if data is None:
            logger.error("No JSON data in request")
            return jsonify({'error': 'No JSON data provided'}), 400
        
        symbol = data.get('symbol', 'AAPL').upper()
        logger.info(f"Analyzing symbol: {symbol}")
        period = data.get('period', '6mo')
        interval = data.get('interval', '1d')
        chart_type = data.get('chart_type', 'candlestick')
        
        # Fetch stock data
        logger.info(f"Fetching data for {symbol} (period={period}, interval={interval})")
        stock_data = data_fetcher.fetch_stock_data(symbol, period, interval)
        
        if stock_data is None:
            logger.error(f"No data returned for {symbol}")
            return jsonify({'error': f'No data found for {symbol}. Please verify the symbol is correct.'}), 404
        
        if stock_data.empty:
            logger.error(f"Empty dataframe for {symbol}")
            return jsonify({'error': f'No data available for {symbol}'}), 404
        
        logger.info(f"Data fetched: {len(stock_data)} rows")
        
        # Calculate indicators
        logger.debug("Calculating technical indicators...")
        try:
            stock_data = pattern_recognizer.calculate_indicators(stock_data)
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return jsonify({'error': f'Error calculating indicators: {str(e)}'}), 500
        
        # Generate chart
        logger.debug(f"Generating {chart_type} chart...")
        try:
            if chart_type == 'line':
                chart_base64 = chart_generator.generate_line_chart(
                    stock_data, symbol
                )
            elif chart_type == 'volume':
                chart_base64 = chart_generator.generate_volume_chart(
                    stock_data, symbol
                )
            else:  # Default to candlestick
                chart_base64 = chart_generator.generate_candlestick_chart(
                    stock_data, symbol
                )
        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            # Continue without chart
            chart_base64 = ""
        
        # Detect patterns
        logger.debug("Detecting patterns...")
        try:
            candlestick_patterns = pattern_recognizer.detect_candlestick_patterns(stock_data)
            support_resistance = pattern_recognizer.detect_support_resistance(stock_data)
            trend = pattern_recognizer.detect_trend(stock_data)
            signals = pattern_recognizer.generate_signals(stock_data)
        except Exception as e:
            logger.error(f"Error detecting patterns: {e}")
            candlestick_patterns = []
            support_resistance = {'support': [], 'resistance': []}
            trend = 'unknown'
            signals = {}
        
        # Get latest values
        try:
            latest = stock_data.iloc[-1]
            prev = stock_data.iloc[-2] if len(stock_data) > 1 else latest
        except Exception as e:
            logger.error(f"Error accessing stock data: {e}")
            return jsonify({'error': f'Error processing stock data: {str(e)}'}), 500
        
        # Prepare indicators summary
        try:
            indicators = {
                'RSI': round(float(latest.get('RSI', 0)), 2) if pd.notna(latest.get('RSI')) else 0,
                'MACD': round(float(latest.get('MACD', 0)), 4) if pd.notna(latest.get('MACD')) else 0,
                'MACD_Signal': round(float(latest.get('MACD_Signal', 0)), 4) if pd.notna(latest.get('MACD_Signal')) else 0,
                'SMA_20': round(float(latest.get('SMA_20', 0)), 2) if pd.notna(latest.get('SMA_20')) else 0,
                'SMA_50': round(float(latest.get('SMA_50', 0)), 2) if pd.notna(latest.get('SMA_50')) else 0,
                'BB_High': round(float(latest.get('BB_High', 0)), 2) if pd.notna(latest.get('BB_High')) else 0,
                'BB_Low': round(float(latest.get('BB_Low', 0)), 2) if pd.notna(latest.get('BB_Low')) else 0,
            }
        except Exception as e:
            logger.error(f"Error preparing indicators: {e}")
            indicators = {'RSI': 0, 'MACD': 0, 'MACD_Signal': 0, 'SMA_20': 0, 'SMA_50': 0, 'BB_High': 0, 'BB_Low': 0}
        
        # LLM analysis
        logger.debug("Running LLM analysis...")
        try:
            llm_analysis = llm_analyzer.analyze_chart(
                chart_base64,
                symbol,
                indicators,
                candlestick_patterns,
                context=f"Current trend: {trend}"
            )
        except Exception as e:
            logger.error(f"Error in LLM analysis: {e}")
            llm_analysis = f"Error performing AI analysis: {str(e)}"
        
        # ML Pattern Detection (Phase 2)
        ml_patterns = []
        ml_prediction = None
        if PHASE2_ENABLED and ml_detector:
            logger.debug("Detecting ML patterns...")
            try:
                ml_patterns = ml_detector.detect_patterns(stock_data, symbol)
                logger.info(f"Detected {len(ml_patterns)} ML patterns")
            except Exception as e:
                logger.error(f"Error detecting ML patterns: {e}")
            
            logger.debug("Generating ML prediction...")
            try:
                ml_prediction = ml_detector.make_prediction(stock_data, symbol)
                if ml_prediction:
                    logger.info(f"ML Prediction: {ml_prediction['predicted_direction']} ({ml_prediction['confidence']*100:.1f}% confidence)")
            except Exception as e:
                logger.error(f"Error making ML prediction: {e}")
        
        # Phase 3: Advanced Analysis
        sentiment_analysis = None
        risk_analysis = None
        timing_analysis = None
        if PHASE3_ENABLED:
            logger.debug("Running Phase 3 analysis...")
            try:
                sentiment_analysis = sentiment_analyzer.analyze_sentiment(stock_data, symbol)
                logger.info(f"Sentiment: {sentiment_analysis.get('sentiment_label', 'N/A')}")
            except Exception as e:
                logger.error(f"Error in sentiment analysis: {e}")
            
            try:
                risk_analysis = risk_analyzer.comprehensive_risk_analysis(stock_data, symbol)
                logger.info(f"Risk Score: {risk_analysis.get('overall_risk_score', 'N/A')}")
            except Exception as e:
                logger.error(f"Error in risk analysis: {e}")
            
            try:
                timing_analysis = {
                    'entry': trading_time_analyzer.analyze_entry_points(stock_data, symbol),
                    'exit': trading_time_analyzer.analyze_exit_points(stock_data, symbol),
                    'volume': trading_time_analyzer.analyze_volume_profile(stock_data, symbol)
                }
                logger.info(f"Entry Score: {timing_analysis['entry'].get('entry_score', 'N/A')}")
            except Exception as e:
                logger.error(f"Error in timing analysis: {e}")
        
        # Company info
        logger.debug("Fetching company info...")
        try:
            company_info = data_fetcher.get_company_info(symbol)
        except Exception as e:
            logger.error(f"Error fetching company info: {e}")
            company_info = {'name': symbol, 'sector': 'N/A', 'industry': 'N/A', 'market_cap': 'N/A', 'description': 'N/A'}
        
        # Prepare response
        try:
            response = {
                'symbol': symbol,
                'company_info': company_info,
                'current_price': round(float(latest['Close']), 2),
                'price_change': round(float(latest['Close'] - prev['Close']), 2),
                'price_change_pct': round(float((latest['Close'] - prev['Close']) / prev['Close'] * 100), 2) if float(prev['Close']) != 0 else 0,
                'volume': int(latest['Volume']) if not pd.isna(latest['Volume']) else 0,
                'trend': trend,
                'chart': f'data:image/png;base64,{chart_base64}' if chart_base64 else '',
                'indicators': indicators,
                'signals': signals,
                'support_resistance': {
                    'support': [round(float(x), 2) for x in support_resistance['support'][-3:]] if support_resistance['support'] else [],
                    'resistance': [round(float(x), 2) for x in support_resistance['resistance'][-3:]] if support_resistance['resistance'] else []
                },
                'patterns': candlestick_patterns,
                'ml_patterns': ml_patterns,
                'ml_prediction': ml_prediction,
                'sentiment': sentiment_analysis,
                'risk': risk_analysis,
                'timing': timing_analysis,
                'llm_analysis': llm_analysis
            }
        except Exception as e:
            logger.error(f"Error preparing response: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Error preparing response: {str(e)}'}), 500
        
        logger.info(f"✓ Analysis complete for {symbol}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error analyzing stock: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/technical-chart', methods=['POST'])
def generate_technical_chart():
    """Generate technical chart with customizable indicators."""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        symbol = data.get('symbol', 'AAPL').upper()
        period = data.get('period', '6mo')
        interval = data.get('interval', '1d')
        indicators = data.get('indicators', [])  # ['rsi', 'macd', 'bb', 'ma']
        
        logger.info(f"Generating technical chart for {symbol} with indicators: {indicators}")
        
        # Fetch stock data
        stock_data = data_fetcher.fetch_stock_data(symbol, period, interval)
        
        if stock_data is None or stock_data.empty:
            return jsonify({'error': f'No data found for {symbol}'}), 404
        
        # Generate technical chart
        chart_base64 = chart_generator.generate_technical_chart(
            stock_data, symbol, indicators
        )
        
        # Get current stats
        latest = stock_data.iloc[-1]
        current_price = float(latest['Close'])
        prev_close = float(stock_data.iloc[-2]['Close']) if len(stock_data) > 1 else current_price
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close * 100) if prev_close != 0 else 0
        
        return jsonify({
            'symbol': symbol,
            'chart': f'data:image/png;base64,{chart_base64}',
            'current_price': round(current_price, 2),
            'price_change': round(price_change, 2),
            'price_change_pct': round(price_change_pct, 2),
            'indicators': indicators
        })
        
    except Exception as e:
        logger.error(f"Error generating technical chart: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    logger.debug("Health check requested")
    return jsonify({
        'status': 'healthy',
        'message': 'Server is running',
        'routes_registered': [str(rule) for rule in app.url_map.iter_rules()]
    })


@app.route('/api/status', methods=['GET'])
def check_status():
    """Check system status."""
    ollama_status = llm_analyzer.check_ollama_status()
    return jsonify({
        'status': 'ok',
        'ollama': ollama_status
    })


@app.route('/api/pattern-info/<pattern_name>', methods=['GET'])
def get_pattern_info(pattern_name):
    """Get information about a specific pattern."""
    try:
        explanation = llm_analyzer.get_pattern_explanation(pattern_name)
        return jsonify({
            'pattern': pattern_name,
            'explanation': explanation
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare', methods=['POST'])
def compare_stocks():
    """Compare multiple stocks with optional chart."""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        period = data.get('period', '6mo')
        normalize = data.get('normalize', True)
        include_chart = data.get('include_chart', False)
        
        if not symbols:
            return jsonify({'error': 'No symbols provided'}), 400
        
        if len(symbols) > 10:
            return jsonify({'error': 'Maximum 10 symbols allowed'}), 400
        
        results = {}
        data_dict = {}
        
        for symbol in symbols:
            symbol_upper = symbol.upper()
            stock_data = data_fetcher.fetch_stock_data(symbol_upper, period)
            
            if stock_data is not None and not stock_data.empty:
                data_dict[symbol_upper] = stock_data
                
                latest = stock_data.iloc[-1]
                first = stock_data.iloc[0]
                
                # Calculate volatility safely
                volatility = 0
                if 'Returns' in stock_data.columns:
                    vol_value = stock_data['Returns'].std() * 100
                    volatility = round(float(vol_value), 2) if pd.notna(vol_value) else 0
                
                # Calculate return safely
                return_pct = 0
                if pd.notna(latest['Close']) and pd.notna(first['Close']) and first['Close'] != 0:
                    return_pct = round(float((latest['Close'] - first['Close']) / first['Close'] * 100), 2)
                
                results[symbol_upper] = {
                    'current_price': round(float(latest['Close']), 2) if pd.notna(latest['Close']) else 0,
                    'return_pct': return_pct,
                    'volatility': volatility,
                    'volume': int(latest['Volume']) if pd.notna(latest['Volume']) else 0,
                    'high': round(float(stock_data['High'].max()), 2) if pd.notna(stock_data['High'].max()) else 0,
                    'low': round(float(stock_data['Low'].min()), 2) if pd.notna(stock_data['Low'].min()) else 0
                }
        
        response = {'symbols': results}
        
        # Generate comparison chart if requested
        if include_chart and data_dict:
            try:
                chart_base64 = chart_generator.generate_comparison_chart(
                    data_dict, 
                    normalize=normalize
                )
                response['chart'] = f'data:image/png;base64,{chart_base64}'
            except Exception as e:
                logger.error(f"Error generating comparison chart: {e}")
                response['chart'] = None
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in compare_stocks: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_watchlist():
    """Manage watchlist."""
    if not PHASE2_ENABLED:
        # Phase 1: Use localStorage
        if request.method == 'GET':
            return jsonify({'message': 'Use localStorage on client', 'symbols': []})
        elif request.method == 'POST':
            data = request.get_json()
            return jsonify({'message': 'Use localStorage on client', 'success': True})
        elif request.method == 'DELETE':
            return jsonify({'message': 'Use localStorage on client', 'success': True})
    
    # Phase 2: Database-backed watchlist
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        if request.method == 'GET':
            watchlist = Watchlist.query.filter_by(user_id=current_user.id).all()
            
            # If watchlist is empty, auto-populate with portfolio symbols
            if not watchlist and PHASE2_ENABLED:
                portfolio_positions = Portfolio.query.filter_by(user_id=current_user.id).all()
                if portfolio_positions:
                    for pos in portfolio_positions:
                        item = Watchlist(
                            user_id=current_user.id,
                            symbol=pos.symbol,
                            notes='Auto-added from portfolio'
                        )
                        db.session.add(item)
                    
                    # Also add common market indices
                    for symbol in ['SPY', 'QQQ', 'DIA']:
                        if not Watchlist.query.filter_by(user_id=current_user.id, symbol=symbol).first():
                            item = Watchlist(
                                user_id=current_user.id,
                                symbol=symbol,
                                notes='Market index'
                            )
                            db.session.add(item)
                    
                    db.session.commit()
                    watchlist = Watchlist.query.filter_by(user_id=current_user.id).all()
                    logger.info(f"Auto-populated watchlist with {len(watchlist)} symbols for user {current_user.id}")
            
            return jsonify({'symbols': [item.to_dict() for item in watchlist]})
        
        elif request.method == 'POST':
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            notes = data.get('notes', '')
            
            if not symbol:
                return jsonify({'error': 'No symbol provided'}), 400
            
            # Check if already exists
            existing = Watchlist.query.filter_by(
                user_id=current_user.id,
                symbol=symbol
            ).first()
            
            if existing:
                return jsonify({'error': 'Symbol already in watchlist'}), 400
            
            # Add to watchlist
            item = Watchlist(
                user_id=current_user.id,
                symbol=symbol,
                notes=notes
            )
            db.session.add(item)
            db.session.commit()
            
            return jsonify({'message': f'Added {symbol} to watchlist', 'success': True})
        
        elif request.method == 'DELETE':
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            
            if not symbol:
                return jsonify({'error': 'No symbol provided'}), 400
            
            item = Watchlist.query.filter_by(
                user_id=current_user.id,
                symbol=symbol
            ).first()
            
            if item:
                db.session.delete(item)
                db.session.commit()
                return jsonify({'message': f'Removed {symbol} from watchlist', 'success': True})
            
            return jsonify({'error': 'Symbol not found in watchlist'}), 404
    
    except Exception as e:
        logger.error(f"Error managing watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts', methods=['GET', 'POST', 'DELETE'])
def manage_alerts():
    """Manage price alerts."""
    if not PHASE2_ENABLED:
        # Phase 1: Use localStorage
        if request.method == 'GET':
            return jsonify({'message': 'Use localStorage on client', 'alerts': []})
        elif request.method == 'POST':
            return jsonify({'message': 'Use localStorage on client', 'success': True})
        elif request.method == 'DELETE':
            return jsonify({'message': 'Use localStorage on client', 'success': True})
    
    # Phase 2: Database-backed alerts
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        if request.method == 'GET':
            alerts = Alert.query.filter_by(user_id=current_user.id, enabled=True).all()
            return jsonify({'alerts': [alert.to_dict() for alert in alerts]})
        
        elif request.method == 'POST':
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            alert_type = data.get('type')  # 'above' or 'below'
            target_price = data.get('targetPrice')
            
            if not all([symbol, alert_type, target_price]):
                return jsonify({'error': 'Missing required fields'}), 400
            
            # Create alert
            alert = Alert(
                user_id=current_user.id,
                symbol=symbol,
                alert_type=alert_type,
                target_price=target_price,
                enabled=True
            )
            db.session.add(alert)
            db.session.commit()
            
            return jsonify({
                'message': f'Alert created for {symbol}',
                'success': True,
                'alert': alert.to_dict()
            })
        
        elif request.method == 'DELETE':
            data = request.get_json()
            alert_id = data.get('id')
            
            if not alert_id:
                return jsonify({'error': 'No alert ID provided'}), 400
            
            alert = Alert.query.filter_by(
                id=alert_id,
                user_id=current_user.id
            ).first()
            
            if alert:
                db.session.delete(alert)
                db.session.commit()
                return jsonify({'message': 'Alert deleted', 'success': True})
            
            return jsonify({'error': 'Alert not found'}), 404
    
    except Exception as e:
        logger.error(f"Error managing alerts: {e}")
        return jsonify({'error': str(e)}), 500

# Phase 2: Portfolio endpoints
@app.route('/api/portfolio/list', methods=['GET'])
def list_portfolio_holdings():
    """Get list of portfolio holdings (Phase 2)."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # Get all holdings
        holdings = Portfolio.query.filter_by(user_id=current_user.id).all()
        
        # Update current prices
        for holding in holdings:
            stock_data = data_fetcher.fetch_stock_data(holding.symbol, '1d')
            if stock_data is not None and not stock_data.empty:
                holding.current_price = float(stock_data.iloc[-1]['Close'])
        
        db.session.commit()
        
        return jsonify({
            'holdings': [h.to_dict() for h in holdings],
            'total_value': sum(h.quantity * h.current_price for h in holdings if h.current_price),
            'total_cost': sum(h.quantity * h.average_cost for h in holdings)
        })
        
    except Exception as e:
        logger.error(f"Error listing portfolio: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio', methods=['POST', 'DELETE'])
def manage_portfolio():
    """Add or remove portfolio holdings (Phase 2)."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        if request.method == 'POST':
            # Add new position
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            asset_type = data.get('asset_type', 'stock')
            quantity = float(data.get('quantity', 0))
            price = float(data.get('price', 0))
            purchase_date = data.get('purchase_date')  # Get purchase date if provided
            
            if not all([symbol, quantity > 0, price > 0]):
                return jsonify({'error': 'Missing or invalid fields'}), 400
            
            # Parse purchase date if provided
            parsed_date = None
            if purchase_date:
                try:
                    from datetime import datetime
                    parsed_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))
                except:
                    parsed_date = datetime.utcnow()
            else:
                parsed_date = datetime.utcnow()
            
            # Check if position exists
            existing = Portfolio.query.filter_by(
                user_id=current_user.id,
                symbol=symbol,
                asset_type=asset_type
            ).first()
            
            if existing:
                # Update average cost
                total_cost = (existing.quantity * existing.average_cost) + (quantity * price)
                total_quantity = existing.quantity + quantity
                existing.average_cost = total_cost / total_quantity
                existing.quantity = total_quantity
                # Keep original purchase date for existing positions
            else:
                # Create new position
                position = Portfolio(
                    user_id=current_user.id,
                    symbol=symbol,
                    asset_type=asset_type,
                    quantity=quantity,
                    average_cost=price,
                    purchase_date=parsed_date
                )
                db.session.add(position)
            
            # Record transaction with the purchase date
            transaction = Transaction(
                user_id=current_user.id,
                symbol=symbol,
                asset_type=asset_type,
                transaction_type='buy',
                quantity=quantity,
                price=price,
                transaction_date=parsed_date
            )
            db.session.add(transaction)
            db.session.commit()
            
            return jsonify({'message': f'Added {quantity} shares of {symbol}', 'success': True}), 201
        
        elif request.method == 'DELETE':
            # Remove position
            data = request.get_json()
            position_id = data.get('id')
            
            if not position_id:
                return jsonify({'error': 'No position ID provided'}), 400
            
            position = Portfolio.query.filter_by(
                id=position_id,
                user_id=current_user.id
            ).first()
            
            if position:
                db.session.delete(position)
                db.session.commit()
                return jsonify({'message': 'Position removed', 'success': True})
            
            return jsonify({'error': 'Position not found'}), 404
    
    except Exception as e:
        logger.error(f"Error managing portfolio: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get transaction history."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        symbol = request.args.get('symbol')
        
        query = Transaction.query.filter_by(user_id=current_user.id)
        if symbol:
            query = query.filter_by(symbol=symbol.upper())
        
        transactions = query.order_by(Transaction.transaction_date.desc()).limit(100).all()
        
        return jsonify({
            'transactions': [t.to_dict() for t in transactions]
        })
    
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/options', methods=['GET', 'POST'])
def manage_options():
    """Manage options positions."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        if request.method == 'GET':
            positions = OptionsPosition.query.filter_by(
                user_id=current_user.id,
                status='open'
            ).all()
            
            return jsonify({
                'positions': [p.to_dict() for p in positions]
            })
        
        elif request.method == 'POST':
            data = request.get_json()
            
            position = OptionsPosition(
                user_id=current_user.id,
                underlying_symbol=data.get('symbol', '').upper(),
                option_type=data.get('option_type'),
                strike_price=float(data.get('strike_price')),
                expiration_date=data.get('expiration_date'),
                quantity=int(data.get('quantity')),
                premium_paid=float(data.get('premium_paid'))
            )
            
            db.session.add(position)
            db.session.commit()
            
            return jsonify({
                'message': 'Options position added',
                'success': True,
                'position': position.to_dict()
            })
    
    except Exception as e:
        logger.error(f"Error managing options: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/options/<int:position_id>', methods=['DELETE'])
def delete_option_position(position_id):
    """Delete an options position."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        position = OptionsPosition.query.filter_by(
            id=position_id,
            user_id=current_user.id
        ).first()
        
        if not position:
            return jsonify({'error': 'Position not found'}), 404
        
        db.session.delete(position)
        db.session.commit()
        
        logger.info(f"Deleted options position {position.underlying_symbol} (ID: {position_id}) for user {current_user.id}")
        return jsonify({'message': 'Position deleted successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error deleting options position: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ml-patterns', methods=['GET', 'POST'])
def manage_ml_patterns():
    """Get or generate ML detected patterns."""
    if not PHASE2_ENABLED:
        return jsonify({'message': 'ML features not available', 'patterns': []})
    
    try:
        if request.method == 'GET':
            # Get existing patterns from database
            symbol = request.args.get('symbol')
            
            query = MLPattern.query
            if symbol:
                query = query.filter_by(symbol=symbol.upper())
            
            patterns = query.order_by(MLPattern.detected_at.desc()).limit(50).all()
            
            return jsonify({
                'patterns': [p.to_dict() for p in patterns]
            })
        
        elif request.method == 'POST':
            # Generate new patterns for a symbol
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            period = data.get('period', '6mo')
            
            if not symbol:
                return jsonify({'error': 'No symbol provided'}), 400
            
            # Fetch stock data
            stock_data = data_fetcher.fetch_stock_data(symbol, period)
            
            if stock_data is None or stock_data.empty:
                return jsonify({'error': f'No data for {symbol}'}), 404
            
            # Detect patterns
            patterns = ml_detector.detect_patterns(stock_data, symbol)
            
            # Save to database
            saved_patterns = []
            for pattern_data in patterns:
                pattern = MLPattern(
                    symbol=pattern_data['symbol'],
                    pattern_type=pattern_data['pattern_type'],
                    confidence=pattern_data['confidence'],
                    prediction=pattern_data['prediction'],
                    time_horizon=pattern_data['time_horizon'],
                    pattern_data=pattern_data['pattern_data'],
                    price_at_detection=pattern_data['price_at_detection']
                )
                db.session.add(pattern)
                saved_patterns.append(pattern_data)
            
            db.session.commit()
            
            return jsonify({
                'message': f'Detected {len(patterns)} patterns for {symbol}',
                'patterns': saved_patterns
            })
    
    except Exception as e:
        logger.error(f"Error managing ML patterns: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ml-predictions', methods=['GET', 'POST'])
def manage_ml_predictions():
    """Get or generate ML predictions."""
    if not PHASE2_ENABLED:
        return jsonify({'message': 'ML features not available', 'predictions': []})
    
    try:
        if request.method == 'GET':
            # Get existing predictions
            symbol = request.args.get('symbol')
            
            query = MLPrediction.query
            if symbol:
                query = query.filter_by(symbol=symbol.upper())
            
            predictions = query.order_by(MLPrediction.created_at.desc()).limit(50).all()
            
            return jsonify({
                'predictions': [p.to_dict() for p in predictions]
            })
        
        elif request.method == 'POST':
            # Generate new prediction
            data = request.get_json()
            symbol = data.get('symbol', '').upper()
            period = data.get('period', '6mo')
            horizon_days = data.get('horizon_days', 5)
            
            if not symbol:
                return jsonify({'error': 'No symbol provided'}), 400
            
            # Fetch stock data
            stock_data = data_fetcher.fetch_stock_data(symbol, period)
            
            if stock_data is None or stock_data.empty:
                return jsonify({'error': f'No data for {symbol}'}), 404
            
            # Make prediction
            prediction_data = ml_detector.make_prediction(stock_data, symbol, horizon_days)
            
            if not prediction_data:
                return jsonify({'error': 'Could not generate prediction'}), 500
            
            # Save to database
            prediction = MLPrediction(
                symbol=prediction_data['symbol'],
                prediction_type=prediction_data['prediction_type'],
                predicted_direction=prediction_data['predicted_direction'],
                predicted_price=prediction_data['predicted_price'],
                confidence=prediction_data['confidence'],
                time_horizon=prediction_data['time_horizon'],
                target_date=prediction_data['target_date'],
                model_version=prediction_data['model_version']
            )
            
            db.session.add(prediction)
            db.session.commit()
            
            return jsonify({
                'message': f'Generated prediction for {symbol}',
                'prediction': prediction_data
            })
    
    except Exception as e:
        logger.error(f"Error managing ML predictions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/status', methods=['GET'])
def monitoring_status():
    """Get monitoring service status."""
    if not PHASE2_ENABLED:
        return jsonify({'message': 'Monitoring not available', 'running': False})
    
    try:
        service = get_monitoring_service()
        if service:
            stats = service.get_monitoring_stats()
            return jsonify(stats)
        else:
            return jsonify({'message': 'Monitoring service not initialized', 'running': False})
    
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/check/<symbol>', methods=['GET'])
def check_symbol_price(symbol):
    """Manually check a symbol's current price."""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Monitoring not available'}), 503
    
    try:
        service = get_monitoring_service()
        if service:
            result = service.check_symbol(symbol.upper())
            return jsonify(result)
        else:
            return jsonify({'error': 'Monitoring service not initialized'}), 503
    
    except Exception as e:
        logger.error(f"Error checking symbol {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ml-patterns', methods=['GET'])
def get_ml_patterns():
    """Get ML detected patterns."""
    if not PHASE2_ENABLED:
        return jsonify({'message': 'ML features not available', 'patterns': []})
    
    try:
        symbol = request.args.get('symbol')
        
        query = MLPattern.query
        if symbol:
            query = query.filter_by(symbol=symbol.upper())
        
        patterns = query.order_by(MLPattern.detected_at.desc()).limit(50).all()
        
        return jsonify({
            'patterns': [p.to_dict() for p in patterns]
        })
    
    except Exception as e:
        logger.error(f"Error fetching ML patterns: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ml-predictions', methods=['GET'])
def get_ml_predictions():
    """Get ML predictions."""
    if not PHASE2_ENABLED:
        return jsonify({'message': 'ML features not available', 'predictions': []})
    
    try:
        symbol = request.args.get('symbol')
        
        query = MLPrediction.query
        if symbol:
            query = query.filter_by(symbol=symbol.upper())
        
        predictions = query.order_by(MLPrediction.created_at.desc()).limit(50).all()
        
        return jsonify({
            'predictions': [p.to_dict() for p in predictions]
        })
    
    except Exception as e:
        logger.error(f"Error fetching ML predictions: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# PHASE 3: ADVANCED TRADING INTELLIGENCE API
# ==========================================

@app.route('/api/options/<symbol>', methods=['GET'])
def get_options_analysis(symbol):
    """Get comprehensive options analysis for a symbol."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        analysis = options_analyzer.analyze_options_comprehensive(symbol)
        
        return jsonify(analysis)
    
    except Exception as e:
        logger.error(f"Error in options analysis for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/options/<symbol>/chain', methods=['GET'])
def get_options_chain(symbol):
    """Get options chain data."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        expiration = request.args.get('expiration')
        chain = options_analyzer.get_options_chain(symbol, expiration)
        
        return jsonify(chain)
    
    except Exception as e:
        logger.error(f"Error fetching options chain for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/options/<symbol>/max-pain', methods=['GET'])
def get_max_pain(symbol):
    """Calculate max pain for options."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        expiration = request.args.get('expiration')
        max_pain = options_analyzer.calculate_max_pain(symbol, expiration)
        
        return jsonify(max_pain)
    
    except Exception as e:
        logger.error(f"Error calculating max pain for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/timing/<symbol>/entry', methods=['GET'])
def get_entry_timing(symbol):
    """Get optimal entry point analysis."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        period = request.args.get('period', '6mo')
        
        stock_data = data_fetcher.fetch_stock_data(symbol, period, '1d')
        if stock_data is None or stock_data.empty:
            return jsonify({'error': 'No data available'}), 404
        
        stock_data = pattern_recognizer.calculate_indicators(stock_data)
        entry_analysis = trading_time_analyzer.analyze_entry_points(stock_data, symbol)
        
        return jsonify(entry_analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing entry timing for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/timing/<symbol>/exit', methods=['GET'])
def get_exit_timing(symbol):
    """Get optimal exit point analysis."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        period = request.args.get('period', '6mo')
        entry_price = request.args.get('entry_price', type=float)
        
        stock_data = data_fetcher.fetch_stock_data(symbol, period, '1d')
        if stock_data is None or stock_data.empty:
            return jsonify({'error': 'No data available'}), 404
        
        stock_data = pattern_recognizer.calculate_indicators(stock_data)
        exit_analysis = trading_time_analyzer.analyze_exit_points(stock_data, symbol, entry_price)
        
        return jsonify(exit_analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing exit timing for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/timing/<symbol>/volume', methods=['GET'])
def get_volume_analysis(symbol):
    """Get volume profile analysis."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        period = request.args.get('period', '6mo')
        
        stock_data = data_fetcher.fetch_stock_data(symbol, period, '1d')
        if stock_data is None or stock_data.empty:
            return jsonify({'error': 'No data available'}), 404
        
        volume_analysis = trading_time_analyzer.analyze_volume_profile(stock_data, symbol)
        
        return jsonify(volume_analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing volume for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sentiment/<symbol>', methods=['GET'])
def get_sentiment_analysis(symbol):
    """Get comprehensive sentiment analysis."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        period = request.args.get('period', '6mo')
        
        stock_data = data_fetcher.fetch_stock_data(symbol, period, '1d')
        if stock_data is None or stock_data.empty:
            return jsonify({'error': 'No data available'}), 404
        
        stock_data = pattern_recognizer.calculate_indicators(stock_data)
        sentiment = sentiment_analyzer.analyze_sentiment(stock_data, symbol)
        
        return jsonify(sentiment)
    
    except Exception as e:
        logger.error(f"Error analyzing sentiment for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/risk/<symbol>', methods=['GET'])
def get_risk_analysis(symbol):
    """Get comprehensive risk analysis."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        symbol = symbol.upper()
        period = request.args.get('period', '6mo')
        position_size = request.args.get('position_size', type=int)
        portfolio_value = request.args.get('portfolio_value', type=float)
        
        stock_data = data_fetcher.fetch_stock_data(symbol, period, '1d')
        if stock_data is None or stock_data.empty:
            return jsonify({'error': 'No data available'}), 404
        
        risk = risk_analyzer.comprehensive_risk_analysis(
            stock_data, symbol, position_size, portfolio_value
        )
        
        return jsonify(risk)
    
    except Exception as e:
        logger.error(f"Error analyzing risk for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/risk/position-sizing', methods=['POST'])
def calculate_position_sizing():
    """Calculate optimal position size."""
    if not PHASE3_ENABLED:
        return jsonify({'message': 'Phase 3 features not available'}), 501
    
    try:
        data = request.get_json()
        
        account_value = data.get('account_value')
        risk_per_trade_pct = data.get('risk_per_trade_pct', 2)
        entry_price = data.get('entry_price')
        stop_loss_price = data.get('stop_loss_price')
        
        if not all([account_value, entry_price, stop_loss_price]):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        position_sizing = risk_analyzer.calculate_position_sizing(
            account_value, risk_per_trade_pct, entry_price, stop_loss_price
        )
        
        return jsonify(position_sizing)
    
    except Exception as e:
        logger.error(f"Error calculating position sizing: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Phase 4: Portfolio Management & Market Intelligence API Endpoints
# ============================================================================

@app.route('/api/market/vix', methods=['GET'])
def get_vix():
    """Get current VIX data with interpretation"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        vix_data = volatility_monitor.get_vix_data()
        
        if not vix_data:
            return jsonify({'error': 'VIX data not available'}), 503
        
        return jsonify(vix_data)
    
    except Exception as e:
        logger.error(f"Error fetching VIX data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/volatility-indices', methods=['GET'])
def get_volatility_indices():
    """Get all major volatility indices (VIX, VXN, RVX)"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        indices = volatility_monitor.get_all_volatility_indices()
        return jsonify(indices)
    
    except Exception as e:
        logger.error(f"Error fetching volatility indices: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/snapshot', methods=['GET'])
def get_market_snapshot():
    """Get quick market overview"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        snapshot = volatility_monitor.get_market_snapshot()
        
        if not snapshot:
            return jsonify({'error': 'Market snapshot not available'}), 503
        
        return jsonify(snapshot)
    
    except Exception as e:
        logger.error(f"Error fetching market snapshot: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/fear-greed', methods=['GET'])
def get_fear_greed():
    """Get Fear & Greed Index"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        fear_greed = volatility_monitor.get_fear_greed_index()
        return jsonify(fear_greed)
    
    except Exception as e:
        logger.error(f"Error calculating fear & greed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/volatile-stocks', methods=['GET'])
def get_volatile_stocks():
    """Get top volatile stocks with comprehensive metrics"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(limit, 100)  # Cap at 100
        
        volatile_stocks = volatility_monitor.get_top_volatile_stocks(limit=limit)
        
        return jsonify({
            'count': len(volatile_stocks),
            'stocks': volatile_stocks,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error fetching volatile stocks: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/fastest-movers', methods=['GET'])
def get_fastest_movers():
    """Get fastest moving stocks by daily % change"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        limit = request.args.get('limit', 25, type=int)
        limit = min(limit, 50)
        
        fastest = volatility_monitor.get_fastest_movers(limit=limit)
        
        return jsonify({
            'count': len(fastest),
            'movers': fastest,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error fetching fastest movers: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/volume-leaders', methods=['GET'])
def get_volume_leaders():
    """Get stocks with highest volume surges"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        limit = request.args.get('limit', 25, type=int)
        limit = min(limit, 50)
        
        volume_leaders = volatility_monitor.get_volume_leaders(limit=limit)
        
        return jsonify({
            'count': len(volume_leaders),
            'leaders': volume_leaders,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error fetching volume leaders: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market/momentum-stocks', methods=['GET'])
def get_momentum_stocks():
    """Get stocks with strongest momentum"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        limit = request.args.get('limit', 25, type=int)
        limit = min(limit, 50)
        
        momentum_stocks = volatility_monitor.get_high_momentum_stocks(limit=limit)
        
        return jsonify({
            'count': len(momentum_stocks),
            'stocks': momentum_stocks,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error fetching momentum stocks: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio', methods=['GET'])
@require_api_auth
def get_portfolio():
    """Get complete portfolio analysis"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = current_user.id
        analysis = portfolio_analyzer.analyze_portfolio(user_id)
        
        if not analysis:
            return jsonify({'error': 'Could not analyze portfolio'}), 500
        
        return jsonify(analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing portfolio: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holding/<int:holding_id>', methods=['GET'])
@require_api_auth
def get_holding_analysis(holding_id):
    """Get detailed analysis of specific holding"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        holding_type = request.args.get('type', 'stock')
        analysis = portfolio_analyzer.analyze_holding(holding_id, holding_type)
        
        if not analysis:
            return jsonify({'error': 'Holding not found'}), 404
        
        logger.info(f"Holding {holding_id} analysis: {analysis.get('symbol')} - Recommendation: {analysis.get('recommendation', {}).get('action', 'N/A')}")
        return jsonify(analysis)
    
    except Exception as e:
        logger.error(f"Error analyzing holding {holding_id}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holding/<int:holding_id>', methods=['DELETE'])
@require_api_auth
def delete_holding(holding_id):
    """Delete a portfolio holding"""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    
    try:
        user_id = current_user.id
        
        holding = Portfolio.query.filter_by(id=holding_id, user_id=user_id).first()
        if not holding:
            return jsonify({'error': 'Holding not found'}), 404
        
        db.session.delete(holding)
        db.session.commit()
        
        logger.info(f"Deleted holding {holding.symbol} (ID: {holding_id}) for user {user_id}")
        return jsonify({'message': 'Holding deleted successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error deleting holding {holding_id}: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/holding/<int:holding_id>', methods=['PUT'])
@require_api_auth
def update_holding(holding_id):
    """Update a portfolio holding (e.g., cost basis)"""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    
    try:
        user_id = current_user.id
        data = request.get_json()
        
        holding = Portfolio.query.filter_by(id=holding_id, user_id=user_id).first()
        if not holding:
            return jsonify({'error': 'Holding not found'}), 404
        
        if 'cost_basis' in data:
            holding.average_cost = float(data['cost_basis'])
        
        if 'purchase_date' in data:
            purchase_date = data['purchase_date']
            if purchase_date:
                try:
                    from datetime import datetime
                    holding.purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))
                except:
                    pass
        
        db.session.commit()
        
        logger.info(f"Updated holding {holding.symbol} (ID: {holding_id}) for user {user_id}")
        return jsonify({'message': 'Holding updated successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error updating holding {holding_id}: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/transaction', methods=['POST'])
@require_api_auth
def record_portfolio_transaction():
    """Record a sell transaction or position adjustment"""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    
    try:
        user_id = current_user.id
        data = request.get_json()
        
        holding_id = data.get('holding_id')
        transaction_type = data.get('transaction_type', 'sell')
        quantity = data.get('quantity')
        price = float(data.get('price', 0))
        sell_all = data.get('sell_all', False)
        
        holding = Portfolio.query.filter_by(id=holding_id, user_id=user_id).first()
        if not holding:
            return jsonify({'error': 'Holding not found'}), 404
        
        # Record transaction in Transaction table
        transaction = Transaction(
            user_id=user_id,
            symbol=holding.symbol,
            asset_type='stock',
            transaction_type=transaction_type,
            quantity=quantity if quantity else holding.quantity,
            price=price,
            transaction_date=datetime.utcnow()
        )
        db.session.add(transaction)
        
        # Update or delete holding
        if sell_all or (quantity and quantity >= holding.quantity):
            # Selling entire position
            db.session.delete(holding)
            logger.info(f"Sold all of {holding.symbol} at ${price} for user {user_id}")
        elif quantity:
            # Partial sell
            holding.quantity -= quantity
            logger.info(f"Sold {quantity} shares of {holding.symbol} at ${price} for user {user_id}")
        
        db.session.commit()
        
        return jsonify({'message': 'Transaction recorded successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error recording transaction: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/rebalance', methods=['GET'])
@require_api_auth
def get_rebalancing_suggestions():
    """Get portfolio rebalancing suggestions"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = current_user.id
        suggestions = portfolio_analyzer.get_rebalancing_suggestions(user_id)
        
        return jsonify({'suggestions': suggestions})
    
    except Exception as e:
        logger.error(f"Error generating rebalancing suggestions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['GET'])
@require_api_auth
def get_alerts():
    """Get all active alerts for user"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = current_user.id
        
        from models import Alert
        alerts = Alert.query.filter_by(
            user_id=user_id,
            status='active'
        ).all()
        
        return jsonify({'alerts': [alert.to_dict() for alert in alerts]})
    
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/triggered', methods=['GET'])
@require_api_auth
def get_triggered_alerts():
    """Get recently triggered alerts"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = current_user.id
        triggered = smart_alerts.get_triggered_alerts(user_id)
        
        return jsonify({'alerts': triggered})
    
    except Exception as e:
        logger.error(f"Error fetching triggered alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['POST'])
@require_api_auth
def create_alert():
    """Create a new smart alert"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        data = request.get_json()
        user_id = current_user.id
        
        symbol = data.get('symbol')
        alert_type = data.get('alert_type')
        condition = data.get('condition')
        priority = data.get('priority', 'medium')
        
        if not all([symbol, alert_type, condition]):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        alert = smart_alerts.create_alert(
            user_id=user_id,
            symbol=symbol,
            alert_type=alert_type,
            condition=condition,
            priority=priority
        )
        
        if alert:
            return jsonify(alert.to_dict()), 201
        else:
            return jsonify({'error': 'Failed to create alert'}), 500
    
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@require_api_auth
def delete_alert(alert_id):
    """Delete an alert"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        success = smart_alerts.delete_alert(alert_id)
        
        if success:
            return jsonify({'message': 'Alert deleted'}), 200
        else:
            return jsonify({'error': 'Alert not found'}), 404
    
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts/<int:alert_id>/dismiss', methods=['PUT'])
@require_api_auth
def dismiss_alert(alert_id):
    """Dismiss/acknowledge an alert"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        success = smart_alerts.dismiss_alert(alert_id)
        
        if success:
            return jsonify({'message': 'Alert dismissed'}), 200
        else:
            return jsonify({'error': 'Alert not found'}), 404
    
    except Exception as e:
        logger.error(f"Error dismissing alert: {e}")
        return jsonify({'error': str(e)}), 500

# ===========================
# PHASE 5: AI ALERT SUGGESTIONS
# ===========================

@app.route('/api/alert-suggestions', methods=['GET'])
@require_api_auth
def get_alert_suggestions():
    """Get pending AI-generated alert suggestions"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Alert suggestions not available'}), 503
    
    try:
        # Get existing active alerts to filter out matching suggestions
        existing_alerts = []
        try:
            active_alerts = Alert.query.filter_by(
                user_id=current_user.id,
                status='active',
                enabled=True
            ).all()
            existing_alerts = [a.to_dict() for a in active_alerts]
            
            # Clean up suggestions that match existing alerts
            alert_suggestions.cleanup_matching_alerts(existing_alerts)
        except Exception as e:
            logger.warning(f"Could not filter existing alerts: {e}")
        
        suggestions = alert_suggestions.get_pending_suggestions(limit=20)
        return jsonify({
            'suggestions': [s.to_dict() for s in suggestions],
            'count': len(suggestions)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching alert suggestions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alert-suggestions/generate', methods=['POST'])
@require_api_auth
def generate_alert_suggestions():
    """Generate new alert suggestions for watchlist and portfolio"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Alert suggestions not available'}), 503
    
    try:
        data = request.get_json() or {}
        symbols = data.get('symbols', [])
        
        # Get portfolio holdings if available
        portfolio_holdings = []
        if PHASE2_ENABLED:
            holdings = Portfolio.query.filter_by(user_id=current_user.id).all()
            portfolio_holdings = [h.to_dict() for h in holdings]
            
            # Add portfolio symbols to watchlist
            for h in holdings:
                if h.symbol not in symbols:
                    symbols.append(h.symbol)
        
        # Get existing active alerts to avoid duplicates
        existing_alerts = []
        try:
            active_alerts = Alert.query.filter_by(
                user_id=current_user.id,
                status='active',
                enabled=True
            ).all()
            existing_alerts = [a.to_dict() for a in active_alerts]
        except Exception as e:
            logger.warning(f"Could not fetch existing alerts: {e}")
        
        # Generate suggestions
        new_suggestions = alert_suggestions.generate_suggestions(symbols, portfolio_holdings)
        
        # Save to database (filtering out ones matching existing alerts)
        saved_count = alert_suggestions.save_suggestions(new_suggestions, existing_alerts)
        
        return jsonify({
            'message': f'Generated {len(new_suggestions)} suggestions, saved {saved_count} new ones',
            'suggestions': new_suggestions
        }), 200
    
    except Exception as e:
        logger.error(f"Error generating alert suggestions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alert-suggestions/<int:suggestion_id>/accept', methods=['POST'])
@require_api_auth
def accept_alert_suggestion(suggestion_id):
    """Accept a suggestion and create an alert"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Alert suggestions not available'}), 503
    
    try:
        logger.info(f"User {current_user.id} accepting suggestion {suggestion_id}")
        
        # Accept the suggestion and get alert data
        alert_data = alert_suggestions.accept_suggestion(suggestion_id)
        
        if not alert_data:
            logger.error(f"Suggestion {suggestion_id} not found or already actioned")
            return jsonify({'error': 'Suggestion not found'}), 404
        
        logger.info(f"Creating alert from suggestion {suggestion_id}: {alert_data}")
        
        # Create condition dict for smart_alerts
        condition = {
            'metric': 'price',
            'operator': '>' if alert_data['type'] == 'high' else '<',
            'value': float(alert_data['price'])
        }
        
        # Create the actual alert
        alert = smart_alerts.create_alert(
            user_id=current_user.id,
            symbol=alert_data['symbol'],
            alert_type='price',
            condition=condition,
            priority='high'
        )
        
        if alert:
            logger.info(f"Alert created successfully: ID={alert.id} for {alert.symbol}")
            return jsonify({
                'message': 'Alert created successfully',
                'alert': alert.to_dict()
            }), 201
        else:
            logger.error("smart_alerts.create_alert returned None")
            return jsonify({'error': 'Failed to create alert - check server logs'}), 500
    
    except Exception as e:
        logger.error(f"Error accepting suggestion {suggestion_id}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/alert-suggestions/<int:suggestion_id>/dismiss', methods=['POST'])
@require_api_auth
def dismiss_alert_suggestion(suggestion_id):
    """Dismiss a suggestion"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Alert suggestions not available'}), 503
    
    try:
        success = alert_suggestions.dismiss_suggestion(suggestion_id)
        
        if success:
            return jsonify({'message': 'Suggestion dismissed'}), 200
        else:
            return jsonify({'error': 'Suggestion not found'}), 404
    
    except Exception as e:
        logger.error(f"Error dismissing suggestion: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Politician Trading Data API Endpoints
# ============================================================================

@app.route('/api/politician-trades', methods=['GET'])
@require_api_auth
def get_politician_trades():
    """Get recent politician trades"""
    try:
        days = request.args.get('days', 30, type=int)
        politician_tracker = PoliticianTradeTracker()
        trades = politician_tracker.get_recent_trades(days=days)
        
        return jsonify({
            'trades': trades,
            'count': len(trades)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching politician trades: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/politician-trades/trending', methods=['GET'])
@require_api_auth
def get_trending_politician_stocks():
    """Get trending stocks among politicians"""
    try:
        politician_tracker = PoliticianTradeTracker()
        trending = politician_tracker.get_trending_symbols()
        
        return jsonify({
            'trending': trending
        }), 200
    except Exception as e:
        logger.error(f"Error fetching trending stocks: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/politician-trades/symbol/<symbol>', methods=['GET'])
@require_api_auth
def get_politician_trades_by_symbol(symbol):
    """Get politician trades for a specific symbol"""
    try:
        politician_tracker = PoliticianTradeTracker()
        trades = politician_tracker.search_by_symbol(symbol)
        
        return jsonify({
            'symbol': symbol,
            'trades': trades,
            'count': len(trades)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching trades for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/politician-trades/performance', methods=['GET'])
@require_api_auth
def get_politician_performance():
    """Get performance metrics by politician"""
    try:
        politician_name = request.args.get('politician')
        politician_tracker = PoliticianTradeTracker()
        performance = politician_tracker.get_politician_performance(politician_name)
        
        return jsonify({
            'politicians': performance
        }), 200
    except Exception as e:
        logger.error(f"Error fetching politician performance: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# Feature #3: News & Events Feed API Endpoints
# ============================================================================

@app.route('/api/news/market', methods=['GET'])
@require_api_auth
def get_market_news():
    """Get general market news"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'News feed not available'}), 503
    
    try:
        limit = request.args.get('limit', 20, type=int)
        news = news_fetcher.get_market_news(limit=limit)
        
        return jsonify({
            'news': news,
            'count': len(news)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching market news: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/symbol/<symbol>', methods=['GET'])
@require_api_auth
def get_symbol_news(symbol):
    """Get news for a specific symbol"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'News feed not available'}), 503
    
    try:
        limit = request.args.get('limit', 10, type=int)
        news = news_fetcher.get_symbol_news(symbol.upper(), limit=limit)
        
        return jsonify({
            'symbol': symbol.upper(),
            'news': news,
            'count': len(news)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/earnings', methods=['GET'])
@require_api_auth
def get_earnings_calendar():
    """Get upcoming earnings calendar"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Earnings calendar not available'}), 503
    
    try:
        days_ahead = request.args.get('days', 7, type=int)
        earnings = news_fetcher.get_earnings_calendar(days_ahead=days_ahead)
        
        return jsonify({
            'earnings': earnings,
            'count': len(earnings),
            'days_ahead': days_ahead
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching earnings calendar: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/trending', methods=['GET'])
@require_api_auth
def get_trending_tickers():
    """Get trending tickers with news"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trending tickers not available'}), 503
    
    try:
        limit = request.args.get('limit', 10, type=int)
        trending = news_fetcher.get_trending_tickers(limit=limit)
        
        return jsonify({
            'trending': trending,
            'count': len(trending)
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching trending tickers: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/market-summary', methods=['GET'])
@require_api_auth
def get_market_summary():
    """Get market summary with news sentiment"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Market summary not available'}), 503
    
    try:
        summary = news_fetcher.get_market_summary()
        return jsonify(summary), 200
    
    except Exception as e:
        logger.error(f"Error fetching market summary: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Correlation & Heat Map API Endpoints (Feature #4)
# ============================================================================

@app.route('/api/correlation/matrix', methods=['GET'])
@require_api_auth
def get_correlation_matrix():
    """Get portfolio correlation matrix"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Correlation analysis not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        period = request.args.get('period', '3mo')
        result = correlation_analyzer.get_portfolio_correlation_matrix(user_id, period)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching correlation matrix: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/correlation/diversification', methods=['GET'])
@require_api_auth
def get_diversification():
    """Get portfolio diversification metrics"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Diversification analysis not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        result = correlation_analyzer.get_diversification_metrics(user_id)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching diversification metrics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/correlation/time-series', methods=['GET'])
@require_api_auth
def get_correlation_time_series():
    """Get correlation over different time periods"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Correlation time series not available'}), 503
    
    try:
        symbols = request.args.get('symbols', '').split(',')
        if len(symbols) != 2:
            return jsonify({'error': 'Provide exactly 2 symbols separated by comma'}), 400
        
        result = correlation_analyzer.get_correlation_over_time(symbols)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching correlation time series: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Trade Journal & Analytics API Endpoints (Feature #5)
# ============================================================================

@app.route('/api/journal/history', methods=['GET'])
@require_api_auth
def get_journal_history():
    """Get trade history with summary metrics"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        result = trade_journal.get_trade_history(user_id, days)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/performance', methods=['GET'])
@require_api_auth
def get_journal_performance():
    """Get trading performance analysis"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        result = trade_journal.analyze_performance(user_id, days)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error analyzing performance: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/insights', methods=['GET'])
@require_api_auth
def get_journal_insights():
    """Get AI-powered trading insights"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        result = trade_journal.get_ai_insights(user_id, days)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error generating AI insights: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/note', methods=['POST'])
@require_api_auth
def save_trade_note():
    """Add or update note for a transaction"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        # Get user_id from either session or current_user
        user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else None)
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        data = request.get_json()
        transaction_id = data.get('transaction_id')
        note = data.get('note', '')
        
        if not transaction_id:
            return jsonify({'error': 'transaction_id required'}), 400
        
        result = trade_journal.add_trade_note(transaction_id, user_id, note)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error saving trade note: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("="*70)
    print("🚀 Financial Chart Analyzer with Local LLM")
    print("="*70)
    print(f"📊 Main Dashboard: http://localhost:{app.config['FLASK_PORT']}")
    print(f"💼 Portfolio: http://localhost:{app.config['FLASK_PORT']}/portfolio")
    print(f"🎯 Copy Trading: http://localhost:{app.config['FLASK_PORT']}/copytrading")
    print(f"🤖 LLM Model: {app.config['OLLAMA_MODEL']}")
    
    if PHASE2_ENABLED:
        print("="*70)
        print("✅ PHASE 2 FEATURES ENABLED")
        print("="*70)
        print("🔐 Authentication: Google OAuth")
        print("💾 Database: SQLite (local)")
        print("📈 Portfolio Tracking: Enabled")
        print("🧠 ML Patterns: Enabled")
    
    if PHASE3_ENABLED:
        print("="*70)
        print("✅ PHASE 3 FEATURES ENABLED")
        print("="*70)
        print("📊 Options Analysis with Greeks")
        print("⏰ Trading Time Intelligence")
        print("💭 Multi-Source Sentiment Analysis")
        print("⚠️  Advanced Risk Assessment")
    
    if PHASE4_ENABLED:
        print("="*70)
        print("✅ PHASE 4 FEATURES ENABLED")
        print("="*70)
        print("📈 Portfolio Analytics & P&L Tracking")
        print("🔔 Smart Alerts System")
        print("📉 VIX & Volatility Monitoring")
        print("💰 Position-Specific Recommendations")
    
    if not PHASE2_ENABLED:
        print("="*70)
        print("ℹ️  PHASE 1 MODE (No Authentication)")
        print("="*70)
        print("   Run 'install_phase2.bat' to enable Phase 2 features")
    elif PHASE2_ENABLED and not PHASE3_ENABLED:
        print("")
        print("⚠️  Phase 3 not enabled - run 'install_phase3.bat'")
    elif PHASE3_ENABLED and not PHASE4_ENABLED:
        print("")
        print("⚠️  Phase 4 not enabled - modules may not be installed")
    else:
        print("")
        print("✅ ALL FEATURES ENABLED - Full Trading Intelligence Platform")
    
    if PHASE2_ENABLED and not os.path.exists('.env'):
        print("")
        print("⚠️  SETUP REQUIRED:")
        print("   1. Create .env file with Google OAuth credentials")
        print("   2. See PHASE2_SETUP.md for instructions")
    
    print("="*70)
    
    app.run(
        host='0.0.0.0',
        port=app.config['FLASK_PORT'],
        debug=app.config['FLASK_DEBUG']
    )
