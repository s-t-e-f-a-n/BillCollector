# -*- coding: utf-8 -*-
"""Design tokens and dark-theme application for the daemon UI.

Dark is the app's only skin (no light mode, no toggle): a "fintech
precision" palette - near-black slate background, 1px slate borders, no
shadows, an emerald primary. All UI text stays English.

:func:`apply_theme` is called at the top of ``build_layout`` so every
protected page inherits the theme before any content renders; the public
``/login`` page is styled separately.

Fonts are system stacks only - no external font CDN (self-hosted NAS,
must work offline).
"""

from nicegui import ui

# ---- Design tokens ----------------------------------------------------------

BG = "#090d16"            # slate-950: body / header / drawer
SURFACE = "#0f172a"       # slate-900: cards, tables, panels
BORDER = "#1e293b"        # slate-800: 1px everywhere, no shadows
PRIMARY = "#10b981"       # emerald-500: buttons, active nav, links, success
PRIMARY_HOVER = "#059669"  # emerald-600
WARNING = "#f59e0b"       # amber-500: waiting, pending
DANGER = "#f43f5e"        # rose-500: failure, errors
RUNNING = "#0ea5e9"       # sky-500: running status
TEXT_PRIMARY = "#f1f5f9"  # slate-100
TEXT_SECONDARY = "#94a3b8"  # slate-400
TEXT_MUTED = "#64748b"    # slate-500

SANS_STACK = ('ui-sans-serif, system-ui, -apple-system, "Segoe UI", '
              "Roboto, sans-serif")
MONO_STACK = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'

# One head block per page: the body background/text, the two font stacks,
# the Quasar body background, and a thin dark scrollbar.
_HEAD_HTML = f"""
<style>
  html, body {{
    background: {BG};
    color: {TEXT_PRIMARY};
  }}
  body {{
    font-family: {SANS_STACK};
  }}
  .q-body {{
    background: {BG} !important;
  }}
  .font-mono {{
    font-family: {MONO_STACK} !important;
  }}
  ::-webkit-scrollbar {{
    width: 10px;
    height: 10px;
  }}
  ::-webkit-scrollbar-track {{
    background: {BG};
  }}
  ::-webkit-scrollbar-thumb {{
    background: {BORDER};
    border-radius: 5px;
  }}
  ::-webkit-scrollbar-thumb:hover {{
    background: #334155;
  }}
</style>
"""


def apply_theme() -> None:
    """Apply the dark theme to the current page.

    Call at the top of a page (before any other element) so the page's
    Quasar colors and dark mode are in place before the content renders.
    """
    ui.dark_mode().enable()
    ui.colors(
        primary=PRIMARY,
        positive=PRIMARY,
        negative=DANGER,
        warning=WARNING,
        info=RUNNING,
        dark=SURFACE,
        dark_page=BG,
    )
    ui.add_head_html(_HEAD_HTML)


def pill(hue: str, label: str = "") -> str:
    """Tailwind classes for the shared status pill.

    ``rounded-full px-2.5 py-0.5 text-xs font-medium`` plus a hue tint
    (``bg-{hue}-500/10 text-{hue}-400 border-{hue}-500/20``). ``label``
    names the pill for the caller's text; the returned string is the
    class list only.
    """
    return (f"rounded-full px-2.5 py-0.5 text-xs font-medium "
            f"bg-{hue}-500/10 text-{hue}-400 border border-{hue}-500/20")


def card() -> str:
    """Tailwind classes for a surface card (1px border, no shadow)."""
    return "bg-slate-900 border border-slate-800 rounded-lg p-4"


def kpi_card(title: str, value: str, sub: str = "",
             tooltip: str = "") -> ui.column:
    """Build one KPI card and return it.

    A surface card (1px border, no shadow) with an uppercase, letter-
    tracked label, a large mono value, and a muted sub-line. ``tooltip``
    (when given) is shown on hover. The value and sub labels are
    exposed as ``el.kpi_value`` / ``el.kpi_sub`` so a poll can update
    them with ``set_text`` without rebuilding the card.
    """
    with ui.column().classes(
            "w-full gap-1 rounded-lg border border-slate-800 bg-slate-900 "
            "p-4") as el:
        if tooltip:
            el.tooltip(tooltip)
        ui.label(title.upper()).classes(
            "text-[10px] font-semibold uppercase tracking-widest "
            "text-slate-500")
        el.kpi_value = ui.label(value).classes(
            "text-2xl font-mono text-slate-100")
        el.kpi_sub = ui.label(sub).classes("text-xs text-slate-400")
    return el


def set_kpi(card, value: str, sub: str = "") -> None:
    """Update a :func:`kpi_card`'s value and sub-line in place."""
    card.kpi_value.set_text(value)
    card.kpi_sub.set_text(sub)
