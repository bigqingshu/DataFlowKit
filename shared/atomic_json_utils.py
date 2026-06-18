# -*- coding: utf-8 -*-
"""Atomic JSON persistence helpers with one-file backup recovery."""

import json
import os
import shutil
import tempfile
from pathlib import Path


def json_backup_path(path):
    return Path(str(Path(path)) + ".bak")


def atomic_write_json(path, data, keep_backup=True):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = json_backup_path(target)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if keep_backup and target.exists():
            shutil.copy2(str(target), str(backup))
        os.replace(str(temp_path), str(target))
        temp_path = None
        return str(target)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def load_json_with_backup(path, default=None):
    target = Path(path)
    backup = json_backup_path(target)
    if not target.exists():
        if default is not None:
            return default, {"source": "default", "warning": ""}
        raise FileNotFoundError(str(target))

    try:
        return json.loads(target.read_text(encoding="utf-8")), {
            "source": "primary",
            "warning": "",
        }
    except Exception as primary_error:
        if backup.exists():
            try:
                data = json.loads(backup.read_text(encoding="utf-8"))
                return data, {
                    "source": "backup",
                    "warning": f"主配置文件损坏，已从备份恢复：{backup}",
                    "primary_error": str(primary_error),
                }
            except Exception as backup_error:
                raise ValueError(
                    f"JSON 主文件和备份均无法读取：{target}；"
                    f"主文件错误：{primary_error}；备份错误：{backup_error}"
                ) from backup_error
        raise ValueError(f"JSON 文件无法读取：{target}；错误：{primary_error}") from primary_error
