import copy
from enum import Enum, auto
from random import uniform

from millify import millify

#from TwitchChannelPointsMiner.utils import char_decision_as_index, float_round
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
    # Real key on Bet dict ['']
    PERCENTAGE_USERS = "percentage_users"
    ODDS_PERCENTAGE = "odds_percentage"
    ODDS = "odds"
    TOP_POINTS = "top_points"
    # Real key on Bet dict [''] - Sum()
    TOTAL_USERS = "total_users"
    TOTAL_POINTS = "total_points"
    # This key does not exist
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
        uncertain_odds_min: float = 41.0,
        uncertain_odds_max: float = 59.0,
        uncertain_max_points: int = 5000,
    ):
        self.strategy = strategy
        self.percentage = percentage
        self.percentage_gap = percentage_gap
        self.max_points = max_points
        self.minimum_points = minimum_points
        self.stealth_mode = stealth_mode
        self.filter_condition = self.__normalize_filter_condition(filter_condition)
        self.delay = delay
        self.delay_mode = delay_mode
        self.uncertain_percentage = uncertain_percentage
        self.uncertain_odds_min = uncertain_odds_min
        self.uncertain_odds_max = uncertain_odds_max
        self.uncertain_max_points = uncertain_max_points

    @staticmethod
    def __normalize_filter_condition(filter_condition):
        if isinstance(filter_condition, (list, tuple)):
            normalized_conditions = [condition for condition in filter_condition if condition is not None]
            if len(normalized_conditions) == 0:
                return None
            return normalized_conditions
        return filter_condition

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
        return f"BetSettings(strategy={self.strategy}, percentage={self.percentage}, percentage_gap={self.percentage_gap}, max_points={self.max_points}, minimum_points={self.minimum_points}, stealth_mode={self.stealth_mode}, uncertain_percentage={self.uncertain_percentage}, uncertain_odds=[{self.uncertain_odds_min}-{self.uncertain_odds_max}], uncertain_max_points={self.uncertain_max_points})"


