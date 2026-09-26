from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QMenu,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.models.api_request import ApiRequest
from app.models.collection import Collection
from app.themes.manager import current_theme
from app.ui import icons
from app.ui.helpers import apply_icon, button, hbox, icon_button, label, vbox

ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_ID = Qt.ItemDataRole.UserRole + 2
ROLE_METHOD = Qt.ItemDataRole.UserRole + 3
ROLE_URL = Qt.ItemDataRole.UserRole + 4
ROLE_COUNT = Qt.ItemDataRole.UserRole + 5
KIND_COLLECTION, KIND_REQUEST = "collection", "request"


class _FilterModel(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._terms: list[str] = []
        self.setRecursiveFilteringEnabled(True)

    def set_query(self, query: str) -> None:
        self._terms = query.lower().split()
        self.invalidateFilter()

    @property
    def active(self) -> bool:
        return bool(self._terms)

    def _matches(self, text: str) -> bool:
        return all(term in text for term in self._terms)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        if not self._terms:
            return True
        model = self.sourceModel()
        index = model.index(row, 0, parent)
        name = (index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
        if index.data(ROLE_KIND) == KIND_COLLECTION:
            return self._matches(name)
        collection = (parent.data(Qt.ItemDataRole.DisplayRole) or "").lower()
        haystack = " ".join([name, (index.data(ROLE_METHOD) or "").lower(), (index.data(ROLE_URL) or "").lower(),
                             collection])
        return self._matches(haystack)


class _TreeDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), 32 if index.data(ROLE_KIND) == KIND_COLLECTION else 30)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        theme = current_theme()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 1, 0, -1)
        is_collection = index.data(ROLE_KIND) == KIND_COLLECTION
        selected = bool(option.state & QStyle.StateFlag.State_Selected) and not is_collection
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.bg_selected if selected else theme.bg_hover))
            painter.drawRoundedRect(rect, 6, 6)
        if selected:
            painter.setBrush(QColor(theme.accent))
            painter.drawRoundedRect(QRect(rect.left(), rect.top() + 5, 3, rect.height() - 10), 1.5, 1.5)

        font = QFont(option.font)
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if is_collection:
            expanded = bool(option.state & QStyle.StateFlag.State_Open)
            x = rect.left() + 6
            center_y = rect.center().y()
            painter.drawPixmap(x, center_y - 6, icons.pixmap("chevron-down" if expanded else "chevron-right",
                                                              theme.text_faint, 12, 2.0))
            painter.drawPixmap(x + 18, center_y - 8, icons.pixmap("folder-open" if expanded else "folder",
                                                                   theme.text_muted, 16))
            count = str(index.data(ROLE_COUNT) or 0)
            small = QFont(font)
            small.setPixelSize(11)
            painter.setFont(small)
            painter.setPen(QColor(theme.text_faint))
            count_rect = QRect(rect.right() - 40, rect.top(), 32, rect.height())
            painter.drawText(count_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, count)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(theme.text))
            text_rect = QRect(x + 42, rect.top(), count_rect.left() - x - 48, rect.height())
            elided = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        else:
            method = index.data(ROLE_METHOD) or "GET"
            color = QColor(theme.method_color(method))
            badge = QRect(rect.left() + 26, rect.center().y() - 9, 52, 18)
            fill = QColor(color)
            fill.setAlpha(34)
            painter.setBrush(fill)
            border = QColor(color)
            border.setAlpha(80)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(badge, 4, 4)
            badge_font = QFont(font)
            badge_font.setPixelSize(10)
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(color)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, method)
            painter.setFont(font)
            painter.setPen(QColor(theme.text if selected or hovered else theme.text_muted))
            text_rect = QRect(badge.right() + 10, rect.top(), rect.right() - badge.right() - 16, rect.height())
            elided = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        painter.restore()


class _Tree(QTreeView):
    delete_pressed = Signal(QModelIndex)
    rename_pressed = Signal(QModelIndex)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        index = self.currentIndex()
        if event.key() == Qt.Key.Key_Delete and index.isValid():
            self.delete_pressed.emit(index)
            return
        if event.key() == Qt.Key.Key_F2 and index.isValid():
            self.rename_pressed.emit(index)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and index.isValid():
            self.activated.emit(index)
            return
        super().keyPressEvent(event)


