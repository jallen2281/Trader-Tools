# AI-Powered Financial Trading Analysis Platform

A comprehensive, production-ready trading intelligence platform featuring real-time market analysis, portfolio management, ML-based pattern detection, sentiment analysis, and automated alerts.

## Features

### Core Capabilities
- **📊 Real-Time Market Analysis**: Live stock quotes, charts, and technical indicators
- **🤖 AI-Powered Insights**: Local LLM integration (Ollama) for intelligent chart analysis
- **📈 Pattern Recognition**: Automated detection of chart patterns (Head & Shoulders, Double Tops/Bottoms, etc.)
- **🧠 ML Pattern Detection**: Machine learning-based prediction of future patterns
- **💹 Portfolio Management**: Track holdings, transactions, and performance metrics
- **📰 News Integration**: Real-time financial news with sentiment analysis
- **⚡ Volatile Stocks Scanner**: Track top movers, volume leaders, and high-momentum stocks (174+ symbols)
- **🎯 Smart Alerts**: Customizable price, volume, and technical indicator alerts
- **👥 Politician Trade Tracking**: Monitor and copy trades from congressional filings
- **📊 Options Analysis**: Advanced options Greeks and strategy analysis  
- **⏰ Trading Time Analyzer**: Identify optimal trading hours based on performance
- **🔗 Correlation Analysis**: Find correlated assets for diversification
- **📝 Trade Journal**: Document and analyze your trading decisions
- **🗓️ Market Calendar**: Track earnings, dividends, and economic events

### Technical Features
- **Cryptocurrency Support**: Monitor 24 major cryptos alongside stocks
- **Custom Watchlists**: Create and manage multiple watchlists
- **Session Persistence**: SQLite database with user authentication
- **Google OAuth**: Secure login with Google accounts
- **Responsive UI**: Modern, mobile-friendly interface
- **RESTful API**: Comprehensive API for programmatic access
- **Production Ready**: Docker + Kubernetes deployment configurations

## Architecture

### Backend Stack
- **Framework**: Flask 3.0
- **Database**: SQLAlchemy with SQLite (easily upgradable to PostgreSQL)
- **Data Sources**: yfinance, Alpha Vantage, News API, Quandl
- **ML/AI**: scikit-learn, statsmodels, Ollama (local LLM)
- **Authentication**: Flask-Login, Authlib (Google OAuth)
- **Charting**: Plotly, mplfinance, matplotlib
- **Production Server**: Gunicorn with worker processes

### Frontend Stack
- **HTML5/CSS3**: Modern semantic markup
- **Vanilla JavaScript**: No framework dependencies
- **Responsive Design**: Mobile-first approach
- **Real-time Updates**: AJAX for live data

## Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/trading-platform.git
cd trading-platform

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.template .env
# Edit .env with your API keys and settings

# Initialize database
python -c "from db_config import init_database; from flask import Flask; app = Flask(__name__); init_database(app)"

# Run application
python app.py
```

Access at `http://localhost:5000`

### Docker

```bash
# Build image
docker build -t trading-platform .

# Run container
docker run -p 5000:5000 --env-file .env trading-platform
```

### Production Kubernetes Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive production deployment guide.

Quick Helm install:
```bash
helm install trading-platform ./helm/trading-platform \
  --set-string secrets.secretKey="your-secret" \
  --set-string secrets.googleClientId="your-client-id" \
  --set-string secrets.googleClientSecret="your-secret"
```

## Configuration

### Required Environment Variables

```bash
# Flask Configuration
SECRET_KEY=your-strong-random-secret-key
FLASK_ENV=production

# Google OAuth (Required for authentication)
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Database
DATABASE_URL=sqlite:///instance/financial_analysis.db

# Optional API Keys (enhance functionality)
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
NEWS_API_KEY=your-news-api-key
QUANDL_API_KEY=your-quandl-api-key

# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
```

### Getting API Keys

