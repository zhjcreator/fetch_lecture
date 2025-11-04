// ==UserScript==
// @name          SEU研究生讲座抢课脚本 v2.6 (原生Cookie版) - 最终防反爬优化
// @namespace     http://tampermonkey.net/
// @version       2.6
// @description   使用原生Cookie和Session发送请求，增强了HTTP Header、随机延迟和预约前置校验，以应对反爬。
// @author        Fixed Version
// @match         https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*
// @grant         GM_setValue
// @grant         GM_getValue
// @require       https://cdn.jsdelivr.net/npm/sweetalert2@11
// @run-at        document-idle
// ==/UserScript==

(function() {
    'use strict';

    // *** 版本更新到 2.6 并修改描述 ***
    console.log("✅ SEU Grab Script v2.6 (Anti-Bot Optimized) is Running!");

    const BASE_URL = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/";
    const KEY_OCR = 'seu_grab_ocr_endpoint';
    const OCR_RETRY_MAX = 3;
    const OCR_TIMEOUT = 10000;
    
    // 定义随机延迟范围（1000ms 到 2000ms）
    const MIN_RANDOM_DELAY = 1000; 
    const MAX_RANDOM_DELAY = 2000;

    let g_config = {
        ocrEndpoint: GM_getValue(KEY_OCR, 'http://127.0.0.1:5000/predict_base64'),
        isGrabbing: false,
        keepAliveEnabled: true,
        keepAliveInterval: 60000
    };
    let g_activeGrabWID = null;
    let g_streamLogCounter = 0;
    let g_keepAliveTimer = null;

    // ===== 状态与日志函数 (保持不变) =====

    function updateStatus(msg) {
        const statusEl = document.getElementById('global-status-seu');
        if (statusEl) statusEl.textContent = `状态: ${msg}`;
        console.log(`[STATUS] ${msg}`);
    }

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

        if (streamEl.children.length >= 50) {
            streamEl.removeChild(streamEl.children[0]);
        }

        streamEl.appendChild(logEntry);
        streamEl.scrollTop = streamEl.scrollHeight;
        console.log(`[${level.toUpperCase()}] ${msg}`);
    }

    /**
     * 【V2.6 最终优化】使用原生 fetch 和浏览器 Cookie - 自动处理会话，并添加关键 Headers 模仿 AJAX
     * Headers 已调整至与 HAR 文件中 yySave.do 请求完全一致
     */
    async function fetchRequest(url, options = {}, timeout = 10000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        // 【修正/优化】添加默认 Headers，模仿浏览器 AJAX 请求
        const defaultHeaders = {
            // 关键 AJAX Headers (与 HAR 文件中 yySave.do 请求一致)
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            // 注意: Content-Type 必须在 POST 请求中由 options.headers 覆盖或在这里设置，
            // 但 queryActivityList.do 和 keepAlive 请求通常不需要此 header，
            // yySave.do (最重要的请求) 会在 fetchLecture 中设置精确的 Content-Type。
            // 这里为了通用性，不设置 Content-Type，让业务函数来覆盖它。
            'X-Requested-With': 'XMLHttpRequest',

            // 来源/安全 Headers (与 HAR 文件中 yySave.do 请求一致)
            'Origin': 'https://ehall.seu.edu.cn', 
            // 【修正】Referer：指向当前页面 URL，完全模拟从列表页点击的行为
            'Referer': window.location.href, 
            
            // 浏览器标识 Headers
            'User-Agent': navigator.userAgent,
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br', // 模拟浏览器接受压缩

            // 新兴安全 Headers (与 HAR 文件中 yySave.do 请求一致，强烈建议保留)
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        };

        try {
            const fetchOptions = {
                method: options.method || 'GET',
                credentials: 'include',
                signal: controller.signal,
                // 【修正】合并默认 Headers 和传入的 Headers
                headers: {
                    ...defaultHeaders,
                    ...options.headers
                }
            };

            if (options.data) {
                fetchOptions.body = options.data;
            }

            const response = await fetch(url, fetchOptions);
            clearTimeout(timeoutId);

            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('请求超时');
            }
            throw error;
        }
    }

    // ===== 预约状态检查函数 (新增) =====

    /**
     * 【新增】预约前置检查：检测用户是否已预约或是否有预约资格
     * 对应原系统 actionAppointment 中的 appiontCheck 逻辑
     */
    async function appiontCheck(hd_wid) {
        const url = BASE_URL + "hdyy/appiontCheck.do";
        const data_json = { "HD_WID": hd_wid };
        const form_data = `paramJson=${encodeURIComponent(JSON.stringify(data_json))}`;
        logStream(`**[CHECK]** 正在进行预约前置检查: WID=${hd_wid}`);

        try {
            const response = await fetchRequest(url, {
                method: 'POST',
                // 必须使用 Content-Type
                headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                data: form_data
            }, 5000);

            const responseText = await response.text();
            
            if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
                throw new Error('会话已失效，需要重新登录');
            }

            const result = JSON.parse(responseText);
            
            if (!result.success) {
                // appiontCheck 失败通常表示：已预约、已取消、名额已满、预约时间未到等
                logStream(`前置检查失败: **${result.msg}**`, 'warn');
                return { 
                    canProceed: false, 
                    msg: result.msg 
                };
            }

            logStream('前置检查通过，可以尝试抢课...', 'success');
            return { 
                canProceed: true, 
                msg: result.msg 
            };

        } catch (error) {
            logStream(`前置检查异常中断: ${error.message}`, 'error');
            throw error;
        }
    }


    /**
     * 调用 OCR API (不变)
     */
    async function callOcrApi(base64Image, ocrEndpoint) {
        if (!ocrEndpoint) throw new Error('请配置 ddddocr HTTP API 地址');

        const b64_data = base64Image.includes(',')
        ? base64Image.split(",")[1]
        : base64Image;

        if (!b64_data) {
            throw new Error('Base64 图片数据为空');
        }

        for (let attempt = 1; attempt <= OCR_RETRY_MAX; attempt++) {
            try {
                // *** 关键修改：直接使用原生 fetch，不使用 fetchRequest，以确保不带目标网站 Cookie ***
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), OCR_TIMEOUT);

                const response = await fetch(
                    ocrEndpoint,
                    {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                            'Accept-Encoding': 'gzip, deflate, br',
                        },
                        body: JSON.stringify({ img_b64: b64_data }),
                        signal: controller.signal,
                        // 显式或隐式地不设置 'include'
                        credentials: 'omit'
                    }
                );

                clearTimeout(timeoutId);
                // *** 关键修改结束 ***

                if (response.status !== 200) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const result = await response.json();
                const ocrResult = (result.result || result.text || '').trim();

                if (!ocrResult) {
                    throw new Error('OCR 识别结果为空');
                }

                logStream(`✓ OCR 识别成功: **${ocrResult}**`, 'success');
                return ocrResult;

            } catch (error) {
                logStream(`OCR 尝试 ${attempt}/${OCR_RETRY_MAX} 失败: ${error.message}`, 'warn');

                if (attempt < OCR_RETRY_MAX) {
                    await new Promise(r => setTimeout(r, 1000 * attempt));
                } else {
                    throw new Error(`OCR 识别失败（已重试 ${OCR_RETRY_MAX} 次）`);
                }
            }
        }
    }

    /**
     * 获取验证码 (不变)
     */
    async function getCode(retryCount = 0) {
        try {
            logStream(`正在获取验证码 (第 ${retryCount + 1} 次)...`);
            const c_url = BASE_URL + `hdyy/vcode.do?_=${Date.now()}`;
            // vcode.do 也是 POST 请求，但不需要 body
            const response = await fetchRequest(c_url, {
                method: 'POST',
                // vcode.do 不需要 Content-Type: application/x-www-form-urlencoded
                headers: { 'Content-Type': 'application/json' } // 使用更通用的 JSON Type
            }, 5000);

            const c_r = await response.json();
            if (!c_r.result) throw new Error('验证码接口返回数据错误');

            const c_img_base64 = c_r.result;
            const result_code = await callOcrApi(c_img_base64, g_config.ocrEndpoint);

            return { v_code: result_code, v_img: c_img_base64 };

        } catch (error) {
            if (retryCount < 2) {
                logStream(`验证码获取失败，1秒后重试: ${error.message}`, 'warn');
                await new Promise(r => setTimeout(r, 1000));
                return getCode(retryCount + 1);
            }
            throw error;
        }
    }

    /**
     * 抢课请求 【修正】使用精确 Headers
     */
    async function fetchLecture(hd_wid, ver_code) {
        const url = BASE_URL + "hdyy/yySave.do";
        const data_json = { "HD_WID": hd_wid, "vcode": ver_code };
        const form_data = `paramJson=${encodeURIComponent(JSON.stringify(data_json))}`;
        logStream(`**[REQUEST]** 发送抢课请求: WID=${hd_wid}, VCode=${ver_code}`);

        try {
            const response = await fetchRequest(url, {
                method: 'POST',
                // 关键：Content-Type 必须保持精确，与 HAR 文件一致
                headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                data: form_data
            }, 5000);

            const responseText = await response.text();

            // 检查是否是 HTML 响应
            if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
                // 检查是否包含 Nginx 或通用错误信息
                if (responseText.includes('error occurred') || responseText.includes('nginx') || responseText.includes('Sorry')) {
                    logStream(`**❌ 服务器错误**，返回了 HTML 错误页面。将重试...`, 'critical');
                    throw new Error('服务器错误，临时无法连接'); // 抛出可重试错误
                } else {
                    // 其他 HTML 页面，视为会话失效（如重定向到登录页）
                    logStream(`**❌ 会话已失效**，返回了 HTML 页面。请刷新页面重新登录。`, 'critical');
                    throw new Error('会话已失效，需要重新登录'); // 抛出致命错误
                }
            }

            const result = JSON.parse(responseText);
            return {
                code: result.code,
                msg: result.msg,
                success: result.success || false
            };
        } catch (error) {
            // 将 fetchRequest 抛出的“请求超时”也视为可重试的服务器错误
            if (error.message.includes('请求超时')) {
                throw new Error('服务器错误，请求超时');
            }
                
            if (error.message.includes('会话已失效') || error.message.includes('服务器错误')) {
                throw error;
            }
            throw new Error(`抢课请求失败: ${error.message}`);
        }
    }

    /**
     * 获取讲座列表 (不变)
     */
    async function getLectureList() {
        const url = BASE_URL + `hdyy/queryActivityList.do?_=${Date.now()}`;
        try {
            const response = await fetchRequest(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                data: 'pageIndex=1&pageSize=100'
            }, 5000);

            const responseText = await response.text();

            // 检查是否是 HTML 响应 (这里仍然视为会话失效)
            if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
                logStream(`**❌ 会话已失效**，需要重新登录。`, 'critical');
                throw new Error('会话已失效，请刷新页面重新登录');
            }

            const json_data = JSON.parse(responseText);
            if (!json_data.datas) throw new Error('讲座列表为空或格式错误');

            injectGrabButtons(json_data.datas);
            return json_data.datas;

        } catch (error) {
            if (error.message.includes('会话已失效')) {
                Swal.fire('会话失效', '您的登录状态已失效，请刷新页面重新登录', 'error');
                throw error;
            }
            logStream(`获取讲座列表失败: ${error.message}`, 'error');
            throw error;
        }
    }

    // ===== 保活函数 (不变) =====

    /**
     * 保活请求 - 定期发送请求保持会话活跃
     */
    async function keepAliveRequest() {
        if (!g_config.keepAliveEnabled || g_config.isGrabbing) {
            return;
        }

        try {
            // KeepAlive 也使用 fetchRequest，以确保携带正确的 Headers
            const url = BASE_URL + `hdyy/queryActivityList.do?_=${Date.now()}`;
            const response = await fetchRequest(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                data: 'pageIndex=1&pageSize=1'
            }, 3000);

            const responseText = await response.text();

            if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
                console.warn('⚠️ 保活检测到会话已失效');
                g_config.keepAliveEnabled = false;
                logStream(`**⚠️ 警告：保活失败，会话可能已失效**，请检查登录状态`, 'warn');
                return;
            }

            const json_data = JSON.parse(responseText);
            if (json_data.datas) {
                console.log('✓ 保活成功 -', new Date().toLocaleTimeString());
            }
        } catch (error) {
            console.error('✗ 保活请求失败:', error.message);
        }
    }

    /**
     * 启动保活定时器 (不变)
     */
    function startKeepAlive() {
        if (g_keepAliveTimer) return;

        logStream(`**启动保活** - 每 ${g_config.keepAliveInterval / 1000} 秒发送一次`, 'info');

        keepAliveRequest();

        g_keepAliveTimer = setInterval(() => {
            keepAliveRequest();
        }, g_config.keepAliveInterval);
    }

    /**
     * 停止保活定时器 (不变)
     */
    function stopKeepAlive() {
        if (g_keepAliveTimer) {
            clearInterval(g_keepAliveTimer);
            g_keepAliveTimer = null;
            logStream(`**停止保活**`, 'info');
        }
    }

    // ===== 倒计时 (不变) =====

    async function waitUntil(targetTime, name) {
        logStream(`**开始倒计时:** 【${name}】目标时间：${targetTime.toLocaleTimeString()}`);
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

    // ===== 抢课核心逻辑 (增加 appiontCheck) =====

    async function startGrab(wid, yykssj, name, buttonElement) {
        if (g_config.isGrabbing) {
            logStream(`有其他任务正在进行，本次操作被忽略。`, 'warn');
            Swal.fire('提示', '请先停止当前抢课任务', 'warning');
            return;
        }

        g_activeGrabWID = wid;
        g_config.isGrabbing = true;
        g_streamLogCounter = 0;

        const targetTime = new Date(yykssj.replace(/-/g, "/"));
        const originalText = buttonElement.textContent;
        buttonElement.style.backgroundColor = '#ff9800';
        buttonElement.textContent = '抢课中...';

        logStream(`--- **开始抢课任务：【${name}】** ---`, 'critical');
        logStream(`目标 WID: ${wid}`, 'info');

        try {
            // 【V2.6 新增】预约前置检查
            const checkResult = await appiontCheck(wid);
            if (!checkResult.canProceed) {
                 // 如果检查失败，并且是“已预约”消息，则直接退出
                if (checkResult.msg.includes('已预约')) {
                    logStream(`**抢课任务结束：** ${checkResult.msg}`, 'success');
                    Swal.fire('提示', `【${name}】${checkResult.msg}`, 'info');
                    return;
                } else if (!checkResult.msg.includes('尚未开放')) {
                    // 对于预约时间未到之外的失败，弹出警告
                    Swal.fire('抢课暂停', `预约前置检查失败：${checkResult.msg}`, 'warning');
                    return;
                }
                logStream(`前置检查结果：${checkResult.msg}，继续等待倒计时...`, 'info');
            }


            const remaining = targetTime.getTime() - Date.now();
            if (remaining > 50) {
                await waitUntil(targetTime, name);
            }
            logStream(`倒计时结束，立即开始抢课循环...`, 'critical');

            if (!g_config.isGrabbing) return;

            let attempt = 1;
            let v_code = '';
            let lastOcrTime = 0;

            while (g_config.isGrabbing) {
                try {
                    updateStatus(`【${name}】第 ${attempt} 次尝试...`);
                    logStream(`**[ATTEMPT ${attempt}]** 开始尝试抢课...`, 'info');

                    let list;
                    try {
                        // 列表请求依然保持，用于余量判断和保活
                        list = await getLectureList();
                    } catch (e) {
                        if (e.message.includes('会话已失效')) {
                            g_config.isGrabbing = false;
                            logStream(`**抢课已停止：${e.message}**`, 'critical');
                            Swal.fire('抢课停止', e.message, 'warning');
                            return;
                        }
                        throw e;
                    }

                    const lecture = list.find(l => l.WID === wid);
                    if (!lecture) throw new Error('讲座已下架或列表获取失败');

                    const total = parseInt(lecture.HDZRS);
                    const booked = parseInt(lecture.YYRS);
                    const available = total - booked;
                    logStream(`余量检查: 总 ${total} / 已 ${booked} / 剩余 **${available}**`);

                    if (available <= 0) {
                        logStream(`人数已满，暂停 2s...`, 'warn');
                        await new Promise(r => setTimeout(r, 2000));
                        attempt++;
                        continue;
                    }

                    // 【微小延迟 A】
                    await new Promise(r => setTimeout(r, Math.random() * 50 + 50));

                    // 验证码逻辑
                    if (!v_code || attempt % 3 === 0) {
                        if (Date.now() - lastOcrTime < 1500) {
                            await new Promise(r => setTimeout(r, 1500 - (Date.now() - lastOcrTime)));
                        }
                        const codeResult = await getCode();
                        v_code = codeResult.v_code;
                        lastOcrTime = Date.now();
                        logStream(`获取新验证码: **${v_code}**`);
                    }

                    // 【微小延迟 B】
                    await new Promise(r => setTimeout(r, Math.random() * 50 + 50));

                    // 执行抢课请求
                    const result = await fetchLecture(wid, v_code);

                    if (result.success) {
                        g_config.isGrabbing = false;
                        logStream(`**🎉🎉🎉 抢课成功!** 消息: ${result.msg}`, 'critical');
                        Swal.fire('成功！', `【${name}】预约成功！`, 'success');
                        updateStatus(`【${name}】抢课成功！`);
                        break;
                    }

                    if (result.msg.includes('验证码')) {
                        v_code = '';
                        logStream(`抢课失败: **验证码错误**`, 'warn');
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
                    // 【固定延迟 C】 抢课失败后的基础间隔
                    await new Promise(r => setTimeout(r, 300));

                } catch (e) {
                    
                    // 致命错误：会话失效，直接停止任务
                    if (e.message.includes('会话已失效')) {
                        g_config.isGrabbing = false;
                        logStream(`**抢课已停止：${e.message}**`, 'critical');
                        Swal.fire('抢课停止', e.message, 'warning');
                        return;
                    }
                    
                    logStream(`**[ATTEMPT ${attempt}]** 异常: ${e.message}`, 'error');
                    
                    let delay = 1000; // 默认延迟 1s
                    
                    // 可重试错误：服务器故障、超时、HTML 错误页面
                    if (e.message.includes('服务器错误') || e.message.includes('请求超时')) {
                        // 随机延迟在 1000ms (1秒) 到 2000ms (2秒) 之间
                        delay = Math.random() * (MAX_RANDOM_DELAY - MIN_RANDOM_DELAY) + MIN_RANDOM_DELAY; 
                        logStream(`检测到服务器错误/超时，使用随机延迟 **${delay.toFixed(0)}ms** 重试...`, 'critical');
                    }
                    
                    attempt++;
                    await new Promise(r => setTimeout(r, delay));
                }
            }

        } catch (e) {
            logStream(`**[CRITICAL]** 任务中断: ${e.message}`, 'critical');
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

    // ===== UI 交互 (保持不变) =====

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

    function injectGrabButtons(lectureList) {
        const tbody = document.querySelector('tbody[id^="tbody_"]');
        if (!tbody) return;

        const rows = tbody.querySelectorAll('tr');
        rows.forEach((row, index) => {
            const lecture = lectureList[index];
            if (!lecture || row.querySelector('.grab-btn-seu')) return;

            const actionCell = row.querySelector('td:first-child');
            if (!actionCell) return;

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

    function injectControlHeader() {
        if (document.getElementById('seu-control-header')) return;

        g_config.ocrEndpoint = GM_getValue(KEY_OCR, g_config.ocrEndpoint);

        const headerHtml = `
            <div id="seu-control-header" style="margin-bottom: 15px; padding: 10px; border: 2px solid #4CAF50; border-radius: 4px; background-color: #f9f9f9;">
                <h3 style="margin-top: 0; color: #4CAF50;">🎓 SEU 抢课助手 v2.6 (原生Cookie版) - 最终防反爬优化</h3>

                <div style="display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; align-items: center;">
                    <label style="font-weight: bold; white-space: nowrap;">OCR API:</label>
                    <input type="text" id="ocr-endpoint-seu" value="${g_config.ocrEndpoint}"
                        style="flex-grow: 1; min-width: 200px; padding: 5px; border: 1px solid #ccc; border-radius: 4px;">
                    <button id="save-ocr-btn" style="padding: 6px 12px; background-color: #007bff; color: white; border: none; cursor: pointer; border-radius: 4px;">保存</button>
                    <button id="refresh-list-btn-seu" style="padding: 6px 12px; background-color: #2196F3; color: white; border: none; cursor: pointer; border-radius: 4px;">刷新列表</button>
                    <button id="stop-btn-seu" style="padding: 6px 12px; background-color: #f44336; color: white; border: none; cursor: pointer; border-radius: 4px;">停止全部</button>
                </div>

                <p id="global-status-seu" style="margin: 5px 0; font-weight: bold; color: #333;">状态: 待机</p>

                <div style="margin-top: 10px; padding: 8px; background-color: #e8f5e9; border-radius: 4px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="keep-alive-switch" checked style="width: 16px; height: 16px; cursor: pointer;">
                        <span style="font-weight: bold; color: #2e7d32;">启用保活 (每60秒)</span>
                        <span style="font-size: 10px; color: #c62828;">(*请注意频繁操作可能触发反爬)</span>
                    </label>
                    <p id="keep-alive-status" style="margin: 5px 0 0 0; font-size: 12px; color: #558b2f;">保活已启用</p>
                </div>
            </div>
        `;

        const streamHtml = `
            <div id="seu-stream-container" style="position: fixed; top: 10px; right: 10px; width: 350px; max-height: 400px; padding: 10px; border: 1px solid #ddd; background-color: rgba(255, 255, 255, 0.95); box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 6px; z-index: 10000;">
                <h4 style="margin: 0 0 5px 0; color: #4CAF50;">实时日志流</h4>
                <div id="seu-stream-log" style="max-height: 350px; overflow-y: auto; background-color: #f0f0f0; padding: 5px; border-radius: 3px;">
                    <p style="margin: 0; font-size: 12px; color: #666;">日志流式显示区域...</p>
                </div>
            </div>
        `;

        const table = document.querySelector('table.zero-grid');
        if (table) {
            table.insertAdjacentHTML('beforebegin', headerHtml);
            document.body.insertAdjacentHTML('afterbegin', streamHtml);

            document.getElementById('refresh-list-btn-seu').addEventListener('click', () => {
                updateStatus('正在获取讲座列表...');
                logStream('手动点击刷新列表...', 'info');
                getLectureList().catch(e => {
                    updateStatus(`获取失败: ${e.message}`);
                    logStream(`列表获取失败: ${e.message}`, 'error');
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

            document.getElementById('keep-alive-switch').addEventListener('change', (e) => {
                g_config.keepAliveEnabled = e.target.checked;
                const statusEl = document.getElementById('keep-alive-status');

                if (e.target.checked) {
                    startKeepAlive();
                    statusEl.textContent = '保活已启用';
                    statusEl.style.color = '#558b2f';
                } else {
                    stopKeepAlive();
                    statusEl.textContent = '保活已禁用';
                    statusEl.style.color = '#c62828';
                }
            });

            startKeepAlive();
        }
    }

    window.addEventListener('load', () => {
        setTimeout(() => {
            injectControlHeader();
            document.getElementById('refresh-list-btn-seu')?.click();
        }, 1500);
    });

    window.addEventListener('beforeunload', () => {
        stopKeepAlive();
    });

    // 暴露函数到全局
    unsafeWindow.seu_getCode = getCode;
    unsafeWindow.seu_startGrab = startGrab;
    unsafeWindow.seu_getLectureList = getLectureList;
    unsafeWindow.seu_config = g_config;
    unsafeWindow.seu_fetchLecture=fetchLecture;
    unsafeWindow.seu_appiontCheck=appiontCheck;

})();