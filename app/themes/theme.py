"""Color palettes. Widgets never hardcode colors: they read the active ``Theme``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Theme:
    name: str
    is_dark: bool
    bg: str              # main content
    bg_sidebar: str      # sidebar & top bar
    bg_panel: str        # cards inside the content area
    bg_input: str        # text fields
    bg_elevated: str     # menus, dialogs, popups
    bg_hover: str
    bg_selected: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    accent_soft: str     # translucent accent for selections
    success: str
    info: str
    warning: str
    danger: str
    danger_hover: str
    syntax_key: str
    syntax_string: str
    syntax_number: str
    syntax_keyword: str
    syntax_punct: str
    syntax_variable: str
    methods: dict[str, str] = field(default_factory=dict)

    def method_color(self, method: str) -> str:
        return self.methods.get(method.upper(), self.text_muted)

    def status_color(self, status: int | None) -> str:
        if status is None:
            return self.danger
        if status < 300:
            return self.success
        if status < 400:
            return self.info
        if status < 500:
            return self.warning
        return self.danger

    def tokens(self) -> dict[str, str]:
        data = {k: v for k, v in asdict(self).items() if isinstance(v, str)}
        data.update({f"method_{k.lower()}": v for k, v in self.methods.items()})
        return data


DARK = Theme(
    name="dark",
    is_dark=True,
    bg="#15171c",
    bg_sidebar="#111317",
    bg_panel="#1a1d23",
    bg_input="#1f232a",
    bg_elevated="#20242c",
    bg_hover="#242932",
    bg_selected="#232c3d",
    border="#262a32",
    border_strong="#343a45",
    text="#e4e7ec",
    text_muted="#9aa2ae",
    text_faint="#6b7380",
    accent="#3b82f6",
    accent_hover="#4b8ef8",
    accent_pressed="#2f6fd6",
    accent_text="#ffffff",
    accent_soft="#1e3a66",
    success="#4cc38a",
    info="#5b9cf5",
    warning="#e3a347",
    danger="#ec6a6a",
    danger_hover="#f07b7b",
    syntax_key="#7cb3f5",
    syntax_string="#e9a978",
    syntax_number="#9fd37b",
    syntax_keyword="#c69af0",
    syntax_punct="#8b93a0",
    syntax_variable="#56c2d6",
    methods={
        "GET": "#4cc38a",
        "POST": "#5b9cf5",
        "PUT": "#e3a347",
        "PATCH": "#b48cf2",
        "DELETE": "#ec6a6a",
        "HEAD": "#56c2d6",
        "OPTIONS": "#9aa2ae",
    },
)

LIGHT = Theme(
    name="light",
    is_dark=False,
    bg="#ffffff",
    bg_sidebar="#f6f7f9",
    bg_panel="#fbfbfc",
    bg_input="#ffffff",
    bg_elevated="#ffffff",
    bg_hover="#eef0f3",
    bg_selected="#e5edfb",
    border="#e3e6ea",
    border_strong="#cfd4db",
    text="#1d2127",
    text_muted="#5d6571",
    text_faint="#8b929c",
    accent="#2563eb",
    accent_hover="#3572ee",
    accent_pressed="#1d4fc4",
    accent_text="#ffffff",
    accent_soft="#d6e3fb",
    success="#1f9d61",
    info="#2563eb",
    warning="#b7791f",
    danger="#d64545",
    danger_hover="#e05555",
    syntax_key="#1f5fbf",
    syntax_string="#b3541e",
    syntax_number="#2f8a3a",
    syntax_keyword="#8a3fd1",
    syntax_punct="#6b7380",
    syntax_variable="#0e8a9e",
    methods={
        "GET": "#1f9d61",
        "POST": "#2563eb",
        "PUT": "#b7791f",
        "PATCH": "#8a3fd1",
        "DELETE": "#d64545",
        "HEAD": "#0e8a9e",
        "OPTIONS": "#5d6571",
    },
)

THEMES = {"dark": DARK, "light": LIGHT}
