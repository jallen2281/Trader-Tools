"""
Correlation Matrix & Heat Map Analysis
Analyzes portfolio correlations, diversification, and risk concentration
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging
import traceback
from models import db, Portfolio, OptionsPosition
from data_fetcher import normalize_crypto_symbol

logger = logging.getLogger(__name__)


class CorrelationAnalyzer:
    """Analyzes portfolio correlations and generates heat maps"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=1)
    
    @staticmethod
    def _extract_close_prices(data, symbols):
        """Extract close prices from yfinance download data, handling all MultiIndex formats."""
        if not isinstance(data.columns, pd.MultiIndex):
            # Single ticker or flat columns
            if 'Close' in data.columns:
                close_prices = data[['Close']].copy()
                if len(symbols) == 1:
                    close_prices.columns = symbols
                return close_prices
            return data.copy()
        
        # MultiIndex columns - try both level orderings
        level_values_0 = data.columns.get_level_values(0).unique().tolist()
        level_values_1 = data.columns.get_level_values(1).unique().tolist()
        
        if 'Close' in level_values_0:
            # Old format: (Price, Ticker) - e.g. ('Close', 'AAPL')
            return data['Close'].copy()
        elif 'Close' in level_values_1:
            # New format: (Ticker, Price) - e.g. ('AAPL', 'Close')
            return data.xs('Close', level=1, axis=1).copy()
        else:
            logger.error(f"Cannot find 'Close' in columns. Level 0: {level_values_0}, Level 1: {level_values_1}")
            raise ValueError(f"Cannot extract close prices from columns: {data.columns.tolist()[:10]}")
    
    def get_portfolio_correlation_matrix(self, user_id: int, period: str = '3mo', account_id=None) -> Dict:
        """
        Calculate correlation matrix for user's portfolio holdings
        
        Args:
            user_id: User ID
            period: Historical period (1mo, 3mo, 6mo, 1y, 2y)
            
        Returns:
            Dict with correlation matrix, symbols, and metadata
        """
        try:
            # Get portfolio holdings (optionally scoped to a single account)
            q = Portfolio.query.filter_by(user_id=user_id)
            if account_id is not None:
                q = q.filter_by(account_id=account_id)
            positions = q.all()
            if not positions:
                return {'error': 'No portfolio found'}
            
            # Normalize symbols (e.g., crypto AVAX → AVAX-USD for yfinance)
            symbols = [normalize_crypto_symbol(pos.symbol, pos.asset_type) for pos in positions]
            # Deduplicate while preserving order
            symbols = list(dict.fromkeys(symbols))
            
            # Also include options positions
            options_positions = OptionsPosition.query.filter_by(user_id=user_id, status='open').all()
            for opt_pos in options_positions:
                if opt_pos.symbol not in symbols:
                    symbols.append(opt_pos.symbol)
            
            if len(symbols) < 2:
                return {
                    'error': 'Need at least 2 symbols for correlation analysis',
                    'symbols': symbols
                }
            
            # Check cache
            cache_key = f"{user_id}_{account_id}_{period}_{'_'.join(sorted(symbols))}"
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if datetime.now() - cached_time < self.cache_duration:
                    logger.info(f"Returning cached correlation matrix for user {user_id}")
                    return cached_data
            
            # Download historical data
            logger.info(f"Calculating correlation matrix for {len(symbols)} symbols over {period}")
            data = yf.download(
                tickers=' '.join(symbols),
                period=period,
                interval='1d',
                progress=False
            )
            
            if data.empty:
                return {'error': 'No historical data available'}
            
            # Get close prices - handle both single and multi-symbol cases
            try:
                close_prices = self._extract_close_prices(data, symbols)
                # Ensure it's a DataFrame
                if isinstance(close_prices, pd.Series):
                    close_prices = close_prices.to_frame(name=symbols[0])
            except Exception as e:
                logger.error(f"Error extracting close prices: {e}")
                return {'error': f'Failed to extract price data: {str(e)}'}
            
            # Drop columns (symbols) that are entirely NaN (failed downloads / delisted)
            valid_before = list(close_prices.columns)
            close_prices = close_prices.dropna(axis=1, how='all')
            dropped = set(valid_before) - set(close_prices.columns)
            if dropped:
                logger.warning(f"Dropped symbols with no price data: {dropped}")
                symbols = [s for s in symbols if s in close_prices.columns]
            
            if len(symbols) < 2:
                return {
                    'error': f'Need at least 2 symbols with data for correlation (dropped: {", ".join(dropped) if dropped else "none"})',
                    'symbols': symbols
                }
            
            # Calculate returns
            # Do NOT drop rows here: dropping any day where *any* symbol is NaN
            # lets the shortest-history holding (e.g. a recent IPO) truncate the
            # sample for EVERY pair, collapsing all correlations toward noise.
            returns = close_prices.pct_change(fill_method=None)

            # Check we have at least a couple of usable rows overall
            if returns.dropna(how='all').shape[0] < 2:
                return {'error': 'Insufficient historical data for correlation analysis'}

            # Pairwise correlation: each pair uses every day where BOTH symbols
            # have data, so one short-history holding only shortens ITS pairs
            # instead of truncating the whole matrix.
            correlation_matrix = returns.corr(min_periods=20)
            
            # Pairs lacking >=20 overlapping days come back NaN — treat as no
            # signal (0) rather than letting them break the matrix.
            if correlation_matrix.isnull().any().any():
                logger.info("Some symbol pairs lacked sufficient overlap; filling those with 0")
                correlation_matrix = correlation_matrix.fillna(0)
            
            # Convert to list format for JSON
            matrix_data = []
            for i, symbol1 in enumerate(correlation_matrix.index):
                row = []
                for j, symbol2 in enumerate(correlation_matrix.columns):
                    corr_value = correlation_matrix.iloc[i, j]
                    # Ensure it's a valid number
                    if pd.isna(corr_value):
                        corr_value = 0.0
                    row.append({
                        'symbol1': symbol1,
                        'symbol2': symbol2,
                        'correlation': round(float(corr_value), 3),
                        'row': i,
                        'col': j
                    })
                matrix_data.append(row)
            
            # Calculate average correlations
            avg_correlations = {}
            for symbol in correlation_matrix.index:
                # Exclude self-correlation (1.0)
                other_corrs = [correlation_matrix.loc[symbol, other] 
                              for other in correlation_matrix.columns if other != symbol]
                # Filter out NaN values
                other_corrs = [c for c in other_corrs if not pd.isna(c)]
                avg_correlations[symbol] = round(float(np.mean(other_corrs)), 3) if other_corrs else 0.0
            
            result = {
                'matrix': matrix_data,
                'symbols': list(correlation_matrix.index),
                'avg_correlations': avg_correlations,
                'period': period,
                'data_points': int(returns.count().max()) if not returns.empty else 0,
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache result
            self.cache[cache_key] = (result, datetime.now())
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating correlation matrix: {e}")
            logger.error(traceback.format_exc())
            return {'error': str(e)}
    
    def get_diversification_metrics(self, user_id: int, account_id=None) -> Dict:
        """
        Calculate diversification metrics for portfolio
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with diversification score and risk metrics
        """
        try:
            q = Portfolio.query.filter_by(user_id=user_id)
            if account_id is not None:
                q = q.filter_by(account_id=account_id)
            positions = q.all()
            if not positions:
                return {'error': 'No portfolio found'}

            if len(positions) < 2:
                return {
                    'diversification_score': 0,
                    'message': 'Need at least 2 positions for diversification analysis'
                }
            
            # Get correlation matrix
            corr_result = self.get_portfolio_correlation_matrix(user_id, period='3mo', account_id=account_id)
            if 'error' in corr_result:
                return corr_result
            
            # Only analyze positions we actually have price data for — this drops
            # non-quotable placeholders (e.g. the manual 401k balance line
            # 'TA401K') and failed downloads so they can't dominate a cost-weighted
            # blend and fake out the score/sector. Sum duplicate symbols held
            # across accounts (e.g. AMZN in both RH and SoFi).
            priced = set(corr_result.get('symbols', []))
            priced_positions = [p for p in positions
                                if normalize_crypto_symbol(p.symbol, p.asset_type) in priced]
            if len(priced_positions) < 2:
                return {'diversification_score': 0,
                        'message': 'Need at least 2 price-quotable positions for diversification analysis'}
            value_by_symbol = {}
            for pos in priced_positions:
                sym = normalize_crypto_symbol(pos.symbol, pos.asset_type)
                value_by_symbol[sym] = value_by_symbol.get(sym, 0.0) + float(pos.quantity * pos.average_cost)
            total_value = sum(value_by_symbol.values())
            weights = {s: (v / total_value if total_value > 0 else 0) for s, v in value_by_symbol.items()}
            
            # Calculate weighted average correlation
            avg_corrs = corr_result['avg_correlations']
            weighted_correlation = sum(weights[sym] * avg_corrs.get(sym, 0) for sym in weights)
            
            # Concentration (Herfindahl) + largest / top-3 exposure
            herfindahl_index = sum(w**2 for w in weights.values())
            concentration_score = round(herfindahl_index * 100, 1)
            ranked = sorted(weights.items(), key=lambda x: x[1], reverse=True)
            largest_position = ({'symbol': ranked[0][0], 'weight': round(ranked[0][1] * 100, 1)}
                                if ranked else {'symbol': None, 'weight': 0})
            top3_weight = round(sum(w for _, w in ranked[:3]) * 100, 1)

            # Diversification score now penalizes BOTH high correlation AND high
            # concentration — a low-correlation book can still be concentrated in a
            # few names, which is not truly diversified.
            corr_factor = max(0.0, 1 - weighted_correlation)
            conc_factor = max(0.0, 1 - herfindahl_index)
            diversification_score = max(0, min(100, round(100 * corr_factor * conc_factor)))
            
            # Risk assessment (blend correlation + concentration)
            risk_level = 'Low'
            if weighted_correlation > 0.6 or largest_position['weight'] > 35 or top3_weight > 65:
                risk_level = 'High'
            elif weighted_correlation > 0.4 or largest_position['weight'] > 25 or top3_weight > 50:
                risk_level = 'Medium'
            
            # Sector analysis (only the price-quotable holdings)
            sector_exposure = self._analyze_sector_exposure(priced_positions)
            
            return {
                'diversification_score': diversification_score,
                'weighted_avg_correlation': round(weighted_correlation, 3),
                'concentration_score': concentration_score,
                'largest_position': largest_position,
                'top3_weight': top3_weight,
                'risk_level': risk_level,
                'position_count': len(priced_positions),
                'sector_exposure': sector_exposure,
                'recommendations': self._get_diversification_recommendations(
                    weighted_correlation, 
                    concentration_score,
                    sector_exposure,
                    largest_position,
                    top3_weight
                ),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating diversification metrics: {e}")
            logger.error(traceback.format_exc())
            return {'error': str(e)}
    
    def _analyze_sector_exposure(self, positions) -> Dict:
        """Analyze sector/industry exposure of portfolio"""
        sector_values = {}
        total_value = 0
        
        for pos in positions:
            try:
                yf_sym = normalize_crypto_symbol(pos.symbol, pos.asset_type)
                ticker = yf.Ticker(yf_sym)
                info = ticker.info
                sector = info.get('sector', 'Unknown')
                
                position_value = float(pos.quantity * pos.average_cost)
                total_value += position_value
                
                if sector not in sector_values:
                    sector_values[sector] = 0
                sector_values[sector] += position_value
                
            except Exception as e:
                logger.debug(f"Error getting sector for {pos.symbol}: {e}")
                continue
        
        # Convert to percentages
        sector_percentages = {}
        for sector, value in sector_values.items():
            sector_percentages[sector] = round((value / total_value * 100), 1) if total_value > 0 else 0
        
        # Sort by exposure
        sorted_sectors = sorted(sector_percentages.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'sectors': dict(sorted_sectors),
            'top_sector': sorted_sectors[0][0] if sorted_sectors else 'Unknown',
            'top_sector_exposure': sorted_sectors[0][1] if sorted_sectors else 0,
            'sector_count': len(sector_percentages)
        }
    
    def _get_diversification_recommendations(self, avg_correlation: float, 
                                            concentration: float,
                                            sector_exposure: Dict,
                                            largest_position: Dict = None,
                                            top3_weight: float = 0) -> List[str]:
        """Generate diversification recommendations"""
        recommendations = []
        
        # High correlation warning
        if avg_correlation > 0.7:
            recommendations.append({
                'type': 'warning',
                'icon': '⚠️',
                'message': 'High correlation detected - portfolio moves together significantly',
                'action': 'Consider adding uncorrelated assets to reduce risk'
            })
        elif avg_correlation > 0.5:
            recommendations.append({
                'type': 'info',
                'icon': 'ℹ️',
                'message': 'Moderate correlation between holdings',
                'action': 'Portfolio has some diversification but could be improved'
            })
        else:
            recommendations.append({
                'type': 'success',
                'icon': '✓',
                'message': 'Well-diversified portfolio with low correlation',
                'action': 'Maintain this diversification across asset classes'
            })
        
        # Single-name / top-3 concentration (more intuitive than a raw HHI number)
        if largest_position and largest_position.get('weight', 0) > 25:
            recommendations.append({
                'type': 'warning',
                'icon': '⚠️',
                'message': f"Largest position {largest_position['symbol']} is {largest_position['weight']}% of the book",
                'action': 'Consider trimming oversized single-name risk'
            })
        if top3_weight > 50:
            recommendations.append({
                'type': 'warning',
                'icon': '⚠️',
                'message': f'Top 3 positions are {top3_weight}% of the book',
                'action': 'Concentrated — spreading into more names would reduce single-name risk'
            })
        
        # Sector concentration
        top_sector_exposure = sector_exposure.get('top_sector_exposure', 0)
        if top_sector_exposure > 40:
            top_sector = sector_exposure.get('top_sector', 'Unknown')
            recommendations.append({
                'type': 'warning',
                'icon': '⚠️',
                'message': f'Over-exposed to {top_sector} sector ({top_sector_exposure}%)',
                'action': 'Consider diversifying across more sectors'
            })
        
        return recommendations
    
    def get_correlation_over_time(self, symbols: List[str], periods: List[str] = None) -> Dict:
        """
        Calculate how correlation has changed over different time periods
        
        Args:
            symbols: List of stock symbols
            periods: List of periods to analyze (default: ['1mo', '3mo', '6mo', '1y'])
            
        Returns:
            Dict with correlation trends over time
        """
        if periods is None:
            periods = ['1mo', '3mo', '6mo', '1y']
        
        if len(symbols) != 2:
            return {'error': 'Provide exactly 2 symbols for correlation over time'}
        
        try:
            results = []
            
            for period in periods:
                data = yf.download(
                    tickers=' '.join(symbols),
                    period=period,
                    interval='1d',
                    progress=False
                )
                
                if data.empty:
                    continue
                
                try:
                    close_prices = self._extract_close_prices(data, symbols)
                except Exception:
                    continue
                returns = close_prices.pct_change(fill_method=None).dropna()
                correlation = returns.corr().iloc[0, 1]
                
                results.append({
                    'period': period,
                    'correlation': round(float(correlation), 3),
                    'data_points': len(returns)
                })
            
            return {
                'symbols': symbols,
                'correlations': results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating correlation over time: {e}")
            logger.error(traceback.format_exc())
            return {'error': str(e)}
