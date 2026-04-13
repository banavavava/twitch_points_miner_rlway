import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

import httpx


@dataclass
class AIAnalyzerSettings:
    api_key: str
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 140
    min_confidence: float = 0.0
    timeout: float = 8.0
    web_lookup_enabled: bool = True
    web_lookup_max_results: int = 2
    web_lookup_max_chars: int = 320


@dataclass
class AIAnalysisResult:
    confidence: float
    preferred_outcome: int
    reasoning: str
    cached: bool = False

    def should_skip(self, min_confidence: float) -> bool:
        try:
            return float(self.confidence) < float(min_confidence)
        except (TypeError, ValueError):
            return False


class _Cache:
    def __init__(self):
        self.store = {}

    def key(self, *args):
        return hashlib.md5(
            json.dumps(args, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v):
        self.store[k] = v


_cache = _Cache()


SYSTEM_PROMPT = """
    Выбери самый вероятный исход Twitch prediction.

    Правила:
    - сравни все исходы;
    - сначала смотри на game, prediction_title, stream_title и streamer;
    - учитывай только релевантный опыт в этой конкретной игре;
    - web_context используй только если он короткий и по делу;
    - если данных о человеке нет, не выдумывай факты по имени;
    - crowd и odds полезны, но это вторичные сигналы;
    - reasoning очень коротко.

    Верни ТОЛЬКО JSON:
    {"confidence":0.0,"preferred_outcome_index":0,"reasoning":"short"}
"""


class AIBetAnalyzer:

    def __init__(self, settings: AIAnalyzerSettings):
        self.settings = settings
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.api_key)

    def _build_prompt(
        self,
        outcome_details,
        outcome_titles=None,
        streamer="",
        game="",
        prediction_title="",
        stream_title="",
    ):
        market = []
        for index, d in enumerate(outcome_details):
            market.append(
                {
                    "i": d.get("i", d.get("index", index)),
                    "t": d.get(
                        "title",
                        outcome_titles[index]
                        if outcome_titles and index < len(outcome_titles)
                        else f"Outcome {index}",
                    ),
                    "u": d.get("percentage_users"),
                    "p": d.get("total_points"),
                    "o": d.get("odds"),
                    "op": d.get("odds_percentage"),
                    "tp": d.get("top_points"),
                }
            )

        payload = {
            "streamer": streamer,
            "game": game,
            "prediction_title": prediction_title,
            "stream_title": stream_title,
            "web_context": self._lookup_web_context(streamer, game, prediction_title, stream_title),
            "outcomes": market,
        }

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _lookup_web_context(self, streamer="", game="", prediction_title="", stream_title=""):
        if not getattr(self.settings, "web_lookup_enabled", False):
            return ""

        names = []
        for source in [streamer, prediction_title, stream_title]:
            if not source:
                continue
            names.extend(re.findall(r"@[A-Za-z0-9_]+|[A-Za-z][A-Za-z0-9_]{2,}", source))

        seen = set()
        candidates = []
        for name in names:
            cleaned = name.lstrip("@")
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            candidates.append(cleaned)

        if not candidates:
            return ""

        snippets = []
        max_results = max(1, int(getattr(self.settings, "web_lookup_max_results", 2)))
        max_chars = max(120, int(getattr(self.settings, "web_lookup_max_chars", 320)))

        for name in candidates[:2]:
            query = quote_plus(f"{name} {game} streamer player")
            url = f"https://duckduckgo.com/html/?q={query}"
            try:
                response = httpx.get(
                    url,
                    timeout=getattr(self.settings, "timeout", 8.0),
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                text = re.sub(r"<[^>]+>", " ", response.text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    snippets.append(f"{name}: {text[:max_chars]}")
            except Exception:
                continue

            if len(snippets) >= max_results:
                break

        return " | ".join(snippets)[:max_chars]

    # =========================
    # PARSER (ROBUST)
    # =========================
    def _parse(self, text: str) -> Optional[dict]:

        if not text:
            return None

        text = text.strip().replace("```json", "").replace("```", "")

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            start = text.index("{")
            end = text.rindex("}")
            return json.loads(text[start:end + 1])
        except Exception:
            pass

        confidence_match = re.search(r'"?confidence"?\s*[:=]\s*([0-9]*\.?[0-9]+)', text)
        preferred_match = re.search(
            r'"?(preferred_outcome_index|preferred_outcome|index|choice)"?\s*[:=]\s*(-?\d+)',
            text,
        )
        reasoning_match = re.search(r'"?reasoning"?\s*[:=]\s*"([^"]+)"', text)

        if confidence_match and preferred_match:
            confidence = float(confidence_match.group(1))
            confidence = max(0.0, min(confidence, 1.0))
            preferred = int(preferred_match.group(2))
            reasoning = (
                reasoning_match.group(1)
                if reasoning_match
                else text[:160].replace("\n", " ").strip()
            )
            return {
                "confidence": confidence,
                "preferred_outcome_index": preferred,
                "reasoning": reasoning,
            }

        return None

    # =========================
    # CALL
    # =========================
    def _call(self, messages):
        resp = self.client.messages.create(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )

    # =========================
    # FALLBACK
    # =========================
    def _fallback(self, outcome_details):

        best = min(
            outcome_details,
            key=lambda x: x.get("percentage_users", 0)
        )

        return AIAnalysisResult(
            confidence=0.45,
            preferred_outcome=best.get("i", best.get("index", 0)),
            reasoning="fallback: crowd heuristic",
            cached=False
        )

    # =========================
    # MAIN
    # =========================
    def analyze(
        self,
        outcome_details,
        outcome_titles=None,
        streamer="",
        game="",
        prediction_title="",
        stream_title="",
        title="",
    ):
        effective_prediction_title = prediction_title or title

        key = _cache.key(
            outcome_details,
            outcome_titles,
            streamer,
            game,
            effective_prediction_title,
            stream_title,
        )

        cached = _cache.get(key)
        if cached:
            cached["cached"] = True
            return AIAnalysisResult(**cached)

        prompt = self._build_prompt(
            outcome_details=outcome_details,
            outcome_titles=outcome_titles,
            streamer=streamer,
            game=game,
            prediction_title=effective_prediction_title,
            stream_title=stream_title,
        )

        raw = self._call([{"role": "user", "content": prompt}])
        data = self._parse(raw)

        if not data:
            logging.warning("AIBetAnalyzer parse failed, raw response: %r", raw)
            repair_prompt = (
                "Convert this analysis to strict JSON only with keys "
                'confidence, preferred_outcome_index, reasoning. '
                "If the text already implies a choice, preserve it.\n\n"
                f"analysis:\n{raw}"
            )
            repaired_raw = self._call([{"role": "user", "content": repair_prompt}])
            data = self._parse(repaired_raw)

        if not data:
            return self._fallback(outcome_details)

        confidence = float(data.get("confidence", 0.5))
        preferred = int(data.get("preferred_outcome_index", 0))
        reasoning = str(data.get("reasoning", "")).replace("\n", " ").strip()

        if reasoning.startswith("{") and '"reasoning"' in reasoning:
            nested = self._parse(reasoning)
            if nested:
                reasoning = str(nested.get("reasoning", "")).replace("\n", " ").strip()

        valid = {
            o.get("i", o.get("index", index))
            for index, o in enumerate(outcome_details)
        }

        if preferred not in valid:
            preferred = min(valid)

        result = {
            "confidence": confidence,
            "preferred_outcome": preferred,
            "reasoning": reasoning,
            "cached": False
        }

        _cache.set(key, result)

        return AIAnalysisResult(**result)
