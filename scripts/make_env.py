"""Writes .env from .env.example, replacing the three secrets. Used by setup.sh."""
import os  # read the secrets from environment variables
import re  # to spot values that need quoting
from pathlib import Path  # simple file reading/writing

KEYS = ("GOOGLE_API_KEY", "APP_ACCESS_USERNAME", "APP_ACCESS_PASSWORD")  # values the user types


def quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_@%+:,./-]+", value):  # plain values need no quotes (also keeps docker --env-file happy)
        return value
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"  # otherwise single-quote and escape backslash and quote


def render(template: str, values: dict[str, str]) -> str:
    lines = []  # output lines
    for line in template.splitlines():  # walk the template
        key = line.split("=", 1)[0].strip()  # name before the "="
        lines.append(f"{key}={quote(values[key])}" if key in values else line)  # replace our three, keep the rest
    return "\n".join(lines) + "\n"  # file text


if __name__ == "__main__":
    secrets = {k: os.environ[k] for k in KEYS}  # exported by setup.sh (avoids shell quoting problems)
    template = Path(".env.example").read_text(encoding="utf-8")  # the template
    Path(".env").write_text(render(template, secrets), encoding="utf-8", newline="\n")  # save the result
