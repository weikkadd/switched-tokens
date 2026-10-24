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
    """获取当前已获得的金币数量（用 Selenium 原生 API 代替 JS execute_script）"""
    try:
        body_text = sb.get_text("body")
        m = re.search(r'(\d+)\s*of\s*(\d+)', body_text)
        if m:
            count = int(m.group(1))
            log(f"当前金币: {count}/{m.group(2)}")
            return count
        log(f"金币检测: body 无 'N of M'，前 200 字符: {body_text[:200]}")
        return -1
    except Exception as e:
        log_warn(f"获取金币数量失败: {e}")
        return -1

def earn_with_vylo(sb) -> bool:
    """点击 'Earn with Vylo' → vylo.cc 新标签页 → PoW+Turnstile+Continue → 金币+2"""
    from selenium.webdriver.common.by import By
    try:
        time.sleep(3)

        original_window = sb.driver.current_window_handle

        # 1. 找并点击 "Earn with Vylo/Linkvertise" 按钮
        elements = sb.find_elements(By.CSS_SELECTOR,
            "button, a, [role=button], [onclick], [href], [class*='earn'], [class*='link'], [class*='unlock'], [class*='claim']")
        earn_els = []
        for el in elements:
            try:
                text = el.text.strip()
                tl = text.lower()
                if text and len(text) < 100:
                    if any(kw in tl for kw in ['earn', 'vylo', 'linkvertise', 'unlock', 'claim', 'get link', 'watch ad']):
                        earn_els.append(el)
            except:
                pass

        clicked = False
        for el in earn_els:
            try:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    log(f"✅ 点击: {el.text.strip()[:60]}")
                    clicked = True
                    break
            except:
                pass
        if not clicked:
            log_warn("未找到 Earn with Vylo 按钮")
            return False

        # 2. 等待新标签页打开（vylo.cc 短链接）
        time.sleep(6)
        handles = sb.driver.window_handles
        if len(handles) <= 1:
            log_warn("新标签页未打开")
            return False

        new_window = [h for h in handles if h != original_window][0]
        sb.driver.switch_to.window(new_window)
        time.sleep(4)
        ad_url = sb.get_current_url()
        log(f"广告页: {ad_url[:80]}")

        # 3. 如果是 linkvertise.com（非 vylo.cc），先点 "Get access" 等跳转到 vylo.cc
        if "vylo.cc" not in ad_url:
            log(f"linkvertise.com 中间页，找 Get access 按钮...")
            for step in range(30):
                try:
                    cur = sb.get_current_url()
                    if "vylo.cc" in cur:
                        log(f"✅ 已跳转到 vylo.cc: {cur[:60]}")
                        break
                except:
                    pass
                try:
                    btns = sb.find_elements(By.CSS_SELECTOR, "button, a, [role=button], input[type=submit]")
                    for b in btns:
                        try:
                            bt = b.text.strip().lower()
                            if 'get access' in bt or 'get started' in bt or 'continue' in bt:
                                try:
                                    b.click()
                                except:
                                    sb.execute_script("arguments[0].click()", b)
                                log(f"  中间页点击: {b.text.strip()[:40]}")
                                time.sleep(5)
                                break
                        except:
                            pass
                except:
                    pass
                time.sleep(2)

        # 4. 注入 navigator.webdriver = false（确保 PoW 运行）
        try:
            sb.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
            log("已注入 navigator.webdriver=false")
        except:
            pass

        # 4. 等待 PoW 完成（input[name="pw"] 有值）
        log("等待 PoW 计算...")
        pw_done = False
        for i in range(60):
            try:
                pw = sb.execute_script("var e=document.querySelector('input[name=\"pw\"]');return e?e.value:'';")
                if pw and pw.strip():
                    log(f"✅ PoW 完成: pw={pw[:20]}")
                    pw_done = True
                    break
            except:
                pass
            time.sleep(1)
        if not pw_done:
            log_warn("PoW 超时（60s），尝试手动计算...")
            try:
                proof = sb.execute_script("return document.querySelector('form[data-proof]')?.dataset.proof || '';")
                bits = int(sb.execute_script("return document.querySelector('form[data-bits]')?.dataset.bits || 16;") or 16)
                if proof:
                    import hashlib
                    n = 0
                    while n < 5000000:
                        h = hashlib.sha256(f"{proof}:{n}".encode()).digest()
                        if int.from_bytes(h[:4], 'big') >> (32 - bits) == 0:
                            sb.execute_script(f"document.querySelector('input[name=\"pw\"]').value='{n}';")
                            log(f"✅ Python PoW: n={n}")
                            pw_done = True
                            break
                        n += 1
            except Exception as e:
                log_warn(f"Python PoW 失败: {e}")

        # 5. 等待 Turnstile 完成（button disabled 消失）
        log("等待 Turnstile...")
        for i in range(90):
            try:
                disabled = sb.execute_script(
                    "var b=document.querySelector('form#step1 button[type=\"submit\"]');"
                    "return b?b.disabled:true;")
                if not disabled:
                    log(f"✅ Turnstile 完成 ({i}s)")
                    break
            except:
                pass
            time.sleep(1)
        else:
            log_warn("Turnstile 超时（90s）")

        # 6. 关闭广告弹窗（找 close 按钮）
        try:
            close_btns = sb.find_elements(By.CSS_SELECTOR, "[data-close-sticky], .ad-close, [aria-label*='lose']")
            for b in close_btns:
                try:
                    b.click()
                    log("已关闭广告弹窗")
                    break
                except:
                    pass
        except:
            pass

        # 7. 点击 Continue 按钮（form#step1 submit）
        time.sleep(2)
        try:
            btn = sb.find_element(By.CSS_SELECTOR, 'form#step1 button[type="submit"]')
            try:
                btn.click()
            except:
                sb.execute_script("arguments[0].click()", btn)
            log("✅ 点击 Continue")
        except Exception as e:
            log_warn(f"Continue 按钮点击失败: {e}")
            try:
                sb.execute_script("document.querySelector('form#step1').requestSubmit();")
                log("✅ JS requestSubmit")
            except:
                pass

        # 8. 等待跳转离开 vylo.cc（最多 30s）
        log("等待广告跳转...")
        for i in range(30):
            time.sleep(2)
            try:
                cur = sb.get_current_url()
                if "vylo.cc" not in cur and "linkvertise" not in cur.lower():
                    log(f"✅ 已跳转: {cur[:80]}")
                    break
            except:
                pass
        else:
            log_warn(f"未跳转，当前: {sb.get_current_url()[:80]}")

        # 9. 关闭广告标签页，切回 switched.cloud
        try:
            sb.driver.close()
        except:
            pass
        try:
            sb.driver.switch_to.window(original_window)
        except:
            pass
        log("已返回 switched.cloud")

        # 10. 等待金币结算
        time.sleep(5)
        sb.open(f"{BASE_URL}/tokens")
        sb.wait_for_ready_state_complete()
        time.sleep(3)
        return True

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