import pytest  # parametrize + monkeypatch

from app.config import Settings, load_env  # the loaders the app uses at startup
from scripts.make_env import render  # what setup.sh uses to write .env

NAMES = ("GOOGLE_API_KEY", "APP_ACCESS_USERNAME", "APP_ACCESS_PASSWORD")  # values setup.sh writes
TRICKY = [
    "simple", 'P@ss "w0rd" #1\\x', "pa${HOME}ss", "$HOME", "${UNSET}", "$(date)", "`cmd`", "it's",
    "a'b\"c", "back\\", "trail\\\\", "ünï¢ode✓", "with space ", "#hash", "x=y", "${A:-fallback}",
]  # characters that commonly break .env files


@pytest.mark.parametrize("password", TRICKY)
def test_secrets_survive_write_and_reload(tmp_path, monkeypatch, password):
    for name in NAMES:
        monkeypatch.setenv(name, "placeholder")  # monkeypatch restores the real values after the test
    template = "LLM_MODEL=x\nGOOGLE_API_KEY=your-key\nAPP_ACCESS_USERNAME=u\nAPP_ACCESS_PASSWORD=p\n# NOTE=1\n"  # mini template
    env_file = tmp_path / ".env"
    env_file.write_text(render(template, dict.fromkeys(NAMES, password)), encoding="utf-8")  # written the way setup.sh writes it
    load_env(str(env_file), override=True)  # loaded the way the app loads it on startup
    loaded = Settings()  # settings read from the environment
    assert loaded.app_access_password == password and loaded.app_access_username == password  # unchanged after reload


def test_plain_values_stay_unquoted():
    text = render("APP_ACCESS_USERNAME=u\n", {"APP_ACCESS_USERNAME": "tapan"})  # simple name
    assert text == "APP_ACCESS_USERNAME=tapan\n"  # no quotes, so docker --env-file reads it correctly
