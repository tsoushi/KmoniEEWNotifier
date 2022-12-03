import requests
import json
import datetime
import time
import threading
import io
from geopy.distance import geodesic
from concurrent.futures import ThreadPoolExecutor

try:
    from PIL import Image
    NO_PIL = False
except ModuleNotFoundError:
    NO_PIL = True

import logging
BASE_LOGGER_NAME = 'KmoniEEWNotifier'
logger = logging.getLogger(BASE_LOGGER_NAME).getChild('Listener')

from send import send
from config import LOCATION_HOME

#fmt = '%a, %d %b %Y %H:%M:%S GMT'
class Listener:
    URL_KMONI = 'http://www.kmoni.bosai.go.jp'
    URL_EEW = 'http://www.kmoni.bosai.go.jp/webservice/hypo/eew/{}.json'
    #URL_EEW = 'http://localhost:3001/server/{}'
    URL_REALTIME = 'http://www.kmoni.bosai.go.jp/data/map_img/RealTimeImg/jma_s/{0}/{0}{1}.jma_s.gif'
    URL_WAVE = 'http://www.kmoni.bosai.go.jp/data/map_img/PSWaveImg/eew/{0}/{0}{1}.eew.gif'
    URL_SHINDO = 'http://www.kmoni.bosai.go.jp/data/map_img/EstShindoImg/eew/{0}/{0}{1}.eew.gif'
    URL_BASE_MAP = 'http://www.kmoni.bosai.go.jp/data/map_img/CommonImg/base_map_w.gif'
    URL_LATEST = 'http://www.kmoni.bosai.go.jp/webservice/server/pros/latest.json'



    def __init__(self):
        logger = logging.getLogger(__name__+'.'+'Listener')
        logger.debug('初期化開始')
        self.kill_flag = False
        self.update_detector_log = []

        logger.debug('ログファイルオープン')
        self.log_file = open('log.txt', mode='a', encoding='utf-8')
        if NO_PIL == False:
            logger.debug('リアルタイム震度画像のベース画像を読み込み')
            self.base_map_img = Image.open(io.BytesIO(self._get_request(self.URL_BASE_MAP).content)).convert('RGBA')
        logger.debug('初期化完了')

    def start(self):

        #初期化
        next_datetime = self.get_latest_datetime()
        next_time = time.time() #次の取得予定時刻
        while 1:
            self._wait_until(next_time) #次の取得予定時刻まで待つ
            if self.kill_flag:
                logger.info('サービスを終了します')
                return

            if time.time() - next_time >= 5: #遅延が5秒以上になったとき
                now_delay = time.time() - next_time
                logger.warning('{}秒の遅延が発生'.format(now_delay))
                #遅延している分をとばす
                next_time += int(now_delay)
                next_datetime += datetime.timedelta(seconds=int(now_delay))
                continue

            try:
                #eew取得、処理
                logger.debug('eew取得処理開始')

                eew = self._get_eew(next_datetime) #取得時刻からeew情報を取得。失敗時は例外発生。
                print('\r{}'.format(next_datetime.strftime('%H:%M:%S')), end='')
                #print('\n', eew.dict)

                if eew.alert_flag != None: #eewが発令中かどうか
                    #eew発令中
                    if self._update_detector(eew): #前に受け取ったものと異なるかどうか確かめる
                        #eew更新時の処理
                        logger.info('新しいeewの発報検知')
                        self._write_log(eew)
                        threading.Thread(target=self.eew_updated, args=(eew,)).start()

                else:
                    #eew発令終了時の初期化
                    self._clear_update_detector()

            except Exception as e:
                logger.error('例外発生のためeew取得処理を終了: '+type(e).__name__+' : '+str(e))

            finally:
                next_time += 1 #次の取得予定時刻を1秒後に設定
                next_datetime += datetime.timedelta(seconds=1) #次の取得時刻を一秒後に設定
                logger.debug('eew取得処理を正常に完了')

    def _update_detector(self, eew):
        eew_hash = (eew.report_num, eew.report_id, eew.is_cancel)
        if eew_hash in self.update_detector_log:
            ret = False
        else:
            ret = True
        self.update_detector_log.append(eew_hash)
        return ret

    def _clear_update_detector(self):
        self.update_detector_log = []

    def _write_log(self, eew):
        try:
            self.log_file.write('\n'+eew.report_time.strftime('%Y%m%d%H%M%S:')+str(eew.dict))
        except Exception as e:
            logger.warning('ログの書き込み中にエラー(処理続行):{}'.format(e))

    def _wait_until(self, tm):
        while 1:
            if time.time() >= tm:
                return
            time.sleep(0.1)

    def _get_eew(self, dttm):
        #例外: Exception
        #dttmで指定した時刻のeewの情報を取得
        logger.debug('eew取得')
        timestr = dttm.strftime('%Y%m%d%H%M%S')
        url = self.URL_EEW.format(timestr)

        res = self._get_request(url, timeout=5)

        res_dic = json.loads(res.content) #結果を辞書に変換
        return EEWParser(res_dic)

    #取得できる最新のeewの時刻を取得する
    def get_latest_datetime(self):
        logger.debug('時刻調整')
        res = self._get_request(self.URL_LATEST, timeout=2)
        if res.status_code != 200:
            logger.critical('時刻調整に失敗(status code: {}'.format(res.status_code))
            raise Exception('時刻調整に失敗(status code: {}'.format(res.status_code))
        latest_time_str = json.loads(res.content)['latest_time']
        latest_datetime = datetime.datetime.strptime(latest_time_str, '%Y/%m/%d %H:%M:%S')
        return latest_datetime

    def eew_updated(self, eew):
        #eew更新時の処理
        logger.debug('eew更新時の処理開始')
        final_text = '(最終報)' if eew.is_final else ''
        try:
            report_time = eew.report_time.strftime('%H時%M分%S秒')
        except Exception as e:
            report_time = '不明'
        try:
            origin_time = eew.origin_time.strftime('%H時%M分%S秒')
        except Exception as e:
            origin_time = '不明'
        try:
            arrival_time = eew.arrival_time.strftime('%H時%M分%S秒')
        except Exception as e:
            arrival_time = '不明'
        if eew.distance:
            distance = int(eew.distance)
        else:
            distance = '不明'

        #Line送信
        #===危険度の判定===
        logger.debug('危険度判定')
        emergency_flag = False
        #if eew.alert_flag in ['警報']:
        #	emergency_flag = True
        if eew.distance <= 100:
            emergency_flag = True
        mag_dist_func = lambda i: (float(i)/4.7)**4*100 if i!=None else 300 #マグニチュードから震度1以上揺れる範囲を推測する
        if eew.distance <= mag_dist_func(eew.magnitude):
            emergency_flag = True 
        #============================
        if emergency_flag == True:
            logger.debug('揺れる可能性ありと判定')
            pre_alert_message = '>>>揺れる可能性あり<<<\n'
        else:
            pre_alert_message = ''
        logger.debug('文字列生成')
        text = f"""\
{pre_alert_message}概要:M-{eew.magnitude} Max-{eew.shindo_max} time-{eew.arrival_span} dis-{distance}
緊急地震速報({eew.alert_flag}) 第{eew.report_num}報 {final_text}
更新時刻: {report_time}

発生時刻: {origin_time}
震源: {eew.center_name}
最大震度: {eew.shindo_max}
マグニチュード: {eew.magnitude}
深さ: {eew.depth}

震源からの距離: {distance} km
>>>到達まで: {eew.arrival_span} 秒後<<<

震源座標: {eew.center[0]}, {eew.center[1]}
到達予想時刻: {arrival_time}"""
        print('\n')
        print(text)
        print('\n')
        text += '\nURL: {}'.format(self.URL_KMONI)
        logger.debug(text)

        try:
            if NO_PIL == False:
                #画像生成
                img = self._gen_eew_image(eew.request_time)
                img_io = io.BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)
            #送信
            logger.error('メッセージ送信')
            send(text=text, image=img_io, emergency=emergency_flag)

        except Exception as e:
            logger.error('画像生成中にエラー: {}'.format(e))
            logger.error('メッセージ送信')
            send(text=text, image=None, emergency=emergency_flag)

    #強震モニタ画像を生成する
    def _gen_eew_image(self, dttm, get_eew=True):
        logger.debug('リアルタイム震度画像の取得、生成処理')
        fmt_args = (dttm.strftime('%Y%m%d'), dttm.strftime('%H%M%S'))
        with ThreadPoolExecutor(max_workers=3) as executor:
            logger.debug('リアルタイム震度画像の取得')
            res_realtime = executor.submit(self._get_request, self.URL_REALTIME.format(*fmt_args))
            if get_eew:
                res_wave = executor.submit(self._get_request, self.URL_WAVE.format(*fmt_args))
                res_shindo = executor.submit(self._get_request, self.URL_SHINDO.format(*fmt_args))
        img = self.base_map_img
        if get_eew:
            #予測震度画像を合成
            logger.debug('予測震度画像の合成')
            shindo_img = Image.open(io.BytesIO(res_shindo.result().content)).convert('RGBA')
            if shindo_img.size == img.size:
                img = Image.alpha_composite(img, shindo_img)
        #リアルタイム震度画像を合成
        logger.debug('リアルタイム震度画像の合成')
        realtime_img = Image.open(io.BytesIO(res_realtime.result().content)).convert('RGBA')
        img = Image.alpha_composite(img, realtime_img)

        if get_eew:
            #予測到達円画像を合成
            logger.debug('予測到達円画像を合成')
            wave_img = Image.open(io.BytesIO(res_wave.result().content)).convert('RGBA')
            if wave_img.size == img.size:
                img = Image.alpha_composite(img, wave_img)
        return img



    def _gen_realtime_url(self, dttm):
        return self.URL_REALTIME.format(dttm.strftime('%Y%m%d'), dttm.strftime('%H%M%S'))

    def _get_request(self, url, timeout=2):
        #例外: Exception
        logger.debug('request {} timeout={}'.format(url, timeout))
        err_count = 0
        while 1:
            res = requests.get(url, timeout=timeout)
            if res.status_code == 200:
                return res
            else:
                logger.info('requestで失敗')
                err_count += 1
                if err_count >= 3:
                    logger.warning('requestに一定回数以上失敗({}回)'.format(err_count))
                    raise Exception('requests.getで失敗')

