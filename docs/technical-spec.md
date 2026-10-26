# 得物图文批量发布 · 全流程实测规范与技术文档

> 更新时间：2026-10-24（全自动连续测速验证版）
> 适用环境：雷电模拟器（LDPlayer 9 / 14），**1080×1920 竖屏，density 480**
> 单条实测耗时：**37.2 秒 ~ 41.4 秒 / 条**（2张图约 37 秒，3张图约 41 秒）

---

## 〇、跨电脑自适应环境检查（每次开跑前）

1. **自动探测 `adb.exe` 并检查设备在线（禁止写死盘符）**：
   ```python
   import os, shutil

   def find_adb() -> str:
       if shutil.which("adb"):
           return shutil.which("adb")
       candidates = [
           r"D:\leidian\LDPlayer14\adb.exe",
           r"C:\leidian\LDPlayer14\adb.exe",
           r"E:\leidian\LDPlayer14\adb.exe",
           r"D:\leidian\LDPlayer9\adb.exe",
           r"C:\leidian\LDPlayer9\adb.exe",
           r"D:\ChangZhi\dnplayer2\adb.exe",
       ]
       for p in candidates:
           if os.path.exists(p):
               os.environ["PATH"] = os.path.dirname(p) + os.pathsep + os.environ.get("PATH", "")
               return p
       raise FileNotFoundError("未找到 adb.exe，请将雷电模拟器目录加入 PATH")
   ```
   - 若 `adb devices` 显示 `offline` → 查端口占用并由用户确认：
     ```cmd
     netstat -ano | findstr :5555
     ```
2. **分辨率确认（必须为 1080×1920 竖屏 / 480 DPI）**：
   ```bash
   adb shell wm size      # Physical size: 1080x1920
   adb shell wm density   # Physical density: 480
   ```
3. **关闭安卓三项过渡动画（防 UIAutomator dump idle 超时报错）**：
   ```bash
   adb shell settings put global window_animation_scale 0
   adb shell settings put global transition_animation_scale 0
   adb shell settings put global animator_duration_scale 0
   ```
4. **核对素材并导入相册**：
   - 素材按组放入本地文件夹 `<货号>-groupNN`（图片直接放文件夹内，禁止多层嵌套）
   - 用 `python scripts/dewu_tool.py import --src <素材根目录>` 推送并刷新媒体库，返回里 `visible_in_gallery` 为 `true` 即可

---

## 一、中文输入与蓝色话题：底层根因与最终稳态方案

### 1.1 历史弯路总结

| 方案 | 结果与原因 |
|---|---|
| 弯路 1：Windows 剪贴板 + `Ctrl+V` | ❌ **已废弃**。Windows 与模拟器剪贴板同步延迟不可控，且会污染用户前台办公剪贴板 |
| 弯路 2：`d.send_keys()` 输入一切 | ⚠️ **仅限单行输入（标题/搜索框）**。`send_keys('#话题')` 不会触发得物话题解析，文字呈白色纯文本（无效话题）；且 `send_keys` 末尾强制收起键盘会导致正文框失焦 |

### 1.2 ✅ 最终稳态方案：不断焦点直输 + 设备端原地粘贴

| 输入目标 | 技术手段 | 核心作用 |
|---|---|---|
| **标题、货号搜索** | `d.send_keys(text)` | 单行输入框，输完自动收起键盘无副作用 |
| **正文（严格 50~100 字）** | **`ADB_KEYBOARD_INPUT_TEXT`（不发 `HIDE`）** | 绕过 `d.send_keys()` 末尾自带的 `ADB_KEYBOARD_HIDE`，保持正文框 `focused="true"` 且光标稳停在正文末尾新行 |
| **话题（限 5 个，100% 变蓝）** | **`d.set_clipboard("#话题")` + `0.05s` + `keyevent 279` + 不断焦点空格** | 趁光标在末尾原地粘贴，触发得物原生粘贴解析变蓝；`0.05s` 极短间隔避免用户前台复制粘贴互相干扰 |
| **清空旧正文重写** | `ADB_KEYBOARD_CLEAR_TEXT` + `set_text("")` 兜底 | 彻底清空不残留 |

