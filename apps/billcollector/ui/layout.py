# -*- coding: utf-8 -*-
"""Shared layout for the daemon UI (M2 chunk D2).

A header with the app name and a left menu (Dashboard, Downloads,
Settings) that highlights the page currently open. Every protected page
calls :func:`build_layout` first, so all pages share one frame (locked
decision 14). The Downloads and Settings entries are registered from D2
even though the pages themselves land in D6 (register the menu items
now; do not hide the disabled ones).
"""

from nicegui import ui

MENU_ITEMS = (
    ("Dashboard", "/"),
    ("Downloads", "/downloads"),
    ("Settings", "/settings"),
)


def build_layout(active: str = "") -> None:
    """Render the shared header + left menu (call at the top of a page).

    ``active`` is the name of the menu entry for the current page; its
    item is highlighted."""
    with ui.header().classes("items-center bg-slate-800 text-white").mark("header"):
        ui.label("BillCollector").classes("text-lg font-bold")
    with ui.left_drawer(value=True).props("bordered").classes("bg-slate-100").mark("left-menu"):
        with ui.list().props("dense").classes("w-full"):
            for name, path in MENU_ITEMS:
                item = ui.item()
                if name == active:
                    item.classes("bg-blue-200")
                with item:
                    ui.link(name, path).classes("w-full text-inherit no-underline")
                item.mark(f"menu-{name.lower()}")
