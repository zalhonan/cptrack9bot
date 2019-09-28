#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import json
import time
from os.path import dirname, realpath
from base64 import b64encode
from sys import argv, exit
import requests
from utils import validate

# Пути к полноразмерному изображению и миниатюре. Разрешение миниатюры должно быть 512 х 512
PIC_PATH = dirname(realpath(__file__)) + "/qr.jpg"
PIC_THUMB_PATH = dirname(realpath(__file__)) + "/qr.jpg"

# Взаимодействие с сервисом работы с сообщениями осуществляется по протоколу TCP
# Запросы, ответы и оповещения о новых сообщениях передаются в виде json, например

# Изображения передаются в кодировке base64

# В данный момент реализованы следующие функции:
# 1. Отправка текстовых сообщений
# 2. Отправка изображений
# 3. Получение текстовых сообщений

# Каждый запрос к сервису содержит поле OpaqueData, которое является идентификатором 
# и добавляется сервисом в ответ
# Для получения сообщений от пользователя необходимо подписаться, отправив команду вида:
# {"subscribe": true, "auth": "1b190253fc80765a897f0d39b13d1774dd34ee77de2116e62bc7121ab6fb625b", "opaque": 0}
# При получении нового сообщения от пользователя сервис отправляет нотификацию вида:
# {"mimetype":"com.seraphim.textmessage","sender":"8bbaa91a3a8cbc6da326ff81b68acf3826ddbfd52839e7435f4b83d67d951653","text":"\xd0\x93"}\n
# Для отправки текстового сообщения необходимо отправить команду вида:
# {"text":"Привет","mimetype":"com.seraphim.textmessage","receiver":"8bbaa91a3a8cbc6da326ff81b68acf3826ddbfd52839e7435f4b83d67d951653","opaque":1,"receiverencoding":"hash","auth":"1b190253fc80765a897f0d39b13d1774dd34ee77de2116e62bc7121ab6fb625b"}
# Отправка изображения аналогична отправке текста, только вместо ключа "text" команда должна содержать 
# ключи "image", "imagethumbnail" (изображения в кодировке base64) и "imageformat" (формат "jpg" или "png").
# {"mimetype":"com.seraphim.imagemessage","receiver":"c13c4f998a3495acc795ea7fc59ab54065c0a29ed6ecb203e8b1c509ba9dfc72","opaque":2,"receiverencoding":"hash","image":"IMAGE_DATA","imagethumbnail":"IMAGE_THUMBNAIL_DATA","imageformat":"jpg","auth":"1b190253fc80765a897f0d39b13d1774dd34ee77de2116e62bc7121ab6fb625b"}

# Ключи к запросам и ответам сервиса работы с сообщениями
class ApiKeys:
    MimeType = "mimetype"  # тип сообщения
    Receiver = "receiver"  # получатель
    Text = "text"  # текст
    OpaqueData = "opaque"  # идентификатор запроса
    ReceiverEncoding = "receiverencoding"  # кодирование получателя сообщения
    Image = "image"  # изображение
    ImageThumbnail = "imagethumbnail"  # миниатюра  изображения
    ImageFormat = "imageformat"  # формат изображения
    Sender = "sender"  # отправитель
    Result = "result"  # результат выполнения
    Auth = "auth"  # аутентификация
    Subscribe = "subscribe"  # подписка на информацию


# Результаты выполнения запроса к сервису работы с сообщениями
class ApiResult:
    Ok = 0  # Запрос выполнен успешно
    JsonFieldMissing = 100  # Не переданы все обязательные поля
    ParsePacketError = 101  # Некорректный пакет
    JsonSyntaxError = 102  # Ошибка парсинга. Не хватает закрывающей скобки или запятой
    SenderNotReady = 103  # Сервис отправки сообщений не может обработать сообщение в данный момент
    FileNotExist = 104  # Файл с контентом не существует. Возможно не было передано изображение
    BadReceiver = 105  # Некорректный получатель сообщения
    Timeout = 106  # Сервер не дождался всех фрагментов команды
    Unauthorized = 107  # Не совпал token аутентификации


# Форматы изображений
class ImageFormat:
    Jpg = "jpg"
    Png = "png"


# Типы сообщений
class MimeTypes:
    Text = "com.seraphim.textmessage"  # Текстовое
    Image = "com.seraphim.imagemessage"  # Изображение


# Варианты кодирования получателя сообщения
class ReceiverEncodings:
    Hash = "hash"  # В виде sha-256 хэш-суммы


