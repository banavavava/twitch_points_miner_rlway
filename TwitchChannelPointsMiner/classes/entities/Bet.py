import copy
from enum import Enum, auto
from random import uniform

from millify import millify

from TwitchChannelPointsMiner.utils import float_round


class Strategy(Enum):
    MOST_VOTED = auto()
    HIGH_ODDS = auto()
    PERCENTAGE = auto()
    SMART_MONEY = auto()
    SMART = auto()
    NUMBER_1 = auto()
    NUMBER_2 = auto()
    NUMBER_3 = auto()
    NUMBER_4 = auto()
    NUMBER_5 = auto()
    NUMBER_6 = auto()
    NUMBER_7 = auto()
    NUMBER_8 = auto()

    def __str__(self):
        return self.name


class Condition(Enum):
    GT = auto()
    LT = auto()
    GTE = auto()
    LTE = auto()

    def __str__(self):
        return self.name


class OutcomeKeys(object):
    PERCENTAGE_USERS = "percentage_users"
    ODDS_PERCENTAGE = "odds_percentage"
    ODDS = "odds"
    TOP_POINTS = "top_points"
    TOTAL_USERS = "total_users"
    TOTAL_POINTS = "total_points"
    DECISION_USERS = "decision_users"
    DECISION_POINTS = "decision_points"
    USERS_GAP = "users_gap"
    USERS_GAP_PERCENTAGE = "users_gap_percentage"
    POINTS_GAP = "points_gap"
    POINTS_GAP_PERCENTAGE = "points_gap_percentage"
    CONFIDENCE = "confidence"


class DelayMode(Enum):
    FROM_START = auto()
    FROM_END = auto()
    PERCENTAGE = auto()

    def __str__(self):
        return self.name


class FilterCondition(object):
    __slots__ = [
        "by",
        "where",
        "value",
    ]

    def __init__(self, by=None, where=None, value=None, decision=None):
        self.by = by
        self.where = where
        self.value = value

    def __repr__(self):
        return f"FilterCondition(by={self.by.upper()}, where={self.where}, value={self.value})"


class BetSettings(object):
    __slots__ = [
        "strategy",
        "percentage",
        "percentage_gap",
        "max_points",
        "minimum_points",
        "stealth_mode",
        "filter_condition",
        "delay",
        "delay_mode",
        "uncertain_percentage",
        "uncertain_odds_min",
        "uncertain_odds_max",
        "uncertain_max_points",
        "ai_analyzer",
        "ai_streamer_name",
        "ai_game_name",
        "ai_min_stake_factor",
    ]

    def __init__(
        self,
        strategy: Strategy = None,
        percentage: int = None,
        percentage_gap: int = None,
        max_points: int = None,
        minimum_points: int = None,
        stealth_mode: bool = None,
        filter_condition: FilterCondition = None,
        delay: float = None,
        delay_mode: DelayMode = None,
        uncertain_percentage: float = None,
        uncertain_odds_min: float = 45.0,
        uncertain_odds_max: float = 55.0,
        uncertain_max_points: int = 5000,
        ai_analyzer=None,
        ai_streamer_name: str = "",
        ai_game_name: str = "",
        ai_min_stake_factor: float = 0.55,
    ):
        self.strategy = strategy
        self.percentage = percentage
        self.percentage_gap = percentage_gap
        self.max_points = max_points
        self.minimum_points = minimum_points
        self.stealth_mode = stealth_mode
        self.filter_condition = filter_condition
        self.delay = delay
        self.delay_mode = delay_mode
        self.uncertain_percentage = uncertain_percentage
        self.uncertain_odds_min = uncertain_odds_min
        self.uncertain_odds_max = uncertain_odds_max
        self.uncertain_max_points = uncertain_max_points
        self.ai_analyzer = ai_analyzer
        self.ai_streamer_name = ai_streamer_name
        self.ai_game_name = ai_game_name
        self.ai_min_stake_factor = ai_min_stake_factor

    def default(self):
        self.strategy = self.strategy if self.strategy is not None else Strategy.SMART
        self.percentage = self.percentage if self.percentage is not None else 5
        self.percentage_gap = (
            self.percentage_gap if self.percentage_gap is not None else 20
        )
        self.max_points = self.max_points if self.max_points is not None else 50000
        self.minimum_points = (
            self.minimum_points if self.minimum_points is not None else 0
        )
        self.stealth_mode = (
            self.stealth_mode if self.stealth_mode is not None else False
        )
        self.delay = self.delay if self.delay is not None else 6
        self.delay_mode = (
            self.delay_mode if self.delay_mode is not None else DelayMode.FROM_END
        )

    def __repr__(self):
        return (
            f"BetSettings(strategy={self.strategy}, percentage={self.percentage}, "
            f"percentage_gap={self.percentage_gap}, max_points={self.max_points}, "
            f"minimum_points={self.minimum_points}, stealth_mode={self.stealth_mode}, "
            f"uncertain_percentage={self.uncertain_percentage}, "
            f"uncertain_odds=[{self.uncertain_odds_min}-{self.uncertain_odds_max}%], "
            f"ai_analyzer={'on' if self.ai_analyzer else 'off'})"
        )

    def get_ai_delay_seconds(self, can_use_ai: bool = True) -> float:
        if can_use_ai is not True or self.ai_analyzer is None:
            return 0
        try:
            return float(getattr(self.ai_analyzer.settings, "timeout", 0) or 0)
        except Exception:
            return 0


