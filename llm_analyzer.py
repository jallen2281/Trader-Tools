"""Module for integrating with local LLM via Ollama."""
import ollama
import base64
from typing import Optional, Dict, List
from config import Config
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading


class LLMAnalyzer:
    """Analyzes financial charts using a local LLM."""
    
    def __init__(self):
        """Initialize the LLM analyzer."""
        self.config = Config()
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Ollama client."""
        try:
            # Test connection
            ollama.list()
            self.client = True
            print(f"✓ Connected to Ollama at {self.config.OLLAMA_HOST}")
        except Exception as e:
            print(f"✗ Could not connect to Ollama: {e}")
            print("Make sure Ollama is running: 'ollama serve'")
            self.client = False
    
    def _call_ollama_with_timeout(self, model: str, messages: List[Dict], options: Dict, timeout: int = 20) -> Optional[Dict]:
        """Call Ollama with timeout to prevent hanging."""
        result = [None]
        exception = [None]
        
        def _call():
            try:
                result[0] = ollama.chat(model=model, messages=messages, options=options)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=_call)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"⚠ Ollama call timed out after {timeout}s")
            return None
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def analyze_chart(
        self,
        chart_base64: str,
        symbol: str,
        indicators: Dict,
        patterns: List[Dict],
        context: Optional[str] = None
    ) -> str:
        """
        Analyze a financial chart using vision-capable LLM.
        
        Args:
            chart_base64: Base64 encoded chart image
            symbol: Stock symbol
            indicators: Dictionary of technical indicators
            patterns: List of detected patterns
            context: Additional context
        
        Returns:
            LLM analysis text
        """
        if not self.client:
            return "LLM not available. Please start Ollama service."
        
        # Use text-only analysis by default (faster and more reliable)
        if not self.config.USE_VISION:
            print(f"Using text-only analysis (USE_VISION=False)...")
            return self._analyze_text_only(symbol, indicators, patterns, context)
        
        try:
            # Prepare the prompt
            prompt = self._build_analysis_prompt(symbol, indicators, patterns, context)
            
            print(f"Attempting vision analysis with {self.config.OLLAMA_MODEL}...")
            
            # Try vision model
            try:
                response = ollama.chat(
                    model=self.config.OLLAMA_MODEL,
                    messages=[{
                        'role': 'user',
                        'content': prompt,
                        'images': [chart_base64]
                    }],
                    options={
                        'temperature': 0.7,
                        'num_predict': 500  # Limit response length
                    }
                )
                
                print("✓ Vision analysis completed")
                return response['message']['content']
                
            except Exception as vision_error:
                error_str = str(vision_error).lower()
                print(f"⚠ Vision analysis failed: {vision_error}")
                
                # If vision fails, fall back to text-only analysis
                if "model" in error_str or "not found" in error_str:
                    return (f"Model '{self.config.OLLAMA_MODEL}' not found or doesn't support vision. "
                           f"Please install it: 'ollama pull llama3.2-vision' "
                           f"or set USE_VISION=False in config for text-only analysis.")
                
                # Try text-only fallback
                print("→ Falling back to text-only analysis...")
                return self._analyze_text_only(symbol, indicators, patterns, context)
            
        except Exception as e:
            error_msg = str(e)
            print(f"✗ Analysis error: {error_msg}")
            return f"Error analyzing chart: {error_msg}"
    
    def _analyze_text_only(
        self,
        symbol: str,
        indicators: Dict,
        patterns: List[Dict],
        context: Optional[str] = None
    ) -> str:
        """
        Fallback text-only analysis when vision fails.
        
        Args:
            symbol: Stock symbol
            indicators: Dictionary of technical indicators
            patterns: List of detected patterns
            context: Additional context
        
        Returns:
            LLM analysis text
        """
        try:
            prompt = self._build_analysis_prompt(symbol, indicators, patterns, context)
            prompt += "\n\nNote: Analyzing based on technical indicators and patterns."
            
            # Use fallback model (text-only)
            model = self.config.FALLBACK_MODEL
            print(f"Using text-only model: {model}")
            
            response = self._call_ollama_with_timeout(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.7, 'num_predict': 400},
                timeout=45  # 45 second timeout for full analysis
            )
            
            if response is None:
                return "AI analysis timed out. Technical analysis shows: " + json.dumps(indicators, indent=2)
            
            print(f"✓ Text-only analysis completed")
            return response['message']['content']
            
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "model" in error_str:
                return (f"Model '{self.config.FALLBACK_MODEL}' not found. "
                       f"Please install it: 'ollama pull {self.config.FALLBACK_MODEL}'")
            return (f"Unable to perform analysis. Please ensure Ollama is running "
                   f"and a model is available. Error: {str(e)}")
    
    def analyze_without_image(
        self,
        symbol: str,
        data_summary: Dict,
        indicators: Dict,
        patterns: List[Dict],
        signals: Dict
    ) -> str:
        """
        Analyze market data without image (text-only).
        
        Args:
            symbol: Stock symbol
            data_summary: Summary of price data
            indicators: Technical indicators
            patterns: Detected patterns
            signals: Trading signals
        
        Returns:
            LLM analysis text
        """
        if not self.client:
            return "LLM not available. Please start Ollama service."
        
        try:
            prompt = self._build_text_analysis_prompt(
                symbol, data_summary, indicators, patterns, signals
            )
            
            # Use a text-only model (fallback)
            model = "llama3.2" if "vision" in self.config.OLLAMA_MODEL else self.config.OLLAMA_MODEL
            
            response = ollama.chat(
                model=model,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            
            return response['message']['content']
            
        except Exception as e:
            return f"Error analyzing data: {str(e)}"
    
    def _build_analysis_prompt(
        self,
        symbol: str,
        indicators: Dict,
        patterns: List[Dict],
        context: Optional[str]
    ) -> str:
        """Build analysis prompt for vision model."""
        prompt = f"""You are a professional financial analyst. Analyze this chart for {symbol}.

