import json
import os
import sys
import time
import base64
import random  # 引入 random 模块
from hashlib import md5
from io import BytesIO
import select
import datetime

import ddddocr
import requests
from PIL import Image
from rich.console import Console
from rich.progress import Progress
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

from seu_auth import seu_login  # 确保该模块存在

# 初始化 rich 组件
console = Console()
error_console = Console(stderr=True, style="bold red")

# 是否保存验证码
save_code = False

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):  # 判断是否处于打包环境
        base_path = getattr(sys, '_MEIPASS', '')  # 临时解压路径
    else:
        base_path = os.path.abspath(".")
    return str(os.path.join(base_path, relative_path))

import ssl
from requests.adapters import HTTPAdapter

class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        # 兼容性设置，避免某些低版本 TLS 握手问题
        ctx.set_ciphers("DEFAULT@SECLEVEL=1") 
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

# 生成浏览器指纹
def generate_fingerprint():
    # 仿照984ba064c2399f4b5c379df8aaeb995a生成，同样字符数，随机生成
    fingerprint = md5(str(time.time()).encode()).hexdigest()
    return fingerprint

# 【新增】统一的 Headers 配置
def get_common_headers():
    return {
        "Host": "ehall.seu.edu.cn",
        # 关键：模仿浏览器 AJAX 行为
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://ehall.seu.edu.cn",
        "X-Requested-With": "XMLHttpRequest", # 关键：模仿 BH_UTILS.doAjax 行为
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/m/home", # 模仿从首页发出的请求
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36" # 完整UA
    }


def fetch_lecture(hd_wid: str, ss: requests.Session, ver_code):
    url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"
    data_json = {"HD_WID": hd_wid, "vcode": ver_code}
    form = {"paramJson": json.dumps(data_json)}
    
    # 【修正 1：应用统一的 Headers】
    headers = get_common_headers()
    # POST 请求需要精确的 Content-Type
    headers['Content-Type'] = "application/x-www-form-urlencoded; charset=UTF-8"
    
    ss.headers.update(headers)
    
    # 增加超时，防止阻塞
    try:
        r = ss.post(url, data=form, timeout=5)
    except requests.exceptions.Timeout:
        return 504, '抢课请求超时', False
    
    # 如果返回的是网页，说明会话失效
    if r.headers.get("Content-Type", "").startswith("text/html"):
        return 500, '请求错误，返回值为网页 (会话可能失效)', False

    try:
        result = r.json()
    except json.JSONDecodeError:
        return 500, f'响应解析失败，非JSON格式: {r.text[:100]}...', False

    if result.get("success", False):
        console.print(Panel.fit(f"[bold green]抢课成功！[/]\n{json.dumps(result, indent=2)}", title="成功"))
        sys.exit(0)
        
    # 增加对会话过期或登录失效的检查
    if "登录" in result.get("msg", "") or "会话" in result.get("msg", "") or result.get("code") == "401":
        return 401, '会话已过期，请重新登录', False
        
    return result["code"], result["msg"], result.get("success", False)


def get_code(ss: requests.Session, captcha_hash_table=None):
    # 【修正 2：确保 get_code 也使用统一 Headers】
    headers = get_common_headers()
    headers.pop('Content-Type') # GET/POST 不带 body 时不需要
    ss.headers.update(headers)
    
    c_url = f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do?_={int(time.time() * 1000)}"
    c = ss.post(c_url, timeout=5)
    
    if c.headers.get("Content-Type", "").startswith("text/html"):
        raise Exception('获取验证码失败，返回了 HTML 页面 (会话可能失效)')
        
    c_r = c.json()
    c_img = base64.b64decode(c_r["result"].split(",")[1])
    result = ""

    if captcha_hash_table:
        img = Image.open(BytesIO(c_img))
        with BytesIO() as output:
            img.save(output, format="JPEG")
            hash_val = md5(output.getvalue()).hexdigest()
        if hash_val in captcha_hash_table:
            result = captcha_hash_table[hash_val]

    if not result:
        result = ocr.classification(c_img)

    return result, c_img

