"""评测用例 case.py：一条 Case = 用户输入 + 期望断言(Expect)；按「场景」组织。

数据形态：一个 `<场景>.jsonl` 文件代表一个场景，每行一条 Case（场景名 = 文件 stem）。
录制回放盒按 `(场景, name)` 键配对（见 replay.py），故 Case 不再持有 cassette 文件名。
用 JSONL（零依赖、stdlib 可读、append 友好），不引入 YAML。每条断言可选，提供哪条就断哪条。
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
    """一条评测用例：scenario 场景名（加载时按文件 stem 注入）、name 场景内唯一、input 用户输入、expect 断言集。"""

    scenario: str = ""  # 所属场景（= jsonl 文件 stem，加载时注入；与 cassette 同名 jsonl 按 name 配对）
    name: str
    input: str
    expect: Expect = Field(default_factory=Expect)


def load_scenario(path: Path) -> list[Case]:
    """加载一个场景 jsonl：逐行解析为 Case，并注入 scenario = 文件 stem（空行跳过）。"""
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(Case.model_validate_json(line).model_copy(update={"scenario": path.stem}))
    return cases


def load_cases(case_dir: Path) -> list[Case]:
    """加载目录下全部 `*.jsonl` 场景（按文件名排序确保稳定），展平为用例列表。"""
    return [case for path in sorted(case_dir.glob("*.jsonl")) for case in load_scenario(path)]
