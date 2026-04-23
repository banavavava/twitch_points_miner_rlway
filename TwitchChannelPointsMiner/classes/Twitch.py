# For documentation on Twitch GraphQL API see:
# https://www.apollographql.com/docs/
# https://github.com/mauricew/twitch-graphql-api
# Full list of available methods: https://azr.ivr.fi/schema/query.doc.html (a bit outdated)


import copy
import logging
import os
import random
import re
import string
import time
import requests
import validators
import json
from datetime import datetime, timezone

from pathlib import Path
from secrets import choice, token_hex
from typing import Dict, Any, Callable, Optional
# from urllib.parse import quote
# from base64 import urlsafe_b64decode
# from datetime import datetime

from TwitchChannelPointsMiner.classes.entities.Campaign import Campaign
from TwitchChannelPointsMiner.classes.entities.CommunityGoal import CommunityGoal
from TwitchChannelPointsMiner.classes.entities.Drop import Drop
from TwitchChannelPointsMiner.classes.Exceptions import (
    StreamerDoesNotExistException,
    StreamerIsOfflineException,
)
from TwitchChannelPointsMiner.classes.Settings import (
    Events,
    FollowersOrder,
    Priority,
    Settings,
)
from TwitchChannelPointsMiner.classes.TwitchLogin import TwitchLogin
from TwitchChannelPointsMiner.constants import (
    CLIENT_ID,
    CLIENT_VERSION,
    URL,
    GQLOperations,
)
from TwitchChannelPointsMiner.utils import (
    _millify,
    create_chunks,
    internet_connection_available,
)

logger = logging.getLogger(__name__)
JsonType = Dict[str, Any]


