"""
招聘网站爬虫程序
支持: Boss直聘、猎聘、智联招聘、前程无忧
"""

import requests
import json
import time
import random
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from urllib.parse import quote, urlencode
import hashlib


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
    experience: str  # 经验要求
    education: str  # 学历要求
    company_type: str = ""  # 公司类型
    company_size: str = ""  # 公司规模
    skills: List[str] = None  # 技能要求
    benefits: List[str] = None  # 福利待遇
    job_url: str = ""  # 职位链接
    source: str = ""  # 来源网站
    publish_time: str = ""  # 发布时间
    
    def __post_init__(self):
        if self.skills is None:
            self.skills = []
        if self.benefits is None:
            self.benefits = []


class BaseJobCrawler(ABC):
    """爬虫基类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        self.session.headers.update(self.headers)
    
    @abstractmethod
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        """搜索职位"""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """获取来源名称"""
        pass
    
    def _random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """随机延迟，避免被封"""
        time.sleep(random.uniform(min_sec, max_sec))


class BossZhipinCrawler(BaseJobCrawler):
    """Boss直聘爬虫"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.zhipin.com"
        self.api_url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
        
        # Boss直聘城市代码映射
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
            "长沙": "101250100",
            "郑州": "101180100",
            "东莞": "101281600",
            "青岛": "101120200",
            "合肥": "101220100",
            "厦门": "101230200",
            "大连": "101070200",
        }
        
        # 经验映射
        self.exp_codes = {
            "不限": "0",
            "应届生": "108",
            "1年以内": "101",
            "1-3年": "102",
            "3-5年": "103",
            "5-10年": "104",
            "10年以上": "105",
        }
        
        # 学历映射
        self.edu_codes = {
            "不限": "0",
            "初中及以下": "209",
            "中专/中技": "208",
            "高中": "206",
            "大专": "202",
            "本科": "203",
            "硕士": "204",
            "博士": "205",
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
    
    def _get_exp_code(self, exp: str) -> str:
        if not exp:
            return "0"
        for key, code in self.exp_codes.items():
            if key in exp or exp in key:
                return code
        return "0"
    
    def _get_edu_code(self, edu: str) -> str:
        if not edu:
            return "0"
        for key, code in self.edu_codes.items():
            if key in edu or edu in key:
                return code
        return "0"
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        jobs = []
        try:
            city_code = self._get_city_code(params.city)
            exp_code = self._get_exp_code(params.experience)
            edu_code = self._get_edu_code(params.education)
            
            query_params = {
                "scene": "1",
                "query": params.position,
                "city": city_code,
                "experience": exp_code,
                "degree": edu_code,
                "stage": "",
                "position": "",
                "jobType": "",
                "salary": "",
                "multiBusinessDistrict": "",
                "multiSubway": "",
                "page": params.page,
                "pageSize": params.page_size,
            }
            
            self.session.headers.update({
                "Referer": f"https://www.zhipin.com/web/geek/job?query={quote(params.position)}&city={city_code}",
                "Host": "www.zhipin.com",
            })
            
            response = self.session.get(self.api_url, params=query_params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0 and data.get("zpData", {}).get("jobList"):
                    for item in data["zpData"]["jobList"]:
                        job = JobInfo(
                            title=item.get("jobName", ""),
                            company=item.get("brandName", ""),
                            salary=item.get("salaryDesc", ""),
                            city=item.get("cityName", ""),
                            experience=item.get("jobExperience", ""),
                            education=item.get("jobDegree", ""),
                            company_type=item.get("brandIndustry", ""),
                            company_size=item.get("brandScaleName", ""),
                            skills=item.get("skills", []),
                            benefits=item.get("welfareList", []),
                            job_url=f"https://www.zhipin.com/job_detail/{item.get('encryptJobId', '')}.html",
                            source=self.get_source_name(),
                            publish_time=item.get("lastModifyTime", ""),
                        )
                        jobs.append(job)
        except Exception as e:
            print(f"Boss直聘爬取错误: {e}")
        
        return jobs


class LiepinCrawler(BaseJobCrawler):
    """猎聘爬虫"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.liepin.com"
        self.api_url = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"
        
        # 猎聘城市代码
        self.city_codes = {
            "全国": "",
            "北京": "010",
            "上海": "020",
            "广州": "050020",
            "深圳": "050090",
            "杭州": "070020",
            "成都": "280020",
            "南京": "060020",
            "武汉": "170020",
            "西安": "270020",
            "苏州": "060080",
            "天津": "030",
            "重庆": "040",
        }
        
        # 经验映射
        self.exp_codes = {
            "不限": "",
            "1年以内": "0$1",
            "1-3年": "1$3",
            "3-5年": "3$5",
            "5-10年": "5$10",
            "10年以上": "10$99",
        }
        
        # 学历映射
        self.edu_codes = {
            "不限": "",
            "大专": "030",
            "本科": "040",
            "硕士": "050",
            "博士": "060",
        }
    
    def get_source_name(self) -> str:
        return "猎聘"
    
    def _get_city_code(self, city: str) -> str:
        if not city:
            return ""
        for key, code in self.city_codes.items():
            if key in city or city in key:
                return code
        return ""
    
    def _get_exp_code(self, exp: str) -> str:
        if not exp:
            return ""
        for key, code in self.exp_codes.items():
            if key in exp or exp in key:
                return code
        return ""
    
    def _get_edu_code(self, edu: str) -> str:
        if not edu:
            return ""
        for key, code in self.edu_codes.items():
            if key in edu or edu in key:
                return code
        return ""
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        jobs = []
        try:
            city_code = self._get_city_code(params.city)
            exp_code = self._get_exp_code(params.experience)
            edu_code = self._get_edu_code(params.education)
            
            payload = {
                "data": {
                    "mainSearchPcConditionForm": {
                        "city": city_code,
                        "dq": city_code,
                        "pubTime": "",
                        "currentPage": params.page - 1,
                        "pageSize": params.page_size,
                        "key": params.position,
                        "suggestTag": "",
                        "workYearCode": exp_code,
                        "eduLevel": edu_code,
                        "salary": "",
                        "industryType": "",
                        "compId": "",
                        "compName": "",
                        "compTag": "",
                        "compScale": "",
                        "jobKind": "",
                        "sortFlag": "0",
                    },
                    "passThroughForm": {
                        "scene": "conditionSearch",
                        "skId": "",
                        "fkId": "",
                        "ckId": "",
                    }
                }
            }
            
            self.session.headers.update({
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": "https://www.liepin.com",
                "Referer": f"https://www.liepin.com/zhaopin/?key={quote(params.position)}",
                "X-Requested-With": "XMLHttpRequest",
            })
            
            response = self.session.post(self.api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("flag") == 1 and data.get("data", {}).get("data", {}).get("jobCardList"):
                    for item in data["data"]["data"]["jobCardList"]:
                        job_data = item.get("job", {})
                        comp_data = item.get("comp", {})
                        job = JobInfo(
                            title=job_data.get("title", ""),
                            company=comp_data.get("compName", ""),
                            salary=job_data.get("salary", ""),
                            city=job_data.get("dq", ""),
                            experience=job_data.get("requireWorkYears", ""),
                            education=job_data.get("requireEduLevel", ""),
                            company_type=comp_data.get("compIndustry", ""),
                            company_size=comp_data.get("compScale", ""),
                            skills=job_data.get("labels", {}).get("skillLabels", []) if isinstance(job_data.get("labels"), dict) else [],
                            benefits=job_data.get("labels", {}).get("compLabels", []) if isinstance(job_data.get("labels"), dict) else [],
                            job_url=f"https://www.liepin.com/job/{job_data.get('jobId', '')}.shtml",
                            source=self.get_source_name(),
                            publish_time=job_data.get("refreshTime", ""),
                        )
                        jobs.append(job)
        except Exception as e:
            print(f"猎聘爬取错误: {e}")
        
        return jobs


class ZhilianCrawler(BaseJobCrawler):
    """智联招聘爬虫"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.zhaopin.com"
        self.api_url = "https://fe-api.zhaopin.com/c/i/sou"
        
        # 智联城市代码
        self.city_codes = {
            "全国": "",
            "北京": "530",
            "上海": "538",
            "广州": "763",
            "深圳": "765",
            "杭州": "653",
            "成都": "801",
            "南京": "635",
            "武汉": "736",
            "西安": "854",
            "苏州": "639",
            "天津": "531",
            "重庆": "551",
        }
        
        # 经验映射
        self.exp_codes = {
            "不限": "-1",
            "不限经验": "-1",
            "1年以下": "1",
            "1-3年": "2",
            "3-5年": "3",
            "5-10年": "4",
            "10年以上": "5",
        }
        
        # 学历映射
        self.edu_codes = {
            "不限": "-1",
            "大专": "5",
            "本科": "6",
            "硕士": "7",
            "博士": "8",
        }
    
    def get_source_name(self) -> str:
        return "智联招聘"
    
    def _get_city_code(self, city: str) -> str:
        if not city:
            return ""
        for key, code in self.city_codes.items():
            if key in city or city in key:
                return code
        return ""
    
    def _get_exp_code(self, exp: str) -> str:
        if not exp:
            return "-1"
        for key, code in self.exp_codes.items():
            if key in exp or exp in key:
                return code
        return "-1"
    
    def _get_edu_code(self, edu: str) -> str:
        if not edu:
            return "-1"
        for key, code in self.edu_codes.items():
            if key in edu or edu in key:
                return code
        return "-1"
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        jobs = []
        try:
            city_code = self._get_city_code(params.city)
            exp_code = self._get_exp_code(params.experience)
            edu_code = self._get_edu_code(params.education)
            
            query_params = {
                "pageSize": params.page_size,
                "cityId": city_code,
                "workExperience": exp_code,
                "education": edu_code,
                "companyType": "-1",
                "employmentType": "-1",
                "jobWelfareTag": "-1",
                "kw": params.position,
                "kt": "3",
                "lastUrlQuery": json.dumps({"p": params.page}),
                "at": str(int(time.time() * 1000)),
                "rt": str(random.randint(100000000, 999999999)),
            }
            
            self.session.headers.update({
                "Referer": f"https://sou.zhaopin.com/?jl={city_code}&kw={quote(params.position)}",
                "Origin": "https://sou.zhaopin.com",
            })
            
            response = self.session.get(self.api_url, params=query_params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200 and data.get("data", {}).get("list"):
                    for item in data["data"]["list"]:
                        job = JobInfo(
                            title=item.get("name", ""),
                            company=item.get("company", {}).get("name", ""),
                            salary=item.get("salary", ""),
                            city=item.get("city", {}).get("display", ""),
                            experience=item.get("workingExp", {}).get("name", ""),
                            education=item.get("eduLevel", {}).get("name", ""),
                            company_type=item.get("company", {}).get("type", {}).get("name", ""),
                            company_size=item.get("company", {}).get("size", {}).get("name", ""),
                            skills=item.get("skillLabel", []) if item.get("skillLabel") else [],
                            benefits=item.get("welfare", []) if item.get("welfare") else [],
                            job_url=item.get("positionURL", ""),
                            source=self.get_source_name(),
                            publish_time=item.get("updateDate", ""),
                        )
                        jobs.append(job)
        except Exception as e:
            print(f"智联招聘爬取错误: {e}")
        
        return jobs


class Job51Crawler(BaseJobCrawler):
    """前程无忧爬虫"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.51job.com"
        self.api_url = "https://we.51job.com/api/job/search-pc"
        
        # 前程无忧城市代码
        self.city_codes = {
            "全国": "",
            "北京": "010000",
            "上海": "020000",
            "广州": "030200",
            "深圳": "040000",
            "杭州": "080200",
            "成都": "090200",
            "南京": "070200",
            "武汉": "180200",
            "西安": "200200",
            "苏州": "070300",
            "天津": "050000",
            "重庆": "060000",
        }
        
        # 经验映射
        self.exp_codes = {
            "不限": "",
            "在校生/应届生": "01",
            "1年以下": "02",
            "1-3年": "03",
            "3-5年": "04",
            "5-10年": "05",
            "10年以上": "06",
        }
        
        # 学历映射
        self.edu_codes = {
            "不限": "",
            "初中及以下": "01",
            "高中/中专/中技": "02",
            "大专": "03",
            "本科": "04",
            "硕士": "05",
            "博士": "06",
        }
    
    def get_source_name(self) -> str:
        return "前程无忧"
    
    def _get_city_code(self, city: str) -> str:
        if not city:
            return ""
        for key, code in self.city_codes.items():
            if key in city or city in key:
                return code
        return ""
    
    def _get_exp_code(self, exp: str) -> str:
        if not exp:
            return ""
        for key, code in self.exp_codes.items():
            if key in exp or exp in key:
                return code
        return ""
    
    def _get_edu_code(self, edu: str) -> str:
        if not edu:
            return ""
        for key, code in self.edu_codes.items():
            if key in edu or edu in key:
                return code
        return ""
    
    def search(self, params: JobSearchParams) -> List[JobInfo]:
        jobs = []
        try:
            city_code = self._get_city_code(params.city)
            exp_code = self._get_exp_code(params.experience)
            edu_code = self._get_edu_code(params.education)
            
            payload = {
                "api_key": "51job",
                "timestamp": str(int(time.time())),
                "keyword": params.position,
                "searchType": "2",
                "function": "",
                "industry": "",
                "jobArea": city_code,
                "jobArea2": "",
                "landmark": "",
                "metro": "",
                "salary": "",
                "workYear": exp_code,
                "degree": edu_code,
                "companyType": "",
                "companySize": "",
                "issueDate": "",
                "sortType": "0",
                "pageNum": str(params.page),
                "pageSize": str(params.page_size),
                "source": "1",
                "accountId": "",
                "pageCode": "sou|sou|sou",
            }
            
            self.session.headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://we.51job.com",
                "Referer": f"https://we.51job.com/pc/search?keyword={quote(params.position)}&searchType=2&sortType=0",
                "Host": "we.51job.com",
            })
            
            response = self.session.post(self.api_url, data=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "1" and data.get("resultbody", {}).get("job", {}).get("items"):
                    for item in data["resultbody"]["job"]["items"]:
                        job = JobInfo(
                            title=item.get("jobName", ""),
                            company=item.get("companyName", ""),
                            salary=item.get("provideSalaryString", ""),
                            city=item.get("jobAreaString", ""),
                            experience=item.get("workYearString", ""),
                            education=item.get("degreeString", ""),
                            company_type=item.get("companyTypeString", ""),
                            company_size=item.get("companySizeString", ""),
                            skills=item.get("jobTags", []) if item.get("jobTags") else [],
                            benefits=item.get("companyTags", []) if item.get("companyTags") else [],
                            job_url=item.get("jobHref", ""),
                            source=self.get_source_name(),
                            publish_time=item.get("issueDateString", ""),
                        )
                        jobs.append(job)
        except Exception as e:
            print(f"前程无忧爬取错误: {e}")
        
        return jobs


class JobCrawlerManager:
    """爬虫管理器"""
    
    def __init__(self, sources: List[str] = None):
        """
        初始化爬虫管理器
        
        Args:
            sources: 要爬取的网站列表，可选值: boss, liepin, zhilian, job51
                    如果为None，则爬取所有网站
        """
        self.crawlers: Dict[str, BaseJobCrawler] = {}
        
        all_crawlers = {
            "boss": BossZhipinCrawler,
            "liepin": LiepinCrawler,
            "zhilian": ZhilianCrawler,
            "job51": Job51Crawler,
        }
        
        if sources is None:
            sources = list(all_crawlers.keys())
        
        for source in sources:
            source_lower = source.lower()
            if source_lower in all_crawlers:
                self.crawlers[source_lower] = all_crawlers[source_lower]()
    
    def search(self, params: JobSearchParams) -> Dict[str, Any]:
        """
        搜索职位
        
        Args:
            params: 搜索参数
            
        Returns:
            包含搜索结果的字典
        """
        all_jobs = []
        source_stats = {}
        
        for source, crawler in self.crawlers.items():
            print(f"正在从 {crawler.get_source_name()} 获取数据...")
            jobs = crawler.search(params)
            all_jobs.extend(jobs)
            source_stats[crawler.get_source_name()] = len(jobs)
            crawler._random_delay()
        
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
        """
        搜索职位并保存到文件
        
        Args:
            params: 搜索参数
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        result = self.search(params)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存到: {output_file}")
        print(f"共找到 {result['statistics']['total']} 个职位")
        for source, count in result['statistics']['by_source'].items():
            print(f"  - {source}: {count} 个")
        
        return output_file


def search_jobs(
    position: str,
    city: str = "",
    experience: str = "",
    education: str = "",
    salary: str = "",
    page: int = 1,
    page_size: int = 20,
    sources: List[str] = None,
    save_to_file: bool = False,
    output_file: str = "jobs_result.json"
) -> Dict[str, Any]:
    """
    搜索职位的便捷函数
    
    Args:
        position: 岗位名称（必填）
        city: 意向城市
        experience: 工作经验，如 "1-3年", "3-5年", "5-10年"
        education: 学历要求，如 "大专", "本科", "硕士"
        salary: 期望薪资
        page: 页码
        page_size: 每页数量
        sources: 要爬取的网站列表，可选: boss, liepin, zhilian, job51
        save_to_file: 是否保存到文件
        output_file: 输出文件路径
        
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
    
    manager = JobCrawlerManager(sources=sources)
    
    if save_to_file:
        manager.search_and_save(params, output_file)
        with open(output_file, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return manager.search(params)


# 示例用法
if __name__ == "__main__":
    # 示例：搜索Python开发工程师职位
    result = search_jobs(
        position="Python开发",  # 岗位名称（必填）
        city="北京",           # 意向城市
        experience="3-5年",    # 工作经验
        education="本科",      # 学历要求
        salary="",             # 期望薪资
        page=1,                # 页码
        page_size=10,          # 每页数量
        sources=["boss", "liepin", "zhilian", "job51"],  # 数据来源
        save_to_file=True,     # 是否保存到文件
        output_file="jobs_result.json"  # 输出文件
    )
    
    # 打印结果预览
    print("\n" + "="*50)
    print("搜索结果预览:")
    print("="*50)
    
    for i, job in enumerate(result.get("jobs", [])[:5], 1):
        print(f"\n{i}. {job['title']}")
        print(f"   公司: {job['company']}")
        print(f"   薪资: {job['salary']}")
        print(f"   城市: {job['city']}")
        print(f"   经验: {job['experience']} | 学历: {job['education']}")
        print(f"   来源: {job['source']}")
