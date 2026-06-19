# Desktop Translator 桌面翻译工具

> 快捷键框选屏幕任意区域 → OCR 识别 → 自动翻译 → 浮窗显示结果

支持极小文字（40×14px）、视频字幕、低对比度文字。结果浮窗可拖动、可固定。

## 快速开始（推荐）

1. 从 [Releases](https://github.com/bigdiu/screen-tranlastor/releases) 下载 `DesktopTranslator_CN.zip`（国内）或 `DesktopTranslator_EN.zip`（海外）
2. 解压到任意文件夹
3. 双击 `DesktopTranslator.exe`
4. 按 **`Ctrl + Shift + S`** 开始框选翻译

> 不需要安装 Python、不需要配置环境，解压即用。

## 两个版本

| 版本 | 翻译源 | 适用 |
|------|--------|------|
| `DesktopTranslator_CN.zip` | 百度 → 有道 → 必应（自动降级） | 🏠 国内直连 |
| `DesktopTranslator_EN.zip` | Google 翻译 | 🌐 海外 |

两个版本除翻译源外完全相同，任选其一即可。

## 使用场景

### 📖 英语学习

| 场景 | 怎么用 |
|------|--------|
| **背单词查释义** | 看到不认识的英文，框选 → 秒出中文释义，不用切出去查词典 |
| **读英文文章/论文** | 遇到整句看不懂，框选整行 → 自动翻译，不打断阅读节奏 |
| **看英文视频学习** | 外挂字幕或不认识的台词，直接框选字幕区域 → 瞬间看懂 |
| **学编程读文档** | 技术文档英文多，边看边框选翻译，不用复制粘贴去网页翻 |
| **刷题/考试** | 模拟题英文题干看不懂，框选秒翻，不影响做题时间 |
| **背单词巩固** | 打开 📌 固定浮窗，反复看原文↔译文对照，加深记忆 |

### 💼 工作场景

| 场景 | 怎么用 |
|------|--------|
| **UI/UX 设计师** | 看国外设计稿里的英文标注、按钮文字 |
| **测试/QA** | 英文软件界面快速理解功能 |
| **写代码看报错** | 英文报错信息框选翻译，快速定位问题 |

## 功能

- **极小文字识别** — 40×14px 级别按钮文字可正确识别
- **视频字幕** — 自动尝试正反双向 OCR（白字黑底/黑字白底），取最优
- **置信度感知拼写纠正** — 高置信度词信任 OCR 原文，不误改
- **结果浮窗可拖动** — 点击浮窗任意位置拖到想要的位置
- **图钉固定** — 点击 📌 固定浮窗不自动消失
- **自定义快捷键** — 设置界面可录制任意组合键
- **翻译缓存** — 重复文本即时返回，省流量

## 快捷键

| 操作 | 快捷键 |
|------|--------|
| 框选截图翻译 | `Ctrl + Shift + S`（可自定义） |
| 取消框选 | `Esc` |
| 关闭结果浮窗 | 点击 ✕ 按钮 |
| 固定/取消固定浮窗 | 点击 📌 按钮 |
| 拖动浮窗 | 点击浮窗任意位置拖拽 |

## 系统托盘

右键托盘图标：显示主界面 · 暂停/继续 · 使用说明 · 退出

---

## 从源码运行（开发者）

### 环境要求

- Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)（安装时勾选 English 语言包）

### 安装与运行

```bash
pip install -r requirements.txt

# 国内版
python desktop_translator_cn.py

# 海外版
python desktop_translator.py

# 自测
python desktop_translator.py --test
```

### 打包为独立 exe

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --collect-all spellchecker desktop_translator_cn.py
```

生成的 `DesktopTranslator.exe` 在 `dist/` 目录，需将 Tesseract 安装目录下的 `tesseract.exe` 和 `tessdata/` 复制到 exe 同级目录。

## 许可证

Apache 2.0
