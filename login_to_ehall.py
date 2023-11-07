from seu_auth import seu_login


def login_to_ehall(username, password):
    """登录到网上办事服务大厅，用于后续访问网上办事服务大厅的其他应用。

    Args:
        username: 一卡通号
        password: 统一身份认证密码

    Returns:
        session: 登录到网上办事服务大厅后的session
    """
    try:
        # 登录统一身份认证平台
        service_url = 'http://ehall.seu.edu.cn/login?service=http://ehall.seu.edu.cn/new/index.html'
        session, redirect_url = seu_login(username, password, service_url)
        if not session:
            raise Exception('Login failed')

        # 更新Headers。UA必填，其他目前无所谓
        session.headers = {
            # 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;'
            #           'q=0.8,application/signed-exchange;v=b3;q=0.7',
            # 'Accept-Encoding': 'gzip, deflate',
            # 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            # 'Connection': 'keep-alive',
            # 'DNT': '1',
            # 'Host': 'ehall.seu.edu.cn',
            # 'Upgrade-Insecure-Requests': '1',
            'Content-Type':
            'application/x-www-form-urlencoded',
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/102.0.0.0 Safari/537.36',
        }

        # 访问网上办事服务大厅首页
        res = session.get(redirect_url)
        if res.status_code != 200:
            raise Exception('Cannot access ehall page')

        # 获取用户身份信息，检查是否登录成功
        user_info_url = 'http://ehall.seu.edu.cn/jsonp/userDesktopInfo.json?type=&_=1693121329211'
        res = session.get(user_info_url)
        if res.status_code != 200:
            raise Exception('Cannot get user information')
        if 'userId' in res.json():
            if res.json()['userId'] == username:
                print(
                    f'Successfully login to ehall, name: {res.json()["userName"][0]}**'
                )
            else:
                raise Exception('Id not match')
        else:
            raise Exception('Cannot get user information')

        return session
    except Exception as e:
        print('Failed to login to ehall, info:', e)
        return None
