#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dewu_tool.py - 得物图文发布的固定命令行工具（与大模型无关）。

子命令：
  env-check  检查并初始化模拟器环境
  scan       扫描本地素材目录，列出相册组
  import     将本地素材目录推送到模拟器相册并刷新媒体库
  validate   校验 posts.json（字数、话题数量等）
  gen-copy   调用智谱 GLM 多模态 API 看图写文案并生成 posts.json（需环境变量 GLM_API_KEY）
  publish    按 posts.json 批量发布
  run        一键流水线：env-check → scan → import → gen-copy → validate → publish

输出约定：
  stdout 仅输出一个 JSON 对象；过程日志输出到 stderr。
  退出码：0 全部成功；1 工具级错误；2 部分帖子失败。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

REAL_STDOUT = sys.stdout
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TOOL_VERSION = "1.0.0"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DEWU_PKG = "com.shizhuang.duapp"
MAX_POSTS = 100
MAX_IMAGES_PER_POST = 5
TITLE_MAX = 20
BODY_MIN = 50
BODY_MAX = 100
TOPIC_MAX = 5


class ToolError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def emit(payload, exit_code):
    REAL_STDOUT.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    REAL_STDOUT.flush()
    sys.exit(exit_code)


def ok_payload(command, data):
    return {"ok": True, "command": command, "tool_version": TOOL_VERSION, "data": data, "error": None}


def err_payload(command, code, message, details=None):
    return {
        "ok": False,
        "command": command,
        "tool_version": TOOL_VERSION,
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
    }


def log(msg):
    sys.stderr.write(str(msg) + "\n")
    sys.stderr.flush()


def load_engine():
    try:
        import publish_batch
    except FileNotFoundError as e:
        raise ToolError("E_ADB_NOT_FOUND", str(e))
    except ImportError as e:
        raise ToolError("E_DEPENDENCY_MISSING", f"缺少 Python 依赖: {e}")
    return publish_batch


