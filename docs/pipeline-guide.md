# 得物图文一键发布流水线（GLM 版）使用文档

流程：**放图 → 一条命令 → 自动看图写文案 → 自动发布**。全程不需要 agent 写代码，只需要触发 `run.sh`。

```
env-check → scan → import → gen-copy(GLM 看图写文案) → validate → publish
```

## 1. 一次性准备（约 10 分钟）

| 项 | 要求 |
|---|---|
| 模拟器 | 雷电模拟器，1080×1920、密度 480，已登录得物 App，保持窗口可见、不要最小化 |
| Python | 3.9+，`pip install uiautomator2 pillow` |
| adb | 雷电自带（`LDPlayer\adb.exe`），工具会自动探测 |
| GLM Key | 到 <https://open.bigmodel.cn> 注册，创建 API Key（免费模型 `glm-4v-flash`） |

设置 Key（只需一次）：

- Windows：`setx GLM_API_KEY "你的key"`，然后重开终端
- Linux/Git Bash：`export GLM_API_KEY=你的key`

可选环境变量：`GLM_MODEL`（默认 `glm-4v-flash`）、`GLM_BASE_URL`（换成其他兼容 OpenAI 格式的多模态接口时使用）、`PYTHON`（指定 Python 路径）。

## 2. 素材目录规范

```
素材/
├─ UWM160041-group01/   1~5 张图
│   ├─ 1.jpg
│   └─ 2.jpg
├─ UWM160041-group02/
└─ meta.json            （可选）
```

- 文件夹名 `货号-groupNN`，货号取 `-group` 之前的部分。
- 每组 1~5 张图，超过 5 张的组会被跳过（`supported:false`）。
- 看图时只取每组按文件名排序的**第一张**图（`glm-4v-flash` 单图输入更稳）。
- `meta.json` 可选，用来指定颜色或覆盖货号，没有它则关联商品时点第一张商品卡：

```json
{ "UWM160041-group02": { "color_name": "黑色" } }
```

## 3. 运行

```bash
# Linux / Git Bash（dewuclaw 调用这个）
GLM_API_KEY=xxx sh run.sh /path/to/素材

# Windows
run.bat D:\素材
```

附加参数（可直接追加在后面）：

| 参数 | 作用 |
|---|---|
| `--skip-import` | 图片已在模拟器相册里，跳过导入（导入每张图约几秒，较慢） |
| `--reuse-config` | 复用已有的 `work/posts.json`，不重新生成文案（可先人工改文案） |
| `--resume` | 断点续发，跳过已发布的帖子 |

分步命令也可以单独跑：`python scripts/dewu_tool.py gen-copy --src 素材 --out work/posts.json`。

## 4. 输出与退出码

- stdout 只有一个 JSON：`{ok, command, data, error}`。`data.stages` 记录每阶段耗时，`data.results` 记录每条帖子的状态（`published` / `failed` / `skipped`）。
- 退出码：`0` 全部成功，`1` 工具错误（流水线在失败阶段停止），`2` 部分帖子失败。
- 失败截图在 `work/screenshots/<id>_failed.png`。
- 文案会保存在 `work/posts.json`，发布前可人工查看修改。

## 5. 文案规则（由 validate 硬校验）

标题 ≤20 字；正文 50~100 字（不含空白）、不含 `#`；话题 1~5 个，以 `#` 开头。
GLM 输出不合格时，会把具体问题回传给它重写，最多 `--retries`（默认 3）次。仍失败的组记录在 `data.failed`，不会阻塞其他组。

## 6. 常见错误码

| 错误码 | 处理 |
|---|---|
| `E_LLM_KEY_MISSING` | 没设置 `GLM_API_KEY` |
| `E_LLM_REQUEST_FAILED` | 网络、限速或 Key 无效；稍后重试，或换 `GLM_MODEL` / `GLM_BASE_URL` |
| `E_COPY_GEN_FAILED` | 所有组文案都没过校验；手写 `work/posts.json` 后用 `--reuse-config` |
| `E_DEVICE_NOT_FOUND` / `E_DEVICE_OFFLINE` | 打开模拟器，等待启动完成 |
| `E_RESOLUTION_MISMATCH` | 模拟器改成 1080×1920、密度 480 |
| `E_UI_TIMEOUT` | 模拟器卡顿或窗口被最小化、黑屏；恢复窗口后加 `--resume` |
| `E_ALBUM_NOT_FOUND` | 先不加 `--skip-import` 重新导入 |

## 7. 给 dewuclaw 的调用约定

1. 只允许执行 `sh run.sh <素材目录> [附加参数]`，读取 stdout 的 JSON 与退出码后向用户汇报。
2. 禁止自行编写代码、禁止修改 `scripts/` 下的文件。
3. 退出码为 1 或 2 时，按错误码提示用户处理，修复后用 `--resume` 重跑。

## 8. 已知限制

- GLM 接口的联网调用我没有用真实 Key 验证，只用本地模拟接口验证了请求格式、JSON 解析和"校验失败后重试"逻辑。首次使用请先拿 1 组图试跑，并核对 `glm-4v-flash` 的模型名和限额是否仍有效。
- 图片会压缩到长边 1024px 的 JPEG 后再上传，商品图会发送给智谱服务器，合规有要求的图请换本地模型。
- 免费额度和并发限制以智谱官网为准。
