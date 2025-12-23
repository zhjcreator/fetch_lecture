// ==UserScript==
// @name         SEU 素质讲座抢课脚本 (v1.7.0 - 暴力重试版)
// @namespace    http://tampermonkey.net/
// @version      1.7.0
// @description  增加抢课前权限检查和任务取消功能，可视化配置API和延迟，支持验证码识别后持续自动点击确定直到成功。
// @author       Your Senior Software Engineer
// @match        https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/*
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      ehall.seu.edu.cn
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // --- 全局配置 ---
    const DEFAULT_CAPTCHA_API_ENDPOINT = 'http://127.0.0.1:5000/predict_base64';
    const DEFAULT_CAPTCHA_CLICK_DELAY_MS = 100; // 识别成功后点击"确定"的初始延迟
    const DEFAULT_COUNTDOWN_END_DELAY_MS = 0;   // 倒计时结束后点击"预约"按钮的延迟
    const DEFAULT_REPEAT_CLICK_MS = 200;        // 验证码确认按钮的重复点击间隔
    const CHECK_PERMISSION_ENDPOINT = 'https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/appiontCheck.do';
    const CHECK_INTERVAL_MS = 200;
    const COUNTDOWN_INTERVAL_MS = 30;
    const CLICK_OFFSET_MS = 50;

    // --- 状态变量 ---
    let selectedCourses = [];
    let countdownTimer = null;
    let forceButtonInterval = null;
    let isProcessingCaptcha = false;
    let clickTimeout = null; // 用于倒计时结束后的延迟点击
    let captchaLoopId = null; // 用于验证码界面的循环点击

    // --- 核心功能函数 ---

    /**
     * 获取页面上的服务器时间
     * @returns {number|null} 当前服务器时间的毫秒数
     */
    function getServerTime() {
        if (typeof unsafeWindow.serverTime !== 'undefined') {
            return unsafeWindow.serverTime;
        }
        // 降低日志频率，避免刷屏
        // logToPanel("警告: 无法获取准确的服务器时间，将使用本地时间，可能存在误差。", "warning");
        return Date.now();
    }

    /**
     * 强制将所有非预约状态的按钮修改为可点击的"预约"按钮
     */
    function forceAppointmentButtons() {
        if (!window.location.hash.includes('hdyy')) return;
        const disabledButtons = document.querySelectorAll('a[data-wid]:not([data-action="appointment"])');
        disabledButtons.forEach(button => {
            const buttonText = button.textContent.trim();
            if (['活动取消', '未开放', '已結束', '人数已满', '已预约'].includes(buttonText)) {
                button.style.pointerEvents = '';
                button.style.color = '#007bff';
                button.setAttribute('data-action', 'appointment');
                button.textContent = '预约';
            }
        });
    }

    /**
     * 解析课程列表并返回课程信息数组
     * @returns {Array} 课程对象数组
     */
    function parseCourses() {
        const courseRows = document.querySelectorAll('tbody[id*="tbody_"] tr');
        if (courseRows.length === 0) return [];
        const courses = [];
        courseRows.forEach(row => {
            try {
                const nameSpan = row.querySelector('td:nth-child(4) span');
                const timeSpan = row.querySelector('td:nth-child(9) span');
                const actionButton = row.querySelector('a[data-wid]');
                if (nameSpan && timeSpan && actionButton) {
                    courses.push({
                        name: nameSpan.title,
                        wid: actionButton.getAttribute('data-wid'),
                        startTime: timeSpan.title,
                        startTimeMs: new Date(timeSpan.title.replace(/-/g, '/')).getTime()
                    });
                }
            } catch (e) { console.error('[抢课脚本] 解析课程行出错:', e); }
        });
        return courses;
    }

    /**
     * 检查用户是否有权限预约指定课程
     * @param {object} course - 包含wid的课程对象
     * @returns {Promise<object>} - 返回接口的JSON结果
     */
    function checkAppointmentPermission(course) {
        return new Promise((resolve, reject) => {
            logToPanel(`正在为 [${course.name}] 进行权限检查...`, 'info');
            GM_xmlhttpRequest({
                method: "POST",
                url: CHECK_PERMISSION_ENDPOINT,
                headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
                data: `wid=${course.wid}`,
                timeout: 5000,
                onload: function(response) {
                    try {
                        const data = JSON.parse(response.responseText);
                        resolve(data);
                    } catch (e) {
                        reject(new Error("解析权限检查响应失败"));
                    }
                },
                onerror: function(response) {
                    reject(new Error("权限检查请求失败"));
                },
                ontimeout: function() {
                    reject(new Error("权限检查请求超时"));
                }
            });
        });
    }

    // --- 验证码处理核心 ---

    /**
     * 处理验证码弹窗
     * @param {HTMLElement} modalNode - 弹窗的根元素
     */
    function handleCaptcha(modalNode) {
        if (isProcessingCaptcha) return;
        isProcessingCaptcha = true;

        logToPanel("检测到验证码弹窗，开始自动处理...", 'info');

        // 从UI读取动态配置
        const currentApiEndpoint = document.getElementById('captcha-api-input').value || DEFAULT_CAPTCHA_API_ENDPOINT;
        const initialClickDelay = Math.max(0, parseInt(document.getElementById('captcha-delay-input').value, 10)) || DEFAULT_CAPTCHA_CLICK_DELAY_MS;
        const repeatClickInterval = Math.max(50, parseInt(document.getElementById('repeat-click-input').value, 10)) || DEFAULT_REPEAT_CLICK_MS;

        const vcodeImg = modalNode.querySelector('#vcodeImg');
        const vcodeInput = modalNode.querySelector('#vcodeInput');
        const confirmButton = modalNode.querySelector('button[zeromodal-btn-ok]');

        if (!vcodeImg || !vcodeInput || !confirmButton) {
            logToPanel("错误：未能找到验证码弹窗内的所有关键元素。", 'error');
            isProcessingCaptcha = false;
            return;
        }

        const base64Data = vcodeImg.src.split(',')[1];
        // logToPanel(`正在发送验证码到 [${currentApiEndpoint}] 进行识别...`);

        GM_xmlhttpRequest({
            method: "POST",
            url: currentApiEndpoint,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({ img_b64: base64Data }),
            timeout: 5000,
            onload: function(response) {
                try {
                    const data = JSON.parse(response.responseText);
                    if (data.result) {
                        const code = data.result;
                        logToPanel(`识别成功: <strong>${code}</strong>`, 'success');
                        vcodeInput.value = code;
                        logToPanel(`将在 ${initialClickDelay}ms 后开始点击，若弹窗未消失则每 ${repeatClickInterval}ms 重试...`, 'info');

                        // 核心修改逻辑：持续点击直到弹窗消失
                        setTimeout(() => {
                            let clickCount = 0;
                            // 先点击一次
                            confirmButton.click();
                            clickCount++;
                            
                            // 启动循环检测点击
                            if (captchaLoopId) clearInterval(captchaLoopId);
                            
                            captchaLoopId = setInterval(() => {
                                // 检查弹窗是否存在于DOM中且显示状态正常
                                if (document.body.contains(modalNode) && modalNode.style.display !== 'none') {
                                    confirmButton.click();
                                    clickCount++;
                                    // 每点击10次在控制台输出一次，避免刷屏
                                    if (clickCount % 10 === 0) {
                                        console.log(`[抢课脚本] 验证码弹窗未消失，已重试点击 ${clickCount} 次...`);
                                    }
                                } else {
                                    // 弹窗消失，说明成功提交或被手动关闭
                                    clearInterval(captchaLoopId);
                                    captchaLoopId = null;
                                    isProcessingCaptcha = false; // 释放锁，允许处理下一个可能的弹窗
                                    logToPanel(`验证码弹窗已消失 (共点击 ${clickCount} 次)，操作结束。`, 'success');
                                }
                            }, repeatClickInterval);

                        }, initialClickDelay);

                    } else { throw new Error(data.error || "API未返回result字段"); }
                } catch (e) {
                    logToPanel(`错误：处理识别结果失败: ${e.message}`, 'error');
                    isProcessingCaptcha = false;
                }
            },
            onerror: function(response) {
                logToPanel("错误：连接验证码识别服务失败！", 'error');
                isProcessingCaptcha = false;
            },
            ontimeout: function() {
                logToPanel("错误：验证码识别服务请求超时。", 'error');
                isProcessingCaptcha = false;
            }
        });
    }

    // --- UI 相关函数 ---

    function createControlPanel() {
        const panelHTML = `
            <div id="course-grabber-panel">
                <div class="panel-header">
                    <span>SEU抢课助手 v1.7.0 (暴力重试版)</span>
                    <div class="panel-buttons">
                        <button id="panel-toggle">-</button>
                        <button id="panel-close">×</button>
                    </div>
                </div>
                <div class="panel-content">
                    <div id="course-list-container">加载课程列表中...</div>

                    <div class="panel-settings">
                        <div>
                            <label for="captcha-api-input">识别API接口:</label>
                            <input type="text" id="captcha-api-input" value="${DEFAULT_CAPTCHA_API_ENDPOINT}">
                        </div>
                        <div>
                            <label for="captcha-delay-input" title="识别出验证码后多久进行第一次点击">首次点击延迟(ms):</label>
                            <input type="number" id="captcha-delay-input" value="${DEFAULT_CAPTCHA_CLICK_DELAY_MS}" min="0" step="50">
                        </div>
                        <div>
                            <label for="repeat-click-input" title="如果弹窗没消失，多久点一次确定">失败重试间隔(ms):</label>
                            <input type="number" id="repeat-click-input" value="${DEFAULT_REPEAT_CLICK_MS}" min="50" step="50" style="color:red;font-weight:bold;">
                        </div>
                        <div>
                            <label for="countdown-end-delay-input">倒计时结束延迟(ms):</label>
                            <input type="number" id="countdown-end-delay-input" value="${DEFAULT_COUNTDOWN_END_DELAY_MS}" min="0" step="50">
                        </div>
                    </div>

                    <div class="panel-actions">
                        <button id="refresh-courses-btn">刷新列表</button>
                        <button id="start-grabbing-btn">开始预约</button>
                    </div>
                    <div id="status-log">
                        <p><strong>状态日志:</strong></p>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', panelHTML);
        addPanelStyles();
        addPanelEvents();
    }

    function updateCourseList() {
        const container = document.getElementById('course-list-container');
        const courses = parseCourses();
        if (courses.length === 0) {
            container.innerHTML = '<p>未检测到课程或页面结构已更改。</p>';
            return;
        }
        let listHTML = '<ul>';
        courses.forEach(course => {
            listHTML += `
                <li>
                    <input type="checkbox" class="course-checkbox" data-wid="${course.wid}" data-starttime="${course.startTime}" data-starttimems="${course.startTimeMs}" data-name="${course.name}">
                    <label title="${course.name}">[${course.startTime}] ${course.name}</label>
                </li>`;
        });
        listHTML += '</ul>';
        container.innerHTML = listHTML;
        logToPanel("课程列表已刷新。");
    }

    function logToPanel(message, type = 'info') {
        const logContainer = document.getElementById('status-log');
        if (!logContainer) return;
        const p = document.createElement('p');
        p.className = `log-${type}`;
        p.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;
        logContainer.appendChild(p);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function addPanelEvents() {
        const panel = document.getElementById('course-grabber-panel');
        const header = panel.querySelector('.panel-header');
        const startBtn = document.getElementById('start-grabbing-btn');
        let isDragging = false, offsetX, offsetY;

        header.onmousedown = (e) => {
            if (e.target.tagName === 'BUTTON') return;
            isDragging = true;
            offsetX = e.clientX - panel.offsetLeft;
            offsetY = e.clientY - panel.offsetTop;
            panel.style.cursor = 'move';
        };
        document.onmousemove = (e) => {
            if (isDragging) {
                panel.style.left = `${e.clientX - offsetX}px`;
                panel.style.top = `${e.clientY - offsetY}px`;
            }
        };
        document.onmouseup = () => {
            isDragging = false;
            panel.style.cursor = 'default';
        };

        document.getElementById('panel-close').onclick = () => panel.style.display = 'none';
        document.getElementById('panel-toggle').onclick = () => {
            const content = panel.querySelector('.panel-content');
            const button = document.getElementById('panel-toggle');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                button.textContent = '-';
            } else {
                content.style.display = 'none';
                button.textContent = '+';
            }
        };
        document.getElementById('refresh-courses-btn').onclick = () => {
            forceAppointmentButtons();
            updateCourseList();
        };

        startBtn.onclick = () => {
            if (countdownTimer) {
                // 如果正在倒计时，则为取消操作
                cancelGrabbingProcess();
            } else {
                // 否则为开始操作
                startGrabbingProcess();
            }
        };
    }

    // --- 核心流程函数 ---

    /**
     * 用户点击"开始预约"后触发的完整流程
     */
    async function startGrabbingProcess() {
        const startBtn = document.getElementById('start-grabbing-btn');
        startBtn.disabled = true; // 防止重复点击
        startBtn.textContent = '检查权限...';

        const checkedBoxes = document.querySelectorAll('.course-checkbox:checked');
        if (checkedBoxes.length === 0) {
            logToPanel("请至少选择一门要预约的课程。", "warning");
            resetStartButton();
            return;
        }

        let initialSelection = [];
        checkedBoxes.forEach(cb => {
            initialSelection.push({
                name: cb.dataset.name,
                wid: cb.dataset.wid,
                startTime: cb.dataset.starttime,
                startTimeMs: parseInt(cb.dataset.starttimems, 10),
            });
        });

        // 权限检查
        const permittedCourses = [];
        for (const course of initialSelection) {
            try {
                const result = await checkAppointmentPermission(course);
                if (result.success) {
                    logToPanel(`[${course.name}] 权限检查通过。`, 'success');
                    permittedCourses.push(course);
                } else {
                    logToPanel(`[${course.name}] 权限检查失败: ${result.msg}`, 'warning');
                }
            } catch (error) {
                logToPanel(`[${course.name}] 权限检查请求出错: ${error.message}`, 'error');
            }
        }

        if (permittedCourses.length === 0) {
            logToPanel("所有已选课程均无预约权限，任务终止。", "error");
            resetStartButton();
            return;
        }

        selectedCourses = permittedCourses;
        selectedCourses.sort((a, b) => a.startTimeMs - b.startTimeMs);

        const targetTime = selectedCourses[0].startTimeMs;
        const targetTimeStr = selectedCourses[0].startTime;

        logToPanel(`权限检查完成！${selectedCourses.length} 门课程可预约。`, 'success');
        logToPanel(`目标时间: <strong>${targetTimeStr}</strong>`);
        selectedCourses.forEach(c => logToPanel(`- ${c.name}`));

        startBtn.disabled = false; // 使能取消按钮
        startBtn.style.backgroundColor = '#dc3545'; // 变为红色

        countdownTimer = setInterval(() => {
            const currentTime = getServerTime();
            const timeLeft = targetTime - currentTime;
            if (timeLeft > 0) {
                startBtn.textContent = `取消 (倒计时: ${(timeLeft / 1000).toFixed(2)}s)`;
            } else {
                clearInterval(countdownTimer);
                countdownTimer = null;
                logToPanel("时间到！等待延迟后开始点击...", "success");
                
                // 获取倒计时结束后的延迟时间
                const countdownEndDelay = Math.max(0, parseInt(document.getElementById('countdown-end-delay-input').value, 10)) || DEFAULT_COUNTDOWN_END_DELAY_MS;
                
                if (countdownEndDelay > 0) {
                    logToPanel(`将在 ${countdownEndDelay}ms 后开始模拟点击...`, "info");
                    startBtn.textContent = `取消 (${countdownEndDelay}ms后点击)`;
                    
                    // 设置倒计时结束后的延迟点击
                    clickTimeout = setTimeout(() => {
                        triggerClicks();
                        resetStartButton();
                    }, countdownEndDelay);
                } else {
                    // 如果没有延迟，立即触发点击
                    triggerClicks();
                    resetStartButton();
                }
            }
        }, COUNTDOWN_INTERVAL_MS);
    }

    /**
     * 取消当前的抢课任务
     */
    function cancelGrabbingProcess() {
        if (countdownTimer) {
            clearInterval(countdownTimer);
            countdownTimer = null;
        }
        if (clickTimeout) {
            clearTimeout(clickTimeout);
            clickTimeout = null;
        }
        if (captchaLoopId) {
            clearInterval(captchaLoopId);
            captchaLoopId = null;
        }
        logToPanel("任务已手动取消。", "warning");
        resetStartButton();
    }

    /**
     * 重置"开始/取消"按钮到初始状态
     */
    function resetStartButton() {
        const startBtn = document.getElementById('start-grabbing-btn');
        startBtn.textContent = '开始预约';
        startBtn.style.backgroundColor = '#28a745'; // 恢复绿色
        startBtn.disabled = false;
    }

    /**
     * 触发点击事件
     */
    function triggerClicks() {
        selectedCourses.forEach((course, index) => {
            setTimeout(() => {
                const buttonToClick = document.querySelector(`a[data-wid="${course.wid}"][data-action="appointment"]`);
                if (buttonToClick) {
                    buttonToClick.click();
                    logToPanel(`已为 [${course.name}] 触发点击！等待验证码弹窗...`, 'success');
                } else {
                    logToPanel(`错误: 未能找到课程 [${course.name}] 的"预约"按钮。`, 'error');
                }
            }, index * CLICK_OFFSET_MS); // 错开点击，避免浏览器卡死
        });
    }

    // --- 样式与初始化 ---

    function addPanelStyles() {
        GM_addStyle(`
            #course-grabber-panel {
                position: fixed; top: 150px; right: 20px; width: 450px; background-color: #f9f9f9;
                border: 1px solid #ccc; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                z-index: 9999; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 14px; color: #333;
            }
            .panel-header {
                padding: 10px; background-color: #eee; border-bottom: 1px solid #ccc; cursor: move;
                display: flex; justify-content: space-between; align-items: center;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            }
            .panel-header span { font-weight: bold; }
            .panel-buttons button {
                margin-left: 5px; cursor: pointer; border: 1px solid #ccc; background: #fff;
                width: 20px; height: 20px; line-height: 18px; text-align: center; border-radius: 4px;
            }
            .panel-content { padding: 10px; max-height: 60vh; display: flex; flex-direction: column; }
            #course-list-container {
                max-height: 250px; overflow-y: auto; border: 1px solid #ddd; padding: 8px;
                background: #fff; margin-bottom: 10px;
            }
            #course-list-container ul { list-style: none; padding: 0; margin: 0; }
            #course-list-container li {
                display: flex; align-items: center; padding: 4px 0; border-bottom: 1px solid #eee;
            }
            #course-list-container li:last-child { border-bottom: none; }
            #course-list-container input[type="checkbox"] { margin-right: 8px; }
            #course-list-container label {
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;
            }

            /* 配置样式 */
            .panel-settings {
                padding: 8px;
                background: #fdfdfd;
                border: 1px solid #ddd;
                margin-bottom: 10px;
                border-radius: 4px;
            }
            .panel-settings div {
                display: flex;
                align-items: center;
                margin-bottom: 5px;
            }
            .panel-settings div:last-child { margin-bottom: 0; }
            .panel-settings label {
                margin-right: 5px;
                font-size: 13px;
                white-space: nowrap;
                min-width: 130px; /* 统一标签宽度 */
            }
            .panel-settings input {
                flex-grow: 1; /* 让输入框占满剩余空间 */
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 13px;
            }
            .panel-settings input[type="number"] {
                flex-grow: 0;
                width: 80px; /* 固定数字输入框宽度 */
            }

            .panel-actions { display: flex; justify-content: space-around; margin-bottom: 10px; }
            .panel-actions button {
                padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;
                color: white; font-size: 14px; transition: background-color 0.2s;
            }
            .panel-actions button:disabled { background-color: #6c757d; cursor: not-allowed; }
            #refresh-courses-btn { background-color: #007bff; }
            #refresh-courses-btn:hover { background-color: #0056b3; }
            #start-grabbing-btn { background-color: #28a745; }
            #start-grabbing-btn:hover { background-color: #1e7e34; }
            #status-log {
                height: 120px; overflow-y: auto; background-color: #fff; border: 1px solid #ddd;
                padding: 8px; font-size: 12px; line-height: 1.5;
            }
            #status-log p { margin: 0 0 4px; }
            .log-info { color: #333; }
            .log-success { color: #28a745; font-weight: bold; }
            .log-warning { color: #ffc107; }
            .log-error { color: #dc3545; font-weight: bold; }
        `);
    }

    // --- 启动脚本 ---

    // 监听DOM变化的观察者，用于捕获验证码弹窗
    const captchaObserver = new MutationObserver((mutationsList) => {
        for(const mutation of mutationsList) {
            if (mutation.type === 'childList') {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === 1 && node.matches('div[zero-unique-container]')) {
                        handleCaptcha(node);
                        return;
                    }
                }
            }
        }
    });

    // 页面加载和路由变化的逻辑
    function initOnPage() {
        if (window.location.hash.includes('hdyy')) {
            setTimeout(() => {
                // 确保页面关键元素加载完成且脚本UI未创建
                if (document.querySelector('tbody[id*="tbody_"]') && !document.getElementById('course-grabber-panel')) {
                    createControlPanel();
                    forceAppointmentButtons();
                    updateCourseList();
                    if (forceButtonInterval) clearInterval(forceButtonInterval);
                    forceButtonInterval = setInterval(forceAppointmentButtons, CHECK_INTERVAL_MS);
                }
            }, 1000);
        }
    }

    // 启动观察者
    captchaObserver.observe(document.body, { childList: true });
    // 监听URL hash变化
    window.addEventListener('hashchange', initOnPage);
    // 首次加载时执行
    initOnPage();

})();