"""Setups: a layout plus a keyboard profile that covers it, collected for the static page."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any

from steno_zero.drill import drill_plan
from steno_zero.keyboard import KeyboardProfile, finger_blocked, profile_sha256
from steno_zero.layout import Layout, layout_obj

SETUPS_FORMAT: str = "steno-zero/setups"
SETUPS_VERSION: int = 1
SETUPS_PREFIX: str = "window.STENO_ZERO_SETUPS = "
SETUPS_SUFFIX: str = ";\n"


def setup_name(layout: Layout, profile: KeyboardProfile | None) -> str:
    return layout.name if profile is None else f"{layout.name}@{profile.name}"


def setups_data(
    layouts: Sequence[Layout], profiles: Sequence[KeyboardProfile], drill: Mapping[str, Any]
) -> dict[str, Any]:
    if not layouts:
        raise ValueError("no layouts")
    layout_names: list[str] = [x.name for x in layouts]
    if len(set(layout_names)) != len(layout_names):
        raise ValueError("layout names repeat")
    profile_names: list[str] = [x.name for x in profiles]
    if len(set(profile_names)) != len(profile_names):
        raise ValueError("profile names repeat")
    seed: int = drill["seed"]
    blocks: int = len(drill["blocks"])
    size: int = drill["size"]
    max_keys: int = drill["max_keys"]
    setups: list[dict[str, Any]] = []
    layout: Layout
    for layout in sorted(layouts, key=lambda x: x.name):
        profile: KeyboardProfile | None
        for profile in sorted(profiles, key=lambda x: x.name):
            if not set(layout.codes) <= set(profile.keys):
                continue
            blocked: tuple[int, ...] = finger_blocked(profile, layout)
            setups.append(
                {
                    "name": setup_name(layout, profile),
                    "layout": layout_obj(layout),
                    "keyboard": {"name": profile.name, "sha256": profile_sha256(profile)},
                    "blocked": list(blocked),
                    "plan": [list(b) for b in drill_plan(seed, blocks, size, max_keys, blocked)],
                }
            )
        setups.append(
            {
                "name": setup_name(layout, None),
                "layout": layout_obj(layout),
                "keyboard": None,
                "blocked": [],
                "plan": None,
            }
        )
    return {
        "format": SETUPS_FORMAT,
        "version": SETUPS_VERSION,
        "drill": {"seed": seed, "blocks": blocks, "size": size, "max_keys": max_keys},
        "setups": setups,
    }


def setups_js(data: Mapping[str, Any]) -> str:
    return SETUPS_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + SETUPS_SUFFIX


def write_setups_js(data: Mapping[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    f: IO[str]
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(setups_js(data))


def read_setups_js(path: Path) -> dict[str, Any]:
    text: str = path.read_text(encoding="utf-8")
    if not (text.startswith(SETUPS_PREFIX) and text.endswith(SETUPS_SUFFIX)):
        raise ValueError("not a setups.js")
    try:
        obj: Any = json.loads(text[len(SETUPS_PREFIX) : len(text) - len(SETUPS_SUFFIX)])
    except ValueError as exc:
        raise ValueError(f"bad setups.js JSON: {exc}") from exc
    if (
        not isinstance(obj, dict)
        or obj.get("format") != SETUPS_FORMAT
        or obj.get("version") != SETUPS_VERSION
    ):
        raise ValueError(f"not a steno-zero setups file, version {SETUPS_VERSION}")
    return obj
