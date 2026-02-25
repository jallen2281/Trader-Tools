"""
News & Events Fetcher
Feature #3: Real-time market news, earnings calendar, and sentiment analysis
"""

import yfinance as yf
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional
import requests
from config import Config

logger = logging.getLogger(__name__)

class NewsFetcher:
    """Fetch and analyze market news and events"""
    
    def __init__(self):
        """Initialize news fetcher"""
        self.config = Config()
        logger.info("✓ News Fetcher initialized")
    
    def get_market_news(self, limit: int = 20) -> List[Dict]:
        """
        Get general market news from major indices
        
        Args:
            limit: Maximum number of articles
            
        Returns:
            List of news articles with sentiment
        """
        try:
            news_items = []
            
            # Fetch news from major market indices
            symbols = ['^GSPC', '^DJI', '^IXIC']  # S&P 500, Dow, Nasdaq
            symbol_names = {
                '^GSPC': 'S&P 500',
                '^DJI': 'Dow Jones',
                '^IXIC': 'Nasdaq'
            }
            
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    ticker_news = ticker.news
                    
                    if ticker_news:
                        for article in ticker_news[:5]:  # Top 5 from each index
                            # Skip articles without valid title data
                            content = article.get('content', article)  # Support both old and new structure
                            title = content.get('title', '')
                            if not title or title.strip() == '':
                                continue
                            
                            news_item = self._parse_yfinance_article(article)
                            news_item['source_index'] = symbol_names.get(symbol, symbol)
                            news_items.append(news_item)
                
                except Exception as e:
                    logger.warning(f"Error fetching news for {symbol}: {e}")
                    continue
            
            # Remove duplicates by link
            seen_links = set()
            unique_news = []
            for item in news_items:
                if item['link'] not in seen_links:
                    seen_links.add(item['link'])
                    unique_news.append(item)
            
            # Sort by published date (newest first)
            unique_news.sort(key=lambda x: x['published'], reverse=True)
            
            # Analyze sentiment for each article
            for item in unique_news[:limit]:
                item['sentiment'] = self._analyze_headline_sentiment(item['title'])
            
            logger.info(f"Fetched {len(unique_news[:limit])} market news articles")
            return unique_news[:limit]
        
        except Exception as e:
            logger.error(f"Error fetching market news: {e}")
            return []
    
    def get_symbol_news(self, symbol: str, limit: int = 10) -> List[Dict]:
        """
        Get news for a specific symbol
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of articles
            
        Returns:
            List of news articles with sentiment
        """
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            if not news:
                return []
            
            articles = []
            for article in news[:limit]:
                try:
                    # Skip None articles
                    if not article:
                        continue
                    
                    # Skip articles without valid title data
                    content = article.get('content', article)  # Support both old and new structure
                    if not content:
                        continue
                    
                    title = content.get('title', '') if isinstance(content, dict) else ''
                    if not title or title.strip() == '':
                        continue
                    
                    news_item = self._parse_yfinance_article(article)
                    news_item['sentiment'] = self._analyze_headline_sentiment(news_item['title'])
                    news_item['symbol'] = symbol
                    articles.append(news_item)
                except Exception as e:
                    logger.warning(f"Error parsing article for {symbol}: {e}")
                    continue
            
            logger.info(f"Fetched {len(articles)} news articles for {symbol}")
            return articles
        
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []
    
    def get_earnings_calendar(self, days_ahead: int = 7) -> List[Dict]:
        """
        Get upcoming earnings calendar
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            List of earnings events
        """
        try:
            # Get major tech stocks and popular symbols for earnings
            symbols = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
                'SPY', 'QQQ', 'DIA', 'IWM',
                'JPM', 'BAC', 'WFC', 'GS',
                'XOM', 'CVX',
                'JNJ', 'PFE', 'UNH'
            ]
            
            earnings_events = []
            today = datetime.now()
            cutoff_date = today + timedelta(days=days_ahead)
            
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    
                    # Get earnings dates
                    earnings_dates = ticker.get_earnings_dates(limit=4)
                    
                    if earnings_dates is not None and not earnings_dates.empty:
                        for date_idx in earnings_dates.index:
                            earnings_date = date_idx.replace(tzinfo=None) if hasattr(date_idx, 'tzinfo') else date_idx
                            
                            # Check if earnings is in our date range
                            if today <= earnings_date <= cutoff_date:
                                # Get stock info for company name
                                info = ticker.info
                                company_name = info.get('longName', symbol)
                                
                                earnings_events.append({
                                    'symbol': symbol,
                                    'company': company_name,
                                    'date': earnings_date.strftime('%Y-%m-%d'),
                                    'datetime': earnings_date.isoformat(),
                                    'days_until': (earnings_date - today).days,
                                    'time': 'Before Market' if earnings_date.hour < 12 else 'After Market'
                                })
                
                except Exception as e:
                    logger.debug(f"No earnings data for {symbol}: {e}")
                    continue
            
            # Sort by date (soonest first)
            earnings_events.sort(key=lambda x: x['datetime'])
            
            logger.info(f"Found {len(earnings_events)} upcoming earnings events")
            return earnings_events
        
        except Exception as e:
            logger.error(f"Error fetching earnings calendar: {e}")
            return []
    
    def get_trending_tickers(self, limit: int = 10) -> List[Dict]:
        """
        Get trending tickers with news
        
        Args:
            limit: Maximum number of tickers
            
        Returns:
            List of trending tickers with news count
        """
        try:
            # Get most active stocks
            most_active = yf.download(
                tickers="SPY QQQ AAPL MSFT GOOGL AMZN TSLA NVDA META",
                period="1d",
                interval="1d",
                progress=False
            )
            
            trending = []
            symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'AMD']
            
            for symbol in symbols[:limit]:
                try:
                    ticker = yf.Ticker(symbol)
                    news_count = len(ticker.news) if ticker.news else 0
                    info = ticker.info
                    
                    trending.append({
                        'symbol': symbol,
                        'name': info.get('longName', symbol),
                        'price': info.get('currentPrice', 0),
                        'change': info.get('regularMarketChangePercent', 0),
                        'news_count': news_count,
                        'volume': info.get('volume', 0)
                    })
                
                except Exception as e:
                    logger.debug(f"Error fetching trending data for {symbol}: {e}")
                    continue
            
            # Sort by news count
            trending.sort(key=lambda x: x['news_count'], reverse=True)
            
            return trending[:limit]
        
        except Exception as e:
            logger.error(f"Error fetching trending tickers: {e}")
            return []
    
    def _parse_yfinance_article(self, article: Dict) -> Dict:
        """Parse yfinance news article format (supports both old and new structure)"""
        try:
            # Handle new nested structure: article['content']['title']
            content = article.get('content', article) if article else {}  # Fall back to article itself for old structure
            if not content:
                content = {}
            
            # Get timestamp from multiple possible locations
            timestamp = content.get('pubDate') or content.get('displayTime') or article.get('providerPublishTime', 0) if article else 0
            if isinstance(timestamp, str):
                # Parse ISO format timestamp
                try:
                    from dateutil import parser
                    dt = parser.parse(timestamp)
                    timestamp = int(dt.timestamp())
                except:
                    timestamp = 0
            
            # Get thumbnail URL
            thumbnail_url = ''
            thumbnail = content.get('thumbnail') or (article.get('thumbnail') if article else None)
            if thumbnail:
                if isinstance(thumbnail, dict):
                    resolutions = thumbnail.get('resolutions', [])
                    if resolutions and len(resolutions) > 0:
                        thumbnail_url = resolutions[0].get('url', '')
            
            # Get provider info
            provider = content.get('provider', {})
            publisher = provider.get('displayName', '') if isinstance(provider, dict) else (article.get('publisher', 'Unknown') if article else 'Unknown')
            
            # Get link from multiple possible locations
            link = ''
            if article:
                link = article.get('link', '')
            if not link and content:
                click_through = content.get('clickThroughUrl', {})
                if isinstance(click_through, dict):
                    link = click_through.get('url', '')
            
            return {
                'title': content.get('title', 'No title'),
                'publisher': publisher,
                'link': link,
                'published': datetime.fromtimestamp(timestamp).isoformat() if timestamp else datetime.now().isoformat(),
                'published_ago': self._time_ago(timestamp) if timestamp else 'Just now',
                'thumbnail': thumbnail_url,
                'type': content.get('contentType', 'article').lower() if content.get('contentType') else 'article'
            }
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            # Return a minimal valid article object
            return {
                'title': 'Error parsing article',
                'publisher': 'Unknown',
                'link': '',
                'published': datetime.now().isoformat(),
                'published_ago': 'Just now',
                'thumbnail': '',
                'type': 'article'
            }
    
    def _analyze_headline_sentiment(self, headline: str) -> Dict:
        """
        Analyze sentiment of headline using keyword matching
        
        Args:
            headline: News headline text
            
        Returns:
            Sentiment analysis dict
        """
        headline_lower = headline.lower()
        
        # Positive keywords
        positive_keywords = [
            'surge', 'soar', 'rally', 'gain', 'jump', 'rise', 'climb', 'beat',
            'record', 'high', 'breakthrough', 'success', 'growth', 'profit',
            'bullish', 'upgrade', 'positive', 'strong', 'outperform', 'boom'
        ]
        
        # Negative keywords
        negative_keywords = [
            'plunge', 'tumble', 'fall', 'drop', 'decline', 'loss', 'crash',
            'miss', 'low', 'concern', 'worry', 'risk', 'fail', 'weak',
            'bearish', 'downgrade', 'negative', 'warning', 'cut', 'layoff'
        ]
        
        positive_count = sum(1 for word in positive_keywords if word in headline_lower)
        negative_count = sum(1 for word in negative_keywords if word in headline_lower)
        
        # Determine sentiment
        if positive_count > negative_count:
            sentiment = 'positive'
            score = min(0.8, 0.5 + (positive_count * 0.1))
            icon = '📈'
            color = '#22c55e'
        elif negative_count > positive_count:
            sentiment = 'negative'
            score = max(-0.8, -0.5 - (negative_count * 0.1))
            icon = '📉'
            color = '#ef4444'
        else:
            sentiment = 'neutral'
            score = 0.0
            icon = '➡️'
            color = '#6b7280'
        
        return {
            'label': sentiment,
            'score': score,
            'icon': icon,
            'color': color
        }
    
    def _time_ago(self, timestamp: int) -> str:
        """Convert timestamp to human-readable time ago"""
        if not timestamp:
            return 'Unknown'
        
        now = datetime.now()
        article_time = datetime.fromtimestamp(timestamp)
        diff = now - article_time
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"
    
    def get_market_summary(self) -> Dict:
        """Get overall market summary with news sentiment"""
        try:
            # Get major indices
            indices = {
                '^GSPC': 'S&P 500',
                '^DJI': 'Dow Jones',
                '^IXIC': 'Nasdaq',
                '^VIX': 'VIX'
            }
            
            market_data = {}
            
            for symbol, name in indices.items():
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    market_data[symbol] = {
                        'name': name,
                        'price': info.get('regularMarketPrice', 0),
                        'change': info.get('regularMarketChange', 0),
                        'change_percent': info.get('regularMarketChangePercent', 0)
                    }
                except Exception as e:
                    logger.debug(f"Error fetching {symbol}: {e}")
            
            # Get news sentiment overview
            recent_news = self.get_market_news(limit=20)
            sentiment_counts = {
                'positive': sum(1 for n in recent_news if n.get('sentiment', {}).get('label') == 'positive'),
                'negative': sum(1 for n in recent_news if n.get('sentiment', {}).get('label') == 'negative'),
                'neutral': sum(1 for n in recent_news if n.get('sentiment', {}).get('label') == 'neutral')
            }
            
            total_articles = len(recent_news)
            overall_sentiment = 'neutral'
            
            if total_articles > 0:
                if sentiment_counts['positive'] > sentiment_counts['negative'] * 1.5:
                    overall_sentiment = 'positive'
                elif sentiment_counts['negative'] > sentiment_counts['positive'] * 1.5:
                    overall_sentiment = 'negative'
            
            return {
                'indices': market_data,
                'news_sentiment': {
                    'overall': overall_sentiment,
                    'counts': sentiment_counts,
                    'total': total_articles
                },
                'updated_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error generating market summary: {e}")
            return {}


# Global instance
news_fetcher = None

def get_news_fetcher():
    """Get or create the global news fetcher instance"""
    global news_fetcher
    if news_fetcher is None:
        news_fetcher = NewsFetcher()
    return news_fetcher
