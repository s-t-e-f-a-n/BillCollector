# -*- coding: utf-8 -*-
"""Shared layout for the daemon UI (M2 chunk D2).

A flat header - app icon + name + version chip on the left, a
"Daemon active" pill (pulsing emerald dot) on the right - and a left
menu (Dashboard, Tasks, Recipes, Downloads, Settings - each with a
Material icon) that highlights the page currently open. Every protected
page calls :func:`build_layout` first, so all pages share one frame
(locked decision 14) and the dark theme (:func:`apply_theme`) applied
here.

The version chip's and daemon pill's hover tooltips carry the full
version string (and the scheduler state on the pill).
"""

from nicegui import ui

from .. import __version__
from .theme import apply_theme, pill

MENU_ITEMS = (
    ("Dashboard", "/", "dashboard"),
    ("Tasks", "/tasks", "list"),
    ("Recipes", "/recipes", "code"),
    ("Downloads", "/downloads", "download"),
    ("Settings", "/settings", "settings"),
)


def build_layout(active: str = "", daemon_running: bool = True) -> None:
    """Render the shared header + left menu (call at the top of a page).

    ``active`` is the name of the menu entry for the current page; its
    item is highlighted. ``daemon_running`` feeds the header pill's
    state (the scheduler's ``running`` flag where the page has it in
    scope); it defaults to ``True`` so pages without the scheduler keep
    the active pill.
    """
    apply_theme()

    with ui.header().classes(
            "items-center justify-between bg-slate-950 "
            "border-b border-slate-800 shadow-none").mark("header"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("receipt_long").classes("text-xl text-emerald-400")
            ui.label("BillCollector").classes(
                "text-lg font-semibold text-slate-100")
            ui.label(__version__).classes(
                "rounded bg-slate-800 px-1.5 py-0.5 font-mono "
                "text-[10px] text-slate-400").tooltip(__version__)
        with ui.element("div").classes(
                f"flex items-center gap-2 {pill('emerald' if daemon_running else 'slate')}") \
                .tooltip(
                    f"Scheduler {'active' if daemon_running else 'stopped'}"
                    f" - BillCollector v{__version__}"):
            ui.html('<span class="inline-block h-2 w-2 rounded-full '
                    'animate-pulse bg-emerald-500"></span>'
                    if daemon_running else
                    '<span class="inline-block h-2 w-2 rounded-full '
                    'bg-slate-600"></span>')
            ui.label("Daemon active" if daemon_running else "Daemon stopped")

    with ui.left_drawer(value=True).classes(
            "border-r border-slate-800 bg-slate-950").style(
                "width: 220px").mark("left-menu"):
        with ui.list().props("dense").classes("w-full p-1"):
            for name, path, icon in MENU_ITEMS:
                item = ui.item()
                if name == active:
                    item.classes(
                        "m-1 rounded-md border border-emerald-500/20 "
                        "bg-emerald-500/10 text-emerald-400")
                else:
                    item.classes(
                        "m-1 rounded-md text-slate-400 "
                        "hover:bg-slate-900 hover:text-slate-200")
                with item:
                    with ui.link(name, path).classes(
                            "w-full items-center gap-2 text-inherit "
                            "no-underline"):
                        ui.icon(icon).classes("text-xl")
                item.mark(f"menu-{name.lower()}")
