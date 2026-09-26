"""Main window: wires services, storage and widgets together.

Widgets emit intent signals (``new_request``, ``delete_request``...); this class
performs the operation through ``ProjectService`` and refreshes the views.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sys

from PySide6.QtCore import QProcess, QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMainWindow, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from app import APP_NAME
from app.i18n import current_language, resolve_language, tr, trn
from app.models.api_response import ApiResponse
from app.models.history import HistoryEntry
from app.models.settings import AppSettings
from app.network.errors import RequestError
from app.repositories import (
    HistoryRepository,
    ProjectLoadError,
    ProjectUiState,
    RecentProjectsRepository,
    SettingsRepository,
    UiStateRepository,
)
from app.services.curl_service import base_url_for, build_curl
from app.services.http_client_service import HttpClientService
from app.services.project_service import ProjectService, find_api_dir
from app.services.request_builder import PreparedRequest
from app.services.variable_service import VariableContext, suggest_variable_name, variable_text
from app.storage.database import Database
from app.themes.manager import ThemeManager
from app.ui.dialogs.base import BaseDialog, ChoiceDialog, ConfirmDialog, MessageDialog, TextInputDialog
from app.ui.dialogs.command_palette import CommandPalette, PaletteEntry
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.dialogs.openapi_dialog import OpenApiImportDialog
from app.ui.dialogs.project_dialogs import CreateProjectDialog, ProjectSettingsDialog
from app.ui.dialogs.request_dialogs import CollectionDialog, CurlImportDialog, NewRequestDialog
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.dialogs.variable_dialogs import SaveVariableDialog
from app.ui.dialogs.variables_window import EnvironmentsResult, VariablesWindow
from app.ui.helpers import Debouncer, button, label
from app.ui.widgets.empty_state import EditorEmptyState
from app.ui.widgets.home_screen import HomeScreen
from app.ui.widgets.request_editor import RequestEditor, curl_import_message
from app.ui.widgets.request_tabs import RequestTabs
from app.ui.widgets.sidebar import Sidebar
from app.ui.widgets.toast import Toast
from app.ui.widgets.top_bar import TopBar

log = logging.getLogger(__name__)

_GEOMETRY_KEY = "window.geometry"
_SPLIT_KEY = "editor.split"
_OBJECT_VIEW_KEY = "editor.object_view"


@dataclass
class AppContext:
    db: Database
    settings_repo: SettingsRepository
    recent: RecentProjectsRepository
    history: HistoryRepository
    ui_state: UiStateRepository
    settings: AppSettings


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.ctx = context
        self.theme = ThemeManager.instance()
        self.http = HttpClientService(lambda: self.ctx.settings.network)
        self.service: ProjectService | None = None
        self.environment: str | None = None
        self._variables_window: VariablesWindow | None = None
        self._dirty: set[str] = set()
        self._editor_split: list[int] = self.ctx.settings_repo.get(_SPLIT_KEY, []) or []

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 650)
        self._autosave = Debouncer(self.ctx.settings.autosave_delay_ms, self.flush_saves, self)
        self._ui_state_saver = Debouncer(600, self._save_ui_state, self)
        self._build_ui()
        self._build_shortcuts()
        self._saved_fade = QTimer(self)
        self._saved_fade.setSingleShot(True)
        self._saved_fade.timeout.connect(lambda: self._save_label.setText(""))
        self.theme.theme_changed.connect(lambda _: self._refresh_theme())
        self._refresh_theme()
        self._restore_geometry()
        self._refresh_recent()
        self._show_home()

    # ================================================================ construction

    def _build_ui(self) -> None:
        self.top_bar = TopBar()
        self.home = HomeScreen()
        self.sidebar = Sidebar()
        self.tabs = RequestTabs()
        self.empty_editor = EditorEmptyState()

        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.empty_editor)
        self.editor_stack.addWidget(self.tabs)

        self.workspace = QSplitter(Qt.Orientation.Horizontal)
        self.workspace.setHandleWidth(1)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.addWidget(self.sidebar)
        self.workspace.addWidget(self.editor_stack)
        self.workspace.setStretchFactor(1, 1)
        self.workspace.setSizes([260, 1000])
        self.workspace.splitterMoved.connect(lambda *_: self._ui_state_saver.trigger())

        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("MainStack")
        self.main_stack.addWidget(self.home)
        self.main_stack.addWidget(self.workspace)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.top_bar)
        layout.addWidget(self.main_stack, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)

        self._project_label = QLabel()
        self._save_label = QLabel()
        self.statusBar().addWidget(self._project_label, 1)
        self.statusBar().addPermanentWidget(self._save_label)
        self.statusBar().setSizeGripEnabled(False)

        # top bar
        tb = self.top_bar
        tb.open_project.connect(self.open_project_dialog)
        tb.create_project.connect(lambda: self.create_project_flow())
        tb.open_recent.connect(lambda path: self.open_folder(Path(path)))
        tb.close_project.connect(self.close_project)
        tb.edit_project.connect(self.edit_project)
        tb.reveal_folder.connect(self.reveal_folder)
        tb.reload_project.connect(self.reload_project)
        tb.environment_selected.connect(self.set_environment)
        tb.manage_environments.connect(lambda: self.manage_environments())
        tb.open_variables.connect(lambda: self.manage_environments())
        tb.open_history.connect(self.show_history)
        tb.open_settings.connect(self.show_settings)
        tb.open_palette.connect(self.show_command_palette)

        # home
        self.home.open_project.connect(self.open_project_dialog)
        self.home.create_project.connect(lambda: self.create_project_flow())
        self.home.open_recent.connect(lambda path: self.open_folder(Path(path)))
        self.home.remove_recent.connect(self._remove_recent)

        # sidebar
        sb = self.sidebar
        sb.request_activated.connect(lambda rid: self.open_request(rid))
        sb.new_request.connect(self.new_request)
        sb.new_collection.connect(self.new_collection)
        sb.new_environment.connect(lambda: self.manage_environments(create_new=True))
        sb.import_curl.connect(self.import_curl)
        sb.import_openapi.connect(self.import_openapi)
        sb.edit_collection.connect(self.edit_collection)
        sb.duplicate_collection.connect(self.duplicate_collection)
        sb.delete_collection.connect(self.delete_collection)
        sb.rename_request.connect(self.rename_request)
        sb.duplicate_request.connect(self.duplicate_request)
        sb.move_request.connect(self.move_request)
        sb.delete_request.connect(self.delete_request)
        sb.copy_curl.connect(self.copy_curl)
        sb.collapsed_changed.connect(self._ui_state_saver.trigger)

        # tabs
        self.tabs.close_requested.connect(self.close_request_tab)
        self.tabs.current_changed.connect(self._on_current_editor_changed)
        self.tabs.new_requested.connect(lambda: self.new_request(None))
        self.empty_editor.new_request.connect(lambda: self.new_request(None))

    def _build_shortcuts(self) -> None:
        def add(sequences: list[str | QKeySequence.StandardKey], handler, needs_project: bool = True) -> None:
            action = QAction(self)
            action.setShortcuts([QKeySequence(s) for s in sequences])
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(lambda: (handler() if (self.service or not needs_project) else None))
            self.addAction(action)

        add(["Ctrl+Return", "Ctrl+Enter"], self.send_current)
        add(["Ctrl+N"], lambda: self.new_request(None))
        add(["Ctrl+Shift+N"], self.new_collection)
        add(["Ctrl+L"], self.focus_url)
        add(["Ctrl+W"], self.close_current_tab)
        add(["Ctrl+Shift+F"], self.format_current)
        add(["Ctrl+K", "Ctrl+Shift+P"], self.show_command_palette)
        add(["Ctrl+O"], self.open_project_dialog, needs_project=False)
        add(["Ctrl+Shift+O"], lambda: self.create_project_flow(), needs_project=False)
        add(["Ctrl+S"], self.save_now)
        add(["Ctrl+,"], self.show_settings, needs_project=False)
        add(["Ctrl+H"], self.show_history)
        add(["Ctrl+E"], self.switch_environment_palette)
        add(["Ctrl+Shift+E"], lambda: self.manage_environments())
        add(["Ctrl+P"], self.sidebar.focus_search)
        add(["Ctrl+D"], self.duplicate_current)
        add(["Ctrl+Tab", "Ctrl+PgDown"], lambda: self.tabs.select_relative(1))
        add(["Ctrl+Shift+Tab", "Ctrl+PgUp"], lambda: self.tabs.select_relative(-1))

    # ================================================================ projects

    def open_project_dialog(self) -> None:
        start = str(self.service.root_dir.parent) if self.service else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, tr("Open backend project folder"), start)
        if chosen:
            self.open_folder(Path(chosen))

    def open_folder(self, folder: Path) -> None:
        if not folder.exists():
            MessageDialog.show_error(self, tr("Folder not found"), tr("{path} does not exist anymore.", path=folder))
            self.ctx.recent.remove(str(folder))
            self._refresh_recent()
            return
        api_dir = find_api_dir(folder)
        if api_dir is not None:
            self.load_project(api_dir)
            return
        if ConfirmDialog.ask(
            self, tr("No API Client configuration"),
            tr("This folder has no api-client/project.json:\n{path}\n\nDo you want to create it?", path=folder),
            tr("Create"), danger=False,
        ):
            self.create_project_flow(folder)

    def create_project_flow(self, folder: Path | None = None) -> None:
        values = CreateProjectDialog.ask(self, folder)
        if values is None:
            return
        root, name, base_url = values
        existing = find_api_dir(root)
        if existing is not None:
            self.load_project(existing)
            return
        try:
            service = ProjectService.create(root, name, base_url)
        except OSError as exc:
            MessageDialog.show_error(self, tr("Could not create project"),
                                     tr("Writing to {path} failed: {error}.", path=root, error=exc.strerror or exc))
            return
        self.load_project(service.api_dir)
        self.toast.show_message(tr("Project created"))

    def load_project(self, api_dir: Path) -> None:
        self._close_current_project()
        try:
            result = ProjectService.open(api_dir)
        except ProjectLoadError as exc:
            MessageDialog.show_error(self, tr("Could not open project"), exc.message,
                                     [tr("Fix the file (it is plain JSON) or restore it from Git, then try again.")])
            self._show_home()
            return
        except OSError as exc:
            MessageDialog.show_error(self, tr("Could not open project"), f"{api_dir}: {exc.strerror or exc}")
            self._show_home()
            return
        self.service = result.service
        state = self.ctx.ui_state.load(self.service.key)
        names = self.service.environment_names
        self.environment = state.environment if state.environment in names else self.service.default_environment()
        self.ctx.recent.touch(self.service.key, self.service.project.name)
        self._refresh_recent()

        self.top_bar.set_project(self.service.project.name)
        self._refresh_environments()
        self.sidebar.search.clear()
        self.sidebar.set_collections(self.service.collections, set(state.collapsed_collections))
        self.workspace.setSizes([max(200, state.sidebar_width), max(600, self.width() - state.sidebar_width)])
        if state.editor_split:
            self._editor_split = state.editor_split
        self.main_stack.setCurrentWidget(self.workspace)
        for request_id in state.open_request_ids:
            if self.service.find_request(request_id):
                self.open_request(request_id, activate=False)
        if state.active_request_id and self.tabs.activate(state.active_request_id):
            self.sidebar.select_request(state.active_request_id)
        self._update_editor_area()
        self._update_status()
        self.setWindowTitle(f"{self.service.project.name} — {APP_NAME}")
        if result.warnings:
            MessageDialog.show_warning(
                self, tr("Some files could not be loaded"),
                tr("These files are invalid and were skipped. They have not been modified; fix them and use "
                   "Reload from disk."), result.warnings,
            )

    def _close_current_project(self) -> None:
        if self.service is None:
            return
        self.flush_saves()
        self._save_ui_state()
        for editor in self.tabs.editors():
            self.tabs.remove(editor.request.id)
        self.service = None
        self.environment = None
        if self._variables_window is not None:
            self._variables_window.hide()

    def close_project(self) -> None:
        self._close_current_project()
        self._show_home()

    def _show_home(self) -> None:
        self.top_bar.set_project(None)
        self.main_stack.setCurrentWidget(self.home)
        self.setWindowTitle(APP_NAME)
        self._project_label.setText("")
        self._save_label.setText("")

    def edit_project(self) -> None:
        if self.service is None:
            return
        values = ProjectSettingsDialog.ask(self, self.service.project.name, self.service.project.base_url,
                                           self.service.api_dir)
        if values is None:
            return
        name, base_url = values
        if self._guard(lambda: self.service.update_project(name=name, base_url=base_url)):
            self.top_bar.set_project(self.service.project.name)
            self.ctx.recent.touch(self.service.key, self.service.project.name)
            self._refresh_recent()
            self._broadcast_context()
            self._sync_variables_window()
            self.setWindowTitle(f"{self.service.project.name} — {APP_NAME}")
            self.toast.show_message(tr("Project saved"))

    def reveal_folder(self) -> None:
        if self.service is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.service.api_dir)))

    def reload_project(self) -> None:
        if self.service is None:
            return
        self.flush_saves()
        try:
            warnings = self.service.reload()
        except ProjectLoadError as exc:
            MessageDialog.show_error(self, tr("Could not reload project"), exc.message)
            return
        for editor in self.tabs.editors():
            found = self.service.find_request(editor.request.id)
            if found is None:
                self.tabs.remove(editor.request.id)
            else:
                editor.load(found[1])
                self.tabs.update_request(found[1])
        self._refresh_structure()
        self._refresh_environments()
        self._broadcast_context()
        self._sync_variables_window()
        if warnings:
            MessageDialog.show_warning(self, tr("Some files could not be loaded"), tr("These files were skipped:"), warnings)
        else:
            self.toast.show_message(tr("Project reloaded"))

    def _refresh_recent(self) -> None:
        recent = self.ctx.recent.list(self.ctx.settings.recent_limit)
        self.home.set_recent(recent)
        self.top_bar.set_recent(recent)

    def _remove_recent(self, path: str) -> None:
        self.ctx.recent.remove(path)
        self._refresh_recent()

    def open_last_project_if_enabled(self) -> None:
        if not self.ctx.settings.open_last_project:
            return
        recent = self.ctx.recent.list(1)
        if recent:
            api_dir = find_api_dir(Path(recent[0].path))
            if api_dir is not None:
                self.load_project(api_dir)

    # ================================================================ environments

    def variable_context(self) -> VariableContext:
        if self.service is None:
            return VariableContext()
        return self.service.variable_context(self.environment)

    def _refresh_environments(self) -> None:
        if self.service is None:
            return
        envs = list(self.service.project.environments.values())
        self.top_bar.set_environments(envs, self.environment)
        if self._variables_window is not None:
            self._variables_window.set_active(self.environment)

    def set_environment(self, name: str) -> None:
        self.environment = name
        self._refresh_environments()
        self._broadcast_context()
        self._ui_state_saver.trigger()
        self._update_status()

    def _broadcast_context(self) -> None:
        context = self.variable_context()
        for editor in self.tabs.editors():
            editor.set_variable_context(context)

    def manage_environments(self, create_new: bool = False) -> None:
        """Open (or bring back) the floating variables window."""
        if self.service is None:
            return
        window = self._variables_window
        if window is None:
            window = self._variables_window = VariablesWindow(self)
            window.changed.connect(self._save_variables)
        if not window.isVisible():
            window.load(self.service.project, self.service.secrets, self.environment, self.environment)
        window.show()
        window.raise_()
        window.activateWindow()
        if create_new:
            window.add_environment()

    def _save_variables(self, result: EnvironmentsResult) -> None:
        if self.service is None:
            return
        ok = self._guard(lambda: self.service.save_environments(result.global_variables, result.global_secrets,
                                                                  result.environments))
        if not ok:
            return
        if self.environment not in self.service.environment_names:
            self.environment = self.service.default_environment()
        self._refresh_environments()
        self._broadcast_context()
        self._ui_state_saver.trigger()
        self._update_status()

    def _sync_variables_window(self) -> None:
        """Variables changed outside the window (reload, project settings, save from a response)."""
        window = self._variables_window
        if window is not None and window.isVisible() and self.service is not None:
            window.load(self.service.project, self.service.secrets, active=self.environment)

    def save_response_variable(self, path: tuple, value: object) -> None:
        """Response "Object" tab → right click → Save as variable…"""
        if self.service is None:
            return
        text = variable_text(value)
        result = SaveVariableDialog.ask(self, self.service.project, self.service.secrets, self.environment,
                                        suggest_variable_name(path), text)
        if result is None:
            return
        if not self._guard(lambda: self.service.set_variable(result.environment, result.name, text,
                                                             secret=result.secret)):
            return
        self._broadcast_context()
        self._sync_variables_window()
        scope = (self.service.project.environments[result.environment].display_name
                 if result.environment else tr("Globals"))
        self.toast.show_message(tr("Saved {var} in {scope}", var="{{" + result.name + "}}", scope=scope))

    def switch_environment_palette(self) -> None:
        if self.service is None:
            return
        entries = [
            PaletteEntry(env.display_name, lambda n=env.name: self.set_environment(n),
                         subtitle=tr("active") if env.name == self.environment else "")
            for env in self.service.project.environments.values()
        ]
        entries.append(PaletteEntry(tr("Manage environments…"), self.manage_environments))
        CommandPalette.run(self, entries, tr("Switch environment…"))

    # ================================================================ requests & tabs

    def open_request(self, request_id: str, *, activate: bool = True, is_new: bool = False) -> None:
        if self.service is None:
            return
        if self.tabs.activate(request_id):
            self.sidebar.select_request(request_id)
            return
        found = self.service.find_request(request_id)
        if found is None:
            self.toast.show_message(tr("That request no longer exists"))
            return
        editor = RequestEditor(found[1], self.http, self.variable_context)
        editor.set_font_size(self.ctx.settings.editor_font_size)
        editor.changed.connect(self._on_request_edited)
        editor.finished.connect(self._record_history)
        editor.duplicate_requested.connect(self.duplicate_request)
        editor.copy_curl_requested.connect(self.copy_curl)
        editor.notify.connect(self.toast.show_message)
        editor.save_variable_requested.connect(self.save_response_variable)
        editor.splitter_moved.connect(self._on_editor_split_moved)
        editor.set_object_view_enabled(bool(self.ctx.settings_repo.get(_OBJECT_VIEW_KEY, False)))
        editor.object_view_toggled.connect(self._on_object_view_toggled)
        if self._editor_split:
            editor.set_splitter_sizes(self._editor_split)
        else:
            QTimer.singleShot(0, lambda e=editor: self._default_split(e))
        editor.open_default_tab()
        self.tabs.add_editor(editor, activate=activate or self.tabs.count() == 0)
        self._update_editor_area()
        if activate:
            self.sidebar.select_request(request_id)
        if is_new:
            editor.focus_url(select_all=False)
        self._ui_state_saver.trigger()

    def _default_split(self, editor: RequestEditor) -> None:
        total = sum(editor.splitter_sizes()) or 700
        editor.set_splitter_sizes([total // 2, total - total // 2])

    def _on_editor_split_moved(self, sizes: list[int]) -> None:
        self._editor_split = sizes
        for editor in self.tabs.editors():
            if editor is not self.tabs.current_editor():
                editor.set_splitter_sizes(sizes)
        self.ctx.settings_repo.set(_SPLIT_KEY, sizes)
        self._ui_state_saver.trigger()

    def _on_object_view_toggled(self, enabled: bool) -> None:
        for editor in self.tabs.editors():
            editor.set_object_view_enabled(enabled)
        self.ctx.settings_repo.set(_OBJECT_VIEW_KEY, enabled)

    def _on_current_editor_changed(self, editor: RequestEditor | None) -> None:
        if editor is not None:
            if self._editor_split:
                editor.set_splitter_sizes(self._editor_split)
            self.sidebar.select_request(editor.request.id)
        else:
            self.sidebar.select_request(None)
        self._ui_state_saver.trigger()

    def close_request_tab(self, request_id: str) -> None:
        if request_id in self._dirty:
            self.flush_saves()
        self.tabs.remove(request_id)
        self._update_editor_area()
        self._ui_state_saver.trigger()

    def close_current_tab(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            self.close_request_tab(editor.request.id)

    def _update_editor_area(self) -> None:
        has_tabs = self.tabs.count() > 0
        self.editor_stack.setCurrentWidget(self.tabs if has_tabs else self.empty_editor)
        if not has_tabs and self.service is not None:
            self.empty_editor.set_has_requests(bool(self.service.all_requests()))

    def send_current(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            editor.send()

    def focus_url(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            editor.focus_url()

    def format_current(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None and editor.format_body():
            self.toast.show_message(tr("JSON formatted"), 1200)

    def duplicate_current(self) -> None:
        editor = self.tabs.current_editor()
        if editor is not None:
            self.duplicate_request(editor.request.id)

    # ================================================================ autosave

    def _on_request_edited(self, request_id: str) -> None:
        if self.service is None:
            return
        found = self.service.find_request(request_id)
        if found is not None:
            self.sidebar.update_request(found[1])
            self.tabs.update_request(found[1])
        self._dirty.add(request_id)
        self.tabs.set_dirty(request_id, True)
        if self.ctx.settings.autosave:
            self._autosave.trigger()
            self._set_save_status(tr("Editing…"))
        else:
            self._set_save_status(tr("Unsaved changes — Ctrl+S to save"), sticky=True)

    def save_now(self) -> None:
        if self._dirty:
            self.flush_saves()
        else:
            self._set_save_status(tr("All changes saved"))

    def flush_saves(self) -> None:
        if self.service is None or not self._dirty:
            return
        self._autosave.cancel()
        pending, self._dirty = self._dirty, set()
        self._set_save_status(tr("Saving…"), sticky=True)
        failures: list[str] = []
        for request_id in pending:
            try:
                self.service.save_request(request_id)
                self.tabs.set_dirty(request_id, False)
            except OSError as exc:
                self._dirty.add(request_id)
                failures.append(f"{exc.filename or request_id}: {exc.strerror or exc}")
        if failures:
            self._set_save_status(tr("Save failed"), sticky=True)
            MessageDialog.show_error(self, tr("Could not save changes"), tr("Your edits are kept in memory. "
                                     "Check the file permissions and press Ctrl+S to retry."), failures)
        else:
            self._set_save_status(tr("Saved"))

    def _set_save_status(self, text: str, sticky: bool = False) -> None:
        self._save_label.setText(text)
        if sticky or text == tr("Editing…"):
            self._saved_fade.stop()
        else:
            self._saved_fade.start(1800)

    # ================================================================ CRUD

    def _guard(self, operation) -> bool:
        """Run a persistence operation, turning disk errors into a readable dialog."""
        try:
            operation()
            return True
        except OSError as exc:
            MessageDialog.show_error(self, tr("Could not write to disk"), f"{exc.filename or ''} {exc.strerror or exc}")
        except KeyError as exc:
            self.toast.show_message(str(exc).strip("'\""))
        return False

    def _refresh_structure(self) -> None:
        if self.service is None:
            return
        self.sidebar.set_collections(self.service.collections)
        self._update_editor_area()
        self._update_status()
        self._ui_state_saver.trigger()

    def new_request(self, collection_id: str | None) -> None:
        if self.service is None:
            return
        self.flush_saves()
        collections = self.service.collections
        selected = collection_id or self.sidebar.selected_collection_id()
        if selected is None and self.tabs.current_editor() is not None:
            found = self.service.find_request(self.tabs.current_editor().request.id)
            selected = found[0].id if found else None
        result = NewRequestDialog.ask(self, collections, selected)
        if result is None:
            return
        try:
            target = result.collection_id
            if target is None:
                target = self.service.create_collection(result.new_collection_name).id
            request = self.service.create_request(target, result.name, result.method, result.url or None)
        except OSError as exc:
            MessageDialog.show_error(self, tr("Could not create request"), str(exc))
            return
        self._refresh_structure()
        self.open_request(request.id, is_new=True)

    def import_curl(self) -> None:
        """Paste a cURL command, then choose name and collection like a new request."""
        if self.service is None:
            return
        self.flush_saves()
        imported = CurlImportDialog.ask(self, base_url_for(self.variable_context()))
        if imported is None:
            return
        selected = self.sidebar.selected_collection_id()
        result = NewRequestDialog.ask(self, self.service.collections, selected, initial=imported.request)
        if result is None:
            return
        try:
            target = result.collection_id
            if target is None:
                target = self.service.create_collection(result.new_collection_name).id
            request = self.service.create_request(target, result.name, result.method, result.url or None)
            imported.request.method, imported.request.url = request.method, request.url
            imported.apply_to(request)
            self.service.save_request(request.id)
        except OSError as exc:
            MessageDialog.show_error(self, tr("Could not create request"), str(exc))
            return
        self._refresh_structure()
        self.open_request(request.id)
        self.toast.show_message(curl_import_message(imported))

    def import_openapi(self) -> None:
        if self.service is None:
            return
        self.flush_saves()
        endpoints = OpenApiImportDialog.ask(self, self.http, self.variable_context(), self.service.collections,
                                            self.service.root_dir)
        if not endpoints:
            return
        holder = {}
        if not self._guard(lambda: holder.setdefault("summary", self.service.import_endpoints(endpoints))):
            return
        summary = holder["summary"]
        self._refresh_structure()
        self.toast.show_message(trn("Imported {n} request", "Imported {n} requests", summary.requests))

    def new_collection(self) -> None:
        if self.service is None:
            return
        values = CollectionDialog.ask(self)
        if values is None:
            return
        name, base_path = values
        holder = {}
        if self._guard(lambda: holder.setdefault("c", self.service.create_collection(name, base_path))):
            self._refresh_structure()
            self.toast.show_message(tr("Collection “{name}” created", name=holder["c"].name))

    def edit_collection(self, collection_id: str) -> None:
        if self.service is None or (collection := self.service.collection(collection_id)) is None:
            return
        values = CollectionDialog.ask(self, collection)
        if values is None:
            return
        name, base_path = values
        self.flush_saves()
        if self._guard(lambda: self.service.update_collection(collection_id, name=name, base_path=base_path)):
            self._refresh_structure()
            self.toast.show_message(tr("Collection saved"))

    def duplicate_collection(self, collection_id: str) -> None:
        if self.service is None:
            return
        self.flush_saves()
        if self._guard(lambda: self.service.duplicate_collection(collection_id)):
            self._refresh_structure()
            self.toast.show_message(tr("Collection duplicated"))

    def delete_collection(self, collection_id: str) -> None:
        if self.service is None or (collection := self.service.collection(collection_id)) is None:
            return
        count = len(collection.requests)
        if count:
            message = trn("“{name}” and its {n} request will be permanently removed ({file} is deleted).",
                          "“{name}” and its {n} requests will be permanently removed ({file} is deleted).",
                          count, name=collection.name, file=collection.file_name)
        else:
            message = tr("“{name}” will be permanently removed ({file} is deleted).",
                         name=collection.name, file=collection.file_name)
        if not ConfirmDialog.ask(self, tr("Delete collection?"), message):
            return
        self.flush_saves()
        request_ids = [r.id for r in collection.requests]
        if self._guard(lambda: self.service.delete_collection(collection_id)):
            for request_id in request_ids:
                self.tabs.remove(request_id)
            self._refresh_structure()
            self.toast.show_message(tr("Collection deleted"))

    def rename_request(self, request_id: str) -> None:
        if self.service is None or (found := self.service.find_request(request_id)) is None:
            return
        name = TextInputDialog.ask(self, tr("Rename request"), tr("Name"), found[1].name, tr("Rename"))
        if not name:
            return
        self.flush_saves()
        if self._guard(lambda: self.service.rename_request(request_id, name)):
            self.sidebar.update_request(found[1])
            self.tabs.update_request(found[1])

    def duplicate_request(self, request_id: str) -> None:
        if self.service is None:
            return
        self.flush_saves()
        holder = {}
        if self._guard(lambda: holder.setdefault("r", self.service.duplicate_request(request_id))):
            self._refresh_structure()
            self.open_request(holder["r"].id)
            self.toast.show_message(tr("Request duplicated"))

    def move_request(self, request_id: str) -> None:
        if self.service is None or (found := self.service.find_request(request_id)) is None:
            return
        options = [(c.id, c.name) for c in self.service.collections]
        target = ChoiceDialog.ask(self, tr("Move request"), tr("Move “{name}” to", name=found[1].name), options, found[0].id, tr("Move"))
        if target is None or target == found[0].id:
            return
        self.flush_saves()
        if self._guard(lambda: self.service.move_request(request_id, target)):
            self._refresh_structure()
            self.sidebar.select_request(request_id)
            self.toast.show_message(tr("Request moved"))

    def delete_request(self, request_id: str) -> None:
        if self.service is None or (found := self.service.find_request(request_id)) is None:
            return
        if not ConfirmDialog.ask(self, tr("Delete request?"), tr("“{name}” will be permanently removed.", name=found[1].name)):
            return
        self._dirty.discard(request_id)
        self.tabs.remove(request_id)
        self.flush_saves()
        if self._guard(lambda: self.service.delete_request(request_id)):
            self._refresh_structure()
            self.toast.show_message(tr("Request deleted"))

    # ================================================================ copy as cURL

    def copy_curl(self, request_id: str) -> None:
        if self.service is None or (found := self.service.find_request(request_id)) is None:
            return
        try:
            prepared = self.http.prepare(found[1], self.variable_context())
        except RequestError as error:
            MessageDialog.show_error(self, tr("Cannot build cURL command"), error.message, [error.hint] if error.hint else [])
            return
        mask = True
        if prepared.contains_secrets:
            choice = self._ask_curl_secrets()
            if choice is None:
                return
            mask = choice == "masked"
        QGuiApplication.clipboard().setText(build_curl(prepared, mask_secrets=mask))
        self.toast.show_message(tr("cURL copied (secrets masked)") if mask and prepared.contains_secrets
                                else tr("cURL copied"))

    def _ask_curl_secrets(self) -> str | None:
        dialog = BaseDialog(self, tr("This request contains credentials"), width=440)
        dialog.content.addWidget(label(
            tr("The command includes an Authorization header or secret variables. Copy it with the values "
               "masked (safe to share), or include them?"), "DialogMessage", wrap=True))
        choice: dict[str, str] = {}
        include = button(tr("Include secrets"), on_click=lambda: (choice.setdefault("v", "full"), dialog.accept()))
        dialog.buttons.insertWidget(1, include)
        dialog.ok_button.setText(tr("Copy masked"))
        dialog.ok_button.clicked.disconnect()
        dialog.ok_button.clicked.connect(lambda: (choice.setdefault("v", "masked"), dialog.accept()))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return choice.get("v", "masked")

    # ================================================================ history

    def _record_history(self, request_id: str, prepared: PreparedRequest, outcome: ApiResponse | RequestError) -> None:
        if self.service is None:
            return
        found = self.service.find_request(request_id)
        entry = HistoryEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            method=prepared.method,
            url=prepared.masked_url,
            status_code=outcome.status_code if isinstance(outcome, ApiResponse) else None,
            elapsed_ms=outcome.elapsed_ms if isinstance(outcome, ApiResponse) else None,
            size_bytes=outcome.size_bytes if isinstance(outcome, ApiResponse) else None,
            error="" if isinstance(outcome, ApiResponse) else outcome.title,
            project_path=self.service.key,
            request_id=request_id,
            request_name=found[1].name if found else "",
        )
        try:
            self.ctx.history.add(entry, keep_last=self.ctx.settings.history_limit)
        except Exception:
            log.exception("Could not store history entry")

    def show_history(self) -> None:
        if self.service is None:
            return
        key = self.service.key
        dialog = HistoryDialog(self, self.ctx.history.list(key, self.ctx.settings.history_limit),
                               lambda: self.ctx.history.clear(key))
        dialog.open_request.connect(lambda rid: self.open_request(rid))
        dialog.exec()

    # ================================================================ settings & palette

    def show_settings(self) -> None:
        updated = SettingsDialog.ask(self, self.ctx.settings)
        if updated is None:
            return
        theme_changed = updated.theme != self.theme.preference
        language_changed = resolve_language(updated.language) != current_language()
        self.ctx.settings = updated
        self.ctx.settings_repo.save(updated)
        self._autosave.set_delay(updated.autosave_delay_ms)
        if theme_changed:
            self.theme.apply(updated.theme, editor_font_size=updated.editor_font_size)
        for editor in self.tabs.editors():
            editor.set_font_size(updated.editor_font_size)
        if updated.autosave and self._dirty:
            self.flush_saves()
        self._refresh_recent()
        self.toast.show_message(tr("Settings saved"))
        if language_changed and ConfirmDialog.ask(
            self, tr("Restart required"), tr("The new language will be applied after restarting API Client."),
            tr("Restart now"), danger=False, cancel_text=tr("Later"),
        ):
            self.restart()

    def restart(self) -> None:
        """Relaunch the application (used to apply a new language)."""
        if not self.close():
            return
        arguments = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, arguments)
        QApplication.quit()

    def show_command_palette(self) -> None:
        entries: list[PaletteEntry] = []
        if self.service is not None:
            for collection, request in self.service.all_requests():
                entries.append(PaletteEntry(request.name, lambda rid=request.id: self.open_request(rid),
                                            subtitle=f"{collection.name}  ·  {request.url}",
                                            method=request.method.value))
            entries += [
                PaletteEntry(tr("New Request"), lambda: self.new_request(None), shortcut="Ctrl+N"),
                PaletteEntry(tr("New Collection"), self.new_collection, shortcut="Ctrl+Shift+N"),
                PaletteEntry(tr("Import cURL…"), self.import_curl),
                PaletteEntry(tr("Import OpenAPI…"), self.import_openapi),
                PaletteEntry(tr("New Environment"), lambda: self.manage_environments(create_new=True)),
                PaletteEntry(tr("Switch Environment"), self.switch_environment_palette, shortcut="Ctrl+E"),
                PaletteEntry(tr("Manage Environments"), self.manage_environments, shortcut="Ctrl+Shift+E"),
                PaletteEntry(tr("Format JSON"), self.format_current, shortcut="Ctrl+Shift+F"),
                PaletteEntry(tr("Open History"), self.show_history, shortcut="Ctrl+H"),
                PaletteEntry(tr("Project Settings"), self.edit_project),
                PaletteEntry(tr("Reload Project from Disk"), self.reload_project),
                PaletteEntry(tr("Close Project"), self.close_project),
            ]
        entries += [
            PaletteEntry(tr("Open Project"), self.open_project_dialog, shortcut="Ctrl+O"),
            PaletteEntry(tr("Create Project"), lambda: self.create_project_flow(), shortcut="Ctrl+Shift+O"),
            PaletteEntry(tr("Settings"), self.show_settings, shortcut="Ctrl+,"),
        ]
        CommandPalette.run(self, entries)

    # ================================================================ state & chrome

    def _update_status(self) -> None:
        if self.service is None:
            self._project_label.setText("")
            return
        collections = self.service.collections
        requests = sum(len(c.requests) for c in collections)
        location = str(self.service.api_dir)
        home = str(Path.home())
        if location.startswith(home):
            location = "~" + location[len(home):]
        self._project_label.setText(
            f"{location}   ·   {trn('{n} collection', '{n} collections', len(collections))}"
            f"   ·   {trn('{n} request', '{n} requests', requests)}"
        )

    def _save_ui_state(self) -> None:
        if self.service is None:
            return
        current = self.tabs.current_editor()
        sizes = self.workspace.sizes()
        state = ProjectUiState(
            open_request_ids=[e.request.id for e in self.tabs.editors()],
            active_request_id=current.request.id if current else None,
            environment=self.environment,
            collapsed_collections=sorted(self.sidebar.collapsed_ids()),
            sidebar_width=sizes[0] if sizes and sizes[0] > 0 else 260,
            editor_split=self._editor_split,
        )
        try:
            self.ctx.ui_state.save(self.service.key, state)
        except Exception:
            log.exception("Could not save UI state")

    def _restore_geometry(self) -> None:
        geometry = self.ctx.settings_repo.get(_GEOMETRY_KEY)
        if isinstance(geometry, str):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        else:
            self.resize(1320, 840)

    def _refresh_theme(self) -> None:
        self.top_bar.refresh_theme()
        self.sidebar.refresh_theme()
        self.tabs.refresh_theme()
        self.home.refresh_theme()
        self.empty_editor.refresh_theme()
        self._refresh_environments()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.flush_saves()
        if self._dirty and not ConfirmDialog.ask(
            self, tr("Quit without saving?"), tr("Some changes could not be written to disk."), tr("Quit anyway")
        ):
            event.ignore()
            return
        self._save_ui_state()
        for editor in self.tabs.editors():
            editor.shutdown()
        self.ctx.settings_repo.set(_GEOMETRY_KEY, bytes(self.saveGeometry().toBase64()).decode("ascii"))
        event.accept()