class Sidebar(QWidget):
    request_activated = Signal(str)
    new_request = Signal(object)      # collection id or None
    new_collection = Signal()
    new_environment = Signal()
    import_curl = Signal()
    edit_collection = Signal(str)
    duplicate_collection = Signal(str)
    delete_collection = Signal(str)
    rename_request = Signal(str)
    duplicate_request = Signal(str)
    move_request = Signal(str)
    delete_request = Signal(str)
    copy_curl = Signal(str)
    collapsed_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(200)
        self._restoring = False

        self.new_button = button(tr("New"), "primary", icon_name="plus")
        self.new_button.setMinimumHeight(34)
        new_menu = QMenu(self.new_button)
        new_menu.addAction(tr("New Request"), lambda: self.new_request.emit(None))
        new_menu.addAction(tr("New Collection"), self.new_collection.emit)
        new_menu.addAction(tr("New Environment"), self.new_environment.emit)
        new_menu.addSeparator()
        new_menu.addAction(tr("Import cURL…"), self.import_curl.emit)
        self.new_button.setMenu(new_menu)

        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText(tr("Search requests..."))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        self._search_icon = QLabel(self.search)
        self._search_icon.move(10, 9)

        self._add_collection = icon_button("plus", tr("New collection (Ctrl+Shift+N)"), size=14,
                                           on_click=self.new_collection.emit)

        self.model = QStandardItemModel(self)
        self.proxy = _FilterModel()
        self.proxy.setSourceModel(self.model)
        self.tree = _Tree()
        self.tree.setObjectName("CollectionTree")
        self.tree.setModel(self.proxy)
        self.tree.setItemDelegate(_TreeDelegate(self.tree))
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setMouseTracking(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_menu)
        self.tree.clicked.connect(self._on_clicked)
        self.tree.activated.connect(self._on_activated)
        self.tree.expanded.connect(self._on_expand_changed)
        self.tree.collapsed.connect(self._on_expand_changed)
        self.tree.delete_pressed.connect(self._on_delete_key)
        self.tree.rename_pressed.connect(self._on_rename_key)

        empty_collections = QWidget()
        empty_collections.setObjectName("SidebarEmpty")
        empty_collections.setLayout(vbox(
            16, label(tr("No collections yet"), "EmptyTitle"),
            label(tr("Group the endpoints of a controller, e.g. Productos → /api/productos."), "Hint", wrap=True),
            4, button(tr("Create collection"), "link", icon_name="plus", on_click=self.new_collection.emit), None,
            spacing=6, margins=(14, 0, 14, 0),
        ))
        no_results = QWidget()
        no_results.setLayout(vbox(16, label(tr("No matching requests"), "Muted"), None, margins=(14, 0, 14, 0)))
        self.body = QStackedWidget()
        self.body.addWidget(self.tree)
        self.body.addWidget(empty_collections)
        self.body.addWidget(no_results)

        header = hbox(label(tr("COLLECTIONS"), "SectionLabel"), None, self._add_collection, margins=(14, 0, 8, 0))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 8)
        layout.setSpacing(0)
        layout.addLayout(vbox(self.new_button, self.search, spacing=8, margins=(12, 0, 12, 0)))
        layout.addSpacing(16)
        layout.addLayout(header)
        layout.addSpacing(6)
        layout.addWidget(self.body, 1)
        self.refresh_theme()

    # -- data -----------------------------------------------------------------------

    def set_collections(self, collections: list[Collection], collapsed: set[str] | None = None) -> None:
        if collapsed is None:
            collapsed = self.collapsed_ids()
        selected = self.selected_request_id()
        self._restoring = True
        self.model.clear()
        for collection in collections:
            parent = QStandardItem(collection.name)
            parent.setData(KIND_COLLECTION, ROLE_KIND)
            parent.setData(collection.id, ROLE_ID)
            parent.setData(len(collection.requests), ROLE_COUNT)
            parent.setToolTip(collection.base_path or collection.name)
            for request in collection.requests:
                parent.appendRow(self._request_item(request))
            self.model.appendRow(parent)
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            self.tree.setExpanded(index, self.proxy.active or index.data(ROLE_ID) not in collapsed)
        self._restoring = False
        if selected:
            self.select_request(selected)
        self._update_body()

    def _request_item(self, request: ApiRequest) -> QStandardItem:
        item = QStandardItem(request.name)
        item.setData(KIND_REQUEST, ROLE_KIND)
        item.setData(request.id, ROLE_ID)
        item.setData(request.method.value, ROLE_METHOD)
        item.setData(request.url, ROLE_URL)
        item.setToolTip(f"{request.method.value}  {request.url}")
        return item

    def update_request(self, request: ApiRequest) -> None:
        item = self._find_item(request.id)
        if item is None:
            return
        if item.text() != request.name:
            item.setText(request.name)
        if item.data(ROLE_METHOD) != request.method.value:
            item.setData(request.method.value, ROLE_METHOD)
        if item.data(ROLE_URL) != request.url:
            item.setData(request.url, ROLE_URL)
            item.setToolTip(f"{request.method.value}  {request.url}")

    def _find_item(self, request_id: str) -> QStandardItem | None:
        for row in range(self.model.rowCount()):
            parent = self.model.item(row)
            for child_row in range(parent.rowCount()):
                child = parent.child(child_row)
                if child.data(ROLE_ID) == request_id:
                    return child
        return None

    def select_request(self, request_id: str | None) -> None:
        if request_id is None:
            self.tree.clearSelection()
            return
        item = self._find_item(request_id)
        if item is None:
            return
        index = self.proxy.mapFromSource(item.index())
        if index.isValid():
            self.tree.setExpanded(index.parent(), True)
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)

    def selected_request_id(self) -> str | None:
        index = self.tree.currentIndex()
        return index.data(ROLE_ID) if index.isValid() and index.data(ROLE_KIND) == KIND_REQUEST else None

    def selected_collection_id(self) -> str | None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return None
        if index.data(ROLE_KIND) == KIND_REQUEST:
            index = index.parent()
        return index.data(ROLE_ID)

    def collapsed_ids(self) -> set[str]:
        if self.proxy.active:
            return getattr(self, "_collapsed_before_search", set())
        collapsed = set()
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            if not self.tree.isExpanded(index):
                collapsed.add(index.data(ROLE_ID))
        return collapsed

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # -- events ---------------------------------------------------------------------

    def _on_search(self, text: str) -> None:
        if text and not self.proxy.active:
            self._collapsed_before_search = self.collapsed_ids()
        self.proxy.set_query(text)
        self._restoring = True
        if self.proxy.active:
            self.tree.expandAll()
        else:
            collapsed = getattr(self, "_collapsed_before_search", set())
            for row in range(self.proxy.rowCount()):
                index = self.proxy.index(row, 0)
                self.tree.setExpanded(index, index.data(ROLE_ID) not in collapsed)
        self._restoring = False
        self._update_body()

    def _update_body(self) -> None:
        if self.model.rowCount() == 0:
            self.body.setCurrentIndex(1)
        elif self.proxy.rowCount() == 0:
            self.body.setCurrentIndex(2)
        else:
            self.body.setCurrentIndex(0)

    def _on_clicked(self, index: QModelIndex) -> None:
        if index.data(ROLE_KIND) == KIND_COLLECTION:
            self.tree.setExpanded(index, not self.tree.isExpanded(index))
        else:
            self.request_activated.emit(index.data(ROLE_ID))

    def _on_activated(self, index: QModelIndex) -> None:
        if index.data(ROLE_KIND) == KIND_REQUEST:
            self.request_activated.emit(index.data(ROLE_ID))

    def _on_expand_changed(self) -> None:
        if not self._restoring and not self.proxy.active:
            self.collapsed_changed.emit()

    def _on_delete_key(self, index: QModelIndex) -> None:
        if index.data(ROLE_KIND) == KIND_REQUEST:
            self.delete_request.emit(index.data(ROLE_ID))
        else:
            self.delete_collection.emit(index.data(ROLE_ID))

    def _on_rename_key(self, index: QModelIndex) -> None:
        if index.data(ROLE_KIND) == KIND_REQUEST:
            self.rename_request.emit(index.data(ROLE_ID))
        else:
            self.edit_collection.emit(index.data(ROLE_ID))

    def _show_menu(self, position: QPoint) -> None:
        index = self.tree.indexAt(position)
        menu = QMenu(self)
        if not index.isValid():
            menu.addAction(tr("New Collection"), self.new_collection.emit)
            menu.addAction(tr("New Request"), lambda: self.new_request.emit(None))
        elif index.data(ROLE_KIND) == KIND_COLLECTION:
            collection_id = index.data(ROLE_ID)
            menu.addAction(tr("New Request"), lambda: self.new_request.emit(collection_id))
            menu.addAction(tr("Rename / Edit…"), lambda: self.edit_collection.emit(collection_id))
            menu.addAction(tr("Duplicate"), lambda: self.duplicate_collection.emit(collection_id))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self.delete_collection.emit(collection_id))
        else:
            request_id = index.data(ROLE_ID)
            menu.addAction(tr("Open"), lambda: self.request_activated.emit(request_id))
            menu.addAction(tr("Rename"), lambda: self.rename_request.emit(request_id))
            menu.addAction(tr("Duplicate"), lambda: self.duplicate_request.emit(request_id))
            menu.addAction(tr("Move to…"), lambda: self.move_request.emit(request_id))
            menu.addAction(tr("Copy as cURL"), lambda: self.copy_curl.emit(request_id))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self.delete_request.emit(request_id))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def refresh_theme(self) -> None:
        theme = current_theme()
        self._search_icon.setPixmap(icons.pixmap("search", theme.text_faint, 14))
        self.new_button.setIcon(icons.icon("plus", theme.accent_text))
        apply_icon(self._add_collection)
        self.tree.viewport().update()
