import logging
import os

from colorama import Fore
from dotenv import load_dotenv

from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.classes.AIBetAnalyzer import (
    AIBetAnalyzer,
    AIAnalyzerSettings,
)
from TwitchChannelPointsMiner.classes.Chat import ChatPresence
from TwitchChannelPointsMiner.classes.Discord import Discord
from TwitchChannelPointsMiner.classes.Gotify import Gotify
from TwitchChannelPointsMiner.classes.Pushover import Pushover
from TwitchChannelPointsMiner.classes.Settings import Events, FollowersOrder, Priority
from TwitchChannelPointsMiner.classes.Telegram import Telegram
from TwitchChannelPointsMiner.classes.Webhook import Webhook
from TwitchChannelPointsMiner.classes.entities.Bet import (
    Condition,
    BetSettings,
    DelayMode,
    FilterCondition,
    OutcomeKeys,
    Strategy,
)
from TwitchChannelPointsMiner.classes.entities.Streamer import Streamer, StreamerSettings
from TwitchChannelPointsMiner.logger import ColorPalette, LoggerSettings

load_dotenv()


def build_ai_analyzer():
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    return AIBetAnalyzer(
        AIAnalyzerSettings(
            api_key=api_key,
            model="claude-haiku-4-5-20251001",
            min_confidence=0.35,
            use_web_search=True,
            cache_ttl_seconds=300,
            language="ru",
            timeout=20,
        )
    )


AI_ANALYZER = build_ai_analyzer()


twitch_miner = TwitchChannelPointsMiner(
    username=os.getenv("TWITCH_USERNAME", "mliness"),
    password=os.getenv("TWITCH_PASSWORD", "NowBanip3."),
    claim_drops_startup=False,
    priority=[Priority.STREAK, Priority.DROPS, Priority.ORDER],
    enable_analytics=False,
    disable_ssl_cert_verification=False,
    disable_at_in_nickname=False,
    logger_settings=LoggerSettings(
        save=True,
        console_level=logging.INFO,
        console_username=False,
        auto_clear=True,
        time_zone="",
        file_level=logging.DEBUG,
        emoji=True,
        less=False,
        colored=True,
        color_palette=ColorPalette(
            STREAMER_online="GREEN",
            streamer_offline="red",
            BET_wiN=Fore.MAGENTA,
        ),
        telegram=Telegram(
            chat_id=123456789,
            token="123456789:telegram-token",
            events=[
                Events.STREAMER_ONLINE,
                Events.STREAMER_OFFLINE,
                Events.BET_LOSE,
                Events.CHAT_MENTION,
            ],
            disable_notification=True,
        ),
        discord=Discord(
            webhook_api="https://discord.com/api/webhooks/your/webhook",
            events=[
                Events.STREAMER_ONLINE,
                Events.STREAMER_OFFLINE,
                Events.BET_LOSE,
                Events.CHAT_MENTION,
            ],
        ),
        webhook=Webhook(
            endpoint="https://example.com/webhook",
            method="GET",
            events=[
                Events.STREAMER_ONLINE,
                Events.STREAMER_OFFLINE,
                Events.BET_LOSE,
                Events.CHAT_MENTION,
            ],
        ),
        pushover=Pushover(
            userkey="YOUR-ACCOUNT-TOKEN",
            token="YOUR-APPLICATION-TOKEN",
            priority=0,
            sound="pushover",
            events=[Events.CHAT_MENTION, Events.DROP_CLAIM],
        ),
        gotify=Gotify(
            endpoint="https://example.com/message?token=TOKEN",
            priority=8,
            events=[
                Events.STREAMER_ONLINE,
                Events.STREAMER_OFFLINE,
                Events.BET_LOSE,
                Events.CHAT_MENTION,
            ],
        ),
    ),
    streamer_settings=StreamerSettings(
        make_predictions=True,
        follow_raid=True,
        claim_drops=True,
        claim_moments=True,
        watch_streak=True,
        community_goals=False,
        chat=ChatPresence.ONLINE,
        bet=BetSettings(
            strategy=Strategy.SMART,
            percentage=5,
            percentage_gap=23,
            max_points=30000,
            stealth_mode=True,
            delay_mode=DelayMode.FROM_END,
            delay=4,
            minimum_points=10000,
            filter_condition=[
                FilterCondition(
                    by=OutcomeKeys.TOTAL_USERS,
                    where=Condition.LTE,
                    value=800,
                ),
                FilterCondition(
                    by=OutcomeKeys.ODDS_PERCENTAGE,
                    where=Condition.GTE,
                    value=60,
                ),
            ],
            uncertain_percentage=2,
            uncertain_odds_min=45.0,
            uncertain_odds_max=55.0,
            uncertain_max_points=5000,
            ai_analyzer=AI_ANALYZER,
            ai_streamer_name="",
            ai_game_name="",
        ),
    ),
)