#### 🔍 为什么以前话题会插在正文中间 / 贴不进去？（源码级根因）
查看 `uiautomator2/_input.py` 源码发现：`d.send_keys()` 在发送完文字广播后，最后一行强制执行了 `self._must_broadcast('ADB_KEYBOARD_HIDE')`（收起键盘）。
而得物图文编辑页监听了键盘收起事件——**一旦收到 `ADB_KEYBOARD_HIDE`，得物会立即调用 `etTrendContent.clearFocus()` 取消正文框焦点（`focused="false"`，焦点跳到左下角「存草稿」）**！
- 如果不重新点正文框，`input keyevent 279` 发出去时正文框没有焦点，根本贴不进去；
- 如果重新去点 `(540, 648)` 恢复焦点，又会把光标点回正文第一行/中间行，导致话题插在正文中间！

#### 💡 100% 稳态置底变蓝代码（实测 5 个话题全蓝且稳居正文末尾）：

```python
import base64, time
import uiautomator2 as u2

def input_text_keep_focus(d: u2.Device, text: str):
    """直接发 AdbKeyboard 输入广播，绝不发 ADB_KEYBOARD_HIDE，保持焦点与末尾光标"""
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    d._must_broadcast("ADB_KEYBOARD_INPUT_TEXT", {"text": b64})

# 1. 点击正文框首行聚焦（确认 focused="true"）
d.click(540, 648)
time.sleep(0.5)

# 2. 输入正文（50-100字，末尾带 \n 换行），全程不收起键盘，光标天然停在最末尾新行
input_text_keep_focus(d, body_text.rstrip("\n") + "\n")
time.sleep(0.5)

# 3. 零二次点击！直接在当前末尾光标处逐个粘贴话题（每篇最多 5 个话题）
for topic in topics[:5]:
    d.set_clipboard(topic)             # ① 写 Android 设备端剪贴板
    time.sleep(0.05)                   # ② 0.05s 极短间隔，防止与用户前台 Ctrl+C 冲突
    d.shell("input keyevent 279")      # ③ Android 原生 KEYCODE_PASTE 触发得物变蓝解析
    time.sleep(0.5)
    input_text_keep_focus(d, " ")      # ④ 补一个空格且不收起键盘（切勿用 keyevent 62 空格，无焦点时会误触返回键）
    time.sleep(0.2)

# 4. 全部填完后再收起键盘，准备点发布
d.hide_keyboard()
```

### 1.3 `AdbKeyboard` 首次自动安装（跨电脑通用）

```python
import os, subprocess, uiautomator2 as u2

def ensure_adb_keyboard(adb_path: str, serial: str = "emulator-5554"):
    out = subprocess.check_output([adb_path, "-s", serial, "shell", "ime", "list", "-a"], text=True, encoding="utf-8", errors="ignore")
    if "com.github.uiautomator/.AdbKeyboard" not in out:
        apk_path = os.path.join(os.path.dirname(u2.__file__), "assets", "app-uiautomator.apk")
        subprocess.run([adb_path, "-s", serial, "push", apk_path, "/sdcard/ime.apk"], check=True)
        subprocess.run([adb_path, "-s", serial, "shell", "pm", "install", "-r", "-t", "/sdcard/ime.apk"], check=True)
    subprocess.run([
        adb_path, "-s", serial, "shell", "settings", "put", "secure",
        "enabled_input_methods", "com.android.inputmethod/.latin.LatinIME:com.github.uiautomator/.AdbKeyboard"
    ], check=True)
    subprocess.run([adb_path, "-s", serial, "shell", "ime", "enable", "com.github.uiautomator/.AdbKeyboard"], check=True)
    subprocess.run([adb_path, "-s", serial, "shell", "ime", "set", "com.github.uiautomator/.AdbKeyboard"], check=True)
```
> ⚠️ `apk` 直接 push 到 `/data/local/tmp` 会报 `INSTALL_FAILED_MEDIA_UNAVAILABLE`，**必须先 push 到 `/sdcard/ime.apk` 再安装**。

---

## 二、坐标与控件总表（1080×1920 竖屏实测）

> 💡 **最佳实践**：优先通过 `d.dump_hierarchy()` 按 `resource-id` 或 `text` 动态解析 `bounds` 中心点，以下坐标作为标准兜底值。

### 2.1 首页与「我」页面

| 元素 | Resource ID / Text | 标准坐标 |
|---|---|---|
| 底部「我」Tab | `text="我"` | **(899, 1836)** |
| 创作中心入口 | `text="创作中心"` | **(132, 580)** |
| 创作中心右上角「+」发布按钮 | `com.shizhuang.duapp:id/ivPublish` | **(996, 153)** |

### 2.2 相册选图页（4 列网格）

