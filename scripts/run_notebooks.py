"""重跑全部 Notebook，并把输出写回文件（in-place）。

为什么需要这个脚本：
GitHub 上直接打开 .ipynb 时，如果文件里没有存输出，读者只能看到代码。
所以仓库里提交的 Notebook 必须是「跑过并带输出」的版本，这个脚本就是用来保证这一点的。

    python scripts/run_notebooks.py            # 全部重跑
    python scripts/run_notebooks.py 02         # 只跑文件名含 02 的
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

ROOT = Path(__file__).resolve().parents[1]
NB_DIR = ROOT / "notebooks"


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted(p for p in NB_DIR.glob("*.ipynb") if pattern in p.name)
    if not files:
        print(f"{NB_DIR} 下没有匹配 {pattern!r} 的 Notebook")
        return 1

    failed = 0
    for path in files:
        print(f"▶ 执行 {path.name} ...", end=" ", flush=True)
        nb = nbformat.read(path, as_version=4)
        client = NotebookClient(
            nb,
            timeout=900,
            kernel_name="python3",
            # cwd 设为 notebooks/，顺便验证 Notebook 里的路径兼容逻辑
            resources={"metadata": {"path": str(NB_DIR)}},
            allow_errors=False,
        )
        try:
            client.execute()
        except CellExecutionError as exc:
            failed += 1
            print("失败")
            print(exc)
            continue
        nbformat.write(nb, path)
        n_out = sum(1 for c in nb.cells if c.cell_type == "code" and c.get("outputs"))
        print(f"完成（{n_out} 个代码单元格带输出）")

    if failed:
        print(f"\n{failed} 个 Notebook 执行失败")
        return 1
    print("\n全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
