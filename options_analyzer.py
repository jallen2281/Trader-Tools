"""
Options Analysis Engine
Phase 3: Advanced options analysis with Greeks, IV, and strategy recommendations
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import norm
import logging

logger = logging.getLogger(__name__)


class OptionsAnalyzer:
    """Comprehensive options analysis including Greeks and strategies"""
    
    def __init__(self):
        """Initialize options analyzer"""
        self.risk_free_rate = 0.045  # Current 10-year Treasury rate (~4.5%)
        
    def get_options_chain(self, symbol, expiration_date=None):
        """
        Get options chain for a symbol
        
        Args:
            symbol: Stock symbol
            expiration_date: Specific expiration date (optional)
            
        Returns:
            dict: Options chain data with calls and puts
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get available expiration dates
            expirations = ticker.options
            if not expirations:
                return {'error': f'No options available for {symbol}'}
            
            # Use nearest expiration if not specified
            if not expiration_date:
                expiration_date = expirations[0]
            
            # Get options chain
            opt_chain = ticker.option_chain(expiration_date)
            
            # Get current stock price
            stock_info = ticker.info
            current_price = stock_info.get('currentPrice', stock_info.get('regularMarketPrice', 0))
            
            result = {
                'symbol': symbol,
                'current_price': current_price,
                'expiration_date': expiration_date,
                'available_expirations': list(expirations),
                'calls': opt_chain.calls.to_dict('records'),
                'puts': opt_chain.puts.to_dict('records'),
                'timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching options chain for {symbol}: {e}")
            return {'error': str(e)}
    
    def calculate_greeks(self, option_type, stock_price, strike_price, 
                        time_to_expiry, volatility, dividend_yield=0):
        """
        Calculate option Greeks using Black-Scholes model
        
        Args:
            option_type: 'call' or 'put'
            stock_price: Current stock price
            strike_price: Option strike price
            time_to_expiry: Time to expiration in years
            volatility: Implied volatility (as decimal, e.g., 0.25 for 25%)
            dividend_yield: Annual dividend yield (as decimal)
            
        Returns:
            dict: Greeks (delta, gamma, theta, vega, rho)
        """
        try:
            if time_to_expiry <= 0:
                return {
                    'delta': 1.0 if option_type == 'call' else -1.0,
                    'gamma': 0,
                    'theta': 0,
                    'vega': 0,
                    'rho': 0
                }
            
            S = stock_price
            K = strike_price
            T = time_to_expiry
            sigma = volatility
            r = self.risk_free_rate
            q = dividend_yield
            
            # Calculate d1 and d2
            d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            
            # Calculate Greeks
            if option_type.lower() == 'call':
                delta = np.exp(-q * T) * norm.cdf(d1)
                theta = ((-S * norm.pdf(d1) * sigma * np.exp(-q * T)) / (2 * np.sqrt(T))
                        - r * K * np.exp(-r * T) * norm.cdf(d2)
                        + q * S * np.exp(-q * T) * norm.cdf(d1)) / 365
                rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
            else:  # put
                delta = -np.exp(-q * T) * norm.cdf(-d1)
                theta = ((-S * norm.pdf(d1) * sigma * np.exp(-q * T)) / (2 * np.sqrt(T))
                        + r * K * np.exp(-r * T) * norm.cdf(-d2)
                        - q * S * np.exp(-q * T) * norm.cdf(-d1)) / 365
                rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
            
            # Gamma and Vega are same for calls and puts
            gamma = (norm.pdf(d1) * np.exp(-q * T)) / (S * sigma * np.sqrt(T))
            vega = S * norm.pdf(d1) * np.sqrt(T) * np.exp(-q * T) / 100
            
            return {
                'delta': round(float(delta), 4),
                'gamma': round(float(gamma), 4),
                'theta': round(float(theta), 4),
                'vega': round(float(vega), 4),
                'rho': round(float(rho), 4)
            }
            
        except Exception as e:
            logger.error(f"Error calculating Greeks: {e}")
            return {'error': str(e)}
    
    def calculate_implied_volatility(self, option_price, option_type, stock_price, 
                                    strike_price, time_to_expiry, dividend_yield=0):
        """
        Calculate implied volatility using Newton-Raphson method
        
        Args:
            option_price: Current option price
            option_type: 'call' or 'put'
            stock_price: Current stock price
            strike_price: Option strike price
            time_to_expiry: Time to expiration in years
            dividend_yield: Annual dividend yield
            
        Returns:
            float: Implied volatility
        """
        try:
            # Initial guess
            sigma = 0.3
            max_iterations = 100
            tolerance = 1e-6
            
            for i in range(max_iterations):
                # Calculate option price with current sigma
                greeks = self.calculate_greeks(option_type, stock_price, strike_price,
                                               time_to_expiry, sigma, dividend_yield)
                
                # Calculate theoretical price
                price = self._black_scholes_price(option_type, stock_price, strike_price,
                                                   time_to_expiry, sigma, dividend_yield)
                
                # Calculate difference
                diff = price - option_price
                
                if abs(diff) < tolerance:
                    return round(sigma, 4)
                
                # Update sigma using vega
                vega = greeks.get('vega', 0)
                if vega == 0:
                    break
                    
                sigma = sigma - diff / (vega * 100)
                
                # Keep sigma positive and reasonable
                sigma = max(0.01, min(sigma, 5.0))
            
            return round(sigma, 4)
            
        except Exception as e:
            logger.error(f"Error calculating IV: {e}")
            return None
    
    def _black_scholes_price(self, option_type, stock_price, strike_price, 
                            time_to_expiry, volatility, dividend_yield=0):
        """Calculate Black-Scholes option price"""
        try:
            S = stock_price
            K = strike_price
            T = time_to_expiry
            sigma = volatility
            r = self.risk_free_rate
            q = dividend_yield
            
            d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            
            if option_type.lower() == 'call':
                price = (S * np.exp(-q * T) * norm.cdf(d1) - 
                        K * np.exp(-r * T) * norm.cdf(d2))
            else:
                price = (K * np.exp(-r * T) * norm.cdf(-d2) - 
                        S * np.exp(-q * T) * norm.cdf(-d1))
            
            return float(price)
            
        except Exception as e:
            return 0
    
    def analyze_options_comprehensive(self, symbol):
        """
        Comprehensive options analysis
        
        Args:
            symbol: Stock symbol
            
        Returns:
            dict: Complete options analysis with Greeks, IV, and recommendations
        """
        try:
            ticker = yf.Ticker(symbol)
            stock_info = ticker.info
            current_price = stock_info.get('currentPrice', stock_info.get('regularMarketPrice', 0))
            
            if not current_price:
                return {'error': 'Unable to fetch current stock price'}
            
            # Get options chain for nearest expiration
            options_data = self.get_options_chain(symbol)
            
            if 'error' in options_data:
                return options_data
            
            # Calculate days to expiration
            exp_date = datetime.strptime(options_data['expiration_date'], '%Y-%m-%d')
            days_to_exp = (exp_date - datetime.now()).days
            time_to_exp = days_to_exp / 365.0
            
            # Analyze calls and puts
            calls_analysis = self._analyze_options_side(
                options_data['calls'], 'call', current_price, time_to_exp
            )
            puts_analysis = self._analyze_options_side(
                options_data['puts'], 'put', current_price, time_to_exp
            )
            
            # Calculate put/call ratio
            total_call_volume = sum(c.get('volume', 0) or 0 for c in options_data['calls'])
            total_put_volume = sum(p.get('volume', 0) or 0 for p in options_data['puts'])
            put_call_ratio = (total_put_volume / total_call_volume 
                             if total_call_volume > 0 else 0)
            
            # Strategy recommendations
            strategies = self.recommend_strategies(
                current_price, calls_analysis, puts_analysis, put_call_ratio
            )
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'expiration_date': options_data['expiration_date'],
                'days_to_expiration': days_to_exp,
                'calls': calls_analysis,
                'puts': puts_analysis,
                'put_call_ratio': round(put_call_ratio, 2),
                'strategies': strategies,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive options analysis for {symbol}: {e}")
            return {'error': str(e)}
    
    def _analyze_options_side(self, options_list, option_type, current_price, time_to_exp):
        """Analyze one side of options chain (calls or puts)"""
        try:
            atm_options = []
            
            # Find ATM options (within 5% of current price)
            for opt in options_list:
                strike = opt.get('strike', 0)
                if abs(strike - current_price) / current_price < 0.05:
                    
                    # Calculate Greeks
                    last_price = opt.get('lastPrice', 0)
                    implied_vol = opt.get('impliedVolatility', 0.3)
                    
                    greeks = self.calculate_greeks(
                        option_type, current_price, strike,
                        time_to_exp, implied_vol
                    )
                    
                    atm_options.append({
                        'strike': strike,
                        'last_price': last_price,
                        'bid': opt.get('bid', 0),
                        'ask': opt.get('ask', 0),
                        'volume': opt.get('volume', 0),
                        'open_interest': opt.get('openInterest', 0),
                        'implied_volatility': round(implied_vol * 100, 2),
                        'greeks': greeks,
                        'in_the_money': opt.get('inTheMoney', False)
                    })
            
            # Sort by volume
            atm_options.sort(key=lambda x: x.get('volume', 0) or 0, reverse=True)
            
            return atm_options[:5]  # Return top 5
            
        except Exception as e:
            logger.error(f"Error analyzing {option_type}s: {e}")
            return []
    
    def recommend_strategies(self, current_price, calls_analysis, puts_analysis, put_call_ratio):
        """
        Recommend options strategies based on current conditions
        
        Args:
            current_price: Current stock price
            calls_analysis: Analyzed call options
            puts_analysis: Analyzed put options
            put_call_ratio: Put/call volume ratio
            
        Returns:
            list: Strategy recommendations
        """
        strategies = []
        
        try:
            # Strategy 1: Covered Call (if bullish but want income)
            if calls_analysis:
                call = calls_analysis[0]
                premium = call['last_price']
                strike = call['strike']
                
                strategies.append({
                    'name': 'Covered Call',
                    'type': 'income',
                    'description': f'Sell {strike} call for ${premium:.2f} premium per share',
                    'max_profit': f'${strike - current_price + premium:.2f} per share',
                    'max_loss': 'Unlimited downside (own stock)',
                    'breakeven': f'${current_price - premium:.2f}',
                    'outlook': 'Neutral to slightly bullish',
                    'capital_required': f'${current_price * 100:.2f} (own 100 shares)',
                    'risk_level': 'Moderate'
                })
            
            # Strategy 2: Protective Put (if bullish but want protection)
            if puts_analysis:
                put = puts_analysis[0]
                premium = put['last_price']
                strike = put['strike']
                
                strategies.append({
                    'name': 'Protective Put',
                    'type': 'protective',
                    'description': f'Buy {strike} put for ${premium:.2f} premium per share',
                    'max_profit': 'Unlimited (own stock)',
                    'max_loss': f'${current_price - strike + premium:.2f} per share',
                    'breakeven': f'${current_price + premium:.2f}',
                    'outlook': 'Bullish with downside protection',
                    'capital_required': f'${(current_price * 100) + (premium * 100):.2f}',
                    'risk_level': 'Low'
                })
            
            # Strategy 3: Bull Call Spread (if moderately bullish)
            if len(calls_analysis) >= 2:
                low_call = min(calls_analysis, key=lambda x: x['strike'])
                high_call = max(calls_analysis, key=lambda x: x['strike'])
                
                net_debit = low_call['last_price'] - high_call['last_price']
                max_profit = (high_call['strike'] - low_call['strike']) - net_debit
                
                strategies.append({
                    'name': 'Bull Call Spread',
                    'type': 'directional',
                    'description': f'Buy {low_call["strike"]} call, Sell {high_call["strike"]} call',
                    'max_profit': f'${max_profit * 100:.2f} total',
                    'max_loss': f'${net_debit * 100:.2f} (net debit)',
                    'breakeven': f'${low_call["strike"] + net_debit:.2f}',
                    'outlook': 'Moderately bullish',
                    'capital_required': f'${net_debit * 100:.2f}',
                    'risk_level': 'Moderate'
                })
            
            # Strategy 4: Iron Condor (if expecting low volatility)
            if len(calls_analysis) >= 2 and len(puts_analysis) >= 2:
                # This is a neutral strategy
                put_spread_credit = puts_analysis[0]['last_price'] - puts_analysis[1]['last_price']
                call_spread_credit = calls_analysis[0]['last_price'] - calls_analysis[1]['last_price']
                total_credit = put_spread_credit + call_spread_credit
                
                strategies.append({
                    'name': 'Iron Condor',
                    'type': 'neutral',
                    'description': 'Sell OTM put spread + Sell OTM call spread',
                    'max_profit': f'${total_credit * 100:.2f} (net credit)',
                    'max_loss': 'Limited to spread width minus credit',
                    'breakeven': 'Two breakevens (upper and lower)',
                    'outlook': 'Neutral (low volatility)',
                    'capital_required': 'Margin requirement',
                    'risk_level': 'Moderate to High'
                })
            
            # Strategy 5: Long Straddle (if expecting high volatility)
            if calls_analysis and puts_analysis:
                atm_call = calls_analysis[0]
                atm_put = puts_analysis[0]
                total_cost = atm_call['last_price'] + atm_put['last_price']
                
                strategies.append({
                    'name': 'Long Straddle',
                    'type': 'volatility',
                    'description': f'Buy ATM call + Buy ATM put',
                    'max_profit': 'Unlimited',
                    'max_loss': f'${total_cost * 100:.2f} (total premium paid)',
                    'breakeven': f'${current_price - total_cost:.2f} or ${current_price + total_cost:.2f}',
                    'outlook': 'High volatility expected',
                    'capital_required': f'${total_cost * 100:.2f}',
                    'risk_level': 'High'
                })
            
            # Add market sentiment-based recommendation
            if put_call_ratio > 1.0:
                sentiment = 'Bearish sentiment (high put volume)'
                suggested_strategies = ['Protective Put', 'Bear Put Spread']
            elif put_call_ratio < 0.7:
                sentiment = 'Bullish sentiment (high call volume)'
                suggested_strategies = ['Covered Call', 'Bull Call Spread']
            else:
                sentiment = 'Neutral sentiment'
                suggested_strategies = ['Iron Condor', 'Butterfly Spread']
            
            # Add sentiment to first strategy
            if strategies:
                strategies[0]['market_sentiment'] = sentiment
                strategies[0]['alternative_strategies'] = suggested_strategies
            
        except Exception as e:
            logger.error(f"Error generating strategy recommendations: {e}")
        
        return strategies
    
    def calculate_max_pain(self, symbol, expiration_date=None):
        """
        Calculate max pain - strike price where most options expire worthless
        
        Args:
            symbol: Stock symbol
            expiration_date: Expiration date
            
        Returns:
            dict: Max pain analysis
        """
        try:
            options_data = self.get_options_chain(symbol, expiration_date)
            
            if 'error' in options_data:
                return options_data
            
            # Calculate pain for each strike price
            strikes = set()
            for call in options_data['calls']:
                strikes.add(call['strike'])
            for put in options_data['puts']:
                strikes.add(put['strike'])
            
            strikes = sorted(list(strikes))
            pain_values = {}
            
            for strike in strikes:
                call_pain = 0
                put_pain = 0
                
                # Calculate call pain
                for call in options_data['calls']:
                    if call['strike'] < strike:
                        call_pain += (strike - call['strike']) * call.get('openInterest', 0)
                
                # Calculate put pain
                for put in options_data['puts']:
                    if put['strike'] > strike:
                        put_pain += (put['strike'] - strike) * put.get('openInterest', 0)
                
                pain_values[strike] = call_pain + put_pain
            
            # Find minimum pain
            max_pain_strike = min(pain_values, key=pain_values.get)
            
            return {
                'symbol': symbol,
                'expiration_date': options_data['expiration_date'],
                'max_pain_strike': max_pain_strike,
                'current_price': options_data['current_price'],
                'distance_from_max_pain': round(options_data['current_price'] - max_pain_strike, 2),
                'distance_pct': round((options_data['current_price'] - max_pain_strike) / options_data['current_price'] * 100, 2),
                'all_strikes': {k: round(v, 0) for k, v in pain_values.items()}
            }
            
        except Exception as e:
            logger.error(f"Error calculating max pain for {symbol}: {e}")
            return {'error': str(e)}