| 元素 | Resource ID / Text | 标准坐标 |
|---|---|---|
| 顶部相册下拉「所有照片 ∨」 | `text="所有照片"` | **(516, 138)** |
| 相册下拉列表项 | `text="<相册文件夹名>"` | 动态解析 `bounds`（第2/3行约 `y=618 / 870, x=540`） |
| 子相册内第 1~4 列勾选圈 | `com.shizhuang.duapp:id/ivThumbSelect` | **y=380，x = 216 / 489 / 762 / 1035** |
| 选图页右下角「下一步」 | `text^="下一步"` | **(850, 1830)** |

### 2.3 图片预览页

| 元素 | Resource ID / Text | 标准坐标 |
|---|---|---|
| 底部缩略图 第 1~4 张 | 缩略图横向列表 | **y=1590，x = 246 / 408 / 570 / 732** |
| 左下角「好物」按钮 | `com.shizhuang.duapp:id/ivTag` | **(69, 1788)** |
| 右下角「下一步」按钮 | `com.shizhuang.duapp:id/tvNextStep` | **(918, 1788)** |

### 2.4 关联好物搜索页

| 元素 | Resource ID / Text | 标准坐标 |
|---|---|---|
| 搜索输入框 | `EditText` (`搜索品牌、商品...`) | **(540, 382)** |
| 搜索结果「商品」Tab | `text="商品"` | **(405, 510)** |
| 历史标签第 1 个 / 第 2 个 | `历史标签` 下方胶囊 | **(379, 626)** / (913, 626) |
| 「商品」Tab 双列卡片图片中心 | `com.shizhuang.duapp:id/ivProduct` | 左上第1个 **(288, 836)** / 右上第2个 **(791, 836)**<br>左下第3个 **(288, 1450)** / 右下第4个 **(791, 1450)** |

> ⚠️ **严禁点击 `(439, 1150)`**：在「商品」Tab 双列视图下，`(439, 1150)` 是左上卡片右下角的「展开^」按钮，点它只会展开商品长标题而不会关联商品！必须点击 `ivProduct` 图片中心（或根据 `tvCSpuInfo` 颜色文本匹配对应卡片的 `ivProduct` 中心）。

### 2.5 图文编辑页

| 元素 | Resource ID / Text | 标准坐标 |
|---|---|---|
| 标题输入框 | `com.shizhuang.duapp:id/etTitle` | **(540, 567)** |
| 正文输入框（首行） | `com.shizhuang.duapp:id/etTrendContent` | **(540, 648)** |
| 底部「发布」按钮 | `com.shizhuang.duapp:id/tvPublish` | **(615, 1806)** |

---

## 三、标准 10 步全自动流程与实测耗时（平均 39.3 秒/条）

| 步骤 | 动作说明 | 3张图耗时 (group01) | 2张图耗时 (group02) |
|---|---|---:|---:|
| **Step 1** | **进入选图页**：先执行 `d.hide_keyboard()` 并检查关闭首页弹窗（如「大家如何称呼你？」）→ 点「我」`(899,1836)` → 点「创作中心」`(132,580)` → 点右上角「+」`(996,153)` | 10.00s | 10.34s |
| **Step 2** | **切换相册并勾图**：点顶部下拉 `(516,138)` → 动态定位目标相册名点击 → 遍历勾选全部 `ivThumbSelect`（间隔 `0.35s`） | 2.15s | 1.55s |
| **Step 3** | **进入预览页**：点右下角「下一步」`(850,1830)`，等待 `下载中` 遮罩消失且 `ivTag` 出现 | 1.22s | 1.20s |
| **Step 4** | **第1张图搜货号关联好物**：点「好物」`(69,1788)` → 点搜索框 `(540,382)` → `send_keys(货号)` + `send_action("search")` → 点「商品」Tab `(405,510)` → 点目标颜色商品卡片 `ivProduct` 图片中心 | 9.30s | 9.39s |
| **Step 5** | **第2~N张图关联历史标签**：依次点底部缩略图 `(408,1590)` / `(570,1590)` → 点「好物」`(69,1788)` → 点历史标签第 1 项 `(379,626)` | 3.54s *(2张)* | 1.94s *(1张)* |
| **Step 6** | **进入文案编辑页**：点右下角「下一步」`(918,1788)`，等待 `下载中` 消失且 `etTitle` 出现 | 1.42s | 1.07s |
| **Step 7** | **填写标题**：点标题框 `(540,567)` 确认聚焦 → `d.send_keys(标题)` | 2.78s | 1.83s |
| **Step 8** | **填写正文（保持焦点）**：点正文首行 `(540,648)` 确认聚焦 → `input_text_keep_focus(正文 + "\n")`（50~100字） | 1.83s | 2.08s |
| **Step 9** | **文末粘贴5个蓝色话题**：原地循环 5 次 `set_clipboard(话题)` + `0.05s` + `keyevent 279` + `input_text_keep_focus(" ")` | 4.87s | 4.72s |
| **Step 10** | **收起键盘并发布**：`d.hide_keyboard()` → 点「发布」`(615,1806)` → 确认回到 `HomeActivity`（连发下一条前缓冲 `3.5s` 等待后台上传完成） | 4.25s | 3.09s |
| **合计** | **单条总耗时** | **41.36s** | **37.19s** |

