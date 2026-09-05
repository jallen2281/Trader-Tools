"""Flask web application for financial chart analysis with local LLM."""

# Fix UTF-8 encoding for Windows PowerShell
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from flask_login import login_required, current_user, logout_user
from functools import wraps
from data_fetcher import FinancialDataFetcher, normalize_crypto_symbol
from chart_generator import ChartGenerator
from pattern_recognizer import PatternRecognizer
from llm_analyzer import LLMAnalyzer
from claude_analyzer import ClaudeAnalyzer
from gemini_analyzer import GeminiAnalyzer
from tax_analyzer import TaxAnalyzer
from config import Config
from datetime import datetime, timedelta, date
import json
import csv
import hashlib
import traceback
import pandas as pd
import os

# Phase 2: Database and Authentication
try:
    from models import db, User, Watchlist, Alert, Portfolio, Transaction, OptionsPosition, AnalysisHistory, MLPattern, MLPrediction, PortfolioSnapshot, PortfolioAccount, Dividend, DiscussionThread, ThreadReply, ThreadVote, CopyTradingFollow, Notification, PaperTrade, TradingSOP, Group, FinanceAccount, Debt, AIInsight, IncomeSource, IncomeEvent, RecurringBill, BudgetCategory, SpendTransaction, PlaidItem, TaxDocument
    from db_config import init_database
    from auth import init_auth, get_auth_routes, require_api_auth
    from monitoring_service import init_monitoring_service, get_monitoring_service
    from ml_pattern_detector import MLPatternDetector
    PHASE2_ENABLED = True
except ImportError as e:
    print(f"⚠ Phase 2 features not available: {e}")
    print("ℹ Run 'install_phase2.bat' to enable database and authentication")
    PHASE2_ENABLED = False
    # Define dummy decorator for when auth is not available
    def require_api_auth(f):
        """Dummy auth decorator when Phase 2 is disabled"""
        return f

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


from werkzeug.middleware.proxy_fix import ProxyFix

def _get_current_user_id():
    """Safely get current user ID without requiring login_manager"""
    uid = session.get('user_id')
    if uid:
        return uid
    try:
        if hasattr(app, 'login_manager') and current_user.is_authenticated:
            return current_user.id
    except Exception:
        pass
    return None

app = Flask(__name__)
app.config.from_object(Config)
# Cap uploads (tax docs / receipts) at 15 MB — plenty for a PDF/photo, and it bounds the
# Postgres blob size. Larger uploads get a 413.
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

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
        
        # Base tick 60s; each user's own alert_check_interval gates actual checks
        monitoring_svc = init_monitoring_service(app, check_interval=60)
        logger.info("✓ Real-time Monitoring Service initialized (60s base tick, per-user intervals)")
        
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
    claude_analyzer = ClaudeAnalyzer()
    logger.info("✓ ClaudeAnalyzer initialized (available=%s)", claude_analyzer.available())
    gemini_analyzer = GeminiAnalyzer()
    logger.info("✓ GeminiAnalyzer initialized (available=%s)", gemini_analyzer.available())
    tax_analyzer = TaxAnalyzer()
    logger.info("✓ TaxAnalyzer initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize LLMAnalyzer: {e}")
    raise


def cached_ai_read(user_id, kind, system, facts, *, ttl_minutes=360, tier='default',
                   max_tokens=500, refresh=False):
    """Cost-controlled AI read: Claude → Gemini → local, memoized in AIInsight.

    The result is keyed by sha256(model|system|facts); an unchanged request within
    ttl_minutes is served from the DB with NO model call (the main AI cost control).
    tier='high' escalates the Claude call to the Opus model for high-stakes reasoning.
    Returns a dict shaped like the endpoints' JSON: {read, engine, model, cached}.
    Pass refresh=True (e.g. from ?refresh=1) to force a regeneration.
    """
    model = claude_analyzer.model_high if tier == 'high' else claude_analyzer.model
    input_hash = hashlib.sha256(f"{model}\x1f{system}\x1f{facts}".encode('utf-8')).hexdigest()
    now = datetime.utcnow()

    if not refresh:
        try:
            hit = (AIInsight.query
                   .filter_by(user_id=user_id, kind=kind, input_hash=input_hash)
                   .filter(AIInsight.expires_at > now)
                   .order_by(AIInsight.created_at.desc()).first())
            if hit:
                return hit.to_dict()
        except Exception as e:
            logger.warning(f"cached_ai_read lookup failed ({kind}): {e}")

    # Miss (or forced refresh) — run the fallback chain.
    read = claude_analyzer.read(system, facts, max_tokens=max_tokens, model=model)
    engine, used_model = ('claude', model) if read else (None, None)
    if not read:
        read = gemini_analyzer.read(system, facts)
        engine, used_model = ('gemini', gemini_analyzer._resolved_model or gemini_analyzer.model) if read else (None, None)
    if not read:
        try:
            local = llm_analyzer._call_llm([{'role': 'user', 'content': system + '\n\n' + facts}], timeout=60)
            if local and not (local.lstrip().startswith("{'") or "'choices'" in local or 'rkllm_chat' in local):
                read, engine, used_model = local, 'local', getattr(Config, 'FALLBACK_MODEL', 'local')
        except Exception as e:
            logger.warning(f"cached_ai_read local fallback failed ({kind}): {e}")
    if not read:
        return {'empty': True, 'message': 'AI is unavailable right now.', 'cached': False}

    read = read.strip()
    try:
        db.session.add(AIInsight(
            user_id=user_id, kind=kind, input_hash=input_hash, engine=engine,
            model=used_model, content=read, created_at=now,
            expires_at=now + timedelta(minutes=ttl_minutes)))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"cached_ai_read store failed ({kind}): {e}")
    return {'read': read, 'engine': engine, 'model': used_model, 'cached': False}



def _can_use_ai():
    """Whether the caller may spend a paid AI call ('ai_analysis' permission).

    Admins bypass, per _effective_permissions. A newly registered account belongs to no
    group and therefore holds no permissions, so open registration cannot burn the API key.
    """
    uid = _get_current_user_id()
    if not uid:
        return False
    return user_has_permission(User.query.get(uid), 'ai_analysis')


def require_perm(perm):
    """Call-time permission gate, for routes defined above the RBAC block.

    Same import-order constraint as require_ai_permission: decorators run at module load,
    and @require_permission is defined over a thousand lines further down.
    """
    def wrapper(f):
        @wraps(f)
        def inner(*args, **kwargs):
            uid = _get_current_user_id()
            user = User.query.get(uid) if uid else None
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            if not user_has_permission(user, perm):
                return jsonify({'error': 'Permission denied', 'missing_permission': perm}), 403
            return f(*args, **kwargs)
        return inner
    return wrapper


def require_ai_permission(f):
    """Gate an endpoint that spends money on a paid AI provider.

    This exists instead of @require_permission('ai_analysis') purely because of import
    order: decorators are evaluated at module load, and several of these routes are defined
    over a thousand lines before the RBAC block. Wrapping the check in a call-time lookup
    sidesteps that without having to move working code.
    """
    @wraps(f)
    def inner(*args, **kwargs):
        if not _can_use_ai():
            return jsonify({'error': 'AI features require the "ai_analysis" permission. '
                                     'Ask an admin to grant it.',
                            'missing_permission': 'ai_analysis'}), 403
        return f(*args, **kwargs)
    return inner


# Initialize Trade Journal after LLM Analyzer (Feature #5)
if PHASE4_ENABLED and PHASE2_ENABLED:
    try:
        trade_journal = TradeJournal(llm_analyzer, claude_analyzer, gemini_analyzer)
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


# The consent version a signed-in user must have accepted. It covers BOTH documents shown
# on the consent page — the privacy policy and the terms of service — which is why it is
# not named after either one. Bump it whenever what a user is agreeing to changes
# materially: everyone is re-prompted on their next request, and the version they accepted
# is recorded, so consent stays auditable per revision.
#
# 2026-09-05: consent extended to cover the terms of service, not the privacy policy alone.
CONSENT_VERSION = '2026-09-05'

# Reachable without having accepted the current policy. /privacy and /consent obviously must
# be, /logout must be so "decline" is always possible, and /login|/authorize must be so the
# sign-in round-trip can complete before consent is even evaluated.
CONSENT_EXEMPT_PATHS = {'/consent', '/privacy', '/terms', '/login', '/authorize',
                        '/logout', '/health'}


@app.route('/privacy')
def privacy():
    """The privacy policy. Deliberately public — it has to be readable without an account,
    both for people deciding whether to sign up and for Plaid, which fetches the URL."""
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    """Terms of service. Public for the same reason as /privacy — someone deciding whether to
    sign up has to be able to read what they would be agreeing to, before they have an
    account and therefore before the consent gate applies."""
    return render_template('terms.html')


@app.before_request
def require_privacy_consent():
    """Gate the application on acceptance of the current privacy policy.

    This is a before_request hook rather than a decorator because consent has to cover all
    130+ authenticated endpoints — decorating them individually would mean touching every
    one and would silently miss every route added afterwards. Token-authenticated API
    callers get a machine-readable 403 instead of an HTML redirect they cannot act on.
    """
    if not PHASE2_ENABLED:
        return None
    if request.endpoint == 'static' or request.path.startswith('/static/'):
        return None
    if request.path in CONSENT_EXEMPT_PATHS:
        return None
    try:
        if not current_user.is_authenticated:
            return None
        if getattr(current_user, 'privacy_consent_version', None) == CONSENT_VERSION:
            return None
    except Exception:
        # Auth stack unavailable — fail open rather than locking the app on a hook error.
        return None
    if request.path.startswith('/api/') or request.headers.get('Authorization', '').startswith('Bearer '):
        return jsonify({'error': 'Privacy policy acceptance required',
                        'code': 'consent_required',
                        'policy_version': CONSENT_VERSION}), 403
    return redirect(url_for('consent'))


@app.route('/consent', methods=['GET', 'POST'])
def consent():
    """Collect explicit consent for collection, processing and storage before first use."""
    if not PHASE2_ENABLED:
        return redirect(url_for('index'))
    try:
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
    except Exception:
        return redirect(url_for('login'))
    if request.method == 'POST':
        if not request.form.get('accept'):
            return render_template('consent.html', version=CONSENT_VERSION,
                                   error='You must accept the privacy policy to continue.'), 400
        current_user.privacy_consent_at = datetime.utcnow()
        current_user.privacy_consent_version = CONSENT_VERSION
        db.session.commit()
        logger.info("Privacy consent recorded for user %s (version %s)",
                    current_user.id, CONSENT_VERSION)
        return redirect(url_for('index'))
    return render_template('consent.html', version=CONSENT_VERSION, error=None)


@app.route('/')
def index():
    """Public landing page for signed-out visitors; the dashboard for everyone else.

    This used to redirect anonymous visitors to /login, which immediately redirected
    off-domain to Google — so a visitor never saw a single page hosted here. Google OAuth
    verification requires a home page on the verified domain that describes what the app
    does and links the privacy policy, and a reviewer landing on a Google sign-in screen
    can see neither. The landing page is what they (and anyone deciding whether to sign up)
    actually get to read.
    """
    if PHASE2_ENABLED:
        try:
            authed = current_user.is_authenticated
        except Exception:
            authed = False
        if not authed:
            return render_template('landing.html')
    logger.debug("Rendering dashboard.html as main page")
    return render_template('dashboard.html')


@app.route('/api/test/yfinance', methods=['GET'])
def test_yfinance():
    """Test endpoint to verify Yahoo Finance connectivity."""
    try:
        symbol = request.args.get('symbol', 'AAPL')
        logger.info(f"Testing Yahoo Finance with symbol: {symbol}")
        
        # Try to fetch minimal data
        stock_data = data_fetcher.fetch_stock_data(symbol, period='5d', interval='1d')
        
        if stock_data is None:
            return jsonify({
                'status': 'failed',
                'error': 'No data returned from Yahoo Finance',
                'symbol': symbol,
                'message': 'Yahoo Finance API may be down or rate limiting'
            }), 503
        
        if stock_data.empty:
            return jsonify({
                'status': 'failed',
                'error': 'Empty data returned',
                'symbol': symbol,
                'message': 'Symbol may be invalid or data not available'
            }), 404
        
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'rows': len(stock_data),
            'columns': list(stock_data.columns),
            'latest_price': float(stock_data['Close'].iloc[-1]) if 'Close' in stock_data.columns else None,
            'message': 'Yahoo Finance connection working'
        }), 200
        
    except Exception as e:
        logger.error(f"Error testing Yahoo Finance: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': 'Exception during Yahoo Finance test'
        }), 500


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


@app.route('/tax')
@login_required
def tax_center():
    """Render the Tax Center — realized gains and (later) harvesting, wash sales, forms."""
    if not PHASE4_ENABLED:
        return "Tax features are not enabled", 503
    return render_template('tax.html')


@app.route('/paper')
@login_required
def paper_trading():
    """Render the Paper Trading module — simulate trades + expectancy stats."""
    if not PHASE4_ENABLED:
        return "Not available", 503
    return render_template('paper.html')


@app.route('/profile')
@login_required
def profile_page():
    """Profile & Settings hub — profile, preferences, and the Trading SOP."""
    return render_template('profile.html')


@app.route('/finances')
@login_required
def finances_page():
    """Personal finances — net worth, debts, cash flow, and an AI advisor."""
    return render_template('finances.html')


# ===================== PERSONAL FINANCES (net worth / debt / outlook) =====================

FINANCE_ACCOUNT_TYPES = {'checking', 'savings', 'cash', 'brokerage', 'retirement', 'property', 'vehicle', 'other'}
DEBT_TYPES = {'mortgage', 'heloc', 'home_equity', 'credit_card', 'auto', 'personal', 'student', 'home_improvement', 'other'}


def _finance_income(user):
    """Monthly gross income: sum of the user's active IncomeSource rows, falling back to
    the legacy preferences.monthlyGrossIncome number for users who haven't added sources."""
    try:
        rows = IncomeSource.query.filter_by(user_id=user.id, active=True).all()
        if rows:
            return round(sum(r.gross_monthly() for r in rows), 2)
    except Exception as e:
        logger.warning(f"_finance_income source sum failed: {e}")
    try:
        return float((user.preferences or {}).get('monthlyGrossIncome') or 0)
    except (TypeError, ValueError):
        return 0.0


