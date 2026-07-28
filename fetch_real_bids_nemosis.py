"""
本地运行模板 —— 用 NEMOSIS 抓取真实机组报价 (BIDDAYOFFER_D / BIDPEROFFER_D)
和真实机组出力 (DISPATCH_UNIT_SCADA)。

⚠️ 这份代码需要你在自己电脑上跑，不能在这个 sandbox 里跑，
   因为这里的网络白名单不包含 nemweb.com.au / aemo.com.au。

安装:
    pip install nemosis

坑提醒:
    1. BIDDAYOFFER_D / BIDPEROFFER_D 这两张表在 2021-03 到 2024-07 之间有缺失
       （NEMOSIS 官方 README 里写的），选时间窗口时要避开或者绕开这段。
    2. Bid 表体积很大（一个月 zip 压缩后 0.5-1.5GB），第一次跑强烈建议只选
       几天到最多一个月，不要一上来就拉一整年。
    3. 第一次跑会把原始 zip 下载到 raw_data_cache 目录并转成 parquet 缓存，
       之后同一时间段再跑会直接读缓存，不会重新下载。
"""
from nemosis import dynamic_data_compiler

# ---------- 基本设置 ----------
RAW_DATA_CACHE = "./nemosis_cache"   # 缓存目录，自己改成本地任意路径
START_TIME = "2025/05/01 00:00:00"   # 建议先挑你诊断出来尖峰最多的月份 (5月)
END_TIME = "2025/05/08 00:00:00"     # 先只拉一周，跑通了再扩大范围
# 注意: BIDDAYOFFER_D / BIDPEROFFER_D 在 2021-03 ~ 2024-07 之间缺失 (NEMOSIS 官方已知问题)，
# 选时间窗口时必须避开这段，否则会报 NoDataToReturn。

# 挑几台真实机组来看 (来自我们之前找到的 NSW1 真实 DUID)
PEAKER_DUIDS = ["ER01", "ER02", "BW01", "BW02"]  # 换成你想研究的 DUID 列表

# ---------- 1. 拉真实报价数据 (机组愿意卖多少钱) ----------
# BIDDAYOFFER_D: 每台机组每天的价格阶梯 (10档价格band)
bid_price_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDDAYOFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("报价价格档 (BIDDAYOFFER_D) 样例:")
print(bid_price_bands.head())

# BIDPEROFFER_D: 每台机组每个5分钟interval，每档价格对应能卖多少MW
bid_volume_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDPEROFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("\n报价数量档 (BIDPEROFFER_D) 样例:")
print(bid_volume_bands.head())

# ---------- 2. 拉真实出力数据 (机组实际发了多少电) ----------
unit_scada = dynamic_data_compiler(
    START_TIME, END_TIME, "DISPATCH_UNIT_SCADA", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("\n真实出力 (DISPATCH_UNIT_SCADA) 样例:")
print(unit_scada.head())

# ---------- 3. 这些数据接下来怎么用（思路，不是完整代码） ----------
# a) 把 bid_price_bands + bid_volume_bands 按 DUID + interval 合并，
#    重建出每台机组每个5分钟的完整报价阶梯（10档价格 x 10档数量）。
# b) 把这个报价阶梯，跟同一时间的系统 reserve margin（可以从你已有的
#    nsw1_2023.csv 算出来）对齐，就能看到「备用容量越紧张，这台机组
#    报价占比越高」这条真实曲线长什么样 —— 这条曲线就是用来替代
#    nem_mvp.py 里那个手编的 alpha 公式的真实校准依据。
# c) unit_scada 则是用来验证「这台机组真的被叫起来发电了吗，
#    发了多少」，可以拿来对比你 ABM 模拟出来的 dispatch 结果对不对得上。
