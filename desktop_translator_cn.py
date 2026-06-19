#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop Translator CN v2 - 截图翻译桌面工具 (国内版)
======================================================
快捷键框选屏幕区域 → OCR 识别英文/中文 → 百度翻译(→有道→必应自动降级) → 浮窗显示

与海外版区别: 翻译源使用国内可直接访问的服务, 无需代理。

安装依赖:
    pip install pytesseract translators mss Pillow pynput pystray

    还需安装 Tesseract OCR 引擎 (必须):
      - 下载: https://github.com/UB-Mannheim/tesseract/wiki
      - 安装时勾选 English 语言包
      - 安装后确保 tesseract.exe 在 PATH 中 (默认 C:\Program Files\Tesseract-OCR)

    若 pystray 有兼容问题, 可额外安装: pip install pillow pystray

PyInstaller 打包:
    pip install pyinstaller
    pyinstaller --noconsole --onefile --icon=myicon.ico desktop_translator_cn.py
    --noconsole 去掉终端窗口, --onefile 单文件, --icon 自定义图标

使用:
    python desktop_translator_cn.py
    启动后自动缩到系统托盘, 按 Ctrl+Shift+S 开始框选截图翻译
"""

import json
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import mss
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import pynput.keyboard as pynput_kb

# ---- 路径常量 ----
CONFIG_DIR = Path.home() / ".desktop_translator"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_FILE = CONFIG_DIR / "translation_cache.json"

# ---- 默认配置 ----
DEFAULT_CONFIG = {
    "hotkey_modifiers": ["ctrl", "shift"],
    "hotkey_char": "s",
    "hotkey_display": "Ctrl+Shift+S",
    "toast_duration": 3,
    "save_debug_images": False,
    "version": "1.0"
}

# ---- pynput 键名映射 ----
MODIFIER_MAP = {
    "ctrl":       pynput_kb.Key.ctrl,
    "ctrl_l":     pynput_kb.Key.ctrl_l,
    "ctrl_r":     pynput_kb.Key.ctrl_r,
    "shift":      pynput_kb.Key.shift,
    "shift_l":    pynput_kb.Key.shift_l,
    "shift_r":    pynput_kb.Key.shift_r,
    "alt":        pynput_kb.Key.alt,
    "alt_l":      pynput_kb.Key.alt_l,
    "alt_r":      pynput_kb.Key.alt_r,
    "cmd":        pynput_kb.Key.cmd,
    "cmd_l":      pynput_kb.Key.cmd_l,
    "cmd_r":      pynput_kb.Key.cmd_r,
}
MODIFIER_REVERSE = {v: k for k, v in MODIFIER_MAP.items()}
# 显示名称映射
DISPLAY_MAP = {
    "ctrl":       "Ctrl",
    "shift":      "Shift",
    "alt":        "Alt",
    "ctrl_l":     "Ctrl",
    "ctrl_r":     "Ctrl",
    "shift_l":    "Shift",
    "shift_r":    "Shift",
    "alt_l":      "Alt",
    "alt_r":      "Alt",
    "cmd":        "Win",
    "cmd_l":      "Win",
    "cmd_r":      "Win",
}


# ====================================================================
# 工具函数
# ====================================================================

def _normalize_modifier_name(name: str) -> str:
    """统一修饰键名: ctrl_l → ctrl, Shift → shift"""
    name = name.lower().replace("_l", "").replace("_r", "")
    return name


def _modifiers_to_pynput(mods: list[str]) -> set:
    """将配置中的修饰键名列表转为 pynput Key 对象集合"""
    result = set()
    for m in mods:
        m = m.lower()
        key = MODIFIER_MAP.get(m)
        if key:
            result.add(key)
    return result


# ====================================================================
# 配置管理
# ====================================================================

class ConfigManager:
    """读取/保存 config.json"""

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self._load()

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    @property
    def hotkey_modifiers(self):
        return self.config.get("hotkey_modifiers", ["ctrl", "shift"])

    @hotkey_modifiers.setter
    def hotkey_modifiers(self, value):
        self.config["hotkey_modifiers"] = value

    @property
    def hotkey_char(self):
        return self.config.get("hotkey_char", "s")

    @hotkey_char.setter
    def hotkey_char(self, value):
        self.config["hotkey_char"] = value

    @property
    def hotkey_display(self):
        return self.config.get("hotkey_display", "Ctrl+Shift+S")

    @hotkey_display.setter
    def hotkey_display(self, value):
        self.config["hotkey_display"] = value

    @property
    def toast_duration(self):
        return self.config.get("toast_duration", 3)

    @toast_duration.setter
    def toast_duration(self, value):
        self.config["toast_duration"] = float(value)

    @property
    def save_debug_images(self):
        return self.config.get("save_debug_images", False)

    @save_debug_images.setter
    def save_debug_images(self, value):
        self.config["save_debug_images"] = bool(value)


# ====================================================================
# 翻译缓存 (内存 + JSON 持久化)
# ====================================================================

class TranslationCache:
    """简单的翻译缓存, 内存+JSON 文件双写"""

    def __init__(self):
        self._mem: dict[str, str] = {}
        self._load()

    def _load(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._mem = json.load(f)
            except Exception:
                self._mem = {}

    def save(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._mem, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, text: str) -> str | None:
        return self._mem.get(text)

    def put(self, text: str, translation: str):
        self._mem[text] = translation

    def clear(self):
        self._mem.clear()
        self.save()


# ====================================================================
# 翻译服务 (国内可用: 百度 → 有道 → 必应 自动降级)
# ====================================================================

class TranslatorService:
    """使用 translators 库, 优先百度, 依次降级有道、必应 — 全部国内可直接访问"""

    # 国内可用翻译源, 按优先级排列
    _BACKENDS = ["baidu", "youdao", "bing"]

    _last_request_time = 0.0
    _lock = threading.Lock()

    @classmethod
    def translate(cls, text: str, cache: TranslationCache | None = None) -> str:
        # 缓存命中
        if cache:
            cached = cache.get(text)
            if cached:
                return cached

        # 限流
        with cls._lock:
            now = time.time()
            elapsed = now - cls._last_request_time
            if elapsed < 0.3:
                time.sleep(0.3 - elapsed)
            cls._last_request_time = time.time()

        # 导入 translators (延迟)
        import translators as ts

        # 依次尝试每个国内可用后端
        errors = []
        for backend in cls._BACKENDS:
            try:
                result = ts.translate_text(
                    text,
                    translator=backend,
                    from_language="en",
                    to_language="zh",
                    if_ignore_empty=True,
                )
                if result and result.strip():
                    result = result.strip()
                    if cache:
                        cache.put(text, result)
                    return result
            except Exception as e:
                errors.append(f"{backend}: {str(e)[:40]}")
                continue

        # 全部失败
        raise RuntimeError(
            f"所有翻译源均失败: {'; '.join(errors)}"
        )


# ====================================================================
# OCR 服务 (延迟加载)
# ====================================================================

# ---- 内置拼写检查器 (零依赖, PyInstaller 友好) ----

# Peter Norvig 风格拼写纠正: 基于编辑距离 + 常用词频表
# 内置 ~3000 常用英文单词, 无需外部数据文件, PyInstaller 打包无忧
_COMMON_WORDS: set[str] = {
    "the","be","to","of","and","a","in","that","have","i","it","for","not","on","with",
    "he","as","you","do","at","this","but","his","by","from","they","we","say","her","she",
    "or","an","will","my","one","all","would","there","their","what","so","up","out","if",
    "about","who","get","which","go","me","when","make","can","like","time","no","just",
    "him","know","take","people","into","year","your","good","some","could","them","see",
    "other","than","then","now","look","only","come","its","over","think","also","back",
    "after","use","two","how","our","work","first","well","way","even","new","want","because",
    "any","these","give","day","most","us","great","government","number","hand","part",
    "place","case","group","problem","fact","system","long","small","large","high","world",
    "house","country","right","school","state","family","student","city","public","program",
    "point","life","child","company","night","water","room","mother","area","money","story",
    "fact","month","lot","book","eye","job","word","business","issue","side","kind","head",
    "service","friend","father","power","hour","game","line","end","member","law","car",
    "market","class","level","color","home","love","name","picture","office","health",
    "person","art","war","history","party","result","change","morning","reason","research",
    "music","paper","space","body","information","door","figure","field","development",
    "image","language","road","society","technology","university","computer","report","wall",
    "team","data","food","answer","window","model","human","safety","process","science",
    "power","south","center","field","building","blood","position","action","department",
    "earth","nature","economy","education","fire","future","analysis","voice","control",
    "force","death","matter","design","knowledge","support","practice","rule","record",
    "increase","player","price","product","section","simple","single","size","south",
    "status","street","table","teacher","weight","account","activity","address","age",
    "agent","air","amount","animal","arm","artist","attention","ball","bank","bar","base",
    "bed","behavior","bit","board","boat","box","boy","brother","call","camp","captain",
    "career","cell","center","chair","chapter","character","church","coast","college",
    "committee","common","community","condition","congress","consumer","cost","couple",
    "course","court","cover","culture","cup","customer","dark","daughter","deal","defense",
    "degree","demand","democratic","difference","dinner","direction","director","discussion",
    "disease","doctor","dog","door","drawing","dream","drive","drug","duty","ear","east",
    "edge","effect","effort","egg","election","employee","energy","engine","environment",
    "evening","event","evidence","example","executive","experience","expert","eye","face",
    "factor","fall","family","fear","feeling","film","final","finger","firm","fish","floor",
    "focus","food","foot","force","form","former","free","friend","front","game","garden",
    "gas","girl","glass","goal","god","government","green","ground","group","growth","gun",
    "hair","half","hall","hand","head","heat","help","hill","history","hole","hope","horse",
    "hospital","hotel","idea","impact","industry","investment","island","item","kitchen",
    "land","language","laugh","law","leader","letter","level","library","light","limit",
    "list","loss","lot","love","machine","magazine","major","majority","management","manager",
    "manner","mark","market","material","matter","meal","media","member","memory","message",
    "method","middle","military","million","mind","minute","mission","model","moment",
    "morning","mother","mountain","mouth","movie","movement","music","nation","network",
    "newspaper","note","notice","number","object","officer","oil","operation","opinion",
    "opportunity","order","organization","owner","page","pain","painting","paper","parent",
    "park","part","partner","party","path","patient","pattern","peace","performance","period",
    "person","personal","phone","photo","piece","plan","plant","player","police","policy",
    "politics","population","position","practice","president","pressure","price","process",
    "professor","program","project","property","purpose","quality","question","race","radio",
    "rain","range","rate","reality","reason","record","region","relationship","religion",
    "report","represent","resource","response","rest","restaurant","result","risk","road",
    "rock","role","room","rule","scene","school","science","screen","sea","season","seat",
    "secretary","section","security","sense","series","service","set","seven","shape","share",
    "shoot","short","shot","shoulder","show","side","sign","single","sister","site","skill",
    "skin","smile","society","soil","soldier","song","sort","sound","source","south","space",
    "speech","sport","spring","staff","stage","stand","standard","star","start","state",
    "statement","station","step","stock","store","story","strategy","street","structure",
    "student","study","style","subject","success","sugar","summer","support","surface",
    "system","table","talk","task","tax","teach","teacher","team","technology","television",
    "tend","term","test","theory","thing","thought","thousand","threat","through","time",
    "today","together","tonight","tool","top","total","town","trade","training","travel",
    "treatment","tree","trial","trip","trouble","truth","turn","type","unit","value","video",
    "view","violence","visit","voice","vote","wall","war","watch","water","weapon","week",
    "weight","west","white","whole","wife","will","win","wind","window","woman","wonder",
    "wood","word","work","worker","world","writer","yard","year","young","account","achieve",
    "acquire","act","adapt","add","address","adjust","admit","adopt","advance","advise",
    "afford","agree","aid","aim","alert","allow","announce","answer","appeal","apply",
    "appoint","approach","approve","argue","arrange","assess","assign","assist","assume",
    "attach","attack","attempt","attend","attract","authorize","available","avoid","base",
    "beat","become","begin","believe","belong","benefit","bind","block","board","borrow",
    "break","breed","bring","broadcast","build","burn","buy","calculate","capture","carry",
    "catch","celebrate","change","choose","claim","climb","close","collect","combine","come",
    "comment","commit","compare","compete","complain","complete","concern","confirm","connect",
    "consider","consist","construct","contain","continue","contribute","convert","cook","copy",
    "correct","count","create","cross","cry","cut","damage","deal","debate","decide","declare",
    "decline","defend","define","deliver","demand","deny","depend","describe","design",
    "destroy","determine","develop","die","dig","direct","discover","discuss","display",
    "divide","document","draft","drag","draw","dress","drink","drive","drop","dry","earn",
    "eat","edit","elect","eliminate","employ","enable","encounter","encourage","engage",
    "enhance","enjoy","ensure","enter","establish","evaluate","examine","exist","expand",
    "expect","experiment","explain","explore","express","extend","fail","fasten","feed",
    "feel","fight","fill","finance","find","finish","fit","fix","fly","focus","fold","follow",
    "forbid","force","forget","forgive","form","found","frame","freeze","gain","gather",
    "generate","grant","grow","handle","hang","happen","heal","hear","heat","hide","hit",
    "hold","hunt","hurry","hurt","identify","ignore","illustrate","imagine","implement",
    "imply","impose","improve","include","incorporate","indicate","influence","inform",
    "initiate","install","intend","introduce","invest","invite","involve","isolate","join",
    "judge","jump","justify","keep","kick","kill","kiss","knock","know","labor","lack",
    "land","last","laugh","launch","lay","lead","lean","learn","leave","lend","lie","lift",
    "like","limit","link","listen","live","load","locate","lock","look","lose","love",
    "maintain","manage","mark","match","matter","mean","measure","meet","mention","merge",
    "mind","miss","mix","modify","monitor","mount","move","name","need","negotiate","note",
    "notice","obtain","occur","offer","open","operate","oppose","order","organize","overcome",
    "owe","own","paint","park","participate","pass","pay","perform","permit","persuade","pick",
    "place","plan","play","point","possess","post","predict","prepare","present","prevent",
    "print","produce","promise","promote","propose","protect","prove","provide","publish",
    "pull","purchase","pursue","push","put","qualify","raise","reach","read","realize",
    "receive","recognize","recommend","record","recover","reduce","refer","reflect","refuse",
    "register","regulate","reject","relate","release","rely","remain","remember","remove",
    "repeat","replace","reply","report","represent","request","require","research","resolve",
    "respond","restore","result","retain","retire","return","reveal","review","ride","ring",
    "rise","roll","run","save","search","secure","seek","select","sell","send","separate",
    "serve","set","settle","shake","shape","share","shelter","shift","shoot","show","shut",
    "sign","signal","sing","sit","sleep","slide","smile","solve","speak","spend","split",
    "spread","stand","stare","start","stay","steal","stick","stop","store","stretch","strike",
    "struggle","study","submit","succeed","suffer","suggest","supply","support","suppose",
    "surround","survive","suspect","sustain","swim","switch","tackle","take","talk","tap",
    "target","teach","tear","tell","tend","thank","think","threaten","throw","touch","track",
    "trade","train","transfer","transform","translate","transport","travel","treat","trigger",
    "trust","try","turn","understand","undertake","use","vary","view","visit","vote","wait",
    "walk","want","warn","wash","watch","wave","wear","welcome","win","wish","wonder","work",
    "worry","wrap","write","yield","active","actual","afraid","alone","ancient","angry",
    "annual","anxious","appropriate","asleep","average","aware","basic","beautiful","big",
    "bitter","black","blue","brief","bright","broad","broken","brown","busy","calm","careful",
    "central","cheap","certain","chief","clean","clear","close","cold","comfortable","common",
    "complex","concerned","confident","conscious","constant","cool","correct","costly","crazy",
    "creative","critical","cultural","current","daily","dangerous","dark","dead","dear","deep",
    "democratic","dependent","desperate","detailed","different","difficult","digital","dirty",
    "distant","distinct","domestic","double","dramatic","dry","due","eager","early","eastern",
    "easy","economic","effective","efficient","electric","electronic","emotional","empty",
    "entire","environmental","equal","essential","every","evil","exact","excellent","exciting",
    "existing","expensive","external","extra","extreme","fair","familiar","famous","fast",
    "federal","female","financial","fine","firm","flat","foreign","formal","former","free",
    "frequent","fresh","friendly","front","full","fundamental","funny","future","general",
    "genuine","global","golden","grand","gray","green","growing","guilty","happy","hard",
    "healthy","heavy","helpful","high","historical","holy","honest","hot","huge","human",
    "hungry","ideal","illegal","immediate","important","impossible","independent","industrial",
    "initial","inner","innocent","intellectual","intelligent","intense","interesting",
    "internal","international","joint","just","key","large","late","latin","leading","left",
    "legal","liberal","likely","limited","literary","little","live","living","local","lonely",
    "long","loose","loud","lovely","low","lucky","mad","magnetic","main","major","male",
    "mass","massive","maximum","medical","mental","mere","middle","mighty","military","minor",
    "minute","missing","mobile","modern","modest","moral","musical","mutual","narrow",
    "national","native","natural","near","negative","nervous","neutral","new","nice","noble",
    "normal","northern","notable","numerous","odd","official","okay","old","only","open",
    "opposite","ordinary","organic","original","other","outside","overall","painful","pale",
    "particular","past","patient","peaceful","perfect","personal","physical","plain","plastic",
    "pleasant","political","poor","popular","positive","possible","potential","powerful",
    "practical","precious","present","pretty","principal","private","professional","proper",
    "protective","proud","public","pure","quick","quiet","racial","random","rapid","rare",
    "raw","ready","real","reasonable","recent","red","regional","regular","related","relative",
    "religious","remaining","remarkable","remote","representative","responsible","rich","right",
    "rising","romantic","rough","royal","rural","sacred","sad","safe","scared","scientific",
    "secondary","secret","secure","senior","sensitive","serious","severe","sexual","sharp",
    "short","sick","significant","silent","silly","similar","simple","sincere","single",
    "slight","slow","small","smart","smooth","social","soft","solar","solid","sorry","southern",
    "specific","spiritual","square","stable","standard","steady","steep","stiff","still",
    "straight","strange","strategic","strict","strong","structural","substantial","successful",
    "sudden","sufficient","suitable","sunny","super","sure","surprised","suspicious","sweet",
    "symbolic","tall","technical","temporary","tender","terrible","theoretical","thick","thin",
    "tight","tiny","tired","total","tough","traditional","tropical","true","typical","ugly",
    "ultimate","unable","uncomfortable","underlying","unexpected","unfair","unhappy","unique",
    "universal","unknown","unlikely","unusual","upper","urban","useful","usual","vague",
    "valid","valuable","various","vast","very","violent","visible","visual","vital","warm",
    "weak","wealthy","weird","welcome","western","wet","white","whole","wide","widespread",
    "wild","willing","wise","wonderful","wooden","working","worldwide","worried","worth",
    "wrong","yellow","young",
}

# 补充常见 OCR 易错映射 (数字/符号误识别为字母)
_OCR_CONFUSIONS = {
    "0": "o", "1": "l", "2": "z", "4": "a", "5": "s", "6": "g",
    "7": "t", "8": "b", "9": "g", "|": "l", "@": "a",
}


class _SimpleSpellChecker:
    """基于编辑距离的内置拼写检查器 (无外部依赖, PyInstaller 友好)"""

    def __init__(self, word_set: set[str] | None = None):
        self._words = word_set or _COMMON_WORDS
        # 生成所有编辑距离为 1 的候选词的 lambda
        self._letters = "abcdefghijklmnopqrstuvwxyz"

    def _edits1(self, word: str) -> set[str]:
        """编辑距离为 1 的所有字符串"""
        splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        deletes = [L + R[1:] for L, R in splits if R]
        transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
        replaces = [L + c + R[1:] for L, R in splits if R for c in self._letters]
        inserts = [L + c + R for L, R in splits for c in self._letters]
        return set(deletes + transposes + replaces + inserts)

    def _edits2(self, word: str) -> set[str]:
        """编辑距离为 2 的所有字符串"""
        return {e2 for e1 in self._edits1(word) for e2 in self._edits1(e1)}

    def _known(self, words_set: set[str]) -> set[str]:
        return words_set & self._words

    def _apply_ocr_fixes(self, word: str) -> str:
        """针对常见 OCR 数字→字母混淆做预修正"""
        result = list(word)
        for i, ch in enumerate(result):
            lower = ch.lower()
            if lower in _OCR_CONFUSIONS:
                # 仅当替换后能组成已知词时才替换
                candidate = word[:i] + _OCR_CONFUSIONS[lower] + word[i+1:]
                if candidate.lower() in self._words:
                    result[i] = _OCR_CONFUSIONS[lower]
        return "".join(result)

    def correction(self, word: str) -> str | None:
        """返回最可能的正确拼写, 若未找到则返回 None"""
        w = word.lower()
        # 已是已知词, 直接返回
        if w in self._words:
            return word
        # 先尝试 OCR 常见混淆修正
        fixed = self._apply_ocr_fixes(w)
        if fixed != w and fixed in self._words:
            return fixed
        # 编辑距离 1 候选
        candidates = self._known(self._edits1(w))
        if candidates:
            return max(candidates, key=lambda c: self._word_score(c, w))
        # 编辑距离 2 候选
        candidates = self._known(self._edits2(w))
        if candidates:
            return max(candidates, key=lambda c: self._word_score(c, w))
        # 找不到已知词 → 返回 None, 保持原词不变
        return None

    def _word_score(self, candidate: str, original: str) -> int:
        """评分函数: 综合考虑词频 + 与原词的相似度
        高分 = 常用词 + 与原词共享更多字符位置"""
        score = 0
        # 1. 高频短词加分
        high_priority = {"the", "be", "to", "of", "and", "a", "in", "that", "have",
                          "i", "it", "for", "not", "on", "with", "he", "as", "you",
                          "do", "at", "this", "but", "his", "by", "from"}
        if candidate in high_priority:
            score += 1000
        # 2. 较短常用词加分 (短词更常见)
        score += max(0, 10 - len(candidate))
        # 3. 与原词共享前缀加分 (如 hel* → hello 优于 well)
        common_prefix = 0
        for a, b in zip(candidate, original):
            if a == b:
                common_prefix += 1
            else:
                break
        score += common_prefix * 5
        # 4. 首字母相同加分 (OCR 很少错首字母)
        if candidate and original and candidate[0] == original[0]:
            score += 3
        return score

    def unknown(self, words: list[str]) -> set[str]:
        """返回不在词表中的单词集合"""
        return {w for w in words if w.lower() not in self._words}


class OCRService:
    """Tesseract OCR 封装，专注英文识别，带置信度过滤 + 拼写纠正"""

    _spell = None  # 拼写检查器实例, 延迟加载

    @classmethod
    def _preprocess(cls, pil_image: Image.Image) -> Image.Image:
        """预处理 — 极致小字识别

        策略 (针对 50×15 级别极小区域):
          1. 超高倍放大 (最高 10×) — 确保字符≥60px 高
          2. 高斯预模糊 → 消除 JPEG/屏幕噪点, 避免放大后放大噪点
          3. LANCZOS 放大 — 产生抗锯齿平滑边缘, 匹配 LSTM 训练分布
          4. 自适应锐化 — 越小锐化越强, 恢复放大损失的边缘
          5. 白边内缩 — Tesseract 对贴边文字识别率急剧下降"""
        w, h = pil_image.size
        min_dim = min(w, h)

        # ─ 自适应放大: 让最小边至少达到 ~150px ─
        if min_dim < 20:
            scale = 10
        elif min_dim < 30:
            scale = 8
        elif min_dim < 50:
            scale = 6
        elif min_dim < 80:
            scale = 5
        elif min_dim < 120:
            scale = 4
        else:
            scale = 3

        # 1. 灰度
        gray = pil_image.convert("L")

        # 2. 直方图拉伸 — 切除两端 1% 极值, 消除雾化背景
        enhanced = ImageOps.autocontrast(gray, cutoff=1)

        # 3. 高斯预模糊 — 微小半径消除噪点, 防止放大时噪点被强化
        #    半径 0.5 不会模糊笔划, 只抑制高频噪点
        smoothed = enhanced.filter(ImageFilter.GaussianBlur(radius=0.5))

        # 4. LANCZOS 高质量放大
        upscaled = smoothed.resize((w * scale, h * scale), Image.LANCZOS)

        # 5. 自适应锐化 — 文字越小锐化越强 (补偿放大后的边缘柔化)
        if min_dim < 30:
            sharpened = upscaled.filter(
                ImageFilter.UnsharpMask(radius=2, percent=220, threshold=1))
        elif min_dim < 60:
            sharpened = upscaled.filter(
                ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))
        else:
            sharpened = upscaled.filter(
                ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

        # 6. 加白边 — Tesseract 对贴边文字识别率极低
        #    在四周各加 8% 白边, 让文字与图像边界分开
        pad_w = max(int(w * scale * 0.08), 8)
        pad_h = max(int(h * scale * 0.08), 8)
        padded = ImageOps.expand(sharpened, border=(pad_w, pad_h, pad_w, pad_h), fill=255)

        return padded

    @classmethod
    def _get_spell(cls):
        """加载拼写检查器: 优先 pyspellchecker (完整词典), 失败则降级到内置版本"""
        if cls._spell is not None:
            return cls._spell

        # 先尝试 pyspellchecker (更准确, 词表更大)
        try:
            from spellchecker import SpellChecker
            cls._spell = SpellChecker()
            return cls._spell
        except Exception:
            pass  # PyInstaller 打包后可能缺数据文件, 静默降级

        # 降级到内置轻量拼写检查器 (零依赖, PyInstaller 安全)
        cls._spell = _SimpleSpellChecker(_COMMON_WORDS)
        return cls._spell

    @classmethod
    def _spell_correct(cls, text: str, confidences: dict[str, int] | None = None) -> str:
        """对 OCR 结果做拼写纠正: 仅修正低置信度的明显拼写错误
        confidences: 词→置信度映射, 高置信度(≥60)词跳过纠正, 信任 OCR 原始结果"""
        try:
            spell = cls._get_spell()
        except Exception:
            return text  # 极端情况: 拼写检查器加载失败, 返回原文

        words = text.split()
        corrected = []
        for word in words:
            # 跳过纯数字、URL、路径、单字符
            if (word.isdigit() or len(word) <= 1
                    or word.startswith(('http', 'www', '/', '\\', '.'))):
                corrected.append(word)
                continue
            # 清理首尾标点 (保留用于后续拼接)
            stripped = word.strip('.,!?;:()[]{}"\'')
            if not stripped:
                corrected.append(word)
                continue
            # 高置信度词: 信任 OCR, 跳过拼写纠正
            conf = (confidences or {}).get(stripped, (confidences or {}).get(stripped.lower(), -1))
            if conf >= 60:
                corrected.append(word)
                continue
            # 仅修正已知的拼写错误, 未登录词保持原样
            misspelled = spell.unknown([stripped])
            if stripped in misspelled:
                fix = spell.correction(stripped)
                if fix and fix != stripped:
                    word = word.replace(stripped, fix)
            corrected.append(word)
        return " ".join(corrected)

    @classmethod
    def _find_tesseract(cls) -> str:
        """自动查找 tesseract.exe 路径
        优先级: 打包目录 > 系统安装 > PATH"""
        import shutil

        # 1. PyInstaller 打包后: 检查 exe 同级的 tesseract 文件夹
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
            bundled = base / "tesseract" / "tesseract.exe"
            if bundled.exists():
                return str(bundled)

        # 2. 常见安装位置
        candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)

        # 3. PATH 中查找
        found = shutil.which("tesseract")
        if found:
            return found

        # 4. 回退默认位置 (让 pytesseract 报错给出明确提示)
        return r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    @classmethod
    def _safe_conf(cls, val) -> int:
        """安全地将置信度值转为 int, 兼容不同 pytesseract 版本"""
        try:
            return int(val)
        except (ValueError, TypeError):
            return -1

    @classmethod
    def _ocr_pass(cls, processed: Image.Image) -> tuple[list[str], dict[str, int]]:
        """在单张预处理图上运行 Tesseract (OEM 1 LSTM, PSM 4→7 降级)
        返回 (words, conf_map) — 最佳配置下的词汇列表和置信度映射"""
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cls._find_tesseract()

        tesseract_configs = [
            '--psm 4 --oem 1',
            '--psm 7 --oem 1',
        ]

        best_words: list[str] = []
        best_conf: dict[str, int] = {}

        for config in tesseract_configs:
            data = pytesseract.image_to_data(
                processed, lang='eng',
                config=config,
                output_type=pytesseract.Output.DICT
            )

            words = []
            conf_map: dict[str, int] = {}
            for i, conf in enumerate(data['conf']):
                c = cls._safe_conf(conf)
                if c >= 30:
                    word = data['text'][i].strip()
                    if word:
                        words.append(word)
                        key = word.lower()
                        if key not in conf_map or c > conf_map[key]:
                            conf_map[key] = c

            if len(words) > len(best_words):
                best_words, best_conf = words, conf_map
            elif (words and best_words
                  and sum(conf_map.values()) / len(conf_map)
                  > sum(best_conf.values()) / len(best_conf)):
                best_words, best_conf = words, conf_map

            if best_words and len(best_words) >= 4:
                if sum(best_conf.values()) / len(best_conf) >= 55:
                    break

        # ─ 置信度过滤后无结果 → 全量回退 ─
        if not best_words:
            for config in tesseract_configs:
                raw = pytesseract.image_to_string(
                    processed, lang='eng', config=config
                ).strip()
                if raw:
                    break
            lines = [ln for ln in raw.splitlines() if ln.strip()]
            raw_text = " ".join(lines)
            if raw_text:
                best_words = raw_text.split()
                # 回退模式下无置信度信息
                best_conf = {}

        return best_words, best_conf

    @classmethod
    def recognize(cls, pil_image: Image.Image) -> str:
        processed = cls._preprocess(pil_image)

        # ── 正向 OCR (深色文字/浅色背景 — UI 常见) ──
        words, conf_map = cls._ocr_pass(processed)

        # ── 反向 OCR (浅色文字/深色背景 — 视频字幕常见) ──
        #     视频字幕通常是白色/浅色文字 + 深色描边, 反转后变成黑字白底
        #     对 Tesseract 更友好, 往往能显著提升识别率
        inverted = ImageOps.invert(processed)
        inv_words, inv_conf = cls._ocr_pass(inverted)

        # ── 选最优: 更多词 + 更高平均置信度 ──
        def _score(w, c):
            if not w:
                return -1
            avg = sum(c.values()) / len(c) if c else 0
            return len(w) * 10 + avg

        if _score(inv_words, inv_conf) > _score(words, conf_map):
            words, conf_map = inv_words, inv_conf

        raw_text = " ".join(words) if words else ""
        return cls._spell_correct(raw_text, confidences=conf_map).strip()
# ====================================================================
# 截图遮罩 (全屏框选)
# ====================================================================

class ScreenOverlay:
    """全屏截图遮罩 — 显示屏幕截图+暗色叠加, 鼠标框选区域 (纯 Pillow, 无 numpy 依赖)"""

    def __init__(self, on_capture, config: "ConfigManager | None" = None):
        """
        on_callback(img: PIL.Image) — 用户完成框选后的回调
        config: ConfigManager — 读取 save_debug_images 等配置
        """
        self.on_capture = on_capture
        self.config = config
        self.window = None
        self.canvas = None
        self._photo = None
        self._original = None   # PIL Image — 原始截图
        self._darkened = None   # PIL Image — 暗化版本
        self._start_x = self._start_y = 0
        self._end_x = self._end_y = 0
        self._drawing = False
        self._w = self._h = 0

    def show(self):
        """显示全屏遮罩"""
        # 截图
        with mss.MSS() as sct:
            monitor = sct.monitors[0]  # 虚拟桌面 (所有显示器)
            sct_img = sct.grab(monitor)
            self._w, self._h = sct_img.size
            self._original = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            # 暗化: 每个像素通道乘以 0.45 (纯 Pillow point 操作)
            self._darkened = self._original.point(lambda p: int(p * 0.45))

        # 窗口
        self.window = tk.Toplevel()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{self._w}x{self._h}+0+0")
        self.window.configure(bg="black")
        self.window.focus_force()

        # Canvas
        self.canvas = tk.Canvas(
            self.window, width=self._w, height=self._h,
            highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack()

        # 初始显示暗化图
        self._update_display()

        # 鼠标事件
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Escape>", lambda e: self._close())
        self.window.bind("<Escape>", lambda e: self._close())

        self.window.grab_set()

    def _update_display(self, x1=0, y1=0, x2=0, y2=0, has_selection=False):
        """绘制暗化底图 + (可选) 高亮选区 (纯 Pillow composite)"""
        if has_selection:
            composited = self._darkened.copy()
            # 选区内恢复原始亮度: crop + paste
            region = self._original.crop((x1, y1, x2, y2))
            composited.paste(region, (x1, y1))
            pil_img = composited
        else:
            pil_img = self._darkened

        self._photo = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        if has_selection and x2 > x1 and y2 > y1:
            # 选区边框
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#00a8ff", width=2, dash=""
            )
            # 尺寸标签
            text = f"{x2 - x1} × {y2 - y1}"
            self.canvas.create_text(
                (x1 + x2) // 2, max(y1 - 20, 5),
                text=text, fill="#00a8ff",
                font=("Microsoft YaHei", 11, "bold"),
                anchor="s"
            )

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        self._drawing = True

    def _on_drag(self, event):
        if not self._drawing:
            return
        self._end_x = max(0, min(event.x, self._w))
        self._end_y = max(0, min(event.y, self._h))
        x1, x2 = sorted((self._start_x, self._end_x))
        y1, y2 = sorted((self._start_y, self._end_y))
        self._update_display(x1, y1, x2, y2, has_selection=True)

    def _on_release(self, event):
        self._drawing = False
        self._end_x = max(0, min(event.x, self._w))
        self._end_y = max(0, min(event.y, self._h))
        x1, x2 = sorted((self._start_x, self._end_x))
        y1, y2 = sorted((self._start_y, self._end_y))
        w, h = x2 - x1, y2 - y1
        if w < 10 or h < 10:
            self._close()
            return

        # 截取选中区域 (Pillow crop)
        pil_img = self._original.crop((x1, y1, x2, y2))

        # 调试截图: 仅在配置开启时保存
        if self.config and self.config.save_debug_images:
            try:
                debug_dir = Path.home() / "Desktop" / "_ocr_debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_path = debug_dir / f"ocr_{int(time.time())}.png"
                pil_img.save(debug_path)
            except Exception:
                pass

        self._close()
        self.on_capture(pil_img)

    def _close(self):
        if self.window:
            try:
                self.window.grab_release()
                self.window.destroy()
            except Exception:
                pass
            self.window = None
            self.canvas = None


# ====================================================================
# 翻译结果浮窗 (右下角, 3 秒自动消失)
# ====================================================================

class ResultToast:
    """可拖动的右下角浮窗, 按配置时长自动关闭, 支持图钉固定"""

    def __init__(self, config: ConfigManager | None = None):
        self.config = config
        self.window = None
        self._pinned = False
        self._auto_close_id = None
        self._drag_x = 0
        self._drag_y = 0

    def _start_drag(self, event):
        """记录拖拽起始偏移"""
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        """拖拽移动窗口"""
        x = self.window.winfo_x() + (event.x - self._drag_x)
        y = self.window.winfo_y() + (event.y - self._drag_y)
        self.window.geometry(f"+{x}+{y}")

    def _stop_drag(self, event):
        """拖拽结束"""
        self._drag_x = 0
        self._drag_y = 0

    def show(self, english: str, translation: str):
        # 关闭旧浮窗
        self._close_window()
        self._pinned = False

        self.window = tk.Toplevel()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        # 主容器 — 点击任意空白区域可拖动, 按钮自动消费事件不干扰拖动
        frame = tk.Frame(self.window, bg="white", relief="solid", bd=1,
                         cursor="fleur")
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        # ── 拖动事件绑定 (在 frame 和 window 级别) ──
        for widget in (self.window, frame):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)
            widget.bind("<ButtonRelease-1>", self._stop_drag)

        # 原文 (英文) — 也绑定拖动, 但不消费 Button-1 (Label 默认不消费)
        en_label = tk.Label(
            frame, text=english.strip(),
            font=("Microsoft YaHei", 11, "bold"),
            fg="#1565C0", bg="white", cursor="fleur",
            wraplength=520, justify="left", anchor="w"
        )
        en_label.pack(fill="x", padx=16, pady=(10, 6))
        for w in (en_label,):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._stop_drag)

        # 分隔线
        sep = tk.Frame(frame, bg="#d0d0d0", height=1)
        sep.pack(fill="x", padx=16, pady=4)

        # 翻译结果 (简体中文) — 可拖动
        tr_label = tk.Label(
            frame, text=translation.strip(),
            font=("Microsoft YaHei", 10),
            fg="#2E7D32", bg="white", cursor="fleur",
            wraplength=520, justify="left", anchor="w"
        )
        tr_label.pack(fill="x", padx=16, pady=(4, 10))
        for w in (tr_label,):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._stop_drag)

        # 图钉按钮 (切换固定/自动消失, 放在关闭按钮左边)
        self._pin_btn = tk.Label(
            frame, text="📌",
            font=("Segoe UI Emoji", 10),
            fg="#999", bg="white", cursor="hand2"
        )
        self._pin_btn.place(relx=1.0, x=-32, y=5, anchor="ne")
        self._pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())
        self._pin_btn.bind("<Enter>", lambda e: self._pin_btn.config(fg="#333"))
        self._pin_btn.bind("<Leave>", lambda e: self._pin_btn.config(
            fg="#e74c3c" if self._pinned else "#999"))

        # 关闭按钮 (右上角)
        close_btn = tk.Label(
            frame, text="✕",
            font=("Consolas", 10),
            fg="#aaa", bg="white", cursor="hand2"
        )
        close_btn.place(relx=1.0, x=-8, y=6, anchor="ne")
        close_btn.bind("<Button-1>", lambda e: self._close_window())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg="#aaa"))

        # 定位右下角 — 先更新布局以获取真实尺寸
        self.window.update_idletasks()
        w = self.window.winfo_reqwidth()
        h = self.window.winfo_reqheight()
        # 限制最小/最大宽度, 避免过长文本超出屏幕
        w = min(620, max(280, w))
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = screen_w - w - 25
        y = screen_h - h - 55
        self.window.geometry(f"{w}x{h}+{x}+{y}")

        # 自动关闭定时器
        self._schedule_auto_close()

    def _schedule_auto_close(self):
        """根据当前固定状态决定是否启动自动关闭定时器"""
        if self._pinned:
            return
        duration = self.config.toast_duration if self.config else 3
        duration_ms = int(duration * 1000)
        self._auto_close_id = self.window.after(duration_ms, self._close_window)

    def _toggle_pin(self):
        """切换图钉状态: 固定 ↔ 自动消失"""
        self._pinned = not self._pinned
        if self._pinned:
            # 固定: 取消自动关闭定时器, 图钉变红
            if self._auto_close_id:
                self.window.after_cancel(self._auto_close_id)
                self._auto_close_id = None
            self._pin_btn.config(text="📍", fg="#e74c3c")
        else:
            # 取消固定: 重新启动定时器, 图钉变灰
            self._pin_btn.config(text="📌", fg="#999")
            self._schedule_auto_close()

    def _close_window(self):
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
            self._auto_close_id = None


# ====================================================================
# 快捷键设置窗口
# ====================================================================

class HotkeyCaptureWindow:
    """捕获用户按下新快捷键的对话框"""

    def __init__(self, master: tk.Tk, callback):
        """
        callback(modifiers: list[str], char: str, display: str)
        """
        self.callback = callback
        self._modifiers = set()
        self._char = None
        self._listener = None

        self.window = tk.Toplevel(master)
        self.window.title("设置快捷键")
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        self.window.configure(bg="#f5f5f5")

        # 居中
        win_w, win_h = 380, 200
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        self.window.geometry(f"{win_w}x{win_h}+{(sw-win_w)//2}+{(sh-win_h)//2}")
        self.window.grab_set()

        # 内容
        frame = tk.Frame(self.window, bg="#f5f5f5")
        frame.pack(expand=True, fill="both", padx=30, pady=25)

        tk.Label(
            frame, text="请按下新的快捷键组合",
            font=("Microsoft YaHei", 12),
            bg="#f5f5f5", fg="#333"
        ).pack(pady=(0, 15))

        self.display_var = tk.StringVar(value="等待按键...")
        tk.Label(
            frame, textvariable=self.display_var,
            font=("Consolas", 18, "bold"),
            bg="#e8e8e8", fg="#1565C0",
            relief="sunken", bd=2, width=20, height=2
        ).pack(pady=(0, 20))

        hint = tk.Label(
            frame, text="至少包含一个修饰键 (Ctrl/Shift/Alt) + 一个字母/数字",
            font=("Microsoft YaHei", 9),
            bg="#f5f5f5", fg="#999"
        )
        hint.pack()

        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.window.bind("<Escape>", lambda e: self._on_cancel())

        # 启动 pynput 监听
        self._listener = pynput_kb.Listener(on_press=self._on_key, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def _update_display(self):
        parts = [DISPLAY_MAP.get(m, m.title()) for m in self._modifiers]
        if self._char:
            parts.append(self._char.upper())
        self.display_var.set(" + ".join(parts) if parts else "等待按键...")

    def _on_key(self, key):
        try:
            if isinstance(key, pynput_kb.Key):
                name = MODIFIER_REVERSE.get(key)
                if name:
                    self._modifiers.add(_normalize_modifier_name(name))
                    self.window.after(0, self._update_display)
            elif isinstance(key, pynput_kb.KeyCode):
                char = key.char
                if char and char.isprintable():
                    self._char = char
                    self.window.after(0, self._update_display)
                    # 完成: 至少一个修饰键 + 一个字符
                    if self._modifiers and self._char:
                        self.window.after(100, self._on_confirm)
        except Exception:
            pass

    def _on_release(self, key):
        pass  # 不需要处理释放

    def _on_confirm(self):
        mods = sorted(self._modifiers)
        char = self._char
        display = " + ".join(
            [DISPLAY_MAP.get(m, m.title()) for m in mods] + [char.upper()]
        )
        self._cleanup()
        self.window.destroy()
        self.callback(mods, char, display)

    def _on_cancel(self):
        self._cleanup()
        self.window.destroy()

    def _cleanup(self):
        if self._listener and self._listener.running:
            self._listener.stop()
            self._listener = None


# ====================================================================
# 主应用程序
# ====================================================================

class TranslatorApp:
    """主应用 — 窗口 + 系统托盘 + 全局快捷键"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("桌面翻译工具")
        self.root.geometry("380x400")
        self.root.resizable(False, False)
        self.root.configure(bg="#fafafa")

        # 配置
        self.config = ConfigManager()
        self.cache = TranslationCache()

        # 组件
        self.toast = ResultToast(config=self.config)
        self.overlay = None
        self._processing = False

        # 全局快捷键状态
        self._hotkey_listener = None
        self._paused = False

        # ---- 界面 ----
        self._build_ui()

        # 关闭窗口 → 隐藏到托盘
        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        # 启动系统托盘
        self._tray_icon = None
        self._tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        self._tray_thread.start()

        # 启动快捷键监听
        self._start_hotkey_listener()

        # 启动自动最小化到托盘
        self.root.after(500, self._minimize_to_tray)

    # ── UI 构建 ──────────────────────────────────────────────────

    def _build_ui(self):
        main_frame = tk.Frame(self.root, bg="#fafafa")
        main_frame.pack(expand=True, fill="both", padx=30, pady=20)

        # 标题
        tk.Label(
            main_frame, text="🔍 桌面翻译工具",
            font=("Microsoft YaHei", 16, "bold"),
            bg="#fafafa", fg="#333"
        ).pack(pady=(0, 5))

        tk.Label(
            main_frame, text="快捷键框选屏幕 → OCR识别 → 自动翻译",
            font=("Microsoft YaHei", 9),
            bg="#fafafa", fg="#999"
        ).pack(pady=(0, 20))

        # 状态显示
        status_frame = tk.Frame(main_frame, bg="#f0f0f0", relief="flat", bd=1)
        status_frame.pack(fill="x", pady=(0, 15))

        tk.Label(
            status_frame, text="状态",
            font=("Microsoft YaHei", 10),
            bg="#f0f0f0", fg="#666"
        ).pack(side="left", padx=(12, 5), pady=8)

        self.status_var = tk.StringVar(value="🟢 监听中")
        tk.Label(
            status_frame, textvariable=self.status_var,
            font=("Microsoft YaHei", 10, "bold"),
            bg="#f0f0f0", fg="#2E7D32"
        ).pack(side="left", pady=8)

        # 快捷键显示
        hotkey_frame = tk.Frame(main_frame, bg="#f0f0f0", relief="flat", bd=1)
        hotkey_frame.pack(fill="x", pady=(0, 20))

        tk.Label(
            hotkey_frame, text="快捷键",
            font=("Microsoft YaHei", 10),
            bg="#f0f0f0", fg="#666"
        ).pack(side="left", padx=(12, 5), pady=8)

        self.hotkey_var = tk.StringVar(value=self.config.hotkey_display)
        tk.Label(
            hotkey_frame, textvariable=self.hotkey_var,
            font=("Consolas", 11, "bold"),
            bg="#e0e0e0", fg="#1565C0",
            relief="sunken", bd=1, padx=8, pady=2
        ).pack(side="left", pady=8)

        # 浮窗停留时间
        duration_frame = tk.Frame(main_frame, bg="#f0f0f0", relief="flat", bd=1)
        duration_frame.pack(fill="x", pady=(0, 15))

        tk.Label(
            duration_frame, text="浮窗停留",
            font=("Microsoft YaHei", 10),
            bg="#f0f0f0", fg="#666"
        ).pack(side="left", padx=(12, 5), pady=8)

        self.duration_var = tk.DoubleVar(value=self.config.toast_duration)
        self.duration_label_var = tk.StringVar(
            value=f"{self.config.toast_duration:.1f} 秒"
        )

        self.duration_scale = tk.Scale(
            duration_frame,
            from_=1.0, to=10.0, resolution=0.5,
            orient="horizontal",
            variable=self.duration_var,
            command=self._on_duration_changed,
            bg="#f0f0f0", fg="#333",
            highlightthickness=0,
            length=160,
        )
        self.duration_scale.pack(side="left", padx=(5, 8), pady=2)

        tk.Label(
            duration_frame, textvariable=self.duration_label_var,
            font=("Microsoft YaHei", 10, "bold"),
            bg="#f0f0f0", fg="#1565C0",
            width=8, anchor="w"
        ).pack(side="left", pady=8)

        # 调试截图开关
        debug_frame = tk.Frame(main_frame, bg="#fafafa")
        debug_frame.pack(fill="x", pady=(0, 12))

        self.debug_var = tk.BooleanVar(value=self.config.save_debug_images)
        self.debug_cb = tk.Checkbutton(
            debug_frame,
            text="保存调试截图到桌面 _ocr_debug 文件夹",
            variable=self.debug_var,
            command=self._on_debug_toggled,
            font=("Microsoft YaHei", 9),
            bg="#fafafa", fg="#555",
            activebackground="#fafafa",
            selectcolor="#fafafa",
            cursor="hand2",
        )
        self.debug_cb.pack(side="left", padx=(8, 0))

        # 按钮行
        btn_frame = tk.Frame(main_frame, bg="#fafafa")
        btn_frame.pack(fill="x")

        btn_style = {"font": ("Microsoft YaHei", 10), "relief": "flat",
                     "cursor": "hand2", "bd": 0, "padx": 12, "pady": 6}

        self.start_btn = tk.Button(
            btn_frame, text="▶ 开始监听", bg="#4CAF50", fg="white",
            command=self._start_listening, **btn_style
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = tk.Button(
            btn_frame, text="⏸ 暂停监听", bg="#FF9800", fg="white",
            command=self._toggle_pause, **btn_style
        )
        self.pause_btn.pack(side="left", padx=(0, 8))

        self.set_btn = tk.Button(
            btn_frame, text="⚙ 设置快捷键", bg="#2196F3", fg="white",
            command=self._open_hotkey_settings, **btn_style
        )
        self.set_btn.pack(side="left")

    # ── 系统托盘 ──────────────────────────────────────────────────

    def _create_tray_image(self):
        """生成 64x64 托盘图标"""
        img = Image.new("RGBA", (64, 64), (37, 99, 235, 255))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("seguiemj.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
        draw.text((12, 8), "📷", font=font, fill=(255, 255, 255, 255))
        return img
    def _run_tray(self):
        """使用 pystray, 左键单击显示主界面"""
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("🪟 显示主界面", lambda: self.root.after(0, self._show_window)),
            pystray.MenuItem(
                "⏸ 暂停/继续",
                lambda: self.root.after(0, self._toggle_pause),
                checked=lambda item: self._paused
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📖 使用说明", lambda: self.root.after(0, self._show_about)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🚪 退出", lambda: self.root.after(0, self._quit_app)),
        )
        icon = pystray.Icon(
            "desktop_translator",
            self._create_tray_image(),
            "桌面翻译工具",
            menu,
            on_click=lambda icon, item: self.root.after(0, self._show_window)
        )
        self._tray_icon = icon
        icon.run()
    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _show_about(self):
        """显示使用说明对话框"""
        tk.messagebox.showinfo("使用说明",
            "快捷键: Ctrl + Shift + S\n\n"
            "1. 按下快捷键进入框选模式\n"
            "2. 鼠标拖拽选择包含英文的区域\n"
            "3. 松开鼠标后自动 OCR 识别并翻译\n"
            "4. 结果显示在浮窗中\n"
            "5. 按 Esc 取消框选\n\n"
            "翻译源: 百度 → 有道 → 必应 (国内可用, 无需代理)\n"
            "浮窗支持拖拽移动。\n"
            "左键单击托盘图标显示主界面。")

    def _minimize_to_tray(self):
        self.root.withdraw()

    # ── 快捷键监听 ────────────────────────────────────────────────

    def _start_hotkey_listener(self):
        """启动/重启 pynput GlobalHotKeys 监听器 (比手动追踪键位更可靠)"""
        self._stop_hotkey_listener()
        self._paused = False
        self._update_status()

        mods = self.config.hotkey_modifiers
        char = self.config.hotkey_char
        target_char = char.lower() if char else "s"

        # 构建 pynput GlobalHotKeys 格式: <ctrl>+<shift>+s
        # GlobalHotKeys 内部使用确定性的状态机, 不会受按键丢失影响
        parts = [f'<{m}>' for m in mods]
        parts.append(target_char)
        hotkey_str = '+'.join(parts)

        def on_trigger():
            """在 listener 线程中触发, 通过 after() 调度到主线程"""
            if not self._paused:
                self.root.after(0, self._trigger_capture)

        self._hotkey_listener = pynput_kb.GlobalHotKeys({
            hotkey_str: on_trigger,
        })
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    def _stop_hotkey_listener(self):
        if self._hotkey_listener and self._hotkey_listener.running:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    # ── 截图触发 ─────────────────────────────────────────────────

    def _trigger_capture(self):
        if self._processing:
            return
        self._processing = True
        self.overlay = ScreenOverlay(self._on_captured, config=self.config)
        self.overlay.show()

    def _on_captured(self, pil_img: Image.Image):
        self._processing = False
        # 后台处理
        threading.Thread(target=self._process, args=(pil_img,), daemon=True).start()

    def _process(self, pil_img: Image.Image):
        """OCR → 翻译 → 显示"""
        try:
            # OCR
            text = OCRService.recognize(pil_img)
            text = text.strip()
            if not text:
                self.root.after(0, lambda: self.toast.show(
                    "未识别到文字",
                    "请选择包含文字的区域重试"
                ))
                return

            # 翻译
            translation = TranslatorService.translate(text, cache=self.cache)

            # 显示
            self.root.after(0, lambda: self.toast.show(text, translation))

            # 持久化缓存
            try:
                self.cache.save()
            except Exception:
                pass

        except ImportError as e:
            pkg = str(e).split("'")[1] if "'" in str(e) else "未知"
            self.root.after(0, lambda: self.toast.show(
                "缺少依赖", f"请安装: pip install {pkg}"
            ))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            err_msg = f"处理出错: {tb[:80]}"
            self.root.after(0, lambda: self.toast.show(
                "处理出错", err_msg
            ))

    # ── 按钮回调 ─────────────────────────────────────────────────

    def _start_listening(self):
        self._start_hotkey_listener()
        self._update_status()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._stop_hotkey_listener()
        else:
            self._start_hotkey_listener()
        self._update_status()
        # 更新托盘菜单 (下次打开时生效)
        self._reload_tray()

    def _open_hotkey_settings(self):
        HotkeyCaptureWindow(self.root, self._on_hotkey_changed)

    def _on_hotkey_changed(self, modifiers, char, display):
        self.config.hotkey_modifiers = modifiers
        self.config.hotkey_char = char
        self.config.hotkey_display = display
        self.config.save()
        self.hotkey_var.set(display)
        self._start_hotkey_listener()

    def _on_duration_changed(self, value):
        """滑块值变化时立即写入 config.json 并更新标签"""
        val = float(value)
        self.config.toast_duration = val
        self.config.save()
        self.duration_label_var.set(f"{val:.1f} 秒")

    def _on_debug_toggled(self):
        """复选框切换时立即写入 config.json"""
        self.config.save_debug_images = self.debug_var.get()
        self.config.save()

    def _update_status(self):
        if self._paused:
            self.status_var.set("🟡 已暂停")
        else:
            self.status_var.set("🟢 监听中")
    def _reload_tray(self):
        """重启托盘图标以更新菜单状态"""
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self._tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        self._tray_thread.start()
    def _quit_app(self):
        self._stop_hotkey_listener()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        try:
            self.cache.save()
        except Exception:
            pass
        self.root.quit()

    def self_test(self):
        """自测流程：生成测试图片 → OCR → 翻译 → 打印结果和耗时"""
        import io
        from PIL import ImageDraw, ImageFont
        import time

        print("=" * 50)
        print("    自测模式 — 模拟截图翻译全流程")
        print("=" * 50)

        # Step 1: 生成测试图片
        print("[1/3] 生成测试图片 ...", end=" ", flush=True)
        t0 = time.time()
        img = Image.new("RGB", (400, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
        draw.text((20, 20), "Hello World", fill=(0, 0, 0), font=font)
        t1 = time.time()
        print(f"完成 ({t1-t0:.3f}s)")

        # Step 2: OCR 识别
        print("[2/3] Tesseract OCR 识别 ...", end=" ", flush=True)
        t0 = time.time()
        text = OCRService.recognize(img)
        t1 = time.time()
        print(f"完成 ({t1-t0:.3f}s)")
        print(f"      识别结果: {text!r}")

        if not text.strip():
            print("!!! OCR 未识别到文字，请检查 Tesseract 是否安装正确")
            return

        # Step 3: 翻译
        print("[3/3] 翻译 (百度/有道/必应) ...", end=" ", flush=True)
        t0 = time.time()
        try:
            translation = TranslatorService.translate(text)
            t1 = time.time()
            print(f"完成 ({t1-t0:.3f}s)")
            print(f"      翻译结果: {translation}")
        except Exception as e:
            t1 = time.time()
            print(f"失败 ({t1-t0:.3f}s)")
            print(f"      错误: {e}")

        print("\n" + "=" * 50)
        print("    自测结束")
        print("=" * 50)

    def run(self):
        self.root.mainloop()


# ====================================================================
# 入口
# ====================================================================

if __name__ == "__main__":
    if "--test" in sys.argv:
        app = TranslatorApp()
        app.self_test()
    else:
        app = TranslatorApp()
        app.run()

