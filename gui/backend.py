"""
后端服务层：封装登录、讲座列表获取、抢课、已预约查询等核心逻辑。
从 main.py 中提取，供 GUI 调用。
"""
import json
import os
import sys
import time
import base64
import random
import logging
import logging.handlers
import urllib3
from hashlib import md5
from io import BytesIO

import ddddocr
import requests
from PIL import Image

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from seu_auth import seu_login

# JSON 解析工具：跳过前导垃圾字节，找到第一个 { 或 [ 开始解析
import re
_JSON_START_RE = re.compile(r'[\[\{]')

def _parse_json(res):
    """尝试从响应中解析 JSON，自动跳过前导不可见字节（BOM、gzip 残留等）。"""
    try:
        return res.json()
    except (json.JSONDecodeError, Exception):
        text = res.text
        m = _JSON_START_RE.search(text)
        if m:
            try:
                return json.loads(text[m.start():])
            except (json.JSONDecodeError, Exception):
                return None
        return None

# 日志（与 app.py 共享同一个日志文件）
_LOG_DIR = os.path.join(PROJECT_ROOT, "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_log_file = os.path.join(_LOG_DIR, "bookings_refresh.log")
_fh = logging.handlers.RotatingFileHandler(
    _log_file, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_log = logging.getLogger("backend")
_log.setLevel(logging.DEBUG)
_log.addHandler(_fh)

import ssl
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)


class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，资源文件在临时解压目录 _MEIPASS 下
        base_path = getattr(sys, '_MEIPASS', '')
    else:
        # 开发环境：以当前文件所在目录（gui/）为基准，返回上级目录（项目根目录）
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return str(os.path.join(base_path, relative_path))


# 全局 OCR 实例（延迟初始化）
_ocr = None
_captcha_hash_table = None


def _init_ocr():
    global _ocr, _captcha_hash_table
    if _ocr is not None:
        return
    # 自定义模型 model.onnx 已与当前验证码格式不兼容，改用默认内置模型
    captcha_hash_table_path = resource_path("captcha_hash_table.csv")
    _ocr = ddddocr.DdddOcr(show_ad=False)
    _captcha_hash_table = {}
    if os.path.exists(captcha_hash_table_path):
        with open(captcha_hash_table_path) as f:
            for line in f:
                if line.strip():
                    hash_val, label = line.strip().split(",", 1)
                    _captcha_hash_table[hash_val] = label


class FetchLectureBackend:
    CAPTCHA_TTL = 5  # 验证码缓存秒数，短时间内验证码不会变，避免重复请求

    def __init__(self, session):
        self.session = session
        _init_ocr()
        self._captcha_code = None
        self._captcha_time = 0

    def get_code(self):
        """获取并识别验证码。短时间内复用缓存，避免重复请求。"""
        now = time.time()
        if self._captcha_code and now - self._captcha_time < self.CAPTCHA_TTL:
            return self._captcha_code

        c_url = f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do?_={int(time.time() * 1000)}"
        c_headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": getattr(self.session, "ehall_referer",
                               "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"),
            "X-Requested-With": "XMLHttpRequest",
        }
        c = self.session.post(c_url, headers=c_headers)
        try:
            c_r = c.json()
        except Exception:
            raise RuntimeError("验证码接口繁忙，响应非JSON")
        if "result" not in c_r:
            raise RuntimeError("验证码接口繁忙，响应缺少result字段")
        c_img = base64.b64decode(c_r["result"].split(",")[1])
        result = ""

        if _captcha_hash_table:
            img = Image.open(BytesIO(c_img))
            with BytesIO() as output:
                img.save(output, format="JPEG")
                hash_val = md5(output.getvalue()).hexdigest()
            if hash_val in _captcha_hash_table:
                result = _captcha_hash_table[hash_val]

        if not result:
            result = _ocr.classification(c_img)

        if result:
            # 只有非空验证码才缓存，空验证码不缓存以免一直发空请求
            self._captcha_code = result
            self._captcha_time = now
        else:
            self._captcha_code = None
            _log.warning("验证码识别失败（空结果），下次重新获取")
        return result

    @staticmethod
    def login(username: str, password: str, fingerprint=None):
        """
        登录统一身份认证 + 讲座系统，返回 (session, error_info)。
        成功时 error_info 为 None，失败时 session 为 None。
        当 error_info == 'non_trusted_device' 时，session 为 auth session（可用于发送验证码）。
        """
        service_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"
        session, redirect_url, error_info = seu_login(username, password, service_url, fingerprint)

        if error_info == 'non_trusted_device':
            return session, 'non_trusted_device'  # session 可用于发送验证码

        if error_info:
            return None, error_info

        if not session or not redirect_url:
            return None, "登录失败：未获取到有效会话"

        # 先挂 TLSAdapter，再访问 redirect_url
        # 原因：redirect_url 是 http://，服务器会 302 到 https://，
        # 若 TLSAdapter 未装好就跟随重定向，校园网 TLS 握手会失败，导致 cookie 未注入
        session.mount("https://", TLSAdapter())
        session.mount("http://", TLSAdapter())

        # seu_auth.py 中 session 全局 header 含 Content-Type: application/json，
        # 会污染后续 form data 请求，这里清掉，让各接口自行指定
        session.headers.pop("Content-Type", None)

        try:
            res = session.get(redirect_url, verify=False, allow_redirects=True)
            if res.status_code != 200:
                return None, f"访问讲座系统失败: HTTP {res.status_code}"
            # 保存 ehall 首页完整 URL（含 gid_ 等安全参数），供后续请求作为 Referer
            session.ehall_referer = res.url
        except Exception as e:
            return None, f"访问讲座系统异常: {e}"
        return session, None

    @staticmethod
    def send_phone_code(username, session):
        """
        向服务器发送手机验证码。使用已有的 auth session（已含 cookie）。
        返回 (success, error_info)。
        """
        session.headers.update({
            'Content-Type': 'application/json',
        })
        send_url = "https://auth.seu.edu.cn/auth/casback/sendStage2Code"
        try:
            res = session.post(send_url, data=json.dumps({"userId": username}))
            if res.status_code != 200:
                return False, f"HTTP {res.status_code} {res.reason}"
            try:
                result = res.json()
            except Exception:
                return False, f"服务器返回非JSON响应 (HTTP {res.status_code})"
            if result.get("success"):
                return True, None
            return False, result.get("info", "发送验证码失败")
        except Exception as e:
            return False, f"发送验证码异常: {e}"

    @staticmethod
    def login_with_phone(username, password, fingerprint, phone_code):
        """
        带手机验证码的登录（验证码已发送，直接登录）。
        """
        from seu_auth import get_pub_key, rsa_encrypt
        from urllib.parse import unquote

        service_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"

        # 重新获取公钥并登录
        session2, pub_key = get_pub_key()
        if not session2 or not pub_key:
            return None, "获取公钥失败"

        enc_password = rsa_encrypt(password, pub_key)
        enc_phone_code = rsa_encrypt(phone_code, pub_key)

        login_url = 'https://auth.seu.edu.cn/auth/casback/casLogin'
        data = {
            'captcha': '', 'loginType': 'account', 'mobilePhoneNum': '',
            'mobileVerifyCode': enc_phone_code, 'password': enc_password,
            'rememberMe': False, 'service': service_url,
            'username': username, 'wxBinded': False,
        }
        if fingerprint:
            data['fingerPrint'] = fingerprint

        res = session2.post(url=login_url, data=json.dumps(data))
        result = res.json()

        if not result.get('success'):
            return None, result.get('info', '登录失败')

        redirect_url = result.get('redirectUrl')
        if redirect_url:
            redirect_url = unquote(redirect_url)
            session2.mount("https://", TLSAdapter())
            session2.mount("http://", TLSAdapter())
            res = session2.get(redirect_url, verify=False, allow_redirects=True)
            session2.ehall_referer = res.url
            return session2, None

        return None, "获取重定向URL失败"

    @staticmethod
    def get_lecture_list(session):
        """
        获取可预约讲座列表。返回 (session, lecture_list, stu_cnt_arr)。
        服务器繁忙时返回空值而不抛异常，让抢课循环继续。
        """
        try:
            res = session.post(
                f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do?_={int(time.time() * 1000)}",
                data={"pageIndex": 1, "pageSize": 100},
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                verify=False
            )
            final_url = str(res.url) if res.url else ""

            # 优先尝试解析 JSON
            data = _parse_json(res)
            if data is None:
                return session, None, None

            # 如果 JSON 里有 datas 字段，说明正常返回
            if "datas" in data:
                pass  # 继续下面的处理
            elif "vpn.seu.edu.cn" in final_url:
                raise RuntimeError("当前不在校园网，请连接 EasyConnect VPN 后重试")
            elif "login" in final_url or "portal" in final_url:
                raise RuntimeError("session 已失效，请重新登录")
            else:
                # 服务器返回异常JSON但非VPN/登录问题，视为繁忙
                return session, None, None

            lecture_list = data["datas"]
            stu_cnt_arr = [[int(l["HDZRS"]), int(l["YYRS"])] for l in lecture_list]
            return session, lecture_list, stu_cnt_arr
        except RuntimeError:
            # VPN/登录失效等需要上层的致命错误，继续抛出
            raise
        except Exception:
            # 网络异常等，返回空让抢课继续
            return session, None, None

    @staticmethod
    def get_my_bookings(session, page=1, page_size=50):
        """
        获取已预约讲座列表。
        """
        url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryMyActivityList.do"
        res = session.post(
            f"{url}?_={int(time.time() * 1000)}",
            data={"pageIndex": page, "pageSize": page_size, "sortField": "", "sortOrder": ""},
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            verify=False
        )
        data = _parse_json(res)
        if data is None:
            final_url = str(res.url) if res.url else ""
            if "vpn.seu.edu.cn" in final_url:
                raise RuntimeError("当前不在校园网，请连接 EasyConnect VPN 后重试")
            return []

    def fetch_lecture(self, hd_wid: str):
        """
        发送抢课请求。返回 (code, msg, success)。
        服务器繁忙时返回友好提示而非致命错误，让抢课循环继续重试。
        """
        try:
            v_code = self.get_code()
        except RuntimeError as e:
            return 500, str(e), False
        if not v_code:
            _log.warning("验证码识别为空，跳过本次请求")
            return 500, "验证码识别失败", False
        url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"

        data_payload = {"HD_WID": hd_wid, "vcode": v_code}
        form_data = {"paramJson": json.dumps(data_payload)}

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": getattr(self.session, "ehall_referer",
                               "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"),
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            r = self.session.post(url, data=form_data, headers=headers, verify=False)

            if not r.text.strip():
                _log.warning("yySave HTTP %s: 响应为空", r.status_code)
                return 500, "服务器繁忙，无响应内容", False
            if r.headers.get("Content-Type", "").startswith("text/html"):
                _log.warning("yySave HTTP %s: 返回HTML页面 (前200字符): %s", r.status_code, r.text[:200])
                return 500, "服务器繁忙，返回异常页面", False

            result = _parse_json(r)
            if result is None:
                prefix = r.content[:20] if r.content else b''
                _log.warning("yySave HTTP %s: 响应非JSON (前200字符): %s | 原始前20字节hex: %s",
                             r.status_code, r.text[:200], prefix.hex())
                return 500, "服务器繁忙，响应非JSON", False

            code = result.get("code", -1)
            msg = result.get("msg", "未知错误")
            success = result.get("success", False)
            if success:
                _log.info("yySave 成功: code=%s msg=%s", code, msg)
            else:
                _log.warning("yySave 失败: code=%s msg=%s", code, msg)
            return code, msg, success

        except requests.exceptions.RequestException as e:
            return 500, f"服务器繁忙，请求异常: {str(e)[:80]}", False

    def check_booking_success(self, target_wid: str, max_page: int = 5, session=None) -> bool:
        """
        通过查询已预约讲座列表，判断指定讲座是否预约成功。
        查询失败时返回 False（而非抛异常），让抢课循环继续重试。
        """
        s = session or self.session
        url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryMyActivityList.do"
        for page in range(1, max_page + 1):
            try:
                res = s.post(
                    f"{url}?_={int(time.time() * 1000)}",
                    data={"pageIndex": page, "pageSize": 10, "sortField": "", "sortOrder": ""},
                    verify=False
                )
                result = _parse_json(res)
                if result is None:
                    continue
                datas = result.get("datas", [])

                for item in datas:
                    if item.get("HD_WID") == target_wid:
                        return True

                if len(datas) < 10:
                    break

            except Exception:
                # 服务器繁忙，查询失败，返回 False 继续抢
                return False

        return False