def get_mobile_verify_code(ss, username: str):
    url = "https://auth.seu.edu.cn/auth/casback/sendStage2Code"
    data = {"userId": username}
    res = ss.post(url, data=json.dumps(data))
    if res.json()["success"] != True:
        raise Exception(f"发送手机验证码失败[{res.status_code}, {res.json()}]")
    else:
        console.print(Panel.fit(f"[bold yellow]⚠ {res.json()['info']}[/]", title="提示"))

def login(username: str, password: str, fingerprint=None):
    try:
        service_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do"
        # 初始登录尝试
        session, redirect_url, error_type = seu_login(username, password, service_url, fingerprint)
        
        if error_type == 'non_trusted_device':
            console.print(Panel.fit(f"[bold yellow]⚠ 非可信设备登录，需要输入手机验证码[/]", title="提示"))
            get_mobile_verify_code(session, username)
            phone_code = Prompt.ask("请输入手机验证码")
            session, redirect_url, error_type = seu_login(username, password, service_url, fingerprint, phone_code)
        
        if not session:
            raise Exception("统一身份认证平台登录失败")
        if not redirect_url:
            raise Exception("获取重定向url失败")

        # 访问 ehall 前重新 mount TLSAdapter
        # 必须先 mount 再 get，以确保 TLS 协商正确
        session.mount("https://", TLSAdapter())
        session.mount("http://", TLSAdapter()) 
        
        res = session.get(redirect_url, verify=False)
        if res.status_code != 200:
            raise Exception(f"访问研究生素质讲座系统失败[{res.status_code}, {res.reason}]")

        # 【新增：在登录成功后设置公共 Headers】
        session.headers.update(get_common_headers())

        return session
    except Exception as e:
        error_console.print(Panel.fit(f"[bold red]✗ 登录失败: {str(e)}[/]", title="错误"))
        return None


def get_lecture_list(session: requests.Session):
    try:
        # 【修正 3：确保 get_lecture_list 使用统一 Headers】
        headers = get_common_headers()
        session.headers.update(headers)
        
        res = session.post(
            f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do?_={int(time.time() * 1000)}",
            data={"pageIndex": 1, "pageSize": 100},
            verify=False,  # 禁用SSL证书验证
            timeout=5
        )
        
        if res.headers.get("Content-Type", "").startswith("text/html"):
            raise Exception('获取列表失败，返回了 HTML 页面 (会话可能失效)')
            
        lecture_list = res.json()["datas"]
        stu_cnt_arr = [[int(l["HDZRS"]), int(l["YYRS"])] for l in lecture_list]

        # console.print("[bold green]✓ 获取讲座列表成功[/]") # 频繁调用时注释，避免刷屏
        return session, lecture_list, stu_cnt_arr
    except Exception as e:
        # error_console.print(f"[bold red]✗ 获取讲座列表失败: {str(e)}[/]") # 频繁调用时注释，避免刷屏
        return None, None, None


def login_and_get_lecture_list(username: str, password: str, fingerprint=None):
    session = login(username, password, fingerprint)
    if session is None:
        return None, None, None

    return get_lecture_list(session)


def print_lecture_list(lecture_list: list):
    # 保持不变
    try:
        table = Table(title="研究生素质讲座列表", show_header=True, header_style="bold magenta")
        table.add_column("序号", style="cyan")
        # table.add_column("WID", style="blue", width=20)
        table.add_column("讲座名称")
        table.add_column("预约时间")
        table.add_column("活动时间")

        for idx, lecture in enumerate(lecture_list):
            table.add_row(
                str(idx),
                # lecture["WID"],
                lecture["JZMC"],
                f"{lecture['YYKSSJ']}至{lecture['YYJSSJ']}",
                lecture["JZSJ"]
            )
        console.print(table)
    except Exception as e:
        error_console.print(f"打印讲座列表失败: {str(e)}")

