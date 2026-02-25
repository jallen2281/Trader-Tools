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

logger = logging.getLogger(__name__)


class CorrelationAnalyzer:
    """Analyzes portfolio correlations and generates heat maps"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=1)
    
    def get_portfolio_correlation_matrix(self, user_id: int, period: str = '3mo') -> Dict:
        """
        Calculate correlation matrix for user's portfolio holdings
        
        Args:
            user_id: User ID
            period: Historical period (1mo, 3mo, 6mo, 1y, 2y)
            
        Returns:
            Dict with correlation matrix, symbols, and metadata
        """
        try:
            # Get portfolio holdings
            positions = Portfolio.query.filter_by(user_id=user_id).all()
            if not positions:
                return {'error': 'No portfolio found'}
            
            symbols = [pos.symbol for pos in positions]
            
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
            cache_key = f"{user_id}_{period}_{'_'.join(sorted(symbols))}"
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
                if len(symbols) == 1:
                    # Single symbol: data has simple column structure
                    if 'Close' in data.columns:
                        close_prices = data[['Close']].copy()
                        close_prices.columns = symbols
                    else:
                        close_prices = data.copy()
                        close_prices.columns = symbols
                else:
                    # Multiple symbols: datahas MultiIndex columns
                    if isinstance(data.columns, pd.MultiIndex):
                        close_prices = data['Close'].copy()
                    else:
                        # Fallback: if for some reason it's not MultiIndex
                        close_prices = data.copy()
            except Exception as e:
                logger.error(f"Error extracting close prices: {e}")
                return {'error': f'Failed to extract price data: {str(e)}'}
            
            # Calculate returns
            returns = close_prices.pct_change().dropna()
            
            # Check if we have enough data
            if returns.empty or len(returns) < 2:
                return {'error': 'Insufficient historical data for correlation analysis'}
            
            # Calculate correlation matrix
            correlation_matrix = returns.corr()
            
            # Handle NaN values (can occur with insufficient data)
            if correlation_matrix.isnull().any().any():
                logger.warning("Correlation matrix contains NaN values, filling with 0")
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
                'data_points': len(returns),
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache result
            self.cache[cache_key] = (result, datetime.now())
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating correlation matrix: {e}")
            logger.error(traceback.format_exc())
            return {'error': str(e)}
    
    def get_diversification_metrics(self, user_id: int) -> Dict:
        """
        Calculate diversification metrics for portfolio
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with diversification score and risk metrics
        """
        try:
            positions = Portfolio.query.filter_by(user_id=user_id).all()
            if not positions:
                return {'error': 'No portfolio found'}
            
            if len(positions) < 2:
                return {
                    'diversification_score': 0,
                    'message': 'Need at least 2 positions for diversification analysis'
                }
            
            # Get correlation matrix
            corr_result = self.get_portfolio_correlation_matrix(user_id, period='3mo')
            if 'error' in corr_result:
                return corr_result
            
            # Calculate position weights
            total_value = sum([float(pos.quantity * pos.average_cost) for pos in positions])
            weights = {}
            for pos in positions:
                position_value = float(pos.quantity * pos.average_cost)
                weights[pos.symbol] = position_value / total_value if total_value > 0 else 0
            
            # Calculate weighted average correlation
            avg_corrs = corr_result['avg_correlations']
            weighted_correlation = sum([weights.get(symbol, 0) * avg_corrs.get(symbol, 0) 
                                       for symbol in weights.keys()])
            
            # Diversification score (0-100, lower correlation = higher score)
            # Score = 100 * (1 - weighted_correlation)
            diversification_score = max(0, min(100, round((1 - weighted_correlation) * 100)))
            
            # Calculate concentration (Herfindahl index)
            herfindahl_index = sum([w**2 for w in weights.values()])
            concentration_score = round(herfindahl_index * 100, 1)
            
            # Risk assessment
            risk_level = 'Low'
            if weighted_correlation > 0.7:
                risk_level = 'High'
            elif weighted_correlation > 0.5:
                risk_level = 'Medium'
            
            # Sector analysis
            sector_exposure = self._analyze_sector_exposure(positions)
            
            return {
                'diversification_score': diversification_score,
                'weighted_avg_correlation': round(weighted_correlation, 3),
                'concentration_score': concentration_score,
                'risk_level': risk_level,
                'position_count': len(positions),
                'sector_exposure': sector_exposure,
                'recommendations': self._get_diversification_recommendations(
                    weighted_correlation, 
                    concentration_score,
                    sector_exposure
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
                ticker = yf.Ticker(pos.symbol)
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
                                            sector_exposure: Dict) -> List[str]:
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
        
        # Concentration warning
        if concentration > 50:
            recommendations.append({
                'type': 'warning',
                'icon': '⚠️',
                'message': f'High concentration ({concentration}%) - portfolio is not well-balanced',
                'action': 'Consider balancing position sizes more evenly'
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
                
                close_prices = data['Close']
                returns = close_prices.pct_change().dropna()
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