class Twitch(object):
    __slots__ = [
        "cookies_file",
        "user_agent",
        "twitch_login",
        "running",
        "device_id",
        # "integrity",
        # "integrity_expire",
        "client_session",
        "client_version",
        "twilight_build_id_pattern",
        "wake_main_loop",
    ]

    def __init__(self, username, user_agent, password=None):
        cookies_path = os.path.join(Path().absolute(), "cookies")
        Path(cookies_path).mkdir(parents=True, exist_ok=True)
        self.cookies_file = os.path.join(cookies_path, f"{username}.pkl")
        self.user_agent = user_agent
        self.device_id = "".join(
            choice(string.ascii_letters + string.digits) for _ in range(32)
        )
        self.twitch_login = TwitchLogin(
            CLIENT_ID, self.device_id, username, self.user_agent, password=password
        )
        self.running = True
        # self.integrity = None
        # self.integrity_expire = 0
        self.client_session = token_hex(16)
        self.client_version = CLIENT_VERSION
        self.twilight_build_id_pattern = re.compile(
            r'window\.__twilightBuildID\s*=\s*"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"'
        )
        self.wake_main_loop: Optional[Callable[[], None]] = None

    def login(self):
        if not os.path.isfile(self.cookies_file):
            if self.twitch_login.login_flow():
                self.twitch_login.save_cookies(self.cookies_file)
        else:
            self.twitch_login.load_cookies(self.cookies_file)
            self.twitch_login.set_token(self.twitch_login.get_auth_token())

    # === STREAMER / STREAM / INFO === #
    def update_stream(self, streamer, force=False):
        if force is True or streamer.stream.update_required() is True:
            stream_info = self.get_stream_info(streamer)
            if stream_info is not None:
                streamer.stream.update(
                    broadcast_id=stream_info["stream"]["id"],
                    title=stream_info["broadcastSettings"]["title"],
                    game=stream_info["broadcastSettings"]["game"],
                    tags=stream_info["stream"]["tags"],
                    viewers_count=stream_info["stream"]["viewersCount"],
                )

                event_properties = {
                    "channel_id": streamer.channel_id,
                    "broadcast_id": streamer.stream.broadcast_id,
                    "player": "site",
                    "user_id": self.twitch_login.get_user_id(),
                    "live": True,
                    "channel": streamer.username,
                }

                if (
                    streamer.stream.game_name() is not None
                    and streamer.stream.game_id() is not None
                    and streamer.settings.claim_drops is True
                ):
                    event_properties["game"] = streamer.stream.game_name()
                    event_properties["game_id"] = streamer.stream.game_id()
                    # Update also the campaigns_ids so we are sure to tracking the correct campaign
                    streamer.stream.campaigns_ids = (
                        self.__get_campaign_ids_from_streamer(streamer)
                    )

                streamer.stream.payload = [
                    {"event": "minute-watched", "properties": event_properties}
                ]

    def get_spade_url(self, streamer):
        try:
            # fixes AttributeError: 'NoneType' object has no attribute 'group'
            # headers = {"User-Agent": self.user_agent}
            from TwitchChannelPointsMiner.constants import USER_AGENTS

            headers = {"User-Agent": USER_AGENTS["Linux"]["FIREFOX"]}

            main_page_request = requests.get(
                streamer.streamer_url, headers=headers)
            response = main_page_request.text
            # logger.info(response)
            regex_settings = "(https://static.twitchcdn.net/config/settings.*?js|https://assets.twitch.tv/config/settings.*?.js)"
            settings_match = re.search(regex_settings, response)
            if settings_match is None:
                logger.error("Unable to extract settings_url from streamer page")
                return
            settings_url = settings_match.group(1)

            settings_request = requests.get(settings_url, headers=headers)
            response = settings_request.text
            regex_spade = '"spade_url":"(.*?)"'
            spade_match = re.search(regex_spade, response)
            if spade_match is None:
                logger.error("Unable to extract spade_url from settings script")
                return
            streamer.stream.spade_url = spade_match.group(1)
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Something went wrong during extraction of 'spade_url': {e}")

    def get_broadcast_id(self, streamer):
        json_data = copy.deepcopy(GQLOperations.WithIsStreamLiveQuery)
        json_data["variables"] = {"id": streamer.channel_id}
        response = self.post_gql_request(json_data)
        if response != {}:
            stream = response["data"]["user"]["stream"]
            if stream is not None:
                return stream["id"]
            else:
                raise StreamerIsOfflineException

    def get_stream_info(self, streamer):
        json_data = copy.deepcopy(
            GQLOperations.VideoPlayerStreamInfoOverlayChannel)
        json_data["variables"] = {"channel": streamer.username}
        response = self.post_gql_request(json_data)
        if response != {}:
            if response["data"]["user"]["stream"] is None:
                raise StreamerIsOfflineException
            else:
                return response["data"]["user"]

    def check_streamer_online(self, streamer):
        offline_recheck_delay = (
            4 if streamer.username == "saintsakura" else 60
        )
        if time.time() < streamer.offline_at + offline_recheck_delay:
            return

        was_online = streamer.is_online
        if streamer.is_online is False:
            try:
                self.get_spade_url(streamer)
                # Force a real live-status check when streamer is currently offline.
                # Without this, a fresh cached stream snapshot may cause false online.
                self.update_stream(streamer, force=True)
            except StreamerIsOfflineException:
                streamer.set_offline()
            else:
                streamer.set_online()
        else:
            try:
                self.update_stream(streamer)
            except StreamerIsOfflineException:
                streamer.set_offline()

        # Trigger an immediate auto-redeem pass when streamer comes online.
        if was_online is False and streamer.is_online is True:
            streamer.auto_redeemed_rewards.clear()
            streamer.auto_redeem_next_check_at = time.time()
            if callable(self.wake_main_loop):
                self.wake_main_loop()

    def get_channel_id(self, streamer_username):
        json_data = copy.deepcopy(GQLOperations.GetIDFromLogin)
        json_data["variables"]["login"] = streamer_username
        json_response = self.post_gql_request(json_data)
        if (
            "data" not in json_response
            or "user" not in json_response["data"]
            or json_response["data"]["user"] is None
        ):
            raise StreamerDoesNotExistException
        else:
            return json_response["data"]["user"]["id"]

    def get_followers(
        self, limit: int = 100, order: FollowersOrder = FollowersOrder.ASC
    ):
        json_data = copy.deepcopy(GQLOperations.ChannelFollows)
        json_data["variables"] = {"limit": limit, "order": str(order)}
        has_next = True
        last_cursor = ""
        follows = []
        while has_next is True:
            json_data["variables"]["cursor"] = last_cursor
            json_response = self.post_gql_request(json_data)
            try:
                follows_response = json_response["data"]["user"]["follows"]
                last_cursor = None
                for f in follows_response["edges"]:
                    follows.append(f["node"]["login"].lower())
                    last_cursor = f["cursor"]

                has_next = follows_response["pageInfo"]["hasNextPage"]
            except KeyError:
                return []
        return follows

    def update_raid(self, streamer, raid):
        if streamer.raid != raid:
            streamer.raid = raid
            json_data = copy.deepcopy(GQLOperations.JoinRaid)
            json_data["variables"] = {"input": {"raidID": raid.raid_id}}
            self.post_gql_request(json_data)

            logger.info(
                f"Joining raid from {streamer} to {raid.target_login}!",
                extra={"emoji": ":performing_arts:",
                       "event": Events.JOIN_RAID},
            )

    def viewer_is_mod(self, streamer):
        json_data = copy.deepcopy(GQLOperations.ModViewChannelQuery)
        json_data["variables"] = {"channelLogin": streamer.username}
        response = self.post_gql_request(json_data)
        try:
            streamer.viewer_is_mod = response["data"]["user"]["self"]["isModerator"]
        except (ValueError, KeyError):
            streamer.viewer_is_mod = False

    # === 'GLOBALS' METHODS === #
    # Create chunk of sleep of speed-up the break loop after CTRL+C
    def __chuncked_sleep(self, seconds, chunk_size=3):
        sleep_time = max(seconds, 0) / chunk_size
        for i in range(0, chunk_size):
            time.sleep(sleep_time)
            if self.running is False:
                break

    def __check_connection_handler(self, chunk_size):
        # The success rate It's very hight usually. Why we have failed?
        # Check internet connection ...
        while internet_connection_available() is False:
            random_sleep = random.randint(1, 3)
            logger.warning(
                f"No internet connection available! Retry after {random_sleep}m"
            )
            self.__chuncked_sleep(random_sleep * 60, chunk_size=chunk_size)

    def post_gql_request(self, json_data):
        try:
            response = requests.post(
                GQLOperations.url,
                json=json_data,
                headers={
                    "Authorization": f"OAuth {self.twitch_login.get_auth_token()}",
                    "Client-Id": CLIENT_ID,
                    # "Client-Integrity": self.post_integrity(),
                    "Client-Session-Id": self.client_session,
                    "Client-Version": self.update_client_version(),
                    "User-Agent": self.user_agent,
                    "X-Device-Id": self.device_id,
                },
            )
            logger.debug(
                f"Data: {json_data}, Status code: {response.status_code}, Content: {response.text}"
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error with GQLOperations ({json_data['operationName']}): {e}"
            )
            return {}

    # Request for Integrity Token
    # Twitch needs Authorization, Client-Id, X-Device-Id to generate JWT which is used for authorize gql requests
    # Regenerate Integrity Token 5 minutes before expire
    """def post_integrity(self):
        if (
            self.integrity_expire - datetime.now().timestamp() * 1000 > 5 * 60 * 1000
            and self.integrity is not None
        ):
            return self.integrity
        try:
            response = requests.post(
                GQLOperations.integrity_url,
                json={},
                headers={
                    "Authorization": f"OAuth {self.twitch_login.get_auth_token()}",
                    "Client-Id": CLIENT_ID,
                    "Client-Session-Id": self.client_session,
                    "Client-Version": self.update_client_version(),
                    "User-Agent": self.user_agent,
                    "X-Device-Id": self.device_id,
                },
            )
            logger.debug(
                f"Data: [], Status code: {response.status_code}, Content: {response.text}"
            )
            self.integrity = response.json().get("token", None)
            # logger.info(f"integrity: {self.integrity}")

            if self.isBadBot(self.integrity) is True:
                logger.info(
                    "Uh-oh, Twitch has detected this miner as a \"Bad Bot\". Don't worry.")

            self.integrity_expire = response.json().get("expiration", 0)
            # logger.info(f"integrity_expire: {self.integrity_expire}")
            return self.integrity
        except requests.exceptions.RequestException as e:
            logger.error(f"Error with post_integrity: {e}")
            return self.integrity

    # verify the integrity token's contents for the "is_bad_bot" flag
    def isBadBot(self, integrity):
        stripped_token: str = self.integrity.split('.')[2] + "=="
        messy_json: str = urlsafe_b64decode(
            stripped_token.encode()).decode(errors="ignore")
        match = re.search(r'(.+)(?<="}).+$', messy_json)
        if match is None:
            # raise MinerException("Unable to parse the integrity token")
            logger.info("Unable to parse the integrity token. Don't worry.")
            return
        decoded_header = json.loads(match.group(1))
        # logger.info(f"decoded_header: {decoded_header}")
        if decoded_header.get("is_bad_bot", "false") != "false":
            return True
        else:
            return False"""

    def update_client_version(self):
        try:
            response = requests.get(URL)
            if response.status_code != 200:
                logger.debug(
                    f"Error with update_client_version: {response.status_code}"
                )
                return self.client_version
            matcher = re.search(self.twilight_build_id_pattern, response.text)
            if not matcher:
                logger.debug("Error with update_client_version: no match")
                return self.client_version
            self.client_version = matcher.group(1)
            logger.debug(f"Client version: {self.client_version}")
            return self.client_version
        except requests.exceptions.RequestException as e:
            logger.error(f"Error with update_client_version: {e}")
            return self.client_version

    def send_minute_watched_events(self, streamers, priority, chunk_size=3):
        while self.running:
            try:
                streamers_index = [
                    i
                    for i in range(0, len(streamers))
                    if streamers[i].is_online is True
                    and (
                        streamers[i].online_at == 0
                        or (time.time() - streamers[i].online_at) > 30
                    )
                ]

                for index in streamers_index:
                    if (streamers[index].stream.update_elapsed() / 60) > 10:
                        # Why this user It's currently online but the last updated was more than 10minutes ago?
                        # Please perform a manually update and check if the user it's online
                        self.check_streamer_online(streamers[index])

                """
                Twitch has a limit - you can't watch more than 2 channels at one time.
                We'll take the first two streamers from the final list as they have the highest priority.
                """
                max_watch_amount = 2
                streamers_watching = set()

                def remaining_watch_amount():
                    return max_watch_amount - len(streamers_watching)

                for prior in priority:
                    if remaining_watch_amount() <= 0:
                        break

                    if prior == Priority.ORDER:
                        # Get the first 2 items, they are already in order
                        streamers_watching.update(streamers_index[:remaining_watch_amount()])

                    elif prior in [Priority.POINTS_ASCENDING, Priority.POINTS_DESCENDING]:
                        items = [
                            {
                                "points": streamers[index].channel_points,
                                "index": index
                            }
                            for index in streamers_index
                        ]
                        items = sorted(
                            items,
                            key=lambda x: x["points"],
                            reverse=(
                                True if prior == Priority.POINTS_DESCENDING else False
                            ),
                        )
                        streamers_watching.update([item["index"] for item in items][:remaining_watch_amount()])

                    elif prior == Priority.STREAK:
                        """
                        Check if we need need to change priority based on watch streak
                        Viewers receive points for returning for x consecutive streams.
                        Each stream must be at least 10 minutes long and it must have been at least 30 minutes since the last stream ended.
                        Watch at least 6m for get the +10
                        """
                        for index in streamers_index:
                            if (
                                streamers[index].settings.watch_streak is True
                                and streamers[index].stream.watch_streak_missing is True
                                and (
                                    streamers[index].offline_at == 0
                                    or (
                                        (time.time() -
                                         streamers[index].offline_at)
                                        // 60
                                    )
                                    > 30
                                )
                                # fix #425
                                and streamers[index].stream.minute_watched < 7
                            ):
                                streamers_watching.add(index)
                                if remaining_watch_amount() <= 0:
                                    break

                    elif prior == Priority.DROPS:
                        for index in streamers_index:
                            if streamers[index].drops_condition() is True:
                                streamers_watching.add(index)
                                if remaining_watch_amount() <= 0:
                                    break

                    elif prior == Priority.SUBSCRIBED:
                        streamers_with_multiplier = [
                            index
                            for index in streamers_index
                            if streamers[index].viewer_has_points_multiplier()
                        ]
                        streamers_with_multiplier = sorted(
                            streamers_with_multiplier,
                            key=lambda x: streamers[x].total_points_multiplier(
                            ),
                            reverse=True,
                        )
                        streamers_watching.update(streamers_with_multiplier[:remaining_watch_amount()])

                streamers_watching = list(streamers_watching)[:max_watch_amount]

                for index in streamers_watching:
                    # next_iteration = time.time() + 60 / len(streamers_watching)
                    next_iteration = time.time() + 20 / len(streamers_watching)

                    try:
                        ####################################
                        # Start of fix for 2024/5 API Change
                        # Create the JSON data for the GraphQL request
                        json_data = copy.deepcopy(
                            GQLOperations.PlaybackAccessToken)
                        json_data["variables"] = {
                            "login": streamers[index].username,
                            "isLive": True,
                            "isVod": False,
                            "vodID": "",
                            "playerType": "site"
                            # "playerType": "picture-by-picture",
                        }

                        # Get signature and value using the post_gql_request method
                        try:
                            responsePlaybackAccessToken = self.post_gql_request(
                                json_data)
                            logger.debug(
                                f"Sent PlaybackAccessToken request for {streamers[index]}")

                            if 'data' not in responsePlaybackAccessToken:
                                logger.error(
                                    f"Invalid response from Twitch: {responsePlaybackAccessToken}")
                                continue

                            streamPlaybackAccessToken = responsePlaybackAccessToken["data"].get(
                                'streamPlaybackAccessToken', {})
                            signature = streamPlaybackAccessToken.get(
                                "signature")
                            value = streamPlaybackAccessToken.get("value")

                            if not signature or not value:
                                logger.error(
                                    f"Missing signature or value in Twitch response: {responsePlaybackAccessToken}")
                                continue

                        except Exception as e:
                            logger.error(
                                f"Error fetching PlaybackAccessToken for {streamers[index]}: {str(e)}")
                            continue

                        # encoded_value = quote(json.dumps(value))

                        # Construct the URL for the broadcast qualities
                        RequestBroadcastQualitiesURL = f"https://usher.ttvnw.net/api/channel/hls/{streamers[index].username}.m3u8?sig={signature}&token={value}"

                        # Get list of video qualities
                        responseBroadcastQualities = requests.get(
                            RequestBroadcastQualitiesURL,
                            headers={"User-Agent": self.user_agent},
                            timeout=20,
                        )  # timeout=60
                        logger.debug(
                            f"Send RequestBroadcastQualitiesURL request for {streamers[index]} - Status code: {responseBroadcastQualities.status_code}"
                        )
                        if responseBroadcastQualities.status_code != 200:
                            continue
                        BroadcastQualities = responseBroadcastQualities.text

                        # Just takes the last line, which should be the URL for the lowest quality
                        BroadcastLowestQualityURL = BroadcastQualities.split(
                            "\n")[-1]
                        if not validators.url(BroadcastLowestQualityURL):
                            continue

                        # Get list of video URLs
                        responseStreamURLList = requests.get(
                            BroadcastLowestQualityURL,
                            headers={"User-Agent": self.user_agent},
                            timeout=20,
                        )  # timeout=60
                        logger.debug(
                            f"Send BroadcastLowestQualityURL request for {streamers[index]} - Status code: {responseStreamURLList.status_code}"
                        )
                        if responseStreamURLList.status_code != 200:
                            continue
                        StreamURLList = responseStreamURLList.text

                        # Just takes the last line, which should be the URL for the lowest quality
                        StreamLowestQualityURL = StreamURLList.split("\n")[-2]
                        if not validators.url(StreamLowestQualityURL):
                            continue

                        # Perform a HEAD request to simulate watching the stream
                        responseStreamLowestQualityURL = requests.head(
                            StreamLowestQualityURL,
                            headers={"User-Agent": self.user_agent},
                            timeout=20,
                        )  # timeout=60
                        logger.debug(
                            f"Send StreamLowestQualityURL request for {streamers[index]} - Status code: {responseStreamLowestQualityURL.status_code}"
                        )
                        if responseStreamLowestQualityURL.status_code != 200:
                            continue
                        # End of fix for 2024/5 API Change
                        ##################################
                        response = requests.post(
                            streamers[index].stream.spade_url,
                            data=streamers[index].stream.encode_payload(),
                            headers={"User-Agent": self.user_agent},
                            # timeout=60,
                            timeout=20,
                        )
                        logger.debug(
                            f"Send minute watched request for {streamers[index]} - Status code: {response.status_code}"
                        )
                        if response.status_code == 204:
                            streamers[index].stream.update_minute_watched()

                            """
                            Remember, you can only earn progress towards a time-based Drop on one participating channel at a time.  [ ! ! ! ]
                            You can also check your progress towards Drops within a campaign anytime by viewing the Drops Inventory.
                            For time-based Drops, if you are unable to claim the Drop in time, you will be able to claim it from the inventory page until the Drops campaign ends.
                            """

                            for campaign in streamers[index].stream.campaigns:
                                for drop in campaign.drops:
                                    # We could add .has_preconditions_met condition inside is_printable
                                    if (
                                        drop.has_preconditions_met is not False
                                        and drop.is_printable is True
                                    ):
                                        drop_messages = [
                                            f"{streamers[index]} is streaming {streamers[index].stream}",
                                            f"Campaign: {campaign}",
                                            f"Drop: {drop}",
                                            f"{drop.progress_bar()}",
                                        ]
                                        for single_line in drop_messages:
                                            logger.info(
                                                single_line,
                                                extra={
                                                    "event": Events.DROP_STATUS,
                                                    "skip_telegram": True,
                                                    "skip_discord": True,
                                                    "skip_webhook": True,
                                                    "skip_matrix": True,
                                                    "skip_gotify": True
                                                },
                                            )

                                        if Settings.logger.telegram is not None:
                                            Settings.logger.telegram.send(
                                                "\n".join(drop_messages),
                                                Events.DROP_STATUS,
                                            )

                                        if Settings.logger.discord is not None:
                                            Settings.logger.discord.send(
                                                "\n".join(drop_messages),
                                                Events.DROP_STATUS,
                                            )
                                        if Settings.logger.webhook is not None:
                                            Settings.logger.webhook.send(
                                                "\n".join(drop_messages),
                                                Events.DROP_STATUS,
                                            )
                                        if Settings.logger.gotify is not None:
                                            Settings.logger.gotify.send(
                                                "\n".join(drop_messages),
                                                Events.DROP_STATUS,
                                            )

                    except requests.exceptions.ConnectionError as e:
                        logger.error(
                            f"Error while trying to send minute watched: {e}")
                        self.__check_connection_handler(chunk_size)
                    except requests.exceptions.Timeout as e:
                        logger.error(
                            f"Error while trying to send minute watched: {e}")

                    self.__chuncked_sleep(
                        next_iteration - time.time(), chunk_size=chunk_size
                    )

                if streamers_watching == []:
                    # self.__chuncked_sleep(60, chunk_size=chunk_size)
                    self.__chuncked_sleep(20, chunk_size=chunk_size)
            except Exception:
                logger.error(
                    "Exception raised in send minute watched", exc_info=True)

    # === CHANNEL POINTS / PREDICTION === #
    def __reward_cost(self, reward):
        return reward.get("cost") or reward.get("defaultCost")

    def __parse_twitch_timestamp(self, dt_str):
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            return None

    def __schedule_auto_redeem_check(self, streamer, timestamp):
        if timestamp is None:
            return
        if streamer.auto_redeem_next_check_at == 0:
            streamer.auto_redeem_next_check_at = timestamp
        else:
            streamer.auto_redeem_next_check_at = min(
                streamer.auto_redeem_next_check_at, timestamp
            )

    def __has_auto_redeem_targets(self, settings):
        return settings is not None and settings.has_auto_redeem_targets()

    def __resolve_auto_redeem_targets(self, settings, custom_rewards):
        redeem_titles = settings.normalized_auto_redeem_reward_titles()

        by_id = {
            reward.get("id"): reward
            for reward in custom_rewards
            if reward.get("id") is not None
        }
        by_title_exact = {
            (reward.get("title") or "").strip().lower(): reward
            for reward in custom_rewards
        }

        targets = []
        for reward_id in settings.auto_redeem_reward_ids:
            reward = by_id.get(reward_id)
            if reward is not None:
                targets.append(reward)

        for reward_title in redeem_titles:
            normalized_title = (reward_title or "").strip().lower()
            if normalized_title == "":
                continue

            reward = by_title_exact.get(normalized_title)
            if reward is not None:
                targets.append(reward)
                continue

            for candidate in custom_rewards:
                candidate_title = (candidate.get("title") or "").strip().lower()
                if normalized_title in candidate_title:
                    targets.append(candidate)
                    break

        deduped = []
        seen = set()
        for reward in targets:
            reward_id = reward.get("id")
            if reward_id in seen:
                continue
            seen.add(reward_id)
            deduped.append(reward)
        return deduped

    def __is_reward_max_per_stream_enabled(self, reward):
        max_per_stream_setting = reward.get("maxPerStreamSetting") or {}
        if (
            isinstance(max_per_stream_setting, dict) is False
            or max_per_stream_setting.get("isEnabled") is not True
        ):
            return False
        try:
            return int(max_per_stream_setting.get("maxPerStream") or 0) > 0
        except (TypeError, ValueError):
            return False

    def __reward_cooldown_seconds(self, reward):
        cooldown_setting = reward.get("globalCooldownSetting") or {}
        if (
            isinstance(cooldown_setting, dict) is False
            or cooldown_setting.get("isEnabled") is not True
        ):
            return 60
        try:
            seconds = int(cooldown_setting.get("globalCooldownSeconds") or 0)
            return seconds if seconds > 0 else 60
        except (TypeError, ValueError):
            return 60

    def __auto_redeem_reward_label(self, reward):
        return (
            f"title='{reward.get('title')}' "
            f"id={reward.get('id')} cost={self.__reward_cost(reward)}"
        )

    def __log_auto_redeem_info(self, streamer, reward, message):
        logger.info(
            f"[auto-redeem] streamer={streamer.username} "
            f"{self.__auto_redeem_reward_label(reward)} :: {message}"
        )

    def __log_auto_redeem_debug(self, streamer, reward, message):
        logger.debug(
            f"[auto-redeem][debug] streamer={streamer.username} "
            f"title={reward.get('title')} "
            f"id={reward.get('id')} "
            f"cost={self.__reward_cost(reward)} "
            f"in_stock={reward.get('isInStock')} "
            f"cooldown_expires_at={reward.get('cooldownExpiresAt')} "
            f"cooldown_seconds={reward.get('cooldownSeconds')} "
            f"max_per_stream={((reward.get('maxPerStreamSetting') or {}).get('maxPerStream'))} "
            f"redeemed_this_stream={reward.get('redemptionsRedeemedCurrentStream')} "
            f"next_check_at={streamer.auto_redeem_next_check_at} "
            f"non_max_next_attempt={streamer.auto_redeem_non_max_next_attempts.get(reward.get('id'))} "
            f":: {message}"
        )

    def prime_auto_redeem_cache(self, streamer):
        streamer.auto_redeem_cache_ready = True
        existing_non_max_next_attempts = dict(streamer.auto_redeem_non_max_next_attempts)
        streamer.auto_redeem_cached_rewards = []

        settings = streamer.settings
        if not self.__has_auto_redeem_targets(settings):
            return

        json_data = copy.deepcopy(GQLOperations.ChannelPointsContext)
        json_data["variables"] = {"channelLogin": streamer.username}
        response = self.post_gql_request(json_data)
        if response == {}:
            return
        if response["data"]["community"] is None:
            raise StreamerDoesNotExistException

        channel = response["data"]["community"]["channel"]
        community_points = channel["self"]["communityPoints"]
        streamer.channel_points = community_points["balance"]
        streamer.activeMultipliers = community_points["activeMultipliers"]

        if community_points["availableClaim"] is not None:
            self.claim_bonus(streamer, community_points["availableClaim"]["id"])

        cps = channel.get("communityPointsSettings", {})
        custom_rewards = cps.get("customRewards", []) if cps else []
        targets = self.__resolve_auto_redeem_targets(settings, custom_rewards)
        logger.debug(
            f"[auto-redeem][debug] streamer={streamer.username} "
            f"cache refresh resolved {len(targets)} target reward(s)"
        )

        cached_rewards = []
        current_reward_ids = set()
        for reward in targets:
            reward_id = reward.get("id")
            if reward_id is None:
                continue
            current_reward_ids.add(reward_id)
            cooldown_seconds = self.__reward_cooldown_seconds(reward)
            cached_reward = {
                "id": reward_id,
                "title": reward.get("title"),
                "cost": reward.get("cost"),
                "defaultCost": reward.get("defaultCost"),
                "pricingType": reward.get("pricingType"),
                "prompt": reward.get("prompt"),
                "isUserInputRequired": reward.get("isUserInputRequired"),
                "maxPerStreamSetting": reward.get("maxPerStreamSetting"),
                "redemptionsRedeemedCurrentStream": reward.get("redemptionsRedeemedCurrentStream"),
                "globalCooldownSetting": reward.get("globalCooldownSetting"),
                "cooldownExpiresAt": reward.get("cooldownExpiresAt"),
                "cooldownSeconds": cooldown_seconds,
                "isInStock": reward.get("isInStock"),
            }
            cached_rewards.append(cached_reward)
            self.__log_auto_redeem_debug(
                streamer, cached_reward, "reward added to fast auto-redeem cache"
            )

            if (
                streamer.username == "saintsakura"
                and self.__is_reward_max_per_stream_enabled(reward) is False
                and reward_id not in existing_non_max_next_attempts
            ):
                cooldown_ts = self.__parse_twitch_timestamp(reward.get("cooldownExpiresAt"))
                if cooldown_ts is not None:
                    # Use Twitch cooldown boundary directly (do not add extra full cooldown).
                    existing_non_max_next_attempts[reward_id] = cooldown_ts + 1
                elif reward.get("isInStock") is not True:
                    existing_non_max_next_attempts[reward_id] = time.time() + cooldown_seconds

        streamer.auto_redeem_non_max_next_attempts = {
            reward_id: next_due
            for reward_id, next_due in existing_non_max_next_attempts.items()
            if reward_id in current_reward_ids
        }
        streamer.auto_redeem_cached_rewards = cached_rewards

    def __is_reward_exhausted_for_current_stream(self, reward):
        max_per_stream_setting = reward.get("maxPerStreamSetting") or {}
        if (
            isinstance(max_per_stream_setting, dict) is False
            or max_per_stream_setting.get("isEnabled") is not True
        ):
            return False

        try:
            max_per_stream = int(max_per_stream_setting.get("maxPerStream") or 0)
            redeemed_current_stream = int(
                reward.get("redemptionsRedeemedCurrentStream") or 0
            )
        except (TypeError, ValueError):
            return False

        return max_per_stream > 0 and redeemed_current_stream >= max_per_stream

    def __redeem_custom_reward(self, streamer, reward, text_input=None):
        silent_fast_mode = streamer.username == "saintsakura"
        cost = self.__reward_cost(reward)
        if cost is None:
            if not silent_fast_mode:
                logger.warning(
                    f"Skip redeem for {streamer} reward {reward.get('id')}: missing cost"
                )
            return False, "MISSING_COST"

        json_data = copy.deepcopy(GQLOperations.RedeemCustomReward)
        json_data["variables"] = {
            "input": {
                "channelID": streamer.channel_id,
                "cost": int(cost),
                "pricingType": reward.get("pricingType") or "POINTS",
                "prompt": reward.get("prompt"),
                "rewardID": reward.get("id"),
                "title": reward.get("title"),
                "transactionID": token_hex(16),
            }
        }
        # Twitch may reject redemption with PROPERTIES_MISMATCH if textInput is sent
        # for rewards that do not require user input.
        if text_input and reward.get("isUserInputRequired") is True:
            json_data["variables"]["input"]["textInput"] = text_input
        elif text_input and reward.get("isUserInputRequired") is not True:
            if not silent_fast_mode:
                logger.debug(
                    "Skip textInput for reward '%s' (%s): isUserInputRequired=%s",
                    reward.get("title"),
                    reward.get("id"),
                    reward.get("isUserInputRequired"),
                )

        logger.debug(
            "[auto-redeem][debug] streamer=%s title=%s id=%s redeem request input=%s",
            streamer.username,
            reward.get("title"),
            reward.get("id"),
            json.dumps(json_data.get("variables", {}).get("input", {}), ensure_ascii=False),
        )

        response = self.post_gql_request(json_data)
        logger.debug(
            "[auto-redeem][debug] streamer=%s title=%s id=%s redeem response=%s",
            streamer.username,
            reward.get("title"),
            reward.get("id"),
            json.dumps(response, ensure_ascii=False),
        )
        if not silent_fast_mode:
            logger.debug(
                "RedeemCustomReward response for '%s' (%s): input=%s response=%s",
                reward.get("title"),
                reward.get("id"),
                json.dumps(json_data.get("variables", {}).get("input", {}), ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
            )

        gql_errors = response.get("errors")
        payload = (
            response.get("data", {}).get("redeemCommunityPointsCustomReward", {})
            if isinstance(response, dict)
            else {}
        )
        payload_error = payload.get("error") if isinstance(payload, dict) else None

        # Twitch may return HTTP 200 with business error inside payload.error.
        has_error = bool(gql_errors) or (payload_error is not None)
        if not has_error:
            self.__log_auto_redeem_info(streamer, reward, "redeem succeeded")
            logger.info(
                f"Auto redeemed reward '{reward.get('title')}' for {streamer}",
                extra={"emoji": ":ticket:", "event": Events.REWARD_REDEEMED},
            )
            return True, None

        error_code = (
            payload_error.get("code")
            if isinstance(payload_error, dict)
            else None
        )
        self.__log_auto_redeem_info(
            streamer,
            reward,
            f"redeem failed error_code={error_code} gql_errors={gql_errors}",
        )
        self.__log_auto_redeem_debug(
            streamer,
            reward,
            f"redeem failed full_response={json.dumps(response, ensure_ascii=False)}",
        )
        if not silent_fast_mode:
            logger.warning(
                f"Failed to auto redeem reward '{reward.get('title')}' for {streamer}. "
                f"error_code={error_code}, gql_errors={gql_errors}, response={response}",
                extra={"emoji": ":warning:", "event": Events.REWARD_FAILED},
            )
        if error_code is None and gql_errors:
            return False, "GQL_ERROR"
        return False, error_code

    def fast_auto_redeem_tick(self, streamer, trigger="periodic"):
        online_transition_mode = trigger == "online_transition"
        settings = streamer.settings
        if settings is None:
            streamer.auto_redeem_next_check_at = 0
            if online_transition_mode:
                logger.info(
                    f"[auto-redeem] {streamer.username} online trigger: skipped (missing settings)",
                    extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                )
            return

        if streamer.is_online is not True:
            streamer.auto_redeem_next_check_at = 0
            return

        self.prime_auto_redeem_cache(streamer)

        poll_interval = 3
        cached_rewards = streamer.auto_redeem_cached_rewards or []
        if len(cached_rewards) == 0:
            streamer.auto_redeem_next_check_at = 0
            if online_transition_mode:
                logger.info(
                    f"[auto-redeem] {streamer.username} online trigger: no cached targets",
                    extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                )
            return

        unavailable_codes = {
            "CUSTOM_REWARD_NOT_FOUND",
            "CUSTOM_REWARD_NOT_ENABLED",
            "CUSTOM_REWARD_NOT_IN_STOCK",
            "MAX_PER_STREAM",
            "MAX_PER_USER_PER_STREAM",
            "MAX_PER_USER_PER_DAY",
            "MAX_GLOBAL_REDEMPTIONS",
            "MAX_PER_STREAM_REACHED",
            "MAX_PER_USER_PER_STREAM_REACHED",
            "MAX_PER_USER_PER_DAY_REACHED",
            "MAX_GLOBAL_REDEMPTIONS_REACHED",
        }
        exhausted_codes = {
            "MAX_PER_STREAM",
            "MAX_PER_USER_PER_STREAM",
            "MAX_GLOBAL_REDEMPTIONS",
            "MAX_PER_STREAM_REACHED",
            "MAX_PER_USER_PER_STREAM_REACHED",
            "MAX_GLOBAL_REDEMPTIONS_REACHED",
        }

        has_max_targets = False
        has_non_max_targets = False
        max_eligible_targets = 0
        max_attempted_targets = 0
        max_unavailable_attempts = 0
        min_non_max_next_due = None
        attempted_targets = 0
        redeemed_targets = 0
        error_codes_seen = set()
        pretty_skip_logged = False

        for reward in cached_rewards:
            reward_id = reward.get("id")
            is_max_per_stream_reward = self.__is_reward_max_per_stream_enabled(reward)
            self.__log_auto_redeem_debug(
                streamer,
                reward,
                (
                    f"evaluate reward trigger={trigger} "
                    f"is_max_per_stream={is_max_per_stream_reward} "
                    f"channel_points={streamer.channel_points} "
                    f"already_redeemed={reward_id in streamer.auto_redeemed_rewards} "
                    f"already_exhausted={reward_id in streamer.auto_redeem_exhausted_rewards}"
                ),
            )

            if is_max_per_stream_reward:
                has_max_targets = True
            else:
                has_non_max_targets = True

            if is_max_per_stream_reward is False:
                next_allowed_at = streamer.auto_redeem_non_max_next_attempts.get(
                    reward_id
                )
                if next_allowed_at is None:
                    cooldown_ts = self.__parse_twitch_timestamp(
                        reward.get("cooldownExpiresAt")
                    )
                    if cooldown_ts is not None:
                        seed_due = cooldown_ts + 1
                    else:
                        seed_due = time.time() + int(
                            reward.get("cooldownSeconds") or 60
                        )
                    streamer.auto_redeem_non_max_next_attempts[reward_id] = seed_due
                    self.__log_auto_redeem_info(
                        streamer,
                        reward,
                        f"waiting for first eligible redeem time until {seed_due:.0f}",
                    )
                    if min_non_max_next_due is None or seed_due < min_non_max_next_due:
                        min_non_max_next_due = seed_due
                    continue

                if time.time() < next_allowed_at:
                    if (
                        min_non_max_next_due is None
                        or next_allowed_at < min_non_max_next_due
                    ):
                        min_non_max_next_due = next_allowed_at
                    self.__log_auto_redeem_debug(
                        streamer,
                        reward,
                        f"skip: cooldown gate active for {round(next_allowed_at - time.time(), 2)}s",
                    )
                    continue

            if (
                settings.auto_redeem_repeat is not True
                and reward_id in streamer.auto_redeemed_rewards
            ):
                self.__log_auto_redeem_debug(
                    streamer, reward, "skip: already redeemed in this stream"
                )
                continue

            if reward_id in streamer.auto_redeem_exhausted_rewards:
                self.__log_auto_redeem_debug(
                    streamer, reward, "skip: reward marked exhausted for this stream"
                )
                continue

            if is_max_per_stream_reward:
                max_eligible_targets += 1

            if streamer.channel_points < int(self.__reward_cost(reward) or 0):
                self.__log_auto_redeem_info(
                    streamer,
                    reward,
                    f"skip: not enough points have={streamer.channel_points} need={int(self.__reward_cost(reward) or 0)}",
                )
                if is_max_per_stream_reward is False and reward_id is not None:
                    next_due = time.time() + 60
                    streamer.auto_redeem_non_max_next_attempts[reward_id] = next_due
                    if min_non_max_next_due is None or next_due < min_non_max_next_due:
                        min_non_max_next_due = next_due
                continue

            self.__log_auto_redeem_info(streamer, reward, "attempt redeem")
            attempted_targets += 1
            if is_max_per_stream_reward:
                max_attempted_targets += 1

            redeemed, error_code = self.__redeem_custom_reward(
                streamer, reward, text_input=settings.auto_redeem_text
            )
            if redeemed is True:
                redeemed_targets += 1
                if settings.auto_redeem_repeat is not True:
                    streamer.auto_redeemed_rewards.add(reward_id)
                if is_max_per_stream_reward is False and reward_id is not None:
                    cooldown_seconds = int(reward.get("cooldownSeconds") or 60)
                    next_due = time.time() + cooldown_seconds
                    streamer.auto_redeem_non_max_next_attempts[reward_id] = next_due
                    if min_non_max_next_due is None or next_due < min_non_max_next_due:
                        min_non_max_next_due = next_due
                continue

            if error_code is not None:
                error_codes_seen.add(error_code)

            if (
                is_max_per_stream_reward
                and error_code in exhausted_codes
                and streamer.is_online
                and reward_id
            ):
                if reward_id not in streamer.auto_redeem_exhausted_rewards:
                    streamer.auto_redeem_exhausted_rewards.add(reward_id)
                    max_per_stream_setting = reward.get("maxPerStreamSetting") or {}
                    max_per_stream = max_per_stream_setting.get("maxPerStream")
                    redeemed_current_stream = reward.get("redemptionsRedeemedCurrentStream")
                    if max_per_stream is not None:
                        limit_details = f" ({redeemed_current_stream}/{max_per_stream}). "
                    else:
                        limit_details = ". "
                    logger.info(
                        f"Skip auto redeem for {streamer}: '{reward.get('title')}' reached max-per-stream"
                        f"{limit_details}Will retry next stream.",
                        extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                    )
                    pretty_skip_logged = True

            if (
                is_max_per_stream_reward
                and streamer.is_online
                and error_code in unavailable_codes
            ):
                max_unavailable_attempts += 1

            if is_max_per_stream_reward is False and reward_id is not None:
                cooldown_seconds = int(reward.get("cooldownSeconds") or 60)
                self.__log_auto_redeem_debug(
                    streamer,
                    reward,
                    f"set next non-max retry after failure to {cooldown_seconds}s",
                )
                next_due = time.time() + cooldown_seconds
                streamer.auto_redeem_non_max_next_attempts[reward_id] = next_due
                if min_non_max_next_due is None or next_due < min_non_max_next_due:
                    min_non_max_next_due = next_due

        should_stop_online_cycle = (
            streamer.is_online
            and has_non_max_targets is False
            and (
                max_eligible_targets == 0
                or (
                    max_attempted_targets > 0
                    and max_attempted_targets == max_unavailable_attempts
                )
            )
        )
        if should_stop_online_cycle:
            streamer.auto_redeem_next_check_at = 0
            logger.info(
                f"[auto-redeem] streamer={streamer.username} stop online cycle "
                f"attempted={attempted_targets} redeemed={redeemed_targets} "
                f"errors={sorted(error_codes_seen) if len(error_codes_seen) > 0 else []}"
            )
            if online_transition_mode and not pretty_skip_logged:
                logger.info(
                    f"[auto-redeem] {streamer.username} online trigger: no redeem "
                    f"(attempted={attempted_targets}, redeemed={redeemed_targets}, "
                    f"errors={sorted(error_codes_seen) if len(error_codes_seen) > 0 else []})",
                    extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                )
            return

        now = time.time()
        next_check_at = now + poll_interval
        if has_max_targets is False and min_non_max_next_due is not None:
            next_check_at = max(now + 0.5, min_non_max_next_due)
        streamer.auto_redeem_next_check_at = next_check_at
        logger.debug(
            f"[auto-redeem][debug] streamer={streamer.username} next_check_at={streamer.auto_redeem_next_check_at} "
            f"attempted={attempted_targets} redeemed={redeemed_targets} "
            f"min_non_max_next_due={min_non_max_next_due}"
        )

        if online_transition_mode:
            if redeemed_targets > 0:
                logger.info(
                    f"[auto-redeem] {streamer.username} online trigger: redeemed={redeemed_targets} "
                    f"(attempted={attempted_targets})",
                    extra={"emoji": ":ticket:", "event": Events.REWARD_REDEEMED},
                )
            elif attempted_targets > 0:
                if not pretty_skip_logged:
                    logger.info(
                        f"[auto-redeem] {streamer.username} online trigger: failed "
                        f"(attempted={attempted_targets}, errors={sorted(error_codes_seen)})",
                        extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                    )
            else:
                logger.info(
                    f"[auto-redeem] {streamer.username} online trigger: waiting "
                    f"(eligible={max_eligible_targets}, points={streamer.channel_points})",
                    extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                )

    def __handle_streamer_rewards(self, streamer, channel):
        settings = streamer.settings
        silent_fast_mode = streamer.username == "saintsakura"
        poll_interval = 3 if silent_fast_mode else 60
        redeem_titles = settings.auto_redeem_reward_titles
        if isinstance(redeem_titles, str):
            redeem_titles = [redeem_titles]

        if (
            settings.fetch_rewards is not True
            and len(settings.auto_redeem_reward_ids) == 0
            and len(redeem_titles) == 0
        ):
            return

        # Auto-redeem runs only while streamer is online.
        if streamer.is_online is not True:
            streamer.auto_redeem_next_check_at = 0
            return

        # Default to a periodic refresh for auto-redeem streamers.
        streamer.auto_redeem_next_check_at = time.time() + poll_interval

        cps = channel.get("communityPointsSettings", {})
        custom_rewards = cps.get("customRewards", []) if cps else []
        automatic_rewards = cps.get("automaticRewards", []) if cps else []

        if settings.fetch_rewards is True and not silent_fast_mode:
            logger.debug(
                f"Rewards for {streamer}: automatic={len(automatic_rewards)} custom={len(custom_rewards)}"
            )
            for reward in custom_rewards:
                logger.debug(
                    f"[CUSTOM] {reward.get('title')} | id={reward.get('id')} | cost={self.__reward_cost(reward)} | inStock={reward.get('isInStock')}"
                )

        targets = self.__resolve_auto_redeem_targets(settings, custom_rewards)

        if len(targets) == 0:
            if silent_fast_mode and streamer.is_online:
                streamer.auto_redeem_next_check_at = 0
            return

        seen = set()
        found_in_stock_target = False
        for reward in targets:
            reward_id = reward.get("id")
            if reward_id in seen:
                continue
            seen.add(reward_id)

            if (
                settings.auto_redeem_repeat is not True
                and reward_id in streamer.auto_redeemed_rewards
            ):
                continue

            if reward_id in streamer.auto_redeem_exhausted_rewards:
                continue

            if reward.get("isInStock") is not True:
                self.__log_auto_redeem_info(
                    streamer,
                    reward,
                    f"skip: reward not in stock cooldown_expires_at={reward.get('cooldownExpiresAt')}",
                )
                if self.__is_reward_exhausted_for_current_stream(reward):
                    if streamer.is_online is True:
                        streamer.auto_redeem_exhausted_rewards.add(reward_id)
                        if not silent_fast_mode:
                            logger.info(
                                f"Skip auto redeem for {streamer}: '{reward.get('title')}' reached max-per-stream "
                                f"({reward.get('redemptionsRedeemedCurrentStream')}/{(reward.get('maxPerStreamSetting') or {}).get('maxPerStream')}). "
                                "Will retry next stream.",
                                extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                            )
                    continue

                cooldown_ts = self.__parse_twitch_timestamp(reward.get("cooldownExpiresAt"))
                if cooldown_ts is not None:
                    # Re-check shortly after cooldown end.
                    self.__schedule_auto_redeem_check(streamer, cooldown_ts + 1)
                if not silent_fast_mode:
                    logger.info(
                        f"Skip auto redeem for {streamer}: '{reward.get('title')}' is out of stock "
                        f"(cooldownExpiresAt={reward.get('cooldownExpiresAt')}, "
                        f"next_check_at={datetime.fromtimestamp(streamer.auto_redeem_next_check_at, timezone.utc).isoformat() if streamer.auto_redeem_next_check_at else None})",
                        extra={"emoji": ":hourglass_flowing_sand:", "event": Events.REWARD_SKIPPED},
                    )
                continue

            found_in_stock_target = True
            self.__log_auto_redeem_info(streamer, reward, "reward is in stock and eligible for evaluation")
            if streamer.channel_points < int(self.__reward_cost(reward) or 0):
                self.__schedule_auto_redeem_check(
                    streamer, time.time() + poll_interval
                )
                if not silent_fast_mode:
                    logger.info(
                        f"Skip auto redeem for {streamer}: not enough points for '{reward.get('title')}'"
                    )
                continue

            self.__log_auto_redeem_info(streamer, reward, "attempt redeem")
            redeemed, _error_code = self.__redeem_custom_reward(
                streamer, reward, text_input=settings.auto_redeem_text
            )
            if redeemed is True:
                if settings.auto_redeem_repeat is not True:
                    streamer.auto_redeemed_rewards.add(reward_id)
                # Refresh soon to observe newly assigned cooldown and continue cycle.
                next_attempt_delay = 3 if silent_fast_mode else 20
                self.__schedule_auto_redeem_check(
                    streamer, time.time() + next_attempt_delay
                )

        if silent_fast_mode and streamer.is_online and not found_in_stock_target:
            streamer.auto_redeem_next_check_at = 0

    # Load the amount of current points for a channel, check if a bonus is available
    def load_channel_points_context(self, streamer, include_rewards=True):
        json_data = copy.deepcopy(GQLOperations.ChannelPointsContext)
        json_data["variables"] = {"channelLogin": streamer.username}

        response = self.post_gql_request(json_data)
        if response != {}:
            if response["data"]["community"] is None:
                raise StreamerDoesNotExistException
            channel = response["data"]["community"]["channel"]
            community_points = channel["self"]["communityPoints"]
            streamer.channel_points = community_points["balance"]
            streamer.activeMultipliers = community_points["activeMultipliers"]

            if streamer.settings.community_goals is True:
                streamer.community_goals = {
                    goal["id"]: CommunityGoal.from_gql(goal)
                    for goal in channel["communityPointsSettings"]["goals"]
                }

            if community_points["availableClaim"] is not None:
                self.claim_bonus(
                    streamer, community_points["availableClaim"]["id"])

            if streamer.settings.community_goals is True:
                self.contribute_to_community_goals(streamer)

            if streamer.settings.community_goals is True:
                self.contribute_to_community_goals(streamer)

            if include_rewards is True:
                self.__handle_streamer_rewards(streamer, channel)

    def make_predictions(self, event):
        decision = event.bet.calculate(event.streamer.channel_points)
        # selector_index = 0 if decision["choice"] == "A" else 1

        logger.info(
            f"Going to complete bet for {event}",
            extra={
                "emoji": ":four_leaf_clover:",
                "event": Events.BET_GENERAL,
            },
        )
        if event.status == "ACTIVE":
            skip, compared_value = event.bet.skip()
            if skip is True:
                logger.info(
                    f"Skip betting for the event {event}",
                    extra={
                        "emoji": ":pushpin:",
                        "event": Events.BET_FILTERS,
                    },
                )
                logger.info(
                    f"Skip settings {event.bet.settings.filter_condition}, current value is: {compared_value}",
                    extra={
                        "emoji": ":pushpin:",
                        "event": Events.BET_FILTERS,
                    },
                )
            else:
                if decision["amount"] >= 10:
                    logger.info(
                        # f"Place {_millify(decision['amount'])} channel points on: {event.bet.get_outcome(selector_index)}",
                        f"Place {_millify(decision['amount'])} channel points on: {event.bet.get_outcome(decision['choice'])}",
                        extra={
                            "emoji": ":four_leaf_clover:",
                            "event": Events.BET_GENERAL,
                        },
                    )

                    json_data = copy.deepcopy(GQLOperations.MakePrediction)
                    json_data["variables"] = {
                        "input": {
                            "eventID": event.event_id,
                            "outcomeID": decision["id"],
                            "points": decision["amount"],
                            "transactionID": token_hex(16),
                        }
                    }
                    response = self.post_gql_request(json_data)
                    if (
                        "data" in response
                        and "makePrediction" in response["data"]
                        and "error" in response["data"]["makePrediction"]
                        and response["data"]["makePrediction"]["error"] is not None
                    ):
                        error_code = response["data"]["makePrediction"]["error"]["code"]
                        logger.error(
                            f"Failed to place bet, error: {error_code}",
                            extra={
                                "emoji": ":four_leaf_clover:",
                                "event": Events.BET_FAILED,
                            },
                        )
                else:
                    logger.info(
                        f"Bet won't be placed as the amount {_millify(decision['amount'])} is less than the minimum required 10",
                        extra={
                            "emoji": ":four_leaf_clover:",
                            "event": Events.BET_GENERAL,
                        },
                    )
        else:
            logger.info(
                f"Oh no! The event is not active anymore! Current status: {event.status}",
                extra={
                    "emoji": ":disappointed_relieved:",
                    "event": Events.BET_FAILED,
                },
            )

    def claim_bonus(self, streamer, claim_id):
        if Settings.logger.less is False:
            logger.info(
                f"Claiming the bonus for {streamer}!",
                extra={"emoji": ":gift:", "event": Events.BONUS_CLAIM},
            )

        json_data = copy.deepcopy(GQLOperations.ClaimCommunityPoints)
        json_data["variables"] = {
            "input": {"channelID": streamer.channel_id, "claimID": claim_id}
        }
        self.post_gql_request(json_data)

    # === MOMENTS === #
    def claim_moment(self, streamer, moment_id):
        if Settings.logger.less is False:
            logger.info(
                f"Claiming the moment for {streamer}!",
                extra={"emoji": ":video_camera:",
                       "event": Events.MOMENT_CLAIM},
            )

        json_data = copy.deepcopy(GQLOperations.CommunityMomentCallout_Claim)
        json_data["variables"] = {"input": {"momentID": moment_id}}
        self.post_gql_request(json_data)

    # === CAMPAIGNS / DROPS / INVENTORY === #
    def __get_campaign_ids_from_streamer(self, streamer):
        json_data = copy.deepcopy(
            GQLOperations.DropsHighlightService_AvailableDrops)
        json_data["variables"] = {"channelID": streamer.channel_id}
        response = self.post_gql_request(json_data)
        try:
            return (
                []
                if response["data"]["channel"]["viewerDropCampaigns"] is None
                else [
                    item["id"]
                    for item in response["data"]["channel"]["viewerDropCampaigns"]
                ]
            )
        except (ValueError, KeyError):
            return []

    def __get_inventory(self):
        response = self.post_gql_request(GQLOperations.Inventory)
        try:
            return (
                response["data"]["currentUser"]["inventory"] if response != {} else {}
            )
        except (ValueError, KeyError, TypeError):
            return {}

    def __get_drops_dashboard(self, status=None):
        response = self.post_gql_request(GQLOperations.ViewerDropsDashboard)
        campaigns = (
            response.get("data", {})
            .get("currentUser", {})
            .get("dropCampaigns", [])
            or []
        )

        if status is not None:
            campaigns = (
                list(filter(lambda x: x["status"] == status.upper(), campaigns)) or []
            )

        return campaigns

    def __get_campaigns_details(self, campaigns):
        result = []
        chunks = create_chunks(campaigns, 20)
        for chunk in chunks:
            json_data = []
            for campaign in chunk:
                json_data.append(copy.deepcopy(
                    GQLOperations.DropCampaignDetails))
                json_data[-1]["variables"] = {
                    "dropID": campaign["id"],
                    "channelLogin": f"{self.twitch_login.get_user_id()}",
                }

            response = self.post_gql_request(json_data)
            if not isinstance(response, list):
                logger.debug("Unexpected campaigns response format, skipping chunk")
                continue
            for r in response:
                drop_campaign = (
                    r.get("data", {}).get("user", {}).get("dropCampaign", None)
                )
                if drop_campaign is not None:
                    result.append(drop_campaign)
        return result

    def __sync_campaigns(self, campaigns):
        # We need the inventory only for get the real updated value/progress
        # Get data from inventory and sync current status with streamers.campaigns
        inventory = self.__get_inventory()
        if inventory not in [None, {}] and inventory["dropCampaignsInProgress"] not in [
            None,
            {},
        ]:
            # Iterate all campaigns from dashboard (only active, with working drops)
            # In this array we have also the campaigns never started from us (not in nventory)
            for i in range(len(campaigns)):
                campaigns[i].clear_drops()  # Remove all the claimed drops
                # Iterate all campaigns currently in progress from out inventory
                for progress in inventory["dropCampaignsInProgress"]:
                    if progress["id"] == campaigns[i].id:
                        campaigns[i].in_inventory = True
                        campaigns[i].sync_drops(
                            progress["timeBasedDrops"], self.claim_drop
                        )
                        # Remove all the claimed drops
                        campaigns[i].clear_drops()
                        break
        return campaigns

    def claim_drop(self, drop):
        logger.info(
            f"Claim {drop}", extra={"emoji": ":package:", "event": Events.DROP_CLAIM}
        )

        json_data = copy.deepcopy(GQLOperations.DropsPage_ClaimDropRewards)
        json_data["variables"] = {
            "input": {"dropInstanceID": drop.drop_instance_id}}
        response = self.post_gql_request(json_data)
        try:
            # response["data"]["claimDropRewards"] can be null and respose["data"]["errors"] != []
            # or response["data"]["claimDropRewards"]["status"] === DROP_INSTANCE_ALREADY_CLAIMED
            if ("claimDropRewards" in response["data"]) and (
                response["data"]["claimDropRewards"] is None
            ):
                return False
            elif ("errors" in response["data"]) and (response["data"]["errors"] != []):
                return False
            elif ("claimDropRewards" in response["data"]) and (
                response["data"]["claimDropRewards"]["status"]
                in ["ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"]
            ):
                return True
            else:
                return False
        except (ValueError, KeyError):
            return False

    def claim_all_drops_from_inventory(self):
        inventory = self.__get_inventory()
        if inventory not in [None, {}]:
            if inventory["dropCampaignsInProgress"] not in [None, {}]:
                for campaign in inventory["dropCampaignsInProgress"]:
                    for drop_dict in campaign["timeBasedDrops"]:
                        drop = Drop(drop_dict)
                        drop.update(drop_dict["self"])
                        if drop.is_claimable is True:
                            drop.is_claimed = self.claim_drop(drop)
                            time.sleep(random.uniform(5, 10))

    def sync_campaigns(self, streamers, chunk_size=3):
        campaigns_update = 0
        campaigns = []
        while self.running:
            try:
                # Get update from dashboard each 60minutes
                if (
                    campaigns_update == 0
                    # or ((time.time() - campaigns_update) / 60) > 60
                    # TEMPORARY AUTO DROP CLAIMING FIX
                    # 30 minutes instead of 60 minutes
                    or ((time.time() - campaigns_update) / 30) > 30
                    #####################################
                ):
                    campaigns_update = time.time()

                    # TEMPORARY AUTO DROP CLAIMING FIX
                    self.claim_all_drops_from_inventory()
                    #####################################

                    # Get full details from current ACTIVE campaigns
                    # Use dashboard so we can explore new drops not currently active in our Inventory
                    campaigns_details = self.__get_campaigns_details(
                        self.__get_drops_dashboard(status="ACTIVE")
                    )
                    campaigns = []

                    # Going to clear array and structure. Remove all the timeBasedDrops expired or not started yet
                    for index in range(0, len(campaigns_details)):
                        if campaigns_details[index] is not None:
                            campaign = Campaign(campaigns_details[index])
                            if campaign.dt_match is True:
                                # Remove all the drops already claimed or with dt not matching
                                campaign.clear_drops()
                                if campaign.drops != []:
                                    campaigns.append(campaign)
                        else:
                            continue

                # Divide et impera :)
                campaigns = self.__sync_campaigns(campaigns)

                # Check if user It's currently streaming the same game present in campaigns_details
                for i in range(0, len(streamers)):
                    if streamers[i].drops_condition() is True:
                        # yes! The streamer[i] have the drops_tags enabled and we It's currently stream a game with campaign active!
                        # With 'campaigns_ids' we are also sure that this streamer have the campaign active.
                        # yes! The streamer[index] have the drops_tags enabled and we It's currently stream a game with campaign active!
                        streamers[i].stream.campaigns = list(
                            filter(
                                lambda x: x.drops != []
                                and x.game == streamers[i].stream.game
                                and x.id in streamers[i].stream.campaigns_ids,
                                campaigns,
                            )
                        )

            except (ValueError, KeyError, requests.exceptions.ConnectionError) as e:
                logger.error(f"Error while syncing inventory: {e}")
                campaigns = []
                self.__check_connection_handler(chunk_size)

            self.__chuncked_sleep(60, chunk_size=chunk_size)

    def contribute_to_community_goals(self, streamer):
        # Don't bother doing the request if no goal is currently started or in stock
        if any(
            goal.status == "STARTED" and goal.is_in_stock
            for goal in streamer.community_goals.values()
        ):
            json_data = copy.deepcopy(GQLOperations.UserPointsContribution)
            json_data["variables"] = {"channelLogin": streamer.username}
            response = self.post_gql_request(json_data)
            user_goal_contributions = response["data"]["user"]["channel"]["self"][
                "communityPoints"
            ]["goalContributions"]

            logger.debug(
                f"Found {len(user_goal_contributions)} community goals for the current stream"
            )

            for goal_contribution in user_goal_contributions:
                goal_id = goal_contribution["goal"]["id"]
                goal = streamer.community_goals[goal_id]
                if goal is None:
                    # TODO should this trigger a new load context request
                    logger.error(
                        f"Unable to find context data for community goal {goal_id}"
                    )
                else:
                    user_stream_contribution = goal_contribution[
                        "userPointsContributedThisStream"
                    ]
                    user_left_to_contribute = (
                        goal.per_stream_user_maximum_contribution
                        - user_stream_contribution
                    )
                    amount = min(
                        goal.amount_left(),
                        user_left_to_contribute,
                        streamer.channel_points,
                    )
                    if amount > 0:
                        self.contribute_to_community_goal(
                            streamer, goal_id, goal.title, amount
                        )
                    else:
                        logger.debug(
                            f"Not contributing to community goal {goal.title}, user channel points {streamer.channel_points}, user stream contribution {user_stream_contribution}, all users total contribution {goal.points_contributed}"
                        )

    def contribute_to_community_goal(self, streamer, goal_id, title, amount):
        json_data = copy.deepcopy(
            GQLOperations.ContributeCommunityPointsCommunityGoal)
        json_data["variables"] = {
            "input": {
                "amount": amount,
                "channelID": streamer.channel_id,
                "goalID": goal_id,
                "transactionID": token_hex(16),
            }
        }

        response = self.post_gql_request(json_data)

        error = response["data"]["contributeCommunityPointsCommunityGoal"]["error"]
        if error:
            logger.error(
                f"Unable to contribute channel points to community goal '{title}', reason '{error}'"
            )
        else:
            logger.info(
                f"Contributed {amount} channel points to community goal '{title}'"
            )
            streamer.channel_points -= amount
