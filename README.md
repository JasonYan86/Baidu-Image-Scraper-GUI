# 百度图片抓取工具

一款面向日常使用的**通用图片下载桌面工具**。基于 Python + Tkinter 构建图形界面，支持关键字搜索、智能尺寸选择、多种防变形保存模式、断点续传与 MD5 去重，并可一键打包为 Windows 独立 exe。

> 仅供学习与交流使用，请遵守目标网站服务条款，合理控制抓取频率。

---

## 核心功能

### 智能尺寸选择

- 预置常用尺寸：**保持原图**、电脑壁纸 (1920×1080)、手机壁纸 (1080×1920)、高清正方形 (1024×1024)
- 支持**新建自定义尺寸**，成功抓取后自动写入 `config.json` 并记住
- 下拉菜单与宽/高输入框**强联动**：选原图时自动禁用缩放相关选项，避免逻辑冲突

### 三种防拉伸保存模式

| 模式 | 说明 |
|------|------|
| **智能居中裁剪** | 保证输出尺寸，不变形，可能裁切边界 (`ImageOps.fit`) |
| **等比缩放保留全图** | 完整保留画面，不变形，输出可能小于目标尺寸 (`ImageOps.contain`) |
| **填充白边补全** | 完整保留画面，不足部分填白 (`ImageOps.pad`) |

界面内置效果样例图，支持点击查看大图。

### 稳定可靠的抓取体验

- **多线程下载**：抓取在后台线程执行，GUI 界面不卡顿
- **断点续传**：按关键字记录百度 API 的 `pn` 页码，下次从上次位置继续
- **MD5 去重**：以 URL 哈希命名文件，已存在则自动跳过，防止覆盖
- **代理兼容**：自动绕过失效的系统代理，直连更稳定

### 可分发

- 支持 PyInstaller 打包为**单文件 exe**，双击即可运行，无需安装 Python

---

## 环境要求

- Python **3.8+**
- Windows（开发与打包环境；理论上其他平台也可运行 GUI，但未专门测试）

---

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/<你的用户名>/image_scraper.git
cd image_scraper
```

### 2. 创建并激活虚拟环境

**Windows PowerShell：**

```powershell
py -3.8 -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 使用说明

### 启动 GUI

```bash
python image_scraper.py
```

### 基本流程

1. 输入**搜索关键字**（如：微信头像）
2. 设置**下载数量**
3. 在**图片保存尺寸**下拉框中选择目标尺寸
   - 选「保持原图尺寸」→ 直接保存原始图片
   - 选预置或自定义尺寸 → 选择缩放模式后抓取
   - 选「新建自定义尺寸...」→ 手动输入宽高，抓取成功后自动保存到配置
4. 点击**开始抓取**，在下方日志区查看实时进度
5. 图片默认保存到 `downloaded_images/` 目录

### 断点与自定义尺寸

- **断点记录**保存在 `search_history.json`（已加入 `.gitignore`，不会上传 Git）
- **自定义尺寸**保存在 `config.json`
- 点击 **清除当前关键字的断点** 可从第 1 页重新开始
- 选中「自定义: xxx」后，点击 **❌** 可删除该尺寸预设

### 样例图片

将三张效果样例图放在 `assets/` 目录：

```
assets/
  sample_cover.jpg    # 智能居中裁剪
  sample_contain.jpg  # 等比缩放保留全图
  sample_pad.jpg      # 填充白边补全
```

---

## 打包为 exe（可选）

安装打包工具：

```bash
pip install pyinstaller
```

单文件、无黑窗口打包命令：

```bash
pyinstaller --onefile --windowed --name "百度图片抓取工具" --add-data "assets;assets" --hidden-import=PIL._imaging --collect-all certifi --collect-all PIL image_scraper.py
```

生成的 exe 位于 `dist/` 目录。若已有 `ImageScraper.spec` 且已配置 `assets`，也可：

```bash
pyinstaller ImageScraper.spec
```

> `config.json` 与 `search_history.json` 会在 exe **同级目录**自动生成，便于持久保存用户配置。

---

## 项目结构

```
image_scraper/
├── image_scraper.py      # 主程序（爬虫逻辑 + GUI）
├── assets/               # 缩放模式效果样例图
├── requirements.txt      # 运行时依赖
├── README.md
├── .gitignore
├── config.json           # 用户自定义尺寸（本地生成，不上传 Git）
└── search_history.json   # 断点记录（本地生成，不上传 Git）
```

---

## 技术栈

- [requests](https://pypi.org/project/requests/) — HTTP 请求
- [Pillow](https://pypi.org/project/Pillow/) — 图片处理与缩放
- [tkinter](https://docs.python.org/3/library/tkinter.html) — 图形界面（Python 标准库）

---

## 免责声明

本工具仅提供通用的图片搜索与下载能力，请勿用于侵犯他人版权、隐私或违反相关法律法规及网站服务条款的用途。使用者需自行承担使用本工具产生的一切后果。

---

## License

MIT