def run_adb(engine, serial, *args):
    cmd = [engine.ADB_PATH, "-s", serial, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode, r.stdout, r.stderr


def check_device_online(engine, serial):
    r = subprocess.run(
        [engine.ADB_PATH, "devices"], capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    state = None
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == serial:
            state = parts[1]
    if state is None:
        raise ToolError("E_DEVICE_NOT_FOUND", f"未发现设备 {serial}", {"adb_devices": r.stdout.strip()})
    if state != "device":
        raise ToolError("E_DEVICE_OFFLINE", f"设备 {serial} 状态为 {state}", {"state": state})


# ---------------------------------------------------------------- env-check
def cmd_env_check(args):
    engine = load_engine()
    check_device_online(engine, args.serial)

    _, out, _ = run_adb(engine, args.serial, "shell", "wm", "size")
    sizes = re.findall(r"(\d+)x(\d+)", out)
    _, out_d, _ = run_adb(engine, args.serial, "shell", "wm", "density")
    dens = re.findall(r"(\d+)", out_d)
    size = f"{sizes[-1][0]}x{sizes[-1][1]}" if sizes else None
    density = int(dens[-1]) if dens else None
    if size != "1080x1920" or density != 480:
        raise ToolError(
            "E_RESOLUTION_MISMATCH",
            "模拟器必须为 1080x1920 竖屏、密度 480",
            {"size": size, "density": density},
        )

    _, out_p, _ = run_adb(engine, args.serial, "shell", "pm", "list", "packages", DEWU_PKG)
    if DEWU_PKG not in out_p:
        raise ToolError("E_DEWU_NOT_INSTALLED", "模拟器未安装得物 App")

    engine.ensure_device_env(engine.ADB_PATH, args.serial)
    _, out_i, _ = run_adb(engine, args.serial, "shell", "ime", "list", "-a")
    ime_ready = "com.github.uiautomator/.AdbKeyboard" in out_i
    if not ime_ready:
        raise ToolError("E_IME_SETUP_FAILED", "AdbKeyboard 输入法安装或启用失败")

    return ok_payload(
        "env-check",
        {
            "adb_path": engine.ADB_PATH,
            "serial": args.serial,
            "resolution": size,
            "density": density,
            "dewu_installed": True,
            "ime_ready": True,
        },
    )


# --------------------------------------------------------------------- scan
def scan_albums(src):
    if not os.path.isdir(src):
        raise ToolError("E_SRC_NOT_FOUND", f"素材目录不存在: {src}")
    albums = []
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if name.startswith(".") or not os.path.isdir(p):
            continue
        entries = os.listdir(p)
        imgs = [f for f in sorted(entries) if os.path.isfile(os.path.join(p, f)) and os.path.splitext(f)[1].lower() in IMG_EXT]
        nested = [f for f in entries if os.path.isdir(os.path.join(p, f))]
        if not imgs:
            continue
        albums.append(
            {
                "album": name,
                "image_count": len(imgs),
                "suggested_code": name.split("-group")[0] if "-group" in name else None,
                "has_nested_dirs": bool(nested),
                "supported": 1 <= len(imgs) <= MAX_IMAGES_PER_POST and not nested,
            }
        )
    return albums


def cmd_scan(args):
    albums = scan_albums(args.src)
    return ok_payload("scan", {"src": os.path.abspath(args.src), "album_count": len(albums), "albums": albums})


# ------------------------------------------------------------------- import
def gallery_buckets(engine, serial):
    _, out, _ = run_adb(
        engine, serial, "shell", "content", "query", "--uri",
        "content://media/external/images/media", "--projection", "bucket_display_name",
    )
    return set(re.findall(r"bucket_display_name=([^\r\n,]+)", out))


def cmd_import(args):
    engine = load_engine()
    check_device_online(engine, args.serial)
    albums = scan_albums(args.src)
    if not albums:
        raise ToolError("E_NO_ALBUM_FOUND", "素材目录下没有包含图片的子文件夹")

    results = []
    for a in albums:
        local = os.path.join(args.src, a["album"])
        rc, out, err = run_adb(engine, args.serial, "push", local, "/sdcard/Pictures/")
        if rc != 0:
            raise ToolError("E_PUSH_FAILED", f"推送失败: {a['album']}", {"stderr": err.strip()})
        files = [f for f in os.listdir(local) if os.path.splitext(f)[1].lower() in IMG_EXT]
        for f in files:
            run_adb(
                engine, args.serial, "shell", "am", "broadcast",
                "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file:///sdcard/Pictures/{a['album']}/{f}",
            )
        results.append({"album": a["album"], "image_count": len(files)})
        log(f"[import] {a['album']} 已推送 {len(files)} 张")

    time.sleep(2.0)
    visible = gallery_buckets(engine, args.serial)
    for r in results:
        r["visible_in_gallery"] = r["album"] in visible
    return ok_payload("import", {"albums": results})


# ----------------------------------------------------------------- validate
def validate_config(path):
    if not os.path.isfile(path):
        raise ToolError("E_CONFIG_NOT_FOUND", f"配置文件不存在: {path}")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except json.JSONDecodeError as e:
        raise ToolError("E_CONFIG_INVALID", f"JSON 解析失败: {e}")

    issues = []

    def add(pid, field, rule, message):
        issues.append({"post_id": pid, "field": field, "rule": rule, "message": message})

    posts = obj.get("posts") if isinstance(obj, dict) else None
    if not isinstance(posts, list) or not posts:
        raise ToolError("E_CONFIG_INVALID", "顶层必须为 {\"posts\": [...]} 且 posts 非空")
    if len(posts) > MAX_POSTS:
        raise ToolError("E_CONFIG_INVALID", f"posts 数量超过上限 {MAX_POSTS}")

    seen = set()
    for i, p in enumerate(posts):
        pid = p.get("id") if isinstance(p, dict) else None
        label = pid if isinstance(pid, str) and pid else f"#{i}"
        if not isinstance(p, dict):
            add(label, "-", "type", "post 必须是对象")
            continue
        for field in ("id", "album", "title", "body", "topics"):
            if field not in p:
                add(label, field, "required", f"缺少字段 {field}")
        if issues and any(x["post_id"] == label and x["rule"] == "required" for x in issues):
            continue
        if pid in seen:
            add(label, "id", "unique", "id 重复")
        seen.add(pid)
        for field in ("id", "album", "title", "body"):
            if not isinstance(p[field], str) or not p[field].strip():
                add(label, field, "type", f"{field} 必须为非空字符串")
        if not isinstance(p["topics"], list):
            add(label, "topics", "type", "topics 必须为数组")
            continue
        if isinstance(p.get("title"), str) and len(p["title"]) > TITLE_MAX:
            add(label, "title", "maxLength", f"标题长度 {len(p['title'])} 超过 {TITLE_MAX}")
        if isinstance(p.get("body"), str):
            n = len(re.sub(r"\s", "", p["body"]))
            if n < BODY_MIN or n > BODY_MAX:
                add(label, "body", "length", f"正文长度 {n}（不含空白），必须在 {BODY_MIN}~{BODY_MAX}")
            if "#" in p["body"]:
                add(label, "body", "no_hash", "正文不得包含 #，话题只能放在 topics")
        if not 1 <= len(p["topics"]) <= TOPIC_MAX:
            add(label, "topics", "count", f"话题数量 {len(p['topics'])}，必须在 1~{TOPIC_MAX}")
        for t in p["topics"]:
            if not isinstance(t, str) or not re.fullmatch(r"#[^\s#]+", t):
                add(label, "topics", "format", f"话题格式非法: {t!r}（必须以 # 开头、无空白、无其他 #）")
        for field in ("code", "color_name"):
            if field in p and (not isinstance(p[field], str) or not p[field].strip()):
                add(label, field, "type", f"{field} 若提供必须为非空字符串")
        if "code" not in p and "-group" not in p.get("album", ""):
            add(label, "code", "required", "未提供 code 且 album 不含 -group，无法推导货号")
    return posts, issues


def cmd_validate(args):
    posts, issues = validate_config(args.config)
    if issues:
        return {
            "ok": False,
            "command": "validate",
            "tool_version": TOOL_VERSION,
            "data": {"post_count": len(posts), "issues": issues},
            "error": {"code": "E_CONFIG_INVALID", "message": f"发现 {len(issues)} 个问题", "details": {}},
        }
    return ok_payload("validate", {"post_count": len(posts), "issues": []})


# ------------------------------------------------------------------ publish
def classify(exc):
    msg = str(exc)
    if "未在下拉列表中找到相册" in msg:
        return "E_ALBUM_NOT_FOUND"
    if "等待超时" in msg or "未能进入相册选图页" in msg:
        return "E_UI_TIMEOUT"
    if isinstance(exc, IndexError):
        return "E_IMAGE_COUNT_UNSUPPORTED"
    return "E_UNEXPECTED"


def cmd_publish(args):
    posts, issues = validate_config(args.config)
    if issues:
        raise ToolError("E_CONFIG_INVALID", f"配置未通过校验，共 {len(issues)} 个问题", {"issues": issues})

    only = set(x for x in (args.only or "").split(",") if x)
    state_path = args.config + ".state.json"
    done = set()
    if args.resume and os.path.isfile(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            done = set(json.load(f).get("done", []))

    engine = load_engine()
    check_device_online(engine, args.serial)
    shots = args.screenshots or os.path.join(os.path.dirname(os.path.abspath(args.config)), "screenshots")
    os.makedirs(shots, exist_ok=True)

    engine.ensure_device_env(engine.ADB_PATH, args.serial)
    try:
        d = engine.u2.connect(args.serial)
        d.set_input_ime(True)
        engine.reset_to_home(d)
    except Exception as e:
        raise ToolError("E_DEVICE_DISCONNECTED", f"连接设备失败: {e}")

    results = []
    batch_t0 = time.perf_counter()
    for p in posts:
        pid = p["id"]
        if (only and pid not in only) or pid in done:
            results.append({"id": pid, "status": "skipped", "duration_sec": 0, "error": None, "steps": {}})
            continue
        cfg = dict(p)
        if "code" not in cfg:
            cfg["code"] = cfg["album"].split("-group")[0]
        t0 = time.perf_counter()
        try:
            steps = engine.run_single_post(d, cfg, shots)
            results.append(
                {"id": pid, "status": "published", "duration_sec": round(time.perf_counter() - t0, 2), "error": None, "steps": steps}
            )
            done.add(pid)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"done": sorted(done)}, f, ensure_ascii=False)
            time.sleep(3.5)
        except Exception as e:
            code = classify(e)
            shot = os.path.join(shots, f"{pid}_failed.png")
            try:
                d.screenshot(shot)
            except Exception:
                shot = None
            results.append(
                {
                    "id": pid,
                    "status": "failed",
                    "duration_sec": round(time.perf_counter() - t0, 2),
                    "error": {"code": code, "message": str(e), "details": {"screenshot": shot}},
                    "steps": {},
                }
            )
            log(f"[publish] {pid} 失败: {code} {e}")
            if args.stop_on_error:
                break
            try:
                engine.reset_to_home(d)
            except Exception:
                pass

    published = sum(1 for r in results if r["status"] == "published")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    payload = {
        "ok": failed == 0,
        "command": "publish",
        "tool_version": TOOL_VERSION,
        "data": {
            "published": published,
            "failed": failed,
            "skipped": skipped,
            "total_sec": round(time.perf_counter() - batch_t0, 2),
            "results": results,
            "state_file": state_path,
        },
        "error": None
        if failed == 0
        else {"code": "E_PARTIAL_FAILURE", "message": f"{failed} 条发布失败", "details": {}},
    }
    return payload


# ----------------------------------------------------------------- gen-copy
GLM_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL_DEFAULT = "glm-4v-flash"

PROMPT = (
    "你是小红书风格的种草文案作者。请根据图片中的真实穿搭和商品细节，为得物App图文动态写一段种草文案。\n"
    "货号：{code}。{color_line}\n"
    "【硬性字数与格式要求，必须严格遵守】：\n"
    "1. title：标题不超过{tmax}个字，吸睛种草。\n"
    "2. body：正文写3~4句完整的上身体验（包括版型细节、面料舒适感、日常穿搭和搭配单品建议），"
    "字数必须在65~85个汉字之间（请充分描写，千万不要少于60字！系统严格校验，低于{bmin}字或高于{bmax}字会直接判定失败打回！）。"
    "口语化，严禁包含#号，严禁出现价格与夸大词汇。\n"
    "3. topics：1~{topic_max}个话题标签，每个以#开头、无空格，贴合穿搭和风格。\n"
    "只输出一个标准 JSON 对象，不要任何前缀和后缀，格式：\n"
    '{{"title":"...","body":"...","topics":["#...","#..."]}}'
)


def encode_image(path, max_side=1024):
    """压缩为 JPEG 并返回 base64；Pillow 不可用时直接读原文件。"""
    import base64
    import io

    try:
        from PIL import Image

        im = Image.open(path).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()


def glm_chat(api_key, model, base_url, img_b64, text, timeout=90):
    import urllib.error
    import urllib.request

    body = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img_b64}},
                    {"type": "text", "text": text},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        base_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"
            if e.code not in (429, 500, 502, 503):
                break
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    raise ToolError("E_LLM_REQUEST_FAILED", f"GLM 请求失败: {last}")


