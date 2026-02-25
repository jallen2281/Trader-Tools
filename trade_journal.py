"""
AI-Powered Trade Journal & Analytics

Analyzes trading history and provides AI-driven insights on:
- Trade performance metrics
- Pattern recognition in win/loss behavior  
- Hold time analysis
- Best/worst performing trades
- AI recommendations for improvement
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from models import Transaction, Portfolio
from llm_analyzer import LLMAnalyzer
import pandas as pd
from decimal import Decimal

logger = logging.getLogger(__name__)


class TradeJournal:
    """Analyzes trade history and generates AI-powered insights"""
    
    def __init__(self, llm_analyzer: LLMAnalyzer):
        self.llm_analyzer = llm_analyzer
        logger.info("✓ Trade Journal initialized")
    
    def get_trade_history(self, user_id: int, days: int = 90) -> Dict:
        """
        Get trade history with basic metrics
        
        Args:
            user_id: User ID
            days: Number of days to look back
            
        Returns:
            Dict with trades and summary metrics
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            # Get transactions
            transactions = Transaction.query.filter(
                Transaction.user_id == user_id,
                Transaction.transaction_date >= since
            ).order_by(Transaction.transaction_date.desc()).all()
            
            if not transactions:
                return {
                    'trades': [],
                    'summary': {
                        'total_trades': 0,
                        'buy_count': 0,
                        'sell_count': 0,
                        'total_invested': 0,
                        'total_proceeds': 0
                    }
                }
            
            # Calculate summary metrics
            buys = [t for t in transactions if t.transaction_type == 'buy']
            sells = [t for t in transactions if t.transaction_type == 'sell']
            
            total_invested = sum([float(t.quantity * t.price) for t in buys])
            total_proceeds = sum([float(t.quantity * t.price) for t in sells])
            
            trades_list = []
            for txn in transactions:
                trades_list.append({
                    'id': txn.id,
                    'symbol': txn.symbol,
                    'type': txn.transaction_type,
                    'quantity': float(txn.quantity),
                    'price': float(txn.price),
                    'total': float(txn.quantity * txn.price),
                    'date': txn.transaction_date.isoformat(),
                    'notes': txn.notes or ''
                })
            
            return {
                'trades': trades_list,
                'summary': {
                    'total_trades': len(transactions),
                    'buy_count': len(buys),
                    'sell_count': len(sells),
                    'total_invested': round(total_invested, 2),
                    'total_proceeds': round(total_proceeds, 2),
                    'net_flow': round(total_proceeds - total_invested, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return {'error': str(e)}
    
    def analyze_performance(self, user_id: int, days: int = 90) -> Dict:
        """
        Analyze trading performance with realized gains/losses
        
        Args:
            user_id: User ID
            days: Number of days to look back
            
        Returns:
            Dict with performance metrics
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            # Get all transactions
            transactions = Transaction.query.filter(
                Transaction.user_id == user_id,
                Transaction.transaction_date >= since
            ).order_by(Transaction.transaction_date.asc()).all()
            
            if not transactions:
                return {'error': 'No transactions found'}
            
            # Track positions to calculate realized P&L
            positions = {}  # symbol -> {quantity, avg_cost}
            realized_gains = []
            
            for txn in transactions:
                symbol = txn.symbol
                
                if txn.transaction_type == 'buy':
                    if symbol not in positions:
                        positions[symbol] = {'quantity': 0, 'total_cost': 0}
                    
                    positions[symbol]['quantity'] += float(txn.quantity)
                    positions[symbol]['total_cost'] += float(txn.quantity * txn.price)
                    
                elif txn.transaction_type == 'sell':
                    if symbol in positions and positions[symbol]['quantity'] > 0:
                        # Calculate average cost
                        avg_cost = positions[symbol]['total_cost'] / positions[symbol]['quantity']
                        
                        # Realized gain/loss
                        sell_proceeds = float(txn.quantity * txn.price)
                        cost_basis = float(txn.quantity) * avg_cost
                        gain = sell_proceeds - cost_basis
                        gain_pct = (gain / cost_basis * 100) if cost_basis > 0 else 0
                        
                        # Hold time calculation
                        hold_time = None
                        buy_txn = Transaction.query.filter(
                            Transaction.user_id == user_id,
                            Transaction.symbol == symbol,
                            Transaction.transaction_type == 'buy',
                            Transaction.transaction_date < txn.transaction_date
                        ).order_by(Transaction.transaction_date.desc()).first()
                        
                        if buy_txn:
                            hold_time = (txn.transaction_date - buy_txn.transaction_date).days
                        
                        realized_gains.append({
                            'symbol': symbol,
                            'sell_date': txn.transaction_date.isoformat(),
                            'quantity': float(txn.quantity),
                            'sell_price': float(txn.price),
                            'avg_cost': round(avg_cost, 2),
                            'gain': round(gain, 2),
                            'gain_pct': round(gain_pct, 2),
                            'hold_days': hold_time
                        })
                        
                        # Update position
                        positions[symbol]['quantity'] -= float(txn.quantity)
                        if positions[symbol]['quantity'] > 0:
                            positions[symbol]['total_cost'] -= cost_basis
                        else:
                            positions[symbol] = {'quantity': 0, 'total_cost': 0}
            
            # Calculate metrics
            if not realized_gains:
                return {
                    'realized_trades': [],
                    'metrics': {
                        'total_realized': 0,
                        'winners': 0,
                        'losers': 0,
                        'win_rate': 0,
                        'avg_gain': 0,
                        'avg_loss': 0,
                        'avg_hold_time': 0,
                        'best_trade': None,
                        'worst_trade': None,
                        'total_trades': 0
                    }
                }
            
            winners = [t for t in realized_gains if t['gain'] > 0]
            losers = [t for t in realized_gains if t['gain'] < 0]
            
            total_realized = sum([t['gain'] for t in realized_gains])
            avg_gain = sum([t['gain'] for t in winners]) / len(winners) if winners else 0
            avg_loss = sum([t['gain'] for t in losers]) / len(losers) if losers else 0
            
            hold_times = [t['hold_days'] for t in realized_gains if t['hold_days'] is not None]
            avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
            
            best_trade = max(realized_gains, key=lambda x: x['gain'])
            worst_trade = min(realized_gains, key=lambda x: x['gain'])
            
            return {
                'realized_trades': realized_gains,
                'metrics': {
                    'total_realized': round(total_realized, 2),
                    'winners': len(winners),
                    'losers': len(losers),
                    'win_rate': round(len(winners) / len(realized_gains) * 100, 1) if realized_gains else 0,
                    'avg_gain': round(avg_gain, 2),
                    'avg_loss': round(avg_loss, 2),
                    'avg_hold_time': round(avg_hold_time, 1),
                    'best_trade': best_trade,
                    'worst_trade': worst_trade,
                    'total_trades': len(realized_gains)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing performance: {e}")
            return {'error': str(e)}
    
    def get_ai_insights(self, user_id: int, days: int = 90) -> Dict:
        """
        Get AI-powered insights on trading patterns
        
        Args:
            user_id: User ID
            days: Number of days to analyze
            
        Returns:
            Dict with AI-generated insights and recommendations
        """
        try:
            # Get performance data
            performance = self.analyze_performance(user_id, days)
            
            if 'error' in performance:
                return performance
            
            metrics = performance['metrics']
            
            if metrics['total_trades'] == 0:
                return {
                    'insights': [],
                    'recommendations': ['Start trading to receive AI-powered insights!']
                }
            
            # Build context for LLM
            context = f"""Analyze this trader's performance over the last {days} days:

Performance Metrics:
- Total Realized P&L: ${metrics['total_realized']}
- Win Rate: {metrics['win_rate']}% ({metrics['winners']} wins, {metrics['losers']} losses)
- Average Gain: ${metrics['avg_gain']}
- Average Loss: ${metrics['avg_loss']}
- Average Hold Time: {metrics['avg_hold_time']} days
- Best Trade: {metrics['best_trade']['symbol']} +${metrics['best_trade']['gain']} ({metrics['best_trade']['gain_pct']}%)
- Worst Trade: {metrics['worst_trade']['symbol']} ${metrics['worst_trade']['gain']} ({metrics['worst_trade']['gain_pct']}%)

Provide 3-4 key insights about their trading patterns and 3-4 actionable recommendations for improvement. Be specific and constructive."""

            # Get AI analysis
            ai_response = self.llm_analyzer.analyze(
                symbol="PORTFOLIO",
                chart_data={},
                additional_context=context
            )
            
            # Parse response into insights and recommendations
            insights = []
            recommendations = []
            
            if ai_response and 'analysis' in ai_response:
                analysis_text = ai_response['analysis']
                
                # Simple parsing - look for sections
                lines = analysis_text.split('\n')
                current_section = None
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if 'insight' in line.lower() or 'pattern' in line.lower():
                        current_section = 'insights'
                    elif 'recommend' in line.lower() or 'suggestion' in line.lower():
                        current_section = 'recommendations'
                    elif current_section == 'insights' and line.startswith(('-', '•', '*', '1', '2', '3')):
                        insights.append(line.lstrip('-•*123456789. '))
                    elif current_section == 'recommendations' and line.startswith(('-', '•', '*', '1', '2', '3')):
                        recommendations.append(line.lstrip('-•*123456789. '))
            
            # Fallback if parsing didn't work
            if not insights:
                insights = [
                    f"Win rate of {metrics['win_rate']}% suggests {'strong' if metrics['win_rate'] > 60 else 'moderate' if metrics['win_rate'] > 40 else 'developing'} trade selection",
                    f"Average hold time of {metrics['avg_hold_time']:.0f} days indicates {'short-term' if metrics['avg_hold_time'] < 30 else 'medium-term'} trading style",
                    f"{'Profits secured' if metrics['total_realized'] > 0 else 'Learning phase'} with ${abs(metrics['total_realized']):.2f} realized"
                ]
            
            if not recommendations:
                recommendations = [
                    "Consider position sizing to limit losses to 2-3% per trade",
                    "Set stop-losses based on technical support levels",
                    "Review winning trades to identify repeatable patterns"
                ]
            
            return {
                'insights': insights[:4],
                'recommendations': recommendations[:4],
                'ai_analysis': ai_response.get('analysis', '') if ai_response else '',
                'metrics_summary': metrics
            }
            
        except Exception as e:
            logger.error(f"Error generating AI insights: {e}")
            return {'error': str(e)}
    
    def add_trade_note(self, transaction_id: int, user_id: int, note: str) -> Dict:
        """
        Add or update notes for a transaction
        
        Args:
            transaction_id: Transaction ID
            user_id: User ID (for security)
            note: Note text
            
        Returns:
            Dict with success status
        """
        try:
            txn = Transaction.query.filter_by(
                id=transaction_id,
                user_id=user_id
            ).first()
            
            if not txn:
                return {'error': 'Transaction not found'}
            
            txn.notes = note
            from models import db
            db.session.commit()
            
            return {'success': True, 'message': 'Note saved successfully'}
            
        except Exception as e:
            logger.error(f"Error saving note: {e}")
            return {'error': str(e)}
