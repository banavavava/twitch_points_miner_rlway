import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AIAnalyzerSettings:
    api_key: str = ""
    model: str = "claude-haiku-4-5-20251001"
    min_confidence: float = 0.3
    use_web_search: bool = True
    cache_ttl_seconds: int = 300
    language: str = "ru"
    timeout: int = 20


@dataclass
class AIAnalysisResult:
    confidence: float
    preferred_outcome: int
    reasoning: str
    used_search: bool = False
    cached: bool = False

    def should_skip(self, min_confidence: float) -> bool:
        return self.confidence < min_confidence


class _AnalysisCache:
    def __init__(self):
        self._store: dict[str, tuple[AIAnalysisResult, float]] = {}

    @staticmethod
    def _key(
        outcomes: list[str],
        streamer: str,
        game: str,
        prediction_title: str,
    ) -> str:
        payload = json.dumps(
            {
                "outcomes": outcomes,
                "streamer": streamer,
                "game": game,
                "prediction_title": prediction_title,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def get(
        self,
        outcomes: list[str],
        streamer: str,
        game: str,
        prediction_title: str,
        ttl: int,
    ) -> Optional[AIAnalysisResult]:
        key = self._key(outcomes, streamer, game, prediction_title)
        if key in self._store:
            result, ts = self._store[key]
            if time.time() - ts < ttl:
                result.cached = True
                return result
        return None

    def set(
        self,
        outcomes: list[str],
        streamer: str,
        game: str,
        prediction_title: str,
        result: AIAnalysisResult,
    ):
        key = self._key(outcomes, streamer, game, prediction_title)
        self._store[key] = (result, time.time())


_cache = _AnalysisCache()


_SYSTEM_RU = """Ты аналитик Twitch-ставок.
Твоя задача: по названию предсказания, имени стримера, текущей игре и вариантам исходов выбрать наиболее вероятный исход и оценить уверенность.

Что нужно учитывать:
- Если известны имя стримера и текущая игра, оцени, насколько стример силен именно в этой игре или режиме.
- Если варианты исхода связаны с матчем, раундом, командой, рейтингом, картой, стриком, челленджем или статистикой, используй это.
- Если доступен веб-поиск, ищи актуальную информацию о форме стримера, результатах, рейтинге, матчапе и текущей игре.
- Если исход зависит в основном от случайности, фана, настроения стримера или троллинга чата, уверенность должна быть низкой.
- Выбери один preferred_outcome_index из списка вариантов и коротко объясни decision.

Отвечай ТОЛЬКО валидным JSON без лишнего текста:
{"confidence": 0.75, "preferred_outcome_index": 0, "reasoning": "кратко почему выбран этот исход"}
"""

_SYSTEM_EN = """You are a Twitch prediction betting analyst.
Your task is to use the prediction title, streamer name, current game, and outcome options to pick the most likely outcome and estimate confidence.

What to consider:
- If streamer name and current game are known, assess how strong the streamer is in that specific game or mode.
- If outcomes refer to a match, round, team, map, streak, challenge, or measurable stat, use that.
- If web search is available, use current information about form, results, ranking, matchup, and current game.
- If outcomes mainly depend on randomness, entertainment, chat trolling, or streamer mood, confidence should be low.
- Pick one preferred_outcome_index from the listed options and briefly explain the decision.

Reply ONLY with valid JSON and no extra text:
{"confidence": 0.75, "preferred_outcome_index": 0, "reasoning": "brief reason for the chosen outcome"}
"""


class AIBetAnalyzer:
    def __init__(self, settings: AIAnalyzerSettings):
        self.settings = settings
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.settings.api_key)
            logger.info("[AIBetAnalyzer] Anthropic client initialized")
        except ImportError:
            logger.error("[AIBetAnalyzer] Install dependency: pip install anthropic")
        except Exception as exc:
            logger.error(f"[AIBetAnalyzer] Initialization error: {exc}")

    def analyze(
        self,
        outcome_titles: list[str],
        streamer: str = "",
        game: str = "",
        prediction_title: str = "",
    ) -> Optional[AIAnalysisResult]:
        if not self._client:
            return None

        cached = _cache.get(
            outcome_titles,
            streamer,
            game,
            prediction_title,
            self.settings.cache_ttl_seconds,
        )
        if cached:
            logger.info(
                f"[AIBetAnalyzer] cache hit confidence={cached.confidence:.2f} "
                f"decision={cached.preferred_outcome}"
            )
            return cached

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._call_api,
                    outcome_titles,
                    streamer,
                    game,
                    prediction_title,
                )
                result = future.result(timeout=self.settings.timeout)
            if result:
                _cache.set(outcome_titles, streamer, game, prediction_title, result)
            return result
        except TimeoutError:
            logger.warning(
                f"[AIBetAnalyzer] Analysis timed out after {self.settings.timeout}s"
            )
            return None
        except Exception as exc:
            logger.warning(f"[AIBetAnalyzer] Analysis error: {exc}")
            return None

    def _build_prompt(
        self,
        outcome_titles: list[str],
        streamer: str,
        game: str,
        prediction_title: str,
    ) -> str:
        parts = []
        if prediction_title:
            parts.append(f"Prediction title: {prediction_title}")
        if streamer:
            parts.append(f"Streamer: {streamer}")
        if game:
            parts.append(f"Current game: {game}")

        outcomes = "\n".join(
            f"[{index}] {title}" for index, title in enumerate(outcome_titles)
        )
        parts.append(f"Outcome options:\n{outcomes}")
        parts.append(
            "Evaluate the streamer in the current game if relevant, compare all outcome options, "
            "then return the best decision as preferred_outcome_index."
        )

        if self.settings.use_web_search:
            parts.append(
                "Use web search when the prediction depends on real current performance, statistics, rankings, or matchup context."
            )

        return "\n".join(parts)

    def _call_api(
        self,
        outcome_titles: list[str],
        streamer: str,
        game: str,
        prediction_title: str,
    ) -> Optional[AIAnalysisResult]:
        system = _SYSTEM_RU if self.settings.language == "ru" else _SYSTEM_EN
        user_msg = self._build_prompt(outcome_titles, streamer, game, prediction_title)

        kwargs = {
            "model": self.settings.model,
            "max_tokens": 500,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        }
        if self.settings.use_web_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

        response = self._client.messages.create(**kwargs)

        text = ""
        used_search = False
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text += block.text
            elif (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == "web_search"
            ):
                used_search = True

        text = text.strip()
        if "```" in text:
            chunks = text.split("```")
            if len(chunks) > 1:
                text = chunks[1].replace("json", "", 1).strip()

        data = json.loads(text)
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        preferred = int(data.get("preferred_outcome_index", 0))
        preferred = max(0, min(preferred, len(outcome_titles) - 1))
        reasoning = str(data.get("reasoning", "")).strip()

        result = AIAnalysisResult(
            confidence=confidence,
            preferred_outcome=preferred,
            reasoning=reasoning,
            used_search=used_search,
        )
        logger.info(
            f"[AIBetAnalyzer] confidence={confidence:.2f} | decision=[{preferred}] "
            f"{outcome_titles[preferred]} | {'search' if used_search else 'no-search'} | "
            f"{reasoning[:100]}"
        )
        return result
