# -*- coding: utf-8 -*-
import os

import dotenv
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi
)

from manager.database_manager import SingleConnection

if __name__ == "__main__":
    dotenv.load_dotenv()

    configuration = Configuration(access_token=os.getenv("LINE_BOT_ACCESS_TOKEN"))
    # handler = WebhookHandler(os.getenv("LINE_BOT_CHANNEL_SECRET"))

    with SingleConnection() as con:
        user_ids = con.execute("SELECT distinct user_id FROM chat_logs").fetchall()
        for user_id in user_ids:
            user_id = user_id[0]
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                profile = line_bot_api.get_profile(user_id)

                print(f"User ({profile.user_id}): {profile.display_name}. Picture URL: {profile.picture_url}")
                print(f"Status message: {profile.status_message}")
