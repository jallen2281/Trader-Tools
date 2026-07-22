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
        self.model = getattr(Config, 'GOOGLE_AI_MODEL', 'gemini-flash-latest')
        self._resolved_model = None  # cache once a working model is confirmed
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

    def list_models(self) -> list:
        """Names of models this key can call generateContent on (best-effort)."""
        if not self.client:
            return []
        out = []
        try:
            for m in self.client.models.list():
                actions = (getattr(m, 'supported_actions', None)
                           or getattr(m, 'supported_generation_methods', None) or [])
                if 'generateContent' in actions:
                    out.append((getattr(m, 'name', '') or '').replace('models/', ''))
        except Exception as e:
            logger.warning("Gemini model list failed: %s", e)
        return out

    def _pick_model(self) -> str | None:
        """Discover a usable model when the configured one is unavailable.

        Prefers a cheap flash model, then pro, then anything that can generate.
        Only models the key can actually call are returned by list_models(), so a
        model deprecated for new users won't be selected.
        """
        names = self.list_models()
        if not names:
            return None
        for pref in ('flash-latest', 'flash', 'pro-latest', 'pro'):
            for n in names:
                low = n.lower()
                if pref in low and 'vision' not in low and 'embedding' not in low and 'tts' not in low:
                    return n
        return names[0]

    def read(self, system: str, facts: str) -> str | None:
        """One-shot Gemini call. Returns the read text, or None on any failure.

        Self-heals across Google's model churn: if the configured model returns
        NOT_FOUND, discover a valid one via list_models(), cache it, and retry once.
        """
        if not self.client:
            return None
        model = self._resolved_model or self.model
        for attempt in range(2):
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=facts,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=400,
                        temperature=0.4,
                    ),
                )
                text = (getattr(resp, 'text', None) or '').strip()
                self._resolved_model = model  # remember what worked
                return text or None
            except Exception as e:
                msg = str(e)
                if attempt == 0 and ('NOT_FOUND' in msg or '404' in msg):
                    picked = self._pick_model()
                    if picked and picked != model:
                        logger.info("Gemini model '%s' unavailable; switching to '%s'", model, picked)
                        model = picked
                        continue
                logger.warning("Gemini read failed (%s); caller will omit this read", e)
                return None
        return None