class Bet(object):
    __slots__ = ["outcomes", "decision", "total_users", "total_points", "settings"]

    def __init__(self, outcomes: list, settings: BetSettings):
        self.outcomes = outcomes
        self.__clear_outcomes()
        self.decision: dict = {}
        self.total_users = 0
        self.total_points = 0
        self.settings = settings

    def update_outcomes(self, outcomes):
        for index in range(0, len(self.outcomes)):
            self.outcomes[index][OutcomeKeys.TOTAL_USERS] = int(
                outcomes[index][OutcomeKeys.TOTAL_USERS]
            )
            self.outcomes[index][OutcomeKeys.TOTAL_POINTS] = int(
                outcomes[index][OutcomeKeys.TOTAL_POINTS]
            )
            if outcomes[index]["top_predictors"] != []:
                # Sort by points placed by other users
                outcomes[index]["top_predictors"] = sorted(
                    outcomes[index]["top_predictors"],
                    key=lambda x: x["points"],
                    reverse=True,
                )
                # Get the first elements (most placed)
                top_points = outcomes[index]["top_predictors"][0]["points"]
                self.outcomes[index][OutcomeKeys.TOP_POINTS] = top_points

        # Inefficient, but otherwise outcomekeys are represented wrong
        self.total_points = 0
        self.total_users = 0
        for index in range(0, len(self.outcomes)):
            self.total_users += self.outcomes[index][OutcomeKeys.TOTAL_USERS]
            self.total_points += self.outcomes[index][OutcomeKeys.TOTAL_POINTS]

        if (
            self.total_users > 0
            and self.total_points > 0
        ):
            for index in range(0, len(self.outcomes)):
                self.outcomes[index][OutcomeKeys.PERCENTAGE_USERS] = float_round(
                    (100 * self.outcomes[index][OutcomeKeys.TOTAL_USERS]) / self.total_users
                )
                self.outcomes[index][OutcomeKeys.ODDS] = float_round(
                    #self.total_points / max(self.outcomes[index][OutcomeKeys.TOTAL_POINTS], 1)
                    0
                    if self.outcomes[index][OutcomeKeys.TOTAL_POINTS] == 0
                    else self.total_points / self.outcomes[index][OutcomeKeys.TOTAL_POINTS]
                )
                self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE] = float_round(
                    #100 / max(self.outcomes[index][OutcomeKeys.ODDS], 1)
                    0
                    if self.outcomes[index][OutcomeKeys.ODDS] == 0
                    else 100 / self.outcomes[index][OutcomeKeys.ODDS]
                )

        self.__clear_outcomes()

    def __repr__(self):
        return f"Bet(total_users={millify(self.total_users)}, total_points={millify(self.total_points)}), decision={self.decision})\n\t\tOutcome A({self.get_outcome(0)})\n\t\tOutcome B({self.get_outcome(1)})"

    def get_decision(self, parsed=False):
        #decision = self.outcomes[0 if self.decision["choice"] == "A" else 1]
        decision = self.outcomes[self.decision["choice"]]
        return decision if parsed is False else Bet.__parse_outcome(decision)

    @staticmethod
    def __parse_outcome(outcome):
        return f"{outcome['title']} ({outcome['color']}), Points: {millify(outcome[OutcomeKeys.TOTAL_POINTS])}, Users: {millify(outcome[OutcomeKeys.TOTAL_USERS])} ({outcome[OutcomeKeys.PERCENTAGE_USERS]}%), Odds: {outcome[OutcomeKeys.ODDS]} ({outcome[OutcomeKeys.ODDS_PERCENTAGE]}%)"

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

    '''def __return_choice(self, key) -> str:
        return "A" if self.outcomes[0][key] > self.outcomes[1][key] else "B"'''

    def __return_choice(self, key) -> int:
        largest=0
        for index in range(0, len(self.outcomes)):
            if self.outcomes[index][key] > self.outcomes[largest][key]:
                largest = index
        return largest

    def __return_number_choice(self, number) -> int:
        if (len(self.outcomes) > number):
            return number
        else:
            return 0

    def __is_uncertain_odds(self, odds_percentage) -> bool:
        return (
            self.settings.uncertain_percentage is not None
            and self.settings.uncertain_percentage > 0
            and self.settings.uncertain_odds_min <= odds_percentage <= self.settings.uncertain_odds_max
        )

    def __get_filter_conditions(self):
        if self.settings.filter_condition is None:
            return []
        return (
            self.settings.filter_condition
            if isinstance(self.settings.filter_condition, (list, tuple))
            else [self.settings.filter_condition]
        )

    @staticmethod
    def __matches_filter_condition(condition, compared_value, value) -> bool:
        if condition == Condition.GT:
            return compared_value > value
        elif condition == Condition.LT:
            return compared_value < value
        elif condition == Condition.GTE:
            return compared_value >= value
        elif condition == Condition.LTE:
            return compared_value <= value
        return False

    def __get_compared_value(self, filter_condition, choice):
        key = filter_condition.by
        fixed_key = (
            key
            if key not in [OutcomeKeys.DECISION_USERS, OutcomeKeys.DECISION_POINTS]
            else key.replace("decision", "total")
        )
        if key in [OutcomeKeys.TOTAL_USERS, OutcomeKeys.TOTAL_POINTS]:
            return self.outcomes[0][fixed_key] + self.outcomes[1][fixed_key]
        return self.outcomes[choice][fixed_key]

    def __get_uncertain_choice(self):
        uncertain_choices = [
            index
            for index in range(0, len(self.outcomes))
            if self.__is_uncertain_odds(
                self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE]
            )
        ]
        if len(uncertain_choices) == 0:
            return None

        if len(uncertain_choices) == 1:
            return uncertain_choices[0]

        return max(
            uncertain_choices,
            key=lambda index: (
                self.outcomes[index][OutcomeKeys.TOP_POINTS],
                self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE],
            ),
        )

    def __apply_uncertain_choice_override(self):
        if self.decision["choice"] is None:
            return

        uncertain_choice = self.__get_uncertain_choice()
        if uncertain_choice is None or uncertain_choice == self.decision["choice"]:
            return

        for filter_condition in self.__get_filter_conditions():
            compared_value = self.__get_compared_value(
                filter_condition, self.decision["choice"]
            )
            if self.__matches_filter_condition(
                filter_condition.where, compared_value, filter_condition.value
            ):
                continue

            if filter_condition.by == OutcomeKeys.ODDS_PERCENTAGE:
                self.decision["choice"] = uncertain_choice
            return

    def skip(self) -> bool:
        conditions = self.__get_filter_conditions()
        if len(conditions) > 0:
            compared_values = []
            for filter_condition in conditions:
                key = filter_condition.by
                condition = filter_condition.where
                value = filter_condition.value
                compared_value = self.__get_compared_value(
                    filter_condition, self.decision["choice"]
                )

                compared_values.append(compared_value)

                if self.__matches_filter_condition(condition, compared_value, value):
                    continue

                if (
                    key == OutcomeKeys.ODDS_PERCENTAGE
                    and self.__is_uncertain_odds(compared_value)
                ):
                    continue

                return True, compared_values[0] if len(compared_values) == 1 else compared_values

            return False, compared_values[0] if len(compared_values) == 1 else compared_values
        else:
            return False, 0  # Default don't skip the bet

    def calculate(self, balance: int) -> dict:
        self.decision = {"choice": None, "amount": 0, "id": None}
        if self.settings.strategy == Strategy.MOST_VOTED:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.TOTAL_USERS)
        elif self.settings.strategy == Strategy.HIGH_ODDS:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS)
        elif self.settings.strategy == Strategy.PERCENTAGE:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS_PERCENTAGE)
        elif self.settings.strategy == Strategy.SMART_MONEY:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.TOP_POINTS)
        elif self.settings.strategy == Strategy.NUMBER_1:
            self.decision["choice"] = self.__return_number_choice(0)
        elif self.settings.strategy == Strategy.NUMBER_2:
            self.decision["choice"] = self.__return_number_choice(1)
        elif self.settings.strategy == Strategy.NUMBER_3:
            self.decision["choice"] = self.__return_number_choice(2)
        elif self.settings.strategy == Strategy.NUMBER_4:
            self.decision["choice"] = self.__return_number_choice(3)
        elif self.settings.strategy == Strategy.NUMBER_5:
            self.decision["choice"] = self.__return_number_choice(4)
        elif self.settings.strategy == Strategy.NUMBER_6:
            self.decision["choice"] = self.__return_number_choice(5)
        elif self.settings.strategy == Strategy.NUMBER_7:
            self.decision["choice"] = self.__return_number_choice(6)
        elif self.settings.strategy == Strategy.NUMBER_8:
            self.decision["choice"] = self.__return_number_choice(7)
        elif self.settings.strategy == Strategy.SMART:
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
            self.__apply_uncertain_choice_override()
            #index = char_decision_as_index(self.decision["choice"])
            index = self.decision["choice"]
            self.decision["id"] = self.outcomes[index]["id"]
            odds_percentage = self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE]
            if self.__is_uncertain_odds(odds_percentage):
                self.decision["amount"] = min(
                    int(balance * (self.settings.uncertain_percentage / 100)),
                    self.settings.uncertain_max_points,
                )
            else:
                self.decision["amount"] = min(
                    int(balance * (self.settings.percentage / 100)),
                    self.settings.max_points,
                )
            if (
                self.settings.stealth_mode is True
                and self.decision["amount"]
                >= self.outcomes[index][OutcomeKeys.TOP_POINTS]
            ):
                reduce_amount = uniform(1, 5)
                self.decision["amount"] = (
                    self.outcomes[index][OutcomeKeys.TOP_POINTS] - reduce_amount
                )
            self.decision["amount"] = int(self.decision["amount"])
        return self.decision
