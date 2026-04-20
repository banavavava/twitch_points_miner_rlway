# -*- coding: utf-8 -*-

import logging
from colorama import Fore
from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.logger import LoggerSettings, ColorPalette
from TwitchChannelPointsMiner.classes.Chat import ChatPresence
from TwitchChannelPointsMiner.classes.Telegram import Telegram
from TwitchChannelPointsMiner.classes.Settings import Priority, Events, FollowersOrder
from TwitchChannelPointsMiner.classes.entities.Bet import Strategy, BetSettings, Condition, OutcomeKeys, FilterCondition, DelayMode
from TwitchChannelPointsMiner.classes.entities.Streamer import Streamer, StreamerSettings

twitch_miner = TwitchChannelPointsMiner(
    username="mliness",
    password="NowBanip3.",           # If no password will be provided, the script will ask interactively
    claim_drops_startup=False,                  # If you want to auto claim all drops from Twitch inventory on the startup
    priority=[                                  # Custom priority in this case for example:
        Priority.STREAK,                        # - We want first of all to catch all watch streak from all streamers
        Priority.DROPS,                         # - When we don't have anymore watch streak to catch, wait until all drops are collected over the streamers
        Priority.ORDER                          # - When we have all of the drops claimed and no watch-streak available, use the order priority (POINTS_ASCENDING, POINTS_DESCENDING)
    ],
    enable_analytics=False,                     # Disables Analytics if False. Disabling it significantly reduces memory consumption
    disable_ssl_cert_verification=False,        # Set to True at your own risk and only to fix SSL: CERTIFICATE_VERIFY_FAILED error
    disable_at_in_nickname=False,               # Set to True if you want to check for your nickname mentions in the chat even without @ sign
    logger_settings=LoggerSettings(
        save=True,                              # If you want to save logs in a file (suggested)
        console_level=logging.INFO,             # Level of logs - use logging.DEBUG for more info
        console_username=False,                 # Adds a username to every console log line if True. Also adds it to Telegram, Discord, etc. Useful when you have several accounts
        auto_clear=True,                        # Create a file rotation handler with interval = 1D and backupCount = 7 if True (default)
        time_zone="",                           # Set a specific time zone for console and file loggers. Use tz database names. Example: "America/Denver"
        file_level=logging.DEBUG,               # Level of logs - If you think the log file it's too big, use logging.INFO
        emoji=True,                             # On Windows, we have a problem printing emoji. Set to false if you have a problem
        less=False,                             # If you think that the logs are too verbose, set this to True
        colored=True,                           # If you want to print colored text
        color_palette=ColorPalette(             # You can also create a custom palette color (for the common message).
            STREAMER_online="GREEN",            # Don't worry about lower/upper case. The script will parse all the values.
            streamer_offline="red",             # Read more in README.md
            BET_wiN=Fore.MAGENTA                # Color allowed are: [BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET].
        ),
        telegram=Telegram(                                                          # You can omit or set to None if you don't want to receive updates on Telegram
            chat_id=7160081907,                                                      # Chat ID to send messages @getmyid_bot
            token="8079715426:AAHnjQpEHRoEOmTDJKdjNYa6vhs2H_iQ-kQ",                          # Telegram API token @BotFather
            events=[Events.STREAMER_ONLINE, Events.STREAMER_OFFLINE,
                    Events.BET_LOSE, Events.CHAT_MENTION, Events.BET_WIN, Events.BET_START, Events.BET_GENERAL, Events.BET_FAILED, Events.BET_REFUND, Events.REWARD_REDEEMED, Events.REWARD_FAILED, Events.REWARD_SKIPPED],                          # Only these events will be sent to the chat
            disable_notification=True,                                              # Revoke the notification (sound/vibration)
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
            strategy=Strategy.PERCENTAGE,
            percentage=5,
            percentage_gap=30,      # Увеличена разница между исходами
            max_points=30000,       # Снижен максимальный риск
            stealth_mode=False,
            delay_mode=DelayMode.FROM_END,
            delay=4,                # Ставка за 4 секунды до конца таймера
            minimum_points=10000,   # Минимальное количество очков для ставки
            uncertain_percentage=1,
            uncertain_odds_min=41,
            uncertain_odds_max=59,
            uncertain_max_points=1500,
            filter_condition=FilterCondition(
                by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60
            )
        )
    )
)