def parse_json_obj(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("响应中没有 JSON 对象")
    return json.loads(m.group(0))


def cmd_gen_copy(args):
    api_key = os.environ.get("GLM_API_KEY", "").strip()
    if not api_key:
        raise ToolError("E_LLM_KEY_MISSING", "未设置环境变量 GLM_API_KEY")
    model = os.environ.get("GLM_MODEL", GLM_MODEL_DEFAULT)
    base_url = os.environ.get("GLM_BASE_URL", GLM_URL)

    albums = [a for a in scan_albums(args.src) if a["supported"]]
    if not albums:
        raise ToolError("E_NO_ALBUM_FOUND", "素材目录下没有可发布的相册组")

    meta = {}
    meta_path = os.path.join(args.src, "meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8-sig") as f:
            meta = json.load(f)

    import tempfile

    posts, failed = [], []
    for a in albums:
        name = a["album"]
        code = meta.get(name, {}).get("code") or a["suggested_code"]
        color = meta.get(name, {}).get("color_name")
        if not code:
            failed.append({"album": name, "reason": "无法推导货号，请在 meta.json 提供 code"})
            continue
        folder = os.path.join(args.src, name)
        first = sorted(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in IMG_EXT)[0]
        img = encode_image(os.path.join(folder, first))
        base_prompt = PROMPT.format(
            code=code,
            color_line=f"颜色：{color}。" if color else "",
            tmax=TITLE_MAX, bmin=BODY_MIN, bmax=BODY_MAX, topic_max=TOPIC_MAX,
        )
        prompt, post, last_issue = base_prompt, None, ""
        for attempt in range(1, args.retries + 1):
            log(f"[gen-copy] {name} 第 {attempt} 次")
            try:
                obj = parse_json_obj(glm_chat(api_key, model, base_url, img, prompt))
                cand = {
                    "id": name, "album": name, "code": code,
                    "title": str(obj.get("title", "")).strip(),
                    "body": str(obj.get("body", "")).strip(),
                    "topics": [str(t).strip() for t in obj.get("topics", [])][:TOPIC_MAX],
                }
                if color:
                    cand["color_name"] = color
            except ToolError:
                raise
            except Exception as e:  # noqa: BLE001
                last_issue = f"输出不是合法 JSON: {e}"
                prompt = base_prompt + f"\n上次问题：{last_issue}。请严格只输出JSON。"
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                json.dump({"posts": [cand]}, tf, ensure_ascii=False)
            try:
                _, issues = validate_config(tf.name)
            finally:
                os.unlink(tf.name)
            if not issues:
                post = cand
                break
            last_issue = "；".join(i["message"] for i in issues)
            prompt = base_prompt + f"\n【警告！上次生成未通过系统校验】：{last_issue}。请务必扩写/修改正文为3~4句话（70字左右），确保字数在50~100字之间，重新输出JSON！"
        if post:
            posts.append(post)
        else:
            failed.append({"album": name, "reason": last_issue})

    if not posts:
        raise ToolError("E_COPY_GEN_FAILED", "所有相册组文案均生成失败", {"failed": failed})
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f, ensure_ascii=False, indent=2)
    return ok_payload("gen-copy", {"out": out, "model": model, "generated": len(posts), "failed": failed})


