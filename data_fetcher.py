"""Module for fetching financial data from various sources."""
import yfinance as yf
import pandas as pd
from typing import Optional, Tuple
from datetime import datetime, timedelta
import time
import logging
import threading
import random

logger = logging.getLogger(__name__)

# Global rate limiter to prevent overwhelming Yahoo Finance API
_request_lock = threading.Lock()
_last_request_time = None
_min_request_interval = 5.0  # 5 seconds base interval (increased from 2s)

# Track 429 errors for adaptive backoff
_last_429_time = None
_consecutive_429s = 0


def _rate_limited_request():
    """
    Global rate limiter for all Yahoo Finance API requests.
    Simple delay with randomization - let yfinance handle its own session management.
    """
    global _last_request_time
    
    with _request_lock:
        # Add random jitter to look more human-like (1-3 seconds extra)
        jitter = random.uniform(1.0, 3.0)
        base_interval = _min_request_interval + jitter
        
        if _last_request_time is not None:
            elapsed = time.time() - _last_request_time
            if elapsed < base_interval:
                sleep_time = base_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s (base={_min_request_interval}, jitter={jitter:.2f})")
                time.sleep(sleep_time)
        _last_request_time = time.time()


class FinancialDataFetcher:
    """Fetches and processes financial market data."""
    
    def __init__(self):
        """Initialize the data fetcher."""
        self.cache = {}
        self.cache_ttl = timedelta(minutes=10)  # Cache for 10 minutes to reduce API load
        # Common index symbol mappings
        self.symbol_map = {
            'SPX': '^GSPC',
            'SP500': '^GSPC',
            'DJI': '^DJI',
            'DOW': '^DJI',
            'NASDAQ': '^IXIC',
            'NDX': '^NDX',
            'RUT': '^RUT',
            'VIX': '^VIX'
        }
    
    def _get_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Get data from cache if not expired."""
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug(f"Cache HIT for {cache_key}")
                return data
            else:
                logger.debug(f"Cache EXPIRED for {cache_key}")
                del self.cache[cache_key]
        return None
    
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """Save data to cache with timestamp."""
        self.cache[cache_key] = (data, datetime.now())
        logger.debug(f"Cached data for {cache_key}")
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol for Yahoo Finance.
        
        Args:
            symbol: Original symbol
        
        Returns:
            Normalized symbol for Yahoo Finance
        """
        symbol = symbol.upper().strip()
        return self.symbol_map.get(symbol, symbol)
    
    def fetch_stock_data(
        self, 
        symbol: str, 
        period: str = "6mo",
        interval: str = "1d",
        max_retries: int = 2  # Reduce retries since we have longer delays
    ) -> Optional[pd.DataFrame]:
        """
        Fetch stock data from Yahoo Finance with retry logic for rate limiting.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'SPX')
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            max_retries: Maximum number of retry attempts for rate limiting
        
        Returns:
            DataFrame with OHLCV data or None if error
        """
        # Normalize symbol (e.g., SPX -> ^GSPC)
        normalized_symbol = self.normalize_symbol(symbol)
        
        global _consecutive_429s
        
        # Check cache first
        cache_key = f"{normalized_symbol}_{period}_{interval}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff with randomization: 5-7s, 10-14s
                    wait_base = (2 ** attempt) * 5
                    wait_jitter = random.uniform(0, wait_base * 0.4)  # Up to 40% jitter
                    wait_time = wait_base + wait_jitter
                    logger.warning(f"⚠ Retry {attempt}/{max_retries} for {symbol} after {wait_time:.1f}s backoff...")
                    time.sleep(wait_time)
                
                # Rate limit requests
                _rate_limited_request()
                
                logger.info(f"Fetching data for {symbol} (as {normalized_symbol}, period={period}, interval={interval})...")
                
                # Use yfinance 1.2.0+ which has better bot detection handling
                try:
                    ticker = yf.Ticker(normalized_symbol)
                    data = ticker.history(
                        period=period,
                        interval=interval
                    )
                    logger.debug(f"yfinance returned: type={type(data)}, shape={data.shape if hasattr(data, 'shape') else 'N/A'}")
                    
                except Exception as fetch_error:
                    error_msg = str(fetch_error)
                    logger.error(f"yfinance fetch failed for {symbol}: {error_msg}")
                
                if data is None:
                    logger.warning(f"No data returned (None) for {symbol} (tried {normalized_symbol})")
                    if attempt < max_retries - 1:
                        logger.info(f"Will retry {symbol} (attempt {attempt + 2}/{max_retries})")
                        continue  # Retry
                    return None
                    
                if data.empty:
                    logger.warning(f"Empty DataFrame returned for {symbol} (tried {normalized_symbol})")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying empty response for {symbol} (attempt {attempt + 2}/{max_retries})...")
                        # Longer delays for empty responses: 10-15s, 20-30s
                        retry_base = 10 * (attempt + 1)
                        retry_jitter = random.uniform(0, 5)
                        retry_delay = retry_base + retry_jitter
                        logger.info(f"Waiting {retry_delay:.1f}s due to empty response...")
                        time.sleep(retry_delay)
                        continue
                    logger.error(f"❌ Failed to fetch {symbol} after {max_retries} attempts - all returned empty")
                    logger.error(f"⚠ Yahoo Finance is blocking this cluster's IP address")
                    return None
                
                logger.info(f"✓ Successfully fetched {len(data)} rows for {symbol}")
                
                # Add useful calculated fields
                data['Symbol'] = symbol
                data['Returns'] = data['Close'].pct_change()
                data['Cumulative_Returns'] = (1 + data['Returns']).cumprod()
                
                # Cache the result
                self._save_to_cache(cache_key, data)
                
                return data
                
            except Exception as e:
                error_msg = str(e).lower()
                # Check if it's a rate limiting error
                if "429" in error_msg or "too many requests" in error_msg or "rate limit" in error_msg:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠ Rate limit (429) hit for {symbol}, retrying...")
                        continue
                    else:
                        logger.error(f"❌ Rate limit persists for {symbol} after {max_retries} attempts")
                        return None
                
                logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    logger.info(f"Retrying {symbol} due to error: {e}")
                    continue
        
        # All retries exhausted
        logger.error(f"✗ Failed to fetch {symbol} after {max_retries} attempts")
        return None
    
    def fetch_multiple_symbols(
        self,
        symbols: list,
        period: str = "6mo",
        interval: str = "1d"
    ) -> dict:
        """
        Fetch data for multiple symbols.
        
        Args:
            symbols: List of ticker symbols
            period: Data period
            interval: Data interval
        
        Returns:
            Dictionary mapping symbols to their DataFrames
        """
        results = {}
        for symbol in symbols:
            data = self.fetch_stock_data(symbol, period, interval)
            if data is not None:
                results[symbol] = data
        return results
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest price for a symbol.
        
        Args:
            symbol: Stock ticker symbol
        
        Returns:
            Latest closing price or None
        """
        try:
            # Normalize symbol
            normalized_symbol = self.normalize_symbol(symbol)
            
            # Rate limit requests
            _rate_limited_request()
            
            # Use yfinance 1.2.0+ default behavior
            ticker = yf.Ticker(normalized_symbol)
            data = ticker.history(period="1d")
            
            if data is not None and not data.empty:
                return float(data['Close'].iloc[-1])
            
            logger.warning(f"No price data for {symbol}")
            return None
        except Exception as e:
            logger.warning(f"Error getting latest price for {symbol}: {e}")
            return None
    
    def get_company_info(self, symbol: str) -> dict:
        """
        Get company information.
        
        Args:
            symbol: Stock ticker symbol
        
        Returns:
            Dictionary with company info
        """
        try:
            # Normalize symbol
            normalized_symbol = self.normalize_symbol(symbol)
            
            ticker = yf.Ticker(normalized_symbol)
            info = ticker.info
            
            # Handle case where info is None or empty
            if info is None or not isinstance(info, dict):
                return {
                    'name': symbol,
                    'sector': 'N/A',
                    'industry': 'N/A',
                    'market_cap': 'N/A',
                    'description': 'N/A'
                }
            
            return {
                'name': info.get('longName', info.get('shortName', symbol)),
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
                'market_cap': info.get('marketCap', 'N/A'),
                'description': info.get('longBusinessSummary', 'N/A')
            }
        except Exception as e:
            print(f"Error getting info for {symbol}: {e}")
            return {
                'name': symbol,
                'sector': 'N/A',
                'industry': 'N/A',
                'market_cap': 'N/A',
                'description': 'N/A'
            }
