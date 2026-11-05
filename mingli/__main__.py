"""python -m mingli —— 本地启动开发服务器。"""
from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("mingli.web.app:app", host="127.0.0.1", port=8800, reload=False)


if __name__ == "__main__":
    main()
