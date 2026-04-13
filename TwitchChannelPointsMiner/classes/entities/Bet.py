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
        if self.ai_analyzer is None or can_use_ai is False:
            return 0

        analyzer_settings = getattr(self.ai_analyzer, "settings", None)
        timeout = getattr(analyzer_settings, "timeout", 0)

        try:
            return max(float(timeout), 0)
        except (TypeError, ValueError):
            return 0


class Bet(object):
    __slots__ = [
        "outcomes",
        "decision",
        "total_users",
        "total_points",
        "settings",
        "_ai_result",
    ]

    def __init__(self, outcomes: list, settings: BetSettings):
        self.outcomes = outcomes
        self.__clear_outcomes()
        self.decision: dict = {}
        self.total_users = 0
        self.total_points = 0
        self.settings = settings
        self._ai_result = None

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

    def analyze_with_ai(
        self,
        prediction_title: str = "",
        streamer_name: str = "",
        game_name: str = "",
        can_use_ai: bool = True,
    ) -> bool:
        self._ai_result = None
        if self.settings.ai_analyzer is None or can_use_ai is False:
            return False

        outcome_titles = [
            outcome.get("title", f"Outcome {index}")
            for index, outcome in enumerate(self.outcomes)
        ]

        self._ai_result = self.settings.ai_analyzer.analyze(
            outcome_titles=outcome_titles,
            streamer=streamer_name or self.settings.ai_streamer_name,
            game=game_name or self.settings.ai_game_name,
            prediction_title=prediction_title,
        )
        return self._ai_result is not None

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

    def __get_compared_value(self, key):
        fixed_key = (
            key
            if key not in [OutcomeKeys.DECISION_USERS, OutcomeKeys.DECISION_POINTS]
            else key.replace("decision", "total")
        )
        if key in [OutcomeKeys.TOTAL_USERS, OutcomeKeys.TOTAL_POINTS]:
            return sum(outcome[fixed_key] for outcome in self.outcomes)

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

    def calculate(self, balance: int) -> dict:
        self.decision = {"choice": None, "amount": 0, "id": None}

        if self._ai_result is not None:
            ai_choice = self._ai_result.preferred_outcome
            if 0 <= ai_choice < len(self.outcomes):
                self.decision["choice"] = ai_choice
            else:
                self._ai_result = None

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

            odds_pct = self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE]

            if self.__is_uncertain_odds(odds_pct):
                raw_amount = int(balance * (self.settings.uncertain_percentage / 100))
                self.decision["amount"] = min(raw_amount, self.settings.uncertain_max_points)
            else:
                self.decision["amount"] = min(
                    int(balance * (self.settings.percentage / 100)),
                    self.settings.max_points,
                )

            if self._ai_result is not None:
                min_confidence = getattr(
                    getattr(self.settings.ai_analyzer, "settings", None),
                    "min_confidence",
                    None,
                )
                if (
                    min_confidence is not None
                    and self._ai_result.should_skip(min_confidence)
                ):
                    self.decision = {"choice": None, "amount": 0, "id": None}
                    return self.decision

                self.decision["amount"] = int(
                    self.decision["amount"] * self._ai_result.confidence
                )

            if (
                self.settings.stealth_mode is True
                and self.decision["amount"] >= self.outcomes[index][OutcomeKeys.TOP_POINTS]
            ):
                reduce_amount = uniform(1, 5)
                self.decision["amount"] = (
                    self.outcomes[index][OutcomeKeys.TOP_POINTS] - reduce_amount
                )

            self.decision["amount"] = int(self.decision["amount"])

        return self.decision