# 从服务器返回数据head中date字段获取当前时间，替代datetime.datetime.now()
def get_current_time_from_server(session: requests.Session):
    # 保持不变，但增加统一 Headers 确保请求稳定
    try:
        headers = get_common_headers()
        session.headers.update(headers)
        
        res = session.post(
            f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do?_={int(time.time() * 1000)}",
            data={"pageIndex": 1, "pageSize": 100},
            timeout=5
        )
        date_str = res.headers['Date']
        console.print(f"[bold green]✓ 获取服务器时间成功: {date_str}[/]")

        date_format = "%a, %d %b %Y %H:%M:%S %Z"
        server_time = datetime.datetime.strptime(date_str, date_format)
        server_time = server_time.replace(tzinfo=datetime.timezone.utc)
        # 转换为本地时间 (假设您的服务器与目标服务器时区差)
        # 服务器返回的是 GMT/UTC，需要转换为东八区时间 (UTC+8)
        server_time_local = server_time + datetime.timedelta(hours=8)
        
        # 不再提前一秒，让抢课逻辑控制精确时间
        # server_time = server_time + datetime.timedelta(seconds=1) 
        
        return server_time_local
    except Exception as e:
        error_console.print(f"[bold red]✗ 获取服务器时间失败: {str(e)}[/]，使用当前时间代替")
        # 如果失败，使用本地时间代替，并加上微小随机延迟
        return datetime.datetime.now() + datetime.timedelta(seconds=random.uniform(0.1, 0.5))


