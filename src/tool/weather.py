"""天气工具 weather.py（mock）：返回城市的模板天气，便于离线演示与测试。"""

from pydantic import BaseModel, Field


# —— 顶层参数 ——
TOOL_NAME = "weather"
TOOL_DESCRIPTION = "查询城市天气（mock）：返回模板化的天气信息。"
RESULT_TEMPLATE = "{city}：晴，气温 22°C，东南风 3 级，湿度 45%（mock 数据）。"


class WeatherArgs(BaseModel):
    """天气查询参数。"""

    city: str = Field(description="城市名，如 北京")


class WeatherTool:
    """mock 天气工具：不联网，按模板生成稳定可复现的天气。"""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = WeatherArgs

    def run(self, args: WeatherArgs) -> str:
        """返回包含城市名的模板化天气。"""
        return RESULT_TEMPLATE.format(city=args.city)
