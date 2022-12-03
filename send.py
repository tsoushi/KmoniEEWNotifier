from messageClient import lineNotify
from messageClient import discordWebhook
import config

import logging
logger = logging.getLogger('KmoniEEWNotifier').getChild('MessageSender')

def send(text, image=None, emergency=False):
    # LineNotifyで送信
    try:
        if config.lineTokens['general']:
            logger.debug('send to LineNotify(general)')
            lineNotify.send(config.lineTokens['general'], text, image)
        if emergency:
            if config.lineTokens['emergency']:
                logger.debug('send to LineNotify(emergency)')
                lineNotify.send(config.lineTokens['emergency'], text, image)
    except lineNotify.LineNotifyError as e:
        logger.warn(e)
    
    if image:
        image.seek(0)
    # Discordで送信
    try:
        if config.discordWebhookUrls['general']:
            logger.debug('send to discord(general)')
            discordWebhook.send(config.discordWebhookUrls['general'], text, image, imageExt='png')
        if emergency:
            if config.discordWebhookUrls['emergency']:
                logger.debug('send to discord(emergency)')
                discordWebhook.send(config.discordWebhookUrls['emergency'], text, image, imageExt='png')
    except discordWebhook.DiscordWebhookError as e:
        logger.warn(e)