# -*- coding: utf-8 -*-

import logging
from colorama import Fore
from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.logger import LoggerSettings, ColorPalette
from TwitchChannelPointsMiner.classes.Chat import ChatPresence
from TwitchChannelPointsMiner.classes.Discord import Discord
from TwitchChannelPointsMiner.classes.Webhook import Webhook
from TwitchChannelPointsMiner.classes.Telegram import Telegram
from TwitchChannelPointsMiner.classes.Pushover import Pushover
from TwitchChannelPointsMiner.classes.Gotify import Gotify
from TwitchChannelPointsMiner.classes.Settings import Priority, Events, FollowersOrder
from TwitchChannelPointsMiner.classes.entities.Bet import Strategy, BetSettings, Condition, OutcomeKeys, FilterCondition, DelayMode
from TwitchChannelPointsMiner.classes.entities.Streamer import Streamer, StreamerSettings

# Инициализация Twitch Channel Points Miner
twitch_miner = TwitchChannelPointsMiner(
    username="mliness",
    password="NowBanip3.",  # Можно оставить пустым, тогда бот спросит при запуске
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
            BET_wiN=Fore.MAGENTA
        ),
        telegram=Telegram(
            chat_id=123456789,
            token="123456789:shfuihreuifheuifhiu34578347",
            events=[Events.STREAMER_ONLINE, Events.STREAMER_OFFLINE, Events.BET_LOSE, Events.CHAT_MENTION],
            disable_notification=True,
        ),
        discord=Discord(
            webhook_api="https://discord.com/api/webhooks/0123456789/0a1B2c3D4e5F6g7H8i9J",
            events=[Events.STREAMER_ONLINE, Events.STREAMER_OFFLINE, Events.BET_LOSE, Events.CHAT_MENTION],
        ),
        webhook=Webhook(
            endpoint="https://example.com/webhook",
            method="GET",
            events=[Events.STREAMER_ONLINE, Events.STREAMER_OFFLINE, Events.BET_LOSE, Events.CHAT_MENTION],
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
            events=[Events.STREAMER_ONLINE, Events.STREAMER_OFFLINE, Events.BET_LOSE, Events.CHAT_MENTION],
        )
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
            percentage_gap=30,      # Увеличена разница между исходами
            max_points=30000,       # Снижен максимальный риск
            stealth_mode=True,
            delay_mode=DelayMode.FROM_END,
            delay=4,                # Ставка за 4 секунды до конца таймера
            minimum_points=10000,   # Минимальное количество очков для ставки
            filter_condition=[
                FilterCondition(by=OutcomeKeys.TOTAL_USERS, where=Condition.LTE, value=800),
                FilterCondition(by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60)
            ]
        )
    )
)

# Настройка стримеров
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
                    percentage=5,
                    percentage_gap=30,
                    max_points=30000,
                    stealth_mode=True,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    filter_condition=[
                        FilterCondition(by=OutcomeKeys.TOTAL_USERS, where=Condition.LTE, value=800),
                        FilterCondition(by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60)
                    ]
                )
            )
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
                    percentage=5,
                    percentage_gap=30,
                    max_points=30000,
                    stealth_mode=True,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    filter_condition=[
                        FilterCondition(by=OutcomeKeys.TOTAL_USERS, where=Condition.LTE, value=800),
                        FilterCondition(by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60)
                    ]
                )
            )
        ),
    ],
    followers=True,
    followers_order=FollowersOrder.ASC
)
