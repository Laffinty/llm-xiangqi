"""本地启动 Web 3D 对局界面（P-18 人工观感评估用）。

**为什么需要这个脚本**：`game.py` 只从环境变量读 `DEEPSEEK_API_KEY` / `MIMO_API_KEY`，
而本机环境变量里的 MiMo key 已失效（401）、DeepSeek key 未设置。
本脚本从**桌面密钥文件**读取并注入当前进程环境，**不写入任何配置文件**。

用法：
    python run_web.py --turns 40

密钥文件路径可用 `LLM_KEY_FILE` 覆盖；密钥不会出现在命令行参数里。
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

DEFAULT_KEY_FILE = Path.home() / "Desktop" / "TEST_API.txt"

# provider 名 -> 环境变量名（与 config/*.yaml 里的 ${...} 对应）
ENV_FOR_PROVIDER = {
    "deepseek": "DEEPSEEK_API_KEY",
    "mimo": "MIMO_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def inject_keys(key_file: Path) -> None:
    """从密钥文件读取并注入环境变量。文件不存在则跳过（可能已有环境变量）。"""
    if not key_file.exists():
        print("[warn] 密钥文件不存在：%s（将依赖已有环境变量）" % key_file)
        return
    from tests.eval.providers import _read_key_file
    keys = _read_key_file(str(key_file))
    for provider, key in keys.items():
        env_name = ENV_FOR_PROVIDER.get(provider)
        if not env_name:
            print("[warn] 未知 provider，跳过：%s" % provider)
            continue
        os.environ[env_name] = key
        print("[ok] 已注入 %s（长度 %d）" % (env_name, len(key)))


def main() -> None:
    ap = argparse.ArgumentParser(description="启动 Web 3D 对局界面")
    ap.add_argument("--turns", type=int, default=40, help="最大回合数（默认 40）")
    ap.add_argument("--key-file", default=str(DEFAULT_KEY_FILE),
                    help="密钥文件路径（默认桌面 TEST_API.txt）")
    args = ap.parse_args()

    inject_keys(Path(args.key_file))

    # 复用 game.py 的完整对局流程（含 Web3D server 启动）
    import game
    sys.argv = [sys.argv[0], "--turns", str(args.turns)]
    asyncio.run(game.main())


if __name__ == "__main__":
    main()