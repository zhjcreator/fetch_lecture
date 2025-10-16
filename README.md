# 东南大学 人文与科学素养系列 抢课

**许可证：MIT License**

位置：信息门户——>学术交流与文体活动

项目主要依赖：
- 网络请求：requests
- 验证码识别：ddddocr
- 图像处理：Pillow
- 加密解密：pycryptodome
- 终端美化：rich

项目使用uv作为虚拟环境和包管理工具，配置了清华镜像源以加速依赖安装。

感谢：[@Golevka2001](https://github.com/Golevka2001) [@surgery7630](https://github.com/surgery7630) [@DgntYang](https://github.com/DgntYang) [@GeeeekExplorer](https://github.com/GeeeekExplorer)

## 安装依赖与虚拟环境配置

### 环境要求
**Python >= 3.11**（项目pyproject.toml中指定的最低版本）

### 使用uv管理环境与依赖
本项目使用uv作为包管理工具，它比传统的pip更快、更高效。

#### 安装uv（如果尚未安装）
```bash
python -m pip install uv
```

#### 初始化虚拟环境
```bash
uv venv
```

#### 激活虚拟环境
- Windows:
```bash
.venv\Scripts\activate
```
- macOS/Linux:
```bash
source .venv/bin/activate
```

#### 安装项目依赖
项目已配置清华镜像源（在pyproject.toml中），可以加速安装过程：
```bash
uv pip install -e .
# 或者直接从pyproject.toml安装
uv pip install .
```

### 依赖说明
本项目依赖的主要包及其用途：
- **ddddocr (>=1.5.6)**：验证码识别库，用于自动识别讲座预约系统的验证码
- **pillow (>=11.3.0)**：图像处理库，用于处理验证码图片
- **pycryptodome (>=3.23.0)**：加密解密库，用于处理登录认证过程中的密码加密
- **requests (>=2.32.5)**：HTTP请求库，用于与讲座预约系统进行通信
- **rich (>=14.1.0)**：终端美化库，提供彩色输出、进度条等功能，提升用户体验

### 手动安装依赖（可选）
如果需要手动安装依赖，可以使用以下命令：
```bash
pip install ddddocr>=1.5.6 pillow>=11.3.0 pycryptodome>=3.23.0 requests>=2.32.5 rich>=14.1.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 油猴脚本使用说明

### 脚本功能

SEU研究生讲座抢课脚本 v2.4 (原生Cookie版)是一个浏览器扩展脚本，用于自动抢占研究生讲座名额，主要功能包括：

- **一键抢课**：在讲座预约页面为每个讲座添加"立即抢课"按钮
- **定时抢课**：根据讲座开放时间自动开始抢课
- **自动验证码识别**：通过OCR API自动识别验证码
- **会话保活**：定期发送请求保持登录状态，避免会话失效
- **实时日志**：显示抢课过程的详细日志信息
- **状态监控**：实时显示抢课状态和进度

### 油猴插件安装方法

1. **安装油猴插件（Tampermonkey）**：
   - **Chrome/Edge浏览器**：访问 [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo) 安装
   - **Firefox浏览器**：访问 [Firefox Add-ons](https://addons.mozilla.org/zh-CN/firefox/addon/tampermonkey/) 安装
   - **Safari浏览器**：访问 [Safari App Store](https://apps.apple.com/us/app/tampermonkey/id1482490089) 安装
   - 安装完成后，浏览器右上角会出现油猴插件图标

2. **安装脚本**：
   - 点击浏览器右上角的油猴插件图标
   - 选择"添加新脚本"
   - 复制项目中 `greasemonkey.js` 文件的完整内容
   - 粘贴到油猴编辑器中
   - 点击编辑器左上角的"文件" → "保存"（或按Ctrl+S）
   - 脚本安装完成后，会在油猴插件的已安装脚本列表中显示

### 配置设置

1. **OCR API配置**：
   - 默认OCR API地址：`http://127.0.0.1:5000/predict_base64`
   - 可以使用项目中的 `ddddocr_api.py` 作为OCR服务
   - 在脚本界面的输入框中可以自定义OCR API地址并保存

2. **保活功能**：
   - 默认启用会话保活功能（每60秒发送一次请求）
   - 可以通过界面上的复选框启用或禁用保活功能

### 使用步骤

1. **启动OCR服务**：
   - 运行 `ddddocr_api.py` 启动本地OCR服务
   - 确保服务在 `http://127.0.0.1:5000` 端口运行

2. **登录系统**：
   - 打开东南大学研究生讲座预约系统：`https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/`
   - 使用校园账号登录系统

3. **开始抢课**：
   - 页面加载后，脚本会自动注入控制界面
   - 在讲座列表中，点击目标讲座旁的"立即抢课"按钮
   - 脚本会自动进行抢课操作，实时显示进度

4. **查看日志**：
   - 页面右上角会显示实时日志流，记录抢课过程的详细信息
   - 可以查看验证码识别结果、抢课尝试次数等信息

5. **停止抢课**：
   - 点击控制界面中的"停止全部"按钮可以停止所有抢课任务
   - 抢课成功或失败后，任务会自动停止

### 注意事项

- 请确保OCR服务正常运行，否则验证码无法自动识别
- 如遇会话失效，请刷新页面重新登录
- 抢课成功后会有弹窗提示
- 建议在讲座开放前1-2分钟开始准备，确保系统稳定

## 更新日志

**2025/10/09**
- 支持自定义模型识别验证码
- 修复SSL证书验证失败问题

**2025/10/08**
- 支持非可信设备验证码
- 添加指纹生成功能

**2025/10/07**
- 修复验证码识别问题
- 优化登录流程

**2024/06/08**
- 修复指纹识别问题

**2023/10/10**
- 优化验证码识别

**2023/04/22**
- 修复依赖缺失问题

**2023/04/20**
- 修复登录问题

**2023/04/18**
- 修复无法识别验证码问题

**2022/04/20**
- 项目初始化
- 支持讲座列表查询
