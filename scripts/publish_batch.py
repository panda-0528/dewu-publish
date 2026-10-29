#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
得物图文批量自动发布脚本 (跨电脑自适应通用版)
支持自动探测雷电模拟器 ADB、自动安装/启用 AdbKeyboard、动态匹配颜色卡片、不断焦点正文输入与 5 个蓝色话题置底粘贴。
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def find_adb() -> str:
    """跨盘符自动探测 adb.exe 路径并将其目录注入 PATH"""
    existing = shutil.which("adb")
    if existing:
        return existing
    for drive in ("C:", "D:", "E:", "F:"):
        for sub in (
            r"leidian\LDPlayer14\adb.exe",
            r"leidian\LDPlayer9\adb.exe",
            r"leidian\LDPlayer4\adb.exe",
            r"ChangZhi\dnplayer2\adb.exe",
            r"Program Files\leidian\LDPlayer14\adb.exe",
            r"Program Files\leidian\LDPlayer9\adb.exe",
        ):
            candidate = os.path.join(drive + os.sep, sub)
            if os.path.exists(candidate):
                adb_dir = os.path.dirname(candidate)
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
                return candidate
    raise FileNotFoundError(
        "未找到 adb.exe！请确认已安装雷电模拟器，或将 adb.exe 所在目录加入系统环境变量 PATH。"
    )


ADB_PATH = find_adb()
import uiautomator2 as u2  # noqa: E402

THUMB_PTS = [
    (246, 1590),  # 第1张缩略图
    (408, 1590),  # 第2张缩略图
    (570, 1590),  # 第3张缩略图
    (732, 1590),  # 第4张缩略图
    (894, 1590),  # 第5张缩略图
]

CARD_FALLBACK_PTS = [
    (288, 836),   # 左上第1个商品卡图片中心
    (791, 836),   # 右上第2个商品卡图片中心
    (288, 1450),  # 左下第3个商品卡图片中心
    (791, 1450),  # 右下第4个商品卡图片中心
]