class EEWParser:
    def __init__(self, eew_dict):
        self.dict = eew_dict
        #self.dict = {'result': {'status': 'success', 'message': '', 'is_auth': True}, 'report_time': '2021/06/15 15:19:07', 'region_code': '', 'request_time': '20210615151907', 'region_name': '東海道南方沖', 'longitude': '138.5', 'is_cancel': False, 'depth': '10km', 'calcintensity': '1', 'is_final': False, 'is_training': False, 'latitude': '33.6', 'origin_time': '20210615151833', 'security': {'realm': '/kyoshin_monitor/static/jsondata/eew_est/', 'hash': 'b61e4d95a8c42e004665825c098a6de4'}, 'magunitude': '3.7', 'report_num': '1', 'request_hypo_type': 'eew', 'report_id': '20210615151852', 'alertflg': '予報'}

        self.alert_flag = self.dict.get('alertflg')
        #self.alert_flag = '予報'
        self.report_id = self.dict.get('report_id') #ID
        self.report_time = self._strptime(self.dict.get('report_time'), '%Y/%m/%d %H:%M:%S') #情報更新時刻
        self.report_num = self.dict.get('report_num') #第n報
        self.origin_time = self._strptime(self.dict.get('origin_time'), '%Y%m%d%H%M%S') #地震発生時刻
        self.center_name = self.dict.get('region_name') #震源地

        self.depth = self.dict.get('depth') #震源の深さ
        if self.depth:
            temp = self.depth.replace('km', '')
            #深さをint型に変換
            if temp.isdigit():
                self.depth_km = int(temp)
            else:
                self.depth_km = None
        else:
            self.depth_km = None

        try:
            self.center = (float(self.dict.get('latitude')), float(self.dict.get('longitude'))) #震源の座標(北緯, 東経)
            self.distance = geodesic(LOCATION_HOME, self.center).km #震源からの距離を求める
        except (TypeError, ValueError):
            self.center = (None, None)
            self.distance = None

        if None not in (self.origin_time, self.distance):
            delta = int(self.distance/4)
            self.arrival_time = self.origin_time + datetime.timedelta(seconds=delta)
        else:
            self.arrival_time = None

        if None not in (self.report_time, self.arrival_time):
            temp = (self.arrival_time - self.report_time).total_seconds()
            if temp < 0:
                temp = 0
            self.arrival_span = temp
        else:
            self.arrival_span = None

        self.shindo_max = self.dict.get('calcintensity') #最大震度
        self.shindo_max_int = self._convert_shindo_int(self.shindo_max)
        self.magnitude = self.dict.get('magunitude') #マグニチュード
        self.is_final = self.dict.get('is_final') #最終報か
        self.is_cancel = self.dict.get('is_cancel') #キャンセル報か
        self.is_training = self.dict.get('is_training') #訓練報か
        self.request_time = self._strptime(self.dict.get('request_time'), '%Y%m%d%H%M%S') #リクエストした時刻

    def _strptime(self, string, fmt):
        #可能な場合のみ、文字列からdatetimeオブジェクトを生成
        try:
            return datetime.datetime.strptime(string, fmt)
        except Exception:
            return None

    def _convert_shindo_int(self, shindo):
        #震度文字列を１０段階の数値に変換(不明の場合-1)
        if shindo.isdigit():
            shindo_int = int(shindo)
            if 0 <= shindo_int <= 4:
                return shindo_int
            elif shindo_int == 7:
                return 9
        else:
            if shindo == '5弱':
                return 5
            elif shindo == '5強':
                return 6
            elif shindo == '6弱':
                return 7
            elif shindo == '6強':
                return 8

        return -1

if __name__ == '__main__':
    import sys
    #loggerの設定
    logger = logging.getLogger(BASE_LOGGER_NAME)
    logger.setLevel(logging.WARNING)
    streamHandler = logging.StreamHandler()
    streamHandler.setLevel(logging.WARNING)
    streamHandler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(streamHandler)
    if len(sys.argv) >= 2:
        if sys.argv[1] == 'info':
            logger.setLevel(logging.INFO)
            streamHandler.setLevel(logging.INFO)
        elif sys.argv[1] == 'debug':
            logger.setLevel(logging.DEBUG)
            streamHandler.setLevel(logging.DEBUG)

    #起動
    app = Listener()
    thread = threading.Thread(target=app.start)
    thread.start()
    try:
        while 1:
            time.sleep(100)
    except:
        print('終了します')
        app.kill_flag = True