def create_text_message(auth_token, text, receiver, opaque):
    ''' Создание текстового сообщения
    :param auth_token: токен аутентификации бота
    :param text: Текст сообщения
    :param receiver: sha-256 хэш-сумма логина получателя
    :param opaque: идентификатор запроса к API. Число
    :return: json команды
    '''

    return json.dumps(
        {ApiKeys.Text: text,
         ApiKeys.MimeType: MimeTypes.Text,
         ApiKeys.Receiver: receiver,
         ApiKeys.OpaqueData: opaque,
         ApiKeys.ReceiverEncoding: ReceiverEncodings.Hash,
         ApiKeys.Auth: auth_token}, separators=(',', ':'))


def create_image_message(auth_token, receiver, opaque, image, image_thumbnail, image_format):
    ''' Создание сообщения с изображением
    :param auth_token: токен аутентификации бота
    :param receiver: sha-256 хэш-сумма логина получателя
    :param opaque: идентификатор запроса к API. Число
    :param image: изображение, закодированное в base64
    :param image_thumbnail: миниатюра изображения, закодированная в base64
    :param image_format: формат изображения
    :return: json команды
    '''

    return json.dumps(
        {ApiKeys.MimeType: MimeTypes.Image,
         ApiKeys.Receiver: receiver,
         ApiKeys.OpaqueData: opaque,
         ApiKeys.ReceiverEncoding: ReceiverEncodings.Hash,
         ApiKeys.Image: b64encode(image).decode(),
         ApiKeys.ImageThumbnail: b64encode(image_thumbnail).decode(),
         ApiKeys.ImageFormat: image_format,
         ApiKeys.Auth: auth_token}, separators=(',', ':'))


def subscribe_to_messages(auth_token, opaque):
    ''' Подписка на сообщение от пользователя
    :param auth_token: токен аутентификации бота
    :param opaque:
    :return: json команды
    '''
    return json.dumps(
        {
            ApiKeys.Subscribe: True,
            ApiKeys.Auth: auth_token,
            ApiKeys.OpaqueData: opaque
        }
    )

OPAQUE = 0

