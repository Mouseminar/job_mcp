"""
实习信息爬虫程序 - Selenium版本
使用浏览器模拟访问，可以更好地绑过反爬虫机制
支持: 实习僧、刺猬实习、Boss直聘实习、猎聘实习
"""

import json
import time
import random
import re
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
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

# 尝试导入 undetected-chromedriver
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False


# 全局配置
_config = None

def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    global _config
    
    if _config is not None:
        return _config
    
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "intern_config.yaml")
    
    default_config = {
        "search": {"position": "", "city": "", "education": "", "page": 1, "page_size": 20},
        "sources": {"enabled": ["shixiseng", "ciwei", "boss_intern"]},
        "browser": {"headless": True, "page_load_timeout": 15},
        "crawl": {"mode": "parallel", "delay": {"min": 1.5, "max": 2.5}},
        "output": {"file": "interns_result.json", "save_by_default": False},
        "city_codes": {
            "全国": "", "北京": "北京", "上海": "上海", "广州": "广州",
            "深圳": "深圳", "杭州": "杭州", "成都": "成都", "南京": "南京",
            "武汉": "武汉", "西安": "西安", "苏州": "苏州", "天津": "天津",
        },
        "display": {"show_progress": True, "max_display_jobs": 10, "color_output": True},
    }
    
    if YAML_AVAILABLE and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    for key, value in user_config.items():
                        if key in default_config and isinstance(value, dict):
                            default_config[key].update(value)
                        else:
                            default_config[key] = value
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
    
    _config = default_config
    return _config


@dataclass
class InternSearchParams:
    """实习搜索参数"""
    position: str  # 岗位名称（必填）
    city: str = ""  # 意向城市
    education: str = ""  # 学历要求
    duration: str = ""  # 实习时长要求
    days_per_week: str = ""  # 每周出勤天数
    page: int = 1  # 页码
    page_size: int = 20  # 每页数量


@dataclass
class InternInfo:
    """实习信息"""
    title: str  # 职位名称
    company: str  # 公司名称
    salary: str  # 薪资（日薪/月薪）
    city: str  # 工作城市
    education: str = ""  # 学历要求
    duration: str = ""  # 实习时长
    days_per_week: str = ""  # 每周天数
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
        
        # 性能优化
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
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        
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
        """随机延迟"""
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
    
    def _scroll_page(self):
        """滚动页面"""
        try:
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(0.2)
            self.driver.execute_script("window.scrollTo(0, 0);")
        except:
            pass