---

## 四、文案与话题生成规范

1. **正文长度**：严格控制在 **50 ~ 100 字**（约 3~4 行，一屏完整展示正文 + 5 个蓝色话题）。
2. **话题数量**：每篇动态**最多 5 个 `#话题`**，全部置于正文最末尾。
3. **风格要求**：小红书/得物高网感种草风，句式短平快、带情绪钩子与穿搭视觉锚点（如「救命！白月光神衣」「一秒掐出小蛮腰✨」「Cleanfit天花板🔥」）。

---

## 五、防坑排错总表（Troubleshooting）

| 异常现象 | 根本原因 | 标准解法 |
|---|---|---|
| 话题插在正文中间 / 贴不进去 | `d.send_keys()` 自动广播 `ADB_KEYBOARD_HIDE` 导致正文框失去焦点，再点 `(540,648)` 把光标点回中间 | 正文和话题间空格一律用 `input_text_keep_focus()`（只发 `ADB_KEYBOARD_INPUT_TEXT`，不发 `HIDE`） |
| 话题文字是白色，没有变蓝 | 用了 `send_keys("#话题")` 直接打字，未触发得物粘贴监听器 | 必须用 `d.set_clipboard("#话题")` + `d.shell("input keyevent 279")` + `input_text_keep_focus(d, " ")` |
| 发布回首页后弹出「选择输入法」 | 首页偶发弹出「大家如何称呼你？」输入框并自动唤醒底部 `AdbKeyboard` 状态栏，`Switch IME` 按钮恰好遮挡 `(899, 1836)`「我」按钮 | 点击「我」前必须先执行 `d.hide_keyboard()`，若 XML 含 `大家如何称呼你` 或 `选择输入法` 则先 `d.press("back")` 关闭弹窗 |
| 在编辑页按空格键突然退回上一页 | 当输入框无焦点时，Android 默认焦点在左上角返回键 `ivLeft`，发 `keyevent 62`（空格）等于点击返回键 | **严禁使用 `input keyevent 62`**，空格一律用 `input_text_keep_focus(d, " ")` |
| 商品搜索结果点击后没反应只展开标题 | 点到了 `(439, 1150)`（卡片右下角「展开^」按钮） | 必须点击商品图片 `ivProduct` 中心：左上 `(288, 836)`、左下 `(288, 1450)` |
| 首次进入预览页/编辑页点不动 | 首次加载滤镜/模板弹出 `下载中... 请稍候` 模态遮罩 | 循环 `d.dump_hierarchy()` 确认不含 `"下载中"` 后再执行点击 |
| APK 安装报 `MEDIA_UNAVAILABLE` | 直接 push 到 `/data/local/tmp` 权限受限 | 先 `adb push` 到 `/sdcard/ime.apk`，再 `pm install -r -t /sdcard/ime.apk` |

---

## 六、相关文件清单

| 文件路径 | 用途说明 |
|---|---|
| `E:\桌面\得物图文批量发布.md` | 本技术规范文档（最新坐标、源码级原理解析与测速表） |
| `E:\桌面\得物自动发布_小白零基础配置手册.md` | 面向零基础用户的雷电模拟器下载设置、Python 环境搭建与一键运行手册 |
| `E:\桌面\skills\dewu-image-publish\SKILL.md` | 可直接复用于任何电脑 / 任何 AI Agent 的标准 Skill 定义 |
| `E:\桌面\skills\dewu-image-publish\scripts\publish_batch.py` | 跨电脑自适应全自动批量发布脚本（内置自动探测 ADB/IME 与分步测速） |
