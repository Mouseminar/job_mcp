"""
实习信息搜索 - 命令行交互工具
使用 Selenium 实现真实浏览器访问
"""

import json
import argparse
import time
import os
from intern_crawler_selenium import search_interns_selenium, load_config, RICH_AVAILABLE

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
    """格式化薪资显示"""
    if not salary or salary == '-':
        return '面议'
    
    import re
    salary = salary.strip()
    
    if re.match(r'^-\s*[Kk万元]', salary) or re.match(r'^[Kk万元]', salary):
        return '面议*'
    
    if not re.search(r'\d', salary):
        return '面议*'
    
    return salary


def print_results_rich(result: dict, elapsed_time: float, max_display: int = 10):
    """使用 rich 库美化输出结果"""
    stats = result.get("statistics", {})
    interns = result.get("interns", [])
    filtered_count = stats.get("filtered_count", 0)
    
    # 打印统计面板
    stats_text = f"[bold green]总计: {stats.get('total', 0)} 个实习[/bold green]\n"
    stats_text += f"[dim]耗时: {elapsed_time:.2f} 秒[/dim]\n\n"
    for source, count in stats.get("by_source", {}).items():
        color = {
            "实习僧": "cyan", 
            "刺猬实习": "yellow", 
            "Boss直聘(实习)": "blue", 
            "猎聘(实习)": "magenta"
        }.get(source, "white")
        stats_text += f"  [{color}]● {source}: {count} 个[/{color}]\n"
    
    # 如果有城市过滤
    if filtered_count > 0:
        stats_text += f"\n[dim]（已过滤 {filtered_count} 个其他城市的结果）[/dim]"
    
    console.print(Panel(stats_text, title="[bold]搜索完成[/bold]", border_style="green"))
    
    if not interns:
        console.print("[yellow]⚠ 未找到符合条件的实习[/yellow]")
        if filtered_count > 0:
            console.print("[dim]提示: 该城市的实习岗位较少，您可以尝试:[/dim]")
            console.print("[dim]  1. 不指定城市搜索全国范围[/dim]")
            console.print("[dim]  2. 搜索临近城市的远程实习[/dim]")
            console.print("[dim]  3. 尝试更通用的关键词[/dim]")
        return
        return
    
    # 创建实习表格
    table = Table(title="实习列表", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("职位", style="bold", max_width=28)
    table.add_column("公司", max_width=18)
    table.add_column("薪资", style="green", max_width=14)
    table.add_column("城市", max_width=12)
    table.add_column("时长/天数", max_width=12)
    table.add_column("来源", max_width=12)
    
    for i, intern in enumerate(interns[:max_display], 1):
        duration_days = ""
        if intern.get('duration'):
            duration_days = intern.get('duration', '')
        if intern.get('days_per_week'):
            if duration_days:
                duration_days += "/" + intern.get('days_per_week', '')
            else:
                duration_days = intern.get('days_per_week', '')
        if not duration_days:
            duration_days = "-"
            
        source = intern.get('source', '')
        source_color = {
            "实习僧": "cyan", 
            "刺猬实习": "yellow", 
            "Boss直聘(实习)": "blue", 
            "猎聘(实习)": "magenta"
        }.get(source, "white")
        salary_display = format_salary(intern.get('salary', '-'))
        
        table.add_row(
            str(i),
            intern.get('title', '-')[:28],
            intern.get('company', '-')[:18],
            salary_display[:14],
            intern.get('city', '-')[:12],
            duration_days[:12],
            f"[{source_color}]{source}[/{source_color}]"
        )
    
    console.print(table)
    
    if len(interns) > max_display:
        console.print(f"\n[dim]... 还有 {len(interns) - max_display} 个实习未显示[/dim]")


def print_results_plain(result: dict, elapsed_time: float, max_display: int = 10):
    """普通文本输出结果"""
    stats = result.get("statistics", {})
    interns = result.get("interns", [])
    
    print(f"\n搜索完成！共找到 {stats.get('total', 0)} 个实习")
    print(f"总耗时: {elapsed_time:.2f} 秒")
    for source, count in stats.get("by_source", {}).items():
        print(f"  - {source}: {count} 个")
    
    if interns:
        print(f"\n{'='*60}")
        print("实习列表:")
        print("="*60)
        
        for i, intern in enumerate(interns[:max_display], 1):
            print(f"\n{i}. {intern['title']}")
            print(f"   公司: {intern['company']}")
            print(f"   薪资: {format_salary(intern.get('salary', '-'))}")
            print(f"   城市: {intern['city']}")
            if intern.get('duration'):
                print(f"   时长: {intern['duration']}")
            if intern.get('days_per_week'):
                print(f"   天数: {intern['days_per_week']}")
            print(f"   来源: {intern['source']}")
            if intern.get('job_url'):
                print(f"   链接: {intern['job_url']}")
        
        if len(interns) > max_display:
            print(f"\n... 还有 {len(interns) - max_display} 个实习未显示")
    else:
        print("\n未找到符合条件的实习，请稍后再试")


def main():
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description="实习信息搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python search_intern.py -p "Python实习" -c "北京"
  python search_intern.py -p "前端实习" -c "上海" --sources shixiseng liepin_intern
  python search_intern.py -p "数据分析实习" -o result.json --save
  python search_intern.py -p "Java实习" -c "杭州" --json
        """
    )
    
    parser.add_argument(
        "-p", "--position",
        type=str,
        required=True,
        help="实习岗位名称（必填）"
    )
    
    parser.add_argument(
        "-c", "--city",
        type=str,
        default="",
        help="意向城市，如：北京、上海、深圳"
    )
    
    parser.add_argument(
        "-d", "--education",
        type=str,
        default="",
        help="学历要求，如：本科在读、硕士在读"
    )
    
    parser.add_argument(
        "--duration",
        type=str,
        default="",
        help="实习时长，如：3个月以上"
    )
    
    parser.add_argument(
        "--days",
        type=str,
        default="",
        help="每周出勤天数，如：3天/周"
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
        choices=["shixiseng", "ciwei", "boss_intern", "liepin_intern"],
        default=["shixiseng", "liepin_intern"],
        help="数据来源，可选：shixiseng(实习僧), ciwei(刺猬), boss_intern(Boss直聘), liepin_intern(猎聘)"
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
        default="interns_result.json",
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
            f"[bold cyan]实习岗位:[/bold cyan] {args.position}\n" +
            (f"[bold cyan]城市:[/bold cyan] {args.city}\n" if args.city else "") +
            (f"[bold cyan]学历:[/bold cyan] {args.education}\n" if args.education else "") +
            (f"[bold cyan]时长:[/bold cyan] {args.duration}\n" if args.duration else "") +
            (f"[bold cyan]天数:[/bold cyan] {args.days}" if args.days else ""),
            title="[bold]搜索条件[/bold]",
            border_style="cyan"
        ))
    else:
        print(f"\n正在搜索实习: {args.position}")
        if args.city:
            print(f"城市: {args.city}")
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
            transient=True,
        ) as progress:
            task = progress.add_task(f"[cyan]正在爬取 {len(args.sources)} 个数据源...", total=None)
            
            result = search_interns_selenium(
                position=args.position,
                city=args.city,
                education=args.education,
                duration=args.duration,
                days_per_week=args.days,
                page=args.page,
                page_size=args.page_size,
                sources=args.sources,
                headless=headless,
                save_to_file=args.save,
                output_file=args.output,
                show_progress=False,
            )
    else:
        result = search_interns_selenium(
            position=args.position,
            city=args.city,
            education=args.education,
            duration=args.duration,
            days_per_week=args.days,
            page=args.page,
            page_size=args.page_size,
            sources=args.sources,
            headless=headless,
            save_to_file=args.save,
            output_file=args.output,
            show_progress=not show_progress,
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
