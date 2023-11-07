# 东南大学 人文与科学素养系列 抢课

位置：信息门户——>学术交流与文体活动

依赖：
网络请求 - requests
验证码识别 - ddddocr
加解密 - pycryptodome

感谢：
@Golevka2001 @surgery7630 @DgntYang

## 更新日志

### 2023/11/7 更新

1. 修复身份验证问题（没有手动获取 cookie 的必要）

2. 更新依赖（现可支持 python 3.11）

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