class Bet(object):
    __slots__ = [
        "outcomes",
        "decision",
        "total_users",
        "total_points",
        "settings",
        "_ai_result",
        "_decision_explanation",
        "_confidence",
        "_confidence_details",
    ]

    def __init__(self, outcomes: list, settings: BetSettings):
        self.outcomes = outcomes
        self.__clear_outcomes()
        self.decision: dict = {}
        self.total_users = 0
        self.total_points = 0
        self.settings = settings
        self._ai_result = None
        self._decision_explanation = ""
        self._confidence = 0.0
        self._confidence_details = {}

    def update_outcomes(self, outcomes):
        for index in range(0, len(self.outcomes)):
            self.outcomes[index][OutcomeKeys.TOTAL_USERS] = int(
                outcomes[index][OutcomeKeys.TOTAL_USERS]
            )
            self.outcomes[index][OutcomeKeys.TOTAL_POINTS] = int(
                outcomes[index][OutcomeKeys.TOTAL_POINTS]
            )
            if outcomes[index]["top_predictors"] != []:
                outcomes[index]["top_predictors"] = sorted(
                    outcomes[index]["top_predictors"],
                    key=lambda x: x["points"],
                    reverse=True,
                )
                top_points = outcomes[index]["top_predictors"][0]["points"]
                self.outcomes[index][OutcomeKeys.TOP_POINTS] = top_points

        self.total_points = 0
        self.total_users = 0
        for index in range(0, len(self.outcomes)):
            self.total_users += self.outcomes[index][OutcomeKeys.TOTAL_USERS]
            self.total_points += self.outcomes[index][OutcomeKeys.TOTAL_POINTS]

        if self.total_users > 0 and self.total_points > 0:
            for index in range(0, len(self.outcomes)):
                self.outcomes[index][OutcomeKeys.PERCENTAGE_USERS] = float_round(
                    (100 * self.outcomes[index][OutcomeKeys.TOTAL_USERS]) / self.total_users
                )
                self.outcomes[index][OutcomeKeys.ODDS] = float_round(
                    0
                    if self.outcomes[index][OutcomeKeys.TOTAL_POINTS] == 0
                    else self.total_points / self.outcomes[index][OutcomeKeys.TOTAL_POINTS]
                )
                self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE] = float_round(
                    0
                    if self.outcomes[index][OutcomeKeys.ODDS] == 0
                    else 100 / self.outcomes[index][OutcomeKeys.ODDS]
                )

        self.__clear_outcomes()

    def __repr__(self):
        return (
            f"Bet(total_users={millify(self.total_users)}, "
            f"total_points={millify(self.total_points)}), decision={self.decision})\n"
            f"\t\tOutcome A({self.get_outcome(0)})\n\t\tOutcome B({self.get_outcome(1)})"
        )

    def get_decision(self, parsed=False):
        decision = self.outcomes[self.decision["choice"]]
        return decision if parsed is False else Bet.__parse_outcome(decision)

    @staticmethod
    def __parse_outcome(outcome):
        return (
            f"{outcome['title']} ({outcome['color']}), "
            f"Points: {millify(outcome[OutcomeKeys.TOTAL_POINTS])}, "
            f"Users: {millify(outcome[OutcomeKeys.TOTAL_USERS])} ({outcome[OutcomeKeys.PERCENTAGE_USERS]}%), "
            f"Odds: {outcome[OutcomeKeys.ODDS]} ({outcome[OutcomeKeys.ODDS_PERCENTAGE]}%)"
        )

    def get_outcome(self, index):
        return Bet.__parse_outcome(self.outcomes[index])

    def __clear_outcomes(self):
        for index in range(0, len(self.outcomes)):
            keys = copy.deepcopy(list(self.outcomes[index].keys()))
            for key in keys:
                if key not in [
                    OutcomeKeys.TOTAL_USERS,
                    OutcomeKeys.TOTAL_POINTS,
                    OutcomeKeys.TOP_POINTS,
                    OutcomeKeys.PERCENTAGE_USERS,
                    OutcomeKeys.ODDS,
                    OutcomeKeys.ODDS_PERCENTAGE,
                    "title",
                    "color",
                    "id",
                ]:
                    del self.outcomes[index][key]
            for key in [
                OutcomeKeys.PERCENTAGE_USERS,
                OutcomeKeys.ODDS,
                OutcomeKeys.ODDS_PERCENTAGE,
                OutcomeKeys.TOP_POINTS,
            ]:
                if key not in self.outcomes[index]:
                    self.outcomes[index][key] = 0

    def __return_choice(self, key) -> int:
        largest = 0
        for index in range(0, len(self.outcomes)):
            if self.outcomes[index][key] > self.outcomes[largest][key]:
                largest = index
        return largest

    def __return_number_choice(self, number) -> int:
        if len(self.outcomes) > number:
            return number
        else:
            return 0

    def __get_filter_conditions(self):
        filter_condition = self.settings.filter_condition
        if filter_condition is None:
            return []
        if isinstance(filter_condition, list):
            return filter_condition
        return [filter_condition]

    def __get_gap_value(self, first, second):
        return abs(first - second)

    def __get_gap_percentage(self, first, second):
        total = first + second
        return float_round(0 if total == 0 else (100 * abs(first - second)) / total)

    def __get_confidence(self):
        return self._confidence

    def __get_compared_value(self, key):
        fixed_key = (
            key
            if key not in [OutcomeKeys.DECISION_USERS, OutcomeKeys.DECISION_POINTS]
            else key.replace("decision", "total")
        )
        if key in [OutcomeKeys.TOTAL_USERS, OutcomeKeys.TOTAL_POINTS]:
            return sum(outcome[fixed_key] for outcome in self.outcomes)

        if key == OutcomeKeys.USERS_GAP:
            if len(self.outcomes) < 2:
                return 0
            return self.__get_gap_value(
                self.outcomes[0][OutcomeKeys.TOTAL_USERS],
                self.outcomes[1][OutcomeKeys.TOTAL_USERS],
            )

        if key == OutcomeKeys.USERS_GAP_PERCENTAGE:
            if len(self.outcomes) < 2:
                return 0
            return self.__get_gap_percentage(
                self.outcomes[0][OutcomeKeys.TOTAL_USERS],
                self.outcomes[1][OutcomeKeys.TOTAL_USERS],
            )

        if key == OutcomeKeys.POINTS_GAP:
            if len(self.outcomes) < 2:
                return 0
            return self.__get_gap_value(
                self.outcomes[0][OutcomeKeys.TOTAL_POINTS],
                self.outcomes[1][OutcomeKeys.TOTAL_POINTS],
            )

        if key == OutcomeKeys.POINTS_GAP_PERCENTAGE:
            if len(self.outcomes) < 2:
                return 0
            return self.__get_gap_percentage(
                self.outcomes[0][OutcomeKeys.TOTAL_POINTS],
                self.outcomes[1][OutcomeKeys.TOTAL_POINTS],
            )

        if key == OutcomeKeys.CONFIDENCE:
            return self.__get_confidence()

        outcome_index = self.decision["choice"]
        return self.outcomes[outcome_index][fixed_key]

    @staticmethod
    def __condition_matches(condition, compared_value, value):
        if condition == Condition.GT:
            return compared_value > value
        if condition == Condition.LT:
            return compared_value < value
        if condition == Condition.GTE:
            return compared_value >= value
        if condition == Condition.LTE:
            return compared_value <= value
        return False

    def __is_uncertain_odds(self, odds_pct: float) -> bool:
        return (
            self.settings.uncertain_percentage is not None
            and self.settings.uncertain_percentage > 0
            and self.settings.uncertain_odds_min <= odds_pct <= self.settings.uncertain_odds_max
        )

    def skip(self) -> bool:
        filter_conditions = self.__get_filter_conditions()
        if filter_conditions:
            compared_values = []
            for filter_condition in filter_conditions:
                key = filter_condition.by
                condition = filter_condition.where
                value = filter_condition.value
                compared_value = self.__get_compared_value(key)
                compared_values.append(
                    {
                        "by": key,
                        "where": str(condition),
                        "value": value,
                        "compared_value": compared_value,
                    }
                )

                if not self.__condition_matches(condition, compared_value, value):
                    if key == OutcomeKeys.ODDS_PERCENTAGE and self.__is_uncertain_odds(
                        compared_value
                    ):
                        continue
                    return True, compared_values

            return False, compared_values
        else:
            return False, 0

    def __calculate_confidence(self, choice_index: int):
        if choice_index is None or len(self.outcomes) < 2:
            self._confidence = 0.0
            self._confidence_details = {}
            return self._confidence

        selected = self.outcomes[choice_index]
        opponent = self.outcomes[1 - choice_index]

        users_gap_pct = self.__get_gap_percentage(
            selected[OutcomeKeys.TOTAL_USERS],
            opponent[OutcomeKeys.TOTAL_USERS],
        )
        points_gap_pct = self.__get_gap_percentage(
            selected[OutcomeKeys.TOTAL_POINTS],
            opponent[OutcomeKeys.TOTAL_POINTS],
        )
        odds_edge = max(
            0.0,
            float_round(
                selected[OutcomeKeys.ODDS_PERCENTAGE] - opponent[OutcomeKeys.ODDS_PERCENTAGE]
            ),
        )

        confidence = float_round(
            (users_gap_pct * 0.45) + (points_gap_pct * 0.35) + (odds_edge * 0.20)
        )

        self._confidence = confidence
        self._confidence_details = {
            "users_gap_percentage": users_gap_pct,
            "points_gap_percentage": points_gap_pct,
            "odds_edge": odds_edge,
        }
        return self._confidence

    def get_decision_explanation(self) -> str:
        return self._decision_explanation

    def analyze_with_ai(
        self,
        prediction_title="",
        streamer_name="",
        game_name="",
        stream_title="",
        can_use_ai: bool = True,
    ):
        self._ai_result = None

        if can_use_ai is not True or self.settings.ai_analyzer is None:
            return None

        outcome_details = []
        outcome_titles = []
        for index, outcome in enumerate(self.outcomes):
            outcome_details.append(
                {
                    "i": index,
                    "title": outcome.get("title", f"Outcome {index}"),
                    "percentage_users": outcome.get(OutcomeKeys.PERCENTAGE_USERS, 0),
                    "total_points": outcome.get(OutcomeKeys.TOTAL_POINTS, 0),
                    "odds": outcome.get(OutcomeKeys.ODDS, 0),
                    "odds_percentage": outcome.get(OutcomeKeys.ODDS_PERCENTAGE, 0),
                    "top_points": outcome.get(OutcomeKeys.TOP_POINTS, 0),
                }
            )
            outcome_titles.append(outcome_details[-1]["title"])

        try:
            self._ai_result = self.settings.ai_analyzer.analyze(
                outcome_details=outcome_details,
                outcome_titles=outcome_titles,
                streamer=self.settings.ai_streamer_name or streamer_name,
                game=self.settings.ai_game_name or game_name,
                prediction_title=prediction_title,
                stream_title=stream_title,
            )
        except Exception as exc:
            self._ai_result = None
            self._decision_explanation = f"AI analysis unavailable: {exc}"

        return self._ai_result

    def calculate(self, balance: int) -> dict:
        self.decision = {"choice": None, "amount": 0, "id": None}
        self._decision_explanation = ""
        self._confidence = 0.0
        self._confidence_details = {}

        if self._ai_result is not None:
            min_confidence = float(
                getattr(getattr(self.settings.ai_analyzer, "settings", None), "min_confidence", 0)
                or 0
            )
            reasoning = getattr(self._ai_result, "reasoning", "")
            ai_confidence = float_round(float(getattr(self._ai_result, "confidence", 0.0)) * 100)

            if self._ai_result.should_skip(min_confidence):
                self._decision_explanation = (
                    f"AI skipped this market: confidence {ai_confidence}% below minimum "
                    f"{float_round(min_confidence * 100)}%."
                    + (f" Reasoning: {reasoning}" if reasoning else "")
                )
                return self.decision

            preferred_outcome = int(getattr(self._ai_result, "preferred_outcome", 0))
            if 0 <= preferred_outcome < len(self.outcomes):
                self.decision["choice"] = preferred_outcome

        if self.decision["choice"] is None and self.settings.strategy == Strategy.MOST_VOTED:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.TOTAL_USERS)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.HIGH_ODDS:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.PERCENTAGE:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS_PERCENTAGE)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.SMART_MONEY:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.TOP_POINTS)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_1:
            self.decision["choice"] = self.__return_number_choice(0)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_2:
            self.decision["choice"] = self.__return_number_choice(1)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_3:
            self.decision["choice"] = self.__return_number_choice(2)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_4:
            self.decision["choice"] = self.__return_number_choice(3)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_5:
            self.decision["choice"] = self.__return_number_choice(4)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_6:
            self.decision["choice"] = self.__return_number_choice(5)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_7:
            self.decision["choice"] = self.__return_number_choice(6)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.NUMBER_8:
            self.decision["choice"] = self.__return_number_choice(7)
        elif self.decision["choice"] is None and self.settings.strategy == Strategy.SMART:
            difference = abs(
                self.outcomes[0][OutcomeKeys.PERCENTAGE_USERS]
                - self.outcomes[1][OutcomeKeys.PERCENTAGE_USERS]
            )
            self.decision["choice"] = (
                self.__return_choice(OutcomeKeys.ODDS)
                if difference < self.settings.percentage_gap
                else self.__return_choice(OutcomeKeys.TOTAL_USERS)
            )

        if self.decision["choice"] is not None:
            index = self.decision["choice"]
            self.decision["id"] = self.outcomes[index]["id"]
            confidence = self.__calculate_confidence(index)

            odds_pct = self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE]

            amount_reasons = []
            base_amount = 0

            if self.__is_uncertain_odds(odds_pct):
                confidence_multiplier = (
                    0.8
                    if confidence < 10
                    else 1.0
                    if confidence < 17
                    else 1.3
                    if confidence < 24
                    else 1.6
                )
                aggressive_uncertain_pct = self.settings.uncertain_percentage * confidence_multiplier
                raw_amount = int(balance * (aggressive_uncertain_pct / 100))
                base_amount = min(raw_amount, self.settings.uncertain_max_points)
                self.decision["amount"] = base_amount
                amount_reasons.append(
                    f"uncertain odds zone {odds_pct}% -> adaptive aggressive mode {float_round(aggressive_uncertain_pct)}% of balance from base uncertain {self.settings.uncertain_percentage}%"
                )
                amount_reasons.append(
                    f"confidence multiplier x{float_round(confidence_multiplier)} from confidence={confidence}%"
                )
                if base_amount != raw_amount:
                    amount_reasons.append(
                        f"capped by uncertain_max_points={self.settings.uncertain_max_points:,}"
                    )
            else:
                confidence_multiplier = (
                    0.75
                    if confidence < 8
                    else 1.0
                    if confidence < 14
                    else 1.2
                    if confidence < 20
                    else 1.45
                    if confidence < 28
                    else 1.75
                )
                aggressive_pct = self.settings.percentage * confidence_multiplier
                raw_amount = int(balance * (aggressive_pct / 100))
                base_amount = min(raw_amount, self.settings.max_points)
                self.decision["amount"] = base_amount
                amount_reasons.append(
                    f"base stake scaled by confidence: {self.settings.percentage}% -> {float_round(aggressive_pct)}% of balance {balance:,} -> {raw_amount:,}"
                )
                amount_reasons.append(
                    f"confidence multiplier x{float_round(confidence_multiplier)} from confidence={confidence}%"
                )
                if base_amount != raw_amount:
                    amount_reasons.append(
                        f"capped by max_points={self.settings.max_points:,}"
                    )

            if confidence < 6:
                self.decision["amount"] = min(self.decision["amount"], 20)
                amount_reasons.append(
                    "very low confidence safety clamp applied"
                )
            elif confidence < 10:
                self.decision["amount"] = int(self.decision["amount"] * 0.5)
                amount_reasons.append(
                    "low confidence stake cut by 50%"
                )
            elif confidence >= 25:
                boosted_amount = int(self.decision["amount"] * 1.15)
                max_cap = (
                    self.settings.uncertain_max_points
                    if self.__is_uncertain_odds(odds_pct)
                    else self.settings.max_points
                )
                self.decision["amount"] = min(boosted_amount, max_cap)
                amount_reasons.append(
                    "elite confidence bonus +15%"
                )

            if (
                self.settings.stealth_mode is True
                and self.decision["amount"] >= self.outcomes[index][OutcomeKeys.TOP_POINTS]
            ):
                original_amount = self.decision["amount"]
                reduce_amount = uniform(1, 5)
                self.decision["amount"] = (
                    self.outcomes[index][OutcomeKeys.TOP_POINTS] - reduce_amount
                )
                amount_reasons.append(
                    f"stealth mode trims stake {int(original_amount):,} -> {int(self.decision['amount']):,} to stay below top predictor"
                )

            self.decision["amount"] = int(self.decision["amount"])

            selected_outcome = self.outcomes[index]
            market_summary = (
                f"picked '{selected_outcome['title']}' with market "
                f"{selected_outcome[OutcomeKeys.TOTAL_POINTS]:,} points, "
                f"{selected_outcome[OutcomeKeys.TOTAL_USERS]:,} users, "
                f"odds {selected_outcome[OutcomeKeys.ODDS]}"
            )
            strategy_summary = f"selection source: {self.settings.strategy}"
            confidence_summary = (
                f"confidence {confidence}% "
                f"(users gap {self._confidence_details['users_gap_percentage']}%, "
                f"points gap {self._confidence_details['points_gap_percentage']}%, "
                f"odds edge {self._confidence_details['odds_edge']}%)"
            )
            explanation = (
                f"{strategy_summary}. {market_summary}. {confidence_summary}. "
                f"Stake sizing: {'; '.join(amount_reasons)}."
            )
            if self._ai_result is not None:
                ai_reasoning = getattr(self._ai_result, "reasoning", "")
                ai_confidence = float_round(float(getattr(self._ai_result, "confidence", 0.0)) * 100)
                ai_summary = (
                    f"AI preference: outcome {getattr(self._ai_result, 'preferred_outcome', index)} "
                    f"at {ai_confidence}% confidence"
                )
                if ai_reasoning:
                    ai_summary += f" ({ai_reasoning})"
                explanation = f"{ai_summary}. {explanation}"
            self._decision_explanation = explanation

        return self.decision
