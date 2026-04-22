import asyncio
import os
import sys
import random
import io
import time
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ================= 终端编码修复 =================
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class HzzhBot:
    """宏志助航 自动学习助手 (多标签并发版)"""
    
    # --- 核心配置 ---
    TARGET_URL = "https://hzzh.chsi.com.cn/kc/"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    USER_DATA_DIR = os.path.join(os.getcwd(), "user_data")
    
    # --- 选择器定义 ---
    SELECTORS = {
        "video": "video",
        "play_buttons": [
            ".prism-big-play-btn", ".prism-play-btn", ".vjs-big-play-button",
            "button[aria-label='Play']", ".play-btn"
        ],
        "popup_buttons": ["继续学习", "确定", "确认", "我知道了", "开始学习", "关闭"],
        "popup_elements": "button:visible, div[role='button']:visible, .el-message-box__btns button, .el-dialog__headerbtn"
    }

    def __init__(self):
        self.browser_context = None
        self.stealth = Stealth()

    def logger(self, msg, level="INFO", tab_id="SYS"):
        """日志输出，增加 tab_id 以支持多标签区分"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        print(f"[{timestamp}] [{level}] [{tab_id}] {msg}")

    async def init_browser(self):
        """初始化"""
        self.logger("正在启动浏览器...")
        p = await async_playwright().start()
        
        launch_args = {
            "user_data_dir": self.USER_DATA_DIR,
            "headless": False,
            "user_agent": self.USER_AGENT,
            "no_viewport": True,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--mute-audio"]
        }

        try:
            self.browser_context = await p.chromium.launch_persistent_context(channel="chrome", **launch_args)
        except Exception:
            self.browser_context = await p.chromium.launch_persistent_context(channel="msedge", **launch_args)

        # 默认页
        page = self.browser_context.pages[0] if self.browser_context.pages else await self.browser_context.new_page()
        await self.stealth.apply_stealth_async(page)
        
        self.logger(f"已跳转至主入口: {self.TARGET_URL}")
        try:
            await page.goto(self.TARGET_URL, wait_until="load", timeout=60000)
        except:
            pass

    async def process_page(self, page, index):
        """处理单个标签页的逻辑"""
        url = page.url
        title = await page.title()
        tab_name = f"Tab-{index}"
        
        # 仅监控课程相关页面
        if "/kc/" not in url:
            return False

        has_activity = False
        try:
            # 1. 扫描视频 (主界面与 Iframe)
            frames_to_check = [page] + page.frames
            for i, frame in enumerate(frames_to_check):
                name = "主窗" if frame == page else f"F-{i}"
                if await self._check_video_in_frame(frame, f"{tab_name}:{name}"):
                    has_activity = True

            # 2. 扫描弹窗
            if await self._handle_popups_in_page(page, tab_name):
                has_activity = True
                
        except Exception as e:
            # 忽略因标签页关闭导致的错误
            pass
        return has_activity

    async def _check_video_in_frame(self, frame, name):
        """帧内视频检查"""
        try:
            videos = await frame.query_selector_all(self.SELECTORS["video"])
            for vid in videos:
                await vid.evaluate("v => { v.muted = true; v.volume = 0; }")
                if await vid.evaluate("v => v.paused"):
                    self.logger("发现视频暂停，尝试恢复...", "监控", name)
                    await vid.evaluate("v => v.play().catch(e => {})")
                    await asyncio.sleep(1)
                    
                    if await vid.evaluate("v => v.paused"):
                        for selector in self.SELECTORS["play_buttons"]:
                            btn = await frame.query_selector(selector)
                            if btn and await btn.is_visible():
                                await btn.click()
                                break
                return True
        except:
            pass
        return False

    async def _handle_popups_in_page(self, page, tab_id):
        """页面弹窗检查"""
        try:
            btns = await page.query_selector_all(self.SELECTORS["popup_elements"])
            for btn in btns:
                if not await btn.is_visible(): continue
                text = (await btn.inner_text()).strip()
                
                # 关闭图标处理
                if not text:
                    cls = await btn.get_attribute("class")
                    if cls and any(k in cls for k in ["close", "btn-close", "headerbtn"]):
                        self.logger(f"点击关闭图标 (Class: {cls})", "动作", tab_id)
                        await btn.click()
                        return True
                
                # 文本按钮处理
                if any(key in text for key in self.SELECTORS["popup_buttons"]):
                    self.logger(f"点击确认按钮「{text}」", "动作", tab_id)
                    await btn.click()
                    return True
        except:
            pass
        return False

    async def run(self):
        """多标签并行调度循环"""
        await self.init_browser()
        
        print("\n" + "="*50)
        print("  宏志助航 自动学习助手 (多标签并行版)")
        print("="*50)
        print("[操作] 你可以在当前 Chrome 中右键课程，“在新标签页中打开”多个课程。")
        print("[操作] 脚本会自动遍历所有标签页并保持它们的播放状态。")
        print("="*50 + "\n")

        while True:
            pages = self.browser_context.pages
            for i, page in enumerate(pages):
                try:
                    await self.process_page(page, i)
                except:
                    continue
            
            # 自适应心跳：页面越多，循环越快以保证响应速度
            wait_time = max(1.0, 3.0 - len(pages) * 0.5)
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    if not os.path.exists(HzzhBot.USER_DATA_DIR): os.makedirs(HzzhBot.USER_DATA_DIR)
    bot = HzzhBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n[退出] 脚本已停止。")
    except Exception as e:
        print(f"\n[意外错误] {e}")
