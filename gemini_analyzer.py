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
        self.last_error = None
        api_key = getattr(Config, 'GOOGLE_AI_API_KEY', '') or ''
        self.client = None
        if _GENAI_AVAILABLE and api_key:
            try:
                # Give the client a hard timeout (ms) so a stuck call fails fast instead
                # of hanging the request. Guarded — older SDKs may lack HttpOptions.
                client_kwargs = {'api_key': api_key}
                # 30s per attempt: long enough for a real advisor read, short enough
                # that a stalled call fails fast so read() can switch to a healthy
                # sibling model within a sane total wait (a few attempts).
                HO = getattr(genai_types, 'HttpOptions', None)
                if HO is not None:
                    try:
                        client_kwargs['http_options'] = HO(timeout=30000)
                    except Exception:
                        pass
                self.client = genai.Client(**client_kwargs)
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

    # Error fragments that mean "this model is momentarily busy/gone" — switch to a
    # sibling model rather than giving up (a 503 on flash-latest doesn't mean every
    # flash variant is down).
    _CAPACITY_MARKERS = (
        'unavailable', 'overloaded', 'high demand', 'resource_exhausted',
        'rate limit', 'try again later', 'internal error', '503', '429', '500',
        'timed out', 'timeout', 'deadline', 'read timed out',
    )

    def _candidate_models(self, exclude=frozenset()) -> list:
        """Ordered text-generation models to try, cheapest/stablest first, so a
        momentarily-overloaded model can fall back to a healthy sibling."""
        names = self.list_models()
        ranked = []
        def ok(low):
            bad = ('vision', 'embedding', 'tts', 'image', 'audio', 'robotics',
                   'computer', 'lyria', 'deep-research', 'gemma')
            return not any(b in low for b in bad)
        # Prefer stable (non-preview) cheap flash, then pro; then anything text-capable.
        for pref in ('2.5-flash-lite', '2.5-flash', 'flash-lite-latest', 'flash-latest',
                     '3.5-flash', '3.6-flash', '3.7-flash', 'flash', 'pro-latest',
                     '2.5-pro', 'pro'):
            for n in names:
                low = n.lower()
                if (pref in low and 'preview' not in low and ok(low)
                        and n not in exclude and n not in ranked):
                    ranked.append(n)
        for n in names:  # last resort: previews and anything else text-capable
            if ok(n.lower()) and n not in exclude and n not in ranked:
                ranked.append(n)
        return ranked

    def _build_config(self, system: str, thinking_off: bool):
        """GenerateContentConfig with an ample output budget and (optionally)
        thinking disabled — current flash models think by default, which starves
        the visible answer of tokens and truncates it mid-sentence."""
        kwargs = dict(system_instruction=system, max_output_tokens=1024, temperature=0.4)
        TC = getattr(genai_types, 'ThinkingConfig', None)
        if thinking_off and TC is not None:
            try:
                kwargs['thinking_config'] = TC(thinking_budget=0)
            except Exception:
                pass
        return genai_types.GenerateContentConfig(**kwargs)

    def read(self, system: str, facts: str) -> str | None:
        """One-shot Gemini call. Returns the read text, or None on any failure.

        Robust to two Gemini quirks: (1) model churn — on NOT_FOUND, discover a
        valid model via list_models() and retry; (2) thinking models eating the
        token budget — request thinking off, and if a model rejects that, retry
        once with thinking left on and a larger budget.
        """
        if not self.client:
            return None
        model = self._resolved_model or self.model
        tried = set()
        alternates = None  # discovered lazily on the first capacity/not-found failure
        thinking_off = True
        tried_thinking_fallback = False
        for _ in range(4):  # ~4 attempts x 30s cap = bounded total wait
            switch = False  # set true to fall through to "try a different model"
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=facts,
                    config=self._build_config(system, thinking_off),
                )
                text = (getattr(resp, 'text', None) or '').strip()
                if text:
                    self._resolved_model = model  # remember what worked
                    self.last_error = None
                    return text
                # Empty text, no exception — usually a safety block or thinking ate the
                # whole budget. Retry once with thinking on, then try another model.
                if not tried_thinking_fallback and thinking_off:
                    thinking_off = False
                    tried_thinking_fallback = True
                    continue
                self.last_error = f"empty response from {model}"[:300]
                switch = True
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                self.last_error = f"{type(e).__name__}: {msg}"[:300]
                if not tried_thinking_fallback and thinking_off and ('thinking' in low or 'invalid_argument' in low):
                    thinking_off = False
                    tried_thinking_fallback = True
                    continue
                transient = (any(m in low for m in self._CAPACITY_MARKERS)
                             or 'not_found' in low or '404' in msg)
                if not transient:
                    logger.warning("Gemini read failed (%s); caller will omit this read", e)
                    return None
                switch = True  # model busy/gone — try a sibling
            if switch:
                tried.add(model)
                if alternates is None:
                    alternates = self._candidate_models(exclude=tried)
                nxt = next((c for c in alternates if c not in tried), None)
                if not nxt:
                    return None
                logger.info("Gemini model '%s' unavailable; switching to '%s'", model, nxt)
                model = nxt
                thinking_off = True
                tried_thinking_fallback = False
        return None
