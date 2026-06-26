# Makefile —— 常用开发命令（基于 uv）
# 用法：make <目标>；直接 make 显示帮助。

.DEFAULT_GOAL := help
.PHONY: help install run-cli test eval eval-online eval-live format check clean

help:  ## 显示所有可用目标
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## 同步依赖（含 dev 组）
	uv sync

run-cli:  ## 启动 CLI 客户端 REPL（需 .env 配好 DEEPSEEK_API_KEY/DEEPSEEK_PROXY）
	uv run python -m cli.main

test:  ## 运行测试（带覆盖率报告）
	uv run pytest

eval:  ## 离线回放打分评测（确定性，CI 闸门用，无需 API）
	uv run python -m eval

eval-online:  ## 在线真实 API 打分评测（跑 case + 软指标 + 比在线基线；需 DEEPSEEK_API_KEY）
	uv run python -m eval.online

eval-live:  ## 客户端真实 API 冒烟（最轻量，pytest @slow；需 DEEPSEEK_API_KEY）
	uv run pytest -m slow

check:  ## 代码格检查修复（ruff）
	uv run ruff check --fix

format:  ## 代码格式化
	uv run ruff format

clean:  ## 清理缓存与覆盖率产物
	rm -rf .pytest_cache .ruff_cache .coverage
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
