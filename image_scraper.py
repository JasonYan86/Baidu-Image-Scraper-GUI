import hashlib
import json
import os
import re
import requests
import sys
import threading
import time
import tkinter as tk
from io import BytesIO
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import quote

from PIL import Image, ImageOps, ImageTk

HISTORY_FILE = "search_history.json"
CONFIG_FILE = "config.json"
PAGE_SIZE = 30
DEFAULT_SAVE_DIR = "downloaded_images"

RESIZE_MODE_COVER = "cover"
RESIZE_MODE_CONTAIN = "contain"
RESIZE_MODE_PAD = "pad"

SIZE_ORIGINAL = "保持原图尺寸"
SIZE_DESKTOP = "电脑壁纸 (1920x1080)"
SIZE_MOBILE = "手机壁纸 (1080x1920)"
SIZE_SQUARE = "高清正方形 (1024x1024)"
SIZE_NEW_CUSTOM = "新建自定义尺寸..."

PRESET_SIZES = {
    SIZE_DESKTOP: (1920, 1080),
    SIZE_MOBILE: (1080, 1920),
    SIZE_SQUARE: (1024, 1024),
}

CUSTOM_SIZE_PATTERN = re.compile(r"^自定义:\s*(\d+)x(\d+)$")

SAMPLE_IMAGES = {
    RESIZE_MODE_COVER: "assets/sample_cover.jpg",
    RESIZE_MODE_CONTAIN: "assets/sample_contain.jpg",
    RESIZE_MODE_PAD: "assets/sample_pad.jpg",
}
PREVIEW_MAX_SIZE = (480, 200)
LARGE_PREVIEW_MAX_SIZE = (960, 720)


def app_file_path(filename):
    """获取与程序同目录的可读写文件路径（兼容 PyInstaller 打包）。"""
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


def resource_path(relative_path):
    """获取资源文件路径，兼容 PyInstaller 单文件打包。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def custom_size_label(width, height):
    return f"自定义: {width}x{height}"


def parse_custom_size_label(label):
    match = CUSTOM_SIZE_PATTERN.match(label.strip())
    if not match:
        raise ValueError(f"无法解析自定义尺寸：{label}")
    return int(match.group(1)), int(match.group(2))


def load_config(path=None):
    path = path or app_file_path(CONFIG_FILE)
    if not os.path.exists(path):
        return {"custom_sizes": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"custom_sizes": []}
    sizes = data.get("custom_sizes", [])
    normalized = []
    for item in sizes:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            normalized.append([int(item[0]), int(item[1])])
    return {"custom_sizes": normalized}


def save_config(config, path=None):
    path = path or app_file_path(CONFIG_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_custom_sizes(config):
    return [tuple(item) for item in config.get("custom_sizes", [])]


def add_custom_size(config, width, height):
    sizes = get_custom_sizes(config)
    target = (width, height)
    if target in sizes or target in PRESET_SIZES.values():
        return False
    sizes.append(target)
    config["custom_sizes"] = [[w, h] for w, h in sizes]
    save_config(config)
    return True


def remove_custom_size(config, width, height):
    sizes = get_custom_sizes(config)
    target = (width, height)
    if target not in sizes:
        return False
    sizes.remove(target)
    config["custom_sizes"] = [[w, h] for w, h in sizes]
    save_config(config)
    return True


def resize_image(img, resize_to, mode):
    """按指定模式将图片缩放到目标尺寸。"""
    if mode == RESIZE_MODE_COVER:
        return ImageOps.fit(img, resize_to, method=Image.LANCZOS)
    if mode == RESIZE_MODE_CONTAIN:
        return ImageOps.contain(img, resize_to, method=Image.LANCZOS)
    if mode == RESIZE_MODE_PAD:
        return ImageOps.pad(img, resize_to, method=Image.LANCZOS, color=(255, 255, 255))
    return ImageOps.fit(img, resize_to, method=Image.LANCZOS)


def _create_session():
    """创建请求会话，忽略系统代理（避免本地代理未开启时连接失败）。"""
    session = requests.Session()
    session.trust_env = False
    return session


def _load_history(path):
    """读取搜索断点记录。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(path, history):
    """保存搜索断点记录。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _url_to_md5(url):
    """将图片 URL 转换为 MD5 字符串。"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def clear_keyword_history(keyword, history_file=HISTORY_FILE):
    """清除指定关键字的断点记录。"""
    history = _load_history(history_file)
    if keyword in history:
        del history[keyword]
        _save_history(history_file, history)