# ---------------------------------------------------------------------- run
def cmd_run(args):
    stages = {}

    def stage(name, fn, a):
        t0 = time.perf_counter()
        log(f"[run] ==> {name}")
        p = fn(a)
        stages[name] = {"ok": p["ok"], "sec": round(time.perf_counter() - t0, 1)}
        if not p["ok"]:
            raise ToolError(p["error"]["code"], f"阶段 {name} 失败: {p['error']['message']}", {"stage": name, "stages": stages, "payload": p.get("data")})
        return p

    ns = argparse.Namespace
    stage("env-check", cmd_env_check, ns(serial=args.serial))
    stage("scan", cmd_scan, ns(src=args.src))
    if not args.skip_import:
        stage("import", cmd_import, ns(serial=args.serial, src=args.src))
    if not (args.reuse_config and os.path.isfile(args.config)):
        stage("gen-copy", cmd_gen_copy, ns(src=args.src, out=args.config, retries=args.retries))
    stage("validate", cmd_validate, ns(config=args.config))
    pub = cmd_publish(ns(config=args.config, serial=args.serial, resume=args.resume, only="",
                         stop_on_error=False, screenshots=None))
    pub["command"] = "run"
    pub["data"]["stages"] = stages
    return pub


COMMANDS = {
    "env-check": cmd_env_check,
    "scan": cmd_scan,
    "import": cmd_import,
    "validate": cmd_validate,
    "gen-copy": cmd_gen_copy,
    "publish": cmd_publish,
    "run": cmd_run,
}


