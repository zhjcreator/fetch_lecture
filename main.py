import json
import os
import sys
import time
import base64
import random
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



def fetch_lecture(hd_wid: str, ss, ver_code):
    """
    发送抢课（预约）请求，模拟类似 AJAX 的异步数据提交。
    """
    url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"
    
    # 模拟前端通过 POST 发送一个包含 JSON 字符串的 'paramJson' 字段
    data_payload = {"HD_WID": hd_wid, "vcode": ver_code}
    form_data = {"paramJson": json.dumps(data_payload)}
    
    # 设置 HTTP Headers，模拟浏览器发送 AJAX 请求
    headers = {
        # ... (大部分保持不变，确保 Content-Type 正确)
        "Host": "ehall.seu.edu.cn",
        "Accept": "application/json, text/javascript, */*; q=0.01",  # 典型的 AJAX 接受类型
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://ehall.seu.edu.cn",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "X-Requested-With": "XMLHttpRequest", # 模拟 AJAX 请求的关键 header
    }
    
    ss.headers.update(headers)
    
    try:
        # 使用 form_data 发送请求
        r = ss.post(url, data=form_data)
        
        # 如果返回的是网页，说明返回值错误
        if r.headers.get("Content-Type", "").startswith("text/html"):
            return 500,'请求错误，返回值为网页', False
        
        result = r.json()

        if result.get("success", False):
            console.print(Panel.fit(f"[bold green]抢课成功！[/]\n{json.dumps(result, indent=2)}", title="成功"))
            sys.exit(0)
        
        return result.get("code", -1), result.get("msg", "未知错误"), result.get("success", False)

    except requests.exceptions.RequestException as e:
        return 500, f"网络请求异常: {str(e)}", False
    except json.JSONDecodeError:
        return 500, f"响应解析失败，非JSON格式: {r.text[:100]}...", False


def get_code(ss, captcha_hash_table=None):
    c_url = f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do?_={int(time.time() * 1000)}"
    c = ss.post(c_url)
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

        res = session.get(redirect_url, verify=False)
        if res.status_code != 200:
            raise Exception(f"访问研究生素质讲座系统失败[{res.status_code}, {res.reason}]")

        # 在访问 ehall 前重新 mount TLSAdapter
        session.mount("https://", TLSAdapter())
        session.mount("http://", TLSAdapter())       
        return session
    except Exception as e:
        error_console.print(Panel.fit(f"[bold red]✗ 登录失败: {str(e)}[/]", title="错误"))
        return None


def get_lecture_list(session):
    try:
        res = session.post(
            f"https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryActivityList.do?_={int(time.time() * 1000)}",
            data={"pageIndex": 1, "pageSize": 100},
            verify=False  # 禁用SSL证书验证
        )
        lecture_list = res.json()["datas"]
        stu_cnt_arr = [[int(l["HDZRS"]), int(l["YYRS"])] for l in lecture_list]

        console.print("[bold green]✓ 获取讲座列表成功[/]")
        return session, lecture_list, stu_cnt_arr
    except Exception as e:
        error_console.print(f"[bold red]✗ 获取讲座列表失败: {str(e)}[/]")
        return None, None, None


def login_and_get_lecture_list(username: str, password: str, fingerprint=None):
    session = login(username, password, fingerprint)
    if session is None:
        return None, None, None

    return get_lecture_list(session)


def print_lecture_list(lecture_list: list):
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