def fetch_images(
    keyword,
    max_images=30,
    save_dir=DEFAULT_SAVE_DIR,
    resize_to=None,
    resize_mode=RESIZE_MODE_COVER,
    history_file=HISTORY_FILE,
    log=print,
):
    """
    通过搜索引擎 API 抓取图片并保存到本地。

    返回本次成功下载的图片数量。
    """

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        log(f"📁 已创建文件夹: {save_dir}")

    history = _load_history(history_file)
    pn = history.get(keyword, {}).get("pn", 0)

    encoded_keyword = quote(keyword)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": f"https://image.baidu.com/search/index?tn=baiduimage&word={encoded_keyword}",
        "X-Requested-With": "XMLHttpRequest",
    }
    session = _create_session()

    log(f"🔍 正在搜索关于 '{keyword}' 的图片...")
    if pn > 0:
        log(f"📌 从上次断点继续，pn={pn}")
    if resize_to:
        mode_labels = {
            RESIZE_MODE_COVER: "智能居中裁剪",
            RESIZE_MODE_CONTAIN: "等比缩放保留全图",
            RESIZE_MODE_PAD: "填充白边补全",
        }
        log(f"📐 缩放模式: {mode_labels.get(resize_mode, resize_mode)} -> {resize_to[0]}x{resize_to[1]}")
    else:
        log("📐 保存尺寸: 保持原图")

    downloaded_count = 0

    try:
        while downloaded_count < max_images:
            api_url = (
                "https://image.baidu.com/search/acjson?"
                f"tn=resultjson_com&logid=&ipn=rj&ct=201326592&is=&fp=result"
                f"&queryWord={encoded_keyword}&cl=2&lm=-1&ie=utf-8&oe=utf-8"
                f"&adpicid=&st=-1&z=&ic=&hd=&latest=&copyright="
                f"&word={encoded_keyword}&s=&se=&tab=&width=&height="
                f"&face=0&istype=2&qc=&nc=1&fr=&expermode=&force="
                f"&pn={pn}&rn={PAGE_SIZE}&gsm=1e&{encoded_keyword}="
            )

            try:
                response = session.get(api_url, headers=headers, timeout=10)
                response.raise_for_status()

                data = response.json()
                if data.get("antiFlag") == 1:
                    log(f"❌ 百度拒绝了爬虫访问: {data.get('message', '未知原因')}")
                    break

                image_list = [img for img in data.get("data", []) if img]

                if not image_list:
                    log("⚠️ 没有找到更多图片了。")
                    break

                for img_info in image_list:
                    if downloaded_count >= max_images:
                        break

                    img_url = img_info.get("thumbURL") or img_info.get("middleURL") or img_info.get("objURL")
                    if not img_url:
                        continue

                    md5_value = _url_to_md5(img_url)
                    file_name = f"{keyword}_{md5_value}.jpg"
                    file_path = os.path.join(save_dir, file_name)

                    if os.path.exists(file_path):
                        log(f"文件已存在，跳过: {file_name}")
                        continue

                    try:
                        img_response = session.get(img_url, headers=headers, timeout=10)
                        img_response.raise_for_status()

                        content = img_response.content
                        if resize_to:
                            img = Image.open(BytesIO(content)).convert("RGB")
                            img = resize_image(img, resize_to, resize_mode)
                            img.save(file_path, "JPEG")
                        else:
                            with open(file_path, "wb") as f:
                                f.write(content)

                        downloaded_count += 1
                        log(f"✅ 成功下载 ({downloaded_count}/{max_images}): {file_name}")

                        time.sleep(0.5)

                    except Exception as e:
                        log(f"❌ 下载单张图片失败 {img_url}: {e}")

                pn += PAGE_SIZE

            except Exception as e:
                log(f"❌ 请求图片列表失败: {e}")
                break

    finally:
        history[keyword] = {"pn": pn}
        _save_history(history_file, history)
        log(f"💾 已保存断点记录: {keyword} -> pn={pn}")

    log(f"\n🎉 任务完成！本次共成功下载 {downloaded_count} 张 '{keyword}' 的图片。")
    return downloaded_count


class ImageScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("百度图片抓取工具")
        self.root.geometry("760x720")
        self.root.minsize(640, 640)

        self._running = False
        self.preview_image = None
        self._current_sample_path = None
        self._mode_radiobuttons = []
        self._config = load_config()
        self._custom_sizes = get_custom_sizes(self._config)

        self._build_ui()
        self._refresh_size_options(keep_selection=False)
        self.size_var.set(SIZE_ORIGINAL)
        self._update_size_ui_state()
        self._update_preview()

    def _build_ui(self):
        form = tk.Frame(self.root, padx=12, pady=12)
        form.pack(fill=tk.X)

        tk.Label(form, text="搜索关键字：").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.keyword_var = tk.StringVar(value="高清壁纸")
        tk.Entry(form, textvariable=self.keyword_var, width=40).grid(row=0, column=1, columnspan=5, sticky=tk.EW, pady=4)

        tk.Label(form, text="下载数量：").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.count_var = tk.StringVar(value="30")
        tk.Entry(form, textvariable=self.count_var, width=40).grid(row=1, column=1, columnspan=5, sticky=tk.EW, pady=4)

        tk.Label(form, text="图片保存尺寸：").grid(row=2, column=0, sticky=tk.W, pady=4)

        size_controls = tk.Frame(form)
        size_controls.grid(row=2, column=1, columnspan=5, sticky=tk.EW, pady=4)

        self.size_var = tk.StringVar(value=SIZE_ORIGINAL)
        self.size_combo = ttk.Combobox(
            size_controls,
            textvariable=self.size_var,
            state="readonly",
            width=28,
        )
        self.size_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.size_combo.bind("<<ComboboxSelected>>", self._on_size_selected)

        self.delete_size_btn = tk.Button(
            size_controls,
            text="❌",
            width=3,
            command=self._on_delete_custom_size,
        )
        self.delete_size_btn.pack(side=tk.LEFT, padx=(6, 12))

        tk.Label(size_controls, text="宽：").pack(side=tk.LEFT)
        self.width_var = tk.StringVar(value="")
        self.width_entry = tk.Entry(size_controls, textvariable=self.width_var, width=7)
        self.width_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(size_controls, text="高：").pack(side=tk.LEFT)
        self.height_var = tk.StringVar(value="")
        self.height_entry = tk.Entry(size_controls, textvariable=self.height_var, width=7)
        self.height_entry.pack(side=tk.LEFT)

        form.columnconfigure(1, weight=1)

        self.mode_frame = tk.LabelFrame(self.root, text="缩放保存模式", padx=12, pady=8)
        self.mode_frame.pack(fill=tk.X, padx=12, pady=(0, 4))

        options_frame = tk.Frame(self.mode_frame)
        options_frame.pack(fill=tk.X, anchor=tk.W)

        self.resize_mode_var = tk.StringVar(value=RESIZE_MODE_COVER)
        self.resize_mode_var.trace_add("write", self._on_mode_changed)

        mode_options = [
            (RESIZE_MODE_COVER, "A. 智能居中裁剪（保证尺寸，不变形，可能裁切边界）"),
            (RESIZE_MODE_CONTAIN, "B. 等比缩放保留全图（不变形，完整保留，最终尺寸可能小于设定值）"),
            (RESIZE_MODE_PAD, "C. 填充白边补全（不变形，完整保留，不足部分填白）"),
        ]
        for value, text in mode_options:
            rb = tk.Radiobutton(
                options_frame,
                text=text,
                variable=self.resize_mode_var,
                value=value,
                anchor=tk.W,
                justify=tk.LEFT,
            )
            rb.pack(anchor=tk.W, pady=2)
            self._mode_radiobuttons.append(rb)

        preview_frame = tk.Frame(self.mode_frame)
        preview_frame.pack(fill=tk.X, pady=(10, 0))

        self.preview_hint_label = tk.Label(preview_frame, text="效果样例（点击图片查看大图）", fg="gray")
        self.preview_hint_label.pack(anchor=tk.W, pady=(0, 4))
        self.preview_label = tk.Label(
            preview_frame,
            relief=tk.GROOVE,
            bg="#f0f0f0",
            text="加载中...",
            cursor="hand2",
        )
        self.preview_label.pack(anchor=tk.W)
        self.preview_label.bind("<Button-1>", self._show_large_preview)

        btn_frame = tk.Frame(self.root, padx=12, pady=8)
        btn_frame.pack(fill=tk.X)

        self.start_btn = tk.Button(btn_frame, text="开始抓取", width=14, command=self._on_start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.reset_btn = tk.Button(btn_frame, text="清除当前关键字的断点", command=self._on_reset_history)
        self.reset_btn.pack(side=tk.LEFT)

        log_frame = tk.Frame(self.root, padx=12, pady=12)
        log_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_frame, text="运行日志：").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_size_option_list(self):
        options = [SIZE_ORIGINAL, SIZE_DESKTOP, SIZE_MOBILE, SIZE_SQUARE]
        for width, height in self._custom_sizes:
            options.append(custom_size_label(width, height))
        options.append(SIZE_NEW_CUSTOM)
        return options

    def _refresh_size_options(self, keep_selection=True):
        current = self.size_var.get() if keep_selection else SIZE_ORIGINAL
        self._config = load_config()
        self._custom_sizes = get_custom_sizes(self._config)
        options = self._build_size_option_list()
        self.size_combo["values"] = options
        if current in options:
            self.size_var.set(current)
        else:
            self.size_var.set(SIZE_ORIGINAL)

    def _on_size_selected(self, event=None):
        self._update_size_ui_state()

    def _set_resize_mode_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for rb in self._mode_radiobuttons:
            rb.configure(state=state)
        self.preview_hint_label.configure(state=state)
        self.preview_label.configure(state=state)
        if enabled:
            self._update_preview()
        else:
            self.preview_label.configure(cursor="")

    def _update_size_ui_state(self):
        selection = self.size_var.get()

        if selection == SIZE_ORIGINAL:
            self.width_var.set("")
            self.height_var.set("")
            self.width_entry.configure(state=tk.DISABLED)
            self.height_entry.configure(state=tk.DISABLED)
            self.delete_size_btn.configure(state=tk.DISABLED)
            self._set_resize_mode_enabled(False)
            return

        self._set_resize_mode_enabled(True)

        if selection == SIZE_NEW_CUSTOM:
            self.width_entry.configure(state=tk.NORMAL)
            self.height_entry.configure(state=tk.NORMAL)
            self.delete_size_btn.configure(state=tk.DISABLED)
            return

        if CUSTOM_SIZE_PATTERN.match(selection):
            width, height = parse_custom_size_label(selection)
            self.width_var.set(str(width))
            self.height_var.set(str(height))
            self.width_entry.configure(state=tk.DISABLED)
            self.height_entry.configure(state=tk.DISABLED)
            self.delete_size_btn.configure(state=tk.NORMAL)
            return

        if selection in PRESET_SIZES:
            width, height = PRESET_SIZES[selection]
            self.width_var.set(str(width))
            self.height_var.set(str(height))
            self.width_entry.configure(state=tk.DISABLED)
            self.height_entry.configure(state=tk.DISABLED)
            self.delete_size_btn.configure(state=tk.DISABLED)
            return

        self.width_entry.configure(state=tk.DISABLED)
        self.height_entry.configure(state=tk.DISABLED)
        self.delete_size_btn.configure(state=tk.DISABLED)

    def _parse_dimension_entry(self, value, label):
        text = value.strip()
        if not text:
            raise ValueError(f"{label}不能为空。")
        try:
            number = int(text)
        except ValueError:
            raise ValueError(f"{label}必须为正整数。")
        if number <= 0:
            raise ValueError(f"{label}必须为正整数。")
        return number

    def _resolve_resize_to(self):
        selection = self.size_var.get()

        if selection == SIZE_ORIGINAL:
            return None

        if selection in PRESET_SIZES:
            return PRESET_SIZES[selection]

        if CUSTOM_SIZE_PATTERN.match(selection):
            return parse_custom_size_label(selection)

        if selection == SIZE_NEW_CUSTOM:
            width = self._parse_dimension_entry(self.width_var.get(), "宽度")
            height = self._parse_dimension_entry(self.height_var.get(), "高度")
            return (width, height)

        raise ValueError("请选择有效的图片保存尺寸。")

    def _on_delete_custom_size(self):
        selection = self.size_var.get()
        if not CUSTOM_SIZE_PATTERN.match(selection):
            return

        width, height = parse_custom_size_label(selection)
        if not messagebox.askyesno("确认删除", f"确定删除自定义尺寸 {width}x{height} 吗？"):
            return

        remove_custom_size(self._config, width, height)
        self._refresh_size_options(keep_selection=False)
        self.size_var.set(SIZE_ORIGINAL)
        self._update_size_ui_state()
        self._append_log(f"🗑️ 已删除自定义尺寸: {width}x{height}")

    def _persist_new_custom_size(self, resize_to):
        width, height = resize_to
        if add_custom_size(self._config, width, height):
            self._refresh_size_options(keep_selection=False)
            self.size_var.set(custom_size_label(width, height))
            self._update_size_ui_state()
            self._append_log(f"💾 已保存自定义尺寸: {width}x{height}")

    def _on_mode_changed(self, *args):
        if self.size_var.get() != SIZE_ORIGINAL:
            self._update_preview()

    def _update_preview(self):
        """切换模式时加载对应样例图（保留 self.preview_image 引用以防被 GC）。"""
        if self.size_var.get() == SIZE_ORIGINAL:
            return

        mode = self.resize_mode_var.get()
        sample_path = resource_path(SAMPLE_IMAGES[mode])
        self._current_sample_path = sample_path

        if not os.path.exists(sample_path):
            self.preview_image = None
            self.preview_label.configure(image="", text="样例图缺失", cursor="")
            return

        try:
            img = Image.open(sample_path)
            img.thumbnail(PREVIEW_MAX_SIZE, Image.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview_label.configure(image=self.preview_image, text="", cursor="hand2")
        except Exception as e:
            self.preview_image = None
            self.preview_label.configure(image="", text=f"加载失败\n{e}", cursor="")

    def _show_large_preview(self, event=None):
        """点击样例图时弹出大图预览窗口。"""
        if self.size_var.get() == SIZE_ORIGINAL:
            return
        if not self._current_sample_path or not os.path.exists(self._current_sample_path):
            return

        try:
            img = Image.open(self._current_sample_path)
            img.thumbnail(LARGE_PREVIEW_MAX_SIZE, Image.LANCZOS)

            top = tk.Toplevel(self.root)
            top.title("效果样例 - 大图预览")
            top.transient(self.root)

            photo = ImageTk.PhotoImage(img)
            label = tk.Label(top, image=photo, relief=tk.GROOVE, bg="#f0f0f0")
            label.image = photo
            label.pack(padx=12, pady=12)

            top.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - top.winfo_width()) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - top.winfo_height()) // 2
            top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception as e:
            messagebox.showerror("预览失败", f"无法加载大图：{e}")

    def _append_log(self, message):
        """线程安全地向日志文本框追加内容。"""
        def _write():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, _write)

    def _set_running(self, running):
        self._running = running
        state = tk.DISABLED if running else tk.NORMAL
        self.start_btn.configure(state=state)
        self.reset_btn.configure(state=state)
        if running:
            self.size_combo.configure(state=tk.DISABLED)
            self.delete_size_btn.configure(state=tk.DISABLED)
            self.width_entry.configure(state=tk.DISABLED)
            self.height_entry.configure(state=tk.DISABLED)
            for rb in self._mode_radiobuttons:
                rb.configure(state=tk.DISABLED)
            self.preview_hint_label.configure(state=tk.DISABLED)
            self.preview_label.configure(state=tk.DISABLED)
        else:
            self.size_combo.configure(state="readonly")
            self._update_size_ui_state()

    def _validate_inputs(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            raise ValueError("搜索关键字不能为空。")

        try:
            max_images = int(self.count_var.get().strip())
        except ValueError:
            raise ValueError("下载数量必须为正整数。")
        if max_images <= 0:
            raise ValueError("下载数量必须为正整数。")

        resize_to = self._resolve_resize_to()
        resize_mode = self.resize_mode_var.get()
        is_new_custom = self.size_var.get() == SIZE_NEW_CUSTOM
        return keyword, max_images, resize_to, resize_mode, is_new_custom

    def _on_start(self):
        if self._running:
            return

        try:
            keyword, max_images, resize_to, resize_mode, is_new_custom = self._validate_inputs()
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return

        self._set_running(True)
        self._append_log(f"--- 开始任务：关键字「{keyword}」，目标 {max_images} 张 ---")

        thread = threading.Thread(
            target=self._run_fetch,
            args=(keyword, max_images, resize_to, resize_mode, is_new_custom),
            daemon=True,
        )
        thread.start()

    def _run_fetch(self, keyword, max_images, resize_to, resize_mode, is_new_custom):
        downloaded_count = 0
        try:
            downloaded_count = fetch_images(
                keyword=keyword,
                max_images=max_images,
                resize_to=resize_to,
                resize_mode=resize_mode,
                log=self._append_log,
            )
        except Exception as e:
            self._append_log(f"❌ 任务异常终止: {e}")
        finally:
            if is_new_custom and resize_to and downloaded_count > 0:
                self.root.after(0, lambda: self._persist_new_custom_size(resize_to))
            self.root.after(0, lambda: self._set_running(False))

    def _on_reset_history(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showerror("输入错误", "请先填写搜索关键字。")
            return

        clear_keyword_history(keyword)
        messagebox.showinfo("提示", "已重置该关键字，下次将从第1页开始搜索")
        self._append_log(f"🔄 已清除关键字「{keyword}」的断点记录")


def main():
    root = tk.Tk()
    ImageScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
