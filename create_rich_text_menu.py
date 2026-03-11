# -*- coding: utf-8 -*-

import os
import sys
from typing import List

import dotenv
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    RichMenuRequest,
    RichMenuArea,
    RichMenuSize,
    RichMenuBounds,
    URIAction,
    RichMenuSwitchAction,
    CreateRichMenuAliasRequest, MessagingApiBlob, DatetimePickerAction
)
from linebot.v3.messaging.models.rich_menu_alias_response import RichMenuAliasResponse
from linebot.v3.messaging.models.rich_menu_response import RichMenuResponse
from pydantic import StrictStr

dotenv.load_dotenv()

channel_access_token = os.getenv('LINE_BOT_ACCESS_TOKEN', None)
if channel_access_token is None:
    print('Specify LINE_BOT_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

configuration = Configuration(
    access_token=channel_access_token
)


def rich_menu_object_a_json():
    return {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": "richmenu-a",
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 1250,
                    "height": 1686
                },
                "action": {
                    "type": "uri",
                    "uri": "https://developers.line.biz/"
                }
            },
            {
                "bounds": {
                    "x": 1251,
                    "y": 0,
                    "width": 1250,
                    "height": 1686
                },
                "action": {
                    "type": "datetimepicker",
                    "label": "Select date",
                    "data": "storeId=12345",
                    "mode": "datetime",
                    "initial": "2017-12-25t00:00",
                    "max": "2018-01-24t23:59",
                    "min": "2017-12-25t00:00"
                }
            }
        ]
    }


def create_action(action):
    if action['type'] == 'uri':
        return URIAction(type=action.get('type'),
                         uri=action.get('uri'),
                         altUri=action.get('altUri') or {},
                         label=action.get('label') or "label")
    elif action['type'] == 'datetimepicker':
        return DatetimePickerAction(type=action.get('type'),
                                    label=action.get('label'),
                                    data=action.get('data'),
                                    mode=action.get('mode'),
                                    initial=action.get('initial'),
                                    min=action.get('min'),
                                    max=action.get('max'))
    else:
        raise RuntimeError(f'Unknown action: {action.get("type")}')


def main():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        rich_menu_list: List[RichMenuResponse] = line_bot_api.get_rich_menu_list().richmenus
        print(type(rich_menu_list), rich_menu_list)
        for rich_menu in rich_menu_list:
            print(type(rich_menu), rich_menu)
            if rich_menu.name in ["richmenu-a", "richmenu-b",
                                  "richmenu-aa", "richmenu-bb",
                                  "richmenu-aaa", "richmenu-bbb"]:
                line_bot_api.delete_rich_menu(rich_menu.rich_menu_id)

        aliases: List[RichMenuAliasResponse] = line_bot_api.get_rich_menu_alias_list().aliases
        print(type(aliases), aliases)
        for alias in aliases:
            print(type(alias), aliases)
            if alias.rich_menu_alias_id in ["richmenu-alias-a", "richmenu-alias-b",
                                            "richmenu-alias-aa", "richmenu-alias-bb",
                                            "richmenu-alias-aaa", "richmenu-alias-bbb"]:
                line_bot_api.delete_rich_menu_alias(StrictStr(alias.rich_menu_alias_id))

            line_bot_blob_api = MessagingApiBlob(api_client)

            # 2. Create rich menu A (richmenu-a)
            rich_menu_object_a = rich_menu_object_a_json()
            areas = [
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=info['bounds']['x'],
                        y=info['bounds']['y'],
                        width=info['bounds']['width'],
                        height=info['bounds']['height']
                    ),
                    action=create_action(info['action'])
                ) for info in rich_menu_object_a['areas']
            ]

            rich_menu_to_a_create = RichMenuRequest(
                size=RichMenuSize(width=rich_menu_object_a['size']['width'],
                                  height=rich_menu_object_a['size']['height']),
                selected=rich_menu_object_a['selected'],
                name=rich_menu_object_a['name'],
                chat_bar_text=rich_menu_object_a['name'],
                areas=areas
            )

            rich_menu_a_id = line_bot_api.create_rich_menu(
                rich_menu_request=rich_menu_to_a_create
            ).rich_menu_id

            # 3. Upload image to rich menu A
            with open('./public/richmenu-a.png', 'rb') as image:
                line_bot_blob_api.set_rich_menu_image(
                    rich_menu_id=rich_menu_a_id,
                    body=bytearray(image.read()),
                    _headers={'Content-Type': 'image/png'}
                )

            # 6. Set rich menu A as the default rich menu
            line_bot_api.set_default_rich_menu(rich_menu_id=rich_menu_a_id)

            # 7. Create rich menu alias A
            alias_a = CreateRichMenuAliasRequest(
                rich_menu_alias_id='richmenu-alias-a',
                rich_menu_id=rich_menu_a_id
            )
            line_bot_api.create_rich_menu_alias(alias_a)

            print('success')


main()