if __name__ == '__main__':
    # if (len(argv) < 4):
    #     print ("Нужно передать параметры: IP адрес, порт, токен")
    #     exit(0)
    ip_addr = "api.seraphim.online"  # IP адрес, например 127.0.0.1
    port = 20007  # порт, например 20000
    auth_token = "c6fbcf9dbf24a284d42fcc0b85fb5d9ef9a19a504b169806aa3c9aef39248d2c"  # токен аутентификации бота
    print (auth_token)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((ip_addr, port))
    msg = subscribe_to_messages(auth_token, OPAQUE)
    print (msg)
    sock.sendall(bytes(msg, 'utf-8'))
    OPAQUE += 1
    # pic = None
    # pic_thumb = None
    # with open(PIC_PATH, "rb") as f_pic:
    #     pic = f_pic.read()
    #     with open(PIC_THUMB_PATH, "rb") as f_pic_thumb:
    #         pic_thumb = f_pic_thumb.read()

    #словарь сессий
    sessions = {}

    #параметры, что нужно узнать
    parameters = ["name", "surname", "passport", "issueDate", "dueDate", "areas"]
    queries = [
        "введите Ваше имя",
        "введите Вашу фамилию",
        "введите номер и серию паспорта без пробелов",
        "введите дату выхода на маршрут в формате гггг-мм-дд, например 2019-09-30",
        "введите дату возврата в формате гггг-мм-дд, например 2019-10-30",
        "введите желаемую зону для посещения: \n 1 - Сочинский национальный парк \n 2 - Государственный Кавказский Биосферный заповедник \n 1,2 - Обе зоны"
    ]

    while True:
        data = sock.recv(1024)

        if data:
            # Так как мы вычитываем раз в секунду, у нас может накопиться несколько сообщений от сервера:
            # {"opaque": 2,  "result": 0}\n{"opaque": 3,  "result": 0}\n
            # необходимо их разделить перед передачей в парсер
            messages = data.split(b"\n")
            for encoded_msg in messages:
                if encoded_msg:
                    msg = json.loads(encoded_msg)
                    if msg.__contains__(ApiKeys.Sender):  # входящее сообщение от пользователя

                        #проверить, есть ли юзер в ключах массива sessions
                        #если нет - создать
                        #если есть: проходить по массиву параметров. Если какого-то параметра нет - запросить
                        #если все параметры есть - послать запрос на АПИ и вернуть картинку

                        sender = msg[ApiKeys.Sender]
                        message = msg[ApiKeys.Text]

                        if message.lower() == 'новый':
                            del(sessions[sender])
                            print("sender deleted", sender)

                        print(sender, message, OPAQUE)

                        try:
                            if sessions[sender]["purchase"] == 1:
                                m = "Спасибо за покупку. Данный QR-код является Вашим билетом по оплаченному маршруту.\
                                    На маршруте пожалуйста предъявите его леснику (егерю) вместе с паспортом. Если\
                                        с получением кода возникли сложности, пожалуйста введите 'получить'\
                                            для новой покупки введите 'новый'"
                                echo_msg = create_text_message(auth_token, m, msg[ApiKeys.Sender], OPAQUE)
                                sock.sendall(bytes(echo_msg, 'utf-8'))  
                                OPAQUE += 1

                                echo_image = create_image_message(auth_token, msg[ApiKeys.Sender], OPAQUE, pic,
                                pic, ImageFormat.Png)
                                OPAQUE += 1
                                sock.sendall(bytes(echo_image, 'utf-8'))
                        except:
                            pass

                        if sender not in list(sessions.keys()):
                            print("-----------new user created", sender)
                            sessions[sender] = {}
                            m = "Здесь Вы можете купить билеты в Сочинский национальный парк\
                                и в Государственный Кавказский Биосферный заповедник.\
                                    обратите внимание, что Ваши имя, фамилия и номер паспорта\
                                         должны соответствовать указанным в паспорте. \nПожалуйста введите ваше имя"
                            echo_msg = create_text_message(auth_token, m, msg[ApiKeys.Sender], OPAQUE)
                            sock.sendall(bytes(echo_msg, 'utf-8'))  
                            OPAQUE += 1

                            sessions[sender]["name"] = 'empty' 
                            print("начало работы", sessions)

                        else:
                            print ("я тут")
                            for parameter in parameters:
                                if parameter not in list(sessions[sender].keys()):
                                    #создать ключ параметр, запросить параметр, брейкнуться
                                    sessions[sender][parameter] = 'empty'

                                    index = parameters.index(parameter)
                                    current_query = queries[index]

                                    echo_msg = create_text_message(auth_token, current_query, msg[ApiKeys.Sender], OPAQUE)
                                    sock.sendall(bytes(echo_msg, 'utf-8'))  
                                    OPAQUE += 1

                                    print("key created", sessions)
                                                                     
                                    break
                                else:
                                    #если параметр уже в листе
                                    #проверить, есть ли у параметра значение. 
                                    #если значения нет - записать туда ответ юзера, брейкнуться
                                    #если значение есть и это areas - созать QR
                                    #если значение есть и это что-то другое - пасс
                                    if sessions[sender][parameter] == 'empty':
                                        
                                        #сюда вставить проверку дат

                                        # if parameter in ["issueDate", "dueDate"] and not validate(parameter):
                                        #     print("все говно давай по новой")
                                        #     del sessions[sender][parameter]
                                        # else:
                                        sessions[sender][parameter] = message
                                        print("value created", sessions)

                                        # break
                                    if parameter == 'areas':

                                        url = "https://cptrack9.herokuapp.com/qr"
                                        params = sessions[sender]
                                        Picture_request = requests.get(url = url, params = params)

                                        if Picture_request.status_code == 200:
                                            with open("qr.png", 'wb') as f:
                                                f.write(Picture_request.content)

                                            pic = None
                                            pic_thumb = None
                                            with open("qr.png", "rb") as f_pic:
                                                pic = f_pic.read()

                                        # m = "Сейчас вы будете отправлены на страницу покупки"
                                        # echo_msg = create_text_message(auth_token, m, msg[ApiKeys.Sender], OPAQUE)
                                        # sock.sendall(bytes(echo_msg, 'utf-8'))  
                                        # OPAQUE += 1

                                        #пометим, что билет куплен
                                        # sessions[sender]["purchase"] = 1
                                        # print("-----purchase-----", sessions)

                                        echo_image = create_image_message(auth_token, msg[ApiKeys.Sender], OPAQUE, pic,
                                        pic, ImageFormat.Png)
                                        OPAQUE += 1
                                        sock.sendall(bytes(echo_image, 'utf-8'))

                                        m = "Спасибо за покупку. Данный QR-код является Вашим билетом по оплаченному маршруту.\
                                            На маршруте пожалуйста предъявите его леснику (егерю) вместе с паспортом. Если\
                                                с получением кода возникли сложности, пожалуйста введите 'получить'\
                                                    для новой покупки введите 'новый'"
                                        echo_msg = create_text_message(auth_token, m, msg[ApiKeys.Sender], OPAQUE)
                                        sock.sendall(bytes(echo_msg, 'utf-8'))  
                                        OPAQUE += 1
    

                    elif msg.__contains__(ApiKeys.OpaqueData):  # результат выполнения запроса
                        if int(msg[ApiKeys.Result]) != ApiResult.Ok:  # здесь можно обработать ошибки
                            print("error :", msg[ApiKeys.Result])

        time.sleep(1)
