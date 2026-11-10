#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小猫桌宠 CatPet
- 透明无边框窗口、始终置顶
- 单击换照片 / 双击冒爱心+说话 / 拖动移动 / 右键菜单
- 喂食 + 饱腹度养成
- 拖动晃动 + 松手抛出（重力落地）
- 跟随鼠标横移
"""
import os
import sys
import math
import random
import time
import tkinter as tk

APP_TITLE = "小猫桌宠"
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SAVE_FILE = os.path.join(os.path.expanduser("~"), ".catpet_state.json")

FRAME_MS = 30           # 主循环间隔（物理/跟随鼠标需要更细腻）

# ---- 台词：按心情分组（淘气吐槽风）----
SPEECHES = ["喵", "人，干嘛", "求撸", "睡觉中"]

SPEECH_FULL = [
    "朕吃饱了", "嗝～", "这鱼干还行", "勉强给你摸一下",
    "我胖了吗？没有", "再看就收费了",
]
SPEECH_OK = [
    "喵", "人，干嘛", "求撸", "睡觉中", "摸头要排队的",
    "别烦我", "今天心情不错", "你又在摸鱼？",
]
SPEECH_HUNGRY = [
    "饿了", "猫粮呢？", "人，饭呢", "你是忘了我吗",
    "就这？", "我不行了…", "饿到没力气理你",
]
SPEECH_STARVING = [
    "要饿死了", "救命", "你这个不负责的人",
    "我恨你（小声）", "算了，我自己睡",
]
SPEECH_DRAGGED = ["放我下来", "晕", "别晃了！", "干嘛呀", "救命啊"]
SPEECH_THROWN = ["哇啊——", "飞了", "刺激！", "我还会回来的"]

# 爱心颜色（随机挑选）
HEART_COLORS = ["#ff6b81", "#ff8fab", "#ff477e", "#ffa8b6"]

# 气泡框配色
BUBBLE_BG = "#fffdf7"
BUBBLE_BORDER = "#ffc9d4"
BUBBLE_FG = "#5a4a42"

# ---- 日程提醒 ----
REMIND_BORDER = "#8ecae6"     # 提醒气泡边框（区别于普通气泡的粉色）
REMIND_BG = "#f4fbff"
REMIND_FG = "#20506b"
REMIND_DURATION = 6000        # 提醒气泡停留 6 秒

# 首次启动默认带一条提醒
DEFAULT_REMINDERS = [
    {
        "id": "drink",
        "name": "喝水",
        "text": "该喝水啦，人",
        "type": "interval",     # interval=每隔多久 / daily=每天几点
        "minutes": 60,
        "time": "09:00",
        "enabled": True,
        "next_at": None,
    }
]

REMIND_WORDS = [
    "该喝水啦，人", "水，喝了吗", "起来动一下，顺便喝口水",
    "你的水杯在等你", "又要脱皮了，快喝水",
]

# ---- 养成/物理参数 ----
HUNGER_DECAY_SEC = 90      # 每 90 秒掉 1 点饱腹度
FEED_AMOUNT = 35           # 一条小鱼干回复的饱腹度
GRAVITY = 2.2
FRICTION = 0.86
FOLLOW_FACTOR = 0.16       # 跟随鼠标的横向插值系数
FOLLOW_MAX_STEP = 2.4      # 跟随时每帧最大位移
TICK_MS = 30
PHYSICS_MS = 16


def load_frames(folder):
    """从素材包目录加载 PNG 序列；若只有一个 GIF 则加载其所有帧。"""
    from PIL import Image, ImageTk, ImageSequence
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".png", ".gif")))
    gifs = [f for f in files if f.lower().endswith(".gif")]
    frames = {}
    if gifs:
        for g in gifs:
            name = os.path.splitext(g)[0]
            im = Image.open(os.path.join(folder, g))
            seq = [f.copy().convert("RGBA") for f in ImageSequence.Iterator(im)]
            frames[name] = seq
    else:
        for f in files:
            name = os.path.splitext(f)[0].rsplit("_", 1)[0]
            im = Image.open(os.path.join(folder, f)).convert("RGBA")
            frames.setdefault(name, []).append(im)
    return frames


class Fish(tk.Toplevel):
    """小鱼干：可拖动的小零食，拖到猫身上就喂它。"""

    def __init__(self, pet, x, y):
        super().__init__(pet.root)
        self.pet = pet
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=_trans_bg())
        _apply_transparency(self)

        # 用 Canvas 画一条小鱼干，不依赖 emoji 字体
        S = 44
        cv = tk.Canvas(self, width=S, height=S, bg=_trans_bg(), highlightthickness=0)
        cv.pack()
        body = "#7ec8e3"
        cv.create_oval(4, 16, 30, 32, fill=body, outline="#4a9bc4", width=2)
        cv.create_polygon(28, 24, 42, 14, 42, 34, fill=body, outline="#4a9bc4", width=2)
        cv.create_oval(10, 20, 15, 25, fill="#1c3d52", outline="")
        cv.bind("<ButtonPress-1>", self._press)
        cv.bind("<B1-Motion>", self._drag)
        cv.bind("<ButtonRelease-1>", self._release)
        self.geometry(f"+{x}+{y}")
        self.after(20000, self._timeout)   # 20 秒不吃就消失

    def _press(self, e):
        self._off = (e.x, e.y)
        self.lift()

    def _drag(self, e):
        x = self.winfo_pointerx() - self._off[0]
        y = self.winfo_pointery() - self._off[1]
        self.geometry(f"+{x}+{y}")

    def _release(self, e):
        # 判断是否落在猫身上
        px, py = self.pet.root.winfo_x(), self.pet.root.winfo_y()
        pw = self.pet.root.winfo_width()
        ph = self.pet.root.winfo_height()
        cx, cy = self.winfo_pointerx(), self.winfo_pointery()
        if px - 30 <= cx <= px + pw + 30 and py - 30 <= cy <= py + ph + 30:
            self.pet.feed()
            self.destroy()
        else:
            # 没喂到，掉到屏幕底部一点点
            self._fall()

    def _fall(self):
        sh = self.winfo_screenheight()
        y = self.winfo_y()
        if y + 40 < sh - 120:
            self.geometry(f"+{self.winfo_x()}+{y + 12}")
            self.after(16, self._fall)

    def _timeout(self):
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass


def _trans_bg():
    """透明窗口该用的背景色。

    macOS 的 -transparent 要求背景是带透明度的颜色（systemTransparent）；
    Windows 用 -transparentcolor 抠掉 black；其余系统只能实色背景。
    """
    if sys.platform == "darwin":
        return "systemTransparent"
    return "black"


def _apply_transparency(win, key="black"):
    """把窗口的指定颜色变透明。

    Windows 用 -transparentcolor（key 是要抠掉的颜色），
    macOS 用 -transparent（参数是布尔值，背景需为 systemTransparent）。
    失败也不影响运行，只是背景色会露出来。
    """
    if sys.platform == "win32":
        try:
            win.attributes("-transparentcolor", key)
            return True
        except tk.TclError:
            return False
    if sys.platform == "darwin":
        try:
            win.attributes("-transparent", True)
            return True
        except tk.TclError:
            return False
    return False


def parse_dt(date_str, time_str):
    """把 '2026-11-15' + '14:30' 解析成本地时间戳；失败返回 None。

    日期允许 2026-11-15 / 2026/11/15 / 11-15（省年份则按今年）。
    """
    ds = str(date_str or "").strip().replace("/", "-").replace(".", "-")
    ts = str(time_str or "").strip().replace("：", ":")
    try:
        parts = [int(x) for x in ds.split("-") if x.strip() != ""]
        if len(parts) == 2:                      # 11-15 -> 补今年
            parts = [time.localtime().tm_year] + parts
        if len(parts) != 3:
            return None
        y, mo, d = parts
        tp = ts.split(":")
        hh, mm = int(tp[0]), int(tp[1])
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        t = time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1))
        # mktime 会把 2 月 31 日顺延成 3 月 3 日，反查一次防止假日期通过
        lt = time.localtime(t)
        if (lt.tm_year, lt.tm_mon, lt.tm_mday) != (y, mo, d):
            return None
        return t
    except (ValueError, IndexError, TypeError, OverflowError, OSError):
        return None


def day_offset_text(ts):
    """返回「今天 / 明天 / 3 天后」这类相对描述，让一次性提醒更直观。"""
    try:
        lt = time.localtime(ts)
        today = time.localtime()
        d0 = time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, -1))
        d1 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        n = int(round((d1 - d0) / 86400))
    except (ValueError, OverflowError, OSError):
        return ""
    if n == 0:
        return "今天"
    if n == 1:
        return "明天"
    if n == 2:
        return "后天"
    if n > 0:
        return f"{n} 天后"
    return f"{-n} 天前"


def _parse_clock(text):
    """解析 HH:MM，返回 (hh, mm)；失败返回 None。"""
    try:
        parts = str(text or "").strip().replace("：", ":").split(":")
        hh, mm = int(parts[0]), int(parts[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, IndexError, TypeError):
        pass
    return None


# 跨平台中文字体：Windows 微软雅黑 / macOS 苹方 / Linux 思源黑体
if sys.platform == "darwin":
    _CJK_FONT = "PingFang SC"
elif sys.platform.startswith("linux"):
    _CJK_FONT = "Noto Sans CJK SC"
else:
    _CJK_FONT = "Microsoft YaHei UI"
UI_FONT = (_CJK_FONT, 10)
_HEART_FONT = "Apple Symbols" if sys.platform == "darwin" else "Segoe UI Emoji"
_ARROW_FONT = _CJK_FONT if sys.platform != "win32" else "Segoe UI"




class ReminderDialog(tk.Toplevel):
    """日程设置窗口：增删提醒、切换启用、调整间隔/时间。"""

    def __init__(self, pet):
        super().__init__(pet.root)
        self.pet = pet
        self.title("小猫提醒 · 日程设置")
        self.configure(bg="#f7f7f9")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)

        top = tk.Frame(self, bg="#f7f7f9")
        top.pack(fill="x", padx=14, pady=(10, 4))
        self.on_var = tk.BooleanVar(value=pet.reminder_on)
        tk.Checkbutton(top, text="启用所有提醒", variable=self.on_var,
                       command=self._toggle_on, bg="#f7f7f9",
                       font=UI_FONT, anchor="w").pack(side="left")
        self.clock = tk.Label(top, text="", bg="#f7f7f9", fg="#7a8794", font=UI_FONT)
        self.clock.pack(side="right")
        self._clock_job = None
        self._tick_clock()

        box = tk.Frame(self, bg="#f7f7f9")
        box.pack(fill="both", expand=True, padx=14)
        self.listbox = tk.Listbox(box, height=6, font=UI_FONT, activestyle="none",
                                  selectmode="browse", bd=1, relief="solid",
                                  highlightthickness=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(box, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<Double-Button-1>", lambda e: self._toggle_selected())

        btns = tk.Frame(self, bg="#f7f7f9")
        btns.pack(fill="x", padx=14, pady=6)
        tk.Button(btns, text="启用/停用", font=UI_FONT,
                  command=self._toggle_selected).pack(side="left")
        tk.Button(btns, text="删除", font=UI_FONT,
                  command=self._delete_selected).pack(side="left", padx=6)
        tk.Button(btns, text="恢复喝水提醒", font=UI_FONT,
                  command=self._restore_drink).pack(side="left")

        add = tk.LabelFrame(self, text=" 添加提醒 ", bg="#f7f7f9", fg="#444", font=UI_FONT)
        add.pack(fill="x", padx=14, pady=(2, 12))

        row1 = tk.Frame(add, bg="#f7f7f9")
        row1.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(row1, text="提醒内容", bg="#f7f7f9", font=UI_FONT).pack(side="left")
        self.name_var = tk.StringVar(value="喝水")
        tk.Entry(row1, textvariable=self.name_var, font=UI_FONT,
                 width=24).pack(side="left", padx=8)

        self.kind = tk.StringVar(value="interval")
        row2 = tk.Frame(add, bg="#f7f7f9")
        row2.pack(fill="x", padx=10, pady=2)
        tk.Radiobutton(row2, text="每隔", variable=self.kind, value="interval",
                       bg="#f7f7f9", font=UI_FONT).pack(side="left")
        self.min_var = tk.StringVar(value="60")
        tk.Spinbox(row2, from_=1, to=1440, textvariable=self.min_var,
                   width=5, font=UI_FONT).pack(side="left", padx=4)
        tk.Label(row2, text="分钟", bg="#f7f7f9", font=UI_FONT).pack(side="left")

        row3 = tk.Frame(add, bg="#f7f7f9")
        row3.pack(fill="x", padx=10, pady=2)
        tk.Radiobutton(row3, text="每天", variable=self.kind, value="daily",
                       bg="#f7f7f9", font=UI_FONT).pack(side="left")
        self.time_var = tk.StringVar(value="09:00")
        tk.Entry(row3, textvariable=self.time_var, width=7,
                 font=UI_FONT).pack(side="left", padx=4)
        tk.Label(row3, text="时:分（24 小时制）", bg="#f7f7f9",
                 font=UI_FONT, fg="#888").pack(side="left")

        # 仅一次的固定日期（默认给一小时后的现实时间）
        soon = time.localtime(time.time() + 3600)
        row4 = tk.Frame(add, bg="#f7f7f9")
        row4.pack(fill="x", padx=10, pady=(2, 6))
        tk.Radiobutton(row4, text="仅一次", variable=self.kind, value="once",
                       bg="#f7f7f9", font=UI_FONT).pack(side="left")
        self.once_date_var = tk.StringVar(value=time.strftime("%Y-%m-%d", soon))
        tk.Entry(row4, textvariable=self.once_date_var, width=11,
                 font=UI_FONT).pack(side="left", padx=4)
        self.once_time_var = tk.StringVar(value=time.strftime("%H:%M", soon))
        tk.Entry(row4, textvariable=self.once_time_var, width=7,
                 font=UI_FONT).pack(side="left")
        tk.Label(row4, text="日期 + 时间（只提醒这一次）", bg="#f7f7f9",
                 font=UI_FONT, fg="#888").pack(side="left", padx=4)

        self.tip = tk.Label(add, text="", bg="#f7f7f9", fg="#c0392b", font=UI_FONT)
        self.tip.pack(fill="x", padx=10)

        tk.Button(add, text="添加到日程", font=UI_FONT, bg="#8ecae6", fg="#12384a",
                  relief="flat", padx=14, pady=4,
                  command=self._add).pack(pady=(2, 12))

        self._refresh()
        # 居中到屏幕
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

    # ---- 列表 ----
    def _refresh(self):
        self.listbox.delete(0, "end")
        for r in self.pet.reminders:
            mark = "✓" if r.get("enabled", True) else "✗"
            extra = ""
            nt = r.get("next_at")
            if r.get("enabled", True) and not r.get("done") and isinstance(nt, (int, float)):
                if r.get("type") == "once":
                    extra = "  到点 " + time.strftime("%m-%d %H:%M", time.localtime(nt))
                else:
                    extra = "  下次 " + time.strftime("%H:%M", time.localtime(nt))
            self.listbox.insert(
                "end", f" {mark} {r.get('name', '提醒')}（{CatPet._reminder_desc(r)}）{extra}")

    def _selected(self):
        sel = self.listbox.curselection()
        if not sel:
            self.tip.configure(text="先在上面选中一条提醒")
            return None
        i = sel[0]
        if i >= len(self.pet.reminders):
            return None
        return i

    def _toggle_on(self):
        self.pet.reminder_on = bool(self.on_var.get())
        self.pet._save_state()

    def _toggle_selected(self):
        i = self._selected()
        if i is None:
            return
        r = self.pet.reminders[i]
        if r.get("enabled", True):
            r["enabled"] = False
            self.tip.configure(text="")
        else:
            if r.get("type") == "once":
                nxt = self.pet._next_time_for(r)
                if nxt is None:
                    self.tip.configure(text="这条的时间已经过了，要重新提醒请改成将来的时间再添加")
                    return
                r["next_at"] = nxt
            else:
                r["next_at"] = self.pet._next_time_for(r)
            r["done"] = False
            r["enabled"] = True
            self.tip.configure(text="")
        self._refresh()
        self.pet._save_state()

    def _delete_selected(self):
        i = self._selected()
        if i is None:
            return
        name = self.pet.reminders[i].get("name", "提醒")
        del self.pet.reminders[i]
        self.tip.configure(text=f"已删除「{name}」")
        self._refresh()
        self.pet._save_state()

    def _restore_drink(self):
        import copy
        if any(r.get("id") == "drink" for r in self.pet.reminders):
            self.tip.configure(text="喝水提醒已经在列表里了")
            return
        d = copy.deepcopy(DEFAULT_REMINDERS[0])
        d["next_at"] = self.pet._next_time_for(d)
        self.pet.reminders.append(d)
        self.tip.configure(text="已加回「喝水（每 1 小时）」")
        self._refresh()
        self.pet._save_state()

    def _add(self):
        name = (self.name_var.get() or "").strip()
        if not name:
            self.tip.configure(text="提醒内容不能为空")
            return
        r = {
            "id": f"r{int(time.time() * 1000) % 10**9}",
            "name": name,
            "text": name,
            "type": self.kind.get(),
            "enabled": True,
            "next_at": None,
        }
        if r["type"] == "daily":
            hm = _parse_clock(self.time_var.get())
            if hm is None:
                self.tip.configure(text="时间格式要写成 09:30 这样")
                return
            r["time"] = f"{hm[0]:02d}:{hm[1]:02d}"
            r["minutes"] = 60
        elif r["type"] == "once":
            d = (self.once_date_var.get() or "").strip()
            t = (self.once_time_var.get() or "").strip()
            ts = parse_dt(d, t)
            if ts is None:
                self.tip.configure(text="日期/时间不对，日期写 2026-11-15，时间写 14:30")
                return
            if ts <= time.time() + 30:
                self.tip.configure(text="这个时间已经过了，请选一个将来的时间")
                return
            lt = time.localtime(ts)
            r["date"] = time.strftime("%Y-%m-%d", lt)
            r["time"] = time.strftime("%H:%M", lt)
            r["minutes"] = 60
            r["done"] = False
            r["next_at"] = ts
        else:
            try:
                m = int(float(self.min_var.get()))
                if m < 1:
                    raise ValueError
            except (ValueError, TypeError):
                self.tip.configure(text="间隔分钟要填大于 0 的数字")
                return
            r["minutes"] = min(m, 1440)
            r["time"] = "09:00"
        if r["type"] != "once":
            r["next_at"] = self.pet._next_time_for(r)
        self.pet.reminders.append(r)
        if r["type"] == "once":
            off = day_offset_text(r["next_at"])
            self.tip.configure(
                text=f"已添加「{name}」：{r['date']} {r['time']}（{off}）只提醒这一次")
        else:
            self.tip.configure(text=f"已添加「{name}」，{CatPet._reminder_desc(r)}提醒")
        self._refresh()
        self.pet._save_state()

    def _tick_clock(self):
        """顶栏显示现实时间，每秒刷新。"""
        try:
            self.clock.configure(text="现在 " + time.strftime("%Y-%m-%d %H:%M:%S"))
            self._clock_job = self.after(1000, self._tick_clock)
        except tk.TclError:
            self._clock_job = None

    def _close(self):
        if self._clock_job is not None:
            try:
                self.after_cancel(self._clock_job)
            except tk.TclError:
                pass
            self._clock_job = None
        try:
            self.pet._bg_windows.remove(self)
        except (ValueError, AttributeError):
            pass
        self.destroy()


class CatPet:
    # 单击切换照片时按这个顺序循环
    ACTIONS = ["idle", "rest", "stretch", "walk", "blink", "happy"]

    def __init__(self, root):
        self.root = root
        self.scale = 1.0
        self.pack_name = "cat"
        self.pinned = None
        self.dragging = False
        self.drag_off = (0, 0)
        self.action = "idle"
        self.idx = 0
        self._pending_click = None
        self._bubble = None
        self._menu = None

        # ---- 养成交互状态 ----
        self.hunger = 100.0          # 饱腹度 0~100
        self.last_hunger_tick = time.time()
        self.follow_mouse = False    # 是否跟着鼠标
        self._last_mouse_x = None

        # ---- 日程提醒 / 自启动 ----
        self.reminders = []          # 提醒列表（_load_state 里填充）
        self.reminder_on = True      # 提醒总开关
        self.autostart = False       # 开机自启动状态
        self._bubble_queue = []      # 气泡排队（避免同时多个提醒互相覆盖）
        self._bg_windows = []        # 设置窗口等附属窗口的引用

        # ---- 物理状态（抛出） ----
        self.vx = 0.0
        self.vy = 0.0
        self.airborne = False
        self._drag_history = []      # 记录拖动轨迹用于算甩出速度
        self._physics_job = None

        root.title(APP_TITLE)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=_trans_bg())

        _apply_transparency(root)
        try:
            root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

        self.label = tk.Label(root, bd=0, bg=_trans_bg())
        self.label.pack()

        self._bind_events()
        self.pack_name = self._pick_start_pack()
        self.frames = self._load_pack(self.pack_name)
        self._load_state()
        self._place_initial()
        self._tick()
        self._physics_loop()

    # ---------- 存档 ----------
    def _load_state(self):
        d = {}
        try:
            import json
            with open(SAVE_FILE, encoding="utf-8") as f:
                d = json.load(f)
            self.hunger = float(d.get("hunger", 100))
            # 离线期间也在饿
            elapsed = time.time() - float(d.get("ts", time.time()))
            self.hunger = max(0.0, self.hunger - elapsed / HUNGER_DECAY_SEC)
            saved_at = float(d.get("ts", time.time()))
            self.last_hunger_tick = time.time() - (time.time() - saved_at) % HUNGER_DECAY_SEC
        except (OSError, ValueError, KeyError, TypeError):
            self.hunger = 100.0
            self.last_hunger_tick = time.time()

        # 提醒列表：没有这个键说明是首次运行，装默认的喝水提醒
        raw = d.get("reminders") if isinstance(d, dict) else None
        if isinstance(raw, list):
            self.reminders = [r for r in raw if isinstance(r, dict) and r.get("id")]
        else:
            import copy
            self.reminders = copy.deepcopy(DEFAULT_REMINDERS)
        self.reminder_on = bool(d.get("reminder_on", True)) if isinstance(d, dict) else True
        # 启动时按注册表实际状态校准（用户可能在别处删过）
        self.autostart = self._autostart_enabled()

    def _save_state(self):
        try:
            import json
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "hunger": round(self.hunger, 2),
                    "ts": time.time(),
                    "reminders": self.reminders,
                    "reminder_on": self.reminder_on,
                }, f, ensure_ascii=False)
        except OSError:
            pass

    # ---------- 素材 ----------
    def _pack_dir(self, name):
        return os.path.join(ASSETS_DIR, name)

    def _available_packs(self):
        try:
            return sorted(d for d in os.listdir(ASSETS_DIR)
                          if os.path.isdir(self._pack_dir(d))
                          and os.listdir(self._pack_dir(d)))
        except OSError:
            return []

    def _pick_start_pack(self):
        packs = self._available_packs()
        if not packs:
            raise RuntimeError("assets 下没有找到任何角色素材包")
        if self.pinned in packs:
            return self.pinned
        if len(packs) == 1:
            return packs[0]
        weights = []
        for p in packs:
            w = 1.0
            wf = os.path.join(self._pack_dir(p), "weight.txt")
            if os.path.isfile(wf):
                try:
                    with open(wf, encoding="utf-8") as f:
                        w = max(0.0, float(f.read().strip() or 1))
                except (ValueError, OSError):
                    w = 1.0
            weights.append(w)
        if sum(weights) <= 0:
            weights = [1.0] * len(packs)
        return random.choices(packs, weights=weights, k=1)[0]

    def _load_pack(self, name):
        from PIL import Image, ImageTk
        raw = load_frames(self._pack_dir(name))
        self._raw = raw
        out = {}
        for act, seq in raw.items():
            imgs = []
            for im in seq:
                if self.scale != 1.0:
                    im = im.resize((max(1, int(im.width * self.scale)),
                                    max(1, int(im.height * self.scale))),
                                   Image.LANCZOS)
                imgs.append(ImageTk.PhotoImage(im))
            out[act] = imgs
        return out

    def _reload_pack(self, name):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.pack_name = name
        self.frames = self._load_pack(name)
        if self.action not in self.frames:
            self.action = next(iter(self.frames))
        self.idx = 0
        f0 = self.frames[self.action][0]
        self.root.geometry(f"{f0.width()}x{f0.height()}+{x}+{y}")
        self.label.configure(image=f0)

    # ---------- 窗口 ----------
    def _place_initial(self):
        f0 = next(iter(self.frames.values()))[0]
        w, h = f0.width(), f0.height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{sw - w - 120}+{sh - h - 120}")

    # ---------- 主循环 ----------
    def _tick(self):
        self._decay_hunger()
        self._follow_watch()
        self._check_reminders()

        seq = self.frames.get(self.action)
        if not seq:
            self.action = next(iter(self.frames))
            seq = self.frames[self.action]
        self.label.configure(image=seq[0])
        self.root.after(TICK_MS, self._tick)

    def _decay_hunger(self):
        now = time.time()
        if now - self.last_hunger_tick >= HUNGER_DECAY_SEC:
            steps = int((now - self.last_hunger_tick) // HUNGER_DECAY_SEC)
            self.hunger = max(0.0, self.hunger - steps)
            self.last_hunger_tick += steps * HUNGER_DECAY_SEC
            # 饿了会主动抱怨（有概率）
            if self.hunger < 25 and random.random() < 0.35:
                self._show_bubble(self._hungry_line())

    def _hungry_line(self):
        if self.hunger < 12:
            return random.choice(SPEECH_STARVING)
        if self.hunger < 40:
            return random.choice(SPEECH_HUNGRY)
        if self.hunger > 88:
            return random.choice(SPEECH_FULL)
        return random.choice(SPEECH_OK)

    # ---------- 跟随鼠标 ----------
    def _follow_watch(self):
        if not self.follow_mouse or self.dragging or self.airborne:
            return
        mx = self.root.winfo_pointerx()
        if self._last_mouse_x is None:
            self._last_mouse_x = mx
            return
        dx = mx - self._last_mouse_x
        # 只在鼠标明显移动时才反应，避免抖动
        if abs(dx) < 6:
            return
        self._last_mouse_x = mx

        cx = self.root.winfo_x() + self.root.winfo_width() // 2
        diff = mx - cx
        # 保持一点距离，太近就不动
        if abs(diff) < 60:
            return
        step = max(-FOLLOW_MAX_STEP, min(FOLLOW_MAX_STEP, diff * FOLLOW_FACTOR))
        nx = self.root.winfo_x() + int(step)
        sw = self.root.winfo_screenwidth()
        w = self.root.winfo_width()
        nx = max(0, min(nx, sw - w))
        self.root.geometry(f"+{nx}+{self.root.winfo_y()}")

    # ---------- 物理：抛出与落地 ----------
    def _physics_loop(self):
        if self.airborne:
            self._apply_physics()
        self._physics_job = self.root.after(PHYSICS_MS, self._physics_loop)

    def _apply_physics(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = self.root.winfo_width(), self.root.winfo_height()

        self.vy += GRAVITY
        x = self.root.winfo_x() + int(self.vx)
        y = self.root.winfo_y() + int(self.vy)

        # 左右撞墙反弹
        if x < 0:
            x = 0
            self.vx = -self.vx * 0.6
        elif x > sw - w:
            x = sw - w
            self.vx = -self.vx * 0.6

        ground = sh - h
        landed = False
        if y >= ground:
            y = ground
            if abs(self.vy) > 3.5:
                self.vy = -self.vy * FRICTION   # 弹一下
                self.vx *= 0.82
            else:
                self.vy = 0
                self.vx = 0
                landed = True

        self.root.geometry(f"+{x}+{y}")

        if landed:
            self.airborne = False
            self._drag_history.clear()
            self._show_bubble(random.choice(["哎哟", "摔死我了", "下次轻点", "还行，挺爽"]))

    def _throw(self, vx, vy):
        self.vx = vx
        self.vy = vy
        if abs(vx) > 2 or abs(vy) > 2:
            self.airborne = True
            if "happy" in self.frames:
                self.action = "happy"
            self._show_bubble(random.choice(SPEECH_THROWN))

    # ---------- 喂食 ----------
    def feed(self):
        self.hunger = min(100.0, self.hunger + FEED_AMOUNT)
        self._save_state()
        self._spawn_heart(count=2)
        self._show_bubble(random.choice(["好吃", "喵！", "还有吗", "这鱼干不错", "朕满意了"]))

    def _drop_fish(self, event=None):
        """在猫旁边生成一条小鱼干。"""
        f0 = self.frames[self.action][0]
        x = self.root.winfo_x() + f0.width() + 10
        y = self.root.winfo_y() + f0.height() // 2
        sw = self.root.winfo_screenwidth()
        if x > sw - 60:
            x = self.root.winfo_x() - 60
        Fish(self, x, y)

    # ---------- 照片切换 ----------
    def _next_photo(self):
        seqs = [a for a in self.ACTIONS if a in self.frames]
        if not seqs:
            return
        if self.action in seqs:
            i = (seqs.index(self.action) + 1) % len(seqs)
        else:
            i = 0
        self.action, self.idx = seqs[i], 0

    def _prev_photo(self):
        seqs = [a for a in self.ACTIONS if a in self.frames]
        if not seqs:
            return
        if self.action in seqs:
            i = (seqs.index(self.action) - 1) % len(seqs)
        else:
            i = 0
        self.action, self.idx = seqs[i], 0

    # ---------- 交互 ----------
    def _bind_events(self):
        w = self.label
        w.bind("<ButtonPress-1>", self._on_press)
        w.bind("<B1-Motion>", self._on_drag)
        w.bind("<ButtonRelease-1>", self._on_release)
        w.bind("<Double-Button-1>", self._on_pet)
        w.bind("<Button-3>", self._on_menu)

    def _on_press(self, e):
        self.dragging = False
        self.airborne = False
        self.drag_off = (e.x, e.y, self.root.winfo_x(), self.root.winfo_y())
        self._drag_history = [(time.time(), self.root.winfo_x(), self.root.winfo_y())]
        self._drag_moved = False

    def _on_drag(self, e):
        if not self.dragging:
            dx0 = abs(e.x - self.drag_off[0])
            dy0 = abs(e.y - self.drag_off[1])
            if dx0 < 3 and dy0 < 3:
                return
            self.dragging = True
            self._drag_moved = True

        dx = e.x - self.drag_off[0]
        dy = e.y - self.drag_off[1]
        nx = self.drag_off[2] + dx
        ny = self.drag_off[3] + dy
        self.root.geometry(f"+{nx}+{ny}")

        now = time.time()
        self._drag_history.append((now, nx, ny))
        # 只保留最近 120ms 的轨迹
        self._drag_history = [t for t in self._drag_history if now - t[0] < 0.12]

    def _on_release(self, e):
        if self.dragging:
            self.dragging = False
            # 算甩出速度
            hist = self._drag_history
            if len(hist) >= 2:
                t0, x0, y0 = hist[0]
                t1, x1, y1 = hist[-1]
                dt = max(t1 - t0, 0.016)
                vx = (x1 - x0) / dt * 0.012
                vy = (y1 - y0) / dt * 0.012
                if abs(vx) > 3 or abs(vy) > 3:
                    self._throw(vx, vy)
            self._drag_history.clear()
            return

        self._pending_click = self.root.after(240, self._do_single_click)

    def _do_single_click(self):
        self._pending_click = None
        self._next_photo()

    def _on_pet(self, event=None):
        """双击：冒爱心 + 说话。"""
        if getattr(self, "_pending_click", None):
            self.root.after_cancel(self._pending_click)
            self._pending_click = None
        self._spawn_heart(count=3)
        self._show_bubble(self._hungry_line())

    # ---------- 爱心 ----------
    def _spawn_heart(self, count=1):
        f0 = self.frames[self.action][0]
        base_x = self.root.winfo_x() + f0.width() // 2
        base_y = self.root.winfo_y() - 10
        for i in range(count):
            heart = tk.Toplevel(self.root)
            heart.overrideredirect(True)
            heart.attributes("-topmost", True)
            heart.configure(bg=_trans_bg())
            _apply_transparency(heart)
            lbl = tk.Label(heart, text="♥", fg=random.choice(HEART_COLORS), bg=_trans_bg(),
                           font=(_HEART_FONT, int(random.randint(13, 20) * max(self.scale, 1))))
            lbl.pack()
            x = base_x + random.randint(-30, 30)
            heart.geometry(f"+{x}+{base_y}")
            self.root.after(i * 120, lambda h=heart, y=base_y, xx=x: self._float_heart(h, xx, y))

    def _float_heart(self, win, x, y):
        try:
            if not win.winfo_exists():
                return
            cur_y = win.winfo_y()
        except tk.TclError:
            return
        if cur_y < self.root.winfo_y() - 100:
            try:
                win.destroy()
            except tk.TclError:
                pass
            return
        nx = x + random.randint(-3, 3)
        try:
            win.geometry(f"+{nx}+{cur_y - 5}")
        except tk.TclError:
            return
        win.after(45, lambda: self._float_heart(win, nx, cur_y - 5))

    # ---------- 气泡 ----------
    def _show_bubble(self, text, duration=3000, accent=None):
        # 已有气泡时排队，避免提醒被别的话冲掉
        if getattr(self, "_bubble", None):
            if len(self._bubble_queue) < 4:
                self._bubble_queue.append((text, duration, accent))
            return

        border = accent or BUBBLE_BORDER
        bg = REMIND_BG if accent == REMIND_BORDER else BUBBLE_BG
        fg = REMIND_FG if accent == REMIND_BORDER else BUBBLE_FG

        f0 = self.frames[self.action][0]
        bubble = tk.Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.configure(bg=border)

        inner = tk.Frame(bubble, bg=bg, padx=10, pady=6)
        inner.pack(padx=2, pady=2)

        tk.Label(inner, text=text, bg=bg, fg=fg,
                 font=(_CJK_FONT, int(12 * max(self.scale, 0.85)), "bold"),
                 wraplength=220, justify="left").pack()

        tk.Label(bubble, text="▼", bg=border, fg=border,
                 font=(_ARROW_FONT, 10)).pack()

        bubble.update_idletasks()
        bw = bubble.winfo_reqwidth()
        bx = self.root.winfo_x() + f0.width() // 2 - bw // 2
        by = self.root.winfo_y() - bubble.winfo_reqheight() + 4
        sw = self.root.winfo_screenwidth()
        bx = max(0, min(bx, sw - bw))
        bubble.geometry(f"+{bx}+{max(0, by)}")
        self._bubble = bubble
        bubble.after(duration, lambda b=bubble: self._close_bubble(b))

    def _close_bubble(self, bubble):
        try:
            if bubble.winfo_exists():
                bubble.destroy()
        except tk.TclError:
            pass
        if getattr(self, "_bubble", None) is bubble:
            self._bubble = None
        # 有排队的气泡就接着弹
        if self._bubble_queue:
            text, dur, acc = self._bubble_queue.pop(0)
            self.root.after(150, lambda: self._show_bubble(text, dur, acc))

    def _say_random(self):
        self._show_bubble(random.choice(SPEECH_OK))

    # ---------- 日程提醒 ----------
    def _check_reminders(self):
        """主循环里每帧检查一次，到点就弹气泡。"""
        if not self.reminder_on:
            return
        now = time.time()
        fired = False
        for r in self.reminders:
            if not r.get("enabled", True):
                continue
            if r.get("type") == "once" and r.get("done"):
                continue                      # 一次性的，响过就算了
            nxt = r.get("next_at")
            if not isinstance(nxt, (int, float)):
                r["next_at"] = self._next_time_for(r, now)
                if r.get("type") == "once":
                    r["done"] = True          # 时间无效或已过期，收工
                    fired = True
                continue
            if now >= nxt:
                self._fire_reminder(r)
                if r.get("type") == "once":
                    r["done"] = True
                    r["next_at"] = None
                else:
                    r["next_at"] = self._next_time_for(r, now)
                fired = True
        if fired:
            self._save_state()

    def _next_time_for(self, r, now=None):
        """算下一次触发时间戳。返回 None 表示不会再触发（一次性已过期）。"""
        now = time.time() if now is None else now
        if r.get("type") == "once":
            t = parse_dt(r.get("date"), r.get("time"))
            if t is None or t <= now:
                return None
            return t
        if r.get("type") == "daily":
            hm = _parse_clock(r.get("time", "09:00")) or (9, 0)
            lt = time.localtime(now)
            target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                  hm[0], hm[1], 0, 0, 0, -1))
            if target <= now:
                target += 86400
            return target
        minutes = r.get("minutes", 60)
        try:
            minutes = max(1, int(minutes))
        except (ValueError, TypeError):
            minutes = 60
        return now + minutes * 60

    def _fire_reminder(self, r):
        text = r.get("text") or r.get("name") or "提醒"
        self._remind(text)
        # 提醒时顺便换个表情、冒颗爱心，别让它悄无声息
        if "happy" in self.frames:
            self.action = "happy"
        self._spawn_heart()

    def _remind(self, text):
        """用提醒专用样式弹气泡（蓝色边框、停留更久、排队不打架）。"""
        self._show_bubble(text, duration=REMIND_DURATION, accent=REMIND_BORDER)

    @staticmethod
    def _reminder_desc(r, verbose=False):
        if r.get("type") == "once":
            d = str(r.get("date", ""))
            t = str(r.get("time", ""))
            year = str(time.localtime().tm_year)
            if d.startswith(year + "-"):
                d = d[len(year) + 1:]          # 今年就省掉年份
            s = f"仅 {d} {t}".strip()
            if r.get("done"):
                s += "（已完成）"
            elif verbose:
                try:
                    ts = parse_dt(r.get("date"), r.get("time"))
                    off = day_offset_text(ts) if ts else ""
                except (ValueError, TypeError):
                    off = ""
                if off:
                    s += f"（{off}）"
            return s
        if r.get("type") == "daily":
            return f"每天 {r.get('time', '09:00')}"
        try:
            m = max(1, int(r.get("minutes", 60)))
        except (ValueError, TypeError):
            m = 60
        if m % 60 == 0:
            return f"每 {m // 60} 小时"
        return f"每 {m} 分钟"

    # ---------- 开机自启动（Windows 注册表） ----------
    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _RUN_NAME = "CatPet"

    def _autostart_cmd(self):
        """拼出开机要执行的命令行：打包成 exe 就指 exe，否则用 pythonw 跑脚本。"""
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        script = os.path.abspath(__file__)
        exe_dir = os.path.dirname(sys.executable)
        pyw = os.path.join(exe_dir, "pythonw.exe")
        runner = pyw if os.path.isfile(pyw) else sys.executable
        return f'"{runner}" "{script}"'

    def _autostart_enabled(self):
        if sys.platform != "win32":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY) as k:
                winreg.QueryValueEx(k, self._RUN_NAME)
            return True
        except (OSError, ImportError):
            return False

    def _set_autostart(self, on):
        if sys.platform != "win32":
            self._show_bubble("自启动只在 Windows 下有效")
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, self._RUN_NAME, 0, winreg.REG_SZ,
                                      self._autostart_cmd())
                else:
                    try:
                        winreg.DeleteValue(k, self._RUN_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as e:
            self._show_bubble(f"设置失败：{e}")
            return False
        self.autostart = on
        self._show_bubble("开机我自己会来" if on else "好，不自动来了")
        return True

    def _toggle_autostart(self):
        self._set_autostart(not self.autostart)

    def _open_reminders(self):
        """打开日程设置窗口（已经开着就提到前面）。"""
        for w in list(self._bg_windows):
            try:
                if w.winfo_exists():
                    w.deiconify()
                    w.lift()
                    w.focus_force()
                    return
            except tk.TclError:
                pass
        self._bg_windows.clear()
        try:
            dlg = ReminderDialog(self)
        except tk.TclError:
            return
        self._bg_windows.append(dlg)

    def _toggle_reminder_master(self):
        self.reminder_on = not self.reminder_on
        self._save_state()
        self._show_bubble("提醒开着呢" if self.reminder_on else "提醒先关掉")

    def _toggle_reminder_at(self, i):
        """菜单里快速开关某一条提醒。"""
        if not (0 <= i < len(self.reminders)):
            return
        r = self.reminders[i]
        name = r.get("name", "提醒")
        if r.get("enabled", True):
            r["enabled"] = False
            self._show_bubble(f"「{name}」关")
        else:
            if r.get("type") == "once":
                nxt = self._next_time_for(r)
                if nxt is None:
                    self._show_bubble(f"「{name}」的时间已经过了")
                    return
                r["next_at"] = nxt
            else:
                r["next_at"] = self._next_time_for(r)
            r["done"] = False
            r["enabled"] = True
            self._show_bubble(f"「{name}」开")
        self._save_state()

    # ---------- 右键菜单 ----------
    def _on_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0)

        size_menu = tk.Menu(menu, tearoff=0)
        for label, s in (("小", 0.7), ("中", 1.0), ("大", 1.5)):
            size_menu.add_command(label=label, command=lambda s=s: self._set_scale(s))
        menu.add_cascade(label="大小", menu=size_menu)

        packs = self._available_packs()
        if len(packs) > 1:
            pack_menu = tk.Menu(menu, tearoff=0)
            for p in packs:
                pack_menu.add_command(label=p, command=lambda p=p: self._reload_pack(p))
            menu.add_cascade(label="素材包", menu=pack_menu)

        menu.add_separator()
        menu.add_command(label="🐟 给它一条小鱼干", command=self._drop_fish)
        menu.add_command(label=f"（饱腹度 {int(self.hunger)}%）", state="disabled")
        menu.add_separator()
        menu.add_command(label="下一张照片", command=self._next_photo)
        menu.add_command(label="上一张照片", command=self._prev_photo)
        menu.add_command(label="说句话", command=self._say_random)
        if len(packs) > 1:
            menu.add_command(label="换一只猫", command=self._swap_pet)

        follow_label = ("✓ 跟着鼠标" if self.follow_mouse else "跟着鼠标")
        menu.add_command(label=follow_label, command=self._toggle_follow)

        menu.add_separator()
        # ---- 日程提醒 ----
        rem_menu = tk.Menu(menu, tearoff=0)
        state = "提醒中" if self.reminder_on else "已暂停"
        rem_menu.add_command(
            label=f"（共 {len(self.reminders)} 条 · {state}）", state="disabled")
        rem_menu.add_command(label="打开设置…", command=self._open_reminders)
        rem_menu.add_command(label="现在试弹一个", command=lambda: self._remind(
            random.choice(REMIND_WORDS)))
        rem_menu.add_separator()
        for i, r in enumerate(self.reminders):
            mark = "✓ " if r.get("enabled", True) else "　"
            rem_menu.add_command(
                label=f"{mark}{r.get('name', '提醒')}（{self._reminder_desc(r)}）",
                command=lambda i=i: self._toggle_reminder_at(i))
        if not self.reminders:
            rem_menu.add_command(label="（还没有提醒，去设置里加）", state="disabled")
        rem_menu.add_separator()
        rem_menu.add_command(
            label=("暂停全部提醒" if self.reminder_on else "恢复全部提醒"),
            command=self._toggle_reminder_master)
        menu.add_cascade(label="⏰ 日程提醒", menu=rem_menu)

        # ---- 开机自启动 ----
        if sys.platform == "win32":
            auto_label = "✓ 开机自启动" if self.autostart else "开机自启动"
            menu.add_command(label=auto_label, command=self._toggle_autostart)
        else:
            menu.add_command(label="开机自启动（仅 Windows）", state="disabled")

        menu.add_separator()
        menu.add_command(label="退出", command=self._quit)

        self._menu = menu
        try:
            menu.post(e.x_root, e.y_root)
        except tk.TclError:
            pass

    def _toggle_follow(self):
        self.follow_mouse = not self.follow_mouse
        self._last_mouse_x = None
        if self.follow_mouse:
            self._show_bubble("我跟着你咯")
        else:
            self._show_bubble("哼，不跟了")

    def _set_scale(self, s):
        self.scale = s
        self._reload_pack(self.pack_name)

    def _swap_pet(self):
        allp = self._available_packs()
        if len(allp) < 2:
            return
        cur = allp.index(self.pack_name) if self.pack_name in allp else -1
        self._reload_pack(allp[(cur + 1) % len(allp)])

    def _quit(self):
        self._save_state()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        root.withdraw()
        tk.messagebox.showerror(APP_TITLE, "缺少 Pillow 库，请先安装：pip install pillow")
        return
    CatPet(root)
    root.mainloop()


if __name__ == "__main__":
    main()