def ensure_device_env(adb_path: str, serial: str = "emulator-5554"):
    """检查模拟器连接、关闭三项系统动画、并自动安装/启用 AdbKeyboard"""
    print(f"[Env] 使用 ADB: {adb_path}")
    # 1. 关闭三项动画
    for anim in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        subprocess.run(
            [adb_path, "-s", serial, "shell", "settings", "put", "global", anim, "0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # 2. 检查并安装 AdbKeyboard
    ime_out = subprocess.check_output(
        [adb_path, "-s", serial, "shell", "ime", "list", "-a"],
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if "com.github.uiautomator/.AdbKeyboard" not in ime_out:
        apk_path = os.path.join(os.path.dirname(u2.__file__), "assets", "app-uiautomator.apk")
        print(f"[Env] 首次运行：正在向模拟器安装 AdbKeyboard ({apk_path})...")
        subprocess.run([adb_path, "-s", serial, "push", apk_path, "/sdcard/ime.apk"], check=True)
        subprocess.run([adb_path, "-s", serial, "shell", "pm", "install", "-r", "-t", "/sdcard/ime.apk"], check=True)

    subprocess.run(
        [
            adb_path, "-s", serial, "shell", "settings", "put", "secure",
            "enabled_input_methods",
            "com.android.inputmethod/.latin.LatinIME:com.github.uiautomator/.AdbKeyboard",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [adb_path, "-s", serial, "shell", "ime", "enable", "com.github.uiautomator/.AdbKeyboard"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [adb_path, "-s", serial, "shell", "ime", "set", "com.github.uiautomator/.AdbKeyboard"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def parse_bounds(bounds_str: str):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if not m:
        return None
    return tuple(map(int, m.groups()))


def parse_bounds_center(bounds_str: str):
    b = parse_bounds(bounds_str)
    if not b:
        return None
    x1, y1, x2, y2 = b
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def get_node_attr(xml_str: str, res_id: str, attr: str = "text") -> str:
    root = ET.fromstring(xml_str)
    for node in root.iter("node"):
        if node.attrib.get("resource-id") == res_id:
            return node.attrib.get(attr, "")
    return ""


def find_node_by_text(xml_str: str, target_text: str):
    root = ET.fromstring(xml_str)
    for node in root.iter("node"):
        if node.attrib.get("text") == target_text:
            pt = parse_bounds_center(node.attrib.get("bounds", ""))
            if pt:
                return pt
    return None


def find_product_card_by_color(xml_str: str, color_name: str):
    """
    在「商品」Tab 双列列表中，根据颜色名（如 '本白'、'黑色'）匹配对应卡片的 ivProduct 图片中心坐标。
    避免点到右下角的 '展开^' 按钮。
    """
    root = ET.fromstring(xml_str)
    iv_pts = []
    color_pts = []
    for node in root.iter("node"):
        rid = node.attrib.get("resource-id", "")
        txt = node.attrib.get("text", "")
        pt = parse_bounds_center(node.attrib.get("bounds", ""))
        if not pt:
            continue
        if rid == "com.shizhuang.duapp:id/ivProduct":
            iv_pts.append(pt)
        elif color_name and (txt == color_name or color_name in txt):
            color_pts.append(pt)

    if color_pts and iv_pts:
        cx, cy = color_pts[0]
        # 寻找同一列（|x1 - x2| < 250）且在颜色文字上方最近的 ivProduct 图片中心
        candidates = [
            (abs(ix - cx) + abs(iy - cy), (ix, iy))
            for (ix, iy) in iv_pts
            if abs(ix - cx) < 250 and iy <= cy
        ]
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

    if iv_pts:
        return iv_pts[0]
    return CARD_FALLBACK_PTS[0]


def input_text_keep_focus(d: u2.Device, text: str):
    """直接发 AdbKeyboard Base64 输入广播，不发送 ADB_KEYBOARD_HIDE，保持焦点与末尾光标"""
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    d._must_broadcast("ADB_KEYBOARD_INPUT_TEXT", {"text": b64})


def wait_for_condition(d: u2.Device, desc: str, check_fn, timeout: float = 20.0, poll: float = 0.4) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        xml = d.dump_hierarchy()
        if "下载中" not in xml and check_fn(xml):
            return xml
        time.sleep(poll)
    raise RuntimeError(f"等待超时: {desc}")


def reset_to_home(d: u2.Device):
    """确保回到得物首页 HomeActivity 并关闭任何遮挡弹窗或键盘底栏（纯轻量，不调耗时 dump）"""
    d.hide_keyboard()
    time.sleep(0.2)
    for _ in range(6):
        cur = d.app_current().get("activity", "")
        if "HomeActivity" in cur:
            d.hide_keyboard()
            time.sleep(0.3)
            return
        d.press("back")
        time.sleep(0.5)


def navigate_to_picker(d: u2.Device):
    """从任意状态安全进入相册选图页（固定坐标直通，耗时从30s缩至4s）"""
    cur = d.app_current().get("activity", "")
    if "Album" in cur or "Picker" in cur or "SelectPhoto" in cur:
        return

    reset_to_home(d)

    # 1. 点击底部「我」(899, 1836)
    d.click(899, 1836)
    time.sleep(0.8)
    d.hide_keyboard()
    time.sleep(0.2)

    # 2. 点击「创作中心」(132, 580)
    d.click(132, 580)
    time.sleep(1.2)

    # 3. 点击右上角「+」选图按钮(996, 153)
    d.click(996, 153)
    time.sleep(1.2)


def run_single_post(d: u2.Device, cfg: dict, screenshot_dir: str = None) -> dict:
    timings = {}
    post_t0 = time.perf_counter()
    gid = cfg.get("id", cfg["album"])
    print(f"\n================ 开始发布: {gid} ({cfg['album']}) ================")

    # Step 1: 导航至相册选图页
    t0 = time.perf_counter()
    navigate_to_picker(d)
    timings["Step 1: 导航至相册选图页"] = round(time.perf_counter() - t0, 2)

    # Step 2: 切换相册并勾选全部图片
    t0 = time.perf_counter()
    xml_now = d.dump_hierarchy()
    if "相机胶卷" not in xml_now:
        pt_drop = find_node_by_text(xml_now, "所有照片") or (516, 138)
        d.click(*pt_drop)
        xml_now = wait_for_condition(d, "相册下拉列表", lambda x: cfg["album"] in x, timeout=10.0)

    album_pt = find_node_by_text(xml_now, cfg["album"])
    if not album_pt:
        raise RuntimeError(f"未在下拉列表中找到相册: {cfg['album']}")
    d.click(*album_pt)

    xml_grid = wait_for_condition(
        d, "子相册图片网格", lambda x: "com.shizhuang.duapp:id/ivThumbSelect" in x, timeout=10.0
    )
    root_grid = ET.fromstring(xml_grid)
    check_pts = []
    for node in root_grid.iter("node"):
        if node.attrib.get("resource-id") == "com.shizhuang.duapp:id/ivThumbSelect":
            pt = parse_bounds_center(node.attrib.get("bounds", ""))
            if pt:
                check_pts.append(pt)
    for pt in check_pts:
        d.click(*pt)
        time.sleep(0.35)
    timings[f"Step 2: 切换相册并勾选{len(check_pts)}张图"] = round(time.perf_counter() - t0, 2)

    # Step 3: 点击下一步进入预览页
    t0 = time.perf_counter()
    d.click(850, 1830)
    time.sleep(1.0)
    wait_for_condition(d, "图片预览页", lambda x: "com.shizhuang.duapp:id/ivTag" in x, timeout=15.0)
    timings["Step 3: 进入图片预览页"] = round(time.perf_counter() - t0, 2)

    # Step 4: 第1张图搜索货号并关联对应颜色好物
    t0 = time.perf_counter()
    d.click(69, 1788)
    time.sleep(1.5)
    d.click(540, 382)
    time.sleep(0.6)
    d.send_keys(cfg["code"])
    time.sleep(0.8)
    d.shell("input keyevent 66")  # 原生回车键，杜绝 u2 广播 60s 超时
    time.sleep(1.0)
    xml_prod = ""
    for _ in range(3):
        d.click(405, 510)  # 商品 Tab
        poll_deadline = time.time() + 6.0
        while time.time() < poll_deadline:
            time.sleep(0.6)
            xml_prod = d.dump_hierarchy()
            if "com.shizhuang.duapp:id/ivProduct" in xml_prod:
                break
        if "com.shizhuang.duapp:id/ivProduct" in xml_prod:
            break
        # 搜索结果未加载：重新回车触发
        d.shell("input keyevent 66")
        time.sleep(1.0)
    if "com.shizhuang.duapp:id/ivProduct" not in xml_prod:
        raise RuntimeError("等待超时: 商品搜索结果未加载")
    color_pt = cfg.get("color_pt")
    if color_pt:
        target_pt = tuple(color_pt)
    else:
        target_pt = find_product_card_by_color(xml_prod, cfg.get("color_name", ""))
    d.click(*target_pt)
    time.sleep(1.2)
    timings[f"Step 4: 图1搜货号关联「{cfg.get('color_name', '默认')}」"] = round(time.perf_counter() - t0, 2)

    # Step 5: 其余图片通过历史标签1关联好物（纯固定坐标与精准延迟，彻底砍掉多余 dump）
    t0 = time.perf_counter()
    for idx in range(1, len(check_pts)):
        d.click(*THUMB_PTS[idx])
        time.sleep(0.6)
        d.click(69, 1788)
        time.sleep(0.7)
        d.click(379, 626)
        time.sleep(0.7)
    timings[f"Step 5: 其余{len(check_pts)-1}张图关联历史标签"] = round(time.perf_counter() - t0, 2)

    # Step 6: 点击下一步进入文案编辑页
    t0 = time.perf_counter()
    d.click(918, 1788)
    time.sleep(1.2)
    timings["Step 6: 进入文案编辑页"] = round(time.perf_counter() - t0, 2)

    # Step 7: 填写标题
    t0 = time.perf_counter()
    d.click(540, 567)
    time.sleep(0.4)
    d.send_keys(cfg["title"])
    time.sleep(0.4)
    timings["Step 7: 填写标题"] = round(time.perf_counter() - t0, 2)

    # Step 8: 填写正文（保持焦点不断开）
    t0 = time.perf_counter()
    d.click(540, 648)
    time.sleep(0.4)
    body_clean = cfg["body"].rstrip("\n") + "\n"
    input_text_keep_focus(d, body_clean)
    time.sleep(0.5)
    timings["Step 8: 填写正文(保持焦点)"] = round(time.perf_counter() - t0, 2)

    # Step 9: 文末粘贴最多5个蓝色话题
    t0 = time.perf_counter()
    for t in cfg["topics"][:5]:
        t_str = t if t.startswith("#") else f"#{t}"
        d.set_clipboard(t_str)
        time.sleep(0.05)
        d.shell("input keyevent 279")
        time.sleep(0.5)
        input_text_keep_focus(d, " ")
        time.sleep(0.2)
    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)
        d.screenshot(os.path.join(screenshot_dir, f"{gid}_before_publish.png"))
    timings["Step 9: 粘贴5个蓝色话题"] = round(time.perf_counter() - t0, 2)

    # Step 10: 收起键盘并点击发布回首页
    t0 = time.perf_counter()
    d.hide_keyboard()
    time.sleep(0.5)
    d.click(615, 1806)
    deadline = time.time() + 15.0
    while time.time() < deadline:
        if "HomeActivity" in d.app_current().get("activity", ""):
            break
        time.sleep(0.4)
    if screenshot_dir:
        d.screenshot(os.path.join(screenshot_dir, f"{gid}_published.png"))
    timings["Step 10: 收起键盘并点击发布"] = round(time.perf_counter() - t0, 2)

    total_sec = round(time.perf_counter() - post_t0, 2)
    timings["单条总耗时 (Total)"] = total_sec
    print(f"================ {gid} 发布完成！总耗时: {total_sec}s ================")
    return timings


DEFAULT_GROUPS = [
    {
        "id": "group01",
        "code": "UWM160041",
        "album": "UWM160041-group01",
        "color_name": "本白",
        "title": "救命！UR这件白月光神衣显瘦绝了😭",
        "body": (
            "秋冬不想穿成米其林的姐妹直接锁死这件！\n"
            "修身立领拼接设计太懂女生了，一秒掐出小蛮腰✨"
            "配条卡其阔腿裤，干净清爽的韩系白月光感拉满，保暖不臃肿，谁穿谁好看！\n"
        ),
        "topics": ["#秋冬穿搭测评", "#显瘦穿搭", "#韩系穿搭", "#每日穿搭", "#UR穿搭"],
    },
    {
        "id": "group02",
        "code": "UWM160041",
        "album": "UWM160041-group02",
        "color_name": "黑色",
        "title": "挖到宝了！这件黑武士拼接外套酷到犯规🖤",
        "body": (
            "今年秋冬Cleanfit天花板被我找到了！\n"
            "这件黑色立领拼接外套版型太绝，修身收腰完全不显胖，视觉立减十斤🔥"
            "配条白裤子和格纹围巾，甜酷高级感拿捏得死死的，日常通勤必入！\n"
        ),
        "topics": ["#Cleanfit穿搭", "#秋冬外套种草", "#甜酷风穿搭", "#显瘦神衣", "#日常通勤穿搭"],
    },
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="得物图文批量自动发布脚本")
    parser.add_argument("--serial", default="emulator-5554", help="ADB 设备序列号 (默认 emulator-5554)")
    parser.add_argument("--config", help="JSON 配置文件路径 (不传则运行内置示例批次)")
    parser.add_argument("--screenshots", default=None, help="保存验证截图的目录")
    args = parser.parse_args()

    ensure_device_env(ADB_PATH, args.serial)
    d = u2.connect(args.serial)
    d.set_input_ime(True)

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            groups = json.load(f)
    else:
        groups = DEFAULT_GROUPS

    reset_to_home(d)
    results = {}
    t_batch = time.perf_counter()
    for i, cfg in enumerate(groups):
        gid = cfg.get("id", f"post_{i+1}")
        results[gid] = run_single_post(d, cfg, args.screenshots)
        if i < len(groups) - 1:
            time.sleep(3.5)
    results["batch_total_sec"] = round(time.perf_counter() - t_batch, 2)
    print("\n📊 批量发布耗时汇总:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
