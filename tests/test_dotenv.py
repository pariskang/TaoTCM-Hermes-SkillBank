import os

from canon_tcm_hermes.cli import main


def test_cli_loads_dotenv_without_overriding_shell(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "TAOTCM_DOTENV_PROBE=from_file\nTAOTCM_DOTENV_SHELL=from_file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TAOTCM_DOTENV_SHELL", "from_shell")
    os.environ.pop("TAOTCM_DOTENV_PROBE", None)
    try:
        main(["init"])
        assert os.environ.get("TAOTCM_DOTENV_PROBE") == "from_file"
        assert os.environ.get("TAOTCM_DOTENV_SHELL") == "from_shell"
    finally:
        os.environ.pop("TAOTCM_DOTENV_PROBE", None)
