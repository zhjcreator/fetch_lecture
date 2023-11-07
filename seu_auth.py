"""使用requests模拟登录新版东南大学统一身份认证平台（https://auth.seu.edu.cn/dist/#/dist/main/login）

函数说明：
get_pub_key()函数用于获取RSA公钥；
rsa_encrypt()函数用于使用RSA公钥加密用户密码；
seu_login()函数用于发起登录请求，返回成功登录的session和包含了ticket的重定向url。包括了对前两个函数的调用，一般只需要导入seu_login()函数即可。

使用方法：
1. 导入seu_login()函数；
2. 调用seu_login()函数，传入一卡通号、密码以及后续所要访问的服务url（可选），获取session和重定向url；
3. 使用session访问重定向url，执行后续操作。

Author: Golevka2001 (https://github.com/Golevka2001)
Email: gol3vka@163.com
Date: 2023/08/20
License: GPL-3.0 License
"""

import base64
import json
from urllib.parse import unquote

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


def get_pub_key():
    """从服务器请求RSA公钥并保存cookie（使用session就不需要另外保存cookie）。
    RSA公钥是变化的，并且应该和cookie有关联，每次登录前需要重新获取。

    Returns:
        session: 包含了和公钥配对的cookie的session，用于后续发起登录请求
        pub_key: RSA公钥
    """
    try:
        session = requests.Session()
        # Headers中的Content-Type、UA必填；
        # Host、Origin、Referer在后续访问其他服务时大多需要填，内容自己去抓包看；
        # 经测试，以下Headers中注释掉的字段均不影响身份认证的登录过程，但访问其他服务时需要自行抓包填写。
        headers = {
            # 'Accept': 'application/json',
            # 'Accept-Encoding': 'gzip, deflate, br',
            # 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            # 'Connection': 'keep-alive',
            'Content-Type':
            'application/json',
            # 'Host': 'auth.seu.edu.cn',
            # 'Origin': 'https://auth.seu.edu.cn',
            # 'Referer': 'https://auth.seu.edu.cn/dist/',
            # 'Sec-Fetch-Dest': 'empty',
            # 'Sec-Fetch-Mode': 'cors',
            # 'Sec-Fetch-Site': 'same-origin',
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/115.0.0.0 Safari/537.36'
        }
        session.headers = headers
        url = 'https://auth.seu.edu.cn/auth/casback/getChiperKey'
        res = session.post(url=url, data=json.dumps({}))

        if res.status_code != 200:
            raise Exception(f'[{res.status_code} {res.reason}]')

        pub_key = res.json()['publicKey']
        print('Successfully get public key')
        return session, pub_key
    except Exception as e:
        print('Failed to get public key, info:', e)
        return None, None


def rsa_encrypt(message, pub_key):
    """使用服务器返回的公钥对用户密码进行RSA加密。

    Args:
        message: 用户密码（明文）
        pub_key: 服务器提供的公钥

    Returns:
        cipher_text: 加密后的用户密码（base64）
    """
    try:
        pub_key = pub_key.replace('-', '+').replace('_',
                                                    '/')  # base64url -> base64
        pub_key = '-----BEGIN PUBLIC KEY-----\n' + pub_key + '\n-----END PUBLIC KEY-----'
        rsa_key = RSA.importKey(pub_key)
        cipher = PKCS1_v1_5.new(rsa_key)
        cipher_text = base64.b64encode(cipher.encrypt(
            message.encode()))  # base64

        print('Successfully encrypt password')
        return cipher_text.decode()
    except Exception as e:
        print('Failed to encrypt password, info:', e)
        return None


def seu_login(username, password, service_url=''):
    """向统一身份认证平台发起登录请求。

    Args:
        username: 一卡通号
        password: 用户密码（明文）
        service_url: 所要访问服务的url，如`http://ehall.seu.edu.cn`

    Returns:
        session: 成功通过身份认证的session，用于后续访问其他服务
        redirect_url: 登录后重定向到所要访问的服务的url
    """
    # 获取RSA公钥
    session, pub_key = get_pub_key()
    if not session:
        return None, None

    # 使用服务器返回的RSA公钥加密用户密码
    encrypted_password = rsa_encrypt(password, pub_key)
    if not encrypted_password:
        return None, None

    # 发起登录请求
    try:
        url = 'https://auth.seu.edu.cn/auth/casback/casLogin'
        data = {
            'captcha': '',
            'loginType': 'account',
            'mobilePhoneNum': '',
            'mobileVerifyCode': '',
            'password': encrypted_password,
            'rememberMe': False,
            'service': service_url,
            'username': username,
            'wxBinded': False,
        }
        res = session.post(url=url, data=json.dumps(data))

        if res.status_code != 200:
            raise Exception(f'[{res.status_code} {res.reason}]')
        if not res.json()['success']:
            raise Exception(res.json()['info'])

        print('Successfully authenticated')

        # 未指定服务，无需重定向，直接返回session
        if res.json()['redirectUrl'] is None:
            return session, None

        # 指定服务，返回重定向url（含ticket）
        redirect_url = unquote(res.json()['redirectUrl'])

        return session, redirect_url
    except Exception as e:
        print('Failed to authenticate, info:', e)
        return None, None
