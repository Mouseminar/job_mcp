"""
招聘网站爬虫 - 命令行交互工具
使用 Selenium 实现真实浏览器访问
"""

import json
import argparse
import time
import os
from job_crawler_selenium import search_jobs_selenium as search_jobs, load_config, RICH_AVAILABLE

if RICH_AVAILABLE:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TaskProgressColumn
    from rich import print as rprint
    console = Console()
else:
    console = None
    rprint = print


def format_salary(salary: str) -> str:
    """格式化薪资显示，处理反爬导致的不完整薪资"""
    if not salary or salary == '-':
        return '面议'
    
    import re
    # 去除首尾空白
    salary = salary.strip()
    
    # 检查是否是不完整的薪资格式
    # 1. 以 "-" 开头后面跟着 K/k/万/元 等单位（如 "-K", "-万", "-元/天"）
    # 2. 只有单位没有数字
    if re.match(r'^-\s*[Kk万元]', salary) or re.match(r'^[Kk万元]', salary):
        # 薪资数字被反爬隐藏
        return '面议*'
    
    # 检查是否包含有效的薪资数字
    # 正常薪资应该有数字，如 "15-25K", "10000-20000元", "1.5-2万"
    if not re.search(r'\d', salary):
        return '面议*'
    
    return salary


def print_results_rich(result: dict, elapsed_time: float, max_display: int = 10):
    """使用 rich 库美化输出结果"""
    stats = result.get("statistics", {})
    jobs = result.get("jobs", [])
    
    # 打印统计面板
    stats_text = f"[bold green]总计: {stats.get('total', 0)} 个职位[/bold green]\n"
    stats_text += f"[dim]耗时: {elapsed_time:.2f} 秒[/dim]\n\n"
    for source, count in stats.get("by_source", {}).items():
        color = {"Boss直聘": "cyan", "猎聘": "yellow", "智联招聘": "blue", "前程无忧": "magenta"}.get(source, "white")
        stats_text += f"  [{color}]● {source}: {count} 个[/{color}]\n"
    
    console.print(Panel(stats_text, title="[bold]搜索完成[/bold]", border_style="green"))
    
    if not jobs:
        console.print("[yellow]未找到符合条件的职位[/yellow]")
        return
    
    # 创建职位表格
    table = Table(title="职位列表", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("职位", style="bold", max_width=28)
    table.add_column("公司", max_width=18)
    table.add_column("薪资", style="green", max_width=20)
    table.add_column("城市", max_width=12)
    table.add_column("经验/学历", max_width=14)
    table.add_column("来源", max_width=10)
    
    for i, job in enumerate(jobs[:max_display], 1):
        exp_edu = f"{job.get('experience', '-')}/{job.get('education', '-')}"
        source = job.get('source', '')
        source_color = {"Boss直聘": "cyan", "猎聘": "yellow", "智联招聘": "blue", "前程无忧": "magenta"}.get(source, "white")
        salary_display = format_salary(job.get('salary', '-'))
        
        table.add_row(
            str(i),
            job.get('title', '-')[:28],
            job.get('company', '-')[:18],
            salary_display[:20],
            job.get('city', '-')[:12],
            exp_edu[:14],
            f"[{source_color}]{source}[/{source_color}]"
        )
    
    console.print(table)
    
    if len(jobs) > max_display:
        console.print(f"\n[dim]... 还有 {len(jobs) - max_display} 个职位未显示[/dim]")


def print_results_plain(result: dict, elapsed_time: float, max_display: int = 10):
    """普通文本输出结果"""
    stats = result.get("statistics", {})
    jobs = result.get("jobs", [])
    
    print(f"\n搜索完成！共找到 {stats.get('total', 0)} 个职位")
    print(f"总耗时: {elapsed_time:.2f} 秒")
    for source, count in stats.get("by_source", {}).items():
        print(f"  - {source}: {count} 个")
    
    if jobs:
        print(f"\n{'='*60}")
        print("职位列表:")
        print("="*60)
        
        for i, job in enumerate(jobs[:max_display], 1):
            print(f"\n{i}. {job['title']}")
            print(f"   公司: {job['company']}")
            print(f"   薪资: {format_salary(job.get('salary', '-'))}")
            print(f"   城市: {job['city']}")
            print(f"   经验: {job['experience']} | 学历: {job['education']}")
            print(f"   来源: {job['source']}")
            if job.get('job_url'):
                print(f"   链接: {job['job_url']}")
        
        if len(jobs) > max_display:
            print(f"\n... 还有 {len(jobs) - max_display} 个职位未显示")
    else:
        print("\n未找到符合条件的职位，可能是反爬机制限制，请稍后再试")


def main():
    # 加载配置
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description="招聘网站职位搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python search_job.py -p "Python开发" -c "北京"
  python search_job.py -p "前端工程师" -c "上海" -e "3-5年" -d "本科"
  python search_job.py -p "Java开发" --sources boss liepin
  python search_job.py -p "数据分析" -o result.json --save
  python search_job.py -p "golang" --mode shared --no-progress
        """
    )
    
    parser.add_argument(
        "-p", "--position",
        type=str,
        required=True,
        help="岗位名称（必填）"
    )
    
    parser.add_argument(
        "-c", "--city",
        type=str,
        default="",
        help="意向城市，如：北京、上海、深圳"
    )
    
    parser.add_argument(
        "-e", "--experience",
        type=str,
        default="",
        help="工作经验，如：1-3年、3-5年、5-10年"
    )
    
    parser.add_argument(
        "-d", "--education",
        type=str,
        default="",
        help="学历要求，如：大专、本科、硕士"
    )
    
    parser.add_argument(
        "-s", "--salary",
        type=str,
        default="",
        help="期望薪资"
    )
    
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="页码，默认1"
    )
    
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="每页数量，默认20"
    )
    
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["boss", "liepin", "zhilian", "job51"],
        default=["liepin", "zhilian"],  # 默认不使用 job51（不稳定）
        help="数据来源，可选：boss, liepin, zhilian, job51"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="使用无头浏览器模式（默认启用）"
    )
    
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="禁用无头浏览器模式，显示浏览器窗口"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="jobs_result.json",
        help="输出文件路径"
    )
    
    parser.add_argument(
        "--save",
        action="store_true",
        help="是否保存到文件"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="以JSON格式输出结果"
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["parallel", "shared"],
        default=config.get("crawl", {}).get("mode", "parallel"),
        help="爬取模式: parallel=多线程并行(快), shared=单浏览器串行(省资源)"
    )
    
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="禁用进度条显示"
    )
    
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用彩色输出"
    )
    
    args = parser.parse_args()
    
    # 是否使用彩色输出
    use_color = RICH_AVAILABLE and not args.no_color and config.get("display", {}).get("color_output", True)
    show_progress = not args.no_progress and config.get("display", {}).get("show_progress", True)
    max_display = config.get("display", {}).get("max_display_jobs", 10)
    
    # 打印搜索信息
    if use_color:
        console.print(Panel(
            f"[bold cyan]职位:[/bold cyan] {args.position}\n" +
            (f"[bold cyan]城市:[/bold cyan] {args.city}\n" if args.city else "") +
            (f"[bold cyan]经验:[/bold cyan] {args.experience}\n" if args.experience else "") +
            (f"[bold cyan]学历:[/bold cyan] {args.education}" if args.education else ""),
            title="[bold]搜索条件[/bold]",
            border_style="cyan"
        ))
    else:
        print(f"\n正在搜索职位: {args.position}")
        if args.city:
            print(f"城市: {args.city}")
        if args.experience:
            print(f"经验: {args.experience}")
        if args.education:
            print(f"学历: {args.education}")
        print("-" * 50)
    
    # 确定是否使用 headless 模式
    headless = not args.no_headless
    
    # 记录开始时间
    start_time = time.time()
    
    # 使用进度条
    if use_color and show_progress:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,  # 完成后清除进度条
        ) as progress:
            task = progress.add_task(f"[cyan]正在爬取 {len(args.sources)} 个数据源...", total=None)
            
            result = search_jobs(
                position=args.position,
                city=args.city,
                experience=args.experience,
                education=args.education,
                salary=args.salary,
                page=args.page,
                page_size=args.page_size,
                sources=args.sources,
                headless=headless,
                save_to_file=args.save,
                output_file=args.output,
                mode=args.mode,
                show_progress=False  # 内部不显示进度
            )
    else:
        result = search_jobs(
            position=args.position,
            city=args.city,
            experience=args.experience,
            education=args.education,
            salary=args.salary,
            page=args.page,
            page_size=args.page_size,
            sources=args.sources,
            headless=headless,
            save_to_file=args.save,
            output_file=args.output,
            mode=args.mode,
            show_progress=not show_progress
        )
    
    # 计算耗时
    elapsed_time = time.time() - start_time
    
    if args.json:
        result['elapsed_time'] = f"{elapsed_time:.2f}秒"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif use_color:
        print_results_rich(result, elapsed_time, max_display)
    else:
        print_results_plain(result, elapsed_time, max_display)
    
    # 保存提示
    if args.save and use_color:
        console.print(f"\n[green]✓ 结果已保存到: {args.output}[/green]")


if __name__ == "__main__":
    main()
