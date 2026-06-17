# -*- coding: utf-8 -*-
"""Plugin discovery and metadata loading for DataFlowKit."""

import ast
import importlib.util
import json
import os
import traceback


def normalize_run_mode(value, default="主程序内置环境"):
    text = str(value or default or "").strip()
    if text in ("external_python", "独立环境", "插件独立环境", "external", "external-python"):
        return "插件独立环境"
    return "主程序内置环境"


def static_read_py_metadata(path):
    """静态读取 .py 插件中的元信息，避免扫描阶段执行业务依赖 import。"""
    with open(path, "r", encoding="utf-8") as stream:
        source = stream.read()
    tree = ast.parse(source, filename=path)
    values = {}
    names = {
        "PLUGIN_INFO",
        "plugin_info",
        "PARAMETER_SCHEMA",
        "parameter_schema",
        "PLUGIN_SCHEMA",
        "SCHEMA",
    }
    for node in tree.body:
        target_name = None
        value_node = None
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target_name = node.targets[0].id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value
        if target_name in names and value_node is not None:
            try:
                values[target_name] = ast.literal_eval(value_node)
            except Exception:
                pass
    info = values.get("PLUGIN_INFO") or values.get("plugin_info")
    schema = (
        values.get("PARAMETER_SCHEMA")
        or values.get("parameter_schema")
        or values.get("PLUGIN_SCHEMA")
        or values.get("SCHEMA")
        or []
    )
    return info, schema


