"""
DefeatBeta API Data Fetcher
Alternative data source for historical stock data with no rate limits.
Uses defeatbeta-api as fallback when yfinance encounters issues.
"""

import logging
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta

# Lazy import to avoid errors if not installed
defeatbeta_api = None

logger = logging.getLogger(__name__)

def _ensure_defeatbeta_imported():
    """Lazy import of defeatbeta_api to avoid startup errors if not installed."""
    global defeatbeta_api
    if defeatbeta_api is None:
        try:
            import defeatbeta_api as db_api
            from defeatbeta_api.data.ticker import Ticker
            from defeatbeta_api.data.tickers import Tickers
            defeatbeta_api = {
                'Ticker': Ticker,
                'Tickers': Tickers,
                'available': True
            }
            logger.info("DefeatBeta API initialized successfully")
        except ImportError as e:
            logger.warning(f"DefeatBeta API not available: {e}")
            defeatbeta_api = {'available': False}
    return defeatbeta_api.get('available', False)


def is_available() -> bool:
    """Check if DefeatBeta API is available."""
    return _ensure_defeatbeta_imported()


def fetch_stock_data(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """
    Fetch historical stock data from DefeatBeta API.
    
    Args:
        symbol: Stock ticker symbol
        period: Time period (not used - DefeatBeta returns all available data)
        
    Returns:
        DataFrame with OHLCV data or None if failed
    """
    if not _ensure_defeatbeta_imported():
        return None
        
    try:
        ticker = defeatbeta_api['Ticker'](symbol)
        df = ticker.price()
        
        if df is None or df.empty:
            logger.warning(f"No data available for {symbol} from DefeatBeta")
            return None
            
        # Rename columns to match yfinance format
        column_mapping = {
            'report_date': 'Date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Set Date as index
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
        
        # Filter by period if needed (DefeatBeta returns all data)
        if period:
            days_map = {
                '1d': 1, '5d': 5, '1mo': 30, '3mo': 90,
                '6mo': 180, '1y': 365, '2y': 730, '5y': 1825,
                '10y': 3650, 'ytd': None, 'max': None
            }
            days = days_map.get(period)
            if days:
                cutoff_date = datetime.now() - timedelta(days=days)
                df = df[df.index >= cutoff_date]
        
        logger.info(f"✓ Fetched {len(df)} rows for {symbol} from DefeatBeta")
        return df
        
    except Exception as e:
        logger.error(f"Error fetching {symbol} from DefeatBeta: {e}")
        return None


def get_latest_price(symbol: str) -> Optional[float]:
    """
    Get the latest closing price for a symbol.
    
    Note: DefeatBeta data is updated weekly, so this returns the most recent
    available close price, not real-time.
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        Latest close price or None
    """
    if not _ensure_defeatbeta_imported():
        return None
        
    try:
        ticker = defeatbeta_api['Ticker'](symbol)
        df = ticker.price()
        
        if df is None or df.empty:
            return None
            
        # Get most recent close price
        latest_price = df['close'].iloc[-1]
        logger.debug(f"Latest price for {symbol}: ${latest_price:.2f}")
        return float(latest_price)
        
    except Exception as e:
        logger.error(f"Error getting latest price for {symbol}: {e}")
        return None


def fetch_financial_metrics(symbol: str) -> Optional[Dict]:
    """
    Fetch fundamental financial metrics from DefeatBeta.
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        Dictionary with financial metrics or None
    """
    if not _ensure_defeatbeta_imported():
        return None
        
    try:
        ticker = defeatbeta_api['Ticker'](symbol)
        
        metrics = {}
        
        # Try to get various metrics
        try:
            roe = ticker.roe()
            if roe is not None and not roe.empty:
                metrics['roe'] = float(roe.iloc[-1]['roe']) if 'roe' in roe.columns else None
        except:
            pass
            
        try:
            ttm_pe = ticker.ttm_pe()
            if ttm_pe is not None and not ttm_pe.empty:
                metrics['pe_ratio'] = float(ttm_pe.iloc[-1]['ttm_pe']) if 'ttm_pe' in ttm_pe.columns else None
        except:
            pass
            
        try:
            market_cap = ticker.market_cap()
            if market_cap is not None and not market_cap.empty:
                metrics['market_cap'] = float(market_cap.iloc[-1]['market_cap']) if 'market_cap' in market_cap.columns else None
        except:
            pass
        
        return metrics if metrics else None
        
    except Exception as e:
        logger.error(f"Error fetching financial metrics for {symbol}: {e}")
        return None


def fetch_batch_prices(symbols: List[str]) -> Dict[str, Optional[float]]:
    """
    Fetch latest prices for multiple symbols efficiently.
    
    Args:
        symbols: List of ticker symbols
        
    Returns:
        Dictionary mapping symbols to their latest prices
    """
    if not _ensure_defeatbeta_imported():
        return {symbol: None for symbol in symbols}
        
    try:
        tickers = defeatbeta_api['Tickers'](symbols)
        price_df = tickers.price()
        
        if price_df is None or price_df.empty:
            return {symbol: None for symbol in symbols}
        
        # Get latest price for each symbol
        result = {}
        for symbol in symbols:
            symbol_data = price_df[price_df['symbol'] == symbol]
            if not symbol_data.empty:
                result[symbol] = float(symbol_data['close'].iloc[-1])
            else:
                result[symbol] = None
                
        return result
        
    except Exception as e:
        logger.error(f"Error fetching batch prices: {e}")
        return {symbol: None for symbol in symbols}


class DefeatBetaFallback:
    """
    Wrapper that uses DefeatBeta as fallback when yfinance fails.
    Maintains the same interface as data_fetcher for easy swapping.
    """
    
    def __init__(self, primary_fetcher):
        """
        Args:
            primary_fetcher: The primary data fetcher module (e.g., data_fetcher)
        """
        self.primary = primary_fetcher
        self.use_fallback = False
        
    def fetch_stock_data(self, symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """Try primary first, fall back to DefeatBeta if needed."""
        try:
            df = self.primary.fetch_stock_data(symbol, period)
            if df is not None and not df.empty and len(df) > 0:
                return df
        except Exception as e:
            logger.warning(f"Primary fetcher failed for {symbol}: {e}")
        
        logger.info(f"Falling back to DefeatBeta for {symbol}")
        return fetch_stock_data(symbol, period)
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Try primary first, fall back to DefeatBeta if needed."""
        try:
            price = self.primary.get_latest_price(symbol)
            if price is not None:
                return price
        except Exception as e:
            logger.warning(f"Primary price fetch failed for {symbol}: {e}")
        
        logger.info(f"Falling back to DefeatBeta for {symbol} price")
        return get_latest_price(symbol)
