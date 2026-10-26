# 得物图文全自动批量发布 · 小白零基础保姆级配置手册

> **适用人群**：完全不懂代码、第一次在新电脑上搭建「雷电模拟器 + Python + AI 自动发得物图文」环境的新手。
> **搭建耗时**：首次配置约 **10 ~ 15 分钟**（只需配置一次，永久生效）。
> **发布速度**：全自动约 **38 ~ 41 秒 / 条**（含选图、搜货号关联好物、写标题正文、加 5 个蓝色话题并发布）。

---

## 第一步：下载并设置「雷电模拟器」

自动化脚本需要通过模拟器操作得物 App。为了保证点击位置 100% 精准，**模拟器分辨率必须设为竖屏 `1080 × 1920`（DPI 480）**。

### 1.1 下载与安装
1. 打开浏览器访问雷电模拟器官网：[https://www.ldmnq.com/](https://www.ldmnq.com/)
2. 点击首页的 **「雷电模拟器 9（64位）」** 或 **「雷电模拟器 14」** 下载安装包。
3. 双击安装包，建议安装在空间充裕的磁盘（例如 `D:\leidian\LDPlayer14` 或 `C:\leidian\LDPlayer9`）。

### 1.2 必做 3 项模拟器设置（非常关键！）
打开雷电模拟器，点击右上角的 **「三条横线 ☰」→「软件设置」**（或右侧工具栏的齿轮图标 ⚙️）：

1. **设置竖屏分辨率（性能设置）**：
   - 左侧点击 **「性能设置」** → 分辨率选择 **「手机版」** → 勾选 **「1080 × 1920（dpi 480）」**（如果列表里没有，点「自定义」，宽填 `1080`、高填 `1920`、DPI 填 `480`）。
2. **开启 ADB 本地调试（其他设置）**：
   - 左侧点击 **「其他设置」** → 找到 **「ADB调试」** → 下拉选择 **「开启本地连接」**。
3. **保存并重启**：
   - 点击右下角 **「保存设置」** → 点击 **「立即重启」** 让竖屏分辨率生效。

### 1.3 安装得物 App 并登录账号
1. 在模拟器桌面上打开「雷电游戏中心」或浏览器，搜索下载并安装 **「得物」** App。
2. 打开得物 App，登录你要发动态的账号。
3. 首次进入「我」→「创作中心」→「+」，当系统弹出「是否允许访问相册/媒体文件」时，点击 **「始终允许」**。

---

## 第二步：下载并配置 Python 环境

自动化脚本依靠 Python 和 `uiautomator2` 控制模拟器。如果电脑还没装 Python，按下面步骤操作：

### 2.1 下载并安装 Python
1. 打开浏览器访问 Python 官网下载页：[https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
2. 下载 **Python 3.11** 或 **Python 3.12** 的 **Windows installer (64-bit)**（例如 `python-3.11.9-amd64.exe`）。
3. **双击运行安装包（⚠️ 注意最底下两个勾！）**：
   - ✅ **必须勾选最下方的 `Add python.exe to PATH`**（把 Python 加入系统环境变量，极其重要！）
   - 然后点击上方的 **「Install Now」**，等待进度条走完点击 `Close` 即可。

> 💡 **如果你不小心忘了勾选 `Add python.exe to PATH` 怎么办？**
> 再次双击刚才下载的 Python 安装包 → 点击 `Modify` → `Next` → 勾选 `Add Python to environment variables` → 点击 `Install` 即可补救。

### 2.2 一键安装自动化控制库（`uiautomator2`）
1. 在电脑键盘上同时按下 **`Win + R`** 键，在左下角弹出的运行框里输入 **`cmd`**，按回车打开黑色的命令提示符窗口。
2. 复制下面这行命令（已配置国内清华镜像源，下载只需几秒钟），在黑窗口里**单击鼠标右键粘贴**，然后按回车：
   ```cmd
   pip install -U uiautomator2 pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```
3. 看到最后出现 `Successfully installed ... uiautomator2 ...` 字样，就说明 Python 环境配置成功了！

---

## 第三步：把图片素材放进模拟器相册

得物选图页面是按**子相册文件夹名**来区分每组衣服素材的（例如 `UWM160041-group01`、`UWM160041-group02`）。

### 3.1 电脑端素材整理规范
在电脑上新建一个总文件夹（比如 `E:\测试`），每篇动态建一个子文件夹，命名格式推荐为 **`货号-group序号`**：
```text
E:\测试\
├── UWM160041-group01\    <-- 第1篇动态的文件夹（白衣组）
│   ├── 1.jpg
│   ├── 2.jpg
│   └── 3.jpg
└── UWM160041-group02\    <-- 第2篇动态的文件夹（黑衣组）
    ├── 1.jpg
    └── 2.jpg
```
> ⚠️ **注意**：图片直接放在 `UWM160041-group01` 里面，里面不要再套一层子文件夹！

### 3.2 一键导入模拟器相册并刷新
保持雷电模拟器开启，打开 `cmd` 命令窗口（或让 AI Agent 调用 `dewu_import`），运行：
```cmd
python "E:\桌面\skills\dewu-image-publish\scripts\dewu_tool.py" import --src "E:\测试"
```
工具会自动找到 `adb`、把每个子文件夹推送到模拟器相册、刷新媒体库，并在返回结果里用 `visible_in_gallery` 告诉你每个相册是否已经出现在相册里。

---

## 第四步：如何使用 Skill / 工具一键全自动发布

### 4.1 设计原则：Agent 只负责「调用」，不写代码

不管你的图是 2~3 组还是 10~20 组，**内网 Agent 都不需要自己写任何程序**。所有底层操作都已经封装成固定命令 [`dewu_tool.py`](file:///E:/桌面/skills/dewu-image-publish/scripts/dewu_tool.py)，Agent 的工作只有三件事：

1. 调用 `scan` 看有哪些素材组
2. 为每一组写好标题、50~100 字正文、5 个话题，保存成 `posts.json`（这是**数据文件**，不是程序）
3. 依次调用 `validate`、`publish`，然后汇报结果

工具会自动完成：找 `adb`、装输入法、选图、搜货号关联好物、填文案、粘蓝色话题、发布、失败重试与断点续跑。

### 4.2 五个固定命令

| 命令 | 作用 | 示例 |
|---|---|---|
| `env-check` | 检查并初始化模拟器环境 | `python dewu_tool.py env-check` |
| `scan` | 列出本地素材相册组 | `python dewu_tool.py scan --src "E:\测试"` |
| `import` | 推送素材到模拟器相册 | `python dewu_tool.py import --src "E:\测试"` |
| `validate` | 校验 `posts.json` | `python dewu_tool.py validate --config posts.json` |
| `publish` | 批量发布 | `python dewu_tool.py publish --config posts.json` |

所有命令只在屏幕上输出一个 JSON 结果，方便 Agent 读取。`publish` 额外支持：

- `--resume`：中断后继续，已发布的帖子不会重复发
- `--only group03,group07`：只重发指定帖子
- `--stop-on-error`：遇错立即停止

### 4.3 接入公司内网 Agent

1. 把桌面的 `skills\dewu-image-publish` 整个文件夹复制到 Agent 的 skills 目录（没有 skills 目录的 Agent，把 [`SKILL.md`](file:///E:/桌面/skills/dewu-image-publish/SKILL.md) 的内容放进系统提示词）。
2. 如果 Agent 支持函数调用（Function Calling），可以直接注册 [`schemas/tools.json`](file:///E:/桌面/skills/dewu-image-publish/schemas/tools.json) 里的 5 个函数，由你的 Agent 平台把函数映射到上表的命令行。
3. 对 Agent 说一句话即可：
   > 「按 dewu-image-publish 技能，把 `E:\测试` 下所有素材组发布到得物，货号取文件夹名前缀，正文 50-100 字小红书种草风，每篇 5 个话题。」

> ⚠️ 前提：Agent 必须有**在本机运行命令和读写文件**的权限。

### 4.4 不用 Agent，自己手动跑

1. 复制 [`examples/posts.example.json`](file:///E:/桌面/skills/dewu-image-publish/examples/posts.example.json) 改成你自己的内容（每个素材组一项）。
2. 依次执行：
   ```cmd
   python "E:\桌面\skills\dewu-image-publish\scripts\dewu_tool.py" env-check
   python "E:\桌面\skills\dewu-image-publish\scripts\dewu_tool.py" validate --config "E:\桌面\posts.json"
   python "E:\桌面\skills\dewu-image-publish\scripts\dewu_tool.py" publish --config "E:\桌面\posts.json"
   ```

### 4.5 当前已知限制

- 单组图片数量支持 **1~5 张**（已实测 2 张、3 张）；超过 5 张的素材组会在 `scan` 里显示 `supported: false`，工具不会发布它。
- 标题上限按 20 字校验。
- 每条约 40 秒，20 组约 14 分钟；发布期间请不要手动操作模拟器。

---

## 第五步：后台运行与常见问题自查（FAQ）

### Q1：脚本在后台发得物的时候，我在电脑前台写文档、复制粘贴（Ctrl+C / Ctrl+V）受影响吗？
- 模拟器的点击、滑动、输入全部走 ADB 通道，不会抢占你电脑的鼠标和键盘。
- 正文采用 Base64 广播直发，不经过剪贴板；只有粘贴话题时会有 `0.05 秒` 的剪贴板调用。

### Q2：为什么模拟器底部会有一排黑灰色的 `Clear Text | Done | Switch IME` 按钮？
- 这是自动化专用输入法 `AdbKeyboard` 的状态栏，请勿手动切换回其他输入法。

### Q3：如果返回 `E_ADB_NOT_FOUND` 怎么办？
- 确认雷电模拟器已安装。如果安装在特殊文件夹，把 `adb.exe` 所在目录加入系统环境变量 `PATH`。

### Q4：如果返回 `E_ALBUM_NOT_FOUND` 怎么办？
- 说明相册还没进到模拟器。重新执行 `import`，确认返回里该相册的 `visible_in_gallery` 为 `true`，再用 `publish --only <id>` 重发。

### Q5：如果返回 `E_DEVICE_NOT_FOUND` 怎么办？
- 模拟器没有启动，或 ADB 本地连接没开。回到「第一步 1.2」检查。
