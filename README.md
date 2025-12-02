# 招聘网站爬虫程序

这是一个Python编写的招聘网站职位爬虫程序，支持多个主流招聘平台的职位搜索。

## 支持的招聘网站

- **Boss直聘** (zhipin.com)
- **猎聘** (liepin.com)
- **智联招聘** (zhaopin.com)
- **前程无忧** (51job.com)

## 两个版本

本项目提供两个版本的爬虫：

1. **API版本** (`job_crawler.py`) - 直接调用网站API，速度快但可能被反爬机制限制
2. **Selenium版本** (`job_crawler_selenium.py`) - 使用浏览器模拟访问，更稳定但需要安装Chrome

## 安装依赖

```bash
pip install -r requirements.txt
```

### Selenium版本额外要求

如果使用Selenium版本，还需要：
1. 安装Chrome浏览器
2. 下载对应版本的[ChromeDriver](https://chromedriver.chromium.org/downloads)并添加到系统PATH

## 使用方法

### 1. API版本 - 作为模块导入使用

```python
from job_crawler import search_jobs

# 搜索职位
result = search_jobs(
    position="Python开发",  # 岗位名称（必填）
    city="北京",           # 意向城市（可选）
    experience="3-5年",    # 工作经验（可选）
    education="本科",      # 学历要求（可选）
    salary="",             # 期望薪资（可选）
    page=1,                # 页码
    page_size=10,          # 每页数量
    sources=["boss", "liepin", "zhilian", "job51"],  # 数据来源
    save_to_file=True,     # 是否保存到文件
    output_file="jobs_result.json"  # 输出文件
)

# 打印结果
print(result)
```

### 2. Selenium版本 - 更稳定的浏览器模拟

```python
from job_crawler_selenium import search_jobs_selenium

# 搜索职位
result = search_jobs_selenium(
    position="Python开发",  # 岗位名称（必填）
    city="北京",           # 意向城市
    experience="3-5年",    # 工作经验
    education="本科",      # 学历要求
    page=1,                # 页码
    page_size=10,          # 每页数量
    sources=["boss", "liepin"],  # 数据来源
    headless=True,         # 无头模式（不显示浏览器）
    save_to_file=True,     # 保存到文件
    output_file="jobs_result.json"
)
```

### 3. 命令行工具

```bash
# 基本搜索
python search_job.py -p "Python开发" -c "北京"

# 完整参数
python search_job.py -p "前端工程师" -c "上海" -e "3-5年" -d "本科"

# 指定来源
python search_job.py -p "Java开发" --sources boss liepin

# 保存到文件
python search_job.py -p "数据分析" -o result.json --save

# 以JSON格式输出
python search_job.py -p "产品经理" --json
```

### 4. 直接运行脚本

```bash
# API版本
python job_crawler.py

# Selenium版本
python job_crawler_selenium.py
```

## 搜索参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position | str | ✅ | 岗位名称，如"Python开发"、"前端工程师" |
| city | str | ❌ | 意向城市，如"北京"、"上海"、"深圳" |
| experience | str | ❌ | 工作经验，如"1-3年"、"3-5年"、"5-10年" |
| education | str | ❌ | 学历要求，如"大专"、"本科"、"硕士" |
| salary | str | ❌ | 期望薪资 |
| page | int | ❌ | 页码，默认1 |
| page_size | int | ❌ | 每页数量，默认20 |
| sources | list | ❌ | 数据来源，可选: boss, liepin, zhilian, job51 |
| save_to_file | bool | ❌ | 是否保存到文件，默认False |
| output_file | str | ❌ | 输出文件路径，默认"jobs_result.json" |

## 支持的城市

- 北京、上海、广州、深圳
- 杭州、成都、南京、武汉
- 西安、苏州、天津、重庆
- 长沙、郑州、东莞、青岛
- 合肥、厦门、大连等

## 返回数据格式

```json
{
  "success": true,
  "message": "搜索完成",
  "params": {
    "position": "Python开发",
    "city": "北京",
    "experience": "3-5年",
    "education": "本科",
    "salary": "不限",
    "page": 1,
    "page_size": 10
  },
  "statistics": {
    "total": 40,
    "by_source": {
      "Boss直聘": 10,
      "猎聘": 10,
      "智联招聘": 10,
      "前程无忧": 10
    }
  },
  "jobs": [
    {
      "title": "Python开发工程师",
      "company": "某科技公司",
      "salary": "20-30K",
      "city": "北京",
      "experience": "3-5年",
      "education": "本科",
      "company_type": "互联网",
      "company_size": "100-499人",
      "skills": ["Python", "Django", "MySQL"],
      "benefits": ["五险一金", "年终奖"],
      "job_url": "https://...",
      "source": "Boss直聘",
      "publish_time": "2024-01-01"
    }
  ]
}
```

## 注意事项

1. **反爬虫机制**: 各招聘网站都有反爬虫机制，程序内置了随机延迟，但仍可能被限制访问。
2. **登录限制**: 部分网站可能需要登录才能获取完整数据。
3. **合法使用**: 请遵守各网站的使用条款，仅用于个人求职用途。
4. **API变化**: 招聘网站的API可能随时变化，如遇问题请更新代码。

## 扩展使用

### 只爬取特定网站

```python
# 只爬取Boss直聘和猎聘
result = search_jobs(
    position="前端工程师",
    city="上海",
    sources=["boss", "liepin"]
)
```

### 分页获取

```python
# 获取第2页数据
result = search_jobs(
    position="Java开发",
    page=2,
    page_size=20
)
```

## License

MIT License

## 在无外网/云服务器（如阿里云容器）上部署 Selenium 说明

如果运行环境无法访问外网，Selenium 的 SeleniumManager 会无法自动下载 ChromeDriver，从而报错 `Unable to obtain driver for chrome`。常见解决方案：

- **方法 A（推荐）**：在镜像/服务器上预安装 Chrome 或 Chromium，并把对应版本的 chromedriver 放到一个可访问路径，然后通过环境变量指定路径：
  - 将 Chrome 或 Chromium 可执行文件路径设置到 `CHROME_BINARY`（例如 `/usr/bin/chromium-browser`）。
  - 将 chromedriver 二进制路径设置到 `CHROMEDRIVER_PATH`（例如 `/opt/chromedriver`）。
  - 运行容器/进程时传入环境变量，例如（PowerShell）:

```powershell
$env:CHROME_BINARY = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:CHROMEDRIVER_PATH = 'C:\tools\chromedriver.exe'
python job_crawler_selenium.py
```

  在 Linux 容器中（Dockerfile 示例片段）:

```Dockerfile
RUN apt-get update && apt-get install -y wget unzip \
    chromium-browser
# 把预先下载好的 chromedriver 放到 /usr/local/bin
COPY chromedriver /usr/local/bin/chromedriver
ENV CHROME_BINARY=/usr/bin/chromium-browser \
    CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
```

- **方法 B**：在镜像构建阶段使用工具（如 `webdriver-manager` 或官方 chromedriver 二进制）下载好对应版本并放入镜像中，然后同样通过 `CHROMEDRIVER_PATH` 指定。

- **方法 C（不推荐在无网络时）**：依赖 SeleniumManager 自动下载，这需要容器能够访问 `https://googlechromelabs.github.io`，若环境被限制则会失败。

调试验证命令（在服务器上执行）：

```bash
# 检查 Chrome/Chromium
which chromium-browser || which google-chrome || echo "chrome not found"
# 检查 chromedriver
/usr/local/bin/chromedriver --version || chromedriver --version
```

如果遇到问题，可以把 Chromedriver 放进同一个目录并通过 `CHROMEDRIVER_PATH` 指定路径，或者把 Chrome 路径通过 `CHROME_BINARY` 指定。程序会优先使用这些环境变量来启动浏览器，从而避免 SeleniumManager 自动下载失败的情况。
