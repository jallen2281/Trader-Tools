"""
Gemini (Google AI) analyzer — a second-opinion voice for holding analysis.

Deliberately separate from claude_analyzer.py (Anthropic) and llm_analyzer.py
(local Ollama/RKLLM). In the holding AI read, Claude gives the primary analyst
take and Gemini gives an independent counterpoint / bear-case — two different
models so the reads genuinely diverge instead of echoing each other.

The API key is read from the environment (Config.GOOGLE_AI_API_KEY), injected by
the k8s deployment via `envFrom: secretRef`. No key => this stays idle and the
caller simply omits the Gemini read.
"""
import logging
from config import Config

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except Exception:  # ImportError, or partial google namespace package
    genai = None
    genai_types = None
    _GENAI_AVAILABLE = False


class GeminiAnalyzer:
    """Narrative analysis via the Google GenAI (Gemini) API."""

    def __init__(self):
        self.model = getattr(Config, 'GOOGLE_AI_MODEL', 'gemini-2.5-flash')
        api_key = getattr(Config, 'GOOGLE_AI_API_KEY', '') or ''
        self.client = None
        if _GENAI_AVAILABLE and api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                logger.info("✓ Gemini analyzer ready (model=%s)", self.model)
            except Exception as e:
                logger.warning("Could not initialize Gemini client: %s", e)
        elif not _GENAI_AVAILABLE:
            logger.info("Gemini analyzer idle: google-genai package not installed")
        else:
            logger.info("Gemini analyzer idle: GOOGLE_AI_API_KEY not set")

    def available(self) -> bool:
        return self.client is not None

    def read(self, system: str, facts: str) -> str | None:
        """One-shot Gemini call. Returns the read text, or None on any failure."""
        if not self.client:
            return None
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=facts,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=400,
                    temperature=0.4,
                ),
            )
            text = (getattr(resp, 'text', None) or '').strip()
            return text or None
        except Exception as e:
            logger.warning("Gemini read failed (%s); caller will omit this read", e)
            return None
