"""
把 scarcity_curve.py 里的 run_window 按月循环跑一遍, 覆盖 2024-08 (AEMO 报价数据缺失区间
结束) 之后所有可用月份, 每个月生成一个独立的 scarcity_curve_data_monthly_YYYYMM.csv。

目的: backtest_holdout.py 之前只能用 3 个人工挑选的 7 天窗口做留一法交叉验证, 独立折数
太少 (n=3), 结论的置信度很低。这个脚本把独立折数从 3 提到十几/二十几个真实月份, 让回测
不再依赖挑窗口的运气。backtest_holdout.py 会自动发现新生成的 scarcity_curve_data_*.csv,
不需要改回测脚本。

⚠️ 必须在有网络访问 nemweb.com.au 权限的机器上跑 (sandbox 里跑不了)。
⚠️ 单月 BIDPEROFFER_D 压缩后约 0.5-1.5GB, 全部 ~24 个月跑下来可能占用 10GB+ 磁盘、
   耗时几十分钟到几小时。脚本按月落盘、可断点续跑 (已存在的月份会跳过)。

用法:
    python fetch_monthly_bids.py                  # 默认 2024-08 ~ 上个月
    python fetch_monthly_bids.py 2024-08 2025-06   # 自定义范围 (含端点)
"""
import os
import sys
from datetime import date
from pathlib import Path

import scarcity_curve

# 用脚本自身所在目录算 nemosis_cache 的路径, 不依赖运行时的工作目录 (cwd) --
# scarcity_curve.py 里原本用的是相对路径 "./nemosis_cache", 谁调用就以谁的 cwd 为准,
# 从 IDE 的 Run 按钮启动时 cwd 往往就是脚本所在目录, 但不能保证每次都一样,
# 之前就因为这个报过 "raw_data_location does not exist"。
RAW_DATA_CACHE = str(Path(__file__).resolve().parent / "nemosis_cache")
scarcity_curve.RAW_DATA_CACHE = RAW_DATA_CACHE
run_window = scarcity_curve.run_window


def month_range(start_ym, end_ym):
    """从起始年月一直数到结束年月 (含两端), 每次吐出一个 (年, 月) 元组。

    参数:
        start_ym: 起始 (年, 月), 比如 (2024, 8)
        end_ym: 结束 (年, 月), 比如 (2025, 6)

    返回:
        一个生成器, 依次产出 (年, 月)
    """
    y, m = start_ym
    while (y, m) <= end_ym:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def default_end_month():
    """算出默认要抓到哪个月为止: 今天所在月份的上一个月 (当月数据往往还没归档完整)。"""
    today = date.today()
    return (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)


def main():
    """主流程: 按命令行参数或默认范围, 一个月一个月地调用 run_window 抓数据并存盘。

    已经抓过的月份 (对应的输出文件已存在) 会自动跳过, 支持中断后重新运行接着抓。
    某个月失败了 (比如那个月数据本来就不存在) 不会中断整体流程, 会跳过继续抓下一个月。
    """
    if len(sys.argv) >= 3:
        start_ym = tuple(int(x) for x in sys.argv[1].split("-"))
        end_ym = tuple(int(x) for x in sys.argv[2].split("-"))
    else:
        start_ym = (2024, 8)
        end_ym = default_end_month()

    print(f"拉取范围: {start_ym[0]}-{start_ym[1]:02d} ~ {end_ym[0]}-{end_ym[1]:02d}")

    ok, skipped, failed = [], [], []
    for y, m in month_range(start_ym, end_ym):
        label = f"monthly_{y}{m:02d}"
        out_path = f"{RAW_DATA_CACHE}/scarcity_curve_data_{label}.parquet"
        if os.path.exists(out_path):
            print(f"跳过 {label} (已存在 {out_path})")
            skipped.append(label)
            continue

        start_time = f"{y}/{m:02d}/01 00:00:00"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end_time = f"{ny}/{nm:02d}/01 00:00:00"

        try:
            run_window(start_time, end_time, label)
            ok.append(label)
        except Exception as e:
            print(f"!! {label} 失败, 跳过: {e}")
            failed.append(label)

    print(f"\n完成: {len(ok)} 个新月份, 跳过 {len(skipped)} 个已存在, {len(failed)} 个失败")
    if failed:
        print(f"失败的月份 (可能是该月数据本来就不存在, 或网络问题): {failed}")
    print("\n现在可以直接跑 backtest_holdout.py, 它会自动发现所有月份文件。")


if __name__ == "__main__":
    main()
