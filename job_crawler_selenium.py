"""
招聘网站爬虫程序 - Selenium版本
使用浏览器模拟访问，可以更好地绑过反爬虫机制
支持: Boss直聘、猎聘、智联招聘、前程无忧
"""

import json
import time
import random
import re
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("警告: 未安装selenium，请运行: pip install selenium")

# 尝试导入 undetected-chromedriver (用于绑过反爬检测)
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("提示: 未安装undetected-chromedriver，Boss直聘可能会被反爬拦截")
    print("安装命令: pip install undetected-chromedriver")


# 全局配置
_config = None

def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    global _config
    
    if _config is not None:
        return _config
    
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    default_config = {
        "search": {"position": "", "city": "", "experience": "", "education": "", "salary": "", "page": 1, "page_size": 20},
        "sources": {"enabled": ["boss", "liepin", "zhilian"]},
        "browser": {"headless": True, "page_load_timeout": 15},
        "crawl": {"mode": "parallel", "delay": {"min": 1.5, "max": 2.5}, "wait_timeout": {"boss": 5, "liepin": 4, "zhilian": 4, "job51": 5}},
        "output": {"file": "jobs_result.json", "save_by_default": False},
        "city_codes": {
            "全国": "100010000", "北京": "101010100", "上海": "101020100", "广州": "101280100",
            "深圳": "101280600", "杭州": "101210100", "成都": "101270100", "南京": "101190100",
            "武汉": "101200100", "西安": "101110100", "苏州": "101190400", "天津": "101030100",
            "重庆": "101040100", "郑州": "101180100", "长沙": "101250100", "东莞": "101281600",
            "青岛": "101120200", "沈阳": "101070100", "宁波": "101210400", "昆明": "101290100",
        },
        "display": {"show_progress": True, "max_display_jobs": 10, "color_output": True},
    }
    
    if YAML_AVAILABLE and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    # 深度合并配置
                    for key, value in user_config.items():
                        if key in default_config and isinstance(value, dict):
                            default_config[key].update(value)
                        else:
                            default_config[key] = value
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
    
    _config = default_config
    return _config


def get_config() -> dict:
    """获取配置"""
    global _config
    if _config is None:
        return load_config()
    return _config


@dataclass
class JobSearchParams:
    """求职搜索参数"""
    position: str  # 岗位名称（必填）
    city: str = ""  # 意向城市
    experience: str = ""  # 工作经验
    salary: str = ""  # 期望薪资
    education: str = ""  # 学历要求
    page: int = 1  # 页码
    page_size: int = 20  # 每页数量


@dataclass
class JobInfo:
    """职位信息"""
    title: str  # 职位名称
    company: str  # 公司名称
    salary: str  # 薪资范围
    city: str  # 工作城市
    experience: str = ""  # 经验要求
    education: str = ""  # 学历要求
    company_type: str = ""  # 公司类型
    company_size: str = ""  # 公司规模
    skills: List[str] = None  # 技能要求
    benefits: List[str] = None  # 福利待遇
    job_url: str = ""  # 职位链接
    source: str = ""  # 来源网站
    publish_time: str = ""  # 发布时间
    description: str = ""  # 职位描述
    
    def __post_init__(self):
        if self.skills is None:
            self.skills = []
        if self.benefits is None:
            self.benefits = []


