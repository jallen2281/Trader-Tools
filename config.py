"""Configuration settings for the financial chart analysis system."""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration."""
    
    # Ollama settings
    OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2-vision')
    OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', 120))  # seconds
    USE_VISION = os.getenv('USE_VISION', 'False').lower() == 'true'  # Default: text-only for speed
    FALLBACK_MODEL = os.getenv('FALLBACK_MODEL', 'llama3.2')  # Text-only fallback
    
    # Flask settings
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Default stock settings
    DEFAULT_SYMBOL = os.getenv('DEFAULT_SYMBOL', 'AAPL')
    DEFAULT_PERIOD = os.getenv('DEFAULT_PERIOD', '6mo')
    DEFAULT_INTERVAL = os.getenv('DEFAULT_INTERVAL', '1d')
    
    # Chart settings
    CHART_WIDTH = 1200
    CHART_HEIGHT = 600
    CHART_DPI = 100
    
    # Pattern recognition settings
    MIN_PATTERN_CONFIDENCE = 0.7