def _seed_income_from_prefs(user):
    """One-time migration: if the user has a legacy preferences.monthlyGrossIncome but no
    IncomeSource rows yet, seed a single salaried source so the new UI shows their income."""
    try:
        if IncomeSource.query.filter_by(user_id=user.id).first():
            return
        monthly = float((user.preferences or {}).get('monthlyGrossIncome') or 0)
        if monthly <= 0:
            return
        db.session.add(IncomeSource(
            user_id=user.id, name='Primary income', owner='me', type='salary',
            annual_salary=round(monthly * 12.0, 2), pay_frequency='biweekly'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"_seed_income_from_prefs failed: {e}")


@app.route('/api/finance/accounts', methods=['GET'])
@require_api_auth
def finance_list_accounts():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    rows = FinanceAccount.query.filter_by(user_id=uid).order_by(FinanceAccount.balance.desc()).all()
    return jsonify({'accounts': [a.to_dict() for a in rows]})


@app.route('/api/finance/accounts', methods=['POST'])
@require_api_auth
def finance_create_account():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    t = (d.get('type') or 'cash').lower()
    a = FinanceAccount(user_id=uid, name=name[:120],
                       type=t if t in FINANCE_ACCOUNT_TYPES else 'other',
                       balance=float(d.get('balance') or 0), notes=(d.get('notes') or None))
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201


@app.route('/api/finance/accounts/<int:aid>', methods=['PUT', 'DELETE'])
@require_api_auth
def finance_modify_account(aid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    a = FinanceAccount.query.filter_by(id=aid, user_id=uid).first()
    if not a:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(a)
        db.session.commit()
        return jsonify({'success': True})
    d = request.get_json() or {}
    if 'name' in d and (d.get('name') or '').strip():
        a.name = d['name'].strip()[:120]
    if 'type' in d:
        t = (d.get('type') or 'cash').lower()
        a.type = t if t in FINANCE_ACCOUNT_TYPES else 'other'
    if 'balance' in d:
        a.balance = float(d.get('balance') or 0)
    if 'notes' in d:
        a.notes = d.get('notes') or None
    db.session.commit()
    return jsonify(a.to_dict())


@app.route('/api/finance/debts', methods=['GET'])
@require_api_auth
def finance_list_debts():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    rows = Debt.query.filter_by(user_id=uid).order_by(Debt.apr.desc()).all()
    return jsonify({'debts': [x.to_dict() for x in rows]})


@app.route('/api/finance/debts', methods=['POST'])
@require_api_auth
def finance_create_debt():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    t = (d.get('type') or 'other').lower()
    x = Debt(user_id=uid, name=name[:120], type=t if t in DEBT_TYPES else 'other',
             lender=(d.get('lender') or None), balance=float(d.get('balance') or 0),
             apr=float(d.get('apr') or 0), min_payment=float(d.get('min_payment') or 0),
             secured=bool(d.get('secured')), notes=(d.get('notes') or None))
    db.session.add(x)
    db.session.commit()
    return jsonify(x.to_dict()), 201


@app.route('/api/finance/debts/<int:did>', methods=['PUT', 'DELETE'])
@require_api_auth
def finance_modify_debt(did):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    x = Debt.query.filter_by(id=did, user_id=uid).first()
    if not x:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(x)
        db.session.commit()
        return jsonify({'success': True})
    d = request.get_json() or {}
    if 'name' in d and (d.get('name') or '').strip():
        x.name = d['name'].strip()[:120]
    if 'type' in d:
        t = (d.get('type') or 'other').lower()
        x.type = t if t in DEBT_TYPES else 'other'
    for f in ('lender', 'notes'):
        if f in d:
            setattr(x, f, d.get(f) or None)
    for f in ('balance', 'apr', 'min_payment'):
        if f in d:
            setattr(x, f, float(d.get(f) or 0))
    if 'secured' in d:
        x.secured = bool(d.get('secured'))
    db.session.commit()
    return jsonify(x.to_dict())


@app.route('/api/finance/income', methods=['PUT'])
@require_api_auth
def finance_set_income():
    """Store monthly gross income (for DTI) in the user's preferences."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    d = request.get_json() or {}
    try:
        inc = float(d.get('monthly_gross_income') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid income'}), 400
    current_user.preferences = {**(current_user.preferences or {}), 'monthlyGrossIncome': inc}
    db.session.commit()
    return jsonify({'success': True, 'monthly_gross_income': inc})


INCOME_SOURCE_TYPES = {'salary', 'hourly', 'self_employed', 'other'}
INCOME_OWNERS = {'me', 'spouse', 'joint', 'other'}
PAY_FREQUENCIES = {'weekly', 'biweekly', 'semimonthly', 'monthly'}
INCOME_TAX_FORMS = {'W2', '1099', 'none'}


def _apply_income_fields(x, d):
    """Copy validated income fields from request dict d onto IncomeSource x."""
    if 'name' in d and (d.get('name') or '').strip():
        x.name = d['name'].strip()[:120]
    if 'owner' in d:
        o = (d.get('owner') or 'me').lower()
        x.owner = o if o in INCOME_OWNERS else 'me'
    if 'type' in d:
        t = (d.get('type') or 'salary').lower()
        x.type = t if t in INCOME_SOURCE_TYPES else 'salary'
    if 'pay_frequency' in d:
        f = (d.get('pay_frequency') or 'biweekly').lower()
        x.pay_frequency = f if f in PAY_FREQUENCIES else 'biweekly'
    if 'tax_form' in d:
        tf = (d.get('tax_form') or 'W2')
        x.tax_form = tf if tf in INCOME_TAX_FORMS else 'W2'
    if 'irregular' in d:
        x.irregular = bool(d.get('irregular'))
    for f in ('annual_salary', 'hourly_rate', 'hours_per_week', 'ot_multiplier',
              'ot_threshold_hours', 'estimated_annual', 'est_tax_rate'):
        if f in d:
            try:
                setattr(x, f, float(d.get(f) or 0))
            except (TypeError, ValueError):
                pass
    if 'next_pay_date' in d:
        npd = (d.get('next_pay_date') or '').strip()
        try:
            x.next_pay_date = datetime.strptime(npd, '%Y-%m-%d').date() if npd else None
        except ValueError:
            x.next_pay_date = None
    if 'active' in d:
        x.active = bool(d.get('active'))


@app.route('/api/finance/incomes', methods=['GET'])
@require_api_auth
def finance_list_incomes():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    user = User.query.get(uid)
    _seed_income_from_prefs(user)  # one-time migration of the legacy single number
    rows = IncomeSource.query.filter_by(user_id=uid).order_by(IncomeSource.created_at).all()
    active = [r for r in rows if r.active]
    return jsonify({
        'incomes': [r.to_dict(include_events=True) for r in rows],
        'total_gross_monthly': round(sum(r.gross_monthly() for r in active), 2),
        'total_gross_annual': round(sum(r.gross_annual() for r in active), 2),
        'total_net_monthly': round(sum(r.net_monthly() for r in active), 2),
        'total_tax_setaside_monthly': round(sum(r.tax_setaside_monthly() for r in active), 2),
    })


@app.route('/api/finance/incomes', methods=['POST'])
@require_api_auth
def finance_create_income():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    x = IncomeSource(user_id=uid, name=name[:120])
    _apply_income_fields(x, d)
    db.session.add(x)
    db.session.commit()
    return jsonify(x.to_dict()), 201


@app.route('/api/finance/incomes/<int:iid>', methods=['PUT', 'DELETE'])
@require_api_auth
def finance_modify_income(iid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    x = IncomeSource.query.filter_by(id=iid, user_id=uid).first()
    if not x:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(x)
        db.session.commit()
        return jsonify({'success': True})
    _apply_income_fields(x, request.get_json() or {})
    db.session.commit()
    return jsonify(x.to_dict(include_events=True))


@app.route('/api/finance/incomes/<int:iid>/events', methods=['GET', 'POST'])
@require_api_auth
def finance_income_events(iid):
    """List or log actual payments (commission checks) against an irregular income source."""
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    src = IncomeSource.query.filter_by(id=iid, user_id=uid).first()
    if not src:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'GET':
        return jsonify({'events': [e.to_dict() for e in src.events]})
    d = request.get_json() or {}
    dt = (d.get('date') or '').strip()
    try:
        edate = datetime.strptime(dt, '%Y-%m-%d').date() if dt else date.today()
    except ValueError:
        return jsonify({'error': 'invalid date (YYYY-MM-DD)'}), 400
    try:
        amt = float(d.get('gross_amount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid gross_amount'}), 400
    ev = IncomeEvent(income_source_id=src.id, user_id=uid, date=edate,
                     gross_amount=amt, description=(d.get('description') or None))
    db.session.add(ev)
    db.session.commit()
    # Return the refreshed source (annualization now reflects the new event).
    return jsonify({'event': ev.to_dict(), 'source': src.to_dict(include_events=True)}), 201


@app.route('/api/finance/incomes/<int:iid>/events/<int:eid>', methods=['DELETE'])
@require_api_auth
def finance_delete_income_event(iid, eid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    ev = IncomeEvent.query.filter_by(id=eid, income_source_id=iid, user_id=uid).first()
    if not ev:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(ev)
    db.session.commit()
    return jsonify({'success': True})


BILL_FREQUENCIES = {'weekly', 'biweekly', 'semimonthly', 'monthly', 'quarterly', 'annual'}
BUDGET_KINDS = {'expense', 'savings', 'income'}
BUDGET_CATEGORIES = {'housing', 'utilities', 'transportation', 'insurance', 'food',
                     'debt', 'subscriptions', 'healthcare', 'childcare', 'savings',
                     'entertainment', 'personal', 'taxes', 'other'}


# Merchant/description keyword -> budget category, first match wins. Deliberately dumb and
# deterministic: auto-categorizing a 400-row import must not cost an AI call (see the Phase 0
# cost controls), and a wrong guess is one dropdown away from fixed.
SPEND_CATEGORY_RULES = [
    ('housing', ('rent', 'mortgage', 'hoa ', 'property mgmt', 'landlord')),
    ('utilities', ('electric', 'energy', 'water dept', 'sewer', 'utility', 'comcast', 'xfinity',
                   'verizon', 'at&t', 'spectrum', 't-mobile', 'internet')),
    ('transportation', ('shell', 'exxon', 'chevron', 'sunoco', 'wawa', 'speedway', 'uber', 'lyft',
                        'parking', 'toll', 'e-zpass', 'dmv', 'autozone', 'jiffy lube')),
    ('insurance', ('insurance', 'geico', 'allstate', 'progressive', 'state farm')),
    ('food', ('grocer', 'wegmans', 'kroger', 'safeway', 'aldi', 'trader joe', 'whole foods',
              'costco', 'walmart', 'target', 'restaurant', 'pizza', 'coffee', 'starbucks',
              'doordash', 'grubhub', 'ubereats', 'chipotle', 'mcdonald')),
    ('subscriptions', ('netflix', 'spotify', 'hulu', 'disney+', 'patreon', 'adobe', 'github',
                       'openai', 'anthropic', 'subscription', 'icloud', 'dropbox')),
    ('healthcare', ('pharmacy', 'cvs', 'walgreens', 'dental', 'medical', 'clinic', 'hospital',
                    'optometr', 'urgent care')),
    ('childcare', ('daycare', 'childcare', 'preschool', 'babysit')),
    ('entertainment', ('cinema', 'theater', 'steam games', 'playstation', 'xbox', 'concert',
                       'ticketmaster', 'stubhub')),
    ('debt', ('loan pmt', 'student loan', 'card payment', 'credit card pmt')),
    ('taxes', ('irs ', 'us treasury', 'tax pmt', 'franchise tax')),
]

# Date layouts seen in real bank exports, tried in order when no explicit date_format is given.
CSV_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d', '%d-%b-%Y', '%b %d, %Y',
                    '%m-%d-%Y', '%d/%m/%Y')


def _guess_spend_category(text):
    t = (text or '').lower()
    for cat, keys in SPEND_CATEGORY_RULES:
        if any(k in t for k in keys):
            return cat
    return 'other'


def _parse_csv_date(s, explicit=None):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ([explicit] if explicit else []) + list(CSV_DATE_FORMATS):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _parse_csv_amount(s):
    """Bank exports write money as '$1,234.56', '(45.00)' for negatives, or bare. Returns None
    if there is no number in there at all."""
    t = str(s or '').strip()
    if not t:
        return None
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace('$', '').replace(',', '').replace(' ', '')
    if not t:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _month_bounds(month=None):
    """('YYYY-MM' or None) -> (first_day, last_day). Defaults to the current month."""
    today = date.today()
    first = date(today.year, today.month, 1)
    if month:
        try:
            y, m = str(month).split('-')[:2]
            first = date(int(y), int(m), 1)
        except (ValueError, TypeError, IndexError):
            pass
    nxt = date(first.year + (1 if first.month == 12 else 0), (first.month % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


def _spend_actuals(user_id, start, end):
    """Actual spend per category over [start, end]. Refunds are negative, so they net out."""
    rows = SpendTransaction.query.filter(
        SpendTransaction.user_id == user_id,
        SpendTransaction.posted_at >= start,
        SpendTransaction.posted_at <= end).all()
    out = {}
    for t in rows:
        c = t.category or 'other'
        out[c] = round(out.get(c, 0) + float(t.amount or 0), 2)
    return out


def _apply_spend_fields(x, d):
    if 'posted_at' in d:
        s = (d.get('posted_at') or '').strip()
        pd_ = _parse_csv_date(s)
        if pd_:
            x.posted_at = pd_
    if 'description' in d and (d.get('description') or '').strip():
        x.description = d['description'].strip()[:200]
    if 'merchant' in d:
        x.merchant = (d.get('merchant') or None)
    if 'category' in d:
        c = (d.get('category') or 'other').lower()
        x.category = c if c in BUDGET_CATEGORIES else 'other'
    if 'amount' in d:
        try:
            x.amount = round(float(d.get('amount') or 0), 2)
        except (TypeError, ValueError):
            pass
    if 'account_id' in d:
        try:
            x.account_id = int(d['account_id']) if d.get('account_id') not in (None, '') else None
        except (TypeError, ValueError):
            x.account_id = None
    if 'pending' in d:
        x.pending = bool(d.get('pending'))
    if 'notes' in d:
        x.notes = (d.get('notes') or None)


def _apply_bill_fields(x, d):
    if 'name' in d and (d.get('name') or '').strip():
        x.name = d['name'].strip()[:120]
    if 'payee' in d:
        x.payee = (d.get('payee') or None)
    if 'category' in d:
        c = (d.get('category') or 'other').lower()
        x.category = c if c in BUDGET_CATEGORIES else 'other'
    if 'frequency' in d:
        f = (d.get('frequency') or 'monthly').lower()
        x.frequency = f if f in BILL_FREQUENCIES else 'monthly'
    if 'amount' in d:
        try:
            x.amount = float(d.get('amount') or 0)
        except (TypeError, ValueError):
            pass
    if 'due_day' in d:
        try:
            x.due_day = int(d['due_day']) if d.get('due_day') not in (None, '') else None
        except (TypeError, ValueError):
            x.due_day = None
    if 'next_due_date' in d:
        nd = (d.get('next_due_date') or '').strip()
        try:
            x.next_due_date = datetime.strptime(nd, '%Y-%m-%d').date() if nd else None
        except ValueError:
            x.next_due_date = None
    if 'autopay' in d:
        x.autopay = bool(d.get('autopay'))
    for f in ('linked_debt_id', 'from_account_id'):
        if f in d:
            try:
                setattr(x, f, int(d[f]) if d.get(f) not in (None, '') else None)
            except (TypeError, ValueError):
                setattr(x, f, None)
    if 'notes' in d:
        x.notes = (d.get('notes') or None)
    if 'active' in d:
        x.active = bool(d.get('active'))


@app.route('/api/finance/bills', methods=['GET', 'POST'])
@require_api_auth
def finance_bills():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    if request.method == 'GET':
        rows = RecurringBill.query.filter_by(user_id=uid).order_by(RecurringBill.category, RecurringBill.name).all()
        return jsonify({
            'bills': [b.to_dict() for b in rows],
            'total_monthly': round(sum(b.monthly_amount() for b in rows if b.active), 2),
        })
    d = request.get_json() or {}
    if not (d.get('name') or '').strip():
        return jsonify({'error': 'name is required'}), 400
    b = RecurringBill(user_id=uid, name='')
    _apply_bill_fields(b, d)
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


@app.route('/api/finance/bills/<int:bid>', methods=['PUT', 'DELETE'])
@require_api_auth
def finance_modify_bill(bid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    b = RecurringBill.query.filter_by(id=bid, user_id=uid).first()
    if not b:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(b)
        db.session.commit()
        return jsonify({'success': True})
    _apply_bill_fields(b, request.get_json() or {})
    db.session.commit()
    return jsonify(b.to_dict())


@app.route('/api/finance/budgets', methods=['GET', 'POST'])
@require_api_auth
def finance_budgets():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    if request.method == 'GET':
        month = request.args.get('month')
        return jsonify({'budgets': _budget_rollup(uid, month),
                        'month': _month_bounds(month)[0].strftime('%Y-%m')})
    d = request.get_json() or {}
    cat = (d.get('category') or '').strip().lower()
    if not cat:
        return jsonify({'error': 'category is required'}), 400
    cat = cat if cat in BUDGET_CATEGORIES else 'other'
    row = BudgetCategory.query.filter_by(user_id=uid, category=cat).first()
    if not row:
        row = BudgetCategory(user_id=uid, category=cat)
        db.session.add(row)
    try:
        row.monthly_limit = float(d.get('monthly_limit') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid monthly_limit'}), 400
    k = (d.get('kind') or 'expense').lower()
    row.kind = k if k in BUDGET_KINDS else 'expense'
    if 'notes' in d:
        row.notes = (d.get('notes') or None)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@app.route('/api/finance/budgets/<int:bid>', methods=['DELETE'])
@require_api_auth
def finance_delete_budget(bid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    row = BudgetCategory.query.filter_by(id=bid, user_id=uid).first()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({'success': True})


# ===================== PLAID: connected bank / brokerage accounts =====================
# Every route here is gated on 'plaid_link'. A newly registered account holds no
# permissions, so open registration can never reach anyone's banking data.

def _plaid():
    from plaid_client import PlaidClient
    return PlaidClient(Config.PLAID_CLIENT_ID, Config.PLAID_SECRET, Config.PLAID_ENV)


def _plaid_item_or_404(uid, iid):
    return PlaidItem.query.filter_by(id=iid, user_id=uid).first()


@app.route('/api/plaid/status', methods=['GET'])
@require_api_auth
@require_perm('plaid_link')
def plaid_status():
    """Whether Plaid is usable, without exposing which credentials are set."""
    import plaid_client as pc
    c = _plaid()
    return jsonify({
        'configured': c.available(),
        'environment': c.env,
        'encryption_ready': pc.encryption_ready(),
        'products': Config.PLAID_PRODUCTS,
    })


@app.route('/api/plaid/link-token', methods=['POST'])
@require_api_auth
@require_perm('plaid_link')
def plaid_link_token():
    """Mint a short-lived link_token for Plaid Link in the browser.

    Refuses up front when the encryption key is missing: better to fail before the user
    hands their bank credentials to Link than to succeed and discover afterwards that the
    resulting access token cannot be stored safely.
    """
    import plaid_client as pc
    uid = _get_current_user_id()
    if not pc.encryption_ready():
        return jsonify({'error': 'PLAID_ENCRYPTION_KEY is not configured; refusing to start '
                                 'a connection whose access token could not be encrypted.'}), 503
    d = request.get_json(silent=True) or {}
    access_token = None
    if d.get('item_id'):
        # Update mode — re-authenticate an item Plaid has flagged as login_required.
        item = _plaid_item_or_404(uid, d['item_id'])
        if not item:
            return jsonify({'error': 'Not found'}), 404
        access_token = pc.decrypt_token(item.access_token_enc)
    try:
        out = _plaid().link_token_create(uid, Config.PLAID_PRODUCTS, access_token=access_token)
    except pc.PlaidError as e:
        return jsonify({'error': str(e), 'code': e.code}), 502
    return jsonify({'link_token': out.get('link_token'), 'expiration': out.get('expiration')})


@app.route('/api/plaid/exchange', methods=['POST'])
@require_api_auth
@require_perm('plaid_link')
def plaid_exchange():
    """Trade the browser's public_token for a long-lived access_token and store it encrypted."""
    import plaid_client as pc
    uid = _get_current_user_id()
    d = request.get_json(silent=True) or {}
    public_token = (d.get('public_token') or '').strip()
    if not public_token:
        return jsonify({'error': 'public_token is required'}), 400
    client = _plaid()
    try:
        ex = client.exchange_public_token(public_token)
        access_token = ex['access_token']
        item_id = ex['item_id']
        inst_id, inst_name = None, None
        try:
            inst_id = ((client.item_get(access_token) or {}).get('item') or {}).get('institution_id')
            if inst_id:
                inst_name = ((client.institution_get(inst_id) or {}).get('institution') or {}).get('name')
        except pc.PlaidError:
            pass          # naming the institution is cosmetic; never fail the connect over it
    except pc.PlaidError as e:
        return jsonify({'error': str(e), 'code': e.code}), 502
    except KeyError:
        return jsonify({'error': 'Unexpected response from Plaid'}), 502

    item = PlaidItem.query.filter_by(user_id=uid, item_id=item_id).first()
    if not item:
        item = PlaidItem(user_id=uid, item_id=item_id)
        db.session.add(item)
    item.access_token_enc = pc.encrypt_token(access_token)
    item.institution_id = inst_id
    item.institution_name = inst_name
    item.status = 'active'
    item.last_error = None
    db.session.commit()
    logger.info("Plaid item connected for user %s (%s)", uid, inst_name or item_id)
    return jsonify(item.to_dict()), 201


@app.route('/api/plaid/items', methods=['GET'])
@require_api_auth
@require_perm('plaid_link')
def plaid_items():
    uid = _get_current_user_id()
    rows = PlaidItem.query.filter_by(user_id=uid).order_by(PlaidItem.created_at).all()
    return jsonify({'items': [i.to_dict() for i in rows]})


def _plaid_sync_item(item, client=None):
    """Pull everything new for one item into the spending ledger.

    Plaid's amount sign already matches SpendTransaction's: positive when money leaves the
    account. Income and transfers-in are skipped, exactly as the CSV importer skips deposits
    — money coming in belongs to the income module. Dedupe is by external_id
    'plaid:<transaction_id>', which is also what makes `removed` and `modified` resolvable.
    """
    import plaid_client as pc
    client = client or _plaid()
    token = pc.decrypt_token(item.access_token_enc)
    added = updated = removed = skipped = 0
    cursor = item.cursor
    for _ in range(50):                     # bounded: 50 * 500 transactions is plenty
        out = client.transactions_sync(token, cursor=cursor)
        for txn in out.get('added', []) + out.get('modified', []):
            if pc.is_income(txn):
                skipped += 1
                continue
            ext = 'plaid:%s' % txn.get('transaction_id')
            cat = pc.category_for(txn)
            if not cat:
                cat = _guess_spend_category('%s %s' % (txn.get('merchant_name') or '',
                                                       txn.get('name') or ''))
            posted = _parse_csv_date(txn.get('date'))
            if not posted:
                skipped += 1
                continue
            row = SpendTransaction.query.filter_by(user_id=item.user_id, external_id=ext).first()
            if row is None:
                row = SpendTransaction(user_id=item.user_id, external_id=ext, source='plaid')
                db.session.add(row)
                added += 1
            else:
                updated += 1
            row.posted_at = posted
            row.description = (txn.get('name') or 'Transaction')[:200]
            row.merchant = (txn.get('merchant_name') or None)
            row.category = cat
            row.amount = round(float(txn.get('amount') or 0), 2)
            row.pending = bool(txn.get('pending'))
        for txn in out.get('removed', []):
            ext = 'plaid:%s' % txn.get('transaction_id')
            n = SpendTransaction.query.filter_by(user_id=item.user_id, external_id=ext).delete(
                synchronize_session=False)
            removed += n
        cursor = out.get('next_cursor') or cursor
        if not out.get('has_more'):
            break
    item.cursor = cursor
    item.last_synced_at = datetime.utcnow()
    item.status = 'active'
    item.last_error = None
    db.session.commit()
    return {'added': added, 'updated': updated, 'removed': removed, 'skipped_income': skipped}


@app.route('/api/plaid/items/<int:iid>/sync', methods=['POST'])
@require_api_auth
@require_perm('plaid_link')
def plaid_sync(iid):
    import plaid_client as pc
    uid = _get_current_user_id()
    item = _plaid_item_or_404(uid, iid)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    try:
        return jsonify(_plaid_sync_item(item))
    except pc.PlaidError as e:
        db.session.rollback()
        # ITEM_LOGIN_REQUIRED is not a failure to retry — the user must re-authenticate
        # through Link in update mode, so surface it as its own state.
        item.status = 'login_required' if e.code == 'ITEM_LOGIN_REQUIRED' else 'error'
        item.last_error = str(e)[:255]
        db.session.commit()
        return jsonify({'error': str(e), 'code': e.code, 'status': item.status}), 502


@app.route('/api/plaid/sync', methods=['POST'])
@require_api_auth
@require_perm('plaid_link')
def plaid_sync_all():
    """Sync every connected item. One failing institution must not abort the others."""
    import plaid_client as pc
    uid = _get_current_user_id()
    results, totals = [], {'added': 0, 'updated': 0, 'removed': 0, 'skipped_income': 0}
    for item in PlaidItem.query.filter_by(user_id=uid).all():
        try:
            r = _plaid_sync_item(item)
            for k in totals:
                totals[k] += r[k]
            results.append({'item': item.to_dict(), **r})
        except pc.PlaidError as e:
            db.session.rollback()
            item.status = 'login_required' if e.code == 'ITEM_LOGIN_REQUIRED' else 'error'
            item.last_error = str(e)[:255]
            db.session.commit()
            results.append({'item': item.to_dict(), 'error': str(e), 'code': e.code})
    return jsonify({'totals': totals, 'results': results})


@app.route('/api/plaid/items/<int:iid>', methods=['DELETE'])
@require_api_auth
@require_perm('plaid_link')
def plaid_disconnect(iid):
    """Disconnect an institution.

    /item/remove is called first so the credential is dead on Plaid's side too, not merely
    deleted on ours — the retention policy promises the token is destroyed on disconnect.
    If that call fails the local row is still removed: keeping a token we can no longer use
    would be worse than orphaning one at Plaid.

    Transactions already imported are deliberately kept. They are the user's spending
    history and deleting them would silently rewrite past budgets; ?purge=1 removes them.
    """
    import plaid_client as pc
    uid = _get_current_user_id()
    item = _plaid_item_or_404(uid, iid)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    remote = True
    try:
        _plaid().item_remove(pc.decrypt_token(item.access_token_enc))
    except Exception as e:
        remote = False
        logger.warning("Plaid item_remove failed for item %s: %s", item.id, e)
    purged = 0
    if request.args.get('purge') == '1':
        purged = SpendTransaction.query.filter(
            SpendTransaction.user_id == uid,
            SpendTransaction.source == 'plaid',
            SpendTransaction.external_id.like('plaid:%')).delete(synchronize_session=False)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True, 'revoked_at_plaid': remote, 'transactions_purged': purged})


def _budget_rollup(user_id, month=None):
    """Per-category: the monthly limit vs what the category actually consumes this month.
    `actual_monthly` is real spend (SpendTransaction rows), `committed_monthly` is the
    recurring-bill floor. A bill that has already been paid appears in BOTH, so adding them
    would double-count it — the honest single number is the larger of the two. That is
    `projected_monthly`, and it is what `remaining` and `over` are measured against: early in
    the month committed leads (bills not yet paid), and as real spend lands actual takes over."""
    start, end = _month_bounds(month)
    budgets = BudgetCategory.query.filter_by(user_id=user_id).all()
    bills = RecurringBill.query.filter_by(user_id=user_id, active=True).all()
    actual = _spend_actuals(user_id, start, end)
    committed = {}
    for b in bills:
        committed[b.category] = round(committed.get(b.category, 0) + b.monthly_amount(), 2)

    def _row(cat, limit, base):
        com, act = committed.get(cat, 0), actual.get(cat, 0)
        proj = round(max(com, act), 2)
        return {**base, 'committed_monthly': com, 'actual_monthly': act,
                'projected_monthly': proj, 'remaining': round(limit - proj, 2),
                'over': proj > limit and limit > 0}

    out, seen = [], set()
    for cat in budgets:
        seen.add(cat.category)
        out.append(_row(cat.category, float(cat.monthly_limit or 0), cat.to_dict()))
    # categories that have bills or spend but no explicit budget row
    for cat in sorted(set(committed) | set(actual)):
        if cat not in seen:
            out.append(_row(cat, 0, {'id': None, 'category': cat, 'monthly_limit': 0,
                                     'kind': 'expense', 'notes': None}))
    out.sort(key=lambda r: -r['projected_monthly'])
    return out


@app.route('/api/finance/transactions', methods=['GET', 'POST'])
@require_api_auth
def finance_transactions():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    if request.method == 'GET':
        start, end = _month_bounds(request.args.get('month'))
        q = SpendTransaction.query.filter(SpendTransaction.user_id == uid,
                                          SpendTransaction.posted_at >= start,
                                          SpendTransaction.posted_at <= end)
        cat = (request.args.get('category') or '').lower()
        if cat in BUDGET_CATEGORIES:
            q = q.filter(SpendTransaction.category == cat)
        src = (request.args.get('source') or '').lower()
        if src in SpendTransaction.SOURCES:
            q = q.filter(SpendTransaction.source == src)
        term = (request.args.get('q') or '').strip()
        if term:
            like = '%{}%'.format(term)
            q = q.filter(db.or_(SpendTransaction.description.ilike(like),
                                SpendTransaction.merchant.ilike(like)))
        try:
            limit = min(max(int(request.args.get('limit', 250)), 1), 1000)
        except (TypeError, ValueError):
            limit = 250
        rows = q.order_by(SpendTransaction.posted_at.desc(),
                          SpendTransaction.id.desc()).limit(limit).all()
        by_cat = {}
        for t in rows:
            c = t.category or 'other'
            by_cat[c] = round(by_cat.get(c, 0) + float(t.amount or 0), 2)
        return jsonify({
            'month': start.strftime('%Y-%m'),
            'transactions': [t.to_dict() for t in rows],
            'total': round(sum(float(t.amount or 0) for t in rows), 2),
            'count': len(rows),
            'by_category': sorted([{'category': c, 'amount': a} for c, a in by_cat.items()],
                                  key=lambda r: -r['amount']),
        })
    d = request.get_json() or {}
    if not (d.get('description') or '').strip():
        return jsonify({'error': 'description is required'}), 400
    t = SpendTransaction(user_id=uid, description='', posted_at=date.today(), source='manual')
    _apply_spend_fields(t, d)
    if not (d.get('category') or '').strip():
        t.category = _guess_spend_category('{} {}'.format(d.get('merchant') or '',
                                                          d.get('description') or ''))
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@app.route('/api/finance/transactions/<int:tid>', methods=['PUT', 'DELETE'])
@require_api_auth
def finance_modify_transaction(tid):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    t = SpendTransaction.query.filter_by(id=tid, user_id=uid).first()
    if not t:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True})
    _apply_spend_fields(t, request.get_json() or {})
    db.session.commit()
    return jsonify(t.to_dict())


def _csv_text_from_request():
    """The CSV can arrive as an uploaded file or as a pasted `csv` string. Bank exports are
    routinely cp1252 (smart quotes in merchant names), so decoding falls back rather than 500s."""
    f = request.files.get('file')
    if f:
        raw = f.read(4 * 1024 * 1024)
        for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')
    if request.form.get('csv'):
        return request.form['csv']
    return ((request.get_json(silent=True) or {}).get('csv') or '')


@app.route('/api/finance/transactions/import-csv', methods=['POST'])
@require_api_auth
def finance_import_transactions_csv():
    """Two-step, so no bank's column names have to be known in advance. POST the file with no
    `mapping` and you get back the detected headers, sample rows, a guessed mapping and the
    sign the data implies; POST again with a confirmed `mapping` and the rows land.

    Re-importing an overlapping export is safe: each row gets external_id
    'csv:<sha1 of date|description|amount|account>', so a row already on file is skipped
    rather than counted twice."""
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    text_body = _csv_text_from_request()
    if not (text_body or '').strip():
        return jsonify({'error': 'No CSV supplied (send a `file` upload or a `csv` string)'}), 400

    try:
        dialect = csv.Sniffer().sniff(text_body[:8192], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text_body), dialect=dialect)
    headers = [h for h in (reader.fieldnames or []) if h and h.strip()]
    if not headers:
        return jsonify({'error': 'Could not read a header row from that CSV'}), 400
    rows = list(reader)
    if not rows:
        return jsonify({'error': 'That CSV has a header but no data rows'}), 400

    body = request.get_json(silent=True) or {}
    mapping = body.get('mapping')
    if not mapping and request.form.get('mapping'):
        try:
            mapping = json.loads(request.form['mapping'])
        except ValueError:
            return jsonify({'error': 'mapping is not valid JSON'}), 400

    def _pick(*cands):
        for h in headers:
            hl = h.strip().lower()
            for c in cands:
                if c in hl:
                    return h
        return None

    guessed = {'date': _pick('post date', 'posted', 'transaction date', 'date'),
               'description': _pick('description', 'name', 'memo', 'payee', 'merchant'),
               'amount': _pick('amount', 'debit'),
               'category': _pick('category')}

    if not mapping:
        # Which way does this file express a debit? Most exports write spend as negative, but
        # plenty write it positive. Decide from the data and let the user override.
        vals = [v for v in (_parse_csv_amount(r.get(guessed['amount'])) for r in rows[:200])
                if v is not None]
        negs = len([v for v in vals if v < 0])
        sign = 'debit_negative' if vals and negs >= len(vals) * 0.6 else 'debit_positive'
        return jsonify({
            'preview': True, 'headers': headers, 'row_count': len(rows),
            'guessed_mapping': guessed, 'guessed_sign': sign,
            'sample': [{h: r.get(h) for h in headers} for r in rows[:5]],
        })

    date_col, desc_col = mapping.get('date'), mapping.get('description')
    amt_col = mapping.get('amount')
    if not (date_col and desc_col and amt_col):
        return jsonify({'error': 'mapping needs at least date, description and amount'}), 400
    merch_col, cat_col = mapping.get('merchant'), mapping.get('category')
    date_format = mapping.get('date_format') or None
    flip = (mapping.get('sign') or 'debit_positive') == 'debit_negative'
    try:
        account_id = int(mapping['account_id']) if mapping.get('account_id') not in (None, '') else None
    except (TypeError, ValueError):
        account_id = None
    skip_income = bool(mapping.get('skip_income', True))

    existing = {e for (e,) in db.session.query(SpendTransaction.external_id)
                .filter(SpendTransaction.user_id == uid,
                        SpendTransaction.external_id.isnot(None)).all()}
    imported, dupes, invalid, skipped_income, seen = 0, 0, 0, 0, set()
    for r in rows:
        posted = _parse_csv_date(r.get(date_col), date_format)
        amt = _parse_csv_amount(r.get(amt_col))
        desc = (r.get(desc_col) or '').strip()
        if not posted or amt is None or not desc:
            invalid += 1
            continue
        if flip:
            amt = -amt
        # After normalization a negative row is money IN (a deposit or a refund). Deposits are
        # income and belong to the income module, so by default they stay out of spend.
        if amt < 0 and skip_income:
            skipped_income += 1
            continue
        amt = round(amt, 2)
        key = 'csv:' + hashlib.sha1('{}|{}|{}|{}'.format(
            posted.isoformat(), desc.lower(), amt, account_id or '').encode('utf-8')).hexdigest()[:24]
        if key in existing or key in seen:
            dupes += 1
            continue
        seen.add(key)
        merchant = (r.get(merch_col) or '').strip()[:160] if merch_col else None
        cat = (r.get(cat_col) or '').strip().lower() if cat_col else ''
        if cat not in BUDGET_CATEGORIES:
            cat = _guess_spend_category('{} {}'.format(merchant or '', desc))
        db.session.add(SpendTransaction(
            user_id=uid, posted_at=posted, description=desc[:200], merchant=merchant or None,
            category=cat, amount=amt, account_id=account_id, source='csv', external_id=key))
        imported += 1
    db.session.commit()
    return jsonify({'imported': imported, 'duplicates_skipped': dupes,
                    'income_rows_skipped': skipped_income, 'unparseable_rows': invalid,
                    'total_rows': len(rows)})


