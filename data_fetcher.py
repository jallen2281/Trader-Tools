"""Module for fetching financial data from various sources."""
import yfinance as yf
import pandas as pd
from typing import Optional, Tuple
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)


class FinancialDataFetcher:
    """Fetches and processes financial market data."""
    
    def __init__(self):
        """Initialize the data fetcher."""
        self.cache = {}
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
        max_retries: int = 3
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
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"⚠ Retry {attempt}/{max_retries} for {symbol} after {wait_time}s backoff...")
                    time.sleep(wait_time)
                
                print(f"Fetching data for {symbol} (as {normalized_symbol})...")
                
                ticker = yf.Ticker(normalized_symbol)
                
                # Try to fetch history with error handling
                try:
                    data = ticker.history(period=period, interval=interval)
                except TypeError as te:
                    print(f"TypeError fetching {symbol}: {te}")
                    # Sometimes yfinance has issues, try with different parameters
                    try:
                        data = ticker.history(period=period)
                    except Exception as retry_error:
                        print(f"Retry also failed for {symbol}: {retry_error}")
                        if attempt < max_retries - 1:
                            continue
                        return None
                except AttributeError as ae:
                    print(f"AttributeError fetching {symbol}: {ae}")
                    print("This may indicate yfinance version issues")
                    return None
                
                if data is None:
                    print(f"No data returned (None) for {symbol} (tried {normalized_symbol})")
                    if "429" in str(data) or attempt < max_retries - 1:
                        continue  # Retry on rate limit
                    return None
                    
                if data.empty:
                    print(f"Empty data returned for {symbol} (tried {normalized_symbol})")
                    if attempt < max_retries - 1:
                        continue  # Retry on empty response (might be rate limiting)
                    return None
                
                print(f"✓ Fetched {len(data)} rows for {symbol}")
                
                # Add useful calculated fields
                data['Symbol'] = symbol
                data['Returns'] = data['Close'].pct_change()
                data['Cumulative_Returns'] = (1 + data['Returns']).cumprod()
                
                return data
                
            except Exception as e:
                error_msg = str(e).lower()
                # Check if it's a rate limiting error
                if "429" in error_msg or "too many requests" in error_msg or "rate limit" in error_msg:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠ Rate limit hit for {symbol}, retrying...")
                        continue
                
                print(f"Error fetching data for {symbol}: {e}")
                if attempt < max_retries - 1:
                    continue
                import traceback
                traceback.print_exc()
                return None
        
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
            
            ticker = yf.Ticker(normalized_symbol)
            data = ticker.history(period="1d")
            if data is not None and not data.empty:
                return float(data['Close'].iloc[-1])
            return None
        except Exception as e:
            print(f"Error getting latest price for {symbol}: {e}")
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