class ShixisengCrawler(SeleniumCrawler):
    """实习僧爬虫 - 最大的实习招聘平台"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.shixiseng.com"
    
    def get_source_name(self) -> str:
        return "实习僧"
    
    def search(self, params: InternSearchParams) -> List[InternInfo]:
        """搜索实习"""
        interns = []
        
        try:
            self._create_driver()
            
            # 实习僧城市代码
            city_codes = {
                "北京": "110100", "上海": "310100", "广州": "440100", "深圳": "440300",
                "杭州": "330100", "成都": "510100", "南京": "320100", "武汉": "420100",
                "西安": "610100", "苏州": "320500", "天津": "120100", "重庆": "500100",
                "郑州": "410100", "长沙": "430100", "东莞": "441900", "青岛": "370200",
                "太原": "140100", "济南": "370100", "厦门": "350200", "福州": "350100",
                "合肥": "340100", "昆明": "530100", "大连": "210200", "沈阳": "210100",
                "哈尔滨": "230100", "长春": "220100", "南昌": "360100", "无锡": "320200",
                "宁波": "330200", "佛山": "440600", "珠海": "440400", "石家庄": "130100",
            }
            
            city_code = ""
            if params.city:
                for city_name, code in city_codes.items():
                    if city_name in params.city or params.city in city_name:
                        city_code = code
                        break
                
                # 提示：即使有城市代码，实习僧在该城市可能也没有数据
                if city_code:
                    print(f"[提示] 正在搜索 {params.city} 的实习...")
                else:
                    print(f"[警告] 实习僧不支持 '{params.city}' 城市筛选，将搜索全国范围")
            
            # 构建URL
            city_param = f"&c={city_code}" if city_code else ""
            url = f"{self.base_url}/interns?k={quote(params.position)}{city_param}&p={params.page}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.5, 2.5)
            self._scroll_page()
            
            # 查找实习卡片
            selectors = [
                ".intern-wrap .intern-item",
                ".intern-item",
                "[class*='intern-item']",
                ".job-item",
            ]
            
            job_cards = []
            for selector in selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个实习卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("实习僧: 页面加载超时或无搜索结果")
                print(f"当前页面标题: {self.driver.title}")
                return interns
            
            for card in job_cards[:params.page_size]:
                try:
                    intern_data = self._parse_intern_card(card)
                    if intern_data:
                        interns.append(intern_data)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"实习僧爬取错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._close_driver()
        
        return interns
    
    def _parse_intern_card(self, card) -> Optional[InternInfo]:
        """解析实习卡片
        
        注意：实习僧使用字体反爬技术，部分文字会显示异常（如 &#xf334）
        这些通过CSS渲染后显示正常，但无法直接抓取
        我们优先获取HTML的title属性，它通常包含正确的文字
        """
        title = ""
        salary = ""
        company = ""
        city = ""
        education = ""
        duration = ""
        days_per_week = ""
        job_url = ""
        
        # 职位名称 - 优先从title属性获取，因为text可能被字体反爬
        for selector in ["a.title", ".intern-detail__job a.title", ".title"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                # 优先使用title属性（不受字体反爬影响）
                title = self._safe_get_attribute(elem, "title") or self._safe_get_text(elem)
                href = self._safe_get_attribute(elem, "href")
                if href:
                    job_url = href if href.startswith("http") else self.base_url + href
                if title:
                    break
            except:
                continue
        
        # 薪资 - 格式: "xxx/天"
        for selector in [".day.font", ".day", "span.day"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text:
                    salary = text.replace("-/天", "面议").strip()
                    break
            except:
                continue
        
        # 公司名称 - 从company区域获取
        for selector in [".intern-detail__company a.title", ".intern-detail__company .title", ".company-name"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                # 优先使用title属性
                company = self._safe_get_attribute(elem, "title") or self._safe_get_text(elem)
                if company:
                    break
            except:
                continue
        
        # 城市 - 明确的city类
        try:
            city_elem = card.find_element(By.CSS_SELECTOR, ".city")
            city = self._safe_get_text(city_elem)
        except:
            pass
        
        # 工作天数和实习时长 - 从tip区域的font类元素获取
        try:
            tip_fonts = card.find_elements(By.CSS_SELECTOR, ".tip .font")
            for font in tip_fonts:
                text = self._safe_get_text(font)
                if not text:
                    continue
                if "天" in text and "周" in text:
                    days_per_week = text
                elif "月" in text:
                    duration = text
        except:
            pass
        
        if title:
            return InternInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                education=education,
                duration=duration,
                days_per_week=days_per_week,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class CiweiCrawler(SeleniumCrawler):
    """刺猬实习爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.ciweishixi.com"
    
    def get_source_name(self) -> str:
        return "刺猬实习"
    
    def search(self, params: InternSearchParams) -> List[InternInfo]:
        """搜索实习"""
        interns = []
        
        try:
            self._create_driver()
            
            # 构建URL
            city_param = f"&city={quote(params.city)}" if params.city else ""
            url = f"{self.base_url}/search?key={quote(params.position)}{city_param}&page={params.page}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.5, 2.5)
            self._scroll_page()
            
            # 查找实习卡片
            selectors = [
                ".job-list .job-item",
                ".job-item",
                "[class*='job-item']",
                ".internship-item",
            ]
            
            job_cards = []
            for selector in selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个实习卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("刺猬实习: 页面加载超时或无搜索结果")
                print(f"当前页面标题: {self.driver.title}")
                return interns
            
            for card in job_cards[:params.page_size]:
                try:
                    intern_data = self._parse_intern_card(card)
                    if intern_data:
                        interns.append(intern_data)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"刺猬实习爬取错误: {e}")
        finally:
            self._close_driver()
        
        return interns
    
    def _parse_intern_card(self, card) -> Optional[InternInfo]:
        """解析实习卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        education = ""
        duration = ""
        days_per_week = ""
        job_url = ""
        
        # 职位名称
        for selector in [".job-title a", ".job-title", ".title a", ".title"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                title = self._safe_get_text(elem)
                href = self._safe_get_attribute(elem, "href")
                if href:
                    job_url = href if href.startswith("http") else self.base_url + href
                if title:
                    break
            except:
                continue
        
        # 薪资
        for selector in [".salary", ".money", ".pay"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                salary = self._safe_get_text(elem)
                if salary:
                    break
            except:
                continue
        
        # 公司名称
        for selector in [".company-name", ".company a", ".company"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                company = self._safe_get_text(elem)
                if company:
                    break
            except:
                continue
        
        # 城市和信息
        try:
            info_elems = card.find_elements(By.CSS_SELECTOR, ".info span, .tags span, .demand span")
            for elem in info_elems:
                text = self._safe_get_text(elem)
                if not text:
                    continue
                if any(c in text for c in ["北京", "上海", "广州", "深圳", "杭州"]) and not city:
                    city = text
                elif "天" in text and "/" in text and not days_per_week:
                    days_per_week = text
                elif "月" in text and not duration:
                    duration = text
        except:
            pass
        
        if title:
            return InternInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                education=education,
                duration=duration,
                days_per_week=days_per_week,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class BossInternCrawler(SeleniumCrawler):
    """Boss直聘实习爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.zhipin.com"
        
        self.city_codes = {
            "全国": "100010000", "北京": "101010100", "上海": "101020100",
            "广州": "101280100", "深圳": "101280600", "杭州": "101210100",
            "成都": "101270100", "南京": "101190100", "武汉": "101200100",
            "西安": "101110100", "苏州": "101190400", "天津": "101030100",
            "重庆": "101040100",
        }
    
    def get_source_name(self) -> str:
        return "Boss直聘(实习)"
    
    def _create_driver(self):
        """创建 WebDriver - 优先使用 undetected-chromedriver"""
        if UC_AVAILABLE:
            try:
                options = uc.ChromeOptions()
                
                if self.headless:
                    options.add_argument("--headless=new")
                
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-logging")
                options.add_argument("--log-level=3")
                
                self.driver = uc.Chrome(options=options, use_subprocess=True)
                self.driver.set_page_load_timeout(30)
                return
            except Exception as e:
                print(f"undetected-chromedriver 初始化失败: {e}")
                print("回退到普通 selenium...")
        
        # 回退到普通 selenium
        super()._create_driver()
    
    def _get_city_code(self, city: str) -> str:
        if not city:
            return "100010000"
        for key, code in self.city_codes.items():
            if key in city or city in key:
                return code
        return "100010000"
    
    def search(self, params: InternSearchParams) -> List[InternInfo]:
        """搜索实习"""
        interns = []
        
        try:
            self._create_driver()
            city_code = self._get_city_code(params.city)
            
            # 添加实习筛选参数 (stage=303 表示实习)
            url = f"{self.base_url}/web/geek/job?query={quote(params.position)}&city={city_code}&stage=303&page={params.page}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(2.0, 3.0)
            self._scroll_page()
            
            # 检查验证页面
            if "验证" in self.driver.title or "验证" in self.driver.page_source[:2000]:
                print("Boss直聘需要人工验证，跳过此数据源")
                return interns
            
            selectors = [".job-card-wrap", ".job-card-box", "li.job-card-box"]
            
            job_cards = []
            for selector in selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个实习卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("Boss直聘(实习): 未找到实习卡片")
                return interns
            
            for card in job_cards[:params.page_size]:
                try:
                    intern_data = self._parse_intern_card(card)
                    if intern_data:
                        interns.append(intern_data)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"Boss直聘(实习)爬取错误: {e}")
        finally:
            self._close_driver()
        
        return interns
    
    def _parse_intern_card(self, card) -> Optional[InternInfo]:
        """解析实习卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        education = ""
        job_url = ""
        
        # 职位名称
        for selector in ["a.job-name", ".job-name", ".job-title a"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                title = self._safe_get_text(elem)
                job_url = self._safe_get_attribute(elem, "href")
                if title:
                    break
            except:
                continue
        
        # 薪资
        for selector in [".salary", ".job-salary", "span.salary"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = elem.get_attribute("textContent")
                if text:
                    salary = text.strip()
                if not salary:
                    salary = self._safe_get_text(elem)
                if salary:
                    break
            except:
                continue
        
        # 公司名称
        for selector in [".company-name a", ".company-name", ".boss-name"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                company = self._safe_get_text(elem)
                if company:
                    break
            except:
                continue
        
        # 城市
        for selector in [".company-location", "span.company-location"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                city = self._safe_get_text(elem)
                if city:
                    break
            except:
                continue
        
        # 经验和学历
        try:
            tags = card.find_elements(By.CSS_SELECTOR, ".tag-list li")
            for tag in tags:
                text = self._safe_get_text(tag)
                if any(c in text for c in ["本科", "硕士", "大专", "学历"]) and not education:
                    education = text
        except:
            pass
        
        if title:
            return InternInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                education=education,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class LiepinInternCrawler(SeleniumCrawler):
    """猎聘实习爬虫"""
    
    def __init__(self, headless: bool = True):
        super().__init__(headless)
        self.base_url = "https://www.liepin.com"
    
    def get_source_name(self) -> str:
        return "猎聘(实习)"
    
    def search(self, params: InternSearchParams) -> List[InternInfo]:
        """搜索实习"""
        interns = []
        
        try:
            self._create_driver()
            
            # 猎聘城市代码 - 注意：猎聘对二线城市支持有限，部分城市可能没有专门代码
            liepin_city_codes = {
                # 一线城市
                "北京": "010", "上海": "020", "广州": "050020", "深圳": "050090",
                # 新一线城市
                "杭州": "070020", "成都": "280020", "南京": "060020", "武汉": "170020",
                "西安": "270020", "苏州": "060080", "天津": "030", "重庆": "040",
                "郑州": "180020", "长沙": "210020", "青岛": "250060", "东莞": "050040",
                # 二线城市
                "济南": "250020", "厦门": "090040", "福州": "090020",
                "合肥": "190020", "昆明": "310020", "大连": "120040", "沈阳": "120020",
                "哈尔滨": "130020", "长春": "140020", "南昌": "200020", "无锡": "060040",
                "宁波": "070060", "佛山": "050050", "珠海": "050060", "石家庄": "160020",
                # 注意：太原、兰州等城市在猎聘上属于"其他"类别，没有单独代码
            }
            
            city_code = None
            if params.city:
                for city_name, code in liepin_city_codes.items():
                    if city_name in params.city or params.city in city_name:
                        city_code = code
                        break
                
                # 如果城市不在支持列表中，给出提示
                if not city_code:
                    print(f"[警告] 猎聘不支持 '{params.city}' 城市筛选，将搜索全国范围")
            
            # 添加实习筛选 (jobKind=2 表示实习)
            if city_code:
                city_param = f"&dq={city_code}"
            else:
                city_param = ""
            
            url = f"{self.base_url}/zhaopin/?key={quote(params.position)}{city_param}&jobKind=2&currentPage={params.page - 1}"
            
            print(f"正在访问: {url}")
            self.driver.get(url)
            self._random_delay(1.5, 2.5)
            self._scroll_page()
            
            selectors = [".job-list-item", "[class*='job-list-item']", "[class*='job-card']"]
            
            job_cards = []
            for selector in selectors:
                try:
                    WebDriverWait(self.driver, 4).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        print(f"使用选择器 '{selector}' 找到 {len(job_cards)} 个实习卡片")
                        break
                except TimeoutException:
                    continue
            
            if not job_cards:
                print("猎聘(实习): 页面加载超时或无搜索结果")
                return interns
            
            for card in job_cards[:params.page_size]:
                try:
                    intern_data = self._parse_intern_card(card)
                    if intern_data:
                        interns.append(intern_data)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"猎聘(实习)爬取错误: {e}")
        finally:
            self._close_driver()
        
        return interns
    
    def _parse_intern_card(self, card) -> Optional[InternInfo]:
        """解析实习卡片"""
        title = ""
        salary = ""
        company = ""
        city = ""
        education = ""
        job_url = ""
        
        # 职位名称
        for selector in [".job-title-box .ellipsis-1", ".job-title", "h3"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_get_text(elem)
                if text and len(text) > 2 and "在线" not in text:
                    title = text
                    break
            except:
                continue
        
        # 薪资
        for selector in [".job-salary", "[class*='salary']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                text = elem.get_attribute("textContent")
                if text:
                    text = text.strip()
                if text and ("元" in text or "K" in text or "k" in text):
                    salary = text
                    break
            except:
                continue
        
        # 公司名称
        for selector in [".company-name a", ".company-name"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                company = self._safe_get_text(elem)
                if company:
                    break
            except:
                continue
        
        # 城市
        for selector in [".job-dq-box .ellipsis-1", ".job-dq"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                city = self._safe_get_text(elem)
                if city:
                    break
            except:
                continue
        
        # 职位链接
        for selector in ["a[href*='/job/']"]:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                href = self._safe_get_attribute(elem, "href")
                if href and "liepin" in href:
                    job_url = href
                    break
            except:
                continue
        
        if title and company:
            return InternInfo(
                title=title,
                company=company,
                salary=salary,
                city=city,
                education=education,
                job_url=job_url,
                source=self.get_source_name(),
            )
        
        return None


class InternCrawlerManager:
    """实习爬虫管理器"""
    
    def __init__(self, sources: List[str] = None, headless: bool = True, show_progress: bool = True):
        self.headless = headless
        self.show_progress = show_progress
        self.crawler_classes = {
            "shixiseng": ShixisengCrawler,
            "ciwei": CiweiCrawler,
            "boss_intern": BossInternCrawler,
            "liepin_intern": LiepinInternCrawler,
        }
        
        if sources is None:
            sources = ["shixiseng", "liepin_intern"]  # 默认使用实习僧和猎聘
        
        self.sources = [s.lower() for s in sources if s.lower() in self.crawler_classes]
        self._lock = threading.Lock()
    
    def _crawl_single_source(self, source: str, params: InternSearchParams) -> tuple:
        """爬取单个数据源"""
        crawler_class = self.crawler_classes[source]
        crawler = crawler_class(headless=self.headless)
        
        print(f"\n[线程] 正在从 {crawler.get_source_name()} 获取数据...")
        try:
            interns = crawler.search(params)
            print(f"[线程] {crawler.get_source_name()} 获取完成，共 {len(interns)} 个实习")
            return (crawler.get_source_name(), interns)
        except Exception as e:
            print(f"[线程] {crawler.get_source_name()} 爬取失败: {e}")
            return (crawler.get_source_name(), [])
    
    def search(self, params: InternSearchParams) -> Dict[str, Any]:
        """搜索实习"""
        all_interns = []
        source_stats = {}
        seen_urls = set()
        
        print(f"\n启动多线程爬取，共 {len(self.sources)} 个数据源...")
        
        with ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            future_to_source = {
                executor.submit(self._crawl_single_source, source, params): source
                for source in self.sources
            }
            
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    source_name, interns = future.result()
                    
                    unique_interns = []
                    with self._lock:
                        for intern in interns:
                            intern_key = intern.job_url if intern.job_url else f"{intern.title}_{intern.company}"
                            if intern_key and intern_key not in seen_urls:
                                seen_urls.add(intern_key)
                                unique_interns.append(intern)
                        
                        all_interns.extend(unique_interns)
                    
                    source_stats[source_name] = len(unique_interns)
                    
                except Exception as e:
                    print(f"获取 {source} 结果时出错: {e}")
                    source_stats[source] = 0
        
        print(f"\n所有数据源爬取完成！")
        
        result = {
            "success": True,
            "message": "搜索完成",
            "params": {
                "position": params.position,
                "city": params.city or "不限",
                "education": params.education or "不限",
                "duration": params.duration or "不限",
                "days_per_week": params.days_per_week or "不限",
                "page": params.page,
                "page_size": params.page_size,
            },
            "statistics": {
                "total": len(all_interns),
                "by_source": source_stats,
            },
            "interns": [asdict(intern) for intern in all_interns],
        }
        
        return result


def search_interns_selenium(
    position: str,
    city: str = "",
    education: str = "",
    duration: str = "",
    days_per_week: str = "",
    page: int = 1,
    page_size: int = 20,
    sources: List[str] = None,
    headless: bool = True,
    save_to_file: bool = False,
    output_file: str = "interns_result.json",
    show_progress: bool = True,
) -> Dict[str, Any]:
    """
    使用Selenium搜索实习的便捷函数
    
    Args:
        position: 岗位名称（必填）
        city: 意向城市
        education: 学历要求
        duration: 实习时长
        days_per_week: 每周天数
        page: 页码
        page_size: 每页数量
        sources: 数据源列表，可选: shixiseng, ciwei, boss_intern, liepin_intern
        headless: 是否使用无头模式
        save_to_file: 是否保存到文件
        output_file: 输出文件路径
        show_progress: 是否显示进度信息
        
    Returns:
        包含搜索结果的字典
    """
    params = InternSearchParams(
        position=position,
        city=city,
        education=education,
        duration=duration,
        days_per_week=days_per_week,
        page=page,
        page_size=page_size,
    )
    
    if sources is None:
        sources = ["shixiseng", "liepin_intern"]
    
    manager = InternCrawlerManager(
        sources=sources,
        headless=headless,
        show_progress=show_progress,
    )
    
    result = manager.search(params)
    
    # 根据城市过滤结果
    if city and result.get("interns"):
        filtered = filter_interns_by_city(result["interns"], city)
        filtered_count = len(result["interns"]) - len(filtered)
        result["interns"] = filtered
        result["statistics"]["total"] = len(filtered)
        result["statistics"]["filtered_count"] = filtered_count
    
    if save_to_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_file}")
    
    return result


def filter_interns_by_city(interns: List[dict], city: str, min_results: int = 0) -> List[dict]:
    """根据城市过滤实习列表
    
    Args:
        interns: 实习列表
        city: 目标城市
        min_results: 最小结果数（0表示严格过滤，只返回匹配的城市）
    
    Returns:
        过滤后的实习列表
    """
    if not city:
        return interns
    
    matched = []
    unmatched = []
    city_lower = city.lower().strip()
    
    for intern in interns:
        intern_city = intern.get("city", "").lower().strip()
        
        # 空城市的保留（可能是数据缺失）
        if not intern_city:
            unmatched.append(intern)
            continue
        
        # 标准化城市名称（处理"北京-海淀区"这样的格式）
        intern_city_normalized = intern_city.replace("-", "·").replace(" ", "·")
        intern_main_city = intern_city_normalized.split("·")[0] if "·" in intern_city_normalized else intern_city_normalized
        
        # 匹配逻辑
        if (city_lower in intern_city_normalized or 
            city_lower in intern_main_city or 
            intern_main_city in city_lower):
            matched.append(intern)
        else:
            unmatched.append(intern)
    
    # 如果没有匹配结果且设置了最小结果数，则从不匹配的结果中补充
    if len(matched) < min_results and unmatched:
        need_count = min_results - len(matched)
        matched.extend(unmatched[:need_count])
    
    return matched


if __name__ == "__main__":
    # 测试代码
    result = search_interns_selenium(
        position="Python实习",
        city="北京",
        sources=["shixiseng", "liepin_intern"],
        headless=True,
    )
    
    print(f"\n共找到 {result['statistics']['total']} 个实习")
    for source, count in result['statistics']['by_source'].items():
        print(f"  - {source}: {count} 个")
    
    for intern in result['interns'][:5]:
        print(f"\n{intern['title']} - {intern['company']}")
        print(f"  薪资: {intern['salary']}, 城市: {intern['city']}")