class SeleniumCrawler:
    """基于Selenium的爬虫基类"""
    
    def __init__(self, headless: bool = True):
        """
        初始化Selenium爬虫
        
        Args:
            headless: 是否使用无头模式（不显示浏览器窗口）
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError("请先安装selenium: pip install selenium")
        
        self.headless = headless
        self.driver = None
    
    def _create_driver(self):
        """创建WebDriver"""
        options = Options()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 性能优化：禁用图片、CSS等资源加载
        prefs = {
            "profile.managed_default_content_settings.images": 2,  # 禁用图片
            "profile.managed_default_content_settings.stylesheets": 2,  # 禁用CSS
            "profile.managed_default_content_settings.fonts": 2,  # 禁用字体
        }
        options.add_experimental_option("prefs", prefs)
        
        # 禁用扩展和日志
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        
        # 设置User-Agent
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=options)
        
        # 设置页面加载超时
        self.driver.set_page_load_timeout(30)
        
        # 执行CDP命令隐藏WebDriver
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
    
    def _close_driver(self):
        """关闭WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def _random_delay(self, min_sec: float = 0.3, max_sec: float = 0.8):
        """随机延迟（已优化为更短时间）"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def _safe_get_text(self, element, default: str = "") -> str:
        """安全获取元素文本"""
        try:
            return element.text.strip() if element else default
        except:
            return default
    
    def _safe_get_attribute(self, element, attr: str, default: str = "") -> str:
        """安全获取元素属性"""
        try:
            return element.get_attribute(attr) if element else default
        except:
            return default


class BossZhipinSeleniumCrawler(SeleniumCrawler):
    """Boss直聘 Selenium爬虫 - 使用 undetected-chromedriver 绑过反爬"""
    
    # Cookie 文件路径
    COOKIE_FILE = "boss_cookies.json"
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.zhipin.com"
        
        # 城市代码映射
        self.city_codes = {
            "全国": "100010000",
            "北京": "101010100",
            "上海": "101020100",
            "广州": "101280100",
            "深圳": "101280600",
            "杭州": "101210100",
            "成都": "101270100",
            "南京": "101190100",
            "武汉": "101200100",
            "西安": "101110100",
            "苏州": "101190400",
            "天津": "101030100",
            "重庆": "101040100",
        }
    
    def get_source_name(self) -> str:
        return "Boss直聘"
    
    def _get_city_code(self, city: str) -> str:
        if not city:
            return "100010000"
        for key, code in self.city_codes.items():
            if key in city or city in key:
                return code
        return "100010000"
    
    def _create_driver(self):
        """创建 WebDriver - 优先使用 undetected-chromedriver"""
        if UC_AVAILABLE:
            try:
                # 使用 undetected-chromedriver 绑过反爬检测
                options = uc.ChromeOptions()
                
                if self.headless:
                    options.add_argument("--headless=new")
                
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                
                # 禁用扩展和日志
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-logging")
                options.add_argument("--log-level=3")
                
                # 创建 undetected chrome driver
                self.driver = uc.Chrome(options=options, use_subprocess=True)
                self.driver.set_page_load_timeout(30)
                
                # 加载保存的 cookies
                self._load_cookies()
                return
            except Exception as e:
                print(f"undetected-chromedriver 初始化失败: {e}")
                print("回退到普通 selenium...")
        
        # 回退到普通 selenium (增强版)
        options = Options()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 随机化 User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        options.add_argument(f"user-agent={random.choice(user_agents)}")
        
        # 禁用扩展和日志
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(20)
        
        # 执行CDP命令隐藏WebDriver特征
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // 隐藏 webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // 修改 navigator.plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // 修改 navigator.languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                
                // 隐藏 Chrome 自动化特征
                window.chrome = {
                    runtime: {}
                };
                
                // 修改 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """
        })
        
        # 加载保存的 cookies
        self._load_cookies()
    
    def _load_cookies(self):
        """加载保存的 cookies"""
        try:
            if os.path.exists(self.COOKIE_FILE):
                # 先访问主页以设置 cookie 域
                self.driver.get(self.base_url)
                time.sleep(1)
                
                with open(self.COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        # 移除可能导致问题的字段
                        cookie.pop("sameSite", None)
                        cookie.pop("expiry", None)
                        try:
                            self.driver.add_cookie(cookie)
                        except:
                            pass
                print("已加载保存的 Boss直聘 cookies")
        except Exception as e:
            pass  # Cookie 加载失败不影响正常使用
    
    def _save_cookies(self):
        """保存 cookies 到文件"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False)
            print("已保存 Boss直聘 cookies")
        except Exception as e:
            pass
    
    def _scroll_page(self):
        """滚动页面以加载更多内容（已优化）"""
        try:
            # 快速滚动页面
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except:
            pass
    
    def _check_and_handle_verification(self) -> bool:
        """检查并处理验证页面，返回是否需要验证"""
        page_source = self.driver.page_source
        page_title = self.driver.title
        
        # 检查是否是验证页面
        if "验证" in page_title or "验证" in page_source[:2000]:
            print("检测到安全验证页面...")
            
            # 如果是无头模式，无法自动完成验证
            if self.headless:
                print("无头模式下无法自动完成验证，尝试使用已保存的 cookies...")
                return True
            
            # 非无头模式，等待用户手动完成验证
            print("请在浏览器中手动完成验证...")
            print("完成后按任意键继续，或等待30秒超时")
            
            # 等待验证完成（最多等30秒）
            for _ in range(30):
                time.sleep(1)
                if "验证" not in self.driver.title:
                    print("验证已完成！")
                    self._save_cookies()  # 保存验证后的 cookies
                    return False
            
            print("验证超时")
            return True
        
        return False
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        """搜索职位"""
        jobs = []
        max_retries = 2
        
        for retry in range(max_retries):
            try:
                self._create_driver()
                city_code = self._get_city_code(params.city)
                
                # 构建搜索URL
                url = f"{self.base_url}/web/geek/job?query={quote(params.position)}&city={city_code}&page={params.page}"
                
                print(f"正在访问: {url}")
                try:
                    self.driver.get(url)
                except TimeoutException:
                    print(f"页面加载超时，重试 {retry + 1}/{max_retries}")
                    self._close_driver()
                    continue
                    
                self._random_delay(2.0, 3.0)  # 稍微增加等待时间
                
                # 检查是否需要验证
                if self._check_and_handle_verification():
                    # 验证未完成，尝试重新访问
                    try:
                        self.driver.get(url)
                    except TimeoutException:
                        print("重新访问超时")
                        self._close_driver()
                        continue
                    self._random_delay(2.0, 3.0)
                    
                    # 再次检查
                    if self._check_and_handle_verification():
                        print("Boss直聘需要人工验证，跳过此数据源")
                        print("提示: 使用 --no-headless 参数可手动完成验证")
                        return jobs
                
                # 滚动页面触发加载
                self._scroll_page()
                
                # 保存 cookies (如果成功访问了页面)
                if "验证" not in self.driver.title and "请稍候" not in self.driver.title:
                    self._save_cookies()
                
                # Boss直聘最新的选择器 - 2024年页面结构
                job_card_selectors = [
                    ".job-card-wrap",
                    ".job-card-box",
                    "li.job-card-box",
                    ".rec-job-list .card-area",
                ]
                
                job_cards = []
                for selector in job_card_selectors:
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if job_cards and len(job_cards) > 0:
                            print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个职位卡片")
                            break
                    except TimeoutException:
                        continue
                
                if not job_cards:
                    print("Boss直聘: 未找到职位卡片，可能需要验证或页面结构变化")
                    print(f"当前页面标题: {self.driver.title}")
                    
                    # 如果页面显示"请稍候"，可能是加载问题，尝试重试
                    if "请稍候" in self.driver.title and retry < max_retries - 1:
                        print(f"页面加载中，重试 {retry + 1}/{max_retries}")
                        self._close_driver()
                        continue
                    
                    # 保存页面源码用于调试
                    try:
                        with open("boss_debug.html", "w", encoding="utf-8") as f:
                            f.write(self.driver.page_source)
                        print("已保存页面源码到 boss_debug.html 用于调试")
                    except:
                        pass
                    
                    # 检查是否需要验证
                    if "验证" in self.driver.page_source or "安全验证" in self.driver.page_source:
                        print("检测到安全验证页面，请手动完成验证后重试")
                    return jobs
                
                for card in job_cards[:params.page_size]:
                    try:
                        job_data = self._parse_job_card(card)
                        if job_data:
                            jobs.append(job_data)
                    except Exception as e:
                        print(f"解析职位卡片失败: {e}")
                        continue
                
                # 成功获取数据，跳出重试循环
                break
                        
            except Exception as e:
                print(f"Boss直聘爬取错误: {e}")
                import traceback
                traceback.print_exc()
                if retry < max_retries - 1:
                    self._close_driver()
                    continue
            finally:
                self._close_driver()
        
        return jobs
    
    def _parse_job_card(self, card) -> Optional[JobInfo]:
        """解析职位卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        experience = ""
        education = ""
        company_type = ""
        company_size = ""
        skills = []
        job_url = ""
        
        # 职位名称 - 使用 .job-name 类
        for selector in ["a.job-name", ".job-name", ".job-title a"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    title = text
                    # 同时获取链接
                    href = self._safe_get_attribute(elem, "href")
                    if href:
                        job_url = href
                    break
            except:
                continue
        
        # 薪资 - Boss直聘使用了反爬机制隐藏薪资数字
        # 尝试多种方式获取薪资
        for selector in [".salary", ".job-salary", "span.salary", "span.job-salary", "[class*='salary']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                
                # 方式1: 使用 innerText (可能包含通过 CSS 伪元素添加的内容)
                text = self.driver.execute_script("return arguments[0].innerText;", elem)
                if text:
                    text = text.strip()
                
                # 方式2: 如果 innerText 无效，尝试 textContent
                if not text or text in ["-K", "-", "K", "薪"]:
                    text = elem.get_attribute("textContent")
                    if text:
                        text = text.strip()
                
                # 方式3: 尝试获取 data 属性
                if not text or text in ["-K", "-", "K", "薪"]:
                    for attr in ["data-salary", "data-v", "data-text"]:
                        attr_val = elem.get_attribute(attr)
                        if attr_val:
                            text = attr_val
                            break
                
                # 方式4: 尝试从子元素组合获取
                if not text or text in ["-K", "-", "K", "薪"]:
                    children = elem.find_elements(By.CSS_SELECTOR, "*")
                    parts = []
                    for child in children:
                        child_text = self._safe_get_text(child)
                        if child_text:
                            parts.append(child_text)
                    if parts:
                        text = "".join(parts)
                
                if text and len(text) > 1:
                    salary = text
                    break
            except:
                continue
        
        # 公司名称 - 使用多种选择器
        for selector in [".company-name a", ".company-name", ".info-company .name", 
                         ".boss-name", "span.boss-name", ".boss-info .boss-name"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    company = text
                    break
            except:
                continue
        
        # 城市/地点 - 使用 .company-location 类
        for selector in [".company-location", "span.company-location"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text:
                    city = text.strip()
                    break
            except:
                continue
        
        # 经验和学历 - 从 .tag-list li 获取
        try:
            tag_list = card.find_elements(By.CSS_SELECTOR, ".tag-list li, ul.tag-list li")
            for i, tag in enumerate(tag_list):
                text = self._safe_get_text(tag)
                if not text:
                    continue
                if i == 0:
                    experience = text
                elif i == 1:
                    education = text
        except:
            pass
        
        # 技能标签 - 从 .job-label-list li 获取（如果有）
        try:
            skill_elems = card.find_elements(By.CSS_SELECTOR, ".job-label-list li")
            skills = [self._safe_get_text(s) for s in skill_elems if self._safe_get_text(s)]
        except:
            pass
        
        # 如果没有从卡片获取到链接，尝试从 a 标签获取
        if not job_url:
            try:
                link_elem = card.find_element(By.CSS_SELECTOR, "a[href*='job_detail']")
                job_url = self._safe_get_attribute(link_elem, "href")
            except:
                pass
        
        # 只有当有标题时才创建JobInfo
        if title and len(title) > 1:
            return JobInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                company_type=company_type,
                company_size=company_size,
                skills=skills,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class LiepinSeleniumCrawler(SeleniumCrawler):
    """猎聘 Selenium爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.liepin.com"
    
    def get_source_name(self) -> str:
        return "猎聘"
    
    def _scroll_page(self):
        """滚动页面以加载更多内容（已优化）"""
        try:
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except:
            pass
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        """搜索职位"""
        jobs = []
        
        try:
            self._create_driver()
            
            # 构建搜索URL - 猎聘使用 dq 参数表示城市
            # 猎聘城市代码映射（已验证有效的城市）
            liepin_city_codes = {
                "北京": "010", "上海": "020", "广州": "050020", "深圳": "050090",
                "杭州": "070020", "成都": "280020", "南京": "060020", "武汉": "170020",
                "西安": "270020", "苏州": "060080", "天津": "030", "重庆": "040",
                "郑州": "200020", "长沙": "190020", "东莞": "050060", "青岛": "250020",
                "沈阳": "210020", "宁波": "070060", "昆明": "310020", "合肥": "150020",
                "福州": "110020", "济南": "120020", "厦门": "110040", "珠海": "050030",
                "无锡": "060050", "佛山": "050050", "大连": "210040", "哈尔滨": "220020",
                "石家庄": "140020", "长春": "230020", "南昌": "160020", "贵阳": "300020",
                "太原": "260020", "南宁": "290020", "海口": "330020",
            }
            
            # 优先使用城市代码
            city_code = None
            if params.city:
                for city_name, code in liepin_city_codes.items():
                    if city_name in params.city or params.city in city_name:
                        city_code = code
                        break
            
            # 构建 URL
            if city_code:
                # 热门城市使用城市代码
                city_param = f"&dq={city_code}"
                search_key = params.position
            elif params.city:
                # 其他城市：将城市名加入搜索关键词
                city_param = ""
                search_key = f"{params.position} {params.city}"
            else:
                city_param = ""
                search_key = params.position
            
            url = f"{self.base_url}/zhaopin/?key={quote(search_key)}{city_param}&currentPage={params.page - 1}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.0, 2.0)
            
            # 滚动页面触发加载
            self._scroll_page()
            
            # 尝试多种选择器定位职位卡片
            job_card_selectors = [
                ".job-list-item",
                "[class*='job-list-item']",
                "[class*='job-card']",
                ".job-list > div",
                "[data-nick='job-card']",
            ]
            
            job_cards = []
            for selector in job_card_selectors:
                try:
                    WebDriverWait(self.driver, 4).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个职位卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("猎聘: 页面加载超时或无搜索结果")
                print(f"当前页面标题: {self.driver.title}")
                return jobs
            
            for card in job_cards[:params.page_size]:
                try:
                    job_data = self._parse_job_card(card)
                    if job_data:
                        jobs.append(job_data)
                except Exception as e:
                    print(f"解析职位卡片失败: {e}")
                    continue
                    
        except Exception as e:
            print(f"猎聘爬取错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._close_driver()
        
        return jobs
    
    def _parse_job_card(self, card) -> Optional[JobInfo]:
        """解析职位卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        experience = ""
        education = ""
        job_url = ""
        
        # 职位名称
        for selector in [".job-title-box .ellipsis-1", ".job-title", "[class*='job-title']", "h3", "a[data-nick]"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 2:
                    # 过滤掉无效的标题
                    if "在线" in text or "分钟" in text or "小时" in text:
                        continue
                    title = text
                    break
            except:
                continue
        
        # 如果没有找到有效标题，返回None
        if not title:
            return None
        
        # 薪资 - 使用 textContent 获取完整文本
        for selector in [".job-salary", "[class*='salary']", "[class*='money']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = elem.get_attribute("textContent")
                if text:
                    text = text.strip()
                if not text:
                    text = self._safe_get_text(elem)
                if text and ("K" in text or "k" in text or "元" in text or "万" in text or "薪" in text):
                    salary = text
                    break
            except:
                continue
        
        # 公司名称
        for selector in [".company-name a", ".company-name", "[class*='company-name']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    company = text
                    break
            except:
                continue
        
        # 城市
        for selector in [".job-dq-box .ellipsis-1", ".job-dq", "[class*='job-dq']", "[class*='city']", "[class*='area']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    city = text
                    break
            except:
                continue
        
        # 经验和学历
        try:
            labels = card.find_elements(By.CSS_SELECTOR, ".job-labels-box .labels-tag, [class*='labels'] span, [class*='requirement'] span")
            for label in labels:
                text = self._safe_get_text(label)
                if not text:
                    continue
                if ("年" in text or "经验" in text) and not experience:
                    experience = text
                elif ("科" in text or "专" in text or "士" in text) and not education:
                    education = text
        except:
            pass
        
        # 职位链接
        for selector in ["a[href*='/job/']", "a[href*='liepin']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                href = self._safe_get_attribute(elem, "href")
                if href and "job" in href and "liepin" in href:
                    job_url = href
                    break
            except:
                continue
        
        # 验证数据有效性
        if title and company:
            return JobInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class ZhilianSeleniumCrawler(SeleniumCrawler):
    """智联招聘 Selenium爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://sou.zhaopin.com"
    
    def get_source_name(self) -> str:
        return "智联招聘"
    
    def _scroll_page(self):
        """滚动页面以加载更多内容（已优化）"""
        try:
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except:
            pass
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        """搜索职位"""
        jobs = []
        
        try:
            self._create_driver()
            
            # 智联招聘城市代码映射（一线及热门城市，已验证有效）
            # 二线城市代码可能不准确，会使用备选方案
            zhilian_city_codes = {
                "北京": "530", "上海": "538", "广州": "763", "深圳": "765",
                "杭州": "653", "成都": "801", "南京": "635", "武汉": "736",
                "西安": "854", "苏州": "639", "天津": "531", "重庆": "551",
                "郑州": "719", "长沙": "749", "东莞": "769", "青岛": "702",
                "沈阳": "599", "宁波": "654", "昆明": "813", "合肥": "664",
                "福州": "681", "济南": "703", "厦门": "682", "珠海": "771",
                "无锡": "636", "佛山": "773", "大连": "600", "哈尔滨": "622",
            }
            
            # 获取城市代码（仅限已验证的城市）
            city_code = None
            if params.city:
                for city_name, code in zhilian_city_codes.items():
                    if city_name in params.city or params.city in city_name:
                        city_code = code
                        break
            
            # 构建搜索URL
            if city_code:
                # 热门城市使用路径格式
                url = f"https://www.zhaopin.com/sou/jl{city_code}/kw{quote(params.position)}/p{params.page}"
            elif params.city:
                # 其他城市：将城市名加入搜索关键词中
                search_term = f"{params.position} {params.city}"
                url = f"{self.base_url}/?kw={quote(search_term)}&p={params.page}"
            else:
                url = f"{self.base_url}/?kw={quote(params.position)}&p={params.page}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.5, 2.5)
            
            # 滚动页面触发加载
            self._scroll_page()
            
            # 尝试多种选择器定位职位卡片
            job_card_selectors = [
                ".joblist-box__item",
                "[class*='joblist-box'] [class*='item']",
                ".positionlist .position-item",
                "[class*='job-item']",
                "[class*='job-card']",
            ]
            
            job_cards = []
            for selector in job_card_selectors:
                try:
                    WebDriverWait(self.driver, 4).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个职位卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("智联招聘: 页面加载超时或无搜索结果")
                print(f"当前页面标题: {self.driver.title}")
                return jobs
            
            for card in job_cards[:params.page_size]:
                try:
                    job_data = self._parse_job_card(card)
                    if job_data:
                        jobs.append(job_data)
                except Exception as e:
                    print(f"解析职位卡片失败: {e}")
                    continue
                    
        except Exception as e:
            print(f"智联招聘爬取错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._close_driver()
        
        return jobs
    
    def _parse_job_card(self, card) -> Optional[JobInfo]:
        """解析职位卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        experience = ""
        education = ""
        benefits = []
        job_url = ""
        
        # 职位名称 - 使用 a.jobinfo__name
        for selector in ["a.jobinfo__name", ".jobinfo__name", "[class*='jobinfo__name']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem) or self._safe_get_attribute(elem, "title")
                if text and len(text) > 2:
                    title = text
                    # 同时获取链接
                    href = self._safe_get_attribute(elem, "href")
                    if href:
                        job_url = href
                    break
            except:
                continue
        
        # 薪资 - 使用 textContent 获取完整文本
        for selector in [".jobinfo__salary", "p.jobinfo__salary", "[class*='salary']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = elem.get_attribute("textContent")
                if text:
                    text = text.strip()
                if not text:
                    text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    salary = text
                    break
            except:
                continue
        
        # 公司名称 - 使用 a.companyinfo__name 的 title 属性
        for selector in ["a.companyinfo__name", ".companyinfo__name", "[class*='companyinfo__name']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_attribute(elem, "title") or self._safe_get_text(elem)
                if text and len(text) > 1:
                    company = text.strip()
                    break
            except:
                continue
        
        # 城市、经验、学历 - 从 .jobinfo__other-info span 获取
        try:
            info_elems = card.find_elements(By.CSS_SELECTOR, ".jobinfo__other-info span, .jobinfo__other span")
            texts = [self._safe_get_text(e) for e in info_elems if self._safe_get_text(e)]
            for text in texts:
                if any(c in text for c in ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "·"]) and not city:
                    city = text
                elif "年" in text and not experience:
                    experience = text
                elif any(c in text for c in ["科", "专", "士", "学历", "不限"]) and not education:
                    education = text
        except:
            pass
        
        # 福利标签
        try:
            welfare_elems = card.find_elements(By.CSS_SELECTOR, ".joblist-box__item-tag span, [class*='welfare'] span")
            benefits = [self._safe_get_text(w) for w in welfare_elems if self._safe_get_text(w)]
        except:
            pass
        
        if title:
            return JobInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                benefits=benefits,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class Job51SeleniumCrawler(SeleniumCrawler):
    """前程无忧 Selenium爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://we.51job.com"
    
    def get_source_name(self) -> str:
        return "前程无忧"
    
    def _scroll_page(self):
        """滚动页面以加载更多内容（已优化）"""
        try:
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except:
            pass
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        """搜索职位"""
        jobs = []
        
        try:
            self._create_driver()
            
            # 构建搜索URL - 使用新版51job
            url = f"{self.base_url}/pc/search?keyword={quote(params.position)}&searchType=2&sortType=0&pageNum={params.page}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.5, 2.5)
            
            # 滚动页面触发加载
            self._scroll_page()
            
            # 尝试多种选择器定位职位卡片
            job_card_selectors = [
                ".joblist .j_joblist .e",
                ".j_joblist .e",
                ".card",  # 新版51job使用card类
                "[class*='joblist'] .e",
                ".elist .e",
            ]
            
            job_cards = []
            for selector in job_card_selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个职位卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("前程无忧: 页面加载超时或无搜索结果")
                print(f"当前页面标题: {self.driver.title}")
                # 保存调试HTML
                try:
                    with open("job51_debug_live.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                except:
                    pass
                return jobs
            
            for card in job_cards[:params.page_size]:
                try:
                    job_data = self._parse_job_card(card)
                    if job_data:
                        jobs.append(job_data)
                except Exception as e:
                    print(f"解析职位卡片失败: {e}")
                    continue
                    
        except Exception as e:
            print(f"前程无忧爬取错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._close_driver()
        
        return jobs
    
    def _parse_job_card(self, card) -> Optional[JobInfo]:
        """解析职位卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        experience = ""
        education = ""
        job_url = ""
        
        # 职位名称 - 新版51job使用不同的类名
        for selector in [".c-top .name", ".jname", ".job_name", "[class*='jname']", "[class*='job-name']", "a[title]"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem) or self._safe_get_attribute(elem, "title")
                if text and len(text) > 2:
                    title = text.strip()
                    break
            except:
                continue
        
        # 薪资 - 新版51job使用 .c-top .salary
        for selector in [".c-top .salary", ".sal", ".salary", "[class*='salary']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text:
                    salary = text.strip()
                    break
            except:
                continue
        
        # 公司名称 - 新版51job使用 .c-mid
        for selector in [".c-mid", ".cname", ".companyname", "[class*='cname']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 1:
                    company = text.strip()
                    break
            except:
                continue
        
        # 城市和条件 - 从标签获取
        try:
            tag_elems = card.find_elements(By.CSS_SELECTOR, ".c-tags .tag, .d .at span, .dc span")
            texts = [self._safe_get_text(e) for e in tag_elems if self._safe_get_text(e)]
            for text in texts:
                if any(c in text for c in ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "区", "市"]) and not city:
                    city = text
                elif "年" in text and not experience:
                    experience = text
                elif any(c in text for c in ["科", "专", "士", "学历", "不限"]) and not education:
                    education = text
        except:
            pass
        
        # 职位链接
        for selector in ["a[href*='51job']", "a[href*='jobs']", "a"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                href = self._safe_get_attribute(elem, "href")
                if href and ("51job" in href or "jobs" in href):
                    job_url = href
                    break
            except:
                continue
        
        if title:
            return JobInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class SeleniumJobCrawlerManager:
    """Selenium爬虫管理器 - 优化版：使用单浏览器多标签页并行爬取"""
    
    def __init__(self, sources: List[str] = None, headless: bool = True, show_progress: bool = True):
        """
        初始化爬虫管理器
        
        Args:
            sources: 要爬取的网站列表，可选值: boss, liepin, zhilian, job51
            headless: 是否使用无头模式
            show_progress: 是否显示进度信息
        """
        self.headless = headless
        self.show_progress = show_progress
        self.crawler_classes = {
            "boss": BossZhipinSeleniumCrawler,
            "liepin": LiepinSeleniumCrawler,
            "zhilian": ZhilianSeleniumCrawler,
            "job51": Job51SeleniumCrawler,
        }
        
        if sources is None:
            sources = list(self.crawler_classes.keys())
        
        self.sources = [s.lower() for s in sources if s.lower() in self.crawler_classes]
        
        # 线程锁，用于保护共享数据
        self._lock = threading.Lock()
        
        # 共享浏览器实例
        self._shared_driver = None
    
    def _log(self, message: str):
        """打印日志（根据 show_progress 控制）"""
        if self.show_progress:
            print(message)
    
    def _create_shared_driver(self):
        """创建共享的WebDriver实例"""
        options = Options()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 性能优化：禁用图片、CSS等资源加载
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
        }
        options.add_experimental_option("prefs", prefs)
        
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        self._shared_driver = webdriver.Chrome(options=options)
        self._shared_driver.set_page_load_timeout(30)
        
        # 执行CDP命令隐藏WebDriver
        self._shared_driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
    
    def _close_shared_driver(self):
        """关闭共享的WebDriver"""
        if self._shared_driver:
            try:
                self._shared_driver.quit()
            except:
                pass
            self._shared_driver = None
    
    def _crawl_single_source(self, source: str, params: JobSearchParams) -> tuple:
        """
        爬取单个数据源（用于多线程，每个线程独立浏览器）
        
        Args:
            source: 数据源名称
            params: 搜索参数
            
        Returns:
            (source_name, jobs_list) 元组
        """
        crawler_class = self.crawler_classes[source]
        crawler = crawler_class(headless=self.headless)
        
        print(f"\n[线程] 正在从 {crawler.get_source_name()} 获取数据...")
        try:
            jobs = crawler.search(params)
            print(f"[线程] {crawler.get_source_name()} 获取完成，共 {len(jobs)} 个职位")
            return (crawler.get_source_name(), jobs)
        except Exception as e:
            print(f"[线程] {crawler.get_source_name()} 爬取失败: {e}")
            return (crawler.get_source_name(), [])
    
    def _crawl_with_tab(self, source: str, params: JobSearchParams, tab_handle: str) -> tuple:
        """
        使用指定标签页爬取数据（单浏览器多标签页模式）
        
        Args:
            source: 数据源名称
            params: 搜索参数
            tab_handle: 标签页句柄
            
        Returns:
            (source_name, jobs_list) 元组
        """
        crawler_class = self.crawler_classes[source]
        # 创建一个临时爬虫实例来获取方法
        temp_crawler = crawler_class.__new__(crawler_class)
        temp_crawler.headless = self.headless
        temp_crawler.driver = None
        
        source_name = {
            "boss": "Boss直聘",
            "liepin": "猎聘", 
            "zhilian": "智联招聘",
            "job51": "前程无忧"
        }.get(source, source)
        
        print(f"\n[标签页] 正在从 {source_name} 获取数据...")
        
        try:
            # 切换到指定标签页
            with self._lock:
                self._shared_driver.switch_to.window(tab_handle)
            
            # 根据不同来源构建URL并访问
            jobs = self._crawl_source_in_tab(source, params, source_name)
            print(f"[标签页] {source_name} 获取完成，共 {len(jobs)} 个职位")
            return (source_name, jobs)
            
        except Exception as e:
            print(f"[标签页] {source_name} 爬取失败: {e}")
            import traceback
            traceback.print_exc()
            return (source_name, [])
    
    def _crawl_source_in_tab(self, source: str, params: JobSearchParams, source_name: str) -> List[JobInfo]:
        """在当前标签页中爬取指定数据源"""
        jobs = []
        driver = self._shared_driver
        
        # 构建URL
        if source == "boss":
            city_codes = {
                "全国": "100010000", "北京": "101010100", "上海": "101020100",
                "广州": "101280100", "深圳": "101280600", "杭州": "101210100",
                "成都": "101270100", "南京": "101190100", "武汉": "101200100",
                "西安": "101110100", "苏州": "101190400", "天津": "101030100",
                "重庆": "101040100",
            }
            city_code = "100010000"
            for key, code in city_codes.items():
                if params.city and (key in params.city or params.city in key):
                    city_code = code
                    break
            url = f"https://www.zhipin.com/web/geek/job?query={quote(params.position)}&city={city_code}&page={params.page}"
            selectors = [".job-card-wrap", ".job-card-box", "li.job-card-box"]
            
        elif source == "liepin":
            city_param = f"&city={quote(params.city)}" if params.city else ""
            url = f"https://www.liepin.com/zhaopin/?key={quote(params.position)}{city_param}&currentPage={params.page - 1}"
            selectors = [".job-list-item", "[class*='job-list-item']", "[class*='job-card']"]
            
        elif source == "zhilian":
            city_param = f"&jl={quote(params.city)}" if params.city else ""
            url = f"https://sou.zhaopin.com/?kw={quote(params.position)}{city_param}&p={params.page}"
            selectors = [".joblist-box__item", "[class*='joblist-box'] [class*='item']"]
            
        elif source == "job51":
            url = f"https://we.51job.com/pc/search?keyword={quote(params.position)}&searchType=2&sortType=0&pageNum={params.page}"
            selectors = [".joblist .j_joblist .e", ".j_joblist .e", ".card"]
        else:
            return jobs
        
        print(f"正在访问: {url}")
        driver.get(url)
        time.sleep(random.uniform(1.5, 2.5))
        
        # 快速滚动
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(0.2)
        driver.execute_script("window.scrollTo(0, 0);")
        
        # 查找职位卡片
        job_cards = []
        for selector in selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                job_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if job_cards:
                    print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个职位卡片")
                    break
            except TimeoutException:
                continue
        
        if not job_cards:
            print(f"{source_name}: 未找到职位卡片")
            return jobs
        
        # 解析职位卡片
        for card in job_cards[:params.page_size]:
            try:
                job_data = self._parse_card_generic(card, source, source_name)
                if job_data:
                    jobs.append(job_data)
            except Exception as e:
                continue
        
        return jobs
    
    def _parse_card_generic(self, card, source: str, source_name: str) -> Optional[JobInfo]:
        """通用的职位卡片解析方法"""
        title = ""
        salary = ""
        company = ""
        city = ""
        experience = ""
        education = ""
        job_url = ""
        
        def safe_get_text(elem) -> str:
            try:
                return elem.text.strip() if elem else ""
            except:
                return ""
        
        def safe_get_attr(elem, attr) -> str:
            try:
                return elem.get_attribute(attr) if elem else ""
            except:
                return ""
        
        if source == "boss":
            # Boss直聘解析
            for sel in ["a.job-name", ".job-name", ".job-title a"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    title = safe_get_text(elem)
                    job_url = safe_get_attr(elem, "href")
                    if title:
                        break
                except:
                    continue
            
            for sel in [".salary", ".job-salary", "span.salary", "span.job-salary", "[class*='salary']"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    # 使用 textContent 获取完整文本
                    salary = safe_get_attr(elem, "textContent")
                    if salary:
                        salary = salary.strip()
                    if not salary:
                        salary = safe_get_text(elem)
                    if salary and len(salary) > 1:
                        break
                except:
                    continue
            
            for sel in [".boss-name", "span.boss-name"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    company = safe_get_text(elem)
                    if company:
                        break
                except:
                    continue
            
            for sel in [".company-location", "span.company-location"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    city = safe_get_text(elem)
                    if city:
                        break
                except:
                    continue
            
            try:
                tags = card.find_elements(By.CSS_SELECTOR, ".tag-list li")
                for i, tag in enumerate(tags):
                    text = safe_get_text(tag)
                    if i == 0:
                        experience = text
                    elif i == 1:
                        education = text
            except:
                pass
                
        elif source == "liepin":
            # 猎聘解析
            for sel in [".job-title-box .ellipsis-1", ".job-title", "h3"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    text = safe_get_text(elem)
                    if text and len(text) > 2 and "在线" not in text:
                        title = text
                        break
                except:
                    continue
            
            for sel in [".job-salary", "[class*='salary']"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    # 使用 textContent 获取完整文本
                    text = safe_get_attr(elem, "textContent")
                    if text:
                        text = text.strip()
                    if not text:
                        text = safe_get_text(elem)
                    if text and ("K" in text or "k" in text or "元" in text or "万" in text):
                        salary = text
                        break
                except:
                    continue
            
            for sel in [".company-name a", ".company-name"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    company = safe_get_text(elem)
                    if company:
                        break
                except:
                    continue
            
            for sel in [".job-dq-box .ellipsis-1", ".job-dq"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    city = safe_get_text(elem)
                    if city:
                        break
                except:
                    continue
            
            try:
                labels = card.find_elements(By.CSS_SELECTOR, ".job-labels-box .labels-tag")
                for label in labels:
                    text = safe_get_text(label)
                    if ("年" in text or "经验" in text) and not experience:
                        experience = text
                    elif ("科" in text or "专" in text or "士" in text) and not education:
                        education = text
            except:
                pass
            
            for sel in ["a[href*='/job/']"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    href = safe_get_attr(elem, "href")
                    if href and "liepin" in href:
                        job_url = href
                        break
                except:
                    continue
                    
        elif source == "zhilian":
            # 智联招聘解析
            for sel in ["a.jobinfo__name", ".jobinfo__name"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    title = safe_get_text(elem) or safe_get_attr(elem, "title")
                    job_url = safe_get_attr(elem, "href")
                    if title:
                        break
                except:
                    continue
            
            for sel in [".jobinfo__salary", "p.jobinfo__salary"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    salary = safe_get_text(elem)
                    if salary:
                        break
                except:
                    continue
            
            for sel in ["a.companyinfo__name", ".companyinfo__name"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    company = safe_get_attr(elem, "title") or safe_get_text(elem)
                    if company:
                        break
                except:
                    continue
            
            try:
                infos = card.find_elements(By.CSS_SELECTOR, ".jobinfo__other-info span")
                for info in infos:
                    text = safe_get_text(info)
                    if any(c in text for c in ["北京", "上海", "广州", "深圳", "·"]) and not city:
                        city = text
                    elif "年" in text and not experience:
                        experience = text
                    elif any(c in text for c in ["科", "专", "士", "不限"]) and not education:
                        education = text
            except:
                pass
                
        elif source == "job51":
            # 前程无忧解析
            for sel in [".c-top .name", ".jname", ".job_name", "a[title]"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    title = safe_get_text(elem) or safe_get_attr(elem, "title")
                    if title:
                        break
                except:
                    continue
            
            for sel in [".c-top .salary", ".sal", ".salary"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    salary = safe_get_text(elem)
                    if salary:
                        break
                except:
                    continue
            
            for sel in [".c-mid", ".cname", ".companyname"]:
                try:
                    elem = card.find_element(By.CSS_SELECTOR, sel)
                    company = safe_get_text(elem)
                    if company:
                        break
                except:
                    continue
            
            try:
                tags = card.find_elements(By.CSS_SELECTOR, ".c-tags .tag, .d .at span")
                for tag in tags:
                    text = safe_get_text(tag)
                    if any(c in text for c in ["北京", "上海", "广州", "深圳", "区", "市"]) and not city:
                        city = text
                    elif "年" in text and not experience:
                        experience = text
                    elif any(c in text for c in ["科", "专", "士", "不限"]) and not education:
                        education = text
            except:
                pass
        
        if title:
            return JobInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                job_url=job_url,
                source=source_name,
            )
        
        return None
    
    def search(self, params: JobSearchParams) -> Dict[str, Any]:
        """
        搜索职位（使用多线程并行爬取，每个线程独立浏览器）
        
        Args:
            params: 搜索参数
            
        Returns:
            包含搜索结果的字典
        """
        all_jobs = []
        source_stats = {}
        seen_urls = set()  # 用于去重
        
        self._log(f"\n启动多线程爬取，共 {len(self.sources)} 个数据源...")
        
        # 使用线程池并行爬取所有数据源
        with ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            # 提交所有爬取任务
            future_to_source = {
                executor.submit(self._crawl_single_source, source, params): source
                for source in self.sources
            }
            
            # 收集结果
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    source_name, jobs = future.result()
                    
                    # 去重：根据职位URL去重
                    unique_jobs = []
                    with self._lock:
                        for job in jobs:
                            # 生成唯一标识：使用URL或者职位名+公司名
                            job_key = job.job_url if job.job_url else f"{job.title}_{job.company}"
                            if job_key and job_key not in seen_urls:
                                seen_urls.add(job_key)
                                unique_jobs.append(job)
                        
                        all_jobs.extend(unique_jobs)
                    
                    source_stats[source_name] = len(unique_jobs)
                    
                except Exception as e:
                    self._log(f"获取 {source} 结果时出错: {e}")
                    source_stats[source] = 0
        
        self._log(f"\n所有数据源爬取完成！")
        
        result = {
            "success": True,
            "message": "搜索完成",
            "params": {
                "position": params.position,
                "city": params.city or "不限",
                "experience": params.experience or "不限",
                "education": params.education or "不限",
                "salary": params.salary or "不限",
                "page": params.page,
                "page_size": params.page_size,
            },
            "statistics": {
                "total": len(all_jobs),
                "by_source": source_stats,
            },
            "jobs": [asdict(job) for job in all_jobs],
        }
        
        return result
    
    def search_with_shared_browser(self, params: JobSearchParams) -> Dict[str, Any]:
        """
        搜索职位（使用单浏览器多标签页串行爬取 - 节省浏览器启动时间）
        
        Args:
            params: 搜索参数
            
        Returns:
            包含搜索结果的字典
        """
        all_jobs = []
        source_stats = {}
        seen_urls = set()
        
        print(f"\n启动单浏览器模式爬取，共 {len(self.sources)} 个数据源...")
        
        try:
            # 创建共享浏览器
            self._create_shared_driver()
            
            # 串行爬取每个数据源
            for source in self.sources:
                source_name = {
                    "boss": "Boss直聘",
                    "liepin": "猎聘",
                    "zhilian": "智联招聘",
                    "job51": "前程无忧"
                }.get(source, source)
                
                print(f"\n正在从 {source_name} 获取数据...")
                
                try:
                    jobs = self._crawl_source_in_tab(source, params, source_name)
                    
                    # 去重
                    unique_jobs = []
                    for job in jobs:
                        job_key = job.job_url if job.job_url else f"{job.title}_{job.company}"
                        if job_key and job_key not in seen_urls:
                            seen_urls.add(job_key)
                            unique_jobs.append(job)
                    
                    all_jobs.extend(unique_jobs)
                    source_stats[source_name] = len(unique_jobs)
                    print(f"{source_name} 获取完成，共 {len(unique_jobs)} 个职位")
                    
                except Exception as e:
                    print(f"{source_name} 爬取失败: {e}")
                    source_stats[source_name] = 0
                    
        finally:
            self._close_shared_driver()
        
        print(f"\n所有数据源爬取完成！")
        
        result = {
            "success": True,
            "message": "搜索完成",
            "params": {
                "position": params.position,
                "city": params.city or "不限",
                "experience": params.experience or "不限",
                "education": params.education or "不限",
                "salary": params.salary or "不限",
                "page": params.page,
                "page_size": params.page_size,
            },
            "statistics": {
                "total": len(all_jobs),
                "by_source": source_stats,
            },
            "jobs": [asdict(job) for job in all_jobs],
        }
        
        return result
    
    def search_and_save(self, params: JobSearchParams, output_file: str = "jobs_result.json") -> str:
        """搜索职位并保存到文件"""
        result = self.search(params)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存到: {output_file}")
        print(f"共找到 {result['statistics']['total']} 个职位")
        for source, count in result['statistics']['by_source'].items():
            print(f"  - {source}: {count} 个")
        
        return output_file


def filter_jobs_by_city(jobs: List[dict], city: str, min_results: int = 5) -> List[dict]:
    """
    根据城市过滤职位列表
    
    Args:
        jobs: 职位列表
        city: 目标城市
        min_results: 最少返回的职位数量，如果匹配结果不足则补充其他城市的职位
        
    Returns:
        过滤后的职位列表
    """
    if not city:
        return jobs
    
    matched = []  # 完全匹配的职位
    unmatched = []  # 不匹配的职位
    city_lower = city.lower().strip()
    
    for job in jobs:
        job_city = job.get("city", "").lower().strip()
        
        # 如果职位没有城市信息，保留该职位（算作匹配）
        if not job_city:
            matched.append(job)
            continue
        
        # 标准化城市字段：统一分隔符
        # 支持 "西安·雁塔", "西安-雁塔区", "西安 雁塔" 等格式
        job_city_normalized = job_city.replace("-", "·").replace(" ", "·")
        
        # 提取主城市名（第一个分隔符之前的部分）
        job_main_city = job_city_normalized.split("·")[0] if "·" in job_city_normalized else job_city_normalized
        
        # 匹配逻辑（更宽松）：
        # 1. 搜索城市包含在职位城市中（如 "西安" in "西安·雁塔"）
        # 2. 职位主城市包含搜索城市（如 "西安" in "西安市"）
        # 3. 搜索城市包含职位主城市（如 "西安市" 包含 "西安"）
        if (city_lower in job_city_normalized or 
            city_lower in job_main_city or 
            job_main_city in city_lower):
            matched.append(job)
        else:
            unmatched.append(job)
    
    # 如果匹配结果不足 min_results 个，从不匹配的职位中补充
    if len(matched) < min_results and unmatched:
        need_count = min_results - len(matched)
        matched.extend(unmatched[:need_count])
    
    return matched


def search_jobs_selenium(
    position: str,
    city: str = "",
    experience: str = "",
    education: str = "",
    salary: str = "",
    page: int = 1,
    page_size: int = 20,
    sources: List[str] = None,
    headless: bool = True,
    save_to_file: bool = False,
    output_file: str = "jobs_result.json",
    mode: str = "parallel",  # "parallel" 多线程并行 | "shared" 单浏览器串行
    show_progress: bool = True,  # 是否显示进度信息
    filter_by_city: bool = True  # 是否根据城市过滤结果
) -> Dict[str, Any]:
    """
    使用Selenium搜索职位的便捷函数
    
    Args:
        position: 岗位名称（必填）
        city: 意向城市
        experience: 工作经验
        education: 学历要求
        salary: 期望薪资
        page: 页码
        page_size: 每页数量
        sources: 数据来源，可选: boss, liepin, zhilian, job51
        headless: 是否使用无头模式
        save_to_file: 是否保存到文件
        output_file: 输出文件路径
        mode: 爬取模式
              - "parallel": 多线程并行（每个源独立浏览器，速度快但占用资源多）
              - "shared": 单浏览器串行（复用浏览器，节省资源但速度稍慢）
        show_progress: 是否显示进度信息
        filter_by_city: 是否根据城市过滤结果（默认开启）
        
    Returns:
        包含搜索结果的字典
    """
    params = JobSearchParams(
        position=position,
        city=city,
        experience=experience,
        education=education,
        salary=salary,
        page=page,
        page_size=page_size,
    )
    
    manager = SeleniumJobCrawlerManager(sources=sources, headless=headless, show_progress=show_progress)
    
    # 根据模式选择搜索方法
    if mode == "shared":
        result = manager.search_with_shared_browser(params)
    else:
        result = manager.search(params)
    
    # 根据城市过滤结果
    if filter_by_city and city:
        original_count = len(result.get("jobs", []))
        filtered_jobs = filter_jobs_by_city(result.get("jobs", []), city)
        result["jobs"] = filtered_jobs
        result["statistics"]["total"] = len(filtered_jobs)
        result["statistics"]["filtered_count"] = original_count - len(filtered_jobs)
        
        # 重新统计各来源数量
        by_source = {}
        for job in filtered_jobs:
            source = job.get("source", "未知")
            by_source[source] = by_source.get(source, 0) + 1
        result["statistics"]["by_source"] = by_source
        
        if show_progress and original_count != len(filtered_jobs):
            print(f"[城市过滤] 从 {original_count} 个职位中筛选出 {len(filtered_jobs)} 个 {city} 的职位")
    
    if save_to_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        if show_progress:
            print(f"\n结果已保存到: {output_file}")
    
    return result


# 示例用法
if __name__ == "__main__":
    if not SELENIUM_AVAILABLE:
        print("请先安装selenium: pip install selenium")
        print("还需要安装Chrome浏览器和对应版本的ChromeDriver")
        exit(1)
    
    # 示例：搜索Python开发工程师职位
    # 设置 headless=False 可以看到浏览器运行过程，便于调试
    result = search_jobs_selenium(
        position="Python开发",  # 岗位名称（必填）
        city="北京",           # 意向城市
        experience="",         # 工作经验
        education="",          # 学历要求
        page=1,                # 页码
        page_size=10,          # 每页数量
        sources=["boss", "liepin"],  # 测试多个网站
        headless=False,        # 设置为False可以看到浏览器运行
        save_to_file=True,     # 保存到文件
        output_file="jobs_selenium_result.json"
    )
    
    # 打印结果预览
    print("\n" + "="*60)
    print("搜索结果预览:")
    print("="*60)
    
    jobs = result.get("jobs", [])
    if jobs:
        for i, job in enumerate(jobs[:5], 1):
            print(f"\n{i}. {job['title']}")
            print(f"   公司: {job['company']}")
            print(f"   薪资: {job['salary']}")
            print(f"   城市: {job['city']}")
            print(f"   经验: {job['experience']} | 学历: {job['education']}")
            print(f"   来源: {job['source']}")
            if job['job_url']:
                print(f"   链接: {job['job_url']}")
    else:
        print("\n未找到任何职位信息")
        print("可能原因:")
        print("1. 网站需要登录或验证")
        print("2. CSS选择器需要更新")
        print("3. 网络连接问题")
        print("\n建议: 设置 headless=False 查看浏览器运行过程")
