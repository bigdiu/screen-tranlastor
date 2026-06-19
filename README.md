# Desktop Translator 桌面翻译工具

> 快捷键框选屏幕任意区域 → OCR 识别 → 自动翻译 → 浮窗显示结果

支持极小文字（40×14px）、视频字幕、低对比度文字。结果浮窗可拖动、可固定。

## 两个版本

| 文件 | 翻译源 | 适用场景 |
|------|--------|----------|
| `desktop_translator.py` | Google 翻译 | 海外 / 已开代理 |
| `desktop_translator_cn.py` | 百度 → 有道 → 必应（自动降级） | **国内直连，无需代理** |

两个版本除翻译源外完全相同。

## 安装

### 1. 安装 Python

需要 Python **3.10+**（推荐 3.10/3.11）

下载：[python.org](https://www.python.org/downloads/)

安装时**务必勾选** `Add Python to PATH`

### 2. 安装 Tesseract OCR 引擎（必须！）

这是 OCR 识别的核心引擎，必须单独安装：

- 下载：[UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- 安装时 **必须勾选 English 语言包**
- 默认安装路径：`C:\Program Files\Tesseract-OCR\`
- 程序会自动查找 Tesseract，无需手动配置

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
或手动安装：


pip install pytesseract translators mss Pillow pynput pystray pyspellchecker
使用

# 海外版
python desktop_translator.py

# 国内版
python desktop_translator_cn.py
启动后自动缩到系统托盘。按下 Ctrl + Shift + S 开始框选截图翻译：

按下快捷键 → 屏幕变暗，鼠标变十字
拖拽框选要翻译的区域
松开鼠标 → 自动 OCR 识别 + 翻译
结果浮窗显示在右下角（可拖动、可固定）
按 Esc 取消框选
自测

python desktop_translator.py --test
会生成一张 "Hello World" 测试图片，验证 OCR 和翻译是否正常。

使用场景
📖 英语学习（学生/自学者）
场景	怎么用
背单词查释义	看到不认识的英文，框选 → 秒出中文释义，不用切出去查词典
读英文文章/论文	遇到整句看不懂，框选整行 → 自动翻译，不打断阅读节奏
看英文视频学习	外挂字幕或不认识的台词，直接框选字幕区域 → 瞬间看懂
学编程读文档	技术文档英文多，边看边框选翻译，不用复制粘贴去网页翻
刷题/考试	模拟题英文题干看不懂，框选秒翻，不影响做题时间
背单词巩固	打开 📌 固定浮窗，反复看原文↔译文对照，加深记忆
💼 工作场景
场景	怎么用
UI/UX 设计师	看国外设计稿里的英文标注、按钮文字
测试/QA	英文软件界面快速理解功能
写代码看报错	英文报错信息框选翻译，快速定位问题
功能特性
极小文字识别 — 40×14px 级别按钮文字可正确识别
视频字幕 — 自动尝试正反双向 OCR（白字黑底/黑字白底），取最优
置信度感知拼写纠正 — 高置信度词信任 OCR 原文，不误改
结果浮窗可拖动 — 点击浮窗任意位置拖到想要的位置
图钉固定 — 点击 📌 固定浮窗不自动消失
自定义快捷键 — 设置界面可录制任意组合键
翻译缓存 — 重复文本即时返回，省流量
调试截图 — 可开启保存每次 OCR 的截图到桌面
打包为独立 exe（可选）
如果不想每次运行 Python，可以打包成单个 exe 文件直接运行：


pip install pyinstaller
pyinstaller --noconsole --onefile --collect-all spellchecker desktop_translator_cn.py
生成的 DesktopTranslator.exe 在 dist/ 目录，需要与 tesseract/ 文件夹放在同一目录（去 Tesseract 安装目录 复制 tesseract.exe 及其语言数据 tessdata/ 即可）。

快捷键
操作	快捷键
框选截图翻译	Ctrl + Shift + S（可自定义）
取消框选	Esc
关闭结果浮窗	点击 ✕ 按钮
固定/取消固定浮窗	点击 📌 按钮
拖动浮窗	点击浮窗任意位置拖拽
系统托盘
右键托盘图标可：

🪟 显示主界面
⏸ 暂停/继续监听
📖 使用说明
🚪 退出
许可证
Apache 2.0
