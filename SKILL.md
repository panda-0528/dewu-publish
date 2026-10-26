---
name: dewu-image-publish
description: >-
  得物图文批量发布的调用契约。当用户要求把本地素材相册组发布为得物图文动态（含货号关联好物、标题、正文、话题）时使用。仅允许调用绑定的 dewu_tool.py 命令，不得编写代码。
---

# dewu-image-publish 契约

## 1. 触发条件

满足全部条件时启用：

- 用户要求发布得物图文动态
- 用户提供素材目录路径，目录下每个子文件夹为一组素材
- 用户提供货号，或素材文件夹名满足 `<货号>-groupNN`

## 2. 强约束

- 禁止自行编写代码
- 禁止自行实现逻辑
- 仅允许调用第 4 节列出的绑定命令
- 允许生成的唯一数据文件为符合 `schemas/posts.schema.json` 的 `posts.json`
- 禁止直接操作模拟器、adb、uiautomator2 或任何坐标
- 禁止修改 `scripts/` 与 `schemas/` 下的任何文件

## 3. 绑定工具

调用方式：`python <skill_dir>/scripts/dewu_tool.py <command> [args]`

| 工具名 | 命令 | 参数 | 作用 |
|---|---|---|---|
| dewu_env_check | `env-check` | `--serial` 可选 | 检查并初始化环境 |
| dewu_scan | `scan` | `--src` 必填 | 列出本地素材相册组 |
| dewu_import | `import` | `--src` 必填，`--serial` 可选 | 推送素材到模拟器相册 |
| dewu_validate | `validate` | `--config` 必填 | 校验 posts.json |
| dewu_publish | `publish` | `--config` 必填，`--serial` `--resume` `--only` `--stop-on-error` 可选 | 批量发布 |

函数形式的入参 schema 见 `schemas/tools.json`。

## 4. 入参 schema

`posts.json` 的 schema 为 `schemas/posts.schema.json`。

字段规则：

| 字段 | 必填 | 规则 |
|---|---|---|
| id | 是 | 全局唯一字符串 |
| album | 是 | 必须与 `scan` 返回的 `album` 完全一致 |
| code | 否 | 缺省时取 `album` 中 `-group` 之前的部分 |
| color_name | 否 | 要关联的商品颜色名；缺省时关联搜索结果第一个商品 |
| title | 是 | 1 到 20 个字符 |
| body | 是 | 不含空白字符的长度为 50 到 100；不得含 `#` |
| topics | 是 | 1 到 5 项；每项以 `#` 开头，无空白，无其他 `#` |

## 5. 出参 schema

所有命令向 stdout 输出且仅输出一个 JSON 对象，schema 为 `schemas/tool-result.schema.json`。

退出码：

| 退出码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 1 | 工具级错误或校验失败 |
| 2 | publish 部分帖子失败 |

`publish` 的 `data.results[]` 中每项 `status` 取值为 `published`、`failed`、`skipped`。

## 6. 错误码

| 错误码 | 含义 | 处理规则 |
|---|---|---|
| E_ADB_NOT_FOUND | 未找到 adb | 终止并告知用户安装雷电模拟器 |
| E_DEPENDENCY_MISSING | 缺少 Python 依赖 | 终止并告知用户执行 `pip install uiautomator2` |
| E_DEVICE_NOT_FOUND | 未发现模拟器 | 终止并告知用户启动模拟器 |
| E_DEVICE_OFFLINE | 模拟器离线 | 终止并告知用户重启模拟器 |
| E_DEVICE_DISCONNECTED | 运行中设备断开 | 终止并告知用户 |
| E_RESOLUTION_MISMATCH | 分辨率不是 1080x1920 且密度 480 | 终止并告知用户修改模拟器设置 |
| E_DEWU_NOT_INSTALLED | 未安装得物 | 终止并告知用户 |
| E_IME_SETUP_FAILED | 输入法初始化失败 | 终止并告知用户 |
| E_SRC_NOT_FOUND | 素材目录不存在 | 向用户确认路径 |
| E_NO_ALBUM_FOUND | 素材目录无可用相册组 | 向用户确认目录 |
| E_PUSH_FAILED | 推送素材失败 | 重试 `import` 一次，仍失败则终止 |
| E_CONFIG_NOT_FOUND | 配置文件不存在 | 重新生成 posts.json |
| E_CONFIG_INVALID | 配置不合法 | 依据 `issues` 修改 posts.json 后重新 `validate`，最多修改 3 次 |
| E_ALBUM_NOT_FOUND | 相册未出现在得物相册列表 | 执行 `import` 后对失败帖子 `publish --only` 重试一次 |
| E_UI_TIMEOUT | 界面等待超时 | 对失败帖子 `publish --only` 重试一次，仍失败则上报 |
| E_IMAGE_COUNT_UNSUPPORTED | 单组图片数量超出 1 到 5 | 不重试，上报用户 |
| E_PARTIAL_FAILURE | 部分帖子失败 | 按 `results[]` 中各项错误码处理 |
| E_UNEXPECTED | 未分类错误 | 不重试，原样上报 |

## 7. 调用规则

按顺序执行，前一步 `ok` 为 `false` 时不得进入下一步：

1. `env-check`
2. `scan`，仅使用返回中 `supported` 为 `true` 的相册组；`supported` 为 `false` 的相册组必须上报用户且不得发布
3. `import`，仅当某相册组 `visible_in_gallery` 缺失或为 `false` 时需要重新执行
4. 生成 `posts.json`
5. `validate`
6. `publish`
7. 向用户汇报 `published`、`failed`、`skipped` 数量及每个失败项的错误码

补充规则：

- 同一 `id` 禁止在无 `--resume` 或 `--only` 的情况下重复 `publish`
- 中断后继续使用 `publish --resume`
- 重试失败帖子使用 `publish --only <id1,id2>`
- 每个错误码的自动重试次数不得超过第 6 节规定
- 不得在用户确认前清除 `*.state.json`

## 8. 内容生成规则

仅限生成 `posts.json` 的文本字段：

- `body` 为小红书种草风、口语化、短句
- `body` 只包含与该组素材相关的信息，不得编造价格、材质参数、功效承诺
- `topics` 与素材品类相关
- 同一批次内各帖子的 `title`、`body` 不得重复

## 9. 硬性禁令

- 禁止声称发布成功，除非对应项 `status` 为 `published`
- 禁止绕过 `validate` 直接 `publish`
- 禁止对 `E_IMAGE_COUNT_UNSUPPORTED`、`E_UNEXPECTED` 自动重试
- 禁止并行启动多个 `publish`
- 禁止对用户的剪贴板、文件进行本契约之外的读写
