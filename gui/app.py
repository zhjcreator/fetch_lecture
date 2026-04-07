"""
东南大学研究生素质讲座抢课工具 - PyQt6 GUI
"""
import sys
import os
import json
import time
import random
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QTextEdit, QSplitter, QGroupBox, QComboBox, QCheckBox,
    QHeaderView, QSizePolicy, QMenu, QSystemTrayIcon, QMessageBox,
    QSpinBox, QDoubleSpinBox, QFrame, QDialog,
    QStyle, QStyleOptionViewItem, QStyledItemDelegate, QScrollArea
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize, QRect, QRectF
)
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QIcon, QAction, QCursor, QTextDocument, QTextOption
)

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend import FetchLectureBackend

# ========== 样式表 ==========
STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget {
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    font-size: 14px;
    color: #cdd6f4;
}
QLabel {
    color: #cdd6f4;
    background: transparent;
}
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #cdd6f4;
    font-size: 14px;
}
QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QLineEdit::placeholder {
    color: #6c7086;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 14px;
}
QPushButton:hover {
    background-color: #b4d0fb;
}
QPushButton:pressed {
    background-color: #74c7ec;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#dangerBtn:hover {
    background-color: #f5a0b8;
}
QPushButton#successBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#successBtn:hover {
    background-color: #b8ebb5;
}
QPushButton#stopBtn {
    background-color: #fab387;
    color: #1e1e2e;
}
QPushButton#stopBtn:hover {
    background-color: #fbc4a2;
}
QTableWidget {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    gridline-color: #45475a;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 6px;
}
QTableWidget::item:selected {
    background-color: #45475a;
}
QHeaderView::section {
    background-color: #1e1e2e;
    color: #89b4fa;
    font-weight: bold;
    border: none;
    border-bottom: 2px solid #45475a;
    padding: 8px 6px;
    font-size: 13px;
}
QTextEdit {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    color: #a6adc8;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: #1e1e2e;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89b4fa;
}
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #cdd6f4;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
    color: #cdd6f4;
}
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
}
QCheckBox {
    color: #cdd6f4;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #45475a;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QSplitter::handle {
    background-color: #45475a;
    width: 2px;
}
QStatusBar {
    background-color: #181825;
    color: #6c7086;
    border-top: 1px solid #313244;
}
"""


class WrapTextDelegate(QStyledItemDelegate):
    """QTableWidget 单元格自动换行委托"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.features |= QStyleOptionViewItem.ViewItemFeature.WrapText

    def sizeHint(self, option, index):
        self.initStyleOption(option, index)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setPlainText(text)
        # 估算可用宽度
        w = option.rect.width() - 12 if option.rect.width() > 50 else 300
        doc.setTextWidth(w)
        return QSize(int(doc.idealWidth()) + 12, max(int(doc.size().height()) + 8, 32))