def import_plugin_module(path, filename):
    module_name = f"workflow_plugin_{os.path.splitext(filename)[0]}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法创建插件导入 spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_plugins(plugins_dir):
    registry = {}
    errors = []

    def normalize_info_schema(info, schema, source_name):
        if not isinstance(info, dict):
            raise RuntimeError("缺少 PLUGIN_INFO / plugin_info 字典")
        plugin_id = str(info.get("id", "")).strip()
        if not plugin_id:
            raise RuntimeError("插件 id 不能为空")
        api_version = str(info.get("api_version", "1.0")).strip()
        if api_version != "1.0":
            raise RuntimeError(f"插件协议版本不兼容：{api_version}，当前支持 1.0")
        if schema is None:
            schema = []
        if not isinstance(schema, list):
            raise RuntimeError("插件参数 schema 必须是 list")
        if plugin_id in registry:
            raise RuntimeError(f"插件 id 重复：{plugin_id}（来源：{source_name}）")
        return plugin_id, dict(info), schema

    def build_registry_item(plugin_id, info, schema, path, *, module=None, external_entry=None,
                            requirements_path="", manifest_path="", run_mode_default="主程序内置环境",
                            import_ok=True, import_error="", metadata_source="import"):
        run_mode_default = normalize_run_mode(run_mode_default, "主程序内置环境")
        if import_ok:
            available_run_modes = ["主程序内置环境", "插件独立环境"]
            load_status = "可内置运行"
        else:
            available_run_modes = ["插件独立环境"]
            load_status = "仅独立环境运行"
            run_mode_default = "插件独立环境"
        registry[plugin_id] = {
            "id": plugin_id,
            "info": info,
            "module": module,
            "schema": schema,
            "path": path,
            "external_entry": external_entry or path,
            "requirements_path": requirements_path,
            "manifest_path": manifest_path,
            "run_mode_default": run_mode_default,
            "import_ok": bool(import_ok),
            "import_error": import_error or "",
            "load_status": load_status,
            "available_run_modes": available_run_modes,
            "metadata_source": metadata_source,
        }

    def register_py_file(path, filename):
        static_info = None
        static_schema = []
        static_error = ""
        try:
            static_info, static_schema = static_read_py_metadata(path)
        except Exception as exc:
            static_error = str(exc)

        declared_mode = ""
        if isinstance(static_info, dict):
            declared_mode = normalize_run_mode(static_info.get("run_mode") or static_info.get("run_mode_default"), "")
        if static_info and declared_mode == "插件独立环境":
            plugin_id, info, schema = normalize_info_schema(static_info, static_schema, filename)
            build_registry_item(
                plugin_id, info, schema, path,
                module=None,
                external_entry=path,
                run_mode_default="插件独立环境",
                import_ok=False,
                import_error="插件声明默认使用独立环境，扫描阶段已跳过主程序 import。",
                metadata_source="static_py",
            )
            return

        try:
            module = import_plugin_module(path, filename)
            info = getattr(module, "PLUGIN_INFO", None) or static_info
            schema_func = getattr(module, "get_parameter_schema", None)
            if callable(schema_func):
                schema = schema_func()
            else:
                schema = getattr(module, "PARAMETER_SCHEMA", None) or static_schema or []
            plugin_id, info, schema = normalize_info_schema(info, schema, filename)
            if not callable(getattr(module, "run", None)):
                raise RuntimeError("插件缺少 run(input_data, params, context) 函数")
            build_registry_item(
                plugin_id, info, schema, path,
                module=module,
                external_entry=path,
                run_mode_default=info.get("run_mode", "主程序内置环境"),
                import_ok=True,
                metadata_source="import_py",
            )
        except Exception as import_exc:
            if static_info:
                plugin_id, info, schema = normalize_info_schema(static_info, static_schema, filename)
                build_registry_item(
                    plugin_id, info, schema, path,
                    module=None,
                    external_entry=path,
                    run_mode_default="插件独立环境",
                    import_ok=False,
                    import_error=str(import_exc),
                    metadata_source="static_py_import_failed",
                )
            else:
                detail = str(import_exc)
                if static_error:
                    detail = f"静态元信息读取失败：{static_error}；导入失败：{detail}"
                raise RuntimeError(detail)

    def register_manifest(plugin_dir, manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        info = manifest.get("PLUGIN_INFO") or manifest.get("plugin_info") or manifest.get("info")
        if info is None and "id" in manifest:
            info = manifest
        schema = manifest.get("schema") or manifest.get("parameters") or manifest.get("parameter_schema") or []
        plugin_id, info, schema = normalize_info_schema(info, schema, manifest_path)
        entry = manifest.get("entry") or manifest.get("main") or info.get("entry") or "plugin.py"
        entry_path = entry if os.path.isabs(entry) else os.path.join(plugin_dir, entry)
        req = manifest.get("requirements") or info.get("requirements") or "requirements.txt"
        req_path = req if os.path.isabs(req) else os.path.join(plugin_dir, req)
        run_mode_default = normalize_run_mode(
            manifest.get("run_mode") or info.get("run_mode") or "插件独立环境",
            "插件独立环境",
        )

        module = None
        import_ok = False
        import_error = ""
        metadata_source = "plugin_json"
        if run_mode_default == "主程序内置环境":
            try:
                module = import_plugin_module(entry_path, os.path.basename(entry_path))
                if not callable(getattr(module, "run", None)):
                    raise RuntimeError("插件缺少 run(input_data, params, context) 函数")
                import_ok = True
                metadata_source = "plugin_json_imported"
            except Exception as exc:
                import_error = str(exc)
                run_mode_default = "插件独立环境"
        else:
            import_error = "plugin.json 注册插件，扫描阶段默认不导入业务入口。"

        build_registry_item(
            plugin_id, info, schema, entry_path,
            module=module,
            external_entry=entry_path,
            requirements_path=req_path if os.path.exists(req_path) else "",
            manifest_path=manifest_path,
            run_mode_default=run_mode_default,
            import_ok=import_ok,
            import_error=import_error,
            metadata_source=metadata_source,
        )

    if not os.path.isdir(plugins_dir):
        return registry, errors

    for name in sorted(os.listdir(plugins_dir)):
        full = os.path.join(plugins_dir, name)
        if not os.path.isdir(full):
            continue
        manifest_path = os.path.join(full, "plugin.json")
        if not os.path.exists(manifest_path):
            continue
        try:
            register_manifest(full, manifest_path)
        except Exception as exc:
            errors.append({
                "file": f"{name}/plugin.json",
                "path": manifest_path,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })

    for filename in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, filename)
        if os.path.isdir(path):
            continue
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        try:
            register_py_file(path, filename)
        except Exception as exc:
            errors.append({
                "file": filename,
                "path": path,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })

    return registry, errors

