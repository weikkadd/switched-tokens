#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Linkvertise 网络请求捕获辅助脚本
手动登录 switched.cloud → 点 Earn with Linkvertise → 完成广告
脚本自动记录所有网络请求到 captured_requests.txt
"""

import time, json, re
from seleniumbase import SB
from selenium.webdriver.common.by import By

LOG_FILE = "captured_requests.txt"
BASE_URL = "https://panel.switched.cloud"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"{ts} {msg}", flush=True)

def extract_requests(sb, all_logs):
    """从 performance logs 提取网络请求"""
    try:
        perf_logs = sb.driver.get_log("performance")
    except Exception:
        return
    for entry in perf_logs:
        try:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method", "")
            params = msg.get("params", {})
            if method == "Network.requestWillBeSent":
                req = params.get("request", {})
                url = req.get("url", "")
                m = req.get("method", "GET")
                rid = params.get("requestId", "")
                if any(kw in url for kw in ["linkvertise", "switched.cloud", "/api/"]):
                    all_logs[rid] = {"url": url, "method": m, "status": None, "response": None}
            elif method == "Network.responseReceived":
                rid = params.get("requestId", "")
                if rid in all_logs:
                    resp = params.get("response", {})
                    all_logs[rid]["status"] = resp.get("status", "")
                    all_logs[rid]["type"] = resp.get("mimeType", "")
        except Exception:
            pass

def save_logs(all_logs):
    """保存请求到文件"""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("Linkvertise 网络请求捕获结果\n")
        f.write(f"捕获时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        for rid, info in all_logs.items():
            if info.get("status") is None and "api" not in info["url"].lower():
                continue
            f.write(f"[{info['method']}] {info.get('status', '?')} {info['url']}\n")
            if info.get("type"):
                f.write(f"  Type: {info['type']}\n")
            f.write("\n")
    log(f"已保存 {len(all_logs)} 个请求到 {LOG_FILE}")

def run():
    log("=" * 60)
    log("Linkvertise 网络请求捕获脚本")
    log("=" * 60)
    log("操作步骤：")
    log("1. 脚本会打开 Chrome，导航到 switched.cloud")
    log("2. 你手动登录（Discord 或 Cookie）")
    log("3. 去 /tokens 页面，点 Earn with Linkvertise")
    log("4. 手动完成广告（点 Get access → Get Started → 等倒计时 → Continue）")
    log("5. 完成后回到终端按 Enter，脚本保存所有请求")
    log("=" * 60)

    all_logs = {}
    last_count = 0

    with SB(uc=True, headless=False, chromium_arg=[
        "--enable-logging",
        "--log-level=0",
    ]) as sb:
        sb.driver.execute_cdp_cmd("Network.enable", {})

        sb.open(f"{BASE_URL}/login")
        log("已打开 switched.cloud 登录页，请在浏览器中操作...")
        log("完成广告后回到这里按 Enter")

        try:
            input("\n>>> 广告完成后按 Enter 键保存请求 <<<\n")
        except (EOFError, KeyboardInterrupt):
            pass

        extract_requests(sb, all_logs)
        save_logs(all_logs)

        if not all_logs:
            log("未捕获到任何请求！可能 performance logs 未启用")
            log("备选方案：手动复制浏览器 F12 Network 的请求")

    log("完成！请把 captured_requests.txt 发给我")

if __name__ == "__main__":
    run()