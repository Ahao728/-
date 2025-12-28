# taobao_ui_optimized.py
# UI 优化版 - 核心逻辑与原版保持一致

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import time
import pickle
import os
import webbrowser
from datetime import datetime
from random import uniform

# 尝试导入 Selenium，如果用户未安装则提示
try:
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    import sys
    print("错误: 未检测到 Selenium 库。请在终端运行: pip install selenium")
    # 为了让程序能跑起来显示个错误弹窗（虽然没有 selenium 没法用）
    webdriver = None


COOKIE_FILE = "taobao_cookies.pkl"
DEFAULT_KEYWORDS = "泡泡玛特, 盲盒"
DEFAULT_TIME = "22:00:00"
DEFAULT_CONFIRM_INTERVAL = 0.5  # 太小会被拒绝，建议 0.5~1.0 秒
DEFAULT_MAX_CONFIRM_ATTEMPTS = 200

class TaobaoSniper:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("淘宝秒杀助手 Pro")
        self.root.geometry("800x800")

        style = ttk.Style()
        style.theme_use('clam')

        self.driver = None
        self.stop_flag = False
        self.monitor_thread = None
        self.confirm_thread = None
        self.init_lock = threading.Lock()  # 防止并发初始化

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # === 主容器，带一点内边距 ===
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ==========================================================
        # 区域 1: 目标设置 (Target Settings)
        # ==========================================================
        group_target = ttk.LabelFrame(main_frame, text=" 🎯 目标设置 ", padding="10")
        group_target.pack(fill=tk.X, pady=(0, 10))

        # 行 0: 关键字
        ttk.Label(group_target, text="商品关键字:").grid(row=0, column=0, sticky="w", padx=5)
        self.entry_keywords = ttk.Entry(group_target, width=60)
        self.entry_keywords.insert(0, DEFAULT_KEYWORDS)
        self.entry_keywords.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        # 提示标签
        ttk.Label(group_target, text="(逗号分隔，如: 手机, 黑色)", foreground="gray").grid(row=0, column=2, sticky="w")

        # 行 1: 抢购时间
        ttk.Label(group_target, text="抢购时间:").grid(row=1, column=0, sticky="w", padx=5)
        self.entry_time = ttk.Entry(group_target, width=20)
        self.entry_time.insert(0, DEFAULT_TIME)
        self.entry_time.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(group_target, text="(格式 HH:MM:SS)", foreground="gray").grid(row=1, column=1, padx=(160, 0), sticky="w")

        group_target.columnconfigure(1, weight=1) # 让输入框自动拉伸

        # ==========================================================
        # 区域 2: 驱动设置 (Driver Settings)
        # ==========================================================
        group_driver = ttk.LabelFrame(main_frame, text=" 🔌 驱动与环境设置 ", padding="10")
        group_driver.pack(fill=tk.X, pady=(0, 10))
        
        row_d = ttk.Frame(group_driver)
        row_d.pack(fill=tk.X, pady=5)
        ttk.Label(row_d, text="Edge驱动路径:").pack(side=tk.LEFT, padx=5)
        self.entry_driver_path = ttk.Entry(row_d)
        self.entry_driver_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row_d, text="浏览...", width=8, command=self.browse_driver).pack(side=tk.LEFT, padx=5)
        
        row_h = ttk.Frame(group_driver)
        row_h.pack(fill=tk.X, pady=5)
        ttk.Label(row_h, text="💡 驱动下载失败？", foreground="blue").pack(side=tk.LEFT, padx=5)
        ttk.Button(row_h, text="查看手动安装教程", command=self.show_driver_help).pack(side=tk.LEFT, padx=5)

        # 区域 3: 高级配置 (Advanced Config)
        # ==========================================================
        group_config = ttk.LabelFrame(main_frame, text=" ⚙️ 高级配置 ", padding="10")
        group_config.pack(fill=tk.X, pady=(0, 10))

        # 提交间隔
        ttk.Label(group_config, text="点击间隔(秒):").grid(row=0, column=0, sticky="w", padx=5)
        self.entry_confirm_interval = ttk.Entry(group_config, width=10)
        self.entry_confirm_interval.insert(0, str(DEFAULT_CONFIRM_INTERVAL))
        self.entry_confirm_interval.grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(group_config, text="推荐: 0.5~1.0秒 ⚠️ 过小会被拒绝", foreground="red").grid(row=0, column=2, sticky="w", padx=5)

        # 最大次数
        ttk.Label(group_config, text="最大尝试次数:").grid(row=1, column=0, sticky="w", padx=5)
        self.entry_confirm_max = ttk.Entry(group_config, width=10)
        self.entry_confirm_max.insert(0, str(DEFAULT_MAX_CONFIRM_ATTEMPTS))
        self.entry_confirm_max.grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(group_config, text="推荐: 100~300次（系统会自动避让繁忙）", foreground="gray").grid(row=1, column=2, sticky="w", padx=5)

        # ==========================================================
        # 区域 4: 控制面板 (Control Panel)
        # ==========================================================
        group_ctrl = ttk.LabelFrame(main_frame, text=" 🎮 控制面板 ", padding="10")
        group_ctrl.pack(fill=tk.X, pady=(0, 10))

        # 为了让按钮居中，我们在 Frame 内部再放一个 Frame
        btn_inner_frame = ttk.Frame(group_ctrl)
        btn_inner_frame.pack()

        # 按钮样式调整：稍微大一点，颜色区分
        # 注意：ttk.Button 很难直接改背景色，所以核心按钮保留使用 tk.Button 以便着色
        
        self.btn_open = tk.Button(btn_inner_frame, text="1. 启动浏览器 & 登录", 
                                  bg="#2196F3", fg="white", font=("Microsoft YaHei", 10, "bold"),
                                  relief="flat", padx=15, pady=5, cursor="hand2",
                                  command=self.open_browser)
        self.btn_open.pack(side=tk.LEFT, padx=10)

        self.btn_start = tk.Button(btn_inner_frame, text="2. 开始抢购任务", state=tk.DISABLED,
                                   bg="#4CAF50", fg="white", font=("Microsoft YaHei", 10, "bold"),
                                   relief="flat", padx=15, pady=5, cursor="hand2",
                                   command=self.start_sniper)
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_stop = tk.Button(btn_inner_frame, text="⏹ 停止/重置", 
                                  bg="#F44336", fg="white", font=("Microsoft YaHei", 10),
                                  relief="flat", padx=15, pady=5, cursor="hand2",
                                  command=self.stop_sniper)
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        # ==========================================================
        # 区域 5: 运行日志 (Logs)
        # ==========================================================
        group_log = ttk.LabelFrame(main_frame, text=" 📝 运行日志 ", padding="10")
        group_log.pack(fill=tk.BOTH, expand=True)

        self.log_area = scrolledtext.ScrolledText(group_log, height=10, state="disabled", font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 初始日志
        self.log("系统就绪。请先点击「启动浏览器」进行扫码登录。")

    # ================== 驱动管理方法 ==================
    
    def browse_driver(self):
        """浏览选择驱动文件"""
        messagebox.showinfo("驱动文件选择", "请选择 msedgedriver.exe 文件\n\n注意：不是 msedge.exe（那是浏览器本身）")
        p = filedialog.askopenfilename(
            title="选择 msedgedriver.exe 文件",
            filetypes=[("WebDriver 驱动", "msedgedriver.exe"), ("所有可执行文件", "*.exe"), ("所有文件", "*.*")],
            initialdir="C:/"
        )
        if p:
            if "msedgedriver" in p.lower():
                self.entry_driver_path.delete(0, tk.END)
                self.entry_driver_path.insert(0, p)
                self.log(f"✅ 驱动路径已设置: {p}")
            else:
                messagebox.showwarning("警告", f"这似乎不是 msedgedriver.exe！\n选择的文件: {os.path.basename(p)}\n\n请选择正确的 msedgedriver.exe 文件")
                self.log(f"⚠️ 用户选择了错误的文件: {p}")
    
    def show_driver_help(self):
        """显示手动安装教程"""
        msg = ("【重要】获取 WebDriver 驱动的正确方法：\n\n"
               "❌ 错误：不要选择 msedge.exe (这是浏览器本身)\n"
               "✅ 正确：要选择 msedgedriver.exe (这是 WebDriver 驱动)\n\n"
               "步骤：\n"
               "1. 打开 Edge 浏览器，进入 [设置] -> [关于 Microsoft Edge]\n"
               "2. 查看您的版本号（例如：120.0.2210.91）\n"
               "3. 访问: https://developer.microsoft.com/zh-cn/microsoft-edge/tools/webdriver/\n"
               "4. 下载对应版本的 msedgedriver.exe\n"
               "5. 解压后将 msedgedriver.exe 放在本脚本目录下或手动指定路径\n\n"
               "点击「确定」打开官方下载页面")
        if messagebox.askokcancel("WebDriver 驱动安装指南", msg):
            webbrowser.open("https://developer.microsoft.com/zh-cn/microsoft-edge/tools/webdriver/?form=MA13LH#installation")
    
    def get_driver_path(self):
        """获取驱动路径（优先级：手动 > 当前目录 > 失败）"""
        # 1. 优先用户手动选择
        manual = self.entry_driver_path.get().strip()
        if manual:
            if os.path.isfile(manual):
                # 检查是否选择了错误的文件
                if "msedge.exe" in manual.lower() and "msedgedriver" not in manual.lower():
                    self.log(f"❌ 错误：你选择的是 Edge 浏览器文件 (msedge.exe)，而不是 WebDriver 驱动文件 (msedgedriver.exe)")
                    self.log(f"❌ 请选择正确的 msedgedriver.exe 文件")
                    return None
                
                self.log(f"✅ 使用指定驱动: {manual}")
                return manual
            else:
                self.log(f"❌ 指定的驱动文件不存在: {manual}")

        # 2. 检查当前目录
        local = os.path.join(os.getcwd(), "msedgedriver.exe")
        if os.path.isfile(local):
            self.log(f"✅ 使用当前目录驱动: {local}")
            return local
        else:
            self.log(f"⚠️ 当前目录驱动不存在: {local}")

        # 3. 失败提示
        self.log("❌ 未找到驱动文件，请手动指定或放在脚本目录下")
        self.log(f"   当前目录: {os.getcwd()}")
        self.log(f"   注意: 需要 msedgedriver.exe，而不是 msedge.exe")
        self.show_driver_help()
        return None

    # ================== 日志与按钮方法 ==================

    def log(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def restore_buttons(self):
        self.btn_start.config(state=tk.NORMAL, bg="#4CAF50") # 恢复绿色
        self.btn_open.config(state=tk.NORMAL, bg="#2196F3")  # 恢复蓝色

    def open_browser(self):
        if not webdriver:
            messagebox.showerror("错误", "未找到 Selenium 库。无法启动浏览器。")
            return

        def run():
            try:
                driver_path = self.get_driver_path()
                if not driver_path:
                    self.log("❌ 驱动路径获取失败，启动中止")
                    return

                self.log(f"🚀 启动浏览器中... (驱动: {os.path.basename(driver_path)})")
                
                # 验证驱动文件
                self.log(f"📌 验证驱动文件: {driver_path}")
                if not os.path.isfile(driver_path):
                    self.log(f"❌ 驱动文件不存在: {driver_path}")
                    return
                
                self.log(f"✅ 驱动文件存在，大小: {os.path.getsize(driver_path)} bytes")
                
                options = EdgeOptions()
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)
                options.add_argument("--disable-blink-features=AutomationControlled")
                # 添加无沙箱模式（某些环境需要）
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

                self.log("📌 创建 EdgeService...")
                self.log(f"   驱动路径: {driver_path}")
                service = EdgeService(driver_path)
                self.log("✅ EdgeService 创建成功")
                
                self.log("📌 正在启动 Edge 浏览器（可能需要 10-30 秒，请耐心等待）...")
                import signal
                import subprocess
                
                # 启动驱动并检查是否成功
                self.log("   执行: webdriver.Edge()")
                self.driver = webdriver.Edge(service=service, options=options)
                self.log("✅ Edge 浏览器启动成功！")
                
                self.log("📌 最大化窗口...")
                self.driver.maximize_window()
                self.log("✅ 窗口已最大化")
                
                self.log("📌 屏蔽 WebDriver 检测...")
                self.driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                self.log("✅ 检测屏蔽成功")

                self.log("📌 导航至淘宝首页...")
                self.driver.get("https://www.taobao.com/")
                self.log("✅ 浏览器已打开，请尽快在浏览器中扫码登录淘宝。")

                # 加载 cookies
                if os.path.exists(COOKIE_FILE):
                    try:
                        self.log("📌 尝试加载历史 Cookie...")
                        cookies = pickle.load(open(COOKIE_FILE, "rb"))
                        for c in cookies:
                            if 'expiry' in c:
                                del c['expiry']
                            self.driver.add_cookie(c)
                        self.driver.refresh()
                        self.log("✅ 已加载历史 Cookie")
                    except Exception as e:
                        self.log(f"⚠️ Cookie 加载失败: {e}")

                self.btn_start.config(state=tk.NORMAL)
                self.btn_open.config(state=tk.DISABLED, bg="#B0BEC5")

            except Exception as e:
                import traceback
                error_msg = f"浏览器启动失败: {str(e)}"
                self.log(f"❌ {error_msg}")
                self.log(f"❌ 详细错误: {traceback.format_exc()[:200]}")
                # 在主线程中弹出错误对话框
                self.root.after(100, lambda: messagebox.showerror("启动失败", error_msg))

        threading.Thread(target=run, daemon=True).start()

    def stop_sniper(self):
        self.stop_flag = True
        self.log("正在停止所有任务...")
        time.sleep(0.3)
        self.restore_buttons()
        self.log("任务已停止。")

    def human_move(self, element):
        try:
            self.driver.execute_script("""
                var rect = arguments[0].getBoundingClientRect();
                var x = rect.left + rect.width / 2;
                var y = rect.top + rect.height / 2;
                var evt = new MouseEvent('mousemove', {
                    view: window, bubbles: true, cancelable: true, pageX: x, pageY: y
                });
                document.dispatchEvent(evt);
            """, element)
        except:
            pass

    def human_click(self, element):
        try:
            self.driver.execute_script("""
                var rect = arguments[0].getBoundingClientRect();
                var x = rect.left + rect.width / 2;
                var y = rect.top + rect.height / 2;
                ['mouseover','mousedown','mouseup','click'].forEach(type => {
                    var evt = new MouseEvent(type, {
                        view: window, bubbles: true, cancelable: true, pageX: x, pageY: y
                    });
                    arguments[0].dispatchEvent(evt);
                });
            """, element)
        except:
            pass

    def start_sniper(self):
        if not self.driver:
            messagebox.showwarning("提示", "请先启动浏览器！")
            return

        self.stop_flag = False
        self.btn_start.config(state=tk.DISABLED, bg="#B0BEC5")
        self.btn_open.config(state=tk.DISABLED, bg="#B0BEC5")

        # 保存 cookies 以备下次使用
        try:
            pickle.dump(self.driver.get_cookies(), open(COOKIE_FILE, "wb"))
            self.log("✅ Cookie 已保存")
        except Exception as e:
            self.log(f"⚠️ Cookie 保存失败: {e}")

        self.log("🚀 启动抢购线程...")
        threading.Thread(target=self.sniper_logic, daemon=True).start()

    def sniper_logic(self):
        driver = self.driver
        # 1. 打开购物车
        self.log("📍 正在跳转至购物车...")
        try:
            driver.get("https://cart.taobao.com/cart.htm")
            self.log("✅ 购物车页面已加载")
        except Exception as e:
            self.log(f"❌ 浏览器连接丢失: {e}")
            self.restore_buttons()
            return

        time.sleep(1.5)

        # 2. 等待时间
        target = self.entry_time.get().strip()
        self.log(f"⏳ 正在等待目标时间：{target}")

        while not self.stop_flag:
            now_str = datetime.now().strftime("%H:%M:%S")
            if now_str >= target:
                self.log("✅ 时间到！开始行动！")
                break
            time.sleep(0.01)

        if self.stop_flag:
            self.log("⚠️ 已中止")
            self.restore_buttons()
            return

        # 3. 勾选商品
        self.log("🔍 正在扫描目标商品...")
        keywords = [k.strip().lower() for k in self.entry_keywords.get().split(",")]

        try:
            items = driver.find_elements(By.CSS_SELECTOR, ".item-content, .trade-cart-item-info, .cart-item")
        except Exception as e:
            self.log(f"⚠️ 查询商品失败: {e}")
            items = []

        found = 0
        for item in items:
            if self.stop_flag:
                break
            try:
                text = item.text.lower()
                if any(k in text for k in keywords):
                    cb = item.find_element(By.CSS_SELECTOR, "input[type='checkbox'], .ant-checkbox-input")
                    if not cb.is_selected():
                        driver.execute_script("arguments[0].click();", cb)
                    found += 1
                    self.log(f"✅ 已勾选商品: {text[:15]}...")
            except Exception as e:
                pass

        if found == 0:
            self.log("⚠️ 未匹配到关键字商品，尝试直接监控结算按钮（假设您已手动勾选）")
        else:
            self.log(f"✅ 共勾选 {found} 件商品")

        self.log("👀 开始监控【结算】按钮...")

        # 启动结算监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

    def monitor_loop(self):
        driver = self.driver
        while not self.stop_flag:
            if "cart" not in driver.current_url and "order" in driver.current_url:
                self.log("检测到页面已跳转至订单页！")
                self.start_confirm_thread()
                break

            try:
                # 寻找结算按钮
                btn = driver.find_element(By.XPATH, "//div[contains(@class,'trade-cart-btn-submit')]//div[contains(text(),'结算')]")
                driver.execute_script("arguments[0].click();", btn)
                # self.human_click(btn) # 备用
                self.log("已点击结算...")
            except:
                pass
            
            if "order" in driver.current_url:
                self.start_confirm_thread()
                break

            time.sleep(0.1)

    def start_confirm_thread(self):
        if self.confirm_thread and self.confirm_thread.is_alive():
            return

        try:
            base_interval = float(self.entry_confirm_interval.get())
            max_attempts = int(self.entry_confirm_max.get())
        except:
            base_interval = DEFAULT_CONFIRM_INTERVAL
            max_attempts = DEFAULT_MAX_CONFIRM_ATTEMPTS

        self.confirm_thread = threading.Thread(
            target=self.confirm_logic, 
            args=(base_interval, max_attempts), 
            daemon=True
        )
        self.confirm_thread.start()

    def confirm_logic(self, base_interval, max_attempts):
        driver = self.driver
        attempts = 0
        self.log("🔥 进入订单提交冲刺阶段！")
        self.log(f"   配置：间隔 {base_interval}秒 | 最大 {max_attempts} 次")
        
        busy_count = 0 
        initial_url = driver.current_url  # 记录初始订单页面
        
        while not self.stop_flag and attempts < max_attempts:
            current_url = driver.current_url
            
            # 1. 成功检测：支付页面
            if "alipay" in current_url or "pay.taobao" in current_url or "pay.tmall" in current_url:
                self.log("🎉 检测到支付页面，抢购成功！")
                self.stop_flag = True
                break
            
            # 2. 失败检测：页面被重定向（最重要的检查）
            # 明确识别 buy.taobao.com 的确认订单页为有效订单页
            is_confirm_order_url = (
                "buy.taobao.com/auction/order/confirm_order.htm" in current_url
                or "confirm_order.htm" in current_url
            )

            if current_url != initial_url and ("order" not in current_url) and (not is_confirm_order_url):
                self.log(f"❌ 页面已跳转到其他地址，被系统拒绝")
                self.log(f"   可能原因：点击太快 或 IP被限流")
                break
            
            # 3. 繁忙检测
            is_busy = False
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "繁忙" in body_text or "拥挤" in body_text or "稍后再试" in body_text or "服务器" in body_text:
                    is_busy = True
                    busy_count += 1
                    if busy_count <= 3:
                        self.log(f"⚠️ 【{busy_count}次】繁忙，暂停 5 秒...")
                    time.sleep(7 if busy_count > 5 else 5)
                    continue
                elif busy_count > 0:
                    self.log(f"✅ 恢复正常（繁忙共 {busy_count} 次）")
                    busy_count = 0
            except:
                pass
            
            # 4. 非订单页面，等待
            if "order" not in driver.current_url:
                time.sleep(0.1)
                continue
            
            attempts += 1
            
            # 5. 点击提交订单按钮
            try:
                submit_btns = driver.find_elements(By.XPATH, "//*[contains(text(),'提交订单')]")
                clicked = False
                for btn in submit_btns:
                    try:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            time.sleep(uniform(0.05, 0.1))
                            driver.execute_script("arguments[0].click();", btn)
                            clicked = True
                            if attempts <= 3 or attempts % 30 == 0:
                                self.log(f"   点击 #{attempts}")
                            break
                    except:
                        pass
            except:
                pass
            
            # 6. 智能间隔：太小会被拒绝！
            min_interval = max(base_interval, 0.5)  # 强制最小 0.5 秒
            real_interval = min_interval * uniform(0.95, 1.3)
            time.sleep(real_interval)
        
        self.log(f"⚡ 结束 (点击 {attempts} 次，繁忙检测 {busy_count} 次)")
        if attempts >= max_attempts and "order" in driver.current_url:
            self.log("📌 已达最大次数，请手动检查订单")
        self.restore_buttons()
    def on_close(self):
        self.stop_flag = True
        self.log("🛑 正在关闭应用...")
        try:
            if self.driver:
                self.driver.quit()
                self.log("✅ 浏览器已关闭")
        except Exception as e:
            self.log(f"⚠️ 关闭浏览器时出错: {e}")
        self.root.destroy()

if __name__ == "__main__":
    app = TaobaoSniper()
    app.root.mainloop()