# encoding=utf-8
import requests
import json
from ids_encrypt import encryptAES
from bs4 import BeautifulSoup


# 登录信息门户，返回登录后的session
def login(cardnum, password):
    ss = requests.Session()
    form = {"username": cardnum}
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"}
    ss.headers = headers

    #  获取登录页面表单，解析隐藏值
    url = "https://newids.seu.edu.cn/authserver/login?goto=http://my.seu.edu.cn/index.portal"
    res = ss.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    attrs = soup.select('[tabid="01"] input[type="hidden"]')
    for k in attrs:
        if k.has_attr('name'):
            form[k['name']] = k['value']
        elif k.has_attr('id'):
            form[k['id']] = k['value']
    form['password'] = encryptAES(password, form['pwdDefaultEncryptSalt'])
    # 登录认证
    res = ss.post(url, data=form)

    # 登录ehall(存在多次302)
    res = ss.get(
        'http://ehall.seu.edu.cn/login?service=http://ehall.seu.edu.cn/new/index.html')

    # 获取登录信息（验证结果）
    res = ss.get('http://ehall.seu.edu.cn/jsonp/userDesktopInfo.json')

    json_res = json.loads(res.text)
    try:
        name = json_res["userName"]
        print(name[0], "** 登陆成功！")
    except Exception:
        print("认证失败！")
        return False

    return ss