- **Google OAuth**: [Google Cloud Console](https://console.cloud.google.com/)
- **Alpha Vantage**: [alphavantage.co](https://www.alphavantage.co/support/#api-key)
- **News API**: [newsapi.org](https://newsapi.org/register)
- **Quandl**: [data.nasdaq.com](https://data.nasdaq.com/sign-up)
- **Ollama**: [ollama.ai](https://ollama.ai) - Free local LLM

## Project Structure

```
trading-platform/
├── app.py                         # Main Flask application
├── models.py                      # Database models
├── config.py                      # Configuration management
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container image definition
├── .dockerignore                  # Docker build exclusions
│
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secret.yaml.template
│   ├── pvc.yaml
│   ├── hpa.yaml
│   └── kustomization.yaml
│
├── helm/                         # Helm chart
│   └── trading-platform/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
├── static/                       # Frontend assets
│   ├── styles.css
│   ├── app.js
│   ├── portfolio.js
│   ├── volatile_stocks.js
│   ├── copytrading.js
│   └── ...
│
├── templates/                    # HTML templates
│   ├── dashboard.html
│   ├── portfolio.html
│   └── ...
│
├── Core Modules
│   ├── data_fetcher.py              # Market data retrieval
│   ├── chart_generator.py           # Chart creation
│   ├── pattern_recognizer.py        # Technical pattern detection
│   ├── llm_analyzer.py              # LLM integration
│   ├── ml_pattern_detector.py       # ML predictions
│   ├── sentiment_analyzer.py        # News sentiment
│   ├── options_analyzer.py          # Options Greeks
│   ├── volatility_monitor.py        # Volatile stocks scanner
│   ├── portfolio_analyzer.py        # Portfolio analytics
│   ├── smart_alerts.py              # Alert engine
│   ├── politician_trades.py         # Congressional trades
│   └── ... 17 total modules
│
└── Documentation
    ├── README.md
    ├── DEPLOYMENT.md
    └── database_schema.sql
```

## API Endpoints

### Market Data
- `POST /analyze` - Analyze a stock symbol
- `GET /api/market/volatile-stocks` - Top volatile stocks
- `GET /api/market/fastest-movers` - Biggest % movers
- `GET /api/market/volume-leaders` - Volume surge leaders
- `GET /api/market/momentum-stocks` - High momentum picks

### Portfolio Management  
- `GET /api/portfolio` - Get portfolio summary
- `POST /api/portfolio/transaction` - Add transaction
- `GET /api/portfolio/performance` - Performance metrics

### Alerts & Monitoring
- `GET /api/alerts` - List active alerts
- `POST /api/alerts` - Create new alert
- `GET /api/alerts/suggestions` - Get AI alert suggestions

### Other Features
- `GET /api/watchlist` - User watchlists
- `GET /api/politician-trades` - Recent politician trades
- `GET /api/correlation` - Asset correlation matrix
- `GET /api/journal` - Trade journal entries

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete API documentation.

## Production Deployment

### Prerequisites
- Docker 20.10+
- Kubernetes 1.24+
- Helm 3.8+ (recommended)
- Container registry access

### Quick Deploy with Helm

```bash
# 1. Build and push image
docker build -t your-registry/trading-platform:latest .
docker push your-registry/trading-platform:latest

# 2. Install with Helm
helm install trading-platform ./helm/trading-platform \
  --set image.repository=your-registry/trading-platform \
  --set-string secrets.secretKey="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --set-string secrets.googleClientId="your-client-id" \
  --set-string secrets.googleClientSecret="your-client-secret"

# 3. Get the URL
kubectl get ingress -n trading-platform
```

### Features in Production
- **High Availability**: 2-10 replicas with auto-scaling
- **Load Balancing**: Kubernetes Service with session affinity
- **Persistent Storage**: 10GB PVC for database
- **Health Checks**: Liveness and readiness probes
- **SSL/TLS**: Automatic certificates with cert-manager
- **Monitoring**: Prometheus metrics and Grafana dashboards
- **Rolling Updates**: Zero-downtime deployments
- **Resource Management**: CPU/memory requests and limits

See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive production deployment guide.

## Development

### Running Tests

```bash
pytest
pytest --cov=. --cov-report=html
```

### Code Style

```bash
black .
flake8 .
mypy app.py
```

### Local LLM Setup

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# PDatabase Schema

The platform uses SQLAlchemy ORM with the following models:

- **User**: User accounts and profiles
- **Watchlist**: Custom stock watchlists
- **Portfolio**: Portfolio holdings
- **Transaction**: Buy/sell transactions  
- **OptionsPosition**: Options contracts
- **Alert**: Price and technical alerts
- **MLPattern**: ML pattern predictions
- **MLPrediction**: Historical predictions
- **AnalysisHistory**: Chart analysis history

See [database_schema.sql](database_schema.sql) for complete schema
| BTC-USD | Bitcoin |

**💡 Tip:** Use shortcuts like **SPX**, **DJI**, or **NASDAQ** - they're automatically mapped to the correct Yahoo Finance symbols!

**📚 For more symbols:** See [SYMBOLS_GUIDE.md](SYMBOLS_GUIDE.md) for a complete list of stocks, indices, ETFs, and cryptocurrencies.

## 🔒 Privacy & Security

- **100% Local**: All AI processing happens on your machine
- **No Cloud Dependencies**: No data sent to external servers
- *Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Copyright © 2026 Your Company. All rights reserved.

## Support

- **Documentation**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Issues**: GitHub Issues
- **Email**: support@yourdomain.com

## Disclaimer

**This platform is for informational and educational purposes only. It is not financial advice. Always conduct your own research and consult with a qualified financial advisor before making investment decisions. Past performance does not guarantee future results. Trading involves risk of loss.**