if __name__ == "__main__":
    # 初始化验证码组件
    onnx_path = resource_path("model.onnx")
    charsets_path = resource_path("charsets.json")
    captcha_hash_table_path = resource_path("captcha_hash_table.csv")
    ocr = ddddocr.DdddOcr(import_onnx_path=onnx_path, charsets_path=charsets_path, show_ad=False)
    captcha_hash_table = {}
    if os.path.exists(captcha_hash_table_path):
        with open(captcha_hash_table_path) as f:
            for line in f:
                if line.strip():
                    hash_val, label = line.strip().split(",")
                    captcha_hash_table[hash_val] = label

    # 用户认证
    with console.status("[bold green]正在读取配置文件...") as status:
        try:
            with open("config.txt") as f:
                stu_info = [line.strip() for line in f if line.strip()]
                user_name, password, fingerprint = stu_info[0], stu_info[1], stu_info[2]
        except Exception:
            status.stop()  # 关键：停止状态动画
            console.print(Panel.fit("[yellow]⚠ 将在当前目录创建 config.txt 文件[/]", title="提示"))
            user_name = Prompt.ask("请输入学号", console=console)
            password = Prompt.ask("请输入密码", password=True, console=console)
            fingerprint = generate_fingerprint()
            with open("config.txt", "w") as f:
                f.write(f"{user_name}\n{password}\n{fingerprint}\n")

    # 获取讲座列表
    console.print(Panel.fit(f"[bold]🕒 {time.ctime()} 开始登录系统...[/]", title="状态"))
    s, lecture_list, stu_cnt_arr = login_and_get_lecture_list(user_name, password, fingerprint)
    
    if lecture_list is None:
        error_console.print("[bold red]✗ 登录失败或讲座列表为空，退出程序[/]")
        sys.exit(1)
        
    print_lecture_list(lecture_list)
    

    # 选择讲座
    target_index = Prompt.ask("请输入课程序号", console=console, default="0")
    try:
        lecture_info = lecture_list[int(target_index)]
    except (ValueError, IndexError, TypeError):
        error_console.print("[bold red]✗ 输入的课程序号无效，请输入有效的序号[/]")
        sys.exit(1)
    wid = lecture_info["WID"]

    if not Confirm.ask(f"确认选择讲座 [cyan]{lecture_info['JZMC']}[/]", default=True, console=console):
        sys.exit(0)

    # 等待抢课
    assert s is not None, "会话对象不能为空"
    start_time = get_current_time_from_server(s)
    # 将预约开始时间字符串解析为 datetime 对象
    target_time = datetime.datetime.strptime(lecture_info["YYKSSJ"], "%Y-%m-%d %H:%M:%S")
    
    # 【修正：使用目标时间减去服务器当前时间来计算总进度】
    target_timestamp = target_time.timestamp()
    start_timestamp = start_time.timestamp()
    
    if target_timestamp < start_timestamp:
        console.print("[bold yellow]⚠ 预约时间已过，将立即开始抢课循环...[/]")
        total_time = 0
    else:
        total_time = target_timestamp - start_timestamp
        
    with Progress() as progress:
        task = progress.add_task(
            f"[red]等待抢课 | 目标时间: {target_time.strftime('%H:%M:%S')}",
            total = total_time # 确保总进度是正值
        )

        last_keep_alive_time = time.time() # 记录上次保活时间
        KEEP_ALIVE_INTERVAL = 5 # 每 5 秒保活一次

        while True:
            current_time = datetime.datetime.now()
            remaining = (target_time - current_time).total_seconds()
            current_timestamp = current_time.timestamp()

            if current_timestamp >= target_timestamp:
                progress.update(task, completed = total_time)
                break
            
            # 【保活逻辑】
            if time.time() - last_keep_alive_time >= KEEP_ALIVE_INTERVAL:
                # 尝试保活并获取最新讲座列表
                s_updated, _, stu_cnt_arr_updated = get_lecture_list(s)
                
                if s_updated is None:
                    # 保活失败（会话可能过期），尝试重新登录
                    error_console.print("[bold red]会话保活失败，尝试重新登录...[/]")
                    s = login(user_name, password, fingerprint)
                    if s is None:
                        # 如果重新登录仍然失败，则退出
                        error_console.print("[bold red]重新登录失败，退出程序[/]")
                        sys.exit(1)
                    s_updated, _, stu_cnt_arr_updated = get_lecture_list(s) # 重新登录后再次获取列表
                    
                if s_updated:
                    s = s_updated # 更新 session
                    if stu_cnt_arr_updated:
                        stu_cnt_arr = stu_cnt_arr_updated
                        
                    # 显示剩余人数
                    lecture_idx = int(target_index)
                    if stu_cnt_arr and lecture_idx < len(stu_cnt_arr):
                        total, booked = stu_cnt_arr[lecture_idx]
                        available = total - booked
                        console.print(f"[bold green]✓ 会话保活成功，剩余人数: {available} | 距离抢课: {int(remaining)}s[/]")
                    else:
                        console.print("[bold yellow]⚠ 会话保活成功，但无法获取剩余人数信息[/]")
                
                last_keep_alive_time = time.time() # 更新保活时间
                
            # 【进度条更新】
            # 确保进度条完成度不超过总时长
            completed_progress = max(0, min(total_time, current_timestamp - start_timestamp))
            progress.update(
                task,
                completed = completed_progress,
                description = f"[bold cyan]等待抢课，剩余时间: {str(datetime.timedelta(seconds=int(remaining)))}[/] | 目标时间: {target_time.strftime('%H:%M:%S')}"
            )
            
            # 动态校准延时（精确到毫秒级）
            # 当剩余时间较多时，每 100 毫秒检查一次；当接近目标时间时，进行毫秒级等待
            if remaining > 5:
                 time_to_sleep = 0.1
            else:
                 time_to_sleep = max(0.005, (remaining % 1) / 2) # 最后 5 秒内进行更频繁的检查
                 
            time.sleep(time_to_sleep)


    # 开始抢课
    console.rule("[bold red]🚀 开始抢课！[/]")
    
    # 【抢课开始前，立即获取最新验证码和列表，确保会话最新】
    console.print("[bold yellow]立即获取最新验证码...[/]")
    try:
        s_updated, _, stu_cnt_arr_updated = get_lecture_list(s)
        if s_updated: s = s_updated
        if stu_cnt_arr_updated: stu_cnt_arr = stu_cnt_arr_updated
        
        # 增加微小随机延迟，模仿人类行为，避免瞬间发包
        time.sleep(random.uniform(0.05, 0.15)) 
        
        v_code, v_img = get_code(ss=s, captcha_hash_table=captcha_hash_table)
        console.print(f"[bold green]✓ 初始验证码获取成功: {v_code}[/]")
    except Exception as e:
        error_console.print(f"[bold red]‼ 抢课前初始验证码或列表获取失败: {str(e)}[/]")
        sys.exit(1)
        
    attempt = 1
    while True:
        try:
            with console.status(
                f"[bold][yellow]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/yellow] - 第 {attempt} 次尝试..."
            ):
                
                # 1. 检查余量（每 3 次抢课检查一次列表）
                if attempt % 3 == 1:
                    # 【增加随机微小延迟】
                    time.sleep(random.uniform(0.05, 0.15)) 
                    assert s is not None, "会话对象不能为空"

                    s_updated, _, stu_cnt_arr_updated = get_lecture_list(s)
                    if s_updated: s = s_updated
                    if stu_cnt_arr_updated: stu_cnt_arr = stu_cnt_arr_updated

                lecture_idx = int(target_index)
                if stu_cnt_arr and lecture_idx < len(stu_cnt_arr):
                    total, booked = stu_cnt_arr[lecture_idx]
                    available = total - booked
                    
                    if available <= 0:
                        console.print("[yellow]当前人数已满，等待下次尝试...[/]")
                        attempt += 1
                        time.sleep(1)
                        continue
                else:
                    console.print("[yellow]无法获取最新人数信息，继续尝试抢课...[/]")


                # 2. 抢课请求
                # 【增加随机微小延迟】
                time.sleep(random.uniform(0.05, 0.15)) 
                
                code, msg, success = fetch_lecture(wid, s, v_code)
                style = "green" if success else "red" if "频繁" in msg else "yellow"
                console.print(f"[{style}]» 状态码: {code}\n   消息: {msg}\n   成功: {success}[/]")

                if success:
                    break

                if "验证码错误" in msg or "验证码为空" in msg:
                    # 验证码错误，立即获取新的
                    if save_code:
                        if not os.path.exists("code_img/false"): os.makedirs("code_img/false")
                        with open(f"code_img/false/captcha_{attempt}_code{v_code}.jpg", "wb") as f:
                            f.write(v_img)
                            
                    # 【增加随机微小延迟】
                    time.sleep(random.uniform(0.05, 0.15)) 
                    v_code, v_img = get_code(ss=s, captcha_hash_table=captcha_hash_table)
                    console.print(f"[yellow]重新获取验证码: {v_code}[/]")
                    attempt += 1 # 不计入 0.5 秒等待，直接进入下一轮
                    continue
                
                elif "会话已过期" in msg or "会话可能失效" in msg or code == 401:
                    error_console.print("[bold red]‼ 会话已失效，尝试重新登录并获取验证码...[/]")
                    s = login(user_name, password, fingerprint)
                    if s is None:
                        error_console.print("[bold red]重新登录失败，退出程序[/]")
                        sys.exit(1)
                        
                    # 重新登录后立即获取新的列表和验证码
                    s, _, stu_cnt_arr = get_lecture_list(s)
                    assert s is not None, "会话对象不能为空"

                    v_code, v_img = get_code(ss=s, captcha_hash_table=captcha_hash_table)
                    attempt += 1
                    time.sleep(1) # 重新登录后多等待 1 秒
                    continue

                elif "频繁" in msg:
                    console.print("[yellow]请求过于频繁，等待 10 秒后重试...[/]")
                    # 【频繁请求等待较久】
                    time.sleep(10)

                elif "已预约" in msg:
                    break
                
                else:
                    # 其他错误，继续尝试
                    pass
                
                # 3. 失败后的一般延迟
                attempt += 1
                time.sleep(random.uniform(0.4, 0.6)) # 随机延迟 0.4s - 0.6s

        except Exception as e:
            error_console.print(f"[bold red]‼ 发生异常: {str(e)}[/]")
            time.sleep(1)

    # 退出处理
    console.print(Panel.fit("[bold]按任意键退出...[/]", title="完成"))
    while True:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.read(1)
            console.print("[italic]退出程序[/]")
            sys.exit(0)
        time.sleep(0.1)