# You can customize the settings for each streamer. If not settings were provided, the script would use the streamer_settings from TwitchChannelPointsMiner.
# If no streamer_settings are provided in TwitchChannelPointsMiner the script will use default settings.
# The streamers array can be a String -> username or Streamer instance.

# The settings priority are: settings in mine function, settings in TwitchChannelPointsMiner instance, default settings.
# For example, if in the mine function you don't provide any value for 'make_prediction' but you have set it on TwitchChannelPointsMiner instance, the script will take the value from here.
# If you haven't set any value even in the instance the default one will be used

#twitch_miner.analytics(host="127.0.0.1", port=5000, refresh=5, days_ago=7)   # Start the Analytics web-server

twitch_miner.mine(
    [
        Streamer(
            "mooda",
            settings=StreamerSettings(
                make_predictions=True,
                follow_raid=True,
                claim_drops=True,
                watch_streak=True,
                community_goals=False,
                fetch_rewards=False,                 # Print current rewards from ChannelPointsContext
                auto_redeem_reward_ids=[],          # Example: ["cb303f46-8d7b-4f4e-9262-aaa796fab3c2"]
                auto_redeem_reward_titles=[],       # Example: ["stay hydrated!"]
                auto_redeem_text=None,              # Optional textInput for reward redeem
                bet=BetSettings(
                    strategy=Strategy.PERCENTAGE,
                    percentage=24,
                    percentage_gap=30,
                    max_points=55000,
                    stealth_mode=False, 
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    uncertain_percentage=10,
                    uncertain_odds_min=41,
                    uncertain_odds_max=59,
                    uncertain_max_points=12000,
                    filter_condition=FilterCondition(
                        by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60
                    )
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
                community_goals=False,
                fetch_rewards=False,
                auto_redeem_reward_ids=[],
                auto_redeem_reward_titles=[],
                auto_redeem_text=None,
                bet=BetSettings(
                    strategy=Strategy.PERCENTAGE,
                    percentage=24,
                    percentage_gap=30,
                    max_points=100000,
                    stealth_mode=False,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    uncertain_percentage=10,
                    uncertain_odds_min=41,
                    uncertain_odds_max=59,
                    uncertain_max_points=12000,
                    filter_condition=FilterCondition(
                        by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60
                    )
                )
            )
        ),
        Streamer(
            "saintsakura",
            settings=StreamerSettings(
                make_predictions=True,
                follow_raid=True,
                claim_drops=True,
                watch_streak=True,
                community_goals=False,
                fetch_rewards=True,                        # Print rewards and resolve IDs by title automatically
                auto_redeem_reward_ids=[],                 # Optional direct IDs (can stay empty)
                auto_redeem_reward_titles=["First!"],  # You can use full or partial title
                auto_redeem_text="",
                auto_redeem_repeat=True,                   # Redeem again automatically when cooldown ends
                bet=BetSettings(
                    strategy=Strategy.PERCENTAGE,
                    percentage=24,
                    percentage_gap=30,
                    max_points=55000,
                    stealth_mode=False,
                    delay_mode=DelayMode.FROM_END,
                    delay=4,
                    minimum_points=10000,
                    uncertain_percentage=10,
                    uncertain_odds_min=41,
                    uncertain_odds_max=59,
                    uncertain_max_points=12000,
                    filter_condition=FilterCondition(
                        by=OutcomeKeys.ODDS_PERCENTAGE, where=Condition.GTE, value=60
                    )
                )
            )
        ),
    ],
    followers=True,
    followers_order=FollowersOrder.ASC
)