@app.route('/api/finance/transactions/import-receipts', methods=['POST'])
@require_api_auth
def finance_import_receipts():
    """Turn Phase 3's stored receipts into budget actuals. Only a receipt the AI (or the user)
    put an amount on can become a transaction; each is tied back to its TaxDocument by
    external_id 'receipt:<id>', so running this repeatedly only picks up what is new."""
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    docs = TaxDocument.query.filter_by(user_id=uid, doc_type='receipt').all()
    existing = {e for (e,) in db.session.query(SpendTransaction.external_id)
                .filter(SpendTransaction.user_id == uid,
                        SpendTransaction.external_id.like('receipt:%')).all()}
    imported, skipped, no_amount = 0, 0, 0
    for doc in docs:
        amt = round(float(doc.amount or 0), 2)
        if amt <= 0:
            no_amount += 1
            continue
        key = 'receipt:{}'.format(doc.id)
        if key in existing:
            skipped += 1
            continue
        merchant = doc.merchant or doc.issuer
        cat = (doc.category or '').lower()
        if cat not in BUDGET_CATEGORIES:
            cat = _guess_spend_category('{} {}'.format(merchant or '', doc.filename or ''))
        db.session.add(SpendTransaction(
            user_id=uid, posted_at=(doc.uploaded_at.date() if doc.uploaded_at else date.today()),
            description=(merchant or doc.filename or 'Receipt')[:200],
            merchant=(merchant or None), category=cat, amount=amt, source='receipt',
            external_id=key, tax_document_id=doc.id,
            notes='Imported from receipt #{}'.format(doc.id)))
        imported += 1
    db.session.commit()
    return jsonify({'imported': imported, 'already_imported': skipped,
                    'receipts_without_amount': no_amount, 'receipts_seen': len(docs)})


def _finance_cashflow(user_id, days=60, starting_balance=None):
    """Project inflows (scheduled paychecks) and outflows (recurring bills) over the next
    `days`, with a running balance. Irregular income is excluded (no schedule to project)."""
    today = date.today()
    horizon = today + timedelta(days=days)
    events = []
    for src in IncomeSource.query.filter_by(user_id=user_id, active=True).all():
        amt = src.paycheck_estimate()
        if src.irregular or amt <= 0:
            continue
        for pd in src.upcoming_paydates(12):
            if today <= pd <= horizon:
                events.append({'date': pd.isoformat(), 'label': src.name, 'amount': round(amt, 2), 'type': 'income'})
    for b in RecurringBill.query.filter_by(user_id=user_id, active=True).all():
        for dd in b.upcoming_due_dates(12):
            if today <= dd <= horizon:
                events.append({'date': dd.isoformat(), 'label': b.name, 'amount': -round(float(b.amount or 0), 2), 'type': 'bill'})
    events.sort(key=lambda e: e['date'])

    # Starting balance: caller-provided, else sum of liquid manual accounts (checking/savings/cash).
    if starting_balance is None:
        liquid = FinanceAccount.query.filter_by(user_id=user_id).all()
        starting_balance = round(sum(float(a.balance or 0) for a in liquid
                                     if a.type in ('checking', 'savings', 'cash')), 2)
    bal = float(starting_balance)
    lowest = bal
    for e in events:
        bal = round(bal + e['amount'], 2)
        e['running_balance'] = bal
        lowest = min(lowest, bal)
    return {
        'days': days, 'starting_balance': round(float(starting_balance), 2),
        'ending_balance': round(bal, 2), 'lowest_balance': round(lowest, 2),
        'total_in': round(sum(e['amount'] for e in events if e['amount'] > 0), 2),
        'total_out': round(sum(-e['amount'] for e in events if e['amount'] < 0), 2),
        'events': events,
    }


