# -*- encoding: utf-8 -*-
"""
@File    : api.py
@Time    : 2024/8/15 下午8:04
@Author  : zhj
@Email   : 864302579@qq.com
@Software: PyCharm
"""
import json
import os
import base64
import yaml
from urllib.parse import unquote

from seu_auth import get_pub_key, rsa_encrypt


# 加密存储yaml，假装安全
def encrypt_yaml(yaml_data):
    for account in yaml_data:
        account['password'] = base64.b64encode(account['password'].encode()).decode()

    with open('accounts.yml', 'w') as f:
        yaml.dump(yaml_data, f)


# 读取yaml
def decrypt_yaml():
    with open('accounts.yml', 'r') as f:
        yaml_data = yaml.load(f, Loader=yaml.FullLoader)
    for account in yaml_data:
        account['password'] = base64.b64decode(account['password'].encode()).decode()

    return yaml_data


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
    result = {'success': False, 'info': None, 'session': None, 'redirectUrl': None}

    # 验证输入
    if not (username and password):
        result['info'] = '用户名或密码为空'
        return result

    # 获取RSA公钥
    session, pub_key = get_pub_key()
    if not session:
        result['info'] = '获取RSA公钥失败'
        return result

    # 使用服务器返回的RSA公钥加密用户密码
    encrypted_password = rsa_encrypt(password, pub_key)
    if not encrypted_password:
        result['info'] = 'RSA公钥加密用户密码失败'
        return result

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
        res = session.post(url=url, data=data)  # 直接使用data参数

        if res.status_code != 200:
            result['info'] = f'HTTP状态码 {res.status_code}: {res.reason}'
            return result
        response_data = res.json()
        if not response_data['success']:
            result['info'] = response_data.get('info', '未知错误')
            return result
        result['info'] = '登录成功！'
        result['session'] = session
        result['success'] = True
        # 未指定服务，无需重定向，直接返回session
        if response_data['redirectUrl'] is None:
            return result

        # 指定服务，返回重定向url（含ticket）
        redirect_url = unquote(response_data['redirectUrl'])
        result['redirectUrl'] = redirect_url
        return result

    except Exception as e:
        result['info'] = f'登录失败！原因：{str(e)}'
        return result


class API:
    def __init__(self):
        self.accounts = None
        self.load_account_list()

    def load_account_list(self):
        # 如果accounts.yml不存在，则创建一个
        if not os.path.exists('accounts.yml'):
            with open('accounts.yml', 'w') as f:
                f.write('')

        # 使用yaml读取accounts.yml
        self.accounts = decrypt_yaml()

    def get_account_list(self):
        # 去除account中的password，并以json格式返回
        return [
            {
                'name': account['name'],
                'student_id': account['student_id'],
                'comment': account['comment']
            } for account in self.accounts
        ]

    def add_account(self, name: str, student_id: str, password: str, comment: str):
        # 添加账号
        self.accounts.append({
            'name': name,
            'student_id': student_id,
            'password': password,
            'comment': comment
        })
        # 写入accounts.yml
        encrypt_yaml(self.accounts)