# 第一次登录：获取讲座列表和初始Session
    console.print(Panel.fit(f"[bold]🕒 {time.ctime()} 首次尝试登录系统并获取讲座列表...[/]", title="状态"))
    s, lecture_list, stu_cnt_arr = login_and_get_lecture_list(user_name, password, fingerprint)
    if lecture_list is None:
        error_console.print("[bold red]✗ 登录或获取讲座列表失败，退出程序[/]")
        sys.exit(1)
        
    print_lecture_list(lecture_list)

    # 选择讲座 (保持不变)
    target_index = Prompt.ask("请输入课程序号", console=console, default="0")
    try:
        lecture_info = lecture_list[int(target_index)]
    except (ValueError, IndexError, TypeError):
        error_console.print("[bold red]✗ 输入的课程序号无效，请输入有效的序号[/]")
        sys.exit(1)
    wid = lecture_info["WID"]

    if not Confirm.ask(f"确认选择讲座 [cyan]{lecture_info['JZMC']}[/]", default=True, console=console):
        sys.exit(0)

    # 等待抢课 - 使用本地时间
    target_time = datetime.datetime.strptime(lecture_info["YYKSSJ"], "%Y-%m-%d %H:%M:%S")
    
    # 提前重新登录的时间（秒）。目标时间前 10 秒重新登录，确保 session 最新
    RELOGIN_BEFORE_SECONDS = 10 
    
    # 倒计时延迟（秒）。目标时间结束后再延迟 0.5 秒开始抢课循环
    START_DELAY_SECONDS = 0.5 

    with Progress() as progress:
        start_time = datetime.datetime.now()
        total_seconds = (target_time - start_time).total_seconds()
        
        # total_seconds 可能为负，确保总数合理
        task = progress.add_task(
            f"[red]等待抢课 | 目标时间: {target_time.strftime('%H:%M:%S')}",
            total=max(total_seconds, 1) # 至少是 1
        )
        
        relogin_done = False

        while True:
            current_time = datetime.datetime.now()
            remaining = (target_time - current_time).total_seconds()
            
            # 检查是否需要提前重新登录
            if not relogin_done and 0 < remaining <= RELOGIN_BEFORE_SECONDS:
                console.rule(f"[bold yellow]🕒 目标时间前 {RELOGIN_BEFORE_SECONDS} 秒，进行二次登录...[/]")
                s = login(user_name, password, fingerprint)
                if s is None:
                    error_console.print("[bold red]✗ 提前二次登录失败，退出程序[/]")
                    sys.exit(1)
                console.print("[bold green]✓ 二次登录成功！[/]")
                relogin_done = True


            if remaining <= -START_DELAY_SECONDS:
                # 倒计时结束且延迟时间已过
                progress.update(task, completed=max(total_seconds, 1))
                break
            
            if remaining <= 0:
                 # 已经到达目标时间，开始延迟计时
                progress.update(
                    task,
                    completed=total_seconds,
                    description=f"[bold red]⏰ 目标已到，延迟 {abs(remaining):.2f} / {START_DELAY_SECONDS:.2f} 秒开始抢课...[/]"
                )
                time.sleep(0.01) # 微小延迟，保持 CPU 占用合理
                continue
            
            # 正常倒计时更新
            progress.update(
                task,
                completed=total_seconds - remaining, # 计算已完成的进度
                description=f"[bold cyan]⏳ 剩余时间: {str(datetime.timedelta(seconds=int(remaining)))}.{int((remaining % 1) * 10):<1} 秒[/] | 目标时间: {target_time.strftime('%H:%M:%S')}"
            )
            
            # 根据剩余时间调整休眠，越接近目标时间越频繁
            if remaining > 60:
                time.sleep(1)
            elif remaining > 10:
                time.sleep(0.5)
            elif remaining > 2:
                time.sleep(0.1)
            else:
                time.sleep(0.01) # 接近 0 时采用更精细的等待

    # 抢课循环开始
    console.rule(f"[bold red]🚀 延迟 {START_DELAY_SECONDS} 秒结束，开始抢课！[/]")
    
    # 确保在开始抢课时 s 是最新的（如果在倒计时期间没有触发二次登录，这里相当于补一个）
    if not relogin_done:
         console.rule("[bold yellow]🕒 未触发二次登录，进行最终登录检查...[/]")
         s = login(user_name, password, fingerprint)
         if s is None:
             error_console.print("[bold red]✗ 最终登录失败，退出程序[/]")
             sys.exit(1)
         console.print("[bold green]✓ 最终登录检查成功，开始抢课！[/]")
    
    # 创建验证码保存目录 (保持不变)
    if save_code:
        os.makedirs("code_img/true", exist_ok=True)
        os.makedirs("code_img/false", exist_ok=True)
    
    # 第一次获取验证码
    v_code, v_img = get_code(ss=s, captcha_hash_table=captcha_hash_table)
    attempt = 1
    while True:
        # 获取最新讲座列表
        s, _, stu_cnt_arr = get_lecture_list(s)
        try:
            with console.status(
                    f"[bold][yellow]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/yellow] - 第 {attempt} 次尝试..."
            ):

                if stu_cnt_arr and stu_cnt_arr[int(target_index)][0] <= stu_cnt_arr[int(target_index)][1]:  # pyright: ignore[reportOptionalSubscript]
                    console.print("[yellow]当前人数已满，等待下次尝试...[/]")
                    attempt += 1
                    time.sleep(1)
                    continue

                code, msg, success = fetch_lecture(wid, s, v_code)
                style = "green" if success else "red" if "频繁" in msg else "yellow"
                console.print(f"[{style}]» 状态码: {code}\n   消息: {msg}\n   成功: {success}[/]")

                if "验证码错误" in msg:
                    # 保存验证码
                    if save_code:
                        with open(f"code_img/false/captcha_{attempt}_code{v_code}.jpg", "wb") as f:
                            f.write(v_img)

                    # 验证码错误后随机延迟 0.1-0.9 秒
                    random_delay = random.uniform(0.1, 0.9)
                    time.sleep(random_delay)
                    
                    v_code, v_img = get_code(ss=s, captcha_hash_table=captcha_hash_table)
                    continue
                else:
                    # 保存验证码
                    if save_code:
                        with open(f"code_img/true/captcha_{attempt}_code{v_code}.jpg", "wb") as f:
                            f.write(v_img)

                if success:
                    break

                if "频繁" in msg:
                    console.print("[yellow]请求过于频繁，等待 10 秒后重试...[/]")
                    time.sleep(10)

                attempt += 1
                time.sleep(0.5)
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