@app.route('/api/finance/cashflow', methods=['GET'])
@require_api_auth
def finance_cashflow():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    days = request.args.get('days', type=int) or 60
    days = max(7, min(days, 180))
    sb = request.args.get('starting_balance', type=float)
    try:
        return jsonify(_finance_cashflow(uid, days=days, starting_balance=sb))
    except Exception as e:
        logger.error(f"Error in cashflow: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def _finance_outlook(user_id):
    """Assemble the whole-picture outlook: assets (manual + investment accounts),
    debts, net worth, DTI, monthly debt service, blended APR, and interest drain."""
    user = User.query.get(user_id)
    manual = FinanceAccount.query.filter_by(user_id=user_id).all()
    debts = Debt.query.filter_by(user_id=user_id).order_by(Debt.apr.desc()).all()

    manual_assets = sum(float(a.balance or 0) for a in manual)

    # Fold in tracked investment accounts (PortfolioAccount cash + holdings market value).
    inv_accounts = []
    inv_total = 0.0
    try:
        for acct in PortfolioAccount.query.filter_by(user_id=user_id).all():
            cash = float(acct.cash_balance or 0)
            hv = 0.0
            for h in Portfolio.query.filter_by(user_id=user_id, account_id=acct.id).all():
                # Prefer live price, but fall back to cost basis (matches the rest of
                # the app). Non-quotable holdings (e.g. a 401k tracked as one lump lot)
                # never get a current_price, so bare current_price folded them in at $0.
                px = float(h.current_price) if h.current_price else float(h.average_cost or 0)
                hv += float(h.quantity or 0) * px
            val = cash + hv
            inv_accounts.append({'id': acct.id, 'name': acct.name, 'value': round(val, 2), 'cash': round(cash, 2)})
            inv_total += val
    except Exception as e:
        logger.warning(f"finance outlook: investment fold-in failed: {e}")

    total_assets = manual_assets + inv_total
    total_debt = sum(float(x.balance or 0) for x in debts)
    net_worth = total_assets - total_debt
    monthly_debt_service = sum(float(x.min_payment or 0) for x in debts)
    monthly_interest = sum(x.monthly_interest() for x in debts)
    blended_apr = round(sum(float(x.balance or 0) * float(x.apr or 0) for x in debts) / total_debt, 2) if total_debt else 0
    income = _finance_income(user)
    dti = round(monthly_debt_service / income * 100, 1) if income else None

    # Income sources + upcoming pay dates (merged across sources, soonest first).
    income_rows = IncomeSource.query.filter_by(user_id=user_id, active=True).all()
    paydates = []
    for r in income_rows:
        for d in r.upcoming_paydates(4):
            paydates.append({'date': d.isoformat(), 'source': r.name, 'amount': r.paycheck_estimate()})
    paydates.sort(key=lambda p: p['date'])

    # Un-withheld (1099) income needs a tax reserve — a big commission check isn't all spendable.
    tax_setaside_monthly = round(sum(r.tax_setaside_monthly() for r in income_rows), 2)
    net_monthly_income = round(sum(r.net_monthly() for r in income_rows), 2)
    has_irregular = any(r.irregular for r in income_rows)

    # Highlight the single most expensive debt (highest APR with a balance)
    worst = max((x for x in debts if float(x.balance or 0) > 0), key=lambda x: float(x.apr or 0), default=None)

    return {
        'net_worth': round(net_worth, 2),
        'total_assets': round(total_assets, 2),
        'manual_assets': round(manual_assets, 2),
        'investment_assets': round(inv_total, 2),
        'total_debt': round(total_debt, 2),
        'monthly_debt_service': round(monthly_debt_service, 2),
        'monthly_interest': round(monthly_interest, 2),
        'annual_interest': round(monthly_interest * 12, 2),
        'blended_apr': blended_apr,
        'monthly_gross_income': income,
        'annual_gross_income': round(income * 12, 2),
        'monthly_net_income': net_monthly_income,
        'monthly_tax_setaside': tax_setaside_monthly,
        'has_irregular_income': has_irregular,
        'dti': dti,
        'accounts': [a.to_dict() for a in manual],
        'investment_accounts': inv_accounts,
        'debts': [x.to_dict() for x in debts],
        'worst_debt': (worst.to_dict() if worst else None),
        'income_sources': [r.to_dict(include_events=True) for r in income_rows],
        'upcoming_paydates': paydates[:8],
    }


@app.route('/api/finance/outlook', methods=['GET'])
@require_api_auth
def finance_outlook():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        return jsonify(_finance_outlook(uid))
    except Exception as e:
        logger.error(f"Error in finance outlook: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/finance/ai-read', methods=['POST'])
@require_api_auth
@require_ai_permission
def finance_ai_read():
    """AI financial advisor — reads the outlook (+ optional question) and gives plain,
    prioritized guidance. Claude → Gemini fallback. Informational, not licensed advice."""
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        o = _finance_outlook(uid)
        question = (request.get_json() or {}).get('question') or ''
        debt_lines = "; ".join(
            f"{d['name']} ${d['balance']:,.0f} @ {d['apr']}%{' (secured)' if d['secured'] else ''}, min ${d['min_payment']:,.0f}/mo"
            for d in o['debts']
        ) or "none"
        irregular_note = ""
        if o.get('has_irregular_income'):
            irregular_note = (
                f"NOTE: some income is irregular 1099/commission (e.g. real-estate) — not withheld and lumpy. "
                f"Est. monthly tax set-aside: ${o.get('monthly_tax_setaside', 0):,.0f}; net after set-aside: "
                f"${o.get('monthly_net_income', 0):,.0f}/mo. Treat commission checks as partly owed to taxes "
                f"(income + ~15.3% self-employment tax) and remind about quarterly estimated payments.\n"
            )
        facts = (
            f"Net worth: ${o['net_worth']:,.0f} (assets ${o['total_assets']:,.0f} incl. ${o['investment_assets']:,.0f} investments; debt ${o['total_debt']:,.0f}).\n"
            f"Monthly gross income: ${o['monthly_gross_income']:,.0f}. DTI: {o['dti']}%.\n"
            + irregular_note
            + f"Monthly debt service: ${o['monthly_debt_service']:,.0f}. Debt interest drain: ${o['annual_interest']:,.0f}/yr (blended APR {o['blended_apr']}%).\n"
            f"Debts (highest-rate first): {debt_lines}.\n"
            + (f"Highest-rate debt: {o['worst_debt']['name']} at {o['worst_debt']['apr']}%.\n" if o['worst_debt'] else "")
            + (f"\nUser's question: {question}\n" if question else "")
        )
        system = (
            "You are a sharp, plain-spoken personal-finance advisor. Given the person's net worth, income, DTI, "
            "and their debts (with balances and APRs), give prioritized, specific guidance: name the single highest-cost "
            "problem (usually the highest-APR balance), quantify the interest drain, and lay out a concrete payoff/order "
            "plan (avalanche by APR, 0% balance-transfer or consolidation where it helps, using liquidity vs. borrowing). "
            "If they asked a specific question (e.g. how to finance a purchase), answer it directly and honestly — including "
            "'wait' or 'don't borrow against the house for a depreciating asset' when that's the right call. Be concrete with "
            "numbers. 6-10 sentences. End with one line: this is general education, not licensed financial advice — verify "
            "actual loan APRs and consider a fee-only advisor for big moves."
        )
        refresh = request.args.get('refresh') == '1' or bool((request.get_json(silent=True) or {}).get('refresh'))
        out = cached_ai_read(uid, 'finance_outlook', system, facts,
                             ttl_minutes=360, max_tokens=750, refresh=refresh)
        if out.get('empty'):
            return jsonify({'empty': True, 'message': 'AI advisor is unavailable right now.'}), 200
        return jsonify(out), 200
    except Exception as e:
        logger.error(f"Error in finance ai-read: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'AI advisor temporarily unavailable'}), 200


# ===================== TRADING SOP (Standard Operating Procedure) =====================

# Canonical, engine-readable SOP knobs. Phase 1 stores/edits/displays these; a later
# phase wires them into the recommendation + alerts engine. Every field is optional —
# a blank means "no rule". Keep keys stable; the UI and AI-generate both reference them.
SOP_RULE_FIELDS = {
    'risk_tolerance': "conservative | moderate | aggressive",
    'max_position_pct': "max % of portfolio in a single position",
    'min_price': "minimum share price ($) to consider",
    'min_market_cap_b': "minimum market cap ($ billions)",
    'max_chase_pct': "skip if already up more than this % from signal/entry",
    'earnings_blackout_days': "no new entry within this many trading days of earnings",
    'stop_loss_pct': "default stop-loss (% below entry)",
    'take_profit_pct': "default take-profit (% above entry)",
    'allowed_assets': "list: equity, option, crypto",
    'allowed_directions': "list: long, short",
    'sectors_avoid': "list of sectors to avoid",
    'max_positions': "max number of concurrent open positions",
}


def _sop_defaults():
    return {
        'risk_tolerance': 'moderate',
        'max_position_pct': None, 'min_price': None, 'min_market_cap_b': None,
        'max_chase_pct': None, 'earnings_blackout_days': None,
        'stop_loss_pct': None, 'take_profit_pct': None,
        'allowed_assets': ['equity'], 'allowed_directions': ['long'],
        'sectors_avoid': [], 'max_positions': None,
    }


def _clean_sop_rules(raw):
    """Coerce an incoming rules dict to the known schema; drop unknown keys."""
    raw = raw or {}
    out = {}
    for k in SOP_RULE_FIELDS:
        if k not in raw:
            continue
        v = raw[k]
        if v in ('', None):
            out[k] = None
        elif k in ('allowed_assets', 'allowed_directions', 'sectors_avoid'):
            out[k] = [str(x).strip().lower() for x in v] if isinstance(v, list) else [s.strip().lower() for s in str(v).split(',') if s.strip()]
        elif k == 'risk_tolerance':
            out[k] = str(v).strip().lower()
        elif k in ('earnings_blackout_days', 'max_positions'):
            try:
                out[k] = int(float(v))
            except (TypeError, ValueError):
                out[k] = None
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = None
    return out


def _next_sop_version(user_id):
    latest = db.session.query(db.func.max(TradingSOP.version)).filter_by(user_id=user_id).scalar()
    return (latest or 0) + 1


@app.route('/api/sop', methods=['GET'])
@require_api_auth
def get_sop():
    """Return the user's active SOP plus their latest draft (if any) and the rule schema."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        active = TradingSOP.query.filter_by(user_id=user_id, status='active').order_by(TradingSOP.version.desc()).first()
        draft = TradingSOP.query.filter_by(user_id=user_id, status='draft').order_by(TradingSOP.updated_at.desc()).first()
        return jsonify({
            'active': active.to_dict() if active else None,
            'draft': draft.to_dict() if draft else None,
            'schema': SOP_RULE_FIELDS,
            'defaults': _sop_defaults(),
        })
    except Exception as e:
        logger.error(f"Error getting SOP: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sop/history', methods=['GET'])
@require_api_auth
def get_sop_history():
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        rows = TradingSOP.query.filter_by(user_id=user_id).order_by(TradingSOP.version.desc()).all()
        return jsonify({'versions': [r.to_dict() for r in rows]})
    except Exception as e:
        logger.error(f"Error getting SOP history: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sop', methods=['POST'])
@require_api_auth
def create_sop_draft():
    """Save a new SOP draft (from the editor or an accepted AI generation). Not applied until approved."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        data = request.get_json() or {}
        draft = TradingSOP(
            user_id=user_id,
            version=_next_sop_version(user_id),
            status='draft',
            name=(data.get('name') or 'My Trading SOP').strip()[:120],
            rules=_clean_sop_rules(data.get('rules')),
            style=data.get('style') or {},
            doc=(data.get('doc') or '').strip() or None,
            source=data.get('source') if data.get('source') in ('manual', 'ai_generated') else 'manual',
        )
        db.session.add(draft)
        db.session.commit()
        return jsonify(draft.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating SOP draft: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sop/<int:sid>', methods=['PUT'])
@require_api_auth
def update_sop_draft(sid):
    """Edit a draft in place. Active/archived versions are immutable — edit produces a new draft via POST."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        sop = TradingSOP.query.filter_by(id=sid, user_id=user_id).first()
        if not sop:
            return jsonify({'error': 'Not found'}), 404
        if sop.status != 'draft':
            return jsonify({'error': 'Only drafts can be edited; approve creates an immutable version'}), 400
        data = request.get_json() or {}
        if 'name' in data:
            sop.name = (data.get('name') or 'My Trading SOP').strip()[:120]
        if 'rules' in data:
            sop.rules = _clean_sop_rules(data.get('rules'))
        if 'doc' in data:
            sop.doc = (data.get('doc') or '').strip() or None
        if 'style' in data:
            sop.style = data.get('style') or {}
        db.session.commit()
        return jsonify(sop.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating SOP draft: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sop/<int:sid>', methods=['DELETE'])
@require_api_auth
def delete_sop(sid):
    """Delete a draft or an archived version. The active SOP cannot be deleted (approve another first)."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        sop = TradingSOP.query.filter_by(id=sid, user_id=user_id).first()
        if not sop:
            return jsonify({'error': 'Not found'}), 404
        if sop.status == 'active':
            return jsonify({'error': 'Cannot delete the active SOP'}), 400
        db.session.delete(sop)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting SOP: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sop/<int:sid>/approve', methods=['POST'])
@require_api_auth
def approve_sop(sid):
    """Activate a draft or re-activate an archived version. Archives the prior active one."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        sop = TradingSOP.query.filter_by(id=sid, user_id=user_id).first()
        if not sop:
            return jsonify({'error': 'Not found'}), 404
        if sop.status == 'active':
            return jsonify(sop.to_dict())  # already active, no-op
        # Archive any currently-active SOP for this user.
        TradingSOP.query.filter_by(user_id=user_id, status='active').update({'status': 'archived'})
        sop.status = 'active'
        sop.activated_at = datetime.utcnow()
        db.session.commit()
        return jsonify(sop.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving SOP: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def _format_sop_for_ai(sop_dict):
    """Render an SOP dict as compact facts for an AI prompt."""
    r = sop_dict.get('rules') or {}
    lines = [f"Name: {sop_dict.get('name')}"]
    label = {
        'risk_tolerance': 'Risk tolerance', 'max_position_pct': 'Max position %',
        'min_price': 'Min share price $', 'min_market_cap_b': 'Min market cap $B',
        'max_chase_pct': 'Max chase %', 'earnings_blackout_days': 'Earnings blackout (td)',
        'stop_loss_pct': 'Default stop-loss %', 'take_profit_pct': 'Default take-profit %',
        'allowed_assets': 'Allowed assets', 'allowed_directions': 'Allowed directions',
        'sectors_avoid': 'Sectors avoided', 'max_positions': 'Max concurrent positions',
    }
    for k in SOP_RULE_FIELDS:
        v = r.get(k)
        if v in (None, '', [], {}):
            continue
        lines.append(f"{label.get(k, k)}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    if sop_dict.get('doc'):
        lines.append(f"Notes/free-form policy:\n{sop_dict['doc']}")
    return "\n".join(lines)


@app.route('/api/sop/ai-review', methods=['POST'])
@require_api_auth
@require_ai_permission
def sop_ai_review():
    """AI critique of an SOP (the active one, or a posted draft). Returns recommendations; no mutation."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        data = request.get_json() or {}
        if data.get('rules') is not None or data.get('doc') is not None:
            sop_dict = {'name': data.get('name') or 'My Trading SOP',
                        'rules': _clean_sop_rules(data.get('rules')), 'doc': data.get('doc') or ''}
        else:
            active = TradingSOP.query.filter_by(user_id=user_id, status='active').order_by(TradingSOP.version.desc()).first()
            if not active:
                return jsonify({'empty': True, 'message': 'No active SOP to review yet.'}), 200
            sop_dict = active.to_dict()
        facts = _format_sop_for_ai(sop_dict)
        system = (
            "You are a seasoned trading coach and risk manager reviewing a trader's written Standard Operating "
            "Procedure (SOP) — their personal rulebook. Give a candid, specific 5-8 sentence review: what's solid, "
            "what's missing or risky (e.g. no position-size cap, no stop discipline, no earnings-blackout, vague "
            "entry/exit criteria, over-concentration), and 2-3 concrete improvements phrased as rules they could add. "
            "Respect their stated risk tolerance and style — don't push them toward more risk. If the SOP is strong, "
            "say so plainly rather than inventing problems. End with one sentence: this is process feedback, not "
            "individualized investment advice."
        )
        read = claude_analyzer.read(system, facts, max_tokens=650)
        engine = 'claude' if read else None
        if not read:
            read = gemini_analyzer.read(system, facts)
            engine = 'gemini' if read else None
        if not read:
            return jsonify({'empty': True, 'message': 'AI review is unavailable right now.'}), 200
        return jsonify({'review': read.strip(), 'engine': engine}), 200
    except Exception as e:
        logger.error(f"Error in SOP ai-review: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'AI review temporarily unavailable'}), 200


@app.route('/api/sop/generate', methods=['POST'])
@require_api_auth
@require_ai_permission
def generate_sop():
    """AI-generate an SOP DRAFT from a short questionnaire. Returns the draft — NOT applied until approved."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        answers = (request.get_json() or {}).get('answers') or {}
        # Render the questionnaire answers as facts.
        q_facts = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in answers.items() if v not in ('', None, []))
        schema_desc = "\n".join(f"  {k}: {desc}" for k, desc in SOP_RULE_FIELDS.items())
        system = (
            "You are a trading coach turning a trader's answers into a concrete Standard Operating Procedure (SOP). "
            "Return ONLY a JSON object (no prose, no markdown fences) with exactly two top-level keys: \"rules\" and "
            "\"doc\". \"rules\" is an object using ONLY these keys (omit any you can't infer; use null for unknown "
            "numeric fields, and lists for the list fields):\n" + schema_desc + "\n"
            "\"doc\" is a clear, human-readable SOP in markdown (3-7 short sections: objective, universe/filters, "
            "entry criteria, position sizing, risk management/stops, exit rules, and what to avoid) that is consistent "
            "with the rules and the trader's stated style and risk tolerance. Be specific and disciplined; prefer "
            "conservative defaults when the trader is unsure. Do not recommend specific securities."
        )
        facts = f"Trader's answers:\n{q_facts}\n\nProduce the SOP now as JSON."
        raw = claude_analyzer.read(system, facts, max_tokens=1400)
        engine = 'claude' if raw else None
        if not raw:
            raw = gemini_analyzer.read(system, facts)
            engine = 'gemini' if raw else None
        if not raw:
            return jsonify({'empty': True, 'message': 'AI SOP generation is unavailable right now.'}), 200

        rules, doc = {}, None
        try:
            txt = raw.strip()
            if txt.startswith('```'):
                txt = txt.split('```', 2)[1]
                if txt.lstrip().lower().startswith('json'):
                    txt = txt.lstrip()[4:]
            start, end = txt.find('{'), txt.rfind('}')
            parsed = json.loads(txt[start:end + 1]) if start != -1 and end != -1 else {}
            rules = _clean_sop_rules(parsed.get('rules'))
            doc = (parsed.get('doc') or '').strip() or None
        except Exception as pe:
            logger.warning(f"SOP generate: JSON parse failed ({pe}); returning raw as doc")
            doc = raw.strip()

        # Persist as a draft so the user can review, tweak, then approve.
        draft = TradingSOP(
            user_id=user_id, version=_next_sop_version(user_id), status='draft',
            name=(answers.get('name') or 'AI-Generated SOP')[:120],
            rules=rules, style=answers, doc=doc, source='ai_generated',
        )
        db.session.add(draft)
        db.session.commit()
        result = draft.to_dict()
        result['engine'] = engine
        return jsonify(result), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating SOP: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ---- Phase 4: the SOP drives the app — audit holdings against the active SOP ----

def _sop_asset_class(asset_type, symbol):
    at = (asset_type or '').lower()
    if at == 'crypto' or (symbol or '').upper().endswith('-USD'):
        return 'crypto'
    if at == 'option':
        return 'option'
    return 'equity'  # stock / etf


def _sop_compliance(user_id, account_id=None):
    """Audit the user's holdings against their ACTIVE SOP. Uses stored holding data
    (position size, price floor, asset type, stop-loss/take-profit, position count).
    Cap/sector/earnings/chase are entry-time or need live data — not audited here."""
    sop = TradingSOP.query.filter_by(user_id=user_id, status='active').order_by(TradingSOP.version.desc()).first()
    if not sop:
        return {'has_sop': False}
    rules = sop.rules or {}
    q = Portfolio.query.filter_by(user_id=user_id)
    if account_id:
        q = q.filter_by(account_id=account_id)
    holdings = q.all()

    def hval(h):
        px = float(h.current_price) if h.current_price else float(h.average_cost or 0)
        return px * float(h.quantity or 0)
    total = sum(hval(h) for h in holdings) or 0.0

    allowed_assets = set(rules.get('allowed_assets') or [])
    max_pos_pct = rules.get('max_position_pct')
    min_price = rules.get('min_price')
    stop_pct = rules.get('stop_loss_pct')
    tp_pct = rules.get('take_profit_pct')

    flagged = []
    for h in holdings:
        px = float(h.current_price) if h.current_price else float(h.average_cost or 0)
        cost = float(h.average_cost or 0)
        val = hval(h)
        weight = (val / total * 100) if total else 0
        pnl_pct = ((px - cost) / cost * 100) if cost else 0
        aclass = _sop_asset_class(h.asset_type, h.symbol)
        breaches = []
        if allowed_assets and aclass not in allowed_assets:
            breaches.append({'rule': 'allowed_assets', 'severity': 'high',
                             'detail': f'{aclass} not permitted (SOP allows {", ".join(sorted(allowed_assets))})'})
        if max_pos_pct and weight > float(max_pos_pct) + 1e-9:
            breaches.append({'rule': 'max_position_pct', 'severity': 'high',
                             'detail': f'{weight:.1f}% of portfolio exceeds your {max_pos_pct}% cap'})
        if min_price and px and px < float(min_price):
            breaches.append({'rule': 'min_price', 'severity': 'medium',
                             'detail': f'${px:.2f} is below your ${min_price} price floor'})
        if stop_pct and cost and pnl_pct <= -float(stop_pct):
            breaches.append({'rule': 'stop_loss', 'severity': 'high',
                             'detail': f'down {pnl_pct:.1f}% — past your {stop_pct}% stop; SOP says exit full'})
        if tp_pct and cost and pnl_pct >= float(tp_pct):
            breaches.append({'rule': 'take_profit', 'severity': 'medium',
                             'detail': f'up {pnl_pct:.1f}% — at/above your {tp_pct}% take-profit target'})
        if breaches:
            flagged.append({'symbol': h.symbol, 'account_id': h.account_id,
                            'weight': round(weight, 1), 'pnl_pct': round(pnl_pct, 1),
                            'value': round(val, 2), 'asset_class': aclass, 'breaches': breaches})

    portfolio_breaches = []
    maxp = rules.get('max_positions')
    if maxp and len(holdings) > int(maxp):
        portfolio_breaches.append({'rule': 'max_positions', 'severity': 'medium',
                                   'detail': f'{len(holdings)} open positions exceeds your {maxp}-position cap'})

    total_breaches = sum(len(f['breaches']) for f in flagged) + len(portfolio_breaches)
    return {
        'has_sop': True,
        'sop_name': sop.name,
        'sop_version': sop.version,
        'summary': {
            'positions': len(holdings),
            'flagged_positions': len(flagged),
            'total_breaches': total_breaches,
            'compliant': total_breaches == 0,
        },
        'holdings': sorted(flagged, key=lambda f: (-max((1 if b['severity'] == 'high' else 0) for b in f['breaches']), -len(f['breaches']))),
        'portfolio_breaches': portfolio_breaches,
        'audited_rules': ['allowed_assets', 'max_position_pct', 'min_price', 'stop_loss', 'take_profit', 'max_positions'],
        'note': 'Audited against stored holding prices — open the Portfolio first to refresh them. Market-cap, sector, earnings-blackout and chase are entry-time rules and are not audited on existing holdings.',
    }


@app.route('/api/sop/compliance', methods=['GET'])
@require_api_auth
def sop_compliance():
    """Live audit of holdings vs the active SOP. Optional ?account_id= to scope it."""
    try:
        uid = _get_current_user_id()
        if not uid:
            return jsonify({'error': 'Authentication required'}), 401
        account_id = request.args.get('account_id', type=int)
        return jsonify(_sop_compliance(uid, account_id))
    except Exception as e:
        logger.error(f"Error in SOP compliance: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


def _paper_strategy_list(user_id):
    rows = db.session.query(PaperTrade.strategy).filter_by(user_id=user_id).distinct().all()
    return sorted({(r[0] or 'default') for r in rows})


def _paper_price(symbol):
    """Latest market price for a symbol (last daily close). None if unavailable."""
    try:
        data = data_fetcher.fetch_stock_data(symbol, period='1d')
        if data is not None and not data.empty:
            return float(data.iloc[-1]['Close'])
    except Exception as e:
        logger.debug(f"_paper_price({symbol}) failed: {e}")
    return None


def _lazy_fill_pending(user_id):
    """Fill any of the user's pending paper orders whose limit has been crossed.
    Runs opportunistically when the user views the page; the background monitor
    also fills them so it works while the page is closed. Returns count filled."""
    try:
        pend = PaperTrade.query.filter_by(user_id=user_id, status='pending').all()
        if not pend:
            return 0
        prices, filled = {}, 0
        for o in pend:
            if o.symbol not in prices:
                prices[o.symbol] = _paper_price(o.symbol)
            px = prices[o.symbol]
            if px is not None and o.fills_at(px):
                o.fill()
                filled += 1
        if filled:
            db.session.commit()
        return filled
    except Exception as e:
        db.session.rollback()
        logger.warning(f"lazy pending-fill failed for user {user_id}: {e}")
        return 0


@app.route('/api/paper/trades', methods=['GET'])
@require_api_auth
def get_paper_trades():
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        _lazy_fill_pending(user_id)  # process any crossed limit orders first
        q = PaperTrade.query.filter_by(user_id=user_id)
        status = request.args.get('status')
        if status in ('open', 'closed', 'pending'):
            q = q.filter_by(status=status)
        strategy = request.args.get('strategy')
        if strategy:
            q = q.filter_by(strategy=strategy)
        trades = q.order_by(PaperTrade.entry_at.desc()).all()
        return jsonify({'trades': [t.to_dict() for t in trades]})
    except Exception as e:
        logger.error(f"Error listing paper trades: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/pending', methods=['POST'])
@require_api_auth
def create_pending_order():
    """Create a pending limit order. It fills into an open position when the symbol's
    price crosses limit_price. trigger_side is derived from limit vs. current price:
    a limit below market waits for a drop ('below'); a limit above waits for a rise ('above')."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        data = request.get_json() or {}
        symbol = (data.get('symbol') or '').upper().strip()
        if not symbol or data.get('limit_price') in (None, ''):
            return jsonify({'error': 'symbol and limit_price are required'}), 400
        limit_price = float(data['limit_price'])  # trigger level on the underlying
        market = _paper_price(symbol)
        if market is None:
            return jsonify({'error': f'Could not get a market price for {symbol} to place the order'}), 400
        trigger_side = 'below' if limit_price <= market else 'above'
        direction = (data.get('direction') or 'long').lower()
        kind = (data.get('kind') or 'stock').lower()
        kind = kind if kind in ('option', 'stock') else 'stock'
        # For options, the recorded entry is the PREMIUM (the underlying only triggers).
        if kind == 'option':
            if data.get('entry_premium') in (None, ''):
                return jsonify({'error': 'entry_premium (the option price you would pay) is required for option orders'}), 400
            entry = float(data['entry_premium'])
        else:
            entry = limit_price
        o = PaperTrade(
            user_id=user_id, symbol=symbol,
            strategy=(data.get('strategy') or 'default').strip()[:60] or 'default',
            kind=kind,
            direction=direction if direction in ('call', 'put', 'long', 'short') else 'long',
            contracts=float(data.get('contracts') or 1),
            entry_price=entry,                # stock: = trigger; option: = premium (kept on fill)
            limit_price=limit_price, trigger_side=trigger_side,
            target_price=float(data['target_price']) if data.get('target_price') not in (None, '') else None,
            stop_price=float(data['stop_price']) if data.get('stop_price') not in (None, '') else None,
            fees=float(data.get('fees') or 0),
            notes=data.get('notes'),
            status='pending',
        )
        db.session.add(o)
        db.session.commit()
        # If the price is already at/through the limit, fill immediately.
        if o.fills_at(market):
            o.fill()
            db.session.commit()
        result = o.to_dict()
        result['market_price'] = round(market, 4)
        return jsonify(result), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating pending order: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/trades', methods=['POST'])
@require_api_auth
def create_paper_trade():
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        data = request.get_json() or {}
        symbol = (data.get('symbol') or '').upper().strip()
        if not symbol or data.get('entry_price') in (None, ''):
            return jsonify({'error': 'symbol and entry_price are required'}), 400
        kind = (data.get('kind') or 'option').lower()
        direction = (data.get('direction') or 'call').lower()
        t = PaperTrade(
            user_id=user_id, symbol=symbol,
            strategy=(data.get('strategy') or 'default').strip()[:60] or 'default',
            kind=kind if kind in ('option', 'stock') else 'option',
            direction=direction if direction in ('call', 'put', 'long', 'short') else 'call',
            contracts=float(data.get('contracts') or 1),
            entry_price=float(data.get('entry_price')),
            entry_at=_parse_txn_date(data.get('entry_at')) or datetime.utcnow(),
            target_price=float(data['target_price']) if data.get('target_price') not in (None, '') else None,
            stop_price=float(data['stop_price']) if data.get('stop_price') not in (None, '') else None,
            fees=float(data.get('fees') or 0),
            notes=data.get('notes'),
            status='open',
        )
        if data.get('exit_price') not in (None, ''):  # log a completed trade in one shot
            t.exit_price = float(data['exit_price'])
            t.exit_at = _parse_txn_date(data.get('exit_at')) or datetime.utcnow()
            t.status = 'closed'
        db.session.add(t)
        db.session.commit()
        return jsonify(t.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating paper trade: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/trades/<int:tid>', methods=['PUT'])
@require_api_auth
def update_paper_trade(tid):
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        t = PaperTrade.query.filter_by(id=tid, user_id=user_id).first()
        if not t:
            return jsonify({'error': 'Not found'}), 404
        data = request.get_json() or {}
        if data.get('exit_price') not in (None, ''):  # close the trade
            t.exit_price = float(data['exit_price'])
            t.exit_at = _parse_txn_date(data.get('exit_at')) or datetime.utcnow()
            t.status = 'closed'
        for f in ('target_price', 'stop_price', 'fees'):
            if f in data and data[f] not in (None, ''):
                setattr(t, f, float(data[f]))
        if 'notes' in data:
            t.notes = data['notes']
        if 'strategy' in data and data['strategy']:
            t.strategy = str(data['strategy']).strip()[:60]
        db.session.commit()
        return jsonify(t.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating paper trade: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/trades/<int:tid>', methods=['DELETE'])
@require_api_auth
def delete_paper_trade(tid):
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        t = PaperTrade.query.filter_by(id=tid, user_id=user_id).first()
        if not t:
            return jsonify({'error': 'Not found'}), 404
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting paper trade: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/stats', methods=['GET'])
@require_api_auth
def get_paper_stats():
    """Expectancy stats over closed paper trades — the honest edge test."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        _lazy_fill_pending(user_id)
        strategy = request.args.get('strategy')
        q = PaperTrade.query.filter_by(user_id=user_id, status='closed')
        if strategy:
            q = q.filter_by(strategy=strategy)
        trades = q.order_by(PaperTrade.exit_at.asc()).all()
        pnls = [t.pnl() for t in trades if t.pnl() is not None]
        open_count = PaperTrade.query.filter_by(user_id=user_id, status='open').count()
        pending_count = PaperTrade.query.filter_by(user_id=user_id, status='pending').count()
        strategies = _paper_strategy_list(user_id)
        n = len(pnls)
        if n == 0:
            return jsonify({'summary': {'count': 0}, 'strategies': strategies, 'open_count': open_count, 'pending_count': pending_count})
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = sum(wins)
        gross_loss = sum(losses)
        net = round(sum(pnls), 2)
        eq = peak = mdd = 0.0
        for p in pnls:
            eq += p
            peak = max(peak, eq)
            mdd = min(mdd, eq - peak)
        holds = [t.hold_minutes() for t in trades if t.hold_minutes() is not None]
        summary = {
            'count': n,
            'wins': len(wins), 'losses': len(losses),
            'win_rate': round(len(wins) / n * 100, 1),
            'avg_win': round(gross_win / len(wins), 2) if wins else 0,
            'avg_loss': round(gross_loss / len(losses), 2) if losses else 0,
            'expectancy': round(net / n, 2),
            'profit_factor': round(gross_win / abs(gross_loss), 2) if gross_loss else None,
            'net_pnl': net,
            'max_drawdown': round(mdd, 2),
            'best': round(max(pnls), 2), 'worst': round(min(pnls), 2),
            'avg_hold_min': round(sum(holds) / len(holds), 1) if holds else None,
            'total_fees': round(sum(float(t.fees or 0) for t in trades), 2),
        }
        return jsonify({'summary': summary, 'strategies': strategies, 'open_count': open_count, 'pending_count': pending_count})
    except Exception as e:
        logger.error(f"Error computing paper stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax/realized', methods=['GET'])
@require_api_auth
def get_tax_realized():
    """Realized capital gains for a tax year, split short-term / long-term.

    Query params: year (YYYY), account_id (int), method (fifo|lifo|hifo).
    Tax-advantaged accounts are excluded automatically.
    """
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        year = request.args.get('year', type=int)
        account_id = request.args.get('account_id', type=int)
        method = request.args.get('method', 'fifo')
        result = tax_analyzer.realized_gains(user_id, year=year, account_id=account_id, method=method)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in tax realized gains: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax/harvest', methods=['GET'])
@require_api_auth
def get_tax_harvest():
    """Tax-loss harvesting candidates — unrealized losers with wash-sale /
    IPO-lock flags and short/long classification."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify(tax_analyzer.harvest_candidates(user_id)), 200
    except Exception as e:
        logger.error(f"Error in tax harvest: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax/lt-threshold', methods=['GET'])
@require_api_auth
def get_tax_lt_threshold():
    """Short-term gain positions approaching the 1-year long-term mark."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify(tax_analyzer.lt_threshold(user_id)), 200
    except Exception as e:
        logger.error(f"Error in tax lt-threshold: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax/export/8949', methods=['GET'])
@require_api_auth
def export_tax_8949():
    """Realized gains as a Form 8949-style CSV (TurboTax-friendly), split into
    Part I (short-term) and Part II (long-term) with subtotals."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        year = request.args.get('year', type=int)
        account_id = request.args.get('account_id', type=int)
        method = request.args.get('method', 'fifo')
        result = tax_analyzer.realized_gains(user_id, year=year, account_id=account_id, method=method)
        disposals = result.get('disposals', [])

        from flask import make_response
        import csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['Description (a)', 'Date Acquired (b)', 'Date Sold (c)',
                    'Proceeds (d)', 'Cost Basis (e)', 'Gain/Loss (h)',
                    'Term', 'Account', 'Basis quality'])

        def _section(rows, label, part):
            if not rows:
                return
            w.writerow([])
            w.writerow([f'=== {label} — Form 8949 Part {part} ==='])
            for d in rows:
                w.writerow([
                    f"{d['quantity']} sh {d['symbol']}",
                    d.get('acquired_date') or '', d.get('sold_date') or '',
                    f"{d['proceeds']:.2f}", f"{d['basis']:.2f}", f"{d['gain']:.2f}",
                    'Long-term' if d['term'] == 'long' else 'Short-term',
                    d.get('account_name') or '',
                    'estimated' if d.get('estimated') else 'actual',
                ])
            w.writerow(['TOTAL ' + label, '', '',
                        f"{sum(d['proceeds'] for d in rows):.2f}",
                        f"{sum(d['basis'] for d in rows):.2f}",
                        f"{sum(d['gain'] for d in rows):.2f}", '', '', ''])

        _section([d for d in disposals if d['term'] == 'short'], 'Short-Term', 'I')
        _section([d for d in disposals if d['term'] == 'long'], 'Long-Term', 'II')

        resp = make_response(buf.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = f'attachment; filename=form8949_{year or "all"}.csv'
        return resp
    except Exception as e:
        logger.error(f"Error exporting 8949: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax/ai-read', methods=['GET'])
@require_api_auth
@require_ai_permission
def get_tax_ai_read():
    """Plain-English read of the whole tax picture — realized, harvestable
    losses, and positions approaching long-term. Claude primary → Gemini →
    local LLM fallback."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        year = request.args.get('year', type=int) or datetime.now().year
        realized = tax_analyzer.realized_gains(user_id, year=year)
        harvest = tax_analyzer.harvest_candidates(user_id)
        lt = tax_analyzer.lt_threshold(user_id)
        rs, hs, ls = realized['summary'], harvest['summary'], lt['summary']
        top_harvest = [c for c in harvest['candidates'] if c['harvestable']][:4]
        top_lt = lt['positions'][:3]

        facts = (
            f"Tax year: {year}\n"
            f"REALIZED so far: short-term {rs['short_term']['gain']}, long-term {rs['long_term']['gain']}, "
            f"total {rs['total_gain']} across {rs['disposal_count']} sales.\n"
            f"HARVESTABLE unrealized losses: {hs['harvestable_loss']} total (short-term {hs['harvestable_short']}, "
            f"long-term {hs['harvestable_long']}); {hs['harvestable_count']} positions harvestable, "
            f"{hs['blocked_count']} blocked by wash-sale or IPO-lock.\n"
            "Top harvestable positions: "
            + (", ".join(f"{c['symbol']} {c['unrealized_loss']} ({c['term']})" for c in top_harvest) or "none")
            + "\n"
            f"APPROACHING LONG-TERM: {ls['count']} short-term gain positions, {ls['within_90_count']} cross within 90 days.\n"
            "Soonest crossings: "
            + (", ".join(f"{r['symbol']} gain {r['unrealized_gain']} in {r['days_to_lt']}d" for r in top_lt) or "none")
            + "\n"
        )
        system = (
            "You are a sharp, plain-spoken tax-aware portfolio analyst. Given the owner's realized gains, "
            "harvestable unrealized losses, and positions approaching long-term status for the tax year, write a "
            "4-6 sentence read: where they stand on realized gains/losses, the single most useful tax-loss "
            "harvesting move (respecting the wash-sale and locked caveats), and any position worth holding a bit "
            "longer for long-term treatment. Be specific with the numbers. Note when realized losses already "
            "exceed likely gains, so extra harvesting mostly builds carryforward (losses offset gains, then up to "
            "$3,000 of ordinary income per year, then carry forward). Do NOT recommend buying or selling specific "
            "securities as investments. End by noting this is informational, not tax advice — reconcile with the "
            "actual 1099s and a CPA."
        )

        refresh = request.args.get('refresh') == '1'
        out = cached_ai_read(user_id, 'tax', system, facts,
                             ttl_minutes=360, max_tokens=700, refresh=refresh)
        if out.get('empty'):
            return jsonify({'empty': True, 'message': 'AI tax read unavailable right now.'}), 200
        out['year'] = year
        return jsonify(out), 200
    except Exception as e:
        logger.error(f"Error in tax ai-read: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'AI tax read temporarily unavailable'}), 200


@app.route('/api/tax/years', methods=['GET'])
@require_api_auth
def get_tax_years():
    """Tax years that have realized (sell) activity."""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify({'years': tax_analyzer.available_years(user_id)}), 200
    except Exception as e:
        logger.error(f"Error in tax years: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ===================== TAX DOCUMENTS + INCOME-TAX ESTIMATE (Phase 3) =====================

TAX_DOC_TYPES = {'W2', '1099-NEC', '1099-MISC', '1099-INT', '1099-DIV', '1099-B', '1098', 'receipt', 'other'}
ALLOWED_DOC_MIMES = {'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp'}


def _tax_doc_extract(doc):
    """Vision-read a stored W2/1099/receipt via Claude and return extracted fields (or None).
    Cached by file hash so re-extraction of the same file costs nothing."""
    if not doc.data or doc.content_type not in ALLOWED_DOC_MIMES:
        return None
    input_hash = hashlib.sha256(f"{doc.doc_type}\x1f".encode() + doc.data).hexdigest()
    now = datetime.utcnow()
    try:
        hit = (AIInsight.query.filter_by(user_id=doc.user_id, kind='taxdoc_extract', input_hash=input_hash)
               .filter(AIInsight.expires_at > now).first())
        if hit:
            return json.loads(hit.content)
    except Exception:
        pass
    system = ("You are a precise tax-document data extractor. Read the attached document and return ONLY a compact "
              "JSON object — no prose, no markdown code fences.")
    if doc.doc_type == 'receipt':
        prompt = ('Extract this receipt as JSON with keys: merchant (string), date (YYYY-MM-DD or null), '
                  'amount (number: the total), category (one of housing, utilities, transportation, insurance, food, '
                  'healthcare, subscriptions, entertainment, personal, other), tax_deductible (true or false, best guess). '
                  'Return only the JSON object.')
    else:
        prompt = ('Extract this US tax form as JSON with keys: form_type (e.g. "W-2","1099-NEC"), tax_year (integer or null), '
                  'issuer (employer or payer name), wages (number: W-2 box 1 wages, or the 1099 income amount), '
                  'federal_income_tax_withheld (number: W-2 box 2, or 1099 withholding; 0 if none). '
                  'Use 0 for any missing number. Return only the JSON object.')
    raw = claude_analyzer.read_document(system, prompt, doc.data, doc.content_type, max_tokens=500)
    if not raw:
        return None
    txt = raw.strip()
    try:
        data = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    except Exception as e:
        logger.warning(f"tax doc extract JSON parse failed: {e}")
        return None
    try:
        db.session.add(AIInsight(user_id=doc.user_id, kind='taxdoc_extract', input_hash=input_hash,
                                 engine='claude', model=claude_analyzer.model, content=json.dumps(data),
                                 created_at=now, expires_at=now + timedelta(days=365)))
        db.session.commit()
    except Exception:
        db.session.rollback()
    return data


def _num(data, *keys):
    for k in keys:
        v = data.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.replace(',', '').replace('$', '').strip())
            except ValueError:
                pass
    return None


def _apply_extracted_to_doc(doc, data):
    """Map extracted JSON onto the doc's structured columns (wages/withheld or receipt fields)."""
    if not isinstance(data, dict):
        return
    doc.extracted = data
    if doc.doc_type == 'receipt':
        a = _num(data, 'amount', 'total')
        if a is not None:
            doc.amount = a
        if data.get('merchant'):
            doc.merchant = str(data['merchant'])[:160]
        if data.get('category'):
            doc.category = str(data['category'])[:50]
        if isinstance(data.get('tax_deductible'), bool):
            doc.deductible = data['tax_deductible']
    else:
        w = _num(data, 'wages', 'box1', 'income', 'amount')
        if w is not None:
            doc.wages = w
        fw = _num(data, 'federal_income_tax_withheld', 'withheld', 'box2', 'federal_withholding')
        if fw is not None:
            doc.fed_withheld = fw
        if data.get('issuer') and not doc.issuer:
            doc.issuer = str(data['issuer'])[:160]
        if isinstance(data.get('tax_year'), int) and not doc.tax_year:
            doc.tax_year = data['tax_year']


@app.route('/api/tax/documents', methods=['GET', 'POST'])
@require_api_auth
def tax_documents():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    if request.method == 'GET':
        q = TaxDocument.query.filter_by(user_id=uid)
        yr = request.args.get('year', type=int)
        if yr:
            q = q.filter_by(tax_year=yr)
        rows = q.order_by(TaxDocument.uploaded_at.desc()).all()
        return jsonify({'documents': [d.to_dict() for d in rows]})
    # POST — multipart upload
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'file is required'}), 400
    ctype = (f.mimetype or '').lower()
    if ctype not in ALLOWED_DOC_MIMES:
        return jsonify({'error': f'unsupported type {ctype}; use PDF or image'}), 400
    from werkzeug.utils import secure_filename
    blob = f.read()
    if not blob:
        return jsonify({'error': 'empty file'}), 400
    form = request.form
    dt = (form.get('doc_type') or 'other')
    doc = TaxDocument(
        user_id=uid, data=blob, size=len(blob), content_type=ctype,
        filename=secure_filename(f.filename)[:255],
        doc_type=dt if dt in TAX_DOC_TYPES else 'other',
        tax_year=(form.get('tax_year', type=int) or datetime.now().year),
        issuer=(form.get('issuer') or None),
        notes=(form.get('notes') or None),
    )
    db.session.add(doc)
    db.session.commit()
    # Best-effort auto-extract unless the client opts out (?extract=0) or lacks the AI
    # permission — the document is still stored either way, just not read automatically.
    if form.get('extract') != '0' and _can_use_ai():
        try:
            data = _tax_doc_extract(doc)
            if data:
                _apply_extracted_to_doc(doc, data)
                db.session.commit()
        except Exception as e:
            logger.warning(f"auto-extract failed for doc {doc.id}: {e}")
    return jsonify(doc.to_dict()), 201


@app.route('/api/tax/documents/<int:did>', methods=['PUT', 'DELETE'])
@require_api_auth
def tax_document_modify(did):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    doc = TaxDocument.query.filter_by(id=did, user_id=uid).first()
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(doc)
        db.session.commit()
        return jsonify({'success': True})
    d = request.get_json() or {}
    if 'doc_type' in d and d['doc_type'] in TAX_DOC_TYPES:
        doc.doc_type = d['doc_type']
    if 'tax_year' in d:
        try:
            doc.tax_year = int(d['tax_year']) if d.get('tax_year') else None
        except (TypeError, ValueError):
            pass
    for f in ('issuer', 'merchant', 'category', 'notes'):
        if f in d:
            setattr(doc, f, (d.get(f) or None))
    for f in ('wages', 'fed_withheld', 'amount'):
        if f in d:
            try:
                setattr(doc, f, float(d.get(f) or 0))
            except (TypeError, ValueError):
                pass
    if 'deductible' in d:
        doc.deductible = bool(d.get('deductible'))
    db.session.commit()
    return jsonify(doc.to_dict())


@app.route('/api/tax/documents/<int:did>/download', methods=['GET'])
@require_api_auth
def tax_document_download(did):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    doc = TaxDocument.query.filter_by(id=did, user_id=uid).first()
    if not doc or not doc.data:
        return jsonify({'error': 'Not found'}), 404
    return Response(doc.data, mimetype=doc.content_type or 'application/octet-stream',
                    headers={'Content-Disposition': f'inline; filename="{doc.filename or "document"}"'})


@app.route('/api/tax/documents/<int:did>/extract', methods=['POST'])
@require_api_auth
@require_ai_permission
def tax_document_extract(did):
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    doc = TaxDocument.query.filter_by(id=did, user_id=uid).first()
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    data = _tax_doc_extract(doc)
    if not data:
        return jsonify({'empty': True, 'message': 'Could not extract fields (enter them manually).'}), 200
    _apply_extracted_to_doc(doc, data)
    db.session.commit()
    return jsonify({'extracted': data, 'document': doc.to_dict()}), 200


# --- Income-tax estimate (approximate; 2025 MFJ figures) ---
_FED_BRACKETS_MFJ = [(0, 0.10), (23850, 0.12), (96950, 0.22), (206700, 0.24),
                     (394600, 0.32), (501050, 0.35), (751600, 0.37)]
_FED_BRACKETS_SINGLE = [(0, 0.10), (11925, 0.12), (48475, 0.22), (103350, 0.24),
                        (197300, 0.32), (250525, 0.35), (626350, 0.37)]
_STD_DEDUCTION = {'mfj': 30000, 'single': 15000}
_SS_WAGE_BASE = 176100


def _bracket_tax(taxable, brackets):
    tax, n = 0.0, len(brackets)
    for i, (floor, rate) in enumerate(brackets):
        ceil = brackets[i + 1][0] if i + 1 < n else float('inf')
        if taxable > floor:
            tax += (min(taxable, ceil) - floor) * rate
        else:
            break
    return round(tax, 2)


def _income_tax_estimate(user_id, year=None, filing='mfj'):
    """Rough federal income + self-employment tax estimate from tracked income sources and
    any W2/1099 withholding on file. Clearly an estimate — not tax advice."""
    filing = filing if filing in _STD_DEDUCTION else 'mfj'
    srcs = IncomeSource.query.filter_by(user_id=user_id, active=True).all()
    w2_wages = round(sum(s.gross_annual() for s in srcs if s.tax_form == 'W2'), 2)
    se_income = round(sum(s.gross_annual() for s in srcs if s.tax_form == '1099'), 2)

    se_net = round(se_income * 0.9235, 2)
    ss_room = max(0.0, _SS_WAGE_BASE - w2_wages)
    se_tax = round(min(se_net, ss_room) * 0.124 + se_net * 0.029, 2)
    half_se = round(se_tax / 2.0, 2)

    std = _STD_DEDUCTION[filing]
    taxable = max(0.0, w2_wages + se_net - half_se - std)
    brackets = _FED_BRACKETS_MFJ if filing == 'mfj' else _FED_BRACKETS_SINGLE
    fed_income_tax = _bracket_tax(taxable, brackets)

    # Withholding already remitted (from W2/1099 docs on file for the year).
    yr = year or datetime.now().year
    withheld = round(sum(float(d.fed_withheld or 0) for d in
                         TaxDocument.query.filter_by(user_id=user_id, tax_year=yr).all()), 2)

    total_tax = round(fed_income_tax + se_tax, 2)
    balance_due = round(total_tax - withheld, 2)
    gross = w2_wages + se_income
    return {
        'year': yr, 'filing_status': filing,
        'w2_wages': w2_wages, 'se_income': se_income, 'se_net': se_net,
        'standard_deduction': std, 'taxable_income': round(taxable, 2),
        'federal_income_tax': fed_income_tax, 'self_employment_tax': se_tax,
        'total_federal_tax': total_tax, 'withheld': withheld,
        'balance_due': balance_due, 'refund': round(-balance_due, 2) if balance_due < 0 else 0,
        'effective_rate': round(total_tax / gross * 100, 1) if gross else 0,
        'quarterly_estimate': round(max(0.0, se_tax + (fed_income_tax if withheld == 0 else 0)) / 4.0, 2),
        'note': 'Approximate: 2025 federal brackets, standard deduction, no state/credits. Not tax advice.',
    }


@app.route('/api/tax/income-estimate', methods=['GET'])
@require_api_auth
def tax_income_estimate():
    uid = _get_current_user_id()
    if not uid:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        year = request.args.get('year', type=int)
        filing = (request.args.get('filing') or 'mfj').lower()
        return jsonify(_income_tax_estimate(uid, year=year, filing=filing))
    except Exception as e:
        logger.error(f"Error in income-tax estimate: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/admin')
@login_required
def admin_page():
    """Render the admin dashboard (admin only)."""
    if not current_user.is_admin():
        return redirect(url_for('portfolio'))
    return render_template('admin.html')


@app.route('/community')
@login_required
def community_page():
    """Render the community discussion page."""
    return render_template('community.html')


# ===================== ADMIN API =====================

@app.route('/api/admin/users', methods=['GET'])
@require_api_auth
def admin_list_users():
    """List all users (admin only)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [u.to_dict() for u in users]})


@app.route('/api/admin/users/<int:user_id>/role', methods=['PUT'])
@require_api_auth
def admin_change_role(user_id):
    """Change a user's role (admin only)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    role = data.get('role')
    if role not in ('user', 'moderator', 'admin'):
        return jsonify({'error': 'Invalid role'}), 400
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot change your own role'}), 400
    user.role = role
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/admin/users/<int:user_id>/active', methods=['PUT'])
@require_api_auth
def admin_toggle_active(user_id):
    """Enable/disable a user account (admin only)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot disable your own account'}), 400
    data = request.get_json()
    user.is_active = data.get('is_active', True)
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/admin/stats', methods=['GET'])
@require_api_auth
def admin_stats():
    """Get admin dashboard stats."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_threads = DiscussionThread.query.count()
    total_holdings = Portfolio.query.count()
    return jsonify({
        'total_users': total_users,
        'active_users': active_users,
        'total_threads': total_threads,
        'total_holdings': total_holdings,
    })


# ===================== GROUPS & PERMISSIONS (RBAC) =====================

# Canonical permission registry. A user's effective permissions = the union across
# their groups; admins bypass and implicitly hold every permission. Add a key here
# and it becomes assignable in the admin Groups UI; gate a feature with
# @require_permission('key') or user_has_permission(user, 'key').
PERMISSIONS = {
    'ai_analysis': 'Use AI analysis (holding/tax/SOP reads)',
    'paper_trading': 'Access the Paper Trading module',
    'copy_trading': 'Use copy trading / follow traders',
    'community_post': 'Post and reply in the Community',
    'tax_center': 'Access the Tax Center',
    'premium_intervals': 'Unlock faster refresh/alert intervals',
    'unlimited_watchlist': 'Remove watchlist size limits',
    'data_export': 'Export portfolio / tax data',
    'api_tokens': 'Create Personal Access Tokens (API / AI access)',
    'plaid_link': 'Connect bank/brokerage accounts via Plaid and see the data they return',
}


def _effective_permissions(user):
    """Set of permission keys a user effectively has. Admins get everything."""
    if user is None:
        return set()
    if user.is_admin():
        return set(PERMISSIONS.keys())
    return {p for p in user.group_permissions() if p in PERMISSIONS}


def user_has_permission(user, perm):
    return perm in _effective_permissions(user)


def require_permission(perm):
    """Decorator to gate an endpoint on a permission (admins always pass)."""
    def wrapper(f):
        @wraps(f)
        def inner(*args, **kwargs):
            uid = _get_current_user_id()
            user = User.query.get(uid) if uid else None
            if not user:
                return jsonify({'error': 'Authentication required'}), 401
            if not user_has_permission(user, perm):
                return jsonify({'error': 'Permission denied', 'missing_permission': perm}), 403
            return f(*args, **kwargs)
        return inner
    return wrapper


def _seed_default_groups():
    """Create built-in groups once, so the RBAC system is usable out of the box."""
    try:
        if Group.query.count() > 0:
            return
        defaults = [
            ('Members', 'Baseline access for all standard members.',
             ['ai_analysis', 'paper_trading', 'community_post', 'tax_center', 'data_export'], True),
            ('Premium', 'Paid tier — everything, including faster intervals and no limits.',
             list(PERMISSIONS.keys()), True),
        ]
        for name, desc, perms, is_sys in defaults:
            db.session.add(Group(name=name, description=desc, permissions=perms, is_system=is_sys))
        db.session.commit()
        logger.info("✓ Seeded default permission groups")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Could not seed default groups: {e}")


@app.route('/api/user/permissions', methods=['GET'])
@require_api_auth
def get_my_permissions():
    """The current user's effective permissions + the full registry (for UI gating)."""
    uid = _get_current_user_id()
    user = User.query.get(uid) if uid else None
    if not user:
        return jsonify({'error': 'Authentication required'}), 401
    return jsonify({
        'permissions': sorted(_effective_permissions(user)),
        'is_admin': user.is_admin(),
        'registry': PERMISSIONS,
        'groups': [{'id': g.id, 'name': g.name} for g in (user.groups or [])],
    })


@app.route('/api/admin/permissions', methods=['GET'])
@require_api_auth
def admin_list_permissions():
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({'permissions': PERMISSIONS})


@app.route('/api/admin/groups', methods=['GET'])
@require_api_auth
def admin_list_groups():
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    groups = Group.query.order_by(Group.name.asc()).all()
    return jsonify({'groups': [g.to_dict(member_count=len(g.members)) for g in groups],
                    'registry': PERMISSIONS})


@app.route('/api/admin/groups', methods=['POST'])
@require_api_auth
def admin_create_group():
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if Group.query.filter(db.func.lower(Group.name) == name.lower()).first():
        return jsonify({'error': 'A group with that name already exists'}), 400
    perms = [p for p in (data.get('permissions') or []) if p in PERMISSIONS]
    g = Group(name=name[:60], description=(data.get('description') or '').strip() or None,
              permissions=perms, is_system=False)
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict(member_count=0)), 201


@app.route('/api/admin/groups/<int:group_id>', methods=['PUT'])
@require_api_auth
def admin_update_group(group_id):
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    g = Group.query.get_or_404(group_id)
    data = request.get_json() or {}
    if 'name' in data and g.is_system:
        return jsonify({'error': 'Cannot rename a system group'}), 400
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        clash = Group.query.filter(db.func.lower(Group.name) == name.lower(), Group.id != group_id).first()
        if clash:
            return jsonify({'error': 'A group with that name already exists'}), 400
        g.name = name[:60]
    if 'description' in data:
        g.description = (data.get('description') or '').strip() or None
    if 'permissions' in data:
        g.permissions = [p for p in (data.get('permissions') or []) if p in PERMISSIONS]
    db.session.commit()
    return jsonify(g.to_dict(member_count=len(g.members)))


@app.route('/api/admin/groups/<int:group_id>', methods=['DELETE'])
@require_api_auth
def admin_delete_group(group_id):
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    g = Group.query.get_or_404(group_id)
    if g.is_system:
        return jsonify({'error': 'Cannot delete a built-in system group'}), 400
    g.members = []  # drop association rows
    db.session.delete(g)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/users/<int:user_id>/groups', methods=['PUT'])
@require_api_auth
def admin_set_user_groups(user_id):
    """Replace a user's group memberships with the provided list of group ids."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    user = User.query.get_or_404(user_id)
    ids = (request.get_json() or {}).get('group_ids') or []
    groups = Group.query.filter(Group.id.in_(ids)).all() if ids else []
    user.groups = groups
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})


# ===================== COMMUNITY API =====================

@app.route('/api/community/threads', methods=['GET'])
@require_api_auth
def list_threads():
    """List discussion threads with optional category filter."""
    category = request.args.get('category', 'all')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    query = DiscussionThread.query
    if category != 'all':
        query = query.filter_by(category=category)
    query = query.order_by(DiscussionThread.pinned.desc(), DiscussionThread.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    threads = []
    for t in pagination.items:
        td = t.to_dict()
        td['reply_count'] = ThreadReply.query.filter_by(thread_id=t.id).count()
        threads.append(td)
    
    return jsonify({
        'threads': threads,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    })


@app.route('/api/community/threads', methods=['POST'])
@require_api_auth
def create_thread():
    """Create a new discussion thread."""
    data = request.get_json()
    title = (data.get('title') or '').strip()
    body = (data.get('body') or '').strip()
    if not title or not body:
        return jsonify({'error': 'Title and body are required'}), 400
    
    thread = DiscussionThread(
        user_id=current_user.id,
        title=title[:200],
        body=body[:10000],
        symbol=(data.get('symbol') or '').upper()[:10] or None,
        category=data.get('category', 'general'),
    )
    db.session.add(thread)
    db.session.commit()
    return jsonify({'success': True, 'thread': thread.to_dict()}), 201


@app.route('/api/community/threads/<int:thread_id>', methods=['GET'])
@require_api_auth
def get_thread(thread_id):
    """Get a single thread with its replies."""
    thread = DiscussionThread.query.get_or_404(thread_id)
    thread.views = (thread.views or 0) + 1
    db.session.commit()
    
    td = thread.to_dict()
    replies = ThreadReply.query.filter_by(thread_id=thread_id)\
        .order_by(ThreadReply.created_at.asc()).all()
    td['replies'] = [r.to_dict() for r in replies]
    
    # Include current user's votes
    votes = ThreadVote.query.filter_by(user_id=current_user.id, thread_id=thread_id).all()
    user_votes = {}
    for v in votes:
        key = f'reply_{v.reply_id}' if v.reply_id else 'thread'
        user_votes[key] = v.vote
    td['user_votes'] = user_votes
    
    return jsonify(td)


@app.route('/api/community/threads/<int:thread_id>/replies', methods=['POST'])
@require_api_auth
def add_reply(thread_id):
    """Add a reply to a thread."""
    thread = DiscussionThread.query.get_or_404(thread_id)
    if thread.locked:
        return jsonify({'error': 'Thread is locked'}), 403
    
    data = request.get_json()
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'Reply body is required'}), 400
    
    reply = ThreadReply(
        thread_id=thread_id,
        user_id=current_user.id,
        body=body[:10000],
    )
    db.session.add(reply)
    thread.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'reply': reply.to_dict()}), 201


@app.route('/api/community/threads/<int:thread_id>/vote', methods=['POST'])
@require_api_auth
def vote_thread(thread_id):
    """Upvote/downvote a thread."""
    thread = DiscussionThread.query.get_or_404(thread_id)
    data = request.get_json()
    vote_val = data.get('vote', 1)
    if vote_val not in (1, -1):
        return jsonify({'error': 'Vote must be 1 or -1'}), 400
    
    existing = ThreadVote.query.filter_by(
        user_id=current_user.id, thread_id=thread_id, reply_id=None
    ).first()
    
    if existing:
        if existing.vote == vote_val:
            # Remove vote
            thread.upvotes = (thread.upvotes or 0) - vote_val
            db.session.delete(existing)
        else:
            # Change vote
            thread.upvotes = (thread.upvotes or 0) + (vote_val - existing.vote)
            existing.vote = vote_val
    else:
        thread.upvotes = (thread.upvotes or 0) + vote_val
        db.session.add(ThreadVote(
            user_id=current_user.id, thread_id=thread_id, reply_id=None, vote=vote_val
        ))
    
    db.session.commit()
    return jsonify({'success': True, 'upvotes': thread.upvotes})


@app.route('/api/community/replies/<int:reply_id>/vote', methods=['POST'])
@require_api_auth
def vote_reply(reply_id):
    """Upvote/downvote a reply."""
    reply = ThreadReply.query.get_or_404(reply_id)
    data = request.get_json()
    vote_val = data.get('vote', 1)
    if vote_val not in (1, -1):
        return jsonify({'error': 'Vote must be 1 or -1'}), 400
    
    existing = ThreadVote.query.filter_by(
        user_id=current_user.id, thread_id=reply.thread_id, reply_id=reply_id
    ).first()
    
    if existing:
        if existing.vote == vote_val:
            reply.upvotes = (reply.upvotes or 0) - vote_val
            db.session.delete(existing)
        else:
            reply.upvotes = (reply.upvotes or 0) + (vote_val - existing.vote)
            existing.vote = vote_val
    else:
        reply.upvotes = (reply.upvotes or 0) + vote_val
        db.session.add(ThreadVote(
            user_id=current_user.id, thread_id=reply.thread_id, reply_id=reply_id, vote=vote_val
        ))
    
    db.session.commit()
    return jsonify({'success': True, 'upvotes': reply.upvotes})


@app.route('/api/community/threads/<int:thread_id>', methods=['DELETE'])
@require_api_auth
def delete_thread(thread_id):
    """Delete a thread (author or moderator)."""
    thread = DiscussionThread.query.get_or_404(thread_id)
    if thread.user_id != current_user.id and not current_user.is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(thread)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/community/threads/<int:thread_id>/lock', methods=['PUT'])
@require_api_auth
def lock_thread(thread_id):
    """Lock/unlock a thread (moderator only)."""
    if not current_user.is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    thread = DiscussionThread.query.get_or_404(thread_id)
    data = request.get_json()
    thread.locked = data.get('locked', True)
    db.session.commit()
    return jsonify({'success': True, 'locked': thread.locked})


@app.route('/api/community/threads/<int:thread_id>/pin', methods=['PUT'])
@require_api_auth
def pin_thread(thread_id):
    """Pin/unpin a thread (moderator only)."""
    if not current_user.is_moderator():
        return jsonify({'error': 'Unauthorized'}), 403
    thread = DiscussionThread.query.get_or_404(thread_id)
    data = request.get_json()
    thread.pinned = data.get('pinned', True)
    db.session.commit()
    return jsonify({'success': True, 'pinned': thread.pinned})


@app.route('/api/community/online', methods=['GET'])
@require_api_auth
def online_users():
    """List recently active users (active in last 5 minutes)."""
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    users = User.query.filter(User.last_active >= cutoff).all()
    return jsonify({'online': [{'id': u.id, 'name': u.name, 'picture_url': u.picture_url} for u in users]})


# ===================== COPY TRADING MEMBER API =====================

@app.route('/api/copytrading/members', methods=['GET'])
@require_api_auth
def list_copy_trading_members():
    """List users who have opted in to member copy trading."""
    members = User.query.filter_by(copy_trading_enabled=True, is_active=True).all()
    result = []
    for m in members:
        holdings_count = Portfolio.query.filter_by(user_id=m.id).count()
        follower_count = CopyTradingFollow.query.filter_by(leader_id=m.id).count()
        is_following = CopyTradingFollow.query.filter_by(
            follower_id=current_user.id, leader_id=m.id
        ).first() is not None
        result.append({
            'id': m.id,
            'name': m.name,
            'picture_url': m.picture_url,
            'bio': m.bio,
            'holdings_count': holdings_count,
            'follower_count': follower_count,
            'is_following': is_following,
            'member_since': m.created_at.isoformat() if m.created_at else None,
        })
    return jsonify({'members': result})


@app.route('/api/copytrading/opt-in', methods=['POST'])
@require_api_auth
def toggle_copy_trading():
    """Toggle copy trading opt-in for current user."""
    data = request.get_json()
    current_user.copy_trading_enabled = data.get('enabled', False)
    if data.get('bio') is not None:
        current_user.bio = (data['bio'] or '')[:500]
    db.session.commit()
    return jsonify({'success': True, 'enabled': current_user.copy_trading_enabled})


@app.route('/api/copytrading/follow/<int:leader_id>', methods=['POST'])
@require_api_auth
def follow_member(leader_id):
    """Follow a member for copy trading."""
    if leader_id == current_user.id:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    leader = User.query.get_or_404(leader_id)
    if not leader.copy_trading_enabled:
        return jsonify({'error': 'This user has not enabled copy trading'}), 400
    existing = CopyTradingFollow.query.filter_by(
        follower_id=current_user.id, leader_id=leader_id
    ).first()
    if existing:
        return jsonify({'error': 'Already following'}), 400
    db.session.add(CopyTradingFollow(follower_id=current_user.id, leader_id=leader_id))
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/copytrading/unfollow/<int:leader_id>', methods=['POST'])
@require_api_auth
def unfollow_member(leader_id):
    """Unfollow a copy trading member."""
    follow = CopyTradingFollow.query.filter_by(
        follower_id=current_user.id, leader_id=leader_id
    ).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/copytrading/status', methods=['GET'])
@require_api_auth
def copy_trading_status():
    """Get current user's copy trading status."""
    return jsonify({
        'enabled': current_user.copy_trading_enabled or False,
        'bio': current_user.bio or '',
        'follower_count': CopyTradingFollow.query.filter_by(leader_id=current_user.id).count(),
        'following_count': CopyTradingFollow.query.filter_by(follower_id=current_user.id).count(),
    })


@app.route('/api/user/heartbeat', methods=['POST'])
@require_api_auth
def user_heartbeat():
    """Update user's last active timestamp."""
    current_user.last_active = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/user/preferences', methods=['GET'])
@require_api_auth
def get_preferences():
    """Get current user's preferences."""
    prefs = current_user.preferences or {}
    return jsonify({'preferences': prefs})


@app.route('/api/user/preferences', methods=['PUT'])
@require_api_auth
def save_preferences():
    """Save current user's preferences."""
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid data'}), 400
    # Only allow known safe keys
    allowed = {'darkMode', 'autoRefreshWatchlist', 'notificationsEnabled',
                'defaultPeriod', 'defaultChartType'}
    prefs = {k: v for k, v in data.items() if k in allowed}
    current_user.preferences = {**(current_user.preferences or {}), **prefs}
    db.session.commit()
    return jsonify({'success': True, 'preferences': current_user.preferences})


@app.route('/api/user/profile', methods=['GET'])
@require_api_auth
def get_user_profile():
    """Current user's profile (self)."""
    return jsonify({'user': current_user.to_dict()})


@app.route('/api/user/profile', methods=['PUT'])
@require_api_auth
def update_user_profile():
    """Update the current user's own editable profile fields (name, bio)."""
    data = request.get_json() or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if name:
            current_user.name = name[:255]
    if 'bio' in data:
        bio = (data.get('bio') or '').strip()
        current_user.bio = bio[:2000] or None
    db.session.commit()
    return jsonify({'success': True, 'user': current_user.to_dict()})


# ===================== ACCOUNT LIFECYCLE (soft-delete) =====================

def _soft_delete_user(user, by_id):
    """Mark an account deleted: scrub display PII, disable login, kill sessions.
    google_id is KEPT so re-login can restore it within the retention window; rows
    are retained (anonymized) until an admin hard-purges."""
    user.deleted_at = datetime.utcnow()
    user.deleted_by = by_id
    user.is_active = False
    user.email = f'deleted+{user.id}@deleted.invalid'  # unique per id, frees the real address
    user.name = 'Deleted User'
    user.picture_url = None
    user.bio = None
    # Invalidate every session/PAT so existing tokens stop working immediately.
    try:
        from models import UserSession
        UserSession.query.filter_by(user_id=user.id).delete()
    except Exception as e:
        logger.warning(f"Could not clear sessions for deleted user {user.id}: {e}")


@app.route('/api/user/account', methods=['DELETE'])
@require_api_auth
def delete_own_account():
    """Self-serve soft-delete of the current user's own account."""
    try:
        uid = _get_current_user_id()
        if not uid:
            return jsonify({'error': 'Authentication required'}), 401
        user = User.query.get(uid)
        if not user or user.is_deleted():
            return jsonify({'error': 'Not found'}), 404
        _soft_delete_user(user, by_id=uid)
        db.session.commit()
        try:
            logout_user()
            session.clear()
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Account deleted. Signing you out. Logging back in with the same Google account within the retention window will restore it.'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting own account: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>/delete', methods=['PUT'])
@require_api_auth
def admin_soft_delete_user(user_id):
    """Admin soft-delete of a member (reversible)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    if user_id == current_user.id:
        return jsonify({'error': 'Use the account page to delete your own account'}), 400
    user = User.query.get_or_404(user_id)
    if user.is_deleted():
        return jsonify({'error': 'Already deleted'}), 400
    _soft_delete_user(user, by_id=current_user.id)
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/admin/users/<int:user_id>/restore', methods=['PUT'])
@require_api_auth
def admin_restore_user(user_id):
    """Admin restore of a soft-deleted member. PII stays scrubbed until the user next
    logs in (which re-hydrates it from Google)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    user = User.query.get_or_404(user_id)
    if not user.is_deleted():
        return jsonify({'error': 'Account is not deleted'}), 400
    user.deleted_at = None
    user.deleted_by = None
    user.is_active = True
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/admin/users/<int:user_id>/purge', methods=['DELETE'])
@require_api_auth
def admin_purge_user(user_id):
    """Admin HARD-purge: permanently delete a user and ALL their data. Irreversible.
    Requires the user to be soft-deleted first (two-step safety)."""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot purge your own account'}), 400
    user = User.query.get_or_404(user_id)
    if not user.is_deleted():
        return jsonify({'error': 'Soft-delete the account before purging'}), 400
    try:
        # Shared with the scheduled retention job (retention.py) so the cascade has exactly
        # one definition — a second copy would drift the moment a model is added.
        from retention import purge_user_record
        uid = purge_user_record(db, user)
        db.session.commit()
        return jsonify({'success': True, 'purged_user_id': uid})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error purging user {user_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/token', methods=['POST'])
@login_required
def create_api_token():
    """Mint a Personal Access Token for programmatic API access (automation/agent).

    Requires an interactive logged-in session (cannot be created from another token)
    AND the 'api_tokens' permission (admins bypass). Returns the token ONCE. Send it
    as `Authorization: Bearer <token>` on API requests. Tokens expire in 30 days and
    can be revoked via DELETE /api/auth/token.
    """
    if not user_has_permission(current_user, 'api_tokens'):
        return jsonify({'error': 'You do not have permission to create API tokens. Ask an admin to grant the "api_tokens" permission.'}), 403
    try:
        from models import UserSession
        import secrets as _secrets
        token = _secrets.token_urlsafe(32)
        sess = UserSession(
            user_id=current_user.id,
            session_token=token,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db.session.add(sess)
        db.session.commit()
        # Verify it actually persisted and is readable back (catches silent write failures)
        check = UserSession.query.filter_by(session_token=token).first()
        if not check:
            return jsonify({'error': 'Token did not persist (DB write silently failed)'}), 500
        return jsonify({
            'token': token,
            'token_type': 'Bearer',
            'expires_in_days': 30,
            'persisted': True,
            'usage': 'Send header: Authorization: Bearer <token>'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating API token: {e}", exc_info=True)
        return jsonify({'error': f'Failed to create token: {type(e).__name__}: {str(e)}'}), 500


@app.route('/api/auth/token', methods=['DELETE'])
@require_api_auth
def revoke_api_token():
    """Revoke a Personal Access Token. Body {"token": "..."} to revoke a specific token,
    or omit to revoke the Bearer token used on this request. Only revokes your own tokens.
    """
    try:
        from models import UserSession
        user = getattr(request, 'current_user', None) or current_user
        data = request.get_json(silent=True) or {}
        target = data.get('token')
        if not target:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                target = auth_header[7:]
        if not target:
            return jsonify({'error': 'No token specified'}), 400
        sess = UserSession.query.filter_by(session_token=target, user_id=user.id).first()
        if not sess:
            return jsonify({'error': 'Token not found'}), 404
        db.session.delete(sess)
        db.session.commit()
        return jsonify({'success': True, 'revoked': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error revoking API token: {e}")
        return jsonify({'error': 'Failed to revoke token'}), 500


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
            logger.error(f"No data returned for {symbol} - check Yahoo Finance API status")
            return jsonify({
                'error': f'Unable to fetch data for {symbol}. Yahoo Finance may be rate limiting or the symbol may be invalid.',
                'symbol': symbol,
                'suggestion': 'Try again in a few moments or verify the symbol is correct.'
            }), 503
        
        if stock_data.empty:
            logger.error(f"Empty dataframe for {symbol}")
            return jsonify({
                'error': f'No data available for {symbol}',
                'symbol': symbol,
                'suggestion': 'Please verify the symbol is correct.'
            }), 404
        
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


@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    git_rev = os.environ.get('GIT_COMMIT', 'unknown')
    logger.debug("Health check requested")
    return jsonify({
        'status': 'healthy',
        'message': 'Server is running',
        'git_commit': git_rev,
        'routes_registered': [str(rule) for rule in app.url_map.iter_rules()]
    })


@app.route('/api/import-data', methods=['POST'])
def import_data():
    """One-time data import from SQLite export JSON. Remove after use."""
    import_key = os.environ.get('IMPORT_KEY', '')
    provided_key = request.headers.get('X-Import-Key', '')
    if not import_key or provided_key != import_key:
        return jsonify({'error': 'Unauthorized'}), 401

    if not PHASE2_ENABLED:
        return jsonify({'error': 'Database not initialized'}), 503

    from models import db
    from sqlalchemy import text

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    results = {}
    # Import order matters for foreign keys
    table_order = [
        'users', 'user_sessions', 'watchlist', 'portfolio_accounts', 'portfolio',
        'transactions', 'options_positions', 'alerts', 'market_conditions',
        'portfolio_snapshots', 'alert_suggestions', 'dividends',
        'discussion_threads', 'thread_replies', 'thread_votes', 'copy_trading_follows',
    ]

    for table in table_order:
        if table not in data:
            continue
        rows = data[table]
        if not rows:
            continue

        imported = 0
        for row in rows:
            cols = list(row.keys())
            col_list = ', '.join(f'"{c}"' for c in cols)
            placeholders = ', '.join(f':{c}' for c in cols)
            sql = text(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING')
            try:
                db.session.execute(sql, row)
                imported += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Import error in {table}: {e}")
                continue

        # Reset sequence
        try:
            db.session.execute(text(
                f"SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM \"{table}\"), 0) + 1, false)"
            ))
        except Exception:
            pass

        db.session.commit()
        results[table] = f"{imported}/{len(rows)}"

    return jsonify({'results': results})


@app.route('/api/version', methods=['GET'])
def version():
    """Return the deployed commit SHA for deployment verification."""
    return jsonify({'commit': os.environ.get('GIT_COMMIT', 'unknown')})


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

# Portfolio Account Management
@app.route('/api/portfolio/accounts', methods=['GET'])
def list_portfolio_accounts():
    """List all portfolio accounts for the user."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        accounts = PortfolioAccount.query.filter_by(user_id=current_user.id).order_by(PortfolioAccount.created_at).all()
        
        # Calculate totals per account
        result = []
        for acc in accounts:
            holdings = Portfolio.query.filter_by(user_id=current_user.id, account_id=acc.id).all()
            total_value = sum(float(h.quantity) * float(h.current_price or h.average_cost) for h in holdings)
            total_cost = sum(float(h.quantity) * float(h.average_cost) for h in holdings)
            cash = float(acc.cash_balance) if acc.cash_balance else 0
            result.append({
                **acc.to_dict(),
                'total_value': round(total_value, 2),
                'total_cost': round(total_cost, 2),
                'gain_loss': round(total_value - total_cost, 2),
                'holdings_count': len(holdings),
                'total_account_value': round(total_value + cash, 2),
                'cash_pct': round((cash / (total_value + cash) * 100) if (total_value + cash) > 0 else 0, 1)
            })
        
        # Also get unassigned holdings count
        unassigned = Portfolio.query.filter_by(user_id=current_user.id, account_id=None).count()
        
        return jsonify({'accounts': result, 'unassigned_count': unassigned})
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/accounts', methods=['POST'])
def create_portfolio_account():
    """Create a new portfolio account."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        investment_style = data.get('investment_style', 'moderate')
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Account name is required'}), 400
        
        valid_styles = ['aggressive', 'moderate', 'conservative', 'balanced']
        if investment_style not in valid_styles:
            return jsonify({'error': f'Invalid style. Must be one of: {", ".join(valid_styles)}'}), 400
        
        existing = PortfolioAccount.query.filter_by(user_id=current_user.id, name=name).first()
        if existing:
            return jsonify({'error': 'Account with this name already exists'}), 400
        
        account = PortfolioAccount(
            user_id=current_user.id,
            name=name,
            investment_style=investment_style,
            description=description,
            cash_balance=float(data.get('cash_balance', 0))
        )
        db.session.add(account)
        db.session.commit()
        
        return jsonify({'account': account.to_dict(), 'message': 'Account created'}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/accounts/<int:account_id>', methods=['PUT'])
def update_portfolio_account(account_id):
    """Update portfolio account settings."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        account = PortfolioAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        data = request.get_json()
        if 'name' in data and data['name'].strip():
            account.name = data['name'].strip()
        if 'investment_style' in data:
            valid_styles = ['aggressive', 'moderate', 'conservative', 'balanced']
            if data['investment_style'] in valid_styles:
                account.investment_style = data['investment_style']
        if 'description' in data:
            account.description = data['description'].strip()
        if 'cash_balance' in data:
            account.cash_balance = max(0, float(data['cash_balance']))
        
        db.session.commit()
        return jsonify({'account': account.to_dict(), 'message': 'Account updated'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/accounts/<int:account_id>', methods=['DELETE'])
def delete_portfolio_account(account_id):
    """Delete a portfolio account (moves holdings to unassigned)."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        account = PortfolioAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        # Unassign holdings instead of deleting them
        Portfolio.query.filter_by(account_id=account_id).update({'account_id': None})
        Transaction.query.filter_by(account_id=account_id).update({'account_id': None})
        
        db.session.delete(account)
        db.session.commit()
        return jsonify({'message': 'Account deleted, holdings moved to unassigned'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/accounts/<int:account_id>/cash', methods=['PUT'])
def update_account_cash(account_id):
    """Update cash balance for an account."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        account = PortfolioAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        data = request.get_json()
        account.cash_balance = max(0, float(data.get('cash_balance', 0)))
        db.session.commit()
        return jsonify({'message': 'Cash balance updated', 'cash_balance': float(account.cash_balance)})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating cash: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/cash-optimization', methods=['GET'])
def get_cash_optimization():
    """Get cash optimization suggestions based on account style and holdings."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        account_id = request.args.get('account_id', type=int)
        if not account_id:
            return jsonify({'error': 'account_id is required'}), 400
        
        account = PortfolioAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        cash = float(account.cash_balance) if account.cash_balance else 0
        if cash <= 0:
            return jsonify({'suggestions': [], 'message': 'No free cash to optimize'})
        
        holdings = Portfolio.query.filter_by(user_id=current_user.id, account_id=account_id).all()
        invested_value = sum(float(h.quantity) * float(h.current_price or h.average_cost) for h in holdings)
        total_account = invested_value + cash
        cash_pct = (cash / total_account * 100) if total_account > 0 else 100
        
        held_symbols = {h.symbol for h in holdings}
        style = account.investment_style or 'moderate'
        
        # Suggestions based on investment style
        suggestions = []
        
        # Style-specific ETF suggestions
        style_etfs = {
            'aggressive': [
                {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust (Nasdaq 100)', 'reason': 'High-growth tech exposure for aggressive portfolios', 'allocation': 30},
                {'symbol': 'ARKK', 'name': 'ARK Innovation ETF', 'reason': 'Disruptive innovation exposure', 'allocation': 15},
                {'symbol': 'SOXX', 'name': 'iShares Semiconductor ETF', 'reason': 'Semiconductor sector growth play', 'allocation': 15},
                {'symbol': 'VGT', 'name': 'Vanguard Info Tech ETF', 'reason': 'Broad tech sector allocation', 'allocation': 20},
                {'symbol': 'TQQQ', 'name': 'ProShares UltraPro QQQ', 'reason': '3x leveraged Nasdaq for high-risk plays', 'allocation': 10},
            ],
            'moderate': [
                {'symbol': 'VOO', 'name': 'Vanguard S&P 500 ETF', 'reason': 'Core S&P 500 index exposure', 'allocation': 35},
                {'symbol': 'QQQ', 'name': 'Invesco QQQ Trust', 'reason': 'Growth tilt via Nasdaq 100', 'allocation': 20},
                {'symbol': 'SCHD', 'name': 'Schwab US Dividend Equity', 'reason': 'Reliable dividend income', 'allocation': 20},
                {'symbol': 'BND', 'name': 'Vanguard Total Bond Market', 'reason': 'Fixed income ballast', 'allocation': 15},
                {'symbol': 'VNQ', 'name': 'Vanguard Real Estate ETF', 'reason': 'Real estate diversification', 'allocation': 10},
            ],
            'conservative': [
                {'symbol': 'BND', 'name': 'Vanguard Total Bond Market', 'reason': 'Core bond holding for stability', 'allocation': 30},
                {'symbol': 'SCHD', 'name': 'Schwab US Dividend Equity', 'reason': 'High-quality dividend stocks', 'allocation': 25},
                {'symbol': 'VIG', 'name': 'Vanguard Dividend Appreciation', 'reason': 'Dividend growth for income', 'allocation': 20},
                {'symbol': 'SHY', 'name': 'iShares 1-3 Year Treasury', 'reason': 'Short-term treasury safety', 'allocation': 15},
                {'symbol': 'VTIP', 'name': 'Vanguard Short-Term TIPS', 'reason': 'Inflation protection', 'allocation': 10},
            ],
            'balanced': [
                {'symbol': 'VTI', 'name': 'Vanguard Total Stock Market', 'reason': 'Broad US equity exposure', 'allocation': 30},
                {'symbol': 'VXUS', 'name': 'Vanguard Total International', 'reason': 'International diversification', 'allocation': 20},
                {'symbol': 'BND', 'name': 'Vanguard Total Bond Market', 'reason': 'Bond allocation for balance', 'allocation': 20},
                {'symbol': 'SCHD', 'name': 'Schwab US Dividend Equity', 'reason': 'Dividend income stream', 'allocation': 15},
                {'symbol': 'GLD', 'name': 'SPDR Gold Shares', 'reason': 'Gold as inflation hedge', 'allocation': 15},
            ]
        }
        
        etfs = style_etfs.get(style, style_etfs['moderate'])
        
        for etf in etfs:
            already_held = etf['symbol'] in held_symbols
            dollar_amount = round(cash * etf['allocation'] / 100, 2)
            suggestions.append({
                'symbol': etf['symbol'],
                'name': etf['name'],
                'reason': etf['reason'],
                'allocation_pct': etf['allocation'],
                'dollar_amount': dollar_amount,
                'already_held': already_held,
                'action': 'Add to position' if already_held else 'New position'
            })
        
        # Cash analysis
        if cash_pct > 30:
            urgency = 'high'
            message = f'{cash_pct:.0f}% of your account is in cash — significant drag on returns. Consider deploying capital.'
        elif cash_pct > 15:
            urgency = 'medium'
            message = f'{cash_pct:.0f}% cash allocation is above typical targets. Consider partially investing.'
        else:
            urgency = 'low'
            message = f'{cash_pct:.0f}% cash is a reasonable reserve. Optional to optimize further.'
        
        return jsonify({
            'account_name': account.name,
            'style': style,
            'cash_balance': cash,
            'invested_value': round(invested_value, 2),
            'total_account_value': round(total_account, 2),
            'cash_pct': round(cash_pct, 1),
            'urgency': urgency,
            'message': message,
            'suggestions': suggestions
        })
    except Exception as e:
        logger.error(f"Error getting cash optimization: {e}")
        return jsonify({'error': str(e)}), 500

# Income (dividend / special distribution / share-lending / interest) tracking endpoints
INCOME_TYPES = {'dividend', 'special', 'lending', 'interest'}

@app.route('/api/portfolio/dividends', methods=['GET'])
def get_dividends():
    """Get dividend history with optional filters."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        query = Dividend.query.filter_by(user_id=current_user.id)
        account_id = request.args.get('account_id')
        if account_id and account_id.isdigit():
            query = query.filter_by(account_id=int(account_id))
        elif account_id == 'unassigned':
            query = query.filter(Dividend.account_id.is_(None))
        symbol = request.args.get('symbol')
        if symbol:
            query = query.filter_by(symbol=symbol.upper())
        dividends = query.order_by(Dividend.pay_date.desc(), Dividend.recorded_at.desc()).all()
        return jsonify([d.to_dict() for d in dividends])
    except Exception as e:
        logger.error(f"Error getting dividends: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/dividends', methods=['POST'])
def record_dividend():
    """Record a new dividend payment."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        data = request.get_json()
        if not data or not data.get('symbol') or not data.get('total_amount'):
            return jsonify({'error': 'symbol and total_amount are required'}), 400
        symbol = data['symbol'].upper().strip()
        total_amount = float(data['total_amount'])
        shares = float(data.get('shares', 0))
        amount_per_share = float(data.get('amount_per_share', 0))
        if shares > 0 and amount_per_share == 0 and total_amount > 0:
            amount_per_share = total_amount / shares
        elif amount_per_share > 0 and shares > 0 and total_amount == 0:
            total_amount = amount_per_share * shares
        income_type = (data.get('income_type') or 'dividend').lower().strip()
        if income_type not in INCOME_TYPES:
            income_type = 'dividend'
        # Only regular dividends can be qualified; special/lending/interest are ordinary.
        if 'qualified' in data:
            qualified = bool(data.get('qualified')) and income_type == 'dividend'
        else:
            qualified = (income_type == 'dividend')
        dividend = Dividend(
            user_id=current_user.id,
            account_id=int(data['account_id']) if data.get('account_id') else None,
            symbol=symbol,
            amount_per_share=amount_per_share,
            shares=shares,
            total_amount=total_amount,
            ex_date=datetime.strptime(data['ex_date'], '%Y-%m-%d').date() if data.get('ex_date') else None,
            pay_date=datetime.strptime(data['pay_date'], '%Y-%m-%d').date() if data.get('pay_date') else None,
            reinvested=data.get('reinvested', False),
            income_type=income_type,
            qualified=qualified,
            notes=data.get('notes', '')
        )
        db.session.add(dividend)
        db.session.commit()
        return jsonify(dividend.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording dividend: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/dividends/<int:dividend_id>', methods=['DELETE'])
def delete_dividend(dividend_id):
    """Delete a dividend record."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        dividend = Dividend.query.filter_by(id=dividend_id, user_id=current_user.id).first()
        if not dividend:
            return jsonify({'error': 'Dividend not found'}), 404
        db.session.delete(dividend)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting dividend: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/dividends/<int:dividend_id>', methods=['PUT'])
def update_dividend(dividend_id):
    """Update an income record — reclassify its type (dividend/special/lending/interest) or edit notes."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        dividend = Dividend.query.filter_by(id=dividend_id, user_id=current_user.id).first()
        if not dividend:
            return jsonify({'error': 'Dividend not found'}), 404
        data = request.get_json() or {}
        if 'income_type' in data:
            it = (data.get('income_type') or 'dividend').lower().strip()
            if it not in INCOME_TYPES:
                return jsonify({'error': 'invalid income_type'}), 400
            dividend.income_type = it
            if it != 'dividend':  # non-dividend income is inherently ordinary
                dividend.qualified = False
        if 'qualified' in data:
            dividend.qualified = bool(data.get('qualified')) and (dividend.income_type == 'dividend')
        if 'notes' in data:
            dividend.notes = (data.get('notes') or '').strip()
        db.session.commit()
        return jsonify(dividend.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating dividend: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/dividends/summary', methods=['GET'])
def get_dividend_summary():
    """Get aggregate dividend summary."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    try:
        from sqlalchemy import func as sqlfunc
        account_id = request.args.get('account_id')
        base_query = Dividend.query.filter_by(user_id=current_user.id)
        if account_id and account_id.isdigit():
            base_query = base_query.filter_by(account_id=int(account_id))
        elif account_id == 'unassigned':
            base_query = base_query.filter(Dividend.account_id.is_(None))

        # Total dividend income
        total_income = db.session.query(sqlfunc.sum(Dividend.total_amount)).filter(
            Dividend.user_id == current_user.id
        )
        if account_id and account_id.isdigit():
            total_income = total_income.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            total_income = total_income.filter(Dividend.account_id.is_(None))
        total_income = total_income.scalar() or 0

        # Per-symbol breakdown
        symbol_query = db.session.query(
            Dividend.symbol,
            sqlfunc.sum(Dividend.total_amount),
            sqlfunc.count(Dividend.id)
        ).filter(Dividend.user_id == current_user.id)
        if account_id and account_id.isdigit():
            symbol_query = symbol_query.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            symbol_query = symbol_query.filter(Dividend.account_id.is_(None))
        symbol_rows = symbol_query.group_by(Dividend.symbol).all()

        by_symbol = [{'symbol': row[0], 'total': round(float(row[1]), 2), 'count': row[2]} for row in symbol_rows]

        # Per-type breakdown (dividend / special / lending / interest); null -> dividend
        type_query = db.session.query(
            Dividend.income_type,
            sqlfunc.sum(Dividend.total_amount),
            sqlfunc.count(Dividend.id)
        ).filter(Dividend.user_id == current_user.id)
        if account_id and account_id.isdigit():
            type_query = type_query.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            type_query = type_query.filter(Dividend.account_id.is_(None))
        _agg = {}
        for row in type_query.group_by(Dividend.income_type).all():
            t = row[0] or 'dividend'
            bucket = _agg.setdefault(t, {'total': 0.0, 'count': 0})
            bucket['total'] += float(row[1] or 0)
            bucket['count'] += int(row[2] or 0)
        by_type = [{'type': t, 'total': round(v['total'], 2), 'count': v['count']} for t, v in _agg.items()]

        # YTD income
        year_start = datetime(datetime.now().year, 1, 1).date()
        ytd_query = db.session.query(sqlfunc.sum(Dividend.total_amount)).filter(
            Dividend.user_id == current_user.id,
            Dividend.pay_date >= year_start
        )
        if account_id and account_id.isdigit():
            ytd_query = ytd_query.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            ytd_query = ytd_query.filter(Dividend.account_id.is_(None))
        ytd_income = ytd_query.scalar() or 0

        # Monthly average (last 12 months)
        year_ago = (datetime.now() - timedelta(days=365)).date()
        recent_query = db.session.query(sqlfunc.sum(Dividend.total_amount)).filter(
            Dividend.user_id == current_user.id,
            Dividend.pay_date >= year_ago
        )
        if account_id and account_id.isdigit():
            recent_query = recent_query.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            recent_query = recent_query.filter(Dividend.account_id.is_(None))
        recent_total = recent_query.scalar() or 0
        monthly_avg = round(float(recent_total) / 12, 2)

        # Qualified (long-term rate) vs ordinary income split. Only regular
        # dividends flagged qualified count as qualified; everything else is ordinary.
        qual_query = db.session.query(sqlfunc.sum(Dividend.total_amount)).filter(
            Dividend.user_id == current_user.id,
            Dividend.income_type == 'dividend',
            Dividend.qualified.is_(True)
        )
        if account_id and account_id.isdigit():
            qual_query = qual_query.filter(Dividend.account_id == int(account_id))
        elif account_id == 'unassigned':
            qual_query = qual_query.filter(Dividend.account_id.is_(None))
        qualified_income = round(float(qual_query.scalar() or 0), 2)
        ordinary_income = round(float(total_income) - qualified_income, 2)

        return jsonify({
            'total_income': round(float(total_income), 2),
            'ytd_income': round(float(ytd_income), 2),
            'monthly_avg': monthly_avg,
            'qualified_income': qualified_income,
            'ordinary_income': ordinary_income,
            'by_symbol': sorted(by_symbol, key=lambda x: x['total'], reverse=True),
            'by_type': sorted(by_type, key=lambda x: x['total'], reverse=True),
            'payment_count': base_query.count()
        })
    except Exception as e:
        logger.error(f"Error getting dividend summary: {e}")
        return jsonify({'error': str(e)}), 500

# Phase 2: Portfolio endpoints
# Symbols that are NOT real, quotable tickers — manual placeholder/total lines
# (e.g. the Transamerica 401k aggregate). Never send these to the price provider;
# yfinance retries ~20s trying to resolve them, which pushed cold-cache portfolio
# loads past the request timeout. Their stored current_price (= cost) is kept.
NONQUOTABLE_SYMBOLS = {'TA401K'}


@app.route('/api/portfolio/list', methods=['GET'])
def list_portfolio_holdings():
    """Get list of portfolio holdings (Phase 2)."""
    if not PHASE2_ENABLED or not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        # Filter by account if specified
        account_id = request.args.get('account_id')
        query = Portfolio.query.filter_by(user_id=current_user.id)
        if account_id:
            if account_id == 'unassigned':
                query = query.filter_by(account_id=None)
            else:
                query = query.filter_by(account_id=int(account_id))
        
        holdings = query.all()
        
        # Update current prices — best-effort + cached. A single symbol's
        # data-provider error (rate limit, delisted/new IPO ticker) or a transient
        # DB write must NEVER fail the whole request, or the watchlist renders empty.
        # Prices are cached for PRICE_TTL to avoid a live Yahoo fetch per holding on
        # every call (which is what was rate-limiting into 500s).
        #
        # Two things kept a cold-cache load slow enough to hit the worker/gateway
        # timeout (→ 500): non-quotable placeholder tickers (the 401k TOTAL line
        # 'TA401K' isn't a real symbol and made yfinance retry ~22s), and pricing
        # every stale symbol SERIALLY. So: skip placeholders, and fetch the rest in
        # parallel under a hard time budget — whatever doesn't finish keeps its
        # cached price and refreshes next call.
        import concurrent.futures
        now = datetime.utcnow()
        PRICE_TTL = timedelta(minutes=10)
        prices_updated = False
        stale = [
            h for h in holdings
            if h.symbol not in NONQUOTABLE_SYMBOLS
            and not (h.current_price and h.last_updated and (now - h.last_updated) < PRICE_TTL)
        ]

        def _fetch_price(sym):
            try:
                sd = data_fetcher.fetch_stock_data(sym, '1d')
                if sd is not None and not sd.empty:
                    return sym, float(sd.iloc[-1]['Close'])
            except Exception as pe:
                logger.warning(f"Price update failed for {sym}: {pe}")
            return sym, None

        fresh_prices = {}
        stale_syms = {h.symbol for h in stale}
        if stale:
            ex = concurrent.futures.ThreadPoolExecutor(max_workers=8)
            try:
                futs = [ex.submit(_fetch_price, h.symbol) for h in stale]
                for fut in concurrent.futures.as_completed(futs, timeout=12):
                    sym, px = fut.result()
                    if px is not None:
                        fresh_prices[sym] = px
            except concurrent.futures.TimeoutError:
                logger.warning("portfolio/list price refresh hit 12s budget; using cached for the rest")
            except Exception as pe:
                logger.warning(f"portfolio/list parallel price refresh error: {pe}")
            finally:
                ex.shutdown(wait=False)  # don't block the response on stragglers

        for holding in holdings:
            if holding.symbol in fresh_prices:
                holding.current_price = fresh_prices[holding.symbol]
                holding.last_updated = now
                prices_updated = True
            elif holding.symbol in stale_syms and holding.current_price:
                # Fetch failed or ran past the budget, but we have a cached price —
                # mark it attempted (bump last_updated) so it isn't re-fetched on every
                # call (which kept warm loads slow); it retries after PRICE_TTL.
                holding.last_updated = now
                prices_updated = True
        if prices_updated:
            try:
                db.session.commit()
            except Exception as ce:
                db.session.rollback()
                logger.warning(f"Portfolio price commit failed (holdings still returned): {ce}")

        return jsonify({
            'holdings': [h.to_dict() for h in holdings],
            'total_value': sum(float(h.quantity) * float(h.current_price) for h in holdings if h.current_price),
            'total_cost': sum(float(h.quantity) * float(h.average_cost) for h in holdings)
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
            account_id = data.get('account_id')  # Optional portfolio account
            
            if not all([symbol, quantity > 0, price > 0]):
                return jsonify({'error': 'Missing or invalid fields'}), 400
            
            # Normalize crypto symbols (e.g., AVAX → AVAX-USD for yfinance)
            original_symbol = symbol
            symbol = normalize_crypto_symbol(symbol, asset_type)
            if symbol != original_symbol:
                logger.info(f"Normalized crypto symbol: {original_symbol} → {symbol}")
            
            # Parse purchase date if provided (datetime is imported at module scope;
            # a local import here shadowed it and broke the no-date path).
            parsed_date = None
            if purchase_date:
                try:
                    parsed_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))
                except Exception:
                    parsed_date = datetime.utcnow()
            else:
                parsed_date = datetime.utcnow()
            
            # Validate account_id if provided
            if account_id:
                account_id = int(account_id)
                account = PortfolioAccount.query.filter_by(id=account_id, user_id=current_user.id).first()
                if not account:
                    return jsonify({'error': 'Invalid account'}), 400
            
            # Check if position exists (scoped to account)
            existing = Portfolio.query.filter_by(
                user_id=current_user.id,
                symbol=symbol,
                asset_type=asset_type,
                account_id=account_id
            ).first()
            
            if existing:
                # Update average cost - cast DB Decimal values to float to avoid type mismatch
                logger.info(f"Updating existing {symbol}: qty type={type(existing.quantity).__name__}, avg_cost type={type(existing.average_cost).__name__}")
                existing_quantity = float(existing.quantity)
                existing_avg_cost = float(existing.average_cost)
                total_cost = (existing_quantity * existing_avg_cost) + (quantity * price)
                total_quantity = existing_quantity + quantity
                logger.info(f"Computed: total_cost={total_cost}, total_quantity={total_quantity}")
                existing.average_cost = total_cost / total_quantity
                existing.quantity = total_quantity
                # Keep original purchase date for existing positions
            else:
                # Create new position
                position = Portfolio(
                    user_id=current_user.id,
                    account_id=account_id,
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
                account_id=account_id,
                symbol=symbol,
                asset_type=asset_type,
                transaction_type='buy',
                quantity=quantity,
                price=price,
                transaction_date=parsed_date
            )
            db.session.add(transaction)
            db.session.commit()
            
            resp = {'message': f'Added {quantity} shares of {symbol}', 'success': True}
            if symbol != original_symbol:
                resp['corrected_symbol'] = symbol
                resp['message'] = f'Added {quantity} shares of {symbol} (normalized from {original_symbol})'
            return jsonify(resp), 201
        
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
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


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


def _parse_txn_date(s):
    """Parse a transaction date from ISO / YYYY-MM-DD / US formats; None if unparseable."""
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s.replace('Z', ''))
    except Exception:
        pass
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


@app.route('/api/portfolio/transactions/import', methods=['POST'])
@require_api_auth
def import_transactions():
    """Bulk-import historical transactions (buys + sells) for cost-basis / tax.

    Body: {"transactions": [{symbol, transaction_type, quantity, price,
    transaction_date, account_id?, asset_type?, commission?, notes?}, ...],
    "account_id": <default account for rows without one>}

    Inserts raw Transaction rows only — does NOT touch holdings or cash (these
    are historical records, not live position changes). Dedupes on
    (symbol, type, date, qty, price, account) so re-imports are idempotent.
    """
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        data = request.get_json() or {}
        rows = data.get('transactions') or []
        default_account = data.get('account_id')
        if not isinstance(rows, list) or not rows:
            return jsonify({'error': 'transactions[] required'}), 400

        def _key(sym, ttype, d, qty, price, acct):
            return (sym, ttype, d, round(float(qty or 0), 6), round(float(price or 0), 4), acct)

        existing = set()
        for t in Transaction.query.filter_by(user_id=user_id).all():
            d = t.transaction_date.date().isoformat() if t.transaction_date else None
            existing.add(_key(t.symbol.upper(), t.transaction_type, d, t.quantity, t.price, t.account_id))

        imported = skipped = 0
        errors = []
        for r in rows:
            try:
                sym = (r.get('symbol') or '').upper().strip()
                ttype = (r.get('transaction_type') or '').lower().strip()
                if ttype in ('b', 'buy', 'bought'):
                    ttype = 'buy'
                elif ttype in ('s', 'sell', 'sold'):
                    ttype = 'sell'
                if not sym or ttype not in ('buy', 'sell'):
                    skipped += 1
                    continue
                qty = float(r.get('quantity') or 0)
                price = float(r.get('price') or 0)
                if qty <= 0:
                    skipped += 1
                    continue
                acct = r.get('account_id', default_account)
                acct = int(acct) if acct not in (None, '', 'null') else None
                dt = _parse_txn_date(r.get('transaction_date'))
                dkey = dt.date().isoformat() if dt else None
                k = _key(sym, ttype, dkey, qty, price, acct)
                if k in existing:
                    skipped += 1
                    continue
                db.session.add(Transaction(
                    user_id=user_id, account_id=acct, symbol=sym,
                    asset_type=(r.get('asset_type') or 'stock'),
                    transaction_type=ttype, quantity=qty, price=price,
                    commission=float(r.get('commission') or 0),
                    transaction_date=(dt or datetime.utcnow()),
                    notes=r.get('notes')))
                existing.add(k)
                imported += 1
            except Exception as ex:
                errors.append(str(ex))
                skipped += 1
        db.session.commit()
        return jsonify({'imported': imported, 'skipped': skipped, 'errors': errors[:5]}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error importing transactions: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions/<int:txn_id>', methods=['DELETE'])
@require_api_auth
def delete_transaction(txn_id):
    """Delete a single transaction (for cleaning up stray/duplicate records)."""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        t = Transaction.query.filter_by(id=txn_id, user_id=user_id).first()
        if not t:
            return jsonify({'error': 'Transaction not found'}), 404
        db.session.delete(t)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting transaction: {e}")
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


# Selectable intervals for alerts and watchlist refresh. Faster options are
# gated per role via each config's 'floors', so future member tiers can unlock
# them by editing one dict — no loop/UI changes needed.
INTERVAL_CONFIG = {
    'alerts': {
        'column': 'alert_check_interval',
        'default': 900,
        'options': [
            {'seconds': 60,    'label': '1 minute'},
            {'seconds': 300,   'label': '5 minutes'},
            {'seconds': 900,   'label': '15 minutes'},
            {'seconds': 1800,  'label': '30 minutes'},
            {'seconds': 3600,  'label': '1 hour'},
            {'seconds': 21600, 'label': '6 hours'},
        ],
        'floors': {'admin': 60, 'moderator': 60, 'premium': 300, 'user': 900},
        'floor_default': 900,
    },
    'watchlist': {
        'column': 'watchlist_refresh_interval',
        'default': 60,
        'options': [
            {'seconds': 15,  'label': '15 seconds'},
            {'seconds': 30,  'label': '30 seconds'},
            {'seconds': 60,  'label': '1 minute'},
            {'seconds': 120, 'label': '2 minutes'},
            {'seconds': 300, 'label': '5 minutes'},
        ],
        'floors': {'admin': 15, 'moderator': 15, 'premium': 30, 'user': 60},
        'floor_default': 60,
    },
}


def _interval_floor(cfg, role):
    return cfg['floors'].get((role or 'user'), cfg['floor_default'])


def _get_interval_payload(kind):
    """Shared GET handler: current value, tier floor, and locked-flagged options."""
    cfg = INTERVAL_CONFIG[kind]
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    user = User.query.get(user_id)
    role = user.role if user else 'user'
    floor = _interval_floor(cfg, role)
    current = getattr(user, cfg['column'], None) or cfg['default']
    options = [{**opt, 'locked': opt['seconds'] < floor} for opt in cfg['options']]
    return jsonify({
        'interval': current,
        'min_interval': floor,
        'default': cfg['default'],
        'role': role,
        'options': options
    })


def _set_interval(kind):
    """Shared PUT handler: validate against options + tier floor, then persist."""
    cfg = INTERVAL_CONFIG[kind]
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    try:
        interval = int(data.get('interval'))
    except (TypeError, ValueError):
        return jsonify({'error': 'interval (seconds) is required'}), 400

    allowed = {o['seconds'] for o in cfg['options']}
    if interval not in allowed:
        return jsonify({'error': 'Invalid interval', 'options': sorted(allowed)}), 400

    floor = _interval_floor(cfg, user.role)
    if interval < floor:
        return jsonify({
            'error': f'Your tier ({user.role or "user"}) allows a minimum of {floor}s. Upgrade for faster updates.',
            'min_interval': floor
        }), 403

    setattr(user, cfg['column'], interval)
    db.session.commit()
    return jsonify({'message': 'Interval updated', 'interval': interval})


@app.route('/api/monitoring/interval', methods=['GET'])
@require_api_auth
def get_alert_interval():
    """Alert-check interval + tier floor + option list."""
    try:
        return _get_interval_payload('alerts')
    except Exception as e:
        logger.error(f"Error getting alert interval: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/interval', methods=['PUT'])
@require_api_auth
def set_alert_interval():
    """Set the alert-check interval (validated against options + tier floor)."""
    try:
        return _set_interval('alerts')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error setting alert interval: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/watchlist-interval', methods=['GET'])
@require_api_auth
def get_watchlist_interval():
    """Watchlist refresh interval + tier floor + option list."""
    try:
        return _get_interval_payload('watchlist')
    except Exception as e:
        logger.error(f"Error getting watchlist interval: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/watchlist-interval', methods=['PUT'])
@require_api_auth
def set_watchlist_interval():
    """Set the watchlist refresh interval (validated against options + tier floor)."""
    try:
        return _set_interval('watchlist')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error setting watchlist interval: {e}")
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
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
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

def _format_holding_facts(a, intent, rec):
    """Compact fact sheet about one holding for the AI models."""
    p3 = a.get('phase3') or {}
    unit = 'contracts' if a.get('type') == 'option' else 'shares'
    lines = [
        f"Symbol: {a.get('symbol')}",
        f"Position: {a.get('quantity')} {unit}",
        f"Cost basis: ${a.get('cost_basis')} per unit (${a.get('total_cost')} total)",
        f"Current price: ${a.get('current_price')} (market value ${a.get('market_value')})",
        f"Unrealized P&L: ${a.get('pnl')} ({a.get('pnl_pct')}%)",
        f"Dividends collected on this symbol: ${a.get('dividend_income')}",
        f"Owner's stated thesis / intent: {intent or 'none recorded'}",
        "Quant signals:",
        f"  - Sentiment: {p3.get('sentiment') or 'n/a'} (score {p3.get('sentiment_score')})",
        f"  - Risk grade: {p3.get('risk_grade') or 'n/a'} (risk score {p3.get('risk_score')})",
        f"  - Technical entry score: {p3.get('entry_score')}/100 ({p3.get('entry_recommendation') or 'n/a'})",
        f"Rule-based recommendation: {rec.get('action')} — {rec.get('reason')}",
    ]
    opt = a.get('option_details')
    if opt:
        lines.append(
            f"Option: {opt.get('type')} strike ${opt.get('strike')} exp {opt.get('expiration')} "
            f"({opt.get('days_to_expiry')} days to expiry)"
        )
    return "\n".join(lines)


@app.route('/api/portfolio/holding/<int:holding_id>/ai-read', methods=['GET'])
@require_api_auth
def get_holding_ai_read(holding_id):
    """Multi-model AI read of ONE holding.

    Claude gives the primary analyst take; Gemini gives an independent
    counterpoint / bear-case (two different models, so the reads diverge instead
    of echoing). Falls back to the local LLM only when neither cloud model is
    available. Also surfaces the pre-computed quant signals (sentiment / risk /
    technical entry) that feed the models.
    """
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        holding_type = request.args.get('type', 'stock')

        # Ownership check + fetch the stated thesis/intent
        intent = None
        if holding_type == 'stock':
            row = Portfolio.query.filter_by(id=holding_id, user_id=user_id).first()
            if not row:
                return jsonify({'error': 'Holding not found'}), 404
            intent = getattr(row, 'intent', None)
        else:
            row = OptionsPosition.query.filter_by(id=holding_id, user_id=user_id).first()
            if not row:
                return jsonify({'error': 'Holding not found'}), 404

        analysis = portfolio_analyzer.analyze_holding(holding_id, holding_type)
        if not analysis:
            return jsonify({'empty': True, 'message': 'Could not analyze this holding right now.'}), 200

        p3 = analysis.get('phase3') or {}
        rec = analysis.get('recommendation') or {}
        signals = {
            'sentiment': p3.get('sentiment'),
            'sentiment_score': p3.get('sentiment_score'),
            'risk_grade': p3.get('risk_grade'),
            'risk_score': p3.get('risk_score'),
            'entry_score': p3.get('entry_score'),
        }

        facts = _format_holding_facts(analysis, intent, rec)

        analyst_system = (
            "You are a sharp, plain-spoken equity analyst. You are given the facts about ONE "
            "position a retail investor holds: cost basis, current price, unrealized P&L, the owner's "
            "stated thesis, and pre-computed quant signals (sentiment, risk grade, technical entry "
            "score). In 3-4 sentences, tell the owner where this position stands relative to their "
            "thesis and the quant signals, and name the single most important thing to watch next. "
            "Be direct and specific. No bullet points, no preamble, no hedging. Do NOT tell them to buy or sell."
        )
        counter_system = (
            "You are a rigorous, risk-focused analyst giving a SECOND OPINION on ONE position a retail "
            "investor holds. You are given cost basis, current price, unrealized P&L, the owner's stated "
            "thesis, and quant signals (sentiment, risk grade, technical entry score). In 2-3 sentences, "
            "state the strongest counter-argument or the biggest risk to the owner's current stance — the "
            "thing most likely to break the thesis. Be specific and unsentimental. No preamble, no bullet "
            "points. Do NOT give an explicit buy or sell instruction."
        )

        # Run the two cloud models in parallel (both are network-bound).
        from concurrent.futures import ThreadPoolExecutor
        results = {}
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {}
            if claude_analyzer.available():
                futs['claude'] = ex.submit(claude_analyzer.read, analyst_system, facts)
            if gemini_analyzer.available():
                futs['gemini'] = ex.submit(gemini_analyzer.read, counter_system, facts)
            for key, fut in futs.items():
                try:
                    results[key] = fut.result(timeout=45)
                except Exception as e:
                    logger.warning("Holding AI read (%s) failed: %s", key, e)
                    results[key] = None

        reads = []
        if results.get('claude'):
            reads.append({'engine': 'claude', 'label': 'Analyst Read · Claude', 'text': results['claude'].strip()})
        if results.get('gemini'):
            reads.append({'engine': 'gemini', 'label': 'Second Opinion · Gemini', 'text': results['gemini'].strip()})

        # Local fallback only if neither cloud model produced anything.
        if not reads:
            try:
                local_prompt = f"{analyst_system}\n\n{facts}\nWrite the 3-4 sentence read now."
                local = llm_analyzer._call_llm([{'role': 'user', 'content': local_prompt}], timeout=60)
                if local and not (local.lstrip().startswith("{'") or "'choices'" in local or 'rkllm_chat' in local):
                    reads.append({'engine': 'local', 'label': 'Local LLM', 'text': local.strip()})
            except Exception as e:
                logger.warning("Local LLM fallback failed for holding ai-read: %s", e)

        if not reads:
            return jsonify({'empty': True, 'signals': signals, 'symbol': analysis.get('symbol'),
                            'message': 'AI analysis unavailable right now.'}), 200

        return jsonify({
            'symbol': analysis.get('symbol'),
            'signals': signals,
            'recommendation': {'action': rec.get('action'), 'reason': rec.get('reason')},
            'reads': reads,
        }), 200

    except Exception as e:
        logger.error(f"Error in holding ai-read {holding_id}: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'AI analysis temporarily unavailable'}), 200


@app.route('/api/ai/status', methods=['GET'])
@require_api_auth
def get_ai_status():
    """Diagnostic: which AI engines are wired up (no secrets exposed, just booleans).

    ?test=1 additionally fires a tiny live Gemini call and returns the raw error
    string if it fails — for diagnosing why a provider is silent.
    """
    import claude_analyzer as _cl
    import gemini_analyzer as _gm
    out = {
        'claude': {
            'available': claude_analyzer.available(),
            'package_importable': _cl._ANTHROPIC_AVAILABLE,
            'key_set': bool(getattr(Config, 'ANTHROPIC_API_KEY', '')),
            'model': claude_analyzer.model,
        },
        'gemini': {
            'available': gemini_analyzer.available(),
            'package_importable': _gm._GENAI_AVAILABLE,
            'key_set': bool(getattr(Config, 'GOOGLE_AI_API_KEY', '')),
            'model': gemini_analyzer.model,
        },
    }
    if request.args.get('test') == '1':
        # The booleans above are free; ?test=1 fires live Claude and Gemini calls, so the
        # diagnostic stays open while the part that costs money does not.
        if not _can_use_ai():
            return jsonify({'error': 'Live provider tests require the "ai_analysis" permission.',
                            'missing_permission': 'ai_analysis'}), 403
        if claude_analyzer.available():
            try:
                # Live one-shot — reflects exactly what users get, and now fails fast
                # (15s timeout) instead of hanging the whole request.
                out['claude']['test_read'] = claude_analyzer.read(
                    "Reply with the single word OK.", "Say OK.", max_tokens=10)
            except Exception as e:
                out['claude']['test_error'] = repr(e)
            out['claude']['last_error'] = getattr(claude_analyzer, 'last_error', None)
        if gemini_analyzer.available():
            try:
                out['gemini']['available_models'] = gemini_analyzer.list_models()
            except Exception as e:
                out['gemini']['list_error'] = repr(e)
            try:
                # Uses the self-healing read path, so this reflects what users get.
                out['gemini']['test_read'] = gemini_analyzer.read("Reply with the single word OK.", "Say OK.")
                out['gemini']['resolved_model'] = gemini_analyzer._resolved_model
            except Exception as e:
                out['gemini']['test_error'] = repr(e)
            out['gemini']['last_error'] = getattr(gemini_analyzer, 'last_error', None)
    return jsonify(out), 200


@app.route('/api/portfolio/holding/<int:holding_id>', methods=['DELETE'])
@require_api_auth
def delete_holding(holding_id):
    """Delete a portfolio holding"""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Phase 2 not enabled'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
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
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
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
        
        if 'account_id' in data:
            new_account_id = data['account_id']
            if new_account_id is not None:
                account = PortfolioAccount.query.filter_by(id=new_account_id, user_id=user_id).first()
                if not account:
                    return jsonify({'error': 'Account not found'}), 404
            holding.account_id = new_account_id

        if 'intent' in data:
            val = data['intent']
            holding.intent = val if val in ('core', 'lottery', 'signal') else None

        if 'ipo_lock_until' in data:
            val = data['ipo_lock_until']
            if val:
                try:
                    from datetime import datetime as _dt
                    holding.ipo_lock_until = _dt.fromisoformat(str(val)[:10]).date()
                except Exception:
                    return jsonify({'error': 'ipo_lock_until must be YYYY-MM-DD'}), 400
            else:
                holding.ipo_lock_until = None

        # Per-position take-profit / stop-loss targets (% of average cost).
        # Send null/empty to clear. TP must be positive; SL between 0 and 100.
        for field, label in (('take_profit_pct', 'take_profit_pct'), ('stop_loss_pct', 'stop_loss_pct')):
            if field in data:
                raw = data[field]
                if raw in (None, ''):
                    setattr(holding, field, None)
                else:
                    try:
                        pct = float(raw)
                    except (TypeError, ValueError):
                        return jsonify({'error': f'{label} must be a number'}), 400
                    if pct <= 0:
                        return jsonify({'error': f'{label} must be greater than 0'}), 400
                    if field == 'stop_loss_pct' and pct >= 100:
                        return jsonify({'error': 'stop_loss_pct must be less than 100'}), 400
                    setattr(holding, field, pct)

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
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
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
            account_id=holding.account_id,
            symbol=holding.symbol,
            asset_type=holding.asset_type or 'stock',
            transaction_type=transaction_type,
            quantity=(float(quantity) if quantity else float(holding.quantity)),
            price=price,
            transaction_date=datetime.utcnow()
        )
        db.session.add(transaction)
        
        # Update or delete holding
        holding_quantity = float(holding.quantity)
        sell_quantity = float(quantity) if quantity else holding_quantity
        if sell_all:
            sell_quantity = holding_quantity
        sell_quantity = min(sell_quantity, holding_quantity)

        # A sale returns cash to the account it was sold from: proceeds =
        # shares sold x execution price. Credit the account's cash balance so
        # available cash reflects the sale (buy-side cash handling lives elsewhere).
        proceeds = round(sell_quantity * float(price or 0), 2)
        new_cash = None
        if transaction_type == 'sell' and holding.account_id:
            _acct = PortfolioAccount.query.filter_by(id=holding.account_id, user_id=user_id).first()
            if _acct:
                _acct.cash_balance = round(float(_acct.cash_balance or 0) + proceeds, 2)
                new_cash = float(_acct.cash_balance)

        if sell_all or sell_quantity >= holding_quantity:
            # Selling entire position
            db.session.delete(holding)
            logger.info(f"Sold all of {holding.symbol} at ${price} for user {user_id}")
        elif quantity:
            # Partial sell
            holding.quantity = holding_quantity - sell_quantity
            logger.info(f"Sold {sell_quantity} shares of {holding.symbol} at ${price} for user {user_id}")
        
        db.session.commit()
        
        _resp = {'message': 'Transaction recorded successfully', 'proceeds': proceeds}
        if new_cash is not None:
            _resp['cash_balance'] = new_cash
        return jsonify(_resp), 200
    
    except Exception as e:
        logger.error(f"Error recording transaction: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/price-history', methods=['GET'])
@require_api_auth
def get_price_history():
    """Price history for one symbol over a selectable range (holding detail chart).

    Reuses the resilient FinancialDataFetcher (yfinance + DefeatBeta fallback).
    """
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        symbol = (request.args.get('symbol') or '').upper().strip()
        rng = (request.args.get('range') or '1w').lower()
        if not symbol:
            return jsonify({'empty': True, 'message': 'symbol required'}), 200

        # range -> (yfinance period, interval)
        RANGES = {
            '1d': ('1d', '5m'),
            '1w': ('5d', '30m'),
            '1m': ('1mo', '1d'),
            '3m': ('3mo', '1d'),
            '1y': ('1y', '1d'),
        }
        period, interval = RANGES.get(rng, RANGES['1w'])

        df = data_fetcher.fetch_stock_data(symbol, period=period, interval=interval)
        if df is None or getattr(df, 'empty', True):
            return jsonify({'symbol': symbol, 'range': rng, 'points': [], 'empty': True,
                            'message': f'No price data for {symbol} ({rng})'}), 200

        col = 'Close' if 'Close' in df.columns else ('close' if 'close' in df.columns else None)
        if col is None:
            return jsonify({'symbol': symbol, 'range': rng, 'points': [], 'empty': True,
                            'message': 'No close prices'}), 200

        series = df[col].dropna()
        points = []
        for ts, val in series.items():
            try:
                t = ts.isoformat()
            except Exception:
                t = str(ts)
            points.append({'t': t, 'c': round(float(val), 4)})

        # Downsample to keep the payload light (~300 points max)
        if len(points) > 300:
            step = (len(points) // 300) + 1
            last = points[-1]
            points = points[::step]
            if points[-1] is not last:
                points.append(last)

        return jsonify({'symbol': symbol, 'range': rng, 'points': points}), 200
    except Exception as e:
        logger.error(f"Error in price-history: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'Price history unavailable'}), 200

@app.route('/api/portfolio/rebalance', methods=['GET'])
@require_api_auth
def get_rebalancing_suggestions():
    """Get portfolio rebalancing suggestions"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        suggestions = portfolio_analyzer.get_rebalancing_suggestions(user_id)
        
        return jsonify({'suggestions': suggestions})
    
    except Exception as e:
        logger.error(f"Error generating rebalancing suggestions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/history', methods=['GET'])
@require_api_auth
def get_portfolio_history():
    """Get portfolio value history for charting"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        period = request.args.get('period', '1m')
        
        period_map = {
            '1d': 1, '1w': 7, '1m': 30, '6m': 180,
            '1y': 365, '3y': 1095, '5y': 1825, 'max': 9999
        }
        days = period_map.get(period, 30)
        
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(days=days)
        
        # Always build history from real price data
        history = _build_portfolio_history(user_id, days)
        
        # Fall back to snapshots only if price history is empty
        if not history:
            snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.timestamp >= since
            ).order_by(PortfolioSnapshot.timestamp.asc()).all()
            if snapshots:
                history = [s.to_dict() for s in snapshots]
        
        # Save a snapshot while we're here
        try:
            portfolio_analyzer.save_portfolio_snapshot(user_id)
        except Exception:
            pass
        
        return jsonify({'history': history, 'period': period})
    
    except Exception as e:
        logger.error(f"Error fetching portfolio history: {e}")
        return jsonify({'error': str(e)}), 500

def _build_portfolio_history(user_id, days):
    """Portfolio value history reconstructed from the transaction ledger.

    Walks actual position state over time (buys add, sells remove — avg-cost
    basis), valued with historical prices, so every period is accurate rather
    than applying today's positions to old prices. Holdings with no recorded
    transaction (e.g. a directly-added crypto position) get a synthesized
    opening lot at their purchase_date.
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    import yfinance as yf
    import pandas as pd
    from data_fetcher import normalize_crypto_symbol

    def _yf(sym, atype):
        sym = (sym or '').upper()
        return sym if '-' in sym else normalize_crypto_symbol(sym, atype)

    holdings = Portfolio.query.filter_by(user_id=user_id).all()
    if not holdings:
        return []

    end = datetime.now()
    period_start = (end - timedelta(days=days)).date()

    # Position-change events from the ledger: (date, yf_symbol, qty_delta, price)
    txns = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.transaction_date.asc()).all()
    events = []
    seen = set()
    for t in txns:
        if (t.asset_type or 'stock') == 'option':
            continue
        d = t.transaction_date.date() if isinstance(t.transaction_date, datetime) else t.transaction_date
        if not d:
            continue
        ysym = _yf(t.symbol, t.asset_type or 'stock')
        q = float(t.quantity or 0)
        events.append((d, ysym, q if t.transaction_type == 'buy' else -q, float(t.price or 0)))
        seen.add((t.symbol or '').upper())

    # Holdings without any transaction → synthesize an opening lot at purchase_date
    for h in holdings:
        if (h.symbol or '').upper() not in seen:
            d = h.purchase_date.date() if isinstance(h.purchase_date, datetime) else (h.purchase_date or end.date())
            events.append((d, _yf(h.symbol, h.asset_type or 'stock'), float(h.quantity or 0), float(h.average_cost or 0)))

    if not events:
        return []
    events.sort(key=lambda e: e[0])
    earliest = events[0][0]
    start = earliest if days >= 9999 else max(period_start, earliest)
    if start > end.date():
        start = earliest

    # Historical prices for every symbol that ever appeared
    price_data = {}
    for ysym in sorted({e[1] for e in events}):
        try:
            hist = yf.Ticker(ysym).history(start=start, end=end + timedelta(days=1))
            if not hist.empty:
                s = hist['Close']
                s.index = [d.date() if hasattr(d, 'date') else d for d in s.index]
                price_data[ysym] = s[~pd.Index(s.index).duplicated(keep='last')]
        except Exception:
            continue
    if not price_data:
        return []

    all_dates = sorted({d for s in price_data.values() for d in s.index if d >= start})
    if not all_dates:
        return []
    date_index = pd.Index(all_dates)
    price_re = {ys: pd.Series(s.values, index=pd.Index(s.index)).sort_index().reindex(date_index, method='ffill')
                for ys, s in price_data.items()}

    # Walk dates, applying events, tracking (qty, cost) per symbol with avg cost
    state = defaultdict(lambda: [0.0, 0.0])
    ei, n = 0, len(events)
    history = []
    for i, date in enumerate(all_dates):
        while ei < n and events[ei][0] <= date:
            _, ysym, dq, px = events[ei]
            st = state[ysym]
            if dq >= 0:
                st[0] += dq
                st[1] += dq * px
            else:
                if st[0] > 0:
                    st[1] -= (min(-dq, st[0]) / st[0]) * st[1]
                st[0] += dq
                if st[0] < 1e-9:
                    st[0], st[1] = 0.0, 0.0
            ei += 1
        total_value = total_cost = 0.0
        for ysym, st in state.items():
            if st[0] <= 0:
                continue
            pr = price_re.get(ysym)
            if pr is None:
                continue
            price = pr.iloc[i]
            if price is not None and not pd.isna(price):
                total_value += st[0] * float(price)
                total_cost += st[1]
        if total_value > 0:
            pnl = total_value - total_cost
            history.append({
                'timestamp': datetime.combine(date, datetime.min.time()).isoformat(),
                'total_value': round(total_value, 2),
                'total_cost_basis': round(total_cost, 2),
                'total_pnl': round(pnl, 2),
                'total_pnl_pct': round((pnl / total_cost * 100) if total_cost > 0 else 0, 4),
            })
    return history

@app.route('/api/alerts', methods=['GET'])
@require_api_auth
def get_alerts():
    """Get all active alerts for user"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
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
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
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
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
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
# LIMIT-PRICE ALERT (convenience)
# ===========================

@app.route('/api/alerts/limit', methods=['POST'])
@require_api_auth
def create_limit_alert():
    """Create a buy/sell limit-price alert.

    Body: {symbol, price, side}. side='buy' fires when price drops to/below the
    limit; side='sell' fires when price rises to/above it. Thin wrapper over the
    smart-alerts price engine so 'notify me at my limit' is one call.
    """
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Phase 4 not enabled'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json() or {}
        symbol = (data.get('symbol') or '').upper().strip()
        side = (data.get('side') or 'buy').lower().strip()
        try:
            price = float(data.get('price'))
        except (TypeError, ValueError):
            return jsonify({'error': 'A numeric price is required'}), 400

        if not symbol:
            return jsonify({'error': 'symbol is required'}), 400
        if side not in ('buy', 'sell'):
            return jsonify({'error': "side must be 'buy' or 'sell'"}), 400

        # buy limit -> alert when price falls to/below; sell limit -> rises to/above
        direction = 'below' if side == 'buy' else 'above'
        alert = smart_alerts.create_price_alert(
            user_id=user_id,
            symbol=symbol,
            target_price=price,
            direction=direction
        )

        if alert:
            return jsonify(alert.to_dict()), 201
        return jsonify({'error': 'Failed to create limit alert'}), 500

    except Exception as e:
        logger.error(f"Error creating limit alert: {e}")
        return jsonify({'error': str(e)}), 500


# ===========================
# NOTIFICATION FEED (durable history of fired alerts)
# ===========================

@app.route('/api/notifications', methods=['GET'])
@require_api_auth
def list_notifications():
    """List the user's notifications (fired alerts + system messages).

    Query params: unread=1 to only return unread; limit (default 50, max 200).
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        q = Notification.query.filter_by(user_id=user_id)
        if request.args.get('unread') in ('1', 'true', 'yes'):
            q = q.filter_by(read=False)

        try:
            limit = min(int(request.args.get('limit', 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        items = q.order_by(Notification.created_at.desc()).limit(limit).all()
        unread_count = Notification.query.filter_by(user_id=user_id, read=False).count()

        return jsonify({
            'notifications': [n.to_dict() for n in items],
            'unread_count': unread_count,
            'count': len(items)
        })
    except Exception as e:
        logger.error(f"Error listing notifications: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/unread-count', methods=['GET'])
@require_api_auth
def notifications_unread_count():
    """Lightweight badge count of unread notifications."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        count = Notification.query.filter_by(user_id=user_id, read=False).count()
        return jsonify({'unread_count': count})
    except Exception as e:
        logger.error(f"Error counting notifications: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/<int:notification_id>/read', methods=['PUT', 'POST'])
@require_api_auth
def mark_notification_read(notification_id):
    """Mark a single notification as read."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        note = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if not note:
            return jsonify({'error': 'Notification not found'}), 404
        note.read = True
        db.session.commit()
        return jsonify({'message': 'marked read'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking notification read: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/read-all', methods=['PUT', 'POST'])
@require_api_auth
def mark_all_notifications_read():
    """Mark every unread notification for the user as read."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        updated = Notification.query.filter_by(user_id=user_id, read=False).update({'read': True})
        db.session.commit()
        return jsonify({'message': 'all marked read', 'updated': updated})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking all notifications read: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@require_api_auth
def delete_notification(notification_id):
    """Delete a notification from the feed."""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        note = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if not note:
            return jsonify({'error': 'Notification not found'}), 404
        db.session.delete(note)
        db.session.commit()
        return jsonify({'message': 'deleted'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting notification: {e}")
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

@app.route('/api/insider-clusters', methods=['GET'])
@require_api_auth
def get_insider_clusters():
    """Recent insider (SEC Form 4) cluster buys — multiple insiders buying the same
    stock in a tight window. Powers the copy-trading 'Pro Traders' tab."""
    try:
        from insider_trades import get_insider_tracker
        limit = request.args.get('limit', 30, type=int)
        clusters = get_insider_tracker().get_cluster_buys(limit=limit)
        return jsonify({'clusters': clusters, 'count': len(clusters)}), 200
    except Exception as e:
        logger.error(f"Error fetching insider clusters: {e}")
        return jsonify({'clusters': [], 'count': 0, 'error': str(e)}), 200


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
        user_id = _get_current_user_id()
        if not user_id:
            logger.warning("Correlation matrix requested without authentication")
            return jsonify({'error': 'Authentication required'}), 401
        
        period = request.args.get('period', '3mo')
        account_id = request.args.get('account_id', type=int)
        logger.debug(f"Fetching correlation matrix for user {user_id}, period={period}, account_id={account_id}")
        result = correlation_analyzer.get_portfolio_correlation_matrix(user_id, period, account_id=account_id)
        
        if 'error' in result:
            logger.info(f"Correlation matrix error for user {user_id}: {result['error']}")
            result.setdefault('empty', True)
            result.setdefault('message', result['error'])
            return jsonify(result), 200
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching correlation matrix: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'Correlation analysis temporarily unavailable'}), 200

@app.route('/api/correlation/diversification', methods=['GET'])
@require_api_auth
def get_diversification():
    """Get portfolio diversification metrics"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Diversification analysis not available'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            logger.warning("Diversification metrics requested without authentication")
            return jsonify({'error': 'Authentication required'}), 401
        
        account_id = request.args.get('account_id', type=int)
        logger.debug(f"Fetching diversification metrics for user {user_id}, account_id={account_id}")
        result = correlation_analyzer.get_diversification_metrics(user_id, account_id=account_id)
        
        if 'error' in result:
            logger.info(f"Diversification metrics error for user {user_id}: {result['error']}")
            result.setdefault('empty', True)
            result.setdefault('message', result['error'])
            return jsonify(result), 200
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching diversification metrics: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'Diversification analysis temporarily unavailable'}), 200

@app.route('/api/correlation/ai-read', methods=['GET'])
@require_api_auth
@require_ai_permission
def get_correlation_ai_read():
    """Plain-English AI read of the diversification metrics.

    Claude (Anthropic API) is the primary engine; falls back to the local LLM
    (Ollama/RKLLM) when Claude is unavailable (no key / package / API error).
    """
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Not available'}), 503
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        account_id = request.args.get('account_id', type=int)
        metrics = correlation_analyzer.get_diversification_metrics(user_id, account_id=account_id)
        if 'error' in metrics:
            return jsonify({'empty': True, 'message': metrics.get('message', metrics['error'])}), 200

        label = 'all accounts'
        if account_id:
            acc = PortfolioAccount.query.filter_by(id=account_id, user_id=user_id).first()
            if acc:
                label = acc.name

        system = claude_analyzer.SYSTEM_PROMPT
        facts = claude_analyzer.format_facts(metrics, label)

        # 1) Claude (primary)
        read = claude_analyzer.read(system, facts)
        engine = 'claude' if read else None

        # 2) Local LLM (fallback)
        if not read:
            try:
                local_prompt = f"{system}\n\n{facts}\nWrite the 3-4 sentence read now."
                read = llm_analyzer._call_llm([{'role': 'user', 'content': local_prompt}], timeout=60)
                # Guard: never surface a raw/empty local-LLM envelope as if it were the read
                if read and (read.lstrip().startswith("{'") or "'choices'" in read or 'rkllm_chat' in read):
                    read = None
                engine = 'local' if read else None
            except Exception as e:
                logger.warning(f"Local LLM fallback failed for ai-read: {e}")

        if not read:
            return jsonify({'empty': True, 'message': 'AI read unavailable right now.'}), 200
        return jsonify({'read': read.strip(), 'engine': engine, 'account_label': label}), 200

    except Exception as e:
        logger.error(f"Error in correlation ai-read: {e}", exc_info=True)
        return jsonify({'error': str(e), 'empty': True, 'message': 'AI read temporarily unavailable'}), 200

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
        user_id = _get_current_user_id()
        if not user_id:
            logger.warning("Journal history requested without authentication")
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        logger.debug(f"Fetching trade history for user {user_id}, days={days}")
        result = trade_journal.get_trade_history(user_id, days)
        
        if 'error' in result:
            logger.info(f"Trade history error for user {user_id}: {result['error']}")
            # Return 200 for empty trades (not an error condition)
            if 'No trades found' in result['error'] or 'No transaction' in result['error']:
                return jsonify({
                    'error': result['error'],
                    'empty': True,
                    'message': 'Your trade history will appear here once you record trades',
                    'trades': []
                }), 200
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error fetching trade history: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/performance', methods=['GET'])
@require_api_auth
def get_journal_performance():
    """Get trading performance analysis"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            logger.warning("Journal performance requested without authentication")
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        logger.debug(f"Fetching journal performance for user {user_id}, days={days}")
        result = trade_journal.analyze_performance(user_id, days)
        
        if 'error' in result:
            logger.info(f"Journal performance error for user {user_id}: {result['error']}")
            # Return 200 for empty trades (not an error condition)
            if 'No trades found' in result['error'] or 'No transaction' in result['error']:
                return jsonify({
                    'error': result['error'],
                    'empty': True,
                    'message': 'Record your trades to see performance analytics'
                }), 200
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error analyzing performance: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/insights', methods=['GET'])
@require_api_auth
def get_journal_insights():
    """Get AI-powered trading insights"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        user_id = _get_current_user_id()
        if not user_id:
            logger.warning("Journal insights requested without authentication")
            return jsonify({'error': 'Authentication required'}), 401
        
        days = int(request.args.get('days', 90))
        logger.debug(f"Generating AI insights for user {user_id}, days={days}")
        result = trade_journal.get_ai_insights(user_id, days)
        
        if 'error' in result:
            logger.info(f"Journal insights error for user {user_id}: {result['error']}")
            # Return 200 for empty trades (not an error condition)
            if 'No trades found' in result['error'] or 'No transaction' in result['error']:
                return jsonify({
                    'error': result['error'],
                    'empty': True,
                    'message': 'Record your trades to get AI-powered insights'
                }), 200
            return jsonify(result), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error generating AI insights: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/journal/note', methods=['POST'])
@require_api_auth
def save_trade_note():
    """Add or update note for a transaction"""
    if not PHASE4_ENABLED:
        return jsonify({'error': 'Trade journal not available'}), 503
    
    try:
        user_id = _get_current_user_id()
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


@app.route('/api/export', methods=['GET'])
@require_api_auth
def export_user_data():
    """Export current user's financial data as JSON or CSV."""
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Database not available'}), 503

    fmt = request.args.get('format', 'json').lower()
    if fmt not in ('json', 'csv'):
        return jsonify({'error': 'Invalid format. Use json or csv'}), 400

    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    from flask import make_response
    import csv
    import io as _io

    watchlist = [w.to_dict() for w in Watchlist.query.filter_by(user_id=user_id).all()]
    portfolio = [p.to_dict() for p in Portfolio.query.filter_by(user_id=user_id).all()]
    transactions = [t.to_dict() for t in Transaction.query.filter_by(user_id=user_id).all()]
    options = [o.to_dict() for o in OptionsPosition.query.filter_by(user_id=user_id).all()]
    alerts = [a.to_dict() for a in Alert.query.filter_by(user_id=user_id).all()]
    dividends = [d.to_dict() for d in Dividend.query.filter_by(user_id=user_id).all()]

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    if fmt == 'json':
        payload = {
            'exported_at': datetime.utcnow().isoformat(),
            'watchlist': watchlist,
            'portfolio': portfolio,
            'transactions': transactions,
            'options_positions': options,
            'alerts': alerts,
            'dividends': dividends,
        }
        resp = make_response(json.dumps(payload, indent=2))
        resp.headers['Content-Type'] = 'application/json'
        resp.headers['Content-Disposition'] = f'attachment; filename=tradertools_export_{timestamp}.json'
        return resp

    # CSV: one sheet per section, separated by blank lines
    buf = _io.StringIO()
    writer = csv.writer(buf)

    sections = [
        ('Watchlist', watchlist),
        ('Portfolio', portfolio),
        ('Transactions', transactions),
        ('Options Positions', options),
        ('Alerts', alerts),
        ('Dividends', dividends),
    ]

    for name, rows in sections:
        writer.writerow([f'=== {name} ==='])
        if rows:
            writer.writerow(list(rows[0].keys()))
            for row in rows:
                writer.writerow(list(row.values()))
        else:
            writer.writerow(['No data'])
        writer.writerow([])

    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = f'attachment; filename=tradertools_export_{timestamp}.csv'
    return resp


@app.route('/api/import', methods=['POST'])
@require_api_auth
def import_user_data():
    """Restore data from an /api/export JSON dump for the current user.

    De-duplicates every section by natural keys, so re-importing the same file
    never creates duplicate records (existing rows are skipped, never clobbered).
    Returns per-section imported/skipped counts.
    """
    if not PHASE2_ENABLED:
        return jsonify({'error': 'Database not available'}), 503
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected a JSON export body'}), 400

    from datetime import datetime as _dt

    def _pdt(v):
        if not v:
            return None
        try:
            return _dt.fromisoformat(str(v).replace('Z', '+00:00'))
        except Exception:
            return None

    def _pdate(v):
        if not v:
            return None
        try:
            return _dt.fromisoformat(str(v)[:10]).date()
        except Exception:
            return None

    acct_by_name = {a.name: a.id for a in PortfolioAccount.query.filter_by(user_id=user_id).all()}
    def _acct(row):
        return acct_by_name.get(row.get('account_name')) if row.get('account_name') else None

    result = {}
    try:
        # Watchlist — unique (user_id, symbol)
        imp = skip = 0
        seen = {w.symbol.upper() for w in Watchlist.query.filter_by(user_id=user_id).all()}
        for r in (data.get('watchlist') or []):
            sym = (r.get('symbol') or '').upper()
            if not sym or sym in seen:
                skip += 1; continue
            db.session.add(Watchlist(user_id=user_id, symbol=sym, notes=r.get('notes')))
            seen.add(sym); imp += 1
        result['watchlist'] = {'imported': imp, 'skipped': skip}

        # Portfolio — dedupe (symbol, asset_type)
        imp = skip = 0
        seen = {(p.symbol.upper(), p.asset_type) for p in Portfolio.query.filter_by(user_id=user_id).all()}
        for r in (data.get('portfolio') or []):
            sym = (r.get('symbol') or '').upper(); at = r.get('asset_type') or 'stock'
            if not sym or (sym, at) in seen:
                skip += 1; continue
            db.session.add(Portfolio(
                user_id=user_id, symbol=sym, asset_type=at,
                quantity=r.get('quantity') or 0, average_cost=r.get('average_cost') or 0,
                current_price=r.get('current_price'), purchase_date=_pdt(r.get('purchase_date')) or _dt.utcnow(),
                account_id=_acct(r),
                intent=r.get('intent') if r.get('intent') in ('core', 'lottery', 'signal') else None,
                ipo_lock_until=_pdate(r.get('ipo_lock_until'))))
            seen.add((sym, at)); imp += 1
        result['portfolio'] = {'imported': imp, 'skipped': skip}

        # Transactions — dedupe (symbol, type, qty, price, date)
        imp = skip = 0
        seen = {(t.symbol.upper(), t.transaction_type, float(t.quantity), float(t.price),
                 t.transaction_date.isoformat() if t.transaction_date else None)
                for t in Transaction.query.filter_by(user_id=user_id).all()}
        for r in (data.get('transactions') or []):
            sym = (r.get('symbol') or '').upper(); d = _pdt(r.get('transaction_date'))
            key = (sym, r.get('transaction_type'), float(r.get('quantity') or 0),
                   float(r.get('price') or 0), d.isoformat() if d else None)
            if not sym or key in seen:
                skip += 1; continue
            db.session.add(Transaction(
                user_id=user_id, symbol=sym, asset_type=r.get('asset_type') or 'stock',
                transaction_type=r.get('transaction_type'), quantity=r.get('quantity') or 0,
                price=r.get('price') or 0, commission=r.get('commission') or 0,
                transaction_date=d or _dt.utcnow(), notes=r.get('notes'), account_id=_acct(r)))
            seen.add(key); imp += 1
        result['transactions'] = {'imported': imp, 'skipped': skip}

        # Options — dedupe (underlying, type, strike, expiration)
        imp = skip = 0
        seen = {(o.underlying_symbol.upper(), o.option_type, float(o.strike_price),
                 o.expiration_date.isoformat() if o.expiration_date else None)
                for o in OptionsPosition.query.filter_by(user_id=user_id).all()}
        for r in (data.get('options_positions') or []):
            us = (r.get('underlying_symbol') or '').upper(); ed = _pdate(r.get('expiration_date'))
            key = (us, r.get('option_type'), float(r.get('strike_price') or 0), ed.isoformat() if ed else None)
            if not us or key in seen:
                skip += 1; continue
            db.session.add(OptionsPosition(
                user_id=user_id, underlying_symbol=us, option_type=r.get('option_type'),
                strike_price=r.get('strike_price') or 0, expiration_date=ed,
                quantity=r.get('quantity') or 0, premium_paid=r.get('premium_paid') or 0,
                current_premium=r.get('current_premium'), status=r.get('status') or 'open'))
            seen.add(key); imp += 1
        result['options_positions'] = {'imported': imp, 'skipped': skip}

        # Alerts — dedupe (symbol, alert_type, condition, target_price)
        imp = skip = 0
        seen = {(a.symbol.upper(), a.alert_type, a.condition, float(a.target_price) if a.target_price else None)
                for a in Alert.query.filter_by(user_id=user_id).all()}
        for r in (data.get('alerts') or []):
            sym = (r.get('symbol') or '').upper(); tp = r.get('target_price') or r.get('targetPrice')
            key = (sym, r.get('alert_type') or r.get('type'), r.get('condition'), float(tp) if tp else None)
            if not sym or key in seen:
                skip += 1; continue
            db.session.add(Alert(
                user_id=user_id, symbol=sym, alert_type=r.get('alert_type') or r.get('type') or 'price',
                condition=r.get('condition'), target_price=tp, priority=r.get('priority') or 'medium',
                message=r.get('message'), enabled=r.get('enabled', True)))
            seen.add(key); imp += 1
        result['alerts'] = {'imported': imp, 'skipped': skip}

        # Dividends — dedupe (symbol, ex_date, total_amount)
        imp = skip = 0
        seen = {(d.symbol.upper(), d.ex_date.isoformat() if d.ex_date else None, float(d.total_amount))
                for d in Dividend.query.filter_by(user_id=user_id).all()}
        for r in (data.get('dividends') or []):
            sym = (r.get('symbol') or '').upper(); ex = _pdate(r.get('ex_date'))
            key = (sym, ex.isoformat() if ex else None, float(r.get('total_amount') or 0))
            if not sym or key in seen:
                skip += 1; continue
            db.session.add(Dividend(
                user_id=user_id, symbol=sym, amount_per_share=r.get('amount_per_share') or 0,
                shares=r.get('shares') or 0, total_amount=r.get('total_amount') or 0,
                ex_date=ex, pay_date=_pdate(r.get('pay_date')),
                reinvested=r.get('reinvested', False),
                income_type=(r.get('income_type') or 'dividend'),
                qualified=r.get('qualified', (r.get('income_type') or 'dividend') == 'dividend'),
                notes=r.get('notes'), account_id=_acct(r)))
            seen.add(key); imp += 1
        result['dividends'] = {'imported': imp, 'skipped': skip}

        db.session.commit()
        total_imp = sum(v['imported'] for v in result.values())
        total_skip = sum(v['skipped'] for v in result.values())
        return jsonify({
            'message': f'Restore complete: {total_imp} record(s) imported, {total_skip} duplicate(s) skipped',
            'sections': result
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Import failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.errorhandler(500)
def handle_500(e):
    """Clear stale sessions and redirect on internal server errors"""
    try:
        session.clear()
        if db:
            db.session.rollback()
    except Exception:
        pass
    return redirect(url_for('login') if PHASE2_ENABLED else url_for('index'))


@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """Catch-all for unhandled exceptions to avoid raw 500 pages"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    try:
        session.clear()
        if db:
            db.session.rollback()
    except Exception:
        pass
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    return redirect(url_for('login') if PHASE2_ENABLED else url_for('index'))


# Seed built-in permission groups at import time (runs under gunicorn too, not just
# __main__). Idempotent — skips if any group already exists.
if PHASE2_ENABLED:
    try:
        with app.app_context():
            _seed_default_groups()
    except Exception as _seed_err:
        logger.warning(f"Default-group seed skipped: {_seed_err}")


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