class LectureDetailDialog(QDialog):
    """讲座详情弹窗"""
    # 字段中文映射（已知字段，尽量覆盖所有可能的拼音缩写）
    FIELD_LABELS = {
        "WID": "讲座ID", "HD_WID": "活动ID",
        "JZMC": "讲座名称", "JZSJ": "活动时间",
        "YYKSSJ": "预约开始时间", "YYJSSJ": "预约结束时间",
        "YYSJ": "预约时间", "YYM": "预约序号",
        "HDZRS": "活动总人数", "YYRS": "已预约人数",
        "SFDK": "是否打卡", "DKSJ": "打卡时间",
        "HDYYR": "活动预约人", "HDDS": "活动地点", "HDLX": "活动类型",
        "HDMS": "活动描述", "HDNR": "活动内容",
        "KSRQ": "开始日期", "JSRQ": "结束日期",
        "KSSJ": "开始时间", "JSSJ": "结束时间",
        "FBR": "发布人", "FBSJ": "发布时间", "FBZT": "发布状态",
        "ZT": "状态", "BZ": "备注", "LX": "类型",
        "DQZT": "当前状态", "YYZT": "预约状态",
        "XXMC": "学校名称",
        "YHXM": "用户姓名", "XH": "学号",
        "XY": "学院", "ZY": "专业", "NJ": "年级", "BJ": "班级",
        "JZDD": "讲座地点", "JZJB": "讲座级别", "JZJS": "讲座介绍",
        "JZXL": "讲座系列", "JZXL_DISPLAY": "讲座系列",
        "ZBF": "主办方", "ZJR": "主讲人", "ZJRJS": "主讲人介绍",
        "HDJSSJ": "活动结束时间", "KSQDSJ": "签到开始时间", "JSQDSJ": "签到结束时间",
        "SFWY": "是否已完成", "SFXSPJ": "是否显示评价",
        "SFXSYQFK": "是否显示已读反馈", "SFYXPJ": "是否已评价",
        "SFYXQXYY": "是否允许取消预约", "SFYXYQFK": "是否已提交反馈",
        "SZXQ": "所在校区", "XTDQSJ": "系统对齐时间",
        "YYIP": "预约IP", "RN": "序号", "JZHB": "讲座编号（内部）",
    }
    # 需要隐藏的内部/技术字段（不会在详情弹窗中显示）
    HIDDEN_FIELDS = {"JZHB", "JZXL"}

    # 重要字段优先排序（其余按原始顺序）
    PRIORITY_FIELDS = [
        "JZMC", "JZXL_DISPLAY", "JZDD", "JZSJ", "HDJSSJ",
        "YYKSSJ", "YYJSSJ", "YYSJ",
        "HDZRS", "YYRS",
        "SFDK", "DKSJ", "SFWY",
        "ZBF", "ZJR", "JZJB",
    ]

    def __init__(self, lecture_data, parent=None):
        super().__init__(parent)
        self._data = lecture_data
        self.setWindowTitle("讲座详情")
        self.setMinimumSize(420, 350)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; font-size: 14px; }
            QTextEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px;
                color: #cdd6f4;
                font-size: 13px;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b4d0fb; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("📋 讲座详情")
        title.setFont(QFont("PingFang SC", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #89b4fa;")
        layout.addWidget(title)

        # 详情文本
        detail_text = QTextEdit()
        detail_text.setReadOnly(True)
        lines = []

        # 第一组：优先显示的重要字段
        shown = set()
        for key in self.PRIORITY_FIELDS:
            if key in self._data:
                shown.add(key)
                label = self.FIELD_LABELS.get(key, key)
                value = self._data[key]
                # 讲座介绍、主讲人介绍等长文本特殊处理
                if key in ("JZJS", "ZJRJS") and len(str(value)) > 100:
                    lines.append(f'<b style="color:#89b4fa">{label}:</b><br><span style="color:#a6adc8">{value}</span>')
                else:
                    lines.append(f"<b>{label}:</b> {value}")

        # 第二组：其余未隐藏的普通字段
        for key, value in self._data.items():
            if key in shown or key in self.HIDDEN_FIELDS:
                continue
            label = self.FIELD_LABELS.get(key, key)
            if key == "WID" and len(str(value)) > 40:
                lines.append(f"<b>{label}:</b> <span style='color:#6c7086;font-size:12px'>{str(value)[:30]}...</span>")
            elif len(str(value)) > 100:
                lines.append(f'<b style="color:#89b4fa">{label}:</b><br><span style="color:#a6adc8">{value}</span>')
            else:
                lines.append(f"<b>{label}:</b> {value}")

        detail_text.setHtml("<br><br>".join(lines))
        layout.addWidget(detail_text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("✖ 关闭")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class LoginWidget(QWidget):
    """登录页面：已记住账号列表 + 新账号登录"""
    login_success = pyqtSignal(object, str, str, str)  # emit (session, username, password, fingerprint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_dir = PROJECT_ROOT / "accounts"
        self.config_dir.mkdir(exist_ok=True)
        self.session = None
        self._current_username = ""
        self._current_password = ""
        self._current_fingerprint = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("🔐 登录")
        title.setFont(QFont("PingFang SC", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #89b4fa; margin-bottom: 8px;")
        layout.addWidget(title)

        # 已保存账号区域
        saved_group = QGroupBox("已保存的账号")
        saved_layout = QVBoxLayout(saved_group)

        self.account_combo = QComboBox()
        self.account_combo.setMinimumHeight(40)
        self._load_saved_accounts()
        saved_layout.addWidget(self.account_combo)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("🔑 使用此账号登录")
        self.btn_load.clicked.connect(self._login_saved)
        self.btn_delete = QPushButton("🗑️ 删除此账号")
        self.btn_delete.setObjectName("dangerBtn")
        self.btn_delete.clicked.connect(self._delete_account)
        btn_row.addWidget(self.btn_load)
        btn_row.addWidget(self.btn_delete)
        saved_layout.addLayout(btn_row)

        layout.addWidget(saved_group)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475a;")
        layout.addWidget(line)

        # 新账号登录区域
        new_group = QGroupBox("新账号登录")
        new_layout = QVBoxLayout(new_group)

        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("请输入学号/一卡通号")
        new_layout.addWidget(self.input_username)

        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("请输入密码")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        password_row = QHBoxLayout()
        password_row.setContentsMargins(0, 0, 0, 0)
        password_row.setSpacing(0)
        password_row.addWidget(self.input_password)
        self.btn_toggle_pwd = QPushButton("👁")
        self.btn_toggle_pwd.setFixedSize(36, 36)
        self.btn_toggle_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pwd.setToolTip("显示/隐藏密码")
        self.btn_toggle_pwd.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                border: 1px solid #45475a;
                border-left: none;
                border-radius: 0 6px 6px 0;
                color: #6c7086;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #89b4fa;
            }
        """)
        self.btn_toggle_pwd.setCheckable(True)
        self.btn_toggle_pwd.toggled.connect(self._toggle_password_visibility)
        password_row.addWidget(self.btn_toggle_pwd)
        new_layout.addLayout(password_row)

        # 调整密码框右侧圆角使其与按钮贴合
        self.input_password.setStyleSheet("""
            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-right: none;
                border-radius: 6px 0 0 6px;
                padding: 8px 12px;
                color: #cdd6f4;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #89b4fa;
            }
            QLineEdit::placeholder {
                color: #6c7086;
            }
        """)

        self.chk_save = QCheckBox("记住此账号")
        self.chk_save.setChecked(True)
        new_layout.addWidget(self.chk_save)

        self.btn_login_new = QPushButton("💾 登录并保存")
        self.btn_login_new.setObjectName("successBtn")
        self.btn_login_new.clicked.connect(self._login_new)
        new_layout.addWidget(self.btn_login_new)

        layout.addWidget(new_group)

        layout.addStretch()

        # 状态提示
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #f38ba8; font-size: 12px;")
        layout.addWidget(self.lbl_status)

    def _get_account_files(self):
        return sorted(self.config_dir.glob("*.json"))

    def _load_saved_accounts(self):
        self.account_combo.clear()
        self.account_combo.addItem("-- 请选择已保存的账号 --")
        for f in self._get_account_files():
            try:
                data = json.loads(f.read_text())
                username = data.get("username", f.stem)
                # 脱敏显示
                masked = username[:3] + "****" + username[-3:] if len(username) > 6 else username
                self.account_combo.addItem(f"{masked} ({f.stem})", f.stem)
            except Exception:
                pass

    def _load_account_data(self, account_key):
        f = self.config_dir / f"{account_key}.json"
        if f.exists():
            return json.loads(f.read_text())
        return None

    def _save_account(self, username, password, fingerprint):
        account_key = username
        data = {
            "username": username,
            "password": password,
            "fingerprint": fingerprint,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        f = self.config_dir / f"{account_key}.json"
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _toggle_password_visibility(self, checked):
        if checked:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pwd.setText("🙈")
            self.btn_toggle_pwd.setToolTip("隐藏密码")
        else:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pwd.setText("👁")
            self.btn_toggle_pwd.setToolTip("显示/隐藏密码")

    def _delete_account(self):
        idx = self.account_combo.currentIndex()
        if idx <= 0:
            return
        account_key = self.account_combo.itemData(idx)
        if not account_key:
            return
        f = self.config_dir / f"{account_key}.json"
        if f.exists():
            f.unlink()
            self._load_saved_accounts()
            self.lbl_status.setText("账号已删除")
            self.lbl_status.setStyleSheet("color: #a6e3a1; font-size: 12px;")

    def _set_loading(self, loading):
        for btn in [self.btn_load, self.btn_delete, self.btn_login_new]:
            btn.setEnabled(not loading)
        if loading:
            self.lbl_status.setText("正在登录...")
            self.lbl_status.setStyleSheet("color: #fab387; font-size: 12px;")

    def _login_saved(self):
        idx = self.account_combo.currentIndex()
        if idx <= 0:
            self.lbl_status.setText("请先选择一个已保存的账号")
            return
        account_key = self.account_combo.itemData(idx)
        data = self._load_account_data(account_key)
        if not data:
            self.lbl_status.setText("账号数据加载失败")
            return
        self._do_login(data["username"], data["password"], data["fingerprint"])

    def _login_new(self):
        username = self.input_username.text().strip()
        password = self.input_password.text().strip()
        if not username or not password:
            self.lbl_status.setText("请输入学号和密码")
            return
        # 生成指纹
        from hashlib import md5
        fingerprint = md5(str(time.time()).encode()).hexdigest()

        self._do_login(username, password, fingerprint, save=self.chk_save.isChecked())

    def _do_login(self, username, password, fingerprint, save=False):
        self._set_loading(True)
        self._login_save_flag = save
        self.thread = LoginThread(username, password, fingerprint)
        self.thread.finished_ok.connect(lambda s: self._on_login_ok(s, username, password, fingerprint, self._login_save_flag))
        self.thread.finished_err.connect(self._on_login_err)
        self.thread.need_phone.connect(self._on_need_phone_verify)
        self.thread.start()

    def _on_login_ok(self, session, username, password, fingerprint, save):
        self._set_loading(False)
        self.session = session
        self._current_username = username
        self._current_password = password
        self._current_fingerprint = fingerprint
        if save:
            self._save_account(username, password, fingerprint)
            self._load_saved_accounts()
        self.lbl_status.setText("✅ 登录成功！")
        self.lbl_status.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        self.login_success.emit(session, username, password, fingerprint)

    def _on_login_err(self, msg):
        self._set_loading(False)
        self.lbl_status.setText(f"❌ {msg}")
        self.lbl_status.setStyleSheet("color: #f38ba8; font-size: 12px;")

    def _on_need_phone_verify(self, username, password, fingerprint):
        """非可信设备，需要手机验证码登录"""
        self._set_loading(False)
        self.lbl_status.setText("⚠️ 当前设备需要手机验证码验证")
        self.lbl_status.setStyleSheet("color: #f9e2af; font-size: 12px;")

        auth_session = getattr(self.thread, 'auth_session', None)
        dialog = PhoneVerifyDialog(username, auth_session, self)
        if dialog.exec() == 1:  # 用户点了"登录"
            phone_code = dialog.get_phone_code()
            if phone_code:
                self._set_loading(True)
                self.lbl_status.setText("正在使用手机验证码登录...")
                self.lbl_status.setStyleSheet("color: #fab387; font-size: 12px;")
                self.phone_thread = PhoneVerifyThread(username, password, fingerprint, phone_code)
                self.phone_thread.finished_ok.connect(lambda s: self._on_login_ok(s, username, password, fingerprint, self._login_save_flag))
                self.phone_thread.finished_err.connect(self._on_login_err)
                self.phone_thread.start()


class PhoneVerifyDialog(QDialog):
    """手机验证码输入弹窗（纯 QDialog，控制焦点和布局）"""
    def __init__(self, username, auth_session, parent=None):
        super().__init__(parent)
        self._username = username
        self._auth_session = auth_session
        self.setWindowTitle("手机验证码")
        self.setFixedSize(400, 280)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px 12px;
                color: #cdd6f4;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #89b4fa;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #b4d0fb;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
            QPushButton#cancelBtn {
                background-color: #45475a;
                color: #cdd6f4;
            }
            QPushButton#cancelBtn:hover {
                background-color: #585b70;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 提示文字
        lbl_hint = QLabel(f"当前设备为非可信设备，需要手机验证码验证。\n学号: {username}")
        lbl_hint.setWordWrap(True)
        layout.addWidget(lbl_hint)

        # 验证码输入行
        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        lbl_code = QLabel("验证码:")
        lbl_code.setFixedWidth(60)
        code_row.addWidget(lbl_code)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("请输入6位验证码")
        self.input_code.setMaxLength(6)
        self.input_code.returnPressed.connect(self._on_confirm)
        code_row.addWidget(self.input_code)

        self.btn_send = QPushButton("📩 发送验证码")
        self.btn_send.setFixedWidth(100)
        self.btn_send.clicked.connect(self._on_send_code)
        code_row.addWidget(self.btn_send)
        layout.addLayout(code_row)

        # 状态提示
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("✖ 取消")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_login = QPushButton("✅ 登录")
        self.btn_login.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.btn_login)
        layout.addLayout(btn_row)

        # 倒计时定时器
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_remaining = 0
        self._send_thread = None

        # 弹出后自动聚焦输入框
        self.input_code.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        # 弹窗显示后自动发送验证码
        self._on_send_code()

    def _on_send_code(self):
        """点击发送验证码（后台线程）"""
        self.btn_send.setEnabled(False)
        self.btn_send.setText("发送中...")
        self.lbl_status.setText("正在发送验证码...")
        self.lbl_status.setStyleSheet("color: #fab387; font-size: 12px;")

        self._send_thread = SendCodeThread(self._username, self._auth_session)
        self._send_thread.finished_ok.connect(self._on_send_ok)
        self._send_thread.finished_err.connect(self._on_send_err)
        self._send_thread.start()

    def _on_send_ok(self):
        self.lbl_status.setText("验证码已发送，请查收手机短信")
        self.lbl_status.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        self._start_countdown(60)

    def _on_send_err(self, msg):
        self.lbl_status.setText(f"发送失败: {msg}")
        self.lbl_status.setStyleSheet("color: #f38ba8; font-size: 12px;")
        self.btn_send.setEnabled(True)
        self.btn_send.setText("重新发送")

    def _start_countdown(self, seconds):
        self._countdown_remaining = seconds
        self.btn_send.setText(f"{seconds}s")
        self.btn_send.setEnabled(False)
        self._countdown_timer.start(1000)

    def _tick_countdown(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self.btn_send.setText("重新发送")
            self.btn_send.setEnabled(True)
        else:
            self.btn_send.setText(f"{self._countdown_remaining}s")

    def _on_confirm(self):
        code = self.input_code.text().strip()
        if not code:
            return
        self.accept()

    def get_phone_code(self):
        return self.input_code.text().strip()


class SendCodeThread(QThread):
    """后台发送手机验证码"""
    finished_ok = pyqtSignal()
    finished_err = pyqtSignal(str)

    def __init__(self, username, auth_session):
        super().__init__()
        self.username = username
        self.auth_session = auth_session

    def run(self):
        try:
            from backend import FetchLectureBackend
            success, error = FetchLectureBackend.send_phone_code(self.username, self.auth_session)
            if success:
                self.finished_ok.emit()
            else:
                self.finished_err.emit(error or "发送失败")
        except Exception as e:
            self.finished_err.emit(str(e))


class LoginThread(QThread):
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)
    need_phone = pyqtSignal(str, str, str)  # username, password, fingerprint

    def __init__(self, username, password, fingerprint):
        super().__init__()
        self.username = username
        self.password = password
        self.fingerprint = fingerprint
        self.auth_session = None  # non_trusted_device 时保存 auth session

    def run(self):
        try:
            session, error_info = FetchLectureBackend.login(self.username, self.password, self.fingerprint)
            if session and not error_info:
                self.finished_ok.emit(session)
            elif error_info == 'non_trusted_device':
                self.auth_session = session  # 保存用于发送验证码
                self.need_phone.emit(self.username, self.password, self.fingerprint)
            else:
                self.finished_err.emit(f"登录失败: {error_info}")
        except Exception as e:
            self.finished_err.emit(f"登录异常: {str(e)}")


class PhoneVerifyThread(QThread):
    """带手机验证码的登录线程"""
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)

    def __init__(self, username, password, fingerprint, phone_code):
        super().__init__()
        self.username = username
        self.password = password
        self.fingerprint = fingerprint
        self.phone_code = phone_code

    def run(self):
        try:
            session, error_info = FetchLectureBackend.login_with_phone(
                self.username, self.password, self.fingerprint, self.phone_code
            )
            if session:
                self.finished_ok.emit(session)
            else:
                self.finished_err.emit(f"验证码登录失败: {error_info}")
        except Exception as e:
            self.finished_err.emit(f"验证码登录异常: {str(e)}")


class LectureListWidget(QWidget):
    """讲座列表 + 抢课控制"""
    start_fetch = pyqtSignal(str, str, str, float, float)  # wid, name, start_time, relogin_sec, delay_sec
    stop_fetch = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 讲座列表
        list_group = QGroupBox("📋 可预约讲座")
        list_layout = QVBoxLayout(list_group)

        refresh_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新列表")
        self.btn_refresh.clicked.connect(self.refresh_list)
        refresh_row.addWidget(self.btn_refresh)
        self.lbl_count = QLabel("")
        refresh_row.addWidget(self.lbl_count)
        refresh_row.addStretch()
        list_layout.addLayout(refresh_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "讲座名称", "预约时间", "活动时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # 讲座名称列自动换行
        self.table.setItemDelegateForColumn(1, WrapTextDelegate(self.table))
        # 右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        # 双击查看详情
        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        list_layout.addWidget(self.table)

        layout.addWidget(list_group, stretch=1)

        # 抢课控制
        ctrl_group = QGroupBox("🎮 抢课控制")
        ctrl_layout = QVBoxLayout(ctrl_group)

        param_row = QHBoxLayout()
        param_row.addWidget(QLabel("提前登录(秒):"))
        self.spin_relogin = QDoubleSpinBox()
        self.spin_relogin.setRange(0, 300)
        self.spin_relogin.setValue(10)
        self.spin_relogin.setSuffix(" s")
        param_row.addWidget(self.spin_relogin)

        param_row.addWidget(QLabel("延迟开始(秒):"))
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(-60, 60)
        self.spin_delay.setValue(0.5)
        self.spin_delay.setSuffix(" s")
        param_row.addWidget(self.spin_delay)
        param_row.addStretch()
        ctrl_layout.addLayout(param_row)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 开始抢课")
        self.btn_start.setObjectName("successBtn")
        self.btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self.btn_stop)
        ctrl_layout.addLayout(btn_row)

        layout.addWidget(ctrl_group)

        # 日志
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(200)
        self.log_edit.setPlaceholderText("日志输出...")
        layout.addWidget(self.log_edit)

    def refresh_list(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ 刷新中...")
        self.thread = RefreshListThread(self.session)
        self.thread.finished_ok.connect(self._on_list_ok)
        self.thread.finished_err.connect(self._on_list_err)
        self.thread.start()

    def _on_list_ok(self, lecture_list, stu_cnt_arr):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 刷新列表")
        self._lecture_list = lecture_list
        self._stu_cnt_arr = stu_cnt_arr

        self.table.setRowCount(len(lecture_list))
        for i, lec in enumerate(lecture_list):
            # 复选框列
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, chk)

            # 讲座名称（设置为换行，后面通过 resizeRowsToContents 自动调整高度）
            name_item = QTableWidgetItem(lec.get("JZMC", ""))
            self.table.setItem(i, 1, name_item)
            self.table.setItem(i, 2, QTableWidgetItem(f"{lec.get('YYKSSJ', '')} ~ {lec.get('YYJSSJ', '')}"))
            self.table.setItem(i, 3, QTableWidgetItem(lec.get("JZSJ", "")))

            # 人数已满的行变暗
            if stu_cnt_arr and stu_cnt_arr[i][0] <= stu_cnt_arr[i][1]:
                for j in range(4):
                    item = self.table.item(i, j)
                    if item:
                        item.setForeground(QColor("#6c7086"))

        # 根据内容自动调整行高（让讲座名称换行后完整显示）
        self.table.resizeRowsToContents()
        self.lbl_count.setText(f"共 {len(lecture_list)} 个讲座")

    def _on_table_context_menu(self, pos):
        """右键菜单：查看详情"""
        row = self.table.rowAt(pos.y())
        if row < 0 or not hasattr(self, '_lecture_list'):
            return
        menu = QMenu(self.table)
        menu.setStyleSheet("""
            QMenu {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)
        action_detail = menu.addAction("📋 查看详情")
        action_detail.triggered.connect(lambda: self._show_lecture_detail(row))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_table_double_click(self, row, col):
        """双击行查看详情"""
        if not hasattr(self, '_lecture_list'):
            return
        self._show_lecture_detail(row)

    def _show_lecture_detail(self, row):
        """显示讲座详情弹窗"""
        if row < 0 or row >= len(self._lecture_list):
            return
        lec = self._lecture_list[row]
        dialog = LectureDetailDialog(lec, self)
        dialog.exec()

    def _on_list_err(self, msg):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 刷新列表")
        self.append_log(f"❌ 获取讲座列表失败: {msg}", "red")

    def _on_start(self):
        # 找到选中的讲座
        selected_idx = -1
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected_idx = i
                break

        if selected_idx < 0 or not hasattr(self, '_lecture_list'):
            self.append_log("⚠ 请先选择一个讲座", "yellow")
            return

        lec = self._lecture_list[selected_idx]
        wid = lec["WID"]
        name = lec["JZMC"]
        start_time = lec["YYKSSJ"]

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_refresh.setEnabled(False)

        self.start_fetch.emit(
            wid, name, start_time,
            self.spin_relogin.value(),
            self.spin_delay.value()
        )

    def _on_stop(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_refresh.setEnabled(True)
        self.stop_fetch.emit()

    def append_log(self, msg, color="white"):
        colors = {
            "white": "#cdd6f4",
            "green": "#a6e3a1",
            "red": "#f38ba8",
            "yellow": "#f9e2af",
            "blue": "#89b4fa",
            "cyan": "#94e2d5",
        }
        c = colors.get(color, color)
        self.log_edit.append(f'<span style="color:{c}">[{datetime.datetime.now().strftime("%H:%M:%S")}] {msg}</span>')
        # 自动滚到底部
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_controls_enabled(self, enabled):
        self.btn_start.setEnabled(enabled)
        self.btn_stop.setEnabled(not enabled)
        self.btn_refresh.setEnabled(enabled)
        self.table.setEnabled(enabled)


class RefreshListThread(QThread):
    finished_ok = pyqtSignal(list, list)
    finished_err = pyqtSignal(str)

    def __init__(self, session):
        super().__init__()
        self.session = session

    def run(self):
        try:
            session, lecture_list, stu_cnt_arr = FetchLectureBackend.get_lecture_list(self.session)
            self.finished_ok.emit(lecture_list, stu_cnt_arr)
        except Exception as e:
            self.finished_err.emit(str(e))


class MyBookingsWidget(QWidget):
    """右侧：已预约讲座列表，定时刷新"""
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # 标题 + 刷新
        header = QHBoxLayout()
        title = QLabel("✅ 已预约讲座")
        title.setFont(QFont("PingFang SC", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #a6e3a1;")
        header.addWidget(title)
        header.addStretch()
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(36, 36)
        self.btn_refresh.setToolTip("立即刷新已预约列表")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # 自动刷新间隔
        auto_row = QHBoxLayout()
        auto_row.addWidget(QLabel("自动刷新:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 300)
        self.spin_interval.setValue(30)
        self.spin_interval.setSuffix(" 秒")
        auto_row.addWidget(self.spin_interval)
        self.chk_auto = QCheckBox("启用")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(self._toggle_auto)
        auto_row.addWidget(self.chk_auto)
        auto_row.addStretch()
        layout.addLayout(auto_row)

        # 卡片式列表（替代表格，讲座名称独占一行）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: #1e1e2e; border: none; }
            QScrollBar:vertical {
                background: #1e1e2e; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #45475a; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(4, 4, 4, 4)
        self.card_layout.setSpacing(6)
        self.card_layout.addStretch()
        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area)

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.spin_interval.value() * 1000)

        # 首次加载
        self.refresh()

    def _toggle_auto(self, checked):
        if checked:
            self.timer.start(self.spin_interval.value() * 1000)
        else:
            self.timer.stop()

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        self.thread = RefreshBookingsThread(self.session)
        self.thread.finished_ok.connect(self._on_ok)
        self.thread.finished_err.connect(self._on_err)
        self.thread.start()

    def _on_ok(self, bookings):
        self.btn_refresh.setEnabled(True)
        self._bookings = bookings

        # 清空旧卡片
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not bookings:
            empty_label = QLabel("暂无已预约讲座")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #6c7086; font-size: 13px; padding: 20px;")
            self.card_layout.addWidget(empty_label)
            self.card_layout.addStretch()
            return

        for i, b in enumerate(bookings):
            card = QFrame()
            card.setStyleSheet("""
                QFrame#card {
                    background-color: #313244;
                    border: 1px solid #45475a;
                    border-radius: 8px;
                }
                QFrame#card:hover {
                    border: 1px solid #89b4fa;
                }
            """)
            card.setObjectName("card")
            card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

            # 水平布局：左侧竖条标签 + 右侧内容
            card_h_layout = QHBoxLayout(card)
            card_h_layout.setContentsMargins(0, 0, 0, 0)
            card_h_layout.setSpacing(0)

            # 左侧竖条状态标签
            sfdk = b.get("SFDK", "0")
            is_checked = sfdk == "1"
            status_bar = QFrame()
            status_bar.setFixedWidth(40)
            bar_color = "#a6e3a1" if is_checked else "#f9e2af"
            status_bar.setStyleSheet(f"""
                QFrame#statusBar {{
                    background-color: {bar_color};
                    border-top-left-radius: 8px;
                    border-bottom-left-radius: 8px;
                }}
            """)
            status_bar.setObjectName("statusBar")
            bar_layout = QVBoxLayout(status_bar)
            bar_layout.setContentsMargins(0, 8, 0, 8)
            bar_layout.setSpacing(0)
            bar_text = QLabel("已\n打\n卡" if is_checked else "未\n打\n卡")
            bar_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bar_text.setFont(QFont("PingFang SC", 10, QFont.Weight.Bold))
            bar_text.setStyleSheet(f"color: #1e1e2e; border: none;")
            bar_text.setFixedWidth(40)
            bar_layout.addWidget(bar_text)
            card_h_layout.addWidget(status_bar)

            # 右侧内容区
            content = QFrame()
            content.setStyleSheet("background: transparent; border: none;")
            card_layout = QVBoxLayout(content)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            # 第一行：讲座名称（独占一行，加粗）
            name_label = QLabel(b.get("JZMC", "（未知讲座）"))
            name_label.setWordWrap(True)
            name_label.setFont(QFont("PingFang SC", 13, QFont.Weight.Bold))
            name_label.setStyleSheet("color: #cdd6f4; border: none;")
            card_layout.addWidget(name_label)

            # 第二行：时间信息
            info_label = QLabel(
                f"📅 预约时间: {b.get('YYSJ', '-')}　　🕐 活动时间: {b.get('JZSJ', '-')}"
            )
            info_label.setFont(QFont("PingFang SC", 11))
            info_label.setStyleSheet("color: #a6adc8; border: none;")
            card_layout.addWidget(info_label)

            card_h_layout.addWidget(content, 1)

            # 点击/双击查看详情
            row_idx = i
            card.mouseDoubleClickEvent = lambda e, r=row_idx: self._show_detail(r)
            card.contextMenuEvent = lambda e, r=row_idx: self._card_context_menu(e, r)

            self.card_layout.addWidget(card)

        self.card_layout.addStretch()

    def _card_context_menu(self, event, row):
        """卡片右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item { padding: 8px 24px; border-radius: 4px; }
            QMenu::item:selected { background-color: #45475a; }
        """)
        action = menu.addAction("📋 查看详情")
        action.triggered.connect(lambda: self._show_detail(row))
        menu.exec(event.globalPos())

    def _show_detail(self, row):
        """显示讲座详情弹窗"""
        if row < 0 or not hasattr(self, '_bookings') or row >= len(self._bookings):
            return
        dialog = LectureDetailDialog(self._bookings[row], self)
        dialog.exec()

    def _on_err(self, msg):
        self.btn_refresh.setEnabled(True)
        # 清空卡片并显示错误
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        err_label = QLabel(f"⚠️ {msg}")
        err_label.setWordWrap(True)
        err_label.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 8px;")
        self.card_layout.addWidget(err_label)
        self.card_layout.addStretch()


class RefreshBookingsThread(QThread):
    finished_ok = pyqtSignal(list)
    finished_err = pyqtSignal(str)

    def __init__(self, session):
        super().__init__()
        self.session = session

    def run(self):
        try:
            url = "https://ehall.seu.edu.cn/gsapp/sys/jzxxtjapp/hdyy/queryMyActivityList.do"
            res = self.session.post(
                f"{url}?_={int(time.time() * 1000)}",
                data={"pageIndex": 1, "pageSize": 50, "sortField": "", "sortOrder": ""},
                verify=False
            )
            result = res.json()
            datas = result.get("datas", [])
            self.finished_ok.emit(datas)
        except Exception as e:
            self.finished_err.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("东南大学研究生素质讲座 - 抢课工具")
        self.setMinimumSize(QSize(960, 640))
        self.resize(QSize(1100, 720))

        self.session = None
        self.fetch_thread = None

        self._init_ui()

    def _init_ui(self):
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 登录页
        self.login_widget = LoginWidget()
        self.login_widget.login_success.connect(self._on_login_success)
        main_layout.addWidget(self.login_widget)

        # 主内容页（左右分栏，登录后显示）
        self.content_widget = QWidget()
        content_layout = QHBoxLayout(self.content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：讲座列表 + 控制
        self.left_widget = QWidget()
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.lecture_widget = None  # 登录后创建
        left_layout.addWidget(QLabel("等待登录..."))
        splitter.addWidget(self.left_widget)

        # 右侧：已预约
        self.right_widget = QWidget()
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.bookings_widget = None  # 登录后创建
        right_layout.addWidget(QLabel("等待登录..."))
        splitter.addWidget(self.right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        content_layout.addWidget(splitter)
        self.content_widget.hide()
        main_layout.addWidget(self.content_widget)

        # 状态栏
        self.statusBar().showMessage("未登录")

    def _on_login_success(self, session, username, password, fingerprint):
        self.session = session
        self._username = username
        self._password = password
        self._fingerprint = fingerprint
        self.login_widget.hide()
        self.content_widget.show()
        self.statusBar().showMessage("✅ 已登录")

        # 创建左侧组件
        left_layout = self.left_widget.layout()
        while left_layout.count():
            left_layout.itemAt(0).widget().setParent(None)
        self.lecture_widget = LectureListWidget(session)
        self.lecture_widget.start_fetch.connect(self._on_start_fetch)
        self.lecture_widget.stop_fetch.connect(self._on_stop_fetch)
        left_layout.addWidget(self.lecture_widget)

        # 创建右侧组件
        right_layout = self.right_widget.layout()
        while right_layout.count():
            right_layout.itemAt(0).widget().setParent(None)
        self.bookings_widget = MyBookingsWidget(session)
        right_layout.addWidget(self.bookings_widget)

        # 自动刷新讲座列表
        self.lecture_widget.refresh_list()

    def _on_start_fetch(self, wid, name, start_time, relogin_sec, delay_sec):
        if not self.session:
            return
        self.fetch_thread = FetchThread(
            self.session, wid, name, start_time, relogin_sec, delay_sec,
            self._username, self._password, self._fingerprint
        )
        self.fetch_thread.log_signal.connect(self.lecture_widget.append_log)
        self.fetch_thread.success_signal.connect(self._on_fetch_success)
        self.fetch_thread.finished_signal.connect(self._on_fetch_finished)
        self.fetch_thread.start()

    def _on_stop_fetch(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.requestInterruption()
            self.fetch_thread.stop_requested = True
            self.lecture_widget.append_log("⏹ 正在停止...", "yellow")

    def _on_fetch_success(self, msg):
        self.lecture_widget.append_log(msg, "green")
        # 刷新右侧已预约列表
        if self.bookings_widget:
            self.bookings_widget.refresh()

    def _on_fetch_finished(self):
        self.lecture_widget.set_controls_enabled(True)

    def closeEvent(self, event):
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.requestInterruption()
            self.fetch_thread.stop_requested = True
            self.fetch_thread.wait(2000)
        event.accept()


class FetchThread(QThread):
    log_signal = pyqtSignal(str, str)  # msg, color
    success_signal = pyqtSignal(str)   # msg
    finished_signal = pyqtSignal()

    def __init__(self, session, wid, name, start_time_str, relogin_sec, delay_sec,
                 username, password, fingerprint):
        super().__init__()
        self.session = session
        self.wid = wid
        self.name = name
        self.start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        self.relogin_sec = relogin_sec
        self.delay_sec = delay_sec
        self.username = username
        self.password = password
        self.fingerprint = fingerprint
        self.stop_requested = False

    def run(self):
        try:
            self._run_countdown()
            if self.stop_requested:
                return
            self._run_fetch_loop()
        except Exception as e:
            self.log_signal.emit(f"❌ 异常: {str(e)}", "red")
        finally:
            self.finished_signal.emit()

    def _run_countdown(self):
        self.log_signal.emit(f"⏰ 目标时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}", "blue")
        relogin_done = False

        while not self.stop_requested:
            now = datetime.datetime.now()
            remaining = (self.start_time - now).total_seconds()

            if remaining <= -self.delay_sec:
                break

            # 提前重新登录
            if not relogin_done and 0 < remaining <= self.relogin_sec:
                self.log_signal.emit(f"🕒 提前 {self.relogin_sec} 秒，进行二次登录...", "yellow")
                try:
                    new_session = FetchLectureBackend.login(self.username, self.password, self.fingerprint)
                    if new_session:
                        self.session = new_session
                        self.log_signal.emit("✅ 二次登录成功", "green")
                    else:
                        self.log_signal.emit("⚠ 二次登录失败，继续使用当前 session", "yellow")
                    relogin_done = True
                except Exception as e:
                    self.log_signal.emit(f"❌ 二次登录失败: {e}", "red")
                    relogin_done = True

            if self.stop_requested:
                break

            # 根据剩余时间调整日志频率
            if remaining > 120:
                if int(remaining) % 30 == 0:
                    self.log_signal.emit(f"⏳ 剩余 {int(remaining)} 秒", "cyan")
                time.sleep(5)
            elif remaining > 10:
                if int(remaining) % 10 == 0:
                    self.log_signal.emit(f"⏳ 剩余 {int(remaining)} 秒", "cyan")
                time.sleep(2)
            elif remaining > 0:
                time.sleep(0.5)
            else:
                time.sleep(0.05)

        if not self.stop_requested:
            self.log_signal.emit("🚀 倒计时结束，开始抢课！", "green")

    def _run_fetch_loop(self):
        backend = FetchLectureBackend(self.session)
        attempt = 0
        check_interval = 5

        while not self.stop_requested:
            attempt += 1
            try:
                # 获取最新讲座列表检查人数
                session, lecture_list, stu_cnt_arr = FetchLectureBackend.get_lecture_list(self.session)
                if lecture_list and stu_cnt_arr:
                    for i, (total, booked) in enumerate(stu_cnt_arr):
                        if lecture_list[i].get("WID") == self.wid:
                            if total <= booked:
                                self.log_signal.emit(f"⚠ 人数已满 ({booked}/{total})，等待...", "yellow")
                                time.sleep(1)
                                attempt -= 1  # 不计为有效尝试
                                continue
                            break

                code, msg, success = backend.fetch_lecture(self.wid)
                style = "green" if success else "red" if "频繁" in msg else "yellow"
                self.log_signal.emit(f"第 {attempt} 次 | {code} | {msg}", style)

                if "验证码错误" in msg:
                    time.sleep(random.uniform(0.1, 0.3))
                    continue

                # 定期或成功时检查已预约列表
                if attempt % check_interval == 0 or success:
                    self.log_signal.emit("🔍 查询已预约列表确认...", "cyan")
                    if backend.check_booking_success(self.wid):
                        self.log_signal.emit(f"🎉 抢课成功！讲座: {self.name}", "green")
                        self.success_signal.emit(f"🎉 抢课成功确认！\n讲座: {self.name}\n第 {attempt} 次尝试")
                        return
                    elif success:
                        self.log_signal.emit("⚠ 服务器返回成功但列表未确认，继续尝试...", "yellow")

                if "频繁" in msg:
                    self.log_signal.emit("请求频繁，等待 10 秒", "yellow")
                    time.sleep(10)

                time.sleep(0.5)

            except Exception as e:
                self.log_signal.emit(f"❌ 异常: {str(e)}", "red")
                time.sleep(1)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
