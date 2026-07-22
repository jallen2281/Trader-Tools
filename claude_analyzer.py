"""
Claude (Anthropic API) analyzer — plain-English portfolio reads.

Kept deliberately separate from llm_analyzer.py (the local Ollama/RKLLM engine).
Claude is the PRIMARY engine for narrative synthesis; callers fall back to the
local LLM when Claude is unavailable (no API key, package missing, or API error).

The API key is read from the environment (Config.ANTHROPIC_API_KEY), which the
k8s deployment injects via `envFrom: secretRef` — so adding ANTHROPIC_API_KEY to
the cluster secret is all it takes to switch this on. No key => this stays idle
and the caller uses the local LLM.
"""
import logging
from config import Config

logger = logging.getLogger(__name__)

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    _ANTHROPIC_AVAILABLE = False


class ClaudeAnalyzer:
    """Narrative portfolio analysis via the Anthropic Messages API."""

    SYSTEM_PROMPT = (
        "You are a sharp, plain-spoken portfolio risk analyst. You are given pre-computed "
        "diversification statistics for ONE stock account. Write a 3-4 sentence read for the "
        "account owner that translates the numbers into what they mean: how many real 'bets' the "
        "book actually is, where the concentration and correlation risk sits, and the one thing "
        "most worth watching. Name the largest position and its weight. Be direct and specific; "
        "no bullet points, no preamble, no hedging, no jargon. Do NOT give buy or sell advice."
    )

    def __init__(self):
        self.model = getattr(Config, 'ANTHROPIC_MODEL', 'claude-opus-4-8')
        api_key = getattr(Config, 'ANTHROPIC_API_KEY', '') or ''
        self.client = None
        if _ANTHROPIC_AVAILABLE and api_key:
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
                logger.info("✓ Claude analyzer ready (model=%s)", self.model)
            except Exception as e:
                logger.warning("Could not initialize Anthropic client: %s", e)
        elif not _ANTHROPIC_AVAILABLE:
            logger.info("Claude analyzer idle: anthropic package not installed (local LLM will be used)")
        else:
            logger.info("Claude analyzer idle: ANTHROPIC_API_KEY not set (local LLM will be used)")

    def available(self) -> bool:
        return self.client is not None

    @staticmethod
    def format_facts(d: dict, account_label: str = "this account") -> str:
        """Turn the diversification metrics dict into a compact fact sheet for the model."""
        se = d.get("sector_exposure", {}) or {}
        sectors = ", ".join(
            f"{k} {v}%" for k, v in (se.get("sectors") or {}).items() if v and v > 0
        )
        lp = d.get("largest_position", {}) or {}
        return (
            f"Account: {account_label}\n"
            f"Positions analyzed: {d.get('position_count')}\n"
            f"Diversification score: {d.get('diversification_score')}/100 (higher = more diversified; "
            f"factors in both correlation and concentration)\n"
            f"Weighted avg pairwise correlation: {d.get('weighted_avg_correlation')} "
            f"(0 = move independently, 1 = move together)\n"
            f"Concentration score (Herfindahl x100): {d.get('concentration_score')}\n"
            f"Largest position: {lp.get('symbol')} at {lp.get('weight')}% of the account\n"
            f"Top-3 positions combined weight: {d.get('top3_weight')}%\n"
            f"Overall risk level: {d.get('risk_level')}\n"
            f"Sector exposure: {sectors or 'unavailable'}\n"
        )

    def read(self, system: str, facts: str) -> str | None:
        """One-shot Claude call. Returns the read text, or None on any failure (caller falls back)."""
        if not self.client:
            return None
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": facts}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return text or None
        except Exception as e:
            logger.warning("Claude read failed (%s); caller should fall back to local LLM", e)
            return None
