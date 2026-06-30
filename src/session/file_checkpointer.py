"""文件检查点 file_checkpointer.py：每 thread 一份 JSONL 的本地持久化（实现 Checkpointer 协议）。

崩溃安全靠追加写、不重写整文件：首行 meta（thread_id/created_at），其后每条「非钉住」消息一行。
钉住前缀不入盘——SessionPrefix 每轮从系统提示/环境/todo 派生重注入，存它只会过期；
载入后下一轮 on_session_start 自会重注入，故磁盘只留真实对话（Human/AI/Tool/非钉住 System）。

注：破坏性压缩（ContextMiddleware，≥MAX_MSG 触发）与追加写的协调留到 P20 非破坏压缩
（见 doc/ddd/03ddd.md §29「完整 transcript 落盘、只压上下文视图」）；P17 阶段会话普遍在阈值内。
"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from src.schema.message import AnyMessage, SystemMessage
from src.schema.state import AgentState


# —— 顶层参数 ——
FILE_SUFFIX = ".jsonl"  # 每 thread 一份此后缀文件
ROLE_KEY = "role"  # 消息行的判别键（含 role 即消息行；首行 meta 无 role）

_MESSAGE_ADAPTER = TypeAdapter(AnyMessage)


class FileCheckpointer:
    """本地 JSONL 持久化：thread_id → <session_dir>/<thread_id>.jsonl。实现 Checkpointer 协议。"""

    def __init__(self, session_dir: str) -> None:
        self._dir = Path(session_dir)
        self._persisted: dict[str, int] = {}  # 各 thread 已落盘的「非钉住」消息条数（本进程缓存，追加偏移）

    def get(self, thread_id: str) -> AgentState | None:
        """读回该 thread 的完整历史；文件不存在返回 None。逐行重放：meta 一行 + 消息若干行。"""
        path = self._path(thread_id)
        if not path.exists():
            return None
        created_at: str | None = None
        messages: list = []
        for obj in self._iter_lines(path):
            if ROLE_KEY in obj:
                messages.append(_MESSAGE_ADAPTER.validate_python(obj))
            else:
                created_at = obj.get("created_at")
        self._persisted[thread_id] = len(messages)
        fields = {"thread_id": thread_id, "messages": messages}
        if created_at is not None:
            fields["created_at"] = created_at
        return AgentState(**fields)

    def put(self, thread_id: str, state: AgentState) -> None:
        """把自上次落盘以来「新增的非钉住消息」追加写入；无新增则不写（空会话不落盘）。"""
        durable = [m for m in state.messages if not (isinstance(m, SystemMessage) and m.pinned)]
        new = durable[self._offset(thread_id) :]
        if not new:
            return
        path = self._path(thread_id)
        lines: list[str] = []
        if not path.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            lines.append(json.dumps({"thread_id": thread_id, "created_at": state.created_at}, ensure_ascii=False))
        lines.extend(m.model_dump_json() for m in new)
        with path.open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        self._persisted[thread_id] = len(durable)

    def list_threads(self) -> list[str]:
        """列出磁盘已有的 thread_id（按文件修改时间，旧→新）。"""
        if not self._dir.exists():
            return []
        paths = sorted(self._dir.glob(f"*{FILE_SUFFIX}"), key=lambda p: p.stat().st_mtime)
        return [p.stem for p in paths]

    def _path(self, thread_id: str) -> Path:
        return self._dir / f"{thread_id}{FILE_SUFFIX}"

    def _offset(self, thread_id: str) -> int:
        """该 thread 已落盘的非钉住消息条数；未缓存则按磁盘现有消息行数初始化（兼容未先 get 即 put）。"""
        if thread_id not in self._persisted:
            path = self._path(thread_id)
            self._persisted[thread_id] = sum(ROLE_KEY in obj for obj in self._iter_lines(path)) if path.exists() else 0
        return self._persisted[thread_id]

    @staticmethod
    def _iter_lines(path: Path):
        """逐行解析非空行为 JSON 对象。"""
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text:
                yield json.loads(text)
