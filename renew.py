#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""switched.cloud 自动获取金币（tokens）脚本
Discord OAuth 登录 + 自动点击 "Earn with Vylo" 刷金币
每天上限 25 个
"""

import os, sys, time, re, json, requests, urllib.parse
from seleniumbase import SB

# ======================== 环境变量 ========================
DISCORD_TOKEN  = os.environ.get("DISCORD_TOKEN", "")        # Discord Token
SWITCHED_COOKIE = os.environ.get("SWITCHED_COOKIE", "")      # switched.cloud Cookie（备用，优先用 Discord 登录）
TG_BOT_TOKEN   = os.environ.get("TG_BOT_TOKEN", "")          # TG bot token（可选）
TG_CHAT_ID     = os.environ.get("TG_CHAT_ID", "")            # TG chat id（可选）
MAX_TOKENS     = int(os.environ.get("MAX_TOKENS", "25"))     # 每天上限
AD_WAIT        = int(os.environ.get("AD_WAIT", "120"))       # 单次广告等待秒数
COOLDOWN       = int(os.environ.get("COOLDOWN", "5"))        # 每次间隔秒数
IS_PROXY       = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER   = os.environ.get("PROXY_SERVER", "").strip() or "socks5://127.0.0.1:1080"

BASE_URL = "https://panel.switched.cloud"
DISCORD_API = "https://discord.com/api/v9/oauth2/authorize"
DISCORD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

# ======================== 日志 ========================
def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"{ts} [INFO] {msg}", flush=True)

def log_warn(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"{ts} [WARNING] {msg}", flush=True)

# ======================== Telegram 通知 ========================
def tg(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
    except Exception:
        pass

# ======================== Discord OAuth 登录 ========================
def do_discord_login(sb) -> bool:
    """通过 Discord OAuth 登录 switched.cloud"""
    if not DISCORD_TOKEN:
        log_warn("未配置 DISCORD_TOKEN，尝试 Cookie 登录...")
        return do_cookie_login(sb)

    try:
        # 1. 打开 switched.cloud 登录页
        sb.open(f"{BASE_URL}/login")
        sb.wait_for_ready_state_complete()
        time.sleep(3)

        # 2. 查找并点击 Discord 登录按钮
        login_selectors = [
            'a[href*="discord"]',
            'a[href*="/api/discord"]',
            'button:contains("Discord")',
            'a:contains("Discord")',
        ]
        clicked = False
        for sel in login_selectors:
            try:
                if sb.is_element_visible(sel):
                    sb.click(sel)
                    clicked = True
                    log(f"✅ 点击 Discord 登录按钮: {sel}")
                    break
            except Exception:
                pass

        if not clicked:
            log_warn("未找到 Discord 登录按钮")
            return False

        time.sleep(5)
        current_url = sb.get_current_url()

        # 3. 如果跳转到 Discord 授权页，用 DISCORD_TOKEN 完成授权
        if "discord.com" in current_url:
            log("已到达 Discord 授权页，使用 DISCORD_TOKEN 完成授权...")
            # 从当前 URL 提取授权 URL
            authorize_url = current_url
            if "redirect_to" in current_url:
                m = re.search(r'redirect_to=(.+)', current_url)
                if m:
                    authorize_url = f"https://discord.com{urllib.parse.unquote(m.group(1))}"

            # 用 DISCORD_TOKEN 调 Discord API 完成授权
            location = discord_authorize(authorize_url)
            if not location:
                log_warn("Discord 授权失败")
                return False

            # 4. 浏览器打开回调 URL
            sb.open(location)
            sb.wait_for_ready_state_complete()
            time.sleep(5)

        # 5. 检查是否登录成功
        current_url = sb.get_current_url()
        if "panel.switched.cloud" in current_url and "/login" not in current_url:
            log("✅ Discord 登录成功")
            return True

        log_warn(f"登录后未到达面板，当前 URL: {current_url}")
        return False

    except Exception as e:
        log_warn(f"Discord 登录异常: {e}")
        return False

def discord_authorize(authorize_url: str) -> str:
    """用 DISCORD_TOKEN 调 Discord API 完成授权，返回回调 URL"""
    proxies = None
    if IS_PROXY:
        proxies = {"http": PROXY_SERVER, "https": PROXY_SERVER}

    # 转换为 API 端点
    if "/oauth2/authorize" in authorize_url and "/api/v9/" not in authorize_url:
        parsed = urllib.parse.urlparse(authorize_url)
        authorize_url = f"https://discord.com/api/v9/oauth2/authorize?{parsed.query}"

    try:
        headers = {
            "Authorization": DISCORD_TOKEN,
            "Content-Type": "application/json",
            "User-Agent": DISCORD_UA,
            "Referer": authorize_url,
        }
        body = json.dumps({
            "permissions": "0",
            "authorize": True,
        })
        resp = requests.post(authorize_url, headers=headers, data=body,
                             proxies=proxies, timeout=20)
        if resp.status_code != 200:
            log_warn(f"Discord 授权失败: HTTP {resp.status_code} - {resp.text[:200]}")
            return ""
        data = resp.json()
        location = data.get("location", "")
        if location:
            log("✅ Discord 授权成功，拿到回调 URL")
            return location
        log_warn(f"Discord 授权响应无 location: {data}")
        return ""
    except Exception as e:
        log_warn(f"Discord 授权异常: {e}")
        return ""

def do_cookie_login(sb) -> bool:
    """用 Cookie 直接登录"""
    if not SWITCHED_COOKIE:
        log_warn("未配置 SWITCHED_COOKIE")
        return False
    try:
        sb.open(f"{BASE_URL}/")
        sb.wait_for_ready_state_complete()
        time.sleep(2)
        for pair in SWITCHED_COOKIE.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                try:
                    sb.add_cookie({"name": k.strip(), "value": v.strip(),
                                   "domain": ".switched.cloud", "path": "/"})
                except Exception:
                    pass
        sb.open(f"{BASE_URL}/tokens")
        sb.wait_for_ready_state_complete()
        time.sleep(3)
        url = sb.get_current_url()
        if "/login" not in url:
            log("✅ Cookie 登录成功")
            return True
        log_warn("Cookie 登录失败")
        return False
    except Exception as e:
        log_warn(f"Cookie 登录异常: {e}")
        return False

# ======================== 金币获取 ========================
def get_token_count(sb) -> int:
    """获取当前已获得的金币数量"""
    try:
        result = sb.execute_script("""
        (function(){
            // 策略1: 匹配 'N of M' 格式
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var t = (all[i].innerText || '').trim();
                if (t.length > 0 && t.length < 100) {
                    var m = t.match(/(\\d+)\\s*of\\s*(\\d+)/i);
                    if (m) return m[1] + '/' + m[2];
                }
            }
            // 策略2: 查找金币相关 class
            var el = document.querySelector('[class*="token"], [class*="coin"], [class*="balance"], [class*="credit"]');
            if (el) return 'class:' + el.innerText.trim();
            // 策略3: 返回页面 body 前 500 字符用于诊断
            return 'body:' + (document.body.innerText || '').substring(0, 500);
        })();
        """)
        if result and result != '-1':
            log(f"金币检测: {str(result)[:200]}")
            m = re.match(r'(\d+)', str(result))
            if m:
                return int(m.group(1))
        return -1
    except Exception as e:
        log_warn(f"获取金币数量失败: {e}")
        return -1

def earn_with_vylo(sb) -> bool:
    """点击 'Earn with Vylo' 按钮，等待广告完成返回"""
    try:
        # 先打印页面所有可点击元素的文字（诊断）
        page_info = sb.execute_script("""
        (function(){
            var info = [];
            var els = document.querySelectorAll('button, a, [role=button], [onclick], [href], [class*="btn"], [class*="button"], [class*="earn"], [class*="vylo"]');
            for (var i = 0; i < els.length && i < 30; i++) {
                var el = els[i];
                var t = (el.innerText || el.textContent || '').trim();
                if (t.length > 0 && t.length < 100) {
                    info.push(el.tagName + ': ' + t.substring(0, 60));
                }
            }
            return info.join(' | ');
        })();
        """)
        log(f"页面可点击元素: {str(page_info)[:300]}")

        # 放宽查找：搜索所有元素含 vylo/earn/get link/unlock/claim
        result = sb.execute_script("""
        (function(){
            var candidates = document.querySelectorAll('button, a, [role=button], [onclick], [href], [class*="btn"], [class*="button"], [class*="earn"], [class*="vylo"], div[onclick], span[onclick]');
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                var t = (el.innerText || el.textContent || '').trim().toLowerCase();
                if (t.indexOf('vylo') !== -1 || t.indexOf('earn') !== -1 ||
                    t.indexOf('get link') !== -1 || t.indexOf('unlock') !== -1 ||
                    t.indexOf('claim') !== -1 || t.indexOf('watch') !== -1) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && !el.disabled) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return 'clicked:' + t.substring(0, 60);
                    }
                }
            }
            return 'not_found';
        })();
        """)
        if not result or not str(result).startswith("clicked:"):
            log_warn(f"未找到 'Earn with Vylo' 按钮: {result}")
            return False
        log(f"✅ 点击按钮: {result}")

        # 等待广告完成（检测返回 tokens 页面或新标签页关闭）
        for i in range(AD_WAIT):
            time.sleep(1)
            try:
                url = sb.get_current_url()
                # 如果返回了 tokens 页面，说明广告完成
                if "panel.switched.cloud" in url and "/tokens" in url:
                    log(f"✅ 广告完成，已返回 tokens 页面 ({i}s)")
                    return True
                # 如果在 Vylo 广告页，继续等待
                if i % 15 == 0 and i > 0:
                    log(f"等待广告完成... ({i}s) URL: {url[:80]}")
            except Exception:
                pass

        # 超时后尝试手动返回 tokens 页面
        log_warn(f"广告等待超时 ({AD_WAIT}s)，尝试返回 tokens 页面...")
        sb.open(f"{BASE_URL}/tokens")
        sb.wait_for_ready_state_complete()
        time.sleep(3)
        return True  # 即使超时也返回 True，让脚本检查金币是否增加

    except Exception as e:
        log_warn(f"Earn with Vylo 失败: {e}")
        return False

# ======================== 主函数 ========================
def run():
    log("=" * 60)
    log("switched.cloud 自动获取金币脚本启动")
    log(f"每日上限: {MAX_TOKENS} | 广告等待: {AD_WAIT}s | 间隔: {COOLDOWN}s")
    log("=" * 60)

    with SB(uc=True, headless=False) as sb:
        # 1. 登录
        if not do_discord_login(sb):
            log("❌ 登录失败，退出")
            tg("❌ switched.cloud 登录失败")
            return

        # 2. 导航到 tokens 页面
        sb.open(f"{BASE_URL}/tokens")
        sb.wait_for_ready_state_complete()
        time.sleep(5)

        # 2.5 诊断：打印当前 URL + 页面标题 + body 前 300 字符
        try:
            cur_url = sb.get_current_url()
            cur_title = sb.get_title()
            body_text = sb.execute_script("return (document.body.innerText || '').substring(0, 300);")
            log(f"当前 URL: {cur_url}")
            log(f"页面标题: {cur_title}")
            log(f"页面内容: {str(body_text)[:200]}")
        except Exception as e:
            log_warn(f"页面诊断失败: {e}")

        # 3. 获取初始金币数量
        initial_count = get_token_count(sb)
        log(f"初始金币: {initial_count}")

        if initial_count >= MAX_TOKENS:
            log(f"已达每日上限 {MAX_TOKENS}，无需刷金币")
            tg(f"switched.cloud 金币已满\n当前: {initial_count}/{MAX_TOKENS}")
            return

        # 4. 循环刷金币
        earned = 0
        fail_count = 0
        for i in range(MAX_TOKENS):
            current = get_token_count(sb)
            if current >= MAX_TOKENS:
                log(f"已达每日上限 {MAX_TOKENS}，停止")
                break

            if fail_count >= 5:
                log_warn("连续失败 5 次，停止")
                break

            log(f"--- 尝试获取第 {current + 1}/{MAX_TOKENS} 个金币 ---")

            if not earn_with_vylo(sb):
                log_warn(f"第 {i+1} 次获取失败")
                fail_count += 1
                sb.open(f"{BASE_URL}/tokens")
                sb.wait_for_ready_state_complete()
                time.sleep(5)
                continue

            # 检查金币是否增加
            time.sleep(2)
            new_count = get_token_count(sb)
            if new_count > current:
                earned += 1
                fail_count = 0
                log(f"✅ 金币增加！{current} → {new_count}（本次 +{new_count - current}）")
            else:
                log_warn(f"金币未增加: {current} → {new_count}")
                fail_count += 1

            time.sleep(COOLDOWN)
            sb.open(f"{BASE_URL}/tokens")
            sb.wait_for_ready_state_complete()
            time.sleep(2)

        # 5. 收尾
        final_count = get_token_count(sb)
        msg = (f"switched.cloud 金币获取完成\n"
               f"初始: {initial_count}\n"
               f"最终: {final_count}/{MAX_TOKENS}\n"
               f"本次获取: {earned}")
        log(msg)
        tg(msg)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log("用户中断")
    except Exception as e:
        log_warn(f"未捕获异常: {e}")
        tg(f"❌ switched.cloud 金币脚本崩溃\n{e}")
        sys.exit(1)