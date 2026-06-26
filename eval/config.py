"""评测配置 config.py：目录与基线路径集中于此（单数命名、不硬编码进函数）。"""

# —— 顶层参数 ——
EVAL_DIR = "eval"  # 评测包根目录
EVAL_CASE_DIR = "eval/case"  # 用例（*.json）目录
EVAL_CASSETTE_DIR = "eval/cassette"  # 录制回放盒（*.json）目录
EVAL_TRACE_DIR = "eval/run"  # 回放产生的结构化 trace 落盘目录
EVAL_BASELINE = "eval/baseline.json"  # 离线回放的指标基线（与本次结果 diff，回归则非零退出）
EVAL_ONLINE_BASELINE = "eval/baseline-online.json"  # 在线（真实 API）打分的指标基线（缺省=不判回归）
