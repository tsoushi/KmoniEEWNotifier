import json
import math

import requests

MAX_TEXT_LENGTH_PER_REQUEST = 2000 # 2000文字以上のメッセージは一度に送れないので分割して送る

class DiscordWebhookError(Exception):
    pass

# Discordに送信する
# 引数
#   image: ファイルオブジェクト
#   imageExt: ファイルの拡張子(imageを指定した時のみ)
def send(url, text, image=None, imageExt=None):

    for i, textBlock in enumerate(separateText(text, MAX_TEXT_LENGTH_PER_REQUEST)):
        if i == 0 and image and imageExt:
            # 画像付きメッセージの送信
            payload = {
                'content': textBlock,
                'embeds': [
                    {
                        'image': {
                            'url': 'attachment://image.' + imageExt
                        }
                    }
                ]
            }

            files = {
                'payload_json': (None, json.dumps(payload), 'application/json'),
                'image': ('image.' + imageExt, image)
            }
            try:
                res = requests.post(url, files=files)
            except Exception as e:
                raise DiscordWebhookError(e)
        else:
            # テキストのみのメッセージの送信
            payload = {
                'content': textBlock
            }
            try:
                res = requests.post(url, json=payload)
            except Exception as e:
                raise DiscordWebhookError(e)


# 指定した最大文字数でテキストを分割する
def separateText(text, length):
    for i in range(math.ceil(len(text) / length)):
        yield text[i*length:(i + 1)*length]