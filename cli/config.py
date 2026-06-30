"""CLI 顶层参数 config.py：终端表现层的可调常量集中于此（禁止散落进函数内部）。

库级运行参数（MAX_TURN/STREAM 等）见 src/config.py；本文件只放 CLI 自身的交互常量。
"""

# —— 顶层参数（集中管理，不要硬编码进函数）——
COMMAND_PREFIX = ":"  # 命令前缀：以此开头即命令，否则按普通对话处理
PROMPT = "» "  # 输入提示符
SESSION_PREVIEW_MAXLEN = 20  # :list/:resume 里会话标题（首条用户消息）展示的截断长度
NEW_SESSION_TITLE = "（新会话）"  # 尚无用户消息的会话在 :list 里的占位标题
WELCOME = "ReAct Agent CLI —— 直接输入消息对话，:help 查看命令。"
GOODBYE = "再见。"
APPROVE_PROMPT = "允许[y] / 拒绝[n] / 总是允许[a]："  # HITL 工具授权三选项提示
HELP = (
    "命令：\n"
    "  :new           开新会话（自动分配 uuid）\n"
    "  :list          列出全部会话（序号 + 首句 + 时间，* 标记当前）\n"
    "  :resume [序号] 缺省列出可恢复会话；带序号则恢复该会话（序号见 :list）\n"
    "  :trace         开关执行/工具日志\n"
    "  :stream        开关流式输出\n"
    "  :think         开关推理（思考）模式\n"
    "  :cassette <场景> 开始录制评测用例（再 :cassette 结束）\n"
    "  :help          显示本帮助\n"
    "  :quit / :exit  退出"
)