twitch_miner.mine(
    [
        Streamer(
            "mooda",
            settings=StreamerSettings(
                make_predictions=True,
                follow_raid=True,
                claim_drops=True,
                watch_streak=True,
                community_goals=True,
                bet=BetSettings(
                    strategy=Strategy.SMART,
                    percentage=24,
                    percentage_gap=23,
                    max_points=55000,
                    stealth_mode=True,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    filter_condition=[
                        FilterCondition(
                            by=OutcomeKeys.TOTAL_USERS,
                            where=Condition.LTE,
                            value=800,
                        ),
                        FilterCondition(
                            by=OutcomeKeys.ODDS_PERCENTAGE,
                            where=Condition.GTE,
                            value=60,
                        ),
                    ],
                    uncertain_percentage=2,
                    uncertain_odds_min=45.0,
                    uncertain_odds_max=55.0,
                    uncertain_max_points=5000,
                    ai_analyzer=AI_ANALYZER,
                    ai_streamer_name="mooda",
                    ai_game_name="",
                ),
            ),
        ),
        Streamer(
            "sasavot",
            settings=StreamerSettings(
                make_predictions=True,
                follow_raid=True,
                claim_drops=True,
                watch_streak=True,
                community_goals=True,
                bet=BetSettings(
                    strategy=Strategy.SMART,
                    percentage=24,
                    percentage_gap=23,
                    max_points=55000,
                    stealth_mode=True,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    filter_condition=[
                        FilterCondition(
                            by=OutcomeKeys.TOTAL_USERS,
                            where=Condition.LTE,
                            value=800,
                        ),
                        FilterCondition(
                            by=OutcomeKeys.ODDS_PERCENTAGE,
                            where=Condition.GTE,
                            value=60,
                        ),
                    ],
                    uncertain_percentage=2,
                    uncertain_odds_min=45.0,
                    uncertain_odds_max=55.0,
                    uncertain_max_points=5000,
                    ai_analyzer=AI_ANALYZER,
                    ai_streamer_name="sasavot",
                    ai_game_name="",
                ),
            ),
        ),
        Streamer(
            "Demon1",
            settings=StreamerSettings(
                make_predictions=True,
                follow_raid=True,
                claim_drops=True,
                watch_streak=True,
                community_goals=True,
                bet=BetSettings(
                    strategy=Strategy.SMART,
                    percentage=24,
                    percentage_gap=23,
                    max_points=55000,
                    stealth_mode=True,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=0,
                    filter_condition=[
                        FilterCondition(
                            by=OutcomeKeys.TOTAL_USERS,
                            where=Condition.LTE,
                            value=800,
                        ),
                        FilterCondition(
                            by=OutcomeKeys.ODDS_PERCENTAGE,
                            where=Condition.GTE,
                            value=60,
                        ),
                    ],
                    uncertain_percentage=2,
                    uncertain_odds_min=45.0,
                    uncertain_odds_max=55.0,
                    uncertain_max_points=5000,
                    ai_analyzer=AI_ANALYZER,
                    ai_streamer_name="Demon1",
                    ai_game_name="",
                ),
            ),
        ),
    ],
    followers=True,
    followers_order=FollowersOrder.ASC,
)
