# -*- coding: utf-8 -*-
"""Callback factories for the table-access editor window."""


def create_table_access_selection_callbacks(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    def current_node():
        return window.current_table_access_window_node(state)

    def current_table_entry():
        return window.current_table_access_window_table_entry(state)

    def refresh_field_tree():
        window.refresh_table_access_window_field_tree(state, field_section, field_tree)

    def refresh_node_tree():
        window.refresh_table_access_node_tree(node_tree, state)

    def refresh_table_tree(select_index=None):
        window.refresh_table_access_window_table_tree(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            select_index=select_index,
        )

    def on_node_selected(event=None, force=False):
        window.on_table_access_window_node_selected(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
            event=event,
            force=force,
        )

    def on_table_selected(event=None):
        window.on_table_access_window_table_selected(
            state,
            table_section,
            field_section,
            table_tree,
            field_tree,
            event=event,
        )

    def on_field_selected(event=None):
        window.on_table_access_window_field_selected(state, field_section, field_tree, event=event)

    return {
        "current_node": current_node,
        "current_table_entry": current_table_entry,
        "refresh_node_tree": refresh_node_tree,
        "refresh_table_tree": refresh_table_tree,
        "refresh_field_tree": refresh_field_tree,
        "on_node_selected": on_node_selected,
        "on_table_selected": on_table_selected,
        "on_field_selected": on_field_selected,
    }


def create_table_access_table_action_callbacks(
    window,
    win,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    def save_table_entry():
        window.save_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def add_table_entry():
        window.add_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
        )

    def delete_table_entry():
        window.delete_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def rebuild_default_access():
        window.rebuild_table_access_window_default_access(
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def check_all_permissions():
        window.check_table_access_window_permissions(win, status_var)

    def preview_impact():
        window.preview_table_access_window_impact(win, state)

    def apply_table_preset(event=None):
        window.apply_table_access_window_table_preset(table_section, event=event)

    return {
        "save_table_entry": save_table_entry,
        "add_table_entry": add_table_entry,
        "delete_table_entry": delete_table_entry,
        "rebuild_default_access": rebuild_default_access,
        "check_all_permissions": check_all_permissions,
        "preview_impact": preview_impact,
        "apply_table_preset": apply_table_preset,
    }


def create_table_access_field_action_callbacks(
    window,
    state,
    table_section,
    field_section,
    field_tree,
    status_var,
):
    def save_field_entry():
        window.save_table_access_window_field_entry(state, table_section, field_section, field_tree, status_var)

    def add_field_entry():
        window.add_table_access_window_field_entry(table_section, field_section, field_tree)

    def delete_field_entry():
        window.delete_table_access_window_field_entry(state, field_section, field_tree, status_var)

    def auto_match_fields():
        window.auto_match_table_access_window_fields(state, field_section, field_tree, status_var)

    def auto_match_fields_by_order():
        window.auto_match_table_access_window_fields_by_order(state, table_section, field_section, field_tree, status_var)

    def clear_fields():
        window.clear_table_access_window_fields(state, field_section, field_tree, status_var)

    return {
        "save_field_entry": save_field_entry,
        "add_field_entry": add_field_entry,
        "delete_field_entry": delete_field_entry,
        "auto_match_fields": auto_match_fields,
        "auto_match_fields_by_order": auto_match_fields_by_order,
        "clear_fields": clear_fields,
    }


def create_table_access_window_callbacks(
    window,
    win,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    selection_callbacks = create_table_access_selection_callbacks(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )
    table_callbacks = create_table_access_table_action_callbacks(
        window,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )
    field_callbacks = create_table_access_field_action_callbacks(
        window,
        state,
        table_section,
        field_section,
        field_tree,
        status_var,
    )
    callbacks = {}
    callbacks.update(selection_callbacks)
    callbacks.update(table_callbacks)
    callbacks.update(field_callbacks)
    return callbacks
