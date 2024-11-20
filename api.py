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
import time

import ddddocr
import yaml
from urllib.parse import unquote

from bottle import redirect

from seu_auth import get_pub_key, rsa_encrypt

from fake_useragent import UserAgent

ua = UserAgent()
headers = {'User-Agent': ua.random}


# 加密存储yaml，假装安全
def encrypt_yaml(yaml_data):
    for account in yaml_data:
        account['password'] = base64.b64encode(account['password'].encode()).decode()

    with open('accounts.yml', 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f)


# 读取yaml
def decrypt_yaml():
    with open('accounts.yml', 'r', encoding='utf-8') as f:
        yaml_data = yaml.load(f, Loader=yaml.FullLoader)
    if yaml_data is None:
        return []
    else:
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
        res = session.post(url=url, data=json.dumps(data))  # 直接使用data参数

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


def get_code(ss):
    ocr = ddddocr.DdddOcr()

    c_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do"
    c = ss.get(c_url)
    c_r = c.json()
    c_img = base64.b64decode(c_r['result'].split(',')[1])
    c = ocr.classification(c_img)
    return c, c_img


class API:
    def __init__(self):
        self.session = None
        self.accounts = None
        self.student_id = None
        self.password = None
        self.redirect_url = None
        self.load_account_list()

    def load_account_list(self):
        # 如果accounts.yml不存在，则创建一个
        if not os.path.exists('accounts.yml'):
            with open('accounts.yml', 'w') as f:
                f.write('')
            self.accounts = []
        else:
            # 使用yaml读取accounts.yml
            self.accounts = decrypt_yaml()

    def get_account_list(self):
        # 去除account中的password，并以json格式返回
        print('获取账号列表...')
        return [
            {
                'name': account['name'],
                'student_id': account['student_id'],
                'comment': account['comment'],
                'validity': account['validity']
            } for account in self.accounts
        ]

    # 添加账号时，先尝试登录，确认账号有效，再添加
    def add_account(self, name: str, student_id: str, password: str, comment: str):
        login_result = seu_login(student_id, password)
        if not login_result['success']:
            return {'success': False, 'info': login_result['info']}
        else:
            # 先检查是否有重复,如果有，则替换
            for account in self.accounts:
                if account['student_id'] == student_id:
                    account['password'] = password
                    account['comment'] = comment
                    account['validity'] = True
                    encrypt_yaml(self.accounts)
                    return {'success': True, 'info': '账号已存在，已替换'}

            # 添加账号
            self.accounts.append({
                'name': name,
                'student_id': student_id,
                'password': password,
                'comment': comment,
                'validity': True
            })
            # 写入accounts.yml
            encrypt_yaml(self.accounts)
            return {'success': True, 'info': '添加成功'}

    def delete_account(self, student_id: str):
        for account in self.accounts:
            if account['student_id'] == student_id:
                self.accounts.remove(account)
                encrypt_yaml(self.accounts)
                return {'success': True, 'info': '删除成功'}
        return {'success': False, 'info': '账号不存在'}

    def login(self, student_id: str, password: str = None):
        direct_login = True if password is not None else False
        service_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"
        result = {'success': False, 'info': None}
        if direct_login:
            login_result = seu_login(student_id, password, service_url=service_url)
            result['info'] = login_result['info']
            self.redirect_url = login_result['redirectUrl']
            if not login_result['success']:
                return result
            else:
                self.session = login_result['session']
                result['success'] = True
                return result

        # 从self.accounts中找到student_id对应的密码
        for account in self.accounts:
            if account['student_id'] == student_id:
                password = account['password']

        if password is None:
            result['info'] = '账号不存在'
            return result

        login_result = seu_login(student_id, password, service_url=service_url)
        self.redirect_url = login_result['redirectUrl']
        if not login_result['success']:
            # 有效性改为false
            for account in self.accounts:
                if account['student_id'] == student_id:
                    account['validity'] = False
                # 写入accounts.yml
                encrypt_yaml(self.accounts)
                result['info'] = login_result['info']
                result['success'] = login_result['success']
                return result

        self.session = login_result['session']
        result['info'] = login_result['info']
        result['success'] = True
        self.student_id = student_id
        self.password = password
        return result

    def get_lecture_list(self):
        result = {
            'success': False,
            'info': None,
            'data': None
        }
        try:
            if self.redirect_url is None:
                raise Exception('未获得重定向url')

            # 访问研究生素质讲座系统页面
            res = self.session.get(self.redirect_url, verify=False, timeout=10)
            if res.status_code != 200:
                raise Exception(
                    f"访问研究生素质讲座系统失败[{res.status_code}, {res.reason}]"
                )

            # 获取所有讲座信息
            res = self.session.post("https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do?_="
                                    + str(int(time.time() * 1000)),
                                    data={
                                        "pageIndex": 1,
                                        "pageSize": 100,
                                        "sortField": None,
                                        "sortOrder": None,
                                    })
            if res.status_code != 200:
                result['info'] = f'POST请求失败[{res.status_code}, {res.reason}]'
                raise Exception(f'POST请求失败[{res.status_code}, {res.reason}]')
            raw_lecture_list = res.json()['datas']
            result_data = []
            for raw_lecture in raw_lecture_list:
                result_data.append({
                    'wid': raw_lecture['WID'],
                    'lecture_name': raw_lecture['JZMC'],
                    # 总人数
                    'total_capacity': raw_lecture['HDZRS'],
                    # 已报名人数
                    'order_capacity': raw_lecture['YYRS'],
                    'order_begin_time': raw_lecture['YYKSSJ'],
                    'order_end_time': raw_lecture['YYJSSJ'],
                    'event_begin_time': raw_lecture['JZSJ'],
                    'event_end_time': raw_lecture['HDJSSJ'],
                    # 地点
                    'location': raw_lecture['JZDD'],
                    # 嘉宾
                    'guest': raw_lecture['ZJR'],
                })
            print(result_data)
            result['data'] = result_data
            result['success'] = True
            return result
        except Exception as e:
            print('获取讲座列表失败，错误信息：', e)
            result['info'] = str(e)
            return result

    def get_lecture_info(self, wid):
        result = {
            'success': False,
            'info': None,
            'data': None
        }
        try:
            res = self.session.post("https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/modules/hdyy/hdxxxq_cx.do?WID=" + wid)
            if res.status_code != 200:
                result['info'] = f'POST请求失败[{res.status_code}, {res.reason}]'
                raise Exception(f'POST请求失败[{res.status_code}, {res.reason}]')
            raw_lecture = res.json()['datas']['hdxxxq_cx']['rows'][0]
            print(raw_lecture)
            result['data'] = {
                'wid': raw_lecture['WID'],
                'lecture_name': raw_lecture['JZMC'],
                # 总人数
                'total_capacity': raw_lecture['HDZRS'],
                # 已报名人数
                'order_capacity': raw_lecture['YYRS'],
                'order_begin_time': raw_lecture['YYKSSJ'],
                'order_end_time': raw_lecture['YYJSSJ'],
                'event_begin_time': raw_lecture['JZSJ'],
                'event_end_time': raw_lecture['HDJSSJ'],
                # 地点
                'location': raw_lecture['JZDD'],
                # 嘉宾
                'guest': raw_lecture['ZJR'],
                # 类别
                'type': raw_lecture['JZXL_DISPLAY'],
                # 线上或线下
                'online': raw_lecture['HDFS_DISPLAY'],
                # 所在校区
                'campus': raw_lecture['SZXQ_DISPLAY'],
                # 承办方
                'organizer': raw_lecture['ZBF'],
            }
            result['success'] = True
            return result
        except Exception as e:
            print('获取讲座信息失败，错误信息：', e)
            result['info'] = str(e)
            return result

    def fetch_lecture(self, wid: str):
        result = {
            'success': False,
            'msg': None,
            'code': None
        }
        # 重新登录保证session 有效
        login_result = self.login(self.student_id, self.password)
        if not login_result['success']:
            result['msg'] = '维持登录状态失败:' + login_result['info']
            return login_result
        # 获取讲座当前已抢和未抢人数
        lecture_info = self.get_lecture_info(wid)
        print(lecture_info)
        if not lecture_info['success']:
            result['msg'] = '获取讲座信息失败:' + lecture_info['info']
            return lecture_info
        if lecture_info['data']['order_capacity'] >= lecture_info['data']['total_capacity']:
            result['msg'] = '讲座已满，开始等待'
            return result
        # 获取验证码
        v_code, c_img = get_code(ss=self.session)
        result['code'] = v_code
        # 抢讲座
        url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"
        data_json = {"HD_WID": wid, "vcode": v_code}
        form = {"paramJson": json.dumps(data_json)}
        headers = {
            "Host": "ehall.seu.edu.cn",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://ehall.seu.edu.cn",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        }
        self.session.headers.update(headers)
        r = self.session.post(url, data=form)
        fetch_result = r.json()

        # 如果验证码正确，进行存储
        if '验证码错误' not in fetch_result['msg']:
            # 存储验证码为v_code.png
            with open(f'{v_code}.png', 'wb') as f:
                f.write(c_img)

        result['msg'] = fetch_result['msg']
        result['success'] = fetch_result['success']

        return result
