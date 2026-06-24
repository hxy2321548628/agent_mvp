"""全局配置：顶层参数集中于此（禁止散落进函数内部），Settings 从 .env 读取密钥。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# —— 顶层参数（集中管理，便于调参；不要硬编码进函数）——
DEFAULT_MODEL = "deepseek-v4-flash"  # 默认对话模型
DEFAULT_BASE_URL = "https://api.deepseek.com"  # DeepSeek（OpenAI 兼容）API 基础 URL
MAX_TURN = 10  # 单次 run 的最大循环轮数（MaxTurnMiddleware 据此终止）
MAX_MSG = 40  # 触发上下文压缩的消息条数阈值（ContextMiddleware）
KEEP_RECENT = 10  # 压缩时保留的最近消息条数
STREAM = True  # 是否默认开启流式输出（on_token 实时回调）


class Settings(BaseSettings):
    """应用配置：优先级 init 参数 > 环境变量 > .env 文件 > 默认值。

    密钥等敏感项放在 .env（不入库），模型/URL 默认回退到上方顶层参数。
    采用依赖注入：由组合根（cli）实例化后注入，不在模块级创建单例。
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API 密钥（放 .env，勿入库）")
    DEEPSEEK_BASE_URL: str = Field(default=DEFAULT_BASE_URL, description="DeepSeek API 基础 URL")
    DEEPSEEK_MODEL: str = Field(default=DEFAULT_MODEL, description="默认对话模型")
