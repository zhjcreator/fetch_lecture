import base64
import json
import sys
import time

import ddddocr  # 导入 ddddocr

from seu_auth import seu_login

ocr = ddddocr.DdddOcr()


def fetch_lecture(hd_wid: str, ss, ver_code):
    url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"
    data_json = {'HD_WID': hd_wid, 'vcode': ver_code}
    form = {"paramJson": json.dumps(data_json)}
    r = ss.post(url, data=form)
    result = r.json()
    if result['success'] is not False:
        print(result)
        sys.exit(0)
    return result['code'], result['msg'], result['success']


def get_code(ss):
    c_url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/vcode.do"
    c = ss.get(c_url)
    c_r = c.json()
    c_img = base64.b64decode(c_r['result'].split(',')[1])
    c = ocr.classification(c_img)
    return c, c_img


# def multi_threads(ss, threads_id, hd_wid: str, ver_code):
#     i = 1
#     while True:
#         code, msg, success = fetch_lecture(hd_wid, ss, ver_code)
#         print('线程{},第{}次请求,code：{},msg：{},success:{}'.format(threads_id, i, code, msg, success))
#         if success is True or msg == '当前活动预约人数已满，请重新选择！' or msg == '已经预约过该活动，无需重新预约！':
#             sys.exit(0)
#         i += 1
#         time.sleep(0.3)


def get_lecture_list(username: str, password: str):
    """登录到研究生素质讲座系统，用于后续在此系统中进行其他操作。

    Args:
        username: 一卡通号
        password: 统一身份认证密码

    Returns:
        session: 登录到研究生素质讲座系统后的session
        lecture_list: 查询到的研究生素质讲座列表
        stu_cnt_arr: 二维数组，每个元素为[讲座总人数, 已预约人数]
    """
    try:
        # 登录统一身份认证平台
        service_url = 'http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do'
        session, redirect_url = seu_login(username, password, service_url)
        if not session:
            raise Exception('统一身份认证平台登录失败')
        if not redirect_url:
            raise Exception('获取重定向url失败')

        # 访问研究生素质讲座系统页面
        res = session.get(redirect_url)
        if res.status_code != 200:
            raise Exception(f'访问研究生素质讲座系统失败[{res.status_code}, {res.reason}]')
        # 获取所有讲座信息
        res = session.post(
            'http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/modules/hdyy/hdxxxs.do',
            data={
                'pageSize': 100,
                'pageNumber': 1
            })
        if res.status_code != 200:
            raise Exception(f'POST请求失败[{res.status_code}, {res.reason}]')
        lecture_list = res.json()['datas']['hdxxxs']['rows']
        stu_cnt_arr = [[0, 0] for _ in range(len(lecture_list))]
        for i, lecture in enumerate(lecture_list):
            stu_cnt_arr[i][0] = int(lecture['HDZRS'])
            stu_cnt_arr[i][1] = int(lecture['YYRS'])
        print('获取讲座列表成功')

        return session, lecture_list, stu_cnt_arr
    except Exception as e:
        print('获取讲座列表失败，错误信息：', e)
        return None, None, None


def get_lecture_info(w_id, ss):
    url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/modules/hdyy/hdxxxq_cx.do"
    data_json = {'WID': w_id}
    r = ss.post(url, data=data_json)
    try:
        result = r.json()['datas']['hdxxxq_cx']['rows'][0]
        return result
    except Exception:
        print("课程信息获取失败")
        return False


if __name__ == '__main__':
    ##### 读取/创建用户账号配置文件 #####
    user_name = None
    password = None
    stu_info = None
    try:
        with open('config.txt', 'r') as f:
            stu_info = [line.strip() for line in f]
    except Exception:
        print('将在本程序同级目录下创建config.txt文件，请按要求填写学号、密码，即可自动登录')

    if stu_info and len(stu_info):
        try:
            user_name = stu_info[0]
            password = stu_info[1]
        except Exception:
            print("请在config.txt配置正确的账号密码，即可自动登录")

    if not user_name and not password:
        user_name = input("请输入学号：").strip()
        password = input("请输入密码：").strip()
        with open('config.txt', 'wb') as f:
            f.write("{}\n".format(user_name).encode())
            f.write("{}\n".format(password).encode())

    ##### 登录 + 爬取课程列表 #####
    print(time.ctime(), "开始登录")
    s, lecture_list, stu_cnt_arr = get_lecture_list(user_name, password)
    print("登录成功")

    print("----------------课程列表----------------")
    for index, lecture in enumerate(lecture_list):
        print('序号：', end='')
        print(index, end=' ')
        print("课程wid：", end=" ")
        print(lecture['WID'], end="  |  ")
        print("课程名称：", end=" ")
        print(lecture['JZMC'], end="  |  ")
        print("预约开始时间：", end=" ")
        print(lecture['YYKSSJ'], end="  |  ")
        print("预约结束时间：", end=" ")
        print(lecture['YYJSSJ'], end="  |  ")
        print("活动时间：")
        print(lecture['JZSJ'])
    print("----------------课程列表end----------------")

    ##### 选择课程 #####
    lecture_info = False
    while True:
        target_index = int(input("请输入课程序号：").strip())
        lecture_info = lecture_list[target_index]
        wid = lecture_info['WID']
        confirm = input(f"确认讲座名称 {lecture_info['JZMC']} (y/n)：").strip()
        if confirm == 'y' or confirm == 'Y':
            break
    advance_time = int(
        input("请输入提前几秒开始抢（请保证本地时间准确，抢课频率受到限制，连续抢10次左右，建议2秒）：").strip())
    current_time = int(time.time())
    begin_time = int(
        time.mktime(time.strptime(lecture_info['YYKSSJ'],
                                  "%Y-%m-%d %H:%M:%S")))
    end_time = int(
        time.mktime(time.strptime(lecture_info['YYJSSJ'],
                                  "%Y-%m-%d %H:%M:%S")))
    if current_time > end_time:
        print("抢课时间已结束，大侠请重新来过")
        sys.exit(0)
    while current_time < begin_time - advance_time:
        current_time = int(time.time())
        print('等待{}秒'.format(begin_time - advance_time - current_time))
        time.sleep(1)

    ##### 抢 #####
    print(time.ctime(), '开始抢课')
    v_code, _ = get_code(ss=s)
    i = 1
    while True:
        try:
            s, _, stu_cnt_arr = get_lecture_list(user_name, password)
            if stu_cnt_arr[target_index][0] > stu_cnt_arr[target_index][1]:
                code, msg, success = fetch_lecture(wid, s, v_code)
                print(f'第{i}次请求，code：{code}，msg：{msg}，success: {success}')
                if success or '请求过于频繁' in msg:
                    break
                if '验证码错误' in msg or '人数已满' in msg:
                    v_code, _ = get_code(ss=s)
                i += 1
            else:
                print("当前人数已满，进入等待状态！已等待时间: {}s".format(
                    int(time.time()) - current_time))
                continue

        except Exception:
            continue
        finally:
            time.sleep(0.5)
