-- Financial Analysis System - Database Schema
-- Phase 2: PostgreSQL Database Design

-- Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    picture_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    preferences JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_users_google_id ON users(google_id);
CREATE INDEX idx_users_email ON users(email);

-- Watchlist Table
CREATE TABLE watchlist (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE(user_id, symbol)
);

CREATE INDEX idx_watchlist_user ON watchlist(user_id);
CREATE INDEX idx_watchlist_symbol ON watchlist(symbol);

-- Price Alerts Table
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(10) CHECK (alert_type IN ('above', 'below')),
    target_price DECIMAL(10, 2) NOT NULL,
    current_price DECIMAL(10, 2),
    triggered BOOLEAN DEFAULT FALSE,
    triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    enabled BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_alerts_user ON alerts(user_id);
CREATE INDEX idx_alerts_symbol ON alerts(symbol);
CREATE INDEX idx_alerts_active ON alerts(user_id, enabled, triggered);

-- Portfolio Holdings Table
CREATE TABLE portfolio (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    asset_type VARCHAR(20) CHECK (asset_type IN ('stock', 'option', 'etf')),
    quantity DECIMAL(15, 6) NOT NULL,
    average_cost DECIMAL(10, 4) NOT NULL,
    current_price DECIMAL(10, 4),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol, asset_type)
);

CREATE INDEX idx_portfolio_user ON portfolio(user_id);
CREATE INDEX idx_portfolio_symbol ON portfolio(symbol);

-- Transactions Table (for detailed cost basis tracking)
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    asset_type VARCHAR(20) CHECK (asset_type IN ('stock', 'option', 'etf')),
    transaction_type VARCHAR(10) CHECK (transaction_type IN ('buy', 'sell')),
    quantity DECIMAL(15, 6) NOT NULL,
    price DECIMAL(10, 4) NOT NULL,
    commission DECIMAL(10, 2) DEFAULT 0,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX idx_transactions_user ON transactions(user_id);
CREATE INDEX idx_transactions_symbol ON transactions(symbol);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);

-- Options Holdings Table
CREATE TABLE options_positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    underlying_symbol VARCHAR(10) NOT NULL,
    option_type VARCHAR(10) CHECK (option_type IN ('call', 'put')),
    strike_price DECIMAL(10, 2) NOT NULL,
    expiration_date DATE NOT NULL,
    quantity INTEGER NOT NULL,
    premium_paid DECIMAL(10, 4) NOT NULL,
    current_premium DECIMAL(10, 4),
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closed', 'exercised', 'expired'))
);

CREATE INDEX idx_options_user ON options_positions(user_id);
CREATE INDEX idx_options_symbol ON options_positions(underlying_symbol);
CREATE INDEX idx_options_expiration ON options_positions(expiration_date);

-- AI Analysis History Table
CREATE TABLE analysis_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    period VARCHAR(10) NOT NULL,
    chart_type VARCHAR(20) NOT NULL,
    analysis_text TEXT,
    chart_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analysis_user ON analysis_history(user_id);
CREATE INDEX idx_analysis_symbol ON analysis_history(symbol);
CREATE INDEX idx_analysis_date ON analysis_history(created_at);

-- ML Pattern Recognition Results Table
CREATE TABLE ml_patterns (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    pattern_type VARCHAR(50) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    prediction VARCHAR(20) CHECK (prediction IN ('bullish', 'bearish', 'neutral')),
    time_horizon VARCHAR(20),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pattern_data JSONB,
    price_at_detection DECIMAL(10, 4)
);

CREATE INDEX idx_patterns_symbol ON ml_patterns(symbol);
CREATE INDEX idx_patterns_type ON ml_patterns(pattern_type);
CREATE INDEX idx_patterns_date ON ml_patterns(detected_at);

-- ML Predictions Table (for tracking prediction accuracy)
CREATE TABLE ml_predictions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    prediction_type VARCHAR(50) NOT NULL,
    predicted_direction VARCHAR(20) CHECK (predicted_direction IN ('up', 'down', 'sideways')),
    predicted_price DECIMAL(10, 4),
    confidence DECIMAL(5, 4) NOT NULL,
    time_horizon VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    target_date TIMESTAMP,
    actual_price DECIMAL(10, 4),
    actual_direction VARCHAR(20),
    accuracy_score DECIMAL(5, 4),
    model_version VARCHAR(50)
);

CREATE INDEX idx_predictions_symbol ON ml_predictions(symbol);
CREATE INDEX idx_predictions_date ON ml_predictions(created_at);
CREATE INDEX idx_predictions_target ON ml_predictions(target_date);

-- System Monitoring Table (for real-time alerts and monitoring)
CREATE TABLE monitoring_log (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    check_type VARCHAR(50) NOT NULL,
    result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_monitoring_symbol ON monitoring_log(symbol);
CREATE INDEX idx_monitoring_date ON monitoring_log(created_at);

-- User Sessions Table (for authentication)
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_expiry ON user_sessions(expires_at);
