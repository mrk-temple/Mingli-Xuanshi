"""离线应用冒烟：独立临时数据，不访问模型、不改写个人存档。"""
from __future__ import annotations

import os
import tempfile


def main() -> None:
    with tempfile.TemporaryDirectory() as root:
        os.environ["MINGLI_DATA_DIR"] = root
        os.environ["MINGLI_SETTINGS_FILE"] = os.path.join(root, "settings.json")
        os.environ["MINGLI_INTERPRETER"] = "rule-engine"
        from fastapi.testclient import TestClient

        from mingli.web.app import app
        with TestClient(app) as client:
            for path in ("/", "/generate", "/generate/tarot", "/generate/bazi", "/settings", "/static/style.css"):
                assert client.get(path).status_code == 200, path
            result = client.post("/generate/tarot", data={"q": "换工作前确认什么？", "seed": "42"}, follow_redirects=False)
            assert result.status_code == 303
            page = client.get(result.headers["location"])
            assert "先用白话回答" in page.text
            assert "五大未证假设" in page.text
            assert client.get(result.headers["location"] + "/report.md").status_code == 200
        print("Application smoke passed (offline, isolated data)")


if __name__ == "__main__":
    main()
