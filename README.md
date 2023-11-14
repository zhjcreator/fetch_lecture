![image](https://github.com/zhjcreator/fetch_lecture/assets/55911606/744c9a1c-f84f-453e-b66b-ab63c944fc28)# 东南大学 人文与科学素养系列 抢课

位置：信息门户——>学术交流与文体活动

依赖：网络请求 - requests，验证码识别 - ddddocr，加解密 - pycryptodome

感谢：[@Golevka2001](https://github.com/Golevka2001) [@surgery7630](https://github.com/surgery7630) [@DgntYang](https://github.com/DgntYang) [@GeeeekExplorer](https://github.com/GeeeekExplorer)

## 安装依赖

**要求 Python <= 3.9**

```shell
# 虚拟环境【可选】
python -m venv lecture_venv
source lecture_venv/bin/activate
# 安装依赖
pip install -r requirements.txt
```

ddddocr 库体积较大且 pypi.org 访问速度较慢，建议使用镜像源，如：`-i https://pypi.tuna.tsinghua.edu.cn/simple`

## 更新日志

### 2023/11/13 更新

1. 修复 [Issue #8](https://github.com/zhjcreator/fetch_lecture/issues/8) 反馈的问题，错误原因为：身份认证后忘记更新 Headers，Content-Type 没有从 `application/json` 改为 `application/x-www-form-urlencoded`。目前本地测试通过，如仍存在问题请继续反馈。

### 2023/11/12 更新

1. 修复 ddddocr 与 pillow 版本的问题，且限制 python 版本在 3.9 及以下
2. TODO：[Issue #8](https://github.com/zhjcreator/fetch_lecture/issues/8) 反馈的问题，需等待下一轮预约开放后测试

### 2023/11/7 更新

1. 修复身份验证问题（没有手动获取 cookie 的必要）

2. 更新依赖

3. 剔除旧版/无用代码

### 2023/11/6 更新

1. seu_auth.py, login_to_ehall.py 改自 https://github.com/Golevka2001/SEU-Auth.git

2. 由于登录讲座页面时无法自动获取 cookie，此处采用手动获取 cookie 的方式

   2.1 进入 http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do#/hdyy 网站

   2.2 按 F12，刷新页面，按如图顺序找到该页面对应 cookie

   ![图片缺失](./images/cookie.png)

   2.3 将 cookie 贴入 main.py，赋值给 main(lecture_cookie)的参数 lecture_cookie

   ```python
   if __name__ == '__main__':
       lecture_cookie = '[你的cookie]'
       main(lecture_cookie)
   ```

3. 添加了捡漏功能

### 2022/4/20 更新

使用 ddddocr 识别验证码，玄学验证，大概 80%成功率。等数据集收集完成可能更新为私有模型。
