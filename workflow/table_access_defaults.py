# -*- coding: utf-8 -*-
"""Pure helpers for default table-access generation."""


def _normalize_mode(normalizer, value):
    return normalizer(value) if callable(normalizer) else value


def _append_current_table_entry(tables, make_table_access_entry, table_permission_set, read=False, write=False, update=False, write_mode="", log_only=True):
    tables.append(
        make_table_access_entry(
            "current",
            "__CURRENT_TABLE__",
            source_type="当前工作流表",
            is_current_table=True,
            permissions=table_permission_set(read=read, write=write, update=update),
            write_mode=write_mode,
            log_only=log_only,
        )
    )


def _append_read_only_entry(tables, make_table_access_entry, table_permission_set, role, table, source_type="SQLite表", **extra):
    tables.append(
        make_table_access_entry(
            role,
            table,
            source_type=source_type,
            permissions=table_permission_set(read=True),
            **extra,
        )
    )


def build_default_table_access_for_node(
    node,
    make_table_access_entry,
    table_permission_set,
    normalize_selected_columns_write_mode=None,
    normalize_group_transit_conflict_mode=None,
    get_plugin_table_access_specs=None,
    make_plugin_declared_access_entry=None,
):
    node = node if isinstance(node, dict) else {}
    node_type = str(node.get("type", "") or "").strip()
    config = node.get("config", {}) if isinstance(node, dict) else {}
    config = config if isinstance(config, dict) else {}
    tables = []

    if node_type in ("跳转锚点节点", "无条件跳转节点", "条件跳转节点"):
        tables = []
    elif node_type == "条件判断节点":
        _append_current_table_entry(
            tables,
            make_table_access_entry,
            table_permission_set,
            read=True,
            write=False,
            update=False,
            write_mode="read_current_table",
            log_only=True,
        )
    else:
        _append_current_table_entry(
            tables,
            make_table_access_entry,
            table_permission_set,
            read=True,
            write=True,
            update=True,
            write_mode="current_table_default",
            log_only=True,
        )

    if node_type == "高级筛选":
        for table in config.get("extra_tables", []) or []:
            table_text = str(table or "").strip()
            if not table_text:
                continue
            if table_text.startswith("中转:"):
                _append_read_only_entry(
                    tables,
                    make_table_access_entry,
                    table_permission_set,
                    "lookup",
                    table_text,
                    source_type="中转副表",
                )
            else:
                _append_read_only_entry(
                    tables,
                    make_table_access_entry,
                    table_permission_set,
                    "lookup",
                    table_text,
                )

    elif node_type == "匹配值输出列名":
        lookup_table = str(config.get("lookup_table", "") or "").strip()
        lookup_source_type = str(config.get("lookup_source_type", "SQLite表") or "SQLite表").strip()
        if lookup_table:
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "lookup",
                lookup_table,
                source_type="中转副表" if lookup_source_type == "中转副表" else "SQLite表",
                field_mapping={
                    field: {"target_field": field, "permissions": {"read_field": True}}
                    for field in (config.get("lookup_fields", []) or [])
                    if str(field or "").strip()
                },
            )

    elif node_type == "选定列写入指定表":
        if config.get("source_type") == "SQLite表" and config.get("source_sqlite_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("source_sqlite_table"),
            )
        if config.get("source_type") == "中转副表" and config.get("source_transit_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("source_transit_table"),
                source_type="中转副表",
            )
        if config.get("target_type", "SQLite表") == "SQLite表":
            can_write = bool(config.get("enable_write", False))
            mode = _normalize_mode(normalize_selected_columns_write_mode, config.get("write_mode", ""))
            tables.append(
                make_table_access_entry(
                    "target",
                    config.get("target_table", ""),
                    permissions=table_permission_set(
                        read=True,
                        write=can_write,
                        create=can_write,
                        update=can_write,
                        clear=can_write and mode == "清空目标字段后覆盖，保留目标原行数",
                        replace=can_write and mode in ("按来源完整结构覆盖", "覆盖重建目标表"),
                        alter=can_write,
                    ),
                    write_mode=mode,
                )
            )
        if config.get("target_type", "SQLite表") == "中转副表":
            can_write = bool(config.get("enable_write", False))
            mode = _normalize_mode(normalize_selected_columns_write_mode, config.get("write_mode", ""))
            tables.append(
                make_table_access_entry(
                    "target",
                    config.get("target_transit_table", "选定列结果"),
                    source_type="中转副表",
                    permissions=table_permission_set(
                        read=True,
                        write=can_write,
                        create=can_write,
                        append=can_write,
                        update=can_write,
                        clear=can_write and mode == "清空目标字段后覆盖，保留目标原行数",
                        replace=can_write and mode in ("按来源完整结构覆盖", "覆盖重建目标表"),
                        alter=can_write,
                    ),
                    write_mode=mode,
                )
            )

    elif node_type == "字段映射写入表":
        if config.get("writeback_direction", "当前表写入SQLite目标表") == "其他表写入当前表":
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("source_table", ""),
            )
        else:
            can_write = bool(config.get("enable_write", False))
            mode = config.get("write_range_mode", "局部覆盖，保留目标原行数")
            tables.append(
                make_table_access_entry(
                    "target",
                    config.get("target_table", ""),
                    permissions=table_permission_set(
                        read=True,
                        write=can_write,
                        update=can_write,
                        clear=can_write and mode == "清空目标字段后覆盖，保留目标原行数",
                        replace=can_write and mode == "按来源完整结构覆盖",
                    ),
                    write_mode=mode,
                )
            )

    elif node_type == "保存中转数据":
        if config.get("save_memory", True):
            append_memory = bool(config.get("append_memory", False))
            tables.append(
                make_table_access_entry(
                    "output",
                    config.get("transit_name", "中转数据"),
                    source_type="中转副表",
                    permissions=table_permission_set(
                        read=True,
                        write=True,
                        create=True,
                        append=append_memory,
                        replace=not append_memory,
                    ),
                    write_mode="追加" if append_memory else "覆盖",
                )
            )
        if config.get("save_sqlite"):
            mode = config.get("sqlite_mode", "自动加时间戳")
            tables.append(
                make_table_access_entry(
                    "sqlite_output",
                    config.get("sqlite_table", config.get("transit_name", "")),
                    permissions=table_permission_set(
                        read=True,
                        write=True,
                        create=True,
                        append=mode == "追加写入",
                        replace=mode == "覆盖同名表",
                    ),
                    write_mode=mode,
                )
            )

    elif node_type == "节点组 / 子工作流":
        if config.get("input_source_type") == "SQLite表" and config.get("input_sqlite_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("input_sqlite_table"),
            )
        if config.get("input_source_type") == "中转副表" and config.get("input_transit_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("input_transit_table"),
                source_type="中转副表",
            )
        if config.get("save_to_transit"):
            mode = _normalize_mode(
                normalize_group_transit_conflict_mode,
                config.get("output_transit_conflict_mode", "覆盖整表"),
            )
            tables.append(
                make_table_access_entry(
                    "output",
                    config.get("output_transit_name") or config.get("group_name", "节点组结果"),
                    source_type="中转副表",
                    permissions=table_permission_set(
                        read=True,
                        write=True,
                        create=True,
                        append=mode == "追加",
                        replace=mode != "追加",
                    ),
                    write_mode=mode,
                )
            )
        if config.get("save_to_sqlite"):
            tables.append(
                make_table_access_entry(
                    "sqlite_output",
                    config.get("output_sqlite_table", config.get("group_name", "")),
                    permissions=table_permission_set(read=True, write=True, create=True, append=True, replace=True),
                    write_mode=config.get("output_sqlite_mode", ""),
                )
            )

    elif node_type == "插件节点":
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        for spec in config.get("input_tables", []) or []:
            if not isinstance(spec, dict):
                continue
            source_type = str(spec.get("source_type", "") or "").strip()
            if source_type == "SQLite表":
                _append_read_only_entry(
                    tables,
                    make_table_access_entry,
                    table_permission_set,
                    spec.get("alias") or "input",
                    spec.get("sqlite_table") or spec.get("table") or "",
                )
            if source_type == "中转副表":
                _append_read_only_entry(
                    tables,
                    make_table_access_entry,
                    table_permission_set,
                    spec.get("alias") or "input",
                    spec.get("transit_table") or spec.get("table") or "",
                    source_type="中转副表",
                )
        output_mode = str(config.get("output_mode", "") or "").strip()
        if bool(config.get("save_output_as_transit", False)) or output_mode.startswith("保存为中转副表"):
            mode = config.get("transit_conflict_mode", "覆盖")
            tables.append(
                make_table_access_entry(
                    "output",
                    config.get("transit_name", config.get("plugin_id", "插件输出")),
                    source_type="中转副表",
                    permissions=table_permission_set(
                        read=True,
                        write=True,
                        create=True,
                        append=mode == "追加",
                        replace=mode != "追加",
                    ),
                    write_mode=mode,
                )
            )
        if config.get("save_plugin_log_transit", False):
            mode = config.get("transit_conflict_mode", "覆盖")
            tables.append(
                make_table_access_entry(
                    "log_output",
                    config.get("plugin_log_transit_name", "插件日志"),
                    source_type="中转副表",
                    permissions=table_permission_set(
                        read=True,
                        write=True,
                        create=True,
                        append=mode == "追加",
                        replace=mode != "追加",
                    ),
                    write_mode=mode,
                )
            )
        if config.get("save_plugin_log_sqlite", False):
            tables.append(
                make_table_access_entry(
                    "sqlite_log",
                    "_plugin_log",
                    permissions=table_permission_set(read=True, write=True, create=True, append=True),
                    write_mode="追加日志",
                )
            )

        plugin_specs = get_plugin_table_access_specs(config) if callable(get_plugin_table_access_specs) else []
        if isinstance(plugin_specs, dict):
            plugin_specs = plugin_specs.get("tables") or [plugin_specs]
        for spec in plugin_specs or []:
            if not isinstance(spec, dict) or not callable(make_plugin_declared_access_entry):
                continue
            tables.append(make_plugin_declared_access_entry(plugin_id, spec))

    elif node_type == "循环执行起点":
        if config.get("source_type") == "SQLite表" and config.get("source_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("source_table"),
            )
        if config.get("source_type") == "中转副表" and config.get("transit_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "source",
                config.get("transit_table"),
                source_type="中转副表",
            )
        tables.append(
            make_table_access_entry(
                "loop_current",
                config.get("current_table_name", "当前循环项"),
                source_type="中转副表",
                permissions=table_permission_set(read=True, write=True, create=True, replace=True),
                write_mode="覆盖当前循环项",
            )
        )

    elif node_type == "循环判断回跳":
        loop_id = config.get("loop_id", "") or "loop"
        tables.append(
            make_table_access_entry(
                "loop_result",
                config.get("result_table_name", "循环结果") or "循环结果",
                source_type="中转副表",
                permissions=table_permission_set(read=True, write=True, create=True, replace=True),
                write_mode="覆盖循环结果",
            )
        )
        tables.append(
            make_table_access_entry(
                "loop_queue",
                f"循环队列_{loop_id}",
                source_type="中转副表",
                permissions=table_permission_set(read=True, write=True, create=True, replace=True),
                write_mode="覆盖循环队列",
            )
        )

    elif node_type in ("条件跳转", "条件分支跳转"):
        source_type = str(config.get("source_type", "当前工作流表") or "当前工作流表").strip()
        if source_type == "SQLite表" and config.get("source_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "branch_source",
                config.get("source_table", ""),
                source_type="SQLite表",
            )
        elif source_type == "中转副表" and config.get("transit_table"):
            _append_read_only_entry(
                tables,
                make_table_access_entry,
                table_permission_set,
                "branch_source",
                config.get("transit_table", ""),
                source_type="中转副表",
            )

    return {"version": 1, "auto_generated": True, "tables": tables}