def build_parser():
    p = argparse.ArgumentParser(prog="dewu_tool.py")
    sub = p.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sp = sub.add_parser(name)
        if name in ("env-check", "import", "publish", "run"):
            sp.add_argument("--serial", default="emulator-5554")
        if name in ("scan", "import", "gen-copy", "run"):
            sp.add_argument("--src", required=True)
        if name in ("validate", "publish", "run"):
            sp.add_argument("--config", required=True)
        if name == "gen-copy":
            sp.add_argument("--out", required=True)
            sp.add_argument("--retries", type=int, default=3)
        if name == "run":
            sp.add_argument("--retries", type=int, default=3)
            sp.add_argument("--skip-import", action="store_true")
            sp.add_argument("--reuse-config", action="store_true")
            sp.add_argument("--resume", action="store_true")
        if name == "publish":
            sp.add_argument("--resume", action="store_true")
            sp.add_argument("--only", default="")
            sp.add_argument("--stop-on-error", action="store_true")
            sp.add_argument("--screenshots", default=None)
    return p


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    REAL = sys.stdout
    args = build_parser().parse_args()
    sys.stdout = sys.stderr  # 引擎中的 print 全部转到 stderr，保证 stdout 只有一个 JSON
    try:
        payload = COMMANDS[args.command](args)
    except ToolError as e:
        sys.stdout = REAL
        emit(err_payload(args.command, e.code, e.message, e.details), 1)
    except Exception as e:  # noqa: BLE001
        sys.stdout = REAL
        emit(err_payload(args.command, "E_UNEXPECTED", f"{type(e).__name__}: {e}"), 1)
    sys.stdout = REAL
    if payload["ok"]:
        emit(payload, 0)
    code = payload["error"]["code"] if payload.get("error") else ""
    emit(payload, 2 if code == "E_PARTIAL_FAILURE" else 1)


if __name__ == "__main__":
    main()
