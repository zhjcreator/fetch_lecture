// ==UserScript==
// @name          SEU研究生讲座抢课脚本 v2.2 (流式增强修复版)
// @namespace     http://tampermonkey.net/
// @version       2.2
// @description   修复了 v2.1 导致的页面显示问题，并实现关键信息流式实时显示。
// @author        Improved & Gemini
// @match         https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*
// @grant         GM_xmlhttpRequest
// @grant         GM_setValue
// @grant         GM_getValue
// @require       https://cdn.jsdelivr.net/npm/sweetalert2@11
// @run-at        document-idle
// ==/UserScript==

(function() {
    'use strict';

    console.log("✅ SEU Grab Script v2.2 (Stream Enhanced Fix) is Running!");

    const BASE_URL = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/";
    const KEY_OCR = 'seu_grab_ocr_endpoint';
    const OCR_TIMEOUT = 10000;

    let g_config = {
        ocrEndpoint: GM_getValue(KEY_OCR, 'http://127.0.0.1:5000/predict_base64'),
        isGrabbing: false,
        ocrRetryCount: 0
    };
    let g_activeGrabWID = null;
    let g_streamLogCounter = 0; // 记录流式日志条数

    // --- 状态与日志显示函数 ---

    /**
     * 更新全局状态显示 (仅顶部控制栏)
     */
    function updateStatus(msg) {
        const statusEl = document.getElementById('global-status-seu');
        if (statusEl) statusEl.textContent = `状态: ${msg}`;
        console.log(`[STATUS] ${msg}`);
    }

    /**
     * 向流式显示容器追加日志
     */
    function logStream(msg, level = 'info') {
        const streamEl = document.getElementById('seu-stream-log');
        if (!streamEl) {
            console.log(`[Stream Log] ${msg}`);
            return;
        }

        g_streamLogCounter++;
        const now = new Date().toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

        let color = '#333';
        if (level === 'error') color = 'red';
        else if (level === 'success') color = 'green';
        else if (level === 'warn') color = 'orange';
        else if (level === 'critical') color = 'darkred';

        const logEntry = document.createElement('p');
        logEntry.style.margin = '0';
        logEntry.style.fontSize = '12px';
        logEntry.style.lineHeight = '1.4';
        logEntry.style.color = color;
        logEntry.innerHTML = `**[#${g_streamLogCounter}] [${now}]** ${msg}`;

        // 确保容器不会无限增大，只保留最新的约 50 条记录
        if (streamEl.children.length >= 50) {
            streamEl.removeChild(streamEl.children[0]);
        }

        streamEl.appendChild(logEntry);
        streamEl.scrollTop = streamEl.scrollHeight; // 滚动到底部实现流式效果
        console.log(`[${level.toUpperCase()}] ${msg}`);
    }

    // --- 网络请求与核心函数 (增强日志) ---

    /**
     * 带超时的 fetch 封装 (GM_xmlhttpRequest)
     */
    function fetchWithTimeout(url, options = {}, timeout = 10000) {
        return new Promise((resolve, reject) => {
             Promise.race([
                 new Promise((_, timeoutReject) =>
                     setTimeout(() => timeoutReject(new Error('请求超时')), timeout)
                 ),
                 new Promise((fetchResolve, fetchReject) => {
                     const defaultHeaders = {
                         "Host": "ehall.seu.edu.cn",
                         "Accept": "application/json, text/javascript, */*; q=0.01",
                         "Referer": "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*default/index.do",
                         ...options.headers
                     };

                     GM_xmlhttpRequest({
                         method: options.method || 'GET',
                         url: url,
                         headers: defaultHeaders,
                         data: options.data,
                         onload: fetchResolve,
                         onerror: fetchReject,
                         ontimeout: () => fetchReject(new Error('网络请求超时'))
                     });
                 })
             ]).then(resolve).catch(reject);
         });
    }

    /**
    * 调用 ddddocr HTTP API（仅尝试一次）
    */
    async function callOcrApi(base64Image, ocrEndpoint) {
        if (!ocrEndpoint) throw new Error('请配置 ddddocr HTTP API 地址');

        // 提取 Base64 数据部分
        const b64_data = base64Image.includes(',')
        ? base64Image.split(",")[1]
        : base64Image;

        if (!b64_data) {
            // 可能是图片抓取失败导致 base64Image 是空的
            throw new Error('Base64 图片数据为空，无法发送 OCR 请求');
        }

        try {
            // 尝试进行一次 API 调用
            const response = await fetchWithTimeout(
                ocrEndpoint,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    data: JSON.stringify({ img_b64: b64_data })
                },
                OCR_TIMEOUT
            );

            if (response.status !== 200) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = JSON.parse(response.responseText);
            // 兼容 ddddocr 的 'result' 和其他接口的 'text' 字段
            const ocrResult = (result.result || result.text || '').trim();

            if (!ocrResult) {
                // 如果 API 调用成功但返回结果为空
                throw new Error('OCR 识别结果为空');
            }

            logStream(`✓ OCR 识别成功: **${ocrResult}**`, 'success');
            return ocrResult;

        } catch (error) {
            // 捕获所有错误（网络错误、HTTP 状态码错误、JSON 解析错误、识别结果为空）
            logStream(`**OCR 识别失败:** ${error.message}`, 'error');
            // 将错误抛出给上层调用者 (getCode) 处理
            throw new Error(`OCR 识别失败: ${error.message}`);
        }
    }

    /**
     * 获取验证码 (带重试)
     */
    async function getCode(retryCount = 0) {
        try {
            logStream(`正在获取验证码 (第 ${retryCount + 1} 次)...`);
            const c_url = BASE_URL + `hdyy/vcode.do?_=${Date.now()}`;
            const response = await fetchWithTimeout(c_url, {
                method: 'POST'
            }, 5000);

            const c_r = JSON.parse(response.responseText);
            if (!c_r.result) throw new Error('验证码接口返回数据错误');

            const c_img_base64 = c_r.result;
            const result_code = await callOcrApi(c_img_base64, g_config.ocrEndpoint);

            return { v_code: result_code, v_img: c_img_base64 };

        } catch (error) {
            if (retryCount < 2) {
                logStream(`验证码获取失败，1秒后重试... 详情: ${error.message}`, 'warn');
                await new Promise(r => setTimeout(r, 1000));
                return getCode(retryCount + 1);
            }
            throw error;
        }
    }

    /**
     * 抢课请求
     */
    async function fetchLecture(hd_wid, ver_code) {
        const url = BASE_URL + "hdyy/yySave.do";
        const data_json = { "HD_WID": hd_wid, "vcode": ver_code };
        const form_data = `paramJson=${encodeURIComponent(JSON.stringify(data_json))}`;
        logStream(`**[REQUEST]** 发送抢课请求: WID=${hd_wid}, VCode=${ver_code}`);

        const response = await fetchWithTimeout(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
            data: form_data
        }, 5000);

        const result = JSON.parse(response.responseText);
        return {
            code: result.code,
            msg: result.msg,
            success: result.success || false
        };
    }

    /**
     * 获取讲座列表
     */
    async function getLectureList() {
        const url = BASE_URL + `hdyy/queryActivityList.do?_=${Date.now()}`;
        const response = await fetchWithTimeout(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            data: 'pageIndex=1&pageSize=100'
        }, 5000);

        const json_data = JSON.parse(response.responseText);
        if (!json_data.datas) throw new Error('讲座列表为空或格式错误');

        injectGrabButtons(json_data.datas);
        return json_data.datas;
    }

    /**
     * 高精度倒计时
     */
    async function waitUntil(targetTime, name) {
        logStream(`**开始倒计时:** 【${name}】预约开始时间：${targetTime.toLocaleTimeString()}`);
        while (g_config.isGrabbing) {
            const now = Date.now();
            let remaining = targetTime.getTime() - now;

            if (remaining <= 0) break;

            if (remaining > 1000) {
                updateStatus(`【${name}】倒计时: **${(remaining / 1000).toFixed(1)}s**`);
                await new Promise(r => setTimeout(r, 100));
            } else if (remaining > 50) {
                updateStatus(`【${name}】倒计时: **${remaining}ms**`);
                await new Promise(r => setTimeout(r, remaining / 10));
            } else {
                while (Date.now() < targetTime.getTime() && g_config.isGrabbing) { }
                break;
            }
        }
    }

    /**
     * 核心抢课逻辑
     */
    async function startGrab(wid, yykssj, name, buttonElement) {
        if (g_config.isGrabbing) {
             logStream(`有其他任务正在进行中 (WID: ${g_activeGrabWID})，本次操作被忽略。`, 'warn');
             Swal.fire('提示', '请先停止当前抢课任务', 'warning');
             return;
        }

        g_activeGrabWID = wid;
        g_config.isGrabbing = true;
        g_streamLogCounter = 0; // 重置日志计数器

        const targetTime = new Date(yykssj.replace(/-/g, "/"));
        const originalText = buttonElement.textContent;
        buttonElement.style.backgroundColor = '#ff9800';
        buttonElement.textContent = '抢课中...';

        logStream(`--- **开始抢课任务：【${name}】** ---`, 'critical');
        logStream(`目标 WID: ${wid}`, 'info');

        try {
            // 倒计时等待
            const remaining = targetTime.getTime() - Date.now();
            if (remaining > 50) {
                await waitUntil(targetTime, name);
            }
            logStream(`倒计时结束，立即开始抢课循环...`, 'critical');

            if (!g_config.isGrabbing) return;

            // 抢课循环
            let attempt = 1;
            let v_code = '';
            let lastOcrTime = 0;

            while (g_config.isGrabbing) {
                try {
                    updateStatus(`【${name}】第 ${attempt} 次尝试...`);
                    logStream(`**[ATTEMPT ${attempt}]** 开始尝试抢课...`, 'info');

                    // 1. 获取列表 (保活 + 检查余量)
                    const list = await getLectureList();
                    const lecture = list.find(l => l.WID === wid);

                    if (!lecture) throw new Error('讲座已下架或列表获取失败');

                    const total = parseInt(lecture.HDZRS);
                    const booked = parseInt(lecture.YYRS);
                    const available = total - booked;
                    logStream(`余量检查: 总 ${total} / 已 ${booked} / 剩余 **${available}**`);

                    if (available <= 0) {
                        logStream(`人数已满，暂停 2s 等待余量变化...`, 'warn');
                        await new Promise(r => setTimeout(r, 2000));
                        attempt++;
                        continue;
                    }

                    // 2. 获取验证码 (每次或错误时)
                    if (!v_code || attempt % 3 === 0) {
                        if (Date.now() - lastOcrTime < 1500) {
                             await new Promise(r => setTimeout(r, 1500 - (Date.now() - lastOcrTime)));
                        }
                        const codeResult = await getCode();
                        v_code = codeResult.v_code;
                        lastOcrTime = Date.now();
                        logStream(`获取新验证码: **${v_code}**`);
                    }

                    // 3. 发送抢课请求
                    const result = await fetchLecture(wid, v_code);

                    if (result.success) {
                        g_config.isGrabbing = false;
                        logStream(`**🎉🎉🎉 抢课成功!** 消息: ${result.msg}`, 'critical');
                        Swal.fire('成功！', `【${name}】预约成功！`, 'success');
                        updateStatus(`【${name}】抢课成功！`);
                        break;
                    }

                    // 4. 错误处理
                    if (result.msg.includes('验证码')) {
                        v_code = '';
                        logStream(`抢课失败: **验证码错误**，重新获取验证码...`, 'warn');
                    } else if (result.msg.includes('频繁')) {
                        logStream(`抢课失败: **请求频繁**，等待 5s...`, 'warn');
                        await new Promise(r => setTimeout(r, 5000));
                    } else if (result.msg.includes('已预约')) {
                         g_config.isGrabbing = false;
                         logStream(`**✅ 抢课任务结束：** ${result.msg}`, 'success');
                         Swal.fire('提示', `【${name}】${result.msg}`, 'info');
                         break;
                    } else {
                        logStream(`抢课失败: **${result.msg}**`, 'error');
                    }

                    attempt++;
                    await new Promise(r => setTimeout(r, 300));
                } catch (e) {
                    logStream(`**[ATTEMPT ${attempt}]** 抢课循环发生异常: ${e.message}`, 'error');
                    attempt++;
                    await new Promise(r => setTimeout(r, 1000));
                }
            }

        } catch (e) {
            logStream(`**[CRITICAL]** 任务异常中断: ${e.message}`, 'critical');
            Swal.fire('异常', e.message, 'error');
            updateStatus(`错误: ${e.message}`);
        } finally {
            logStream(`--- **抢课任务结束：【${name}】** ---`, 'critical');
            g_activeGrabWID = null;
            g_config.isGrabbing = false;
            buttonElement.style.backgroundColor = '#4CAF50';
            buttonElement.textContent = originalText;
        }
    }

    // --- 界面交互函数 ---

    /**
     * 处理抢课按钮点击
     */
    function handleGrabButtonClick(event) {
        event.preventDefault();
        const btn = event.currentTarget;
        const wid = btn.getAttribute('data-wid');
        const yykssj = btn.getAttribute('data-yykssj');
        const name = btn.getAttribute('data-name');

        if (!wid) {
            Swal.fire('错误', '无法获取讲座 ID', 'error');
            return;
        }

        if (g_config.isGrabbing && g_activeGrabWID === wid) {
            Swal.fire('提示', '该讲座已在抢课中', 'warning');
            return;
        }

        if (g_config.isGrabbing && g_activeGrabWID !== wid) {
            Swal.fire('提示', '请先停止当前抢课任务', 'warning');
            return;
        }

        startGrab(wid, yykssj, name, btn);
    }

    /**
     * 停止抢课
     */
    function handleStopClick() {
        if (g_activeGrabWID) {
            const activeBtn = document.querySelector(`.grab-btn-seu[data-wid="${g_activeGrabWID}"]`);
            if (activeBtn) {
                activeBtn.style.backgroundColor = '#4CAF50';
                activeBtn.textContent = '立即抢课';
            }
        }
        g_config.isGrabbing = false;
        g_activeGrabWID = null;
        updateStatus('已停止');
        logStream('**手动停止全部抢课任务**', 'critical');
        Swal.close();
    }

    /**
     * 注入按钮
     */
    function injectGrabButtons(lectureList) {
        const tbody = document.querySelector('tbody[id^="tbody_"]');
        if (!tbody) return;

        const rows = tbody.querySelectorAll('tr');
        rows.forEach((row, index) => {
            const lecture = lectureList[index];
            if (!lecture || row.querySelector('.grab-btn-seu')) return;

            const actionCell = row.querySelector('td:first-child');
            if (!actionCell) return;

            // 清除原有内容（如官方的“立即预约”）
            actionCell.innerHTML = '';

            const btnHtml = `
                 <button class="grab-btn-seu"
                     data-wid="${lecture.WID}"
                     data-yykssj="${lecture.YYKSSJ}"
                     data-name="${lecture.JZMC}"
                     style="padding: 5px 8px; background-color: #4CAF50; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 12px; margin: 2px;">
                     立即抢课
                 </button>
            `;

            actionCell.insertAdjacentHTML('beforeend', btnHtml);
            actionCell.querySelector('.grab-btn-seu').addEventListener('click', handleGrabButtonClick);

            if (g_activeGrabWID === lecture.WID) {
                const btn = actionCell.querySelector('.grab-btn-seu');
                btn.style.backgroundColor = '#ff9800';
                btn.textContent = '抢课中...';
            }
        });
    }

    /**
     * 注入控制栏 (修复版，使用 position: fixed 实现悬浮日志)
     */
    function injectControlHeader() {
        if (document.getElementById('seu-control-header')) return;

        g_config.ocrEndpoint = GM_getValue(KEY_OCR, g_config.ocrEndpoint);

        const headerHtml = `
            <div id="seu-control-header" style="margin-bottom: 15px; padding: 10px; border: 2px solid #4CAF50; border-radius: 4px; background-color: #f9f9f9;">
                <h3 style="margin-top: 0; color: #4CAF50;">🎓 SEU 抢课助手 v2.2 (流式增强修复版)</h3>

                <div style="display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; align-items: center;">
                    <label style="font-weight: bold; white-space: nowrap;">OCR API:</label>
                    <input type="text" id="ocr-endpoint-seu" value="${g_config.ocrEndpoint}"
                        style="flex-grow: 1; min-width: 200px; padding: 5px; border: 1px solid #ccc; border-radius: 4px;">
                    <button id="save-ocr-btn" style="padding: 6px 12px; background-color: #007bff; color: white; border: none; cursor: pointer; border-radius: 4px;">保存</button>
                    <button id="refresh-list-btn-seu" style="padding: 6px 12px; background-color: #2196F3; color: white; border: none; cursor: pointer; border-radius: 4px;">刷新列表</button>
                    <button id="stop-btn-seu" style="padding: 6px 12px; background-color: #f44336; color: white; border: none; cursor: pointer; border-radius: 4px;">停止全部</button>
                </div>

                <p id="global-status-seu" style="margin: 5px 0; font-weight: bold; color: #333;">状态: 待机</p>
            </div>
        `;

        // 悬浮日志流容器 (position: fixed 确保不影响页面流)
        const streamHtml = `
            <div id="seu-stream-container" style="position: fixed; top: 10px; right: 10px; width: 350px; max-height: 400px; padding: 10px; border: 1px solid #ddd; background-color: rgba(255, 255, 255, 0.95); box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 6px; z-index: 10000;">
                <h4 style="margin: 0 0 5px 0; color: #4CAF50;">实时日志流 (抢课详情)</h4>
                <div id="seu-stream-log" style="max-height: 350px; overflow-y: auto; background-color: #f0f0f0; padding: 5px; border-radius: 3px;">
                    <p style="margin: 0; font-size: 12px; color: #666;">日志流式显示区域...</p>
                </div>
            </div>
        `;

        // 策略恢复：将控制栏插入到表格之前
        const table = document.querySelector('table.zero-grid');
        if (table) {
            table.insertAdjacentHTML('beforebegin', headerHtml);

            // 将悬浮日志流容器插入到 body 顶部，确保全局可见
            document.body.insertAdjacentHTML('afterbegin', streamHtml);

            document.getElementById('refresh-list-btn-seu').addEventListener('click', () => {
                updateStatus('正在获取讲座列表...');
                logStream('手动点击刷新列表...', 'info');
                getLectureList().catch(e => {
                    updateStatus(`获取失败: ${e.message}`);
                    logStream(`列表获取失败: ${e.message}`, 'error');
                    Swal.fire('错误', e.message, 'error');
                });
            });

            document.getElementById('stop-btn-seu').addEventListener('click', handleStopClick);

            document.getElementById('save-ocr-btn').addEventListener('click', () => {
                const newOcr = document.getElementById('ocr-endpoint-seu').value.trim();
                GM_setValue(KEY_OCR, newOcr);
                g_config.ocrEndpoint = newOcr;
                Swal.fire('成功', `已保存: ${newOcr}`, 'success');
                logStream(`已保存 OCR API 地址: **${newOcr}**`, 'info');
            });
        }
    }

    window.addEventListener('load', () => {
        // 延迟加载确保页面元素到位
        setTimeout(() => {
            injectControlHeader();
            // 自动触发一次列表刷新，加载按钮
            document.getElementById('refresh-list-btn-seu')?.click();
        }, 1500);
    });
    unsafeWindow.getCode = getCode;

})();