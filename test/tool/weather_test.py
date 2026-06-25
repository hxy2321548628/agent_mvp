"""tool/weather 模块测试：mock 天气返回含 city 的稳定结构。"""

from src.tool.weather import WeatherArgs, WeatherTool


def test_weather_result_contains_city() -> None:
    """mock 天气应包含城市名。"""
    assert "北京" in WeatherTool().run(WeatherArgs(city="北京"))


def test_weather_is_deterministic() -> None:
    """mock 工具应稳定可复现。"""
    tool = WeatherTool()
    assert tool.run(WeatherArgs(city="上海")) == tool.run(WeatherArgs(city="上海"))


def test_weather_exposes_protocol_fields() -> None:
    """应暴露 name 与 args_model 供注册与 schema 生成。"""
    tool = WeatherTool()
    assert tool.name == "weather"
    assert tool.args_model is WeatherArgs
