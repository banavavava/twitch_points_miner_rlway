# -*- coding: utf-8 -*-

import logging
import os
import random
import signal
import sys
import threading
import time
from typing import Optional
import uuid
from datetime import datetime
from pathlib import Path

from TwitchChannelPointsMiner.classes.Chat import ChatPresence, ThreadChat
from TwitchChannelPointsMiner.classes.entities.PubsubTopic import PubsubTopic
from TwitchChannelPointsMiner.classes.entities.Streamer import (
    Streamer,
    StreamerSettings,
)
from TwitchChannelPointsMiner.classes.Exceptions import StreamerDoesNotExistException
from TwitchChannelPointsMiner.classes.Settings import FollowersOrder, Priority, Settings
from TwitchChannelPointsMiner.classes.Twitch import Twitch
from TwitchChannelPointsMiner.classes.WebSocketsPool import WebSocketsPool
from TwitchChannelPointsMiner.logger import LoggerSettings, configure_loggers
from TwitchChannelPointsMiner.utils import (
    _millify,
    at_least_one_value_in_settings_is,
    check_versions,
    get_user_agent,
    internet_connection_available,
    set_default_settings,
)

# Suppress:
#   - chardet.charsetprober - [feed]
#   - chardet.charsetprober - [get_confidence]
#   - requests - [Starting new HTTPS connection (1)]
#   - Flask (werkzeug) logs
#   - irc.client - [process_data]
#   - irc.client - [_dispatcher]
#   - irc.client - [_handle_message]
logging.getLogger("chardet.charsetprober").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("irc.client").setLevel(logging.ERROR)
logging.getLogger("seleniumwire").setLevel(logging.ERROR)
logging.getLogger("websocket").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class TwitchChannelPointsMiner:
    __slots__ = [
        "username",
        "twitch",
        "claim_drops_startup",
        "enable_analytics",
        "disable_ssl_cert_verification",
        "disable_at_in_nickname",
        "priority",
        "streamers",
        "events_predictions",
        "minute_watcher_thread",
        "sync_campaigns_thread",
        "ws_pool",
        "session_id",
        "running",
        "start_datetime",
        "original_streamers",
        "logs_file",
        "queue_listener",
        "wakeup_event",
    ]

    def __init__(
        self,
        username: str,
        password: Optional[str] = None,
        claim_drops_startup: bool = False,
        enable_analytics: bool = False,
        disable_ssl_cert_verification: bool = False,
        disable_at_in_nickname: bool = False,
        # Settings for logging and selenium as you can see.
        priority: list = [Priority.STREAK, Priority.DROPS, Priority.ORDER],
        # This settings will be global shared trought Settings class
        logger_settings: Optional[LoggerSettings] = None,
        # Default values for all streamers
        streamer_settings: Optional[StreamerSettings] = None,
    ):
        # Fixes TypeError: 'NoneType' object is not subscriptable
        if not username or username == "your-twitch-username":
            logger.error("Please edit your runner file (usually run.py) and try again.")
            logger.error("No username, exiting...")
            sys.exit(0)

        # This disables certificate verification and allows the connection to proceed, but also makes it vulnerable to man-in-the-middle (MITM) attacks.
        Settings.disable_ssl_cert_verification = disable_ssl_cert_verification

        Settings.disable_at_in_nickname = disable_at_in_nickname

        import socket

        def is_connected():
            try:
                # resolve the IP address of the Twitch.tv domain name
                socket.gethostbyname("twitch.tv")
                return True
            except OSError:
                pass
            return False

        # check for Twitch.tv connectivity every 5 seconds
        error_printed = False
        while not is_connected():
            if not error_printed:
                logger.error("Waiting for Twitch.tv connectivity...")
                error_printed = True
            time.sleep(5)

        # Analytics switch
        Settings.enable_analytics = enable_analytics

        if enable_analytics is True:
            Settings.analytics_path = os.path.join(
                Path().absolute(), "analytics", username
            )
            Path(Settings.analytics_path).mkdir(parents=True, exist_ok=True)

        self.username = username

        if logger_settings is None:
            logger_settings = LoggerSettings()
        if streamer_settings is None:
            streamer_settings = StreamerSettings()

        # Set as global config
        Settings.logger = logger_settings

        # Init as default all the missing values
        streamer_settings.default()
        if streamer_settings.bet is None:
            assert False, "streamer_settings.bet can't be None, it will be initialized with default values if you don't provide it"
        streamer_settings.bet.default()
        Settings.streamer_settings = streamer_settings

        # user_agent = get_user_agent("FIREFOX")
        user_agent = get_user_agent("CHROME")
        self.twitch = Twitch(self.username, user_agent, password)

        self.claim_drops_startup = claim_drops_startup
        self.priority = priority if isinstance(priority, list) else [priority]

        self.streamers: list[Streamer] = []
        self.events_predictions = {}
        self.minute_watcher_thread = None
        self.sync_campaigns_thread = None
        self.ws_pool = None

        self.session_id = str(uuid.uuid4())
        self.running = False
        self.start_datetime = None
        self.original_streamers = []
        self.wakeup_event = threading.Event()
        self.twitch.wake_main_loop = self.wakeup_event.set

        self.logs_file, self.queue_listener = configure_loggers(
            self.username, logger_settings
        )

        # Check for the latest version of the script
        current_version, github_version = check_versions()

        logger.info(
            f"Twitch Channel Points Miner v2-{current_version} (fork by rdavydov)"
        )
        logger.info("https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2")

        if github_version == "0.0.0":
            logger.error(
                "Unable to detect if you have the latest version of this script"
            )
        elif current_version != github_version:
            logger.info(f"You are running version {current_version} of this script")
            logger.info(f"The latest version on GitHub is {github_version}")

        for sign in [signal.SIGINT, signal.SIGSEGV, signal.SIGTERM]:
            signal.signal(sign, self.end)

    def analytics(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        refresh: int = 5,
        days_ago: int = 7,
    ):
        # Analytics switch
        if Settings.enable_analytics is True:
            from TwitchChannelPointsMiner.classes.AnalyticsServer import AnalyticsServer

            days_ago = days_ago if days_ago <= 365 * 15 else 365 * 15
            http_server = AnalyticsServer(
                host=host,
                port=port,
                refresh=refresh,
                days_ago=days_ago,
                username=self.username,
            )
            http_server.daemon = True
            http_server.name = "Analytics Thread"
            http_server.start()
        else:
            logger.error("Can't start analytics(), please set enable_analytics=True")

    def mine(
        self,
        streamers: list = [],
        blacklist: list = [],
        followers: bool = False,
        followers_order: FollowersOrder = FollowersOrder.ASC,
    ):
        self.run(streamers=streamers, blacklist=blacklist, followers=followers)

    def run(
        self,
        streamers: list = [],
        blacklist: list = [],
        followers: bool = False,
        followers_order: FollowersOrder = FollowersOrder.ASC,
    ):
        if self.running:
            logger.error("You can't start multiple sessions of this instance!")
        else:
            logger.info(
                f"Start session: '{self.session_id}'", extra={"emoji": ":bomb:"}
            )
            self.running = True
            self.start_datetime = datetime.now()

            self.twitch.login()

            if self.claim_drops_startup is True:
                self.twitch.claim_all_drops_from_inventory()

            streamers_name: list = []
            streamers_dict: dict = {}
            explicit_streamers_usernames: set[str] = set()
            streamer_context_interval: dict[str, int] = {}

            for streamer in streamers:
                username = (
                    streamer.username
                    if isinstance(streamer, Streamer)
                    else streamer.lower().strip()
                )
                if username not in blacklist:
                    streamers_name.append(username)
                    streamers_dict[username] = streamer
                    explicit_streamers_usernames.add(username)
                    streamer_context_interval[username] = (
                        4 if username == "saintsakura" else 12
                    )

            if followers is True:
                followers_array = self.twitch.get_followers(order=followers_order)
                logger.info(
                    f"Load {len(followers_array)} followers from your profile!",
                    extra={"emoji": ":clipboard:"},
                )
                for username in followers_array:
                    if (
                        username not in explicit_streamers_usernames
                        and username not in streamers_dict
                        and username not in blacklist
                    ):
                        streamers_name.append(username)
                        streamers_dict[username] = username.lower().strip()
                        streamer_context_interval[username] = 60

            logger.info(
                f"Loading data for {len(streamers_name)} streamers. Please wait...",
                extra={"emoji": ":nerd_face:"},
            )
            for username in streamers_name:
                if username in streamers_name:
                    interval = streamer_context_interval.get(username, 60)
                    startup_delay = (
                        random.uniform(0.05, 0.15)
                        if interval <= 12
                        else random.uniform(0.15, 0.35)
                    )
                    time.sleep(startup_delay)
                    try:
                        streamer = (
                            streamers_dict[username]
                            if isinstance(streamers_dict[username], Streamer) is True
                            else Streamer(username)
                        )
                        streamer.channel_id = self.twitch.get_channel_id(username)
                        streamer.settings = set_default_settings(
                            streamer.settings, Settings.streamer_settings
                        )
                        streamer.settings.bet = set_default_settings(
                            streamer.settings.bet, Settings.streamer_settings.bet
                        )
                        if streamer.settings.chat != ChatPresence.NEVER:
                            streamer.irc_chat = ThreadChat(
                                self.username,
                                self.twitch.twitch_login.get_auth_token(),
                                streamer.username,
                            )
                        self.streamers.append(streamer)
                    except StreamerDoesNotExistException:
                        logger.info(
                            f"Streamer {username} does not exist",
                            extra={"emoji": ":cry:"},
                        )

            # Populate the streamers with default values.
            # 1. Load channel points and auto-claim bonus
            # 2. Check if streamers are online
            # 3. DEACTIVATED: Check if the user is a moderator. (was used before the 5th of April 2021 to deactivate predictions)
            explicit_streamers: list[Streamer] = []
            explicit_streamers_seen: set[str] = set()
            for streamer in self.streamers:
                if (
                    streamer.username in explicit_streamers_usernames
                    and streamer.username not in explicit_streamers_seen
                ):
                    explicit_streamers.append(streamer)
                    explicit_streamers_seen.add(streamer.username)

            def explicit_streamer_atomic_loop(streamer: Streamer, interval: int):
                # Run immediately, then continue by per-streamer timer.
                next_context_due = time.time()
                fast_silent_redeem_mode = streamer.is_fast_auto_redeem_mode()
                has_auto_redeem_targets = streamer.has_auto_redeem_targets()
                if fast_silent_redeem_mode and has_auto_redeem_targets:
                    self.twitch.prime_auto_redeem_cache(streamer)
                logger.debug(
                    f"[atomic] start checker for {streamer.username} interval={interval}s"
                )
                while self.running and self.twitch.running:
                    try:
                        now = time.time()

                        if now >= next_context_due:
                            logger.debug(
                                f"[atomic] tick context for {streamer.username} "
                                f"(online={streamer.is_online})"
                            )
                            # Always refresh points context for explicit streamers,
                            # then verify live status.
                            self.twitch.load_channel_points_context(
                                streamer, include_rewards=False
                            )
                            self.twitch.check_streamer_online(streamer)
                            if fast_silent_redeem_mode and streamer.has_auto_redeem_targets():
                                self.twitch.prime_auto_redeem_cache(streamer)
                            next_context_due = time.time() + interval

                        has_auto_redeem_targets = streamer.has_auto_redeem_targets()
                        if (
                            fast_silent_redeem_mode
                            and has_auto_redeem_targets
                            and streamer.auto_redeem_next_check_at == 0
                        ):
                            has_cached_offline_repeat_rewards = any(
                                (
                                    isinstance((reward.get("maxPerStreamSetting") or {}), dict)
                                    is False
                                )
                                or (reward.get("maxPerStreamSetting") or {}).get("isEnabled") is not True
                                or int((reward.get("maxPerStreamSetting") or {}).get("maxPerStream") or 0) <= 0
                                for reward in (streamer.auto_redeem_cached_rewards or [])
                            )
                            if (
                                streamer.is_online is not True
                                and has_cached_offline_repeat_rewards
                            ):
                                streamer.auto_redeem_next_check_at = time.time()

                        if (
                            has_auto_redeem_targets
                            and streamer.auto_redeem_next_check_at != 0
                            and time.time() >= streamer.auto_redeem_next_check_at
                        ):
                            if not fast_silent_redeem_mode:
                                logger.debug(
                                    f"[atomic] tick auto_redeem for {streamer.username} "
                                    f"(online={streamer.is_online})"
                                )
                            # Reset before request to avoid tight loops on failures.
                            streamer.auto_redeem_next_check_at = 0
                            if fast_silent_redeem_mode:
                                trigger = (
                                    "online_transition"
                                    if streamer.is_online is True
                                    and len(streamer.auto_redeemed_rewards) == 0
                                    else "periodic"
                                )
                                self.twitch.fast_auto_redeem_tick(streamer, trigger=trigger)
                            elif streamer.is_online:
                                self.twitch.load_channel_points_context(streamer)
                            else:
                                self.twitch.check_streamer_online(streamer)
                                if streamer.is_online:
                                    self.twitch.load_channel_points_context(streamer)

                        due_times = [next_context_due]
                        if (
                            has_auto_redeem_targets
                            and streamer.auto_redeem_next_check_at != 0
                        ):
                            due_times.append(streamer.auto_redeem_next_check_at)
                        wait_for = max(0.25, min(2.0, min(due_times) - time.time()))
                        time.sleep(wait_for)
                    except Exception:
                        logger.error(
                            f"Exception raised in atomic checker for {streamer}",
                            exc_info=True,
                        )
                        time.sleep(1)

            for streamer in explicit_streamers:
                interval = streamer_context_interval.get(streamer.username, 12)
                checker_thread = threading.Thread(
                    target=explicit_streamer_atomic_loop,
                    args=(streamer, interval),
                )
                checker_thread.name = f"Atomic checker: {streamer.username}"
                checker_thread.daemon = True
                checker_thread.start()

            if len(explicit_streamers) > 0:
                logger.debug(
                    f"[atomic] enabled checkers for {len(explicit_streamers)} explicit streamers"
                )

            for streamer in self.streamers:
                if streamer.username in explicit_streamers_usernames:
                    continue
                interval = streamer_context_interval.get(streamer.username, 60)
                startup_delay = (
                    random.uniform(0.05, 0.15)
                    if interval <= 12
                    else random.uniform(0.15, 0.35)
                )
                time.sleep(startup_delay)
                try:
                    self.twitch.load_channel_points_context(
                        streamer, include_rewards=False
                    )
                    # Full online check at startup only for streamers explicitly passed to mine(...),
                    # followers will be tracked by pubsub shortly after startup.
                    if streamer.username in explicit_streamers_usernames:
                        self.twitch.check_streamer_online(streamer)
                        # If streamer is already online and has auto-redeem targets,
                        # run reward check immediately without waiting for the main loop.
                        settings = streamer.settings
                        if streamer.is_online and settings is not None:
                            has_auto_redeem = (
                                len(settings.auto_redeem_reward_ids or []) > 0
                                or len(settings.auto_redeem_reward_titles or []) > 0
                                or settings.fetch_rewards is True
                            )
                            if has_auto_redeem:
                                self.twitch.load_channel_points_context(streamer)
                                streamer.auto_redeem_next_check_at = 0
                    else:
                        # Keep startup status logs for non-explicit (followers) streamers too.
                        self.twitch.check_streamer_online(streamer)
                    # self.twitch.viewer_is_mod(streamer)
                except StreamerDoesNotExistException:
                    logger.info(
                        f"Streamer {streamer.username} does not exist",
                        extra={"emoji": ":cry:"},
                    )

            self.original_streamers = [
                streamer.channel_points for streamer in self.streamers
            ]
            next_context_check_at: dict[str, float] = {}
            for streamer in self.streamers:
                interval = streamer_context_interval.get(streamer.username, 60)
                next_context_check_at[streamer.username] = time.time() + interval

            # If we have at least one streamer with settings = make_predictions True
            make_predictions = at_least_one_value_in_settings_is(
                self.streamers, "make_predictions", True
            )

            # If we have at least one streamer with settings = claim_drops True
            # Spawn a thread for sync inventory and dashboard
            if (
                at_least_one_value_in_settings_is(self.streamers, "claim_drops", True)
                is True
            ):
                self.sync_campaigns_thread = threading.Thread(
                    target=self.twitch.sync_campaigns,
                    args=(self.streamers,),
                )
                self.sync_campaigns_thread.name = "Sync campaigns/inventory"
                self.sync_campaigns_thread.start()
                time.sleep(30)

            self.minute_watcher_thread = threading.Thread(
                target=self.twitch.send_minute_watched_events,
                args=(self.streamers, self.priority),
            )
            self.minute_watcher_thread.name = "Minute watcher"
            self.minute_watcher_thread.start()

            self.ws_pool = WebSocketsPool(
                twitch=self.twitch,
                streamers=self.streamers,
                events_predictions=self.events_predictions,
            )

            # Subscribe to community-points-user. Get update for points spent or gains
            user_id = self.twitch.twitch_login.get_user_id()
            # print(f"!!!!!!!!!!!!!! USER_ID: {user_id}")

            # Fixes 'ERR_BADAUTH'
            if not user_id:
                logger.error("No user_id, exiting...")
                self.end(0, 0)

            self.ws_pool.submit(
                PubsubTopic(
                    "community-points-user-v1",
                    user_id=user_id,
                )
            )

            # Going to subscribe to predictions-user-v1. Get update when we place a new prediction (confirm)
            if make_predictions is True:
                self.ws_pool.submit(
                    PubsubTopic(
                        "predictions-user-v1",
                        user_id=user_id,
                    )
                )

            for streamer in self.streamers:
                settings = streamer.settings
                if settings is None:
                    continue
                self.ws_pool.submit(
                    PubsubTopic("video-playback-by-id", streamer=streamer)
                )

                if settings.follow_raid is True:
                    self.ws_pool.submit(PubsubTopic("raid", streamer=streamer))

                if settings.make_predictions is True:
                    self.ws_pool.submit(
                        PubsubTopic("predictions-channel-v1", streamer=streamer)
                    )

                if settings.claim_moments is True:
                    self.ws_pool.submit(
                        PubsubTopic("community-moments-channel-v1", streamer=streamer)
                    )

                if settings.community_goals is True:
                    self.ws_pool.submit(
                        PubsubTopic("community-points-channel-v1", streamer=streamer)
                    )

            refresh_context = time.time()
            while self.running:
                default_sleep = random.uniform(20, 60)
                next_due_times = []
                for streamer in self.streamers:
                    if streamer.username in explicit_streamers_usernames:
                        continue
                    due_at = next_context_check_at.get(streamer.username, 0)
                    if due_at != 0:
                        next_due_times.append(due_at)
                    if streamer.auto_redeem_next_check_at != 0:
                        next_due_times.append(streamer.auto_redeem_next_check_at)

                if len(next_due_times) > 0:
                    earliest_due = min(next_due_times)
                    wait_for = max(0.0, earliest_due - time.time())
                    # Wake up close to reward cooldown/context deadlines.
                    sleep_for = min(default_sleep, max(1.0, wait_for))
                else:
                    sleep_for = default_sleep

                self.wakeup_event.wait(timeout=sleep_for)
                self.wakeup_event.clear()
                # Do an external control for WebSocket. Check if the thread is running
                # Check if is not None because maybe we have already created a new connection on array+1 and now index is None
                for index in range(0, len(self.ws_pool.ws)):
                    if (
                        self.ws_pool.ws[index].is_reconnecting is False
                        and self.ws_pool.ws[index].elapsed_last_ping() > 10
                        and internet_connection_available() is True
                    ):
                        logger.info(
                            f"#{index} - The last PING was sent more than 10 minutes ago. Reconnecting to the WebSocket..."
                        )
                        WebSocketsPool.handle_reconnection(self.ws_pool.ws[index])

                if ((time.time() - refresh_context) // 60) >= 30:
                    refresh_context = time.time()
                    for index in range(0, len(self.streamers)):
                        streamer = self.streamers[index]
                        if streamer.username in explicit_streamers_usernames:
                            continue
                        if streamer.is_online:
                            self.twitch.load_channel_points_context(
                                streamer, include_rewards=False
                            )
                            interval = streamer_context_interval.get(streamer.username, 60)
                            next_context_check_at[streamer.username] = time.time() + interval
                else:
                    for index in range(0, len(self.streamers)):
                        streamer = self.streamers[index]
                        if streamer.username in explicit_streamers_usernames:
                            continue
                        settings = streamer.settings
                        if settings is None:
                            continue
                        has_auto_redeem_targets = (
                            len(settings.auto_redeem_reward_ids or []) > 0
                            or len(settings.auto_redeem_reward_titles or []) > 0
                        )
                        # Followers keep the regular context refresh cadence.
                        due_at = next_context_check_at.get(streamer.username, 0)
                        if due_at != 0 and time.time() >= due_at:
                            self.twitch.load_channel_points_context(
                                streamer, include_rewards=False
                            )
                            interval = streamer_context_interval.get(streamer.username, 60)
                            next_context_check_at[streamer.username] = time.time() + interval

                        if (
                            streamer.is_online
                            and
                            has_auto_redeem_targets
                            and streamer.auto_redeem_next_check_at != 0
                            and time.time() >= streamer.auto_redeem_next_check_at
                        ):
                            # Reset before request to avoid tight loops on failures.
                            streamer.auto_redeem_next_check_at = 0
                            self.twitch.load_channel_points_context(streamer)

    def end(self, signum, frame):
        if not self.running:
            return
        
        logger.info("CTRL+C Detected! Please wait just a moment!")

        for streamer in self.streamers:
            settings = streamer.settings
            if (
                streamer.irc_chat is not None
                and settings is not None
                and settings.chat != ChatPresence.NEVER
            ):
                streamer.leave_chat()
                if streamer.irc_chat.is_alive() is True:
                    streamer.irc_chat.join()

        self.running = self.twitch.running = False
        self.wakeup_event.set()
        if self.ws_pool is not None:
            self.ws_pool.end()

        if self.minute_watcher_thread is not None:
            self.minute_watcher_thread.join()

        if self.sync_campaigns_thread is not None:
            self.sync_campaigns_thread.join()

        # Check if all the mutex are unlocked.
        # Prevent breaks of .json file
        for streamer in self.streamers:
            if streamer.mutex.locked():
                streamer.mutex.acquire()
                streamer.mutex.release()

        self.__print_report()

        # Stop the queue listener to make sure all messages have been logged
        self.queue_listener.stop()

        sys.exit(0)

    def __print_report(self):
        print("\n")
        logger.info(
            f"Ending session: '{self.session_id}'", extra={"emoji": ":stop_sign:"}
        )
        if self.logs_file is not None:
            logger.info(
                f"Logs file: {self.logs_file}", extra={"emoji": ":page_facing_up:"}
            )
        session_duration = (
            datetime.now() - self.start_datetime
            if self.start_datetime is not None
            else "unknown"
        )
        logger.info(
            f"Duration {session_duration}",
            extra={"emoji": ":hourglass:"},
        )

        if not Settings.logger.less and self.events_predictions != {}:
            print("")
            for event_id in self.events_predictions:
                event = self.events_predictions[event_id]
                if (
                    event.bet_confirmed is True
                    and event.streamer.settings.make_predictions is True
                ):
                    logger.info(
                        f"{event.streamer.settings.bet}",
                        extra={"emoji": ":wrench:"},
                    )
                    if event.streamer.settings.bet.filter_condition is not None:
                        logger.info(
                            f"{event.streamer.settings.bet.filter_condition}",
                            extra={"emoji": ":pushpin:"},
                        )
                    logger.info(
                        f"{event.print_recap()}",
                        extra={"emoji": ":bar_chart:"},
                    )

        print("")
        for streamer_index in range(0, len(self.streamers)):
            if self.streamers[streamer_index].history != {}:
                gained = (
                    self.streamers[streamer_index].channel_points
                    - self.original_streamers[streamer_index]
                )
                
                from colorama import Fore
                streamer_highlight = Fore.YELLOW
                
                streamer_gain = (
                    f"{streamer_highlight}{self.streamers[streamer_index]}{Fore.RESET}, Total Points Gained: {_millify(gained)}"
                    if Settings.logger.less
                    else f"{streamer_highlight}{repr(self.streamers[streamer_index])}{Fore.RESET}, Total Points Gained (after farming - before farming): {_millify(gained)}"
                )
                
                indent = ' ' * 25
                streamer_history = '\n'.join(f"{indent}{history}" for history in self.streamers[streamer_index].print_history().split('; ')) 
                
                logger.info(
                    f"{streamer_gain}\n{streamer_history}",
                    extra={"emoji": ":moneybag:"},
                )
