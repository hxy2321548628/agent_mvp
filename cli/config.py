"""CLI 顶层参数 config.py：终端表现层的可调常量集中于此（禁止散落进函数内部）。

库级运行参数（MAX_TURN/STREAM 等）见 src/config.py；本文件只放 CLI 自身的交互常量。
"""


# —— 顶层参数（集中管理，不要硬编码进函数）——
COMMAND_PREFIX = ":"  # 命令前缀：以此开头即命令，否则按普通对话处理
DEFAULT_THREAD = "w1"  # 启动时的默认窗口（thread_id）
PROMPT = "» "  # 输入提示符
WELCOME = "ReAct Agent CLI —— 直接输入消息对话，:help 查看命令。"
GOODBYE = "再见。"
HELP = (
    "命令：\n"
    "  :new [id]      开新窗口（缺省自动命名）\n"
    "  :switch <id>   切换到指定窗口\n"
    "  :list          列出全部窗口（* 标记当前）\n"
    "  :trace         开关执行/工具日志\n"
    "  :stream        开关流式输出\n"
    "  :help          显示本帮助\n"
    "  :quit / :exit  退出"
)