Technical Indicators:
{json.dumps(indicators, indent=2)}

Detected Patterns:
{json.dumps(patterns, indent=2)}

"""
        
        if context:
            prompt += f"Additional Context:\n{context}\n\n"
        
        prompt += """Please provide:
1. Overall trend analysis
2. Key support and resistance levels visible in the chart
3. Pattern interpretations
4. Potential trading opportunities
5. Risk assessment
6. Short-term and medium-term outlook

Be specific and reference what you see in the chart."""
        
        return prompt
    
    def _build_text_analysis_prompt(
        self,
        symbol: str,
        data_summary: Dict,
        indicators: Dict,
        patterns: List[Dict],
        signals: Dict
    ) -> str:
        """Build text-only analysis prompt."""
        prompt = f"""You are a professional financial analyst. Analyze the following market data for {symbol}.

Price Summary:
- Current Price: ${data_summary.get('current_price', 'N/A')}
- Change: {data_summary.get('change_pct', 'N/A')}%
- High: ${data_summary.get('high', 'N/A')}
- Low: ${data_summary.get('low', 'N/A')}
- Volume: {data_summary.get('volume', 'N/A')}

Technical Indicators:
{json.dumps(indicators, indent=2)}

Trading Signals:
{json.dumps(signals, indent=2)}

Detected Patterns:
{json.dumps(patterns, indent=2)}

Please provide:
1. Overall technical analysis
2. Trend assessment
3. Momentum analysis
4. Support/resistance levels
5. Trading recommendations
6. Risk factors to consider

Be specific and data-driven in your analysis."""
        
        return prompt
    
    def get_pattern_explanation(self, pattern_name: str) -> str:
        """
        Get explanation for a specific pattern.
        
        Args:
            pattern_name: Name of the pattern
        
        Returns:
            Explanation text
        """
        if not self.client:
            return "LLM not available."
        
        try:
            prompt = f"""Explain the '{pattern_name}' trading pattern in simple terms:
1. What it looks like
2. What it indicates
3. How traders typically respond to it
4. Reliability and limitations

Keep it concise (3-4 sentences)."""
            
            model = "llama3.2" if "vision" in self.config.OLLAMA_MODEL else self.config.OLLAMA_MODEL
            
            response = ollama.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            return response['message']['content']
            
        except Exception as e:
            return f"Error getting explanation: {str(e)}"
    
    def check_ollama_status(self) -> Dict:
        """
        Check Ollama service status and available models.
        
        Returns:
            Status dictionary
        """
        try:
            models = ollama.list()
            model_names = [m['name'] for m in models.get('models', [])]
            
            return {
                'status': 'running',
                'models': model_names,
                'configured_model': self.config.OLLAMA_MODEL,
                'model_available': self.config.OLLAMA_MODEL in model_names
            }
        except Exception as e:
            return {
                'status': 'not_running',
                'error': str(e),
                'message': 'Please start Ollama: ollama serve'
            }
