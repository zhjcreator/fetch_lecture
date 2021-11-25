import sys

import requests, json
from login import login
import time
import threading
import copy


def fetch_lecture(hd_wid: str, ss):
    url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/yySave.do"
    data_json = {'HD_WID': hd_wid}
    form = {"paramJson": json.dumps(data_json)}
    r = ss.post(url, data=form)
    result = r.json()
    if result['success'] is not False:
        print(result)
        sys.exit(0)
    return result['code'], result['msg'], result['success']


def multi_threads(ss, threads_id, hd_wid: str):
    i = 1
    while True:
        code, msg, success = fetch_lecture(hd_wid, ss)
        print('线程{},第{}次请求,code：{},msg：{},success:{}'.format(threads_id, i, code, msg, success))
        if success is True or msg == '当前活动预约人数已满，请重新选择！' or msg == '已经预约过该活动，无需重新预约！':
            sys.exit(0)
        i += 1
        time.sleep(0.3)


def get_lecture_list(ss):
    url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do#/hdyy"
    ss.get(url)
    url = "http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/modules/hdyy/hdxxxs.do"
    form = {"pageSize": 12, "pageNumber": 1}
    r = ss.post(url, data=form)
    response = r.json()
    rows = response['datas']['hdxxxs']['rows']
    return rows


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


# 按间距中的绿色按钮以运行脚本。
if __name__ == '__main__':
    user_name = None
    password = None
    stu_info = None
    try:
        with open('config.txt', 'r') as f:
            stu_info = [line.strip() for line in f]
    except Exception as identifier:
        print('将在本程序同级目录下创建config.txt文件，请按要求填写学号、密码，即可自动登录')

    if stu_info and len(stu_info):
        try:
            user_name = stu_info[0]
            password = stu_info[1]
        except IndexError as identifier:
            print("请在config.txt配置正确的账号密码，即可自动登录")

    if not user_name and not password:
        user_name = input("请输入学号：").strip()
        password = input("请输入密码：").strip()
        with open('config.txt', 'wb') as f:
            f.write("{}\n".format(user_name).encode())
            f.write("{}\n".format(password).encode())

    print(time.ctime(), " 开始登陆")
    s = login(user_name, password)
    while s is False or s is None:
        print("请重新登陆")
        print("请输入帐号:")
        user_name = input()
        print("请输入密码:")
        password = input()
        print("开始登陆")
        s = login(user_name, password)
    print("登陆成功")
    print("----------------课程列表----------------")
    lecture_list = get_lecture_list(s)
    target_index = None
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
    lecture_info = False
    while True:
        print("请输入课程序号：")
        target_index = int(input().strip())
        lecture_info = lecture_list[target_index]
        wid = lecture_info['WID']
        # lecture_info = get_lecture_info(wid, s)
        if lecture_info is not False:
            print("确认讲座名称：{}. y/n".format(lecture_info['JZMC']))
            confirm = input().strip()
            if confirm == 'y' or confirm == 'Y':
                break
            else:
                pass
    print("请输入提前几秒开始抢（请保证本地时间准确）：")
    advance_time = int(input().strip())
    current_time = int(time.time())
    begin_time = int(time.mktime(time.strptime(lecture_info['YYKSSJ'], "%Y-%m-%d %H:%M:%S")))
    end_time = int(time.mktime(time.strptime(lecture_info['YYJSSJ'], "%Y-%m-%d %H:%M:%S")))
    if current_time > end_time:
        print("抢课时间已结束，大侠请重新来过")
        sys.exit(0)
    while current_time < begin_time - advance_time:
        current_time = int(time.time())
        print('等待{}秒'.format(begin_time - advance_time - current_time))
        time.sleep(1)
        print(time.ctime(), '开始抢课')
    t1 = threading.Thread(target=multi_threads, args=(copy.deepcopy(s), 't1', wid))
    t2 = threading.Thread(target=multi_threads, args=(copy.deepcopy(s), 't2', wid))
    t3 = threading.Thread(target=multi_threads, args=(copy.deepcopy(s), 't3', wid))
    t1.start()
    time.sleep(0.1)
    t2.start()
    time.sleep(0.1)
    t3.start()
