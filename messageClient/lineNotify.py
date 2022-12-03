import requests
import json
import math

url = 'https://notify-api.line.me/api/notify'
MAX_TEXT_LENGTH_PER_REQUEST = 1000 # 1000文字以上のメッセージは一度に送れないので分割して送る

# LineNotifyの送信に失敗
class LineNotifyError(Exception):
    pass

# LineNotifyでメッセージの送信をする
def send(token, text, file=None):
    headers = {'Authorization': 'Bearer '+token}

    for i, message in enumerate(separateText(text, MAX_TEXT_LENGTH_PER_REQUEST)):
        params = {'message': text}
        if i != 0 or file == None :
            r = requests.post(url, headers=headers, params=params)
        else:
            r = requests.post(url, headers=headers, params=params, files={'imageFile': file})
        if r.status_code != 200:
            err_message = json.loads(r.content)['message']
            raise LineNotifyError('Lineの送信に失敗({})'.format(err_message))

    return r

# 指定した最大文字数でテキストを分割する
def separateText(text, length):
    for i in range(math.ceil(len(text) / length)):
        yield text[i*length:(i + 1)*length]
