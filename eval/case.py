"""评测用例 case.py：一条 Case = 用户输入 + 录制回放盒(cassette) + 期望断言(Expect)。

用 JSON（零依赖、stdlib 可读），不引入 YAML。每条断言可选，提供哪条就断哪条。
"""

from pathlib import Path

from pydantic import BaseModel, Field


class Expect(BaseModel):
    """对一次 run 的期望断言（全部可选）：工具序列 / 必调 / 禁调 / 答案子串 / 轮数上限。"""

    tool_sequence: list[str] | None = None  # 工具调用名的精确序列（按调用先后）
    must_call: list[str] = Field(default_factory=list)  # 必须出现的工具
    must_not_call: list[str] = Field(default_factory=list)  # 不得出现的工具
    answer_contains: str | None = None  # 最终答案应包含的子串
    max_turns: int | None = None  # 模型轮数上限


class Case(BaseModel):
    """一条评测用例：name 唯一、input 用户输入、cassette 回放盒文件名、expect 断言集。"""

    name: str
    input: str
    cassette: str
    expect: Expect = Field(default_factory=Expect)


def load_case(path: Path) -> Case:
    """从 JSON 文件加载一条 Case。"""
    return Case.model_validate_json(path.read_text(encoding="utf-8"))


def load_cases(case_dir: Path) -> list[Case]:
    """加载目录下全部 *.json 用例（按文件名排序，确保稳定）。"""
    return [load_case(path) for path in sorted(case_dir.glob("*.json"))]
