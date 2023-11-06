# 东南大学 人文与科学素养系列 抢课

位置：信息门户——>学术交流与文体活动

依赖:requests,js2py,bs4,ddddocr

登录代码抄自https://github.com/luzy99/SEUAutoLogin

### 2022/4/20更新
使用ddddocr识别验证码，玄学验证，大概80%成功率。等数据集收集完成可能更新为私有模型。

---------------------------

### 2023/11/6更新
1. seu_auth.py, login_to_ehall.py  改自  https://github.com/Golevka2001/SEU-Auth.git


2. 由于登录讲座页面时无法自动获取cookie，此处采用手动获取cookie的方式

   2.1 进入  http://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do#/hdyy 网站

   2.2 按F12，刷新页面，按如图顺序找到该页面对应cookie
    
   ![图片缺失](./images/cookie.png)

   2.3 将cookie贴入main.py，赋值给main(lecture_cookie)的参数lecture_cookie
   
   ```python
   if __name__ == '__main__':
       lecture_cookie = '[你的cookie]'
       main(lecture_cookie)
   ```

3. 添加了捡漏功能
