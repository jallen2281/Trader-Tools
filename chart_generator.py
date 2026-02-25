"""Module for generating financial charts and visualizations."""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
from io import BytesIO
import base64
from typing import Optional, Dict, List
from config import Config


class ChartGenerator:
    """Generates various types of financial charts with technical indicators."""
    
    def __init__(self):
        """Initialize the chart generator."""
        self.config = Config()
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index (RSI)"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        ema_fast = data.ewm(span=fast, adjust=False).mean()
        ema_slow = data.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def calculate_bollinger_bands(self, data: pd.Series, period: int = 20, std_dev: int = 2) -> Dict:
        """Calculate Bollinger Bands"""
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }
    
    def calculate_moving_averages(self, data: pd.Series, periods: List[int] = [20, 50, 200]) -> Dict:
        """Calculate Simple Moving Averages"""
        mas = {}
        for period in periods:
            mas[f'MA{period}'] = data.rolling(window=period).mean()
        return mas
    
    def generate_candlestick_chart(
        self,
        data: pd.DataFrame,
        symbol: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        Generate a candlestick chart.
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol for title
            save_path: Optional path to save the image
        
        Returns:
            Base64 encoded image string or file path
        """
        # Prepare data for mplfinance
        df = data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        
        # Create custom style
        mc = mpf.make_marketcolors(
            up='#26a69a',
            down='#ef5350',
            edge='inherit',
            wick='inherit',
            volume='in'
        )
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False)
        
        # Create figure
        fig, axes = mpf.plot(
            df,
            type='candle',
            style=s,
            title=f'{symbol} - Candlestick Chart',
            ylabel='Price ($)',
            volume=True,
            figsize=(12, 8),
            returnfig=True
        )
        
        # Save or convert to base64
        if save_path:
            fig.savefig(save_path, dpi=self.config.CHART_DPI, bbox_inches='tight')
            plt.close(fig)
            return save_path
        else:
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=self.config.CHART_DPI, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return img_base64
    
    def generate_line_chart(
        self,
        data: pd.DataFrame,
        symbol: str,
        columns: list = ['Close'],
        save_path: Optional[str] = None
    ) -> str:
        """
        Generate a line chart.
        
        Args:
            data: DataFrame with price data
            symbol: Stock symbol for title
            columns: Columns to plot
            save_path: Optional path to save the image
        
        Returns:
            Base64 encoded image string or file path
        """
        fig, ax = plt.subplots(figsize=(12, 6))
        
        for col in columns:
            if col in data.columns:
                ax.plot(data.index, data[col], label=col, linewidth=2)
        
        ax.set_title(f'{symbol} - Price Chart', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Price ($)', fontsize=12)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save or convert to base64
        if save_path:
            fig.savefig(save_path, dpi=self.config.CHART_DPI, bbox_inches='tight')
            plt.close(fig)
            return save_path
        else:
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=self.config.CHART_DPI, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return img_base64
    
    def generate_volume_chart(
        self,
        data: pd.DataFrame,
        symbol: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        Generate a volume chart with price overlay.
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol for title
            save_path: Optional path to save the image
        
        Returns:
            Base64 encoded image string or file path
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                       gridspec_kw={'height_ratios': [3, 1]})
        
        # Price chart
        ax1.plot(data.index, data['Close'], label='Close Price', 
                linewidth=2, color='#1f77b4')
        ax1.set_title(f'{symbol} - Price and Volume', fontsize=16, fontweight='bold')
        ax1.set_ylabel('Price ($)', fontsize=12)
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        
        # Volume chart
        colors = ['#26a69a' if data['Close'].iloc[i] >= data['Open'].iloc[i] 
                  else '#ef5350' for i in range(len(data))]
        ax2.bar(data.index, data['Volume'], color=colors, alpha=0.7)
        ax2.set_xlabel('Date', fontsize=12)
        ax2.set_ylabel('Volume', fontsize=12)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save or convert to base64
        if save_path:
            fig.savefig(save_path, dpi=self.config.CHART_DPI, bbox_inches='tight')
            plt.close(fig)
            return save_path
        else:
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=self.config.CHART_DPI, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return img_base64
    
    def save_chart_to_file(self, data: pd.DataFrame, symbol: str, 
                          filename: str, chart_type: str = 'candlestick') -> str:
        """
        Save a chart to a file.
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol
            filename: Output filename
            chart_type: Type of chart ('candlestick', 'line', 'volume')
        
        Returns:
            Path to saved file
        """
        if chart_type == 'candlestick':
            return self.generate_candlestick_chart(data, symbol, filename)
        elif chart_type == 'line':
            return self.generate_line_chart(data, symbol, save_path=filename)
        elif chart_type == 'volume':
            return self.generate_volume_chart(data, symbol, filename)
        else:
            raise ValueError(f"Unknown chart type: {chart_type}")
    
    def generate_comparison_chart(
        self,
        data_dict: Dict[str, pd.DataFrame],
        normalize: bool = True,
        save_path: Optional[str] = None
    ) -> str:
        """
        Generate a comparison chart for multiple symbols.
        
        Args:
            data_dict: Dictionary mapping symbols to DataFrames
            normalize: Whether to normalize prices to percentage change
            save_path: Optional path to save the image
        
        Returns:
            Base64 encoded image string or file path
        """
        fig, ax = plt.subplots(figsize=(14, 8))
        
        for idx, (symbol, data) in enumerate(data_dict.items()):
            if 'Close' not in data.columns or data.empty:
                continue
                
            color = self.colors[idx % len(self.colors)]
            
            if normalize:
                # Normalize to percentage change from first value
                prices = data['Close']
                normalized = ((prices / prices.iloc[0]) - 1) * 100
                ax.plot(data.index, normalized, label=symbol, 
                       linewidth=2.5, color=color, alpha=0.8)
            else:
                # Plot actual prices
                ax.plot(data.index, data['Close'], label=symbol, 
                       linewidth=2.5, color=color, alpha=0.8)
        
        # Styling
        symbols_str = ', '.join(data_dict.keys())
        title = f'Comparison: {symbols_str} - ' + ('Normalized (% Change)' if normalize else 'Absolute Prices')
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('% Change' if normalize else 'Price ($)', fontsize=12)
        ax.legend(loc='best', fontsize=11, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Add zero line if normalized
        if normalize:
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
        
        plt.tight_layout()
        
        # Save or convert to base64
        if save_path:
            fig.savefig(save_path, dpi=self.config.CHART_DPI, bbox_inches='tight')
            plt.close(fig)
            return save_path
        else:
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=self.config.CHART_DPI, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return img_base64
    
    def generate_technical_chart(
        self,
        data: pd.DataFrame,
        symbol: str,
        indicators: List[str] = None,
        save_path: Optional[str] = None
    ) -> str:
        """
        Generate advanced chart with technical indicators.
        
        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol for title
            indicators: List of indicators to display ['rsi', 'macd', 'bb', 'ma']
            save_path: Optional path to save the image
        
        Returns:
            Base64 encoded image string or file path
        """
        if indicators is None:
            indicators = []
        
        # Calculate indicators
        close_prices = data['Close']
        
        rsi = self.calculate_rsi(close_prices) if 'rsi' in indicators else None
        macd_data = self.calculate_macd(close_prices) if 'macd' in indicators else None
        bb_data = self.calculate_bollinger_bands(close_prices) if 'bb' in indicators else None
        ma_data = self.calculate_moving_averages(close_prices) if 'ma' in indicators else None
        
        # Count subplots needed
        num_subplots = 1  # Main price chart
        if rsi is not None:
            num_subplots += 1
        if macd_data is not None:
            num_subplots += 1
        
        # Create figure with subplots
        height_ratios = [3] + [1] * (num_subplots - 1)
        fig, axes = plt.subplots(num_subplots, 1, figsize=(14, 4 * num_subplots),
                                gridspec_kw={'height_ratios': height_ratios})
        
        if num_subplots == 1:
            axes = [axes]
        
        ax_idx = 0
        
        # Main price chart with candlesticks
        ax = axes[ax_idx]
        ax_idx += 1
        
        # Plot candlesticks manually
        for i in range(len(data)):
            color = '#26a69a' if data['Close'].iloc[i] >= data['Open'].iloc[i] else '#ef5350'
            ax.plot([i, i], [data['Low'].iloc[i], data['High'].iloc[i]], 
                   color=color, linewidth=0.5, alpha=0.8)
            width = 0.6
            if data['Close'].iloc[i] >= data['Open'].iloc[i]:
                ax.bar(i, data['Close'].iloc[i] - data['Open'].iloc[i], 
                      width, bottom=data['Open'].iloc[i], color=color, alpha=0.8)
            else:
                ax.bar(i, data['Open'].iloc[i] - data['Close'].iloc[i], 
                      width, bottom=data['Close'].iloc[i], color=color, alpha=0.8)
        
        # Add Bollinger Bands
        if bb_data is not None:
            x_range = range(len(data))
            ax.plot(x_range, bb_data['upper'], 'b--', linewidth=1, alpha=0.5, label='BB Upper')
            ax.plot(x_range, bb_data['middle'], 'b-', linewidth=1, alpha=0.7, label='BB Middle (SMA20)')
            ax.plot(x_range, bb_data['lower'], 'b--', linewidth=1, alpha=0.5, label='BB Lower')
            ax.fill_between(x_range, bb_data['lower'], bb_data['upper'], alpha=0.1, color='blue')
        
        # Add Moving Averages
        if ma_data is not None:
            x_range = range(len(data))
            colors_ma = {'MA20': 'orange', 'MA50': 'purple', 'MA200': 'brown'}
            for ma_name, ma_values in ma_data.items():
                ax.plot(x_range, ma_values, linewidth=2, alpha=0.7, 
                       label=ma_name, color=colors_ma.get(ma_name, 'gray'))
        
        ax.set_title(f'{symbol} - Technical Analysis', fontsize=16, fontweight='bold')
        ax.set_ylabel('Price ($)', fontsize=12)
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-0.5, len(data) - 0.5)
        
        # RSI subplot
        if rsi is not None:
            ax = axes[ax_idx]
            ax_idx += 1
            x_range = range(len(data))
            ax.plot(x_range, rsi, color='#9c27b0', linewidth=2)
            ax.axhline(y=70, color='r', linestyle='--', linewidth=1, alpha=0.5)
            ax.axhline(y=30, color='g', linestyle='--', linewidth=1, alpha=0.5)
            ax.fill_between(x_range, 30, 70, alpha=0.1, color='gray')
            ax.set_ylabel('RSI', fontsize=12)
            ax.set_ylim(0, 100)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-0.5, len(data) - 0.5)
        
        # MACD subplot
        if macd_data is not None:
            ax = axes[ax_idx]
            ax_idx += 1
            x_range = range(len(data))
            ax.plot(x_range, macd_data['macd'], color='#2196f3', linewidth=2, label='MACD')
            ax.plot(x_range, macd_data['signal'], color='#ff9800', linewidth=2, label='Signal')
            
            # Histogram
            colors_hist = ['#26a69a' if h > 0 else '#ef5350' for h in macd_data['histogram']]
            ax.bar(x_range, macd_data['histogram'], color=colors_hist, alpha=0.5, label='Histogram')
            
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
            ax.set_ylabel('MACD', fontsize=12)
            ax.legend(loc='best', fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-0.5, len(data) - 0.5)
        
        # Set x-axis labels on bottom subplot
        axes[-1].set_xlabel('Date', fontsize=12)
        
        # Format x-axis with dates (sample every N labels to avoid crowding)
        step = max(1, len(data) // 10)
        tick_positions = list(range(0, len(data), step))
        tick_labels = [data.index[i].strftime('%Y-%m-%d') if i < len(data) else '' 
                      for i in tick_positions]
        axes[-1].set_xticks(tick_positions)
        axes[-1].set_xticklabels(tick_labels, rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save or convert to base64
        if save_path:
            fig.savefig(save_path, dpi=self.config.CHART_DPI, bbox_inches='tight')
            plt.close(fig)
            return save_path
        else:
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=self.config.CHART_DPI, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return img_base64
