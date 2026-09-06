from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .models import FolderRef, GroupInfo

AVATAR_SIZE = 42
ROW_HEIGHT = 58
AvatarLoader = Callable[[GroupInfo], Awaitable[bytes | None]]


def _avatar_letter(title: str) -> str:
    text = title.strip()
    return text[:1].upper() if text else "?"


def _placeholder_icon(group: GroupInfo) -> QIcon:
    palette = (
        "#4f46e5",
        "#2563eb",
        "#0891b2",
        "#059669",
        "#65a30d",
        "#ca8a04",
        "#ea580c",
        "#dc2626",
        "#db2777",
        "#7c3aed",
    )
    color = QColor(palette[abs(group.chat_id) % len(palette)])
    pixmap = QPixmap(AVATAR_SIZE, AVATAR_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(0, 0, AVATAR_SIZE, AVATAR_SIZE)
    painter.setPen(QColor("white"))
    font = QFont("Microsoft YaHei UI", 14)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, _avatar_letter(group.title))
    painter.end()
    return QIcon(pixmap)


def _circular_icon(data: bytes) -> QIcon | None:
    source = QPixmap()
    if not source.loadFromData(data):
        return None

    scaled = source.scaled(
        AVATAR_SIZE,
        AVATAR_SIZE,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - AVATAR_SIZE) // 2)
    y = max(0, (scaled.height() - AVATAR_SIZE) // 2)

    target = QPixmap(AVATAR_SIZE, AVATAR_SIZE)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, AVATAR_SIZE, AVATAR_SIZE)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled, x, y, AVATAR_SIZE, AVATAR_SIZE)
    painter.end()
    return QIcon(target)


def _item_text(group: GroupInfo) -> str:
    details: list[str] = []
    if group.username:
        details.append(f"@{group.username}")
    details.append("群组" if group.is_group else "频道")
    if group.unread_count:
        details.append(f"未读 {group.unread_count}")
    return f"{group.title}\n{' · '.join(details)}"


class GroupSelectorDialog(QDialog):
    """Searchable selector for the full Telegram dialog catalogue.

    The main window should only display the selected working set. Telegram's
    account-side chat folders (dialog filters) can narrow the catalogue before
    the user searches/checks groups. Small chat avatars are loaded lazily for
    visible rows only and are purely UI decoration, never export content.
    """

    def __init__(
        self,
        groups: list[GroupInfo],
        selected_ids: set[int],
        parent=None,
        *,
        avatar_loader: AvatarLoader | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("选择要放到编辑面板的群组")
        self.resize(820, 760)
        self._groups = groups
        self._groups_by_id = {group.chat_id: group for group in groups}
        if avatar_loader is None:
            service = getattr(parent, "service", None)
            candidate = getattr(service, "group_avatar_bytes", None)
            if callable(candidate):
                avatar_loader = candidate
        self._avatar_loader = avatar_loader
        self._avatar_tasks: dict[int, asyncio.Task[None]] = {}
        self._avatar_attempted: set[int] = set()
        self._avatar_semaphore = asyncio.Semaphore(6)

        root = QVBoxLayout(self)
        intro = QLabel(
            "这里是账号中的完整群组/频道目录。可以先按 Telegram 账号里已有的聊天分组筛选，"
            "再搜索并勾选常用群组；只有勾中的项目会出现在主界面的导出编辑面板。"
            "群头像按当前可见项目异步加载并仅缓存在本机。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Telegram 分组："))
        self.folder = QComboBox()
        self.folder.setMinimumWidth(280)
        self.folder.addItem("全部群组/频道", None)

        folder_map: dict[int, FolderRef] = {}
        folder_counts: dict[int, int] = {}
        for group in groups:
            for ref in group.folders:
                folder_map.setdefault(ref.folder_id, ref)
                folder_counts[ref.folder_id] = folder_counts.get(ref.folder_id, 0) + 1
        for ref in sorted(folder_map.values(), key=lambda item: (item.order, item.title.casefold())):
            self.folder.addItem(f"{ref.title}  ({folder_counts.get(ref.folder_id, 0)})", ref.folder_id)

        folder_row.addWidget(self.folder, 1)
        if not folder_map:
            no_folder = QLabel("未读取到包含群组/频道的账号分组")
            no_folder.setStyleSheet("color: #6b7280;")
            folder_row.addWidget(no_folder)
        root.addLayout(folder_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("在当前分组中搜索群名或 @username…")
        self.search.setClearButtonEnabled(True)
        root.addWidget(self.search)

        toolbar = QHBoxLayout()
        self.visible_all_btn = QPushButton("勾选当前筛选结果")
        self.visible_none_btn = QPushButton("取消当前筛选结果")
        self.count_label = QLabel()
        toolbar.addWidget(self.visible_all_btn)
        toolbar.addWidget(self.visible_none_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.count_label)
        root.addLayout(toolbar)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setIconSize(QSize(AVATAR_SIZE, AVATAR_SIZE))
        self.list.setSpacing(2)
        self.list.setStyleSheet(
            "QListWidget::item { padding: 5px 8px; border-radius: 7px; }"
            "QListWidget::item:selected { background: #dbeafe; color: #1f2937; }"
        )
        root.addWidget(self.list, 1)

        for group in groups:
            item = QListWidgetItem(_placeholder_icon(group), _item_text(group))
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            item.setData(Qt.ItemDataRole.UserRole, group.chat_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, f"{group.title} {group.username or ''}".casefold())
            item.setData(Qt.ItemDataRole.UserRole + 2, [ref.folder_id for ref in group.folders])
            if group.folders:
                item.setToolTip("Telegram 分组：" + "、".join(ref.title for ref in group.folders))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if group.chat_id in selected_ids else Qt.CheckState.Unchecked)
            self.list.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.search.textChanged.connect(self._apply_filter)
        self.folder.currentIndexChanged.connect(self._apply_filter)
        self.visible_all_btn.clicked.connect(lambda: self._set_visible(Qt.CheckState.Checked))
        self.visible_none_btn.clicked.connect(lambda: self._set_visible(Qt.CheckState.Unchecked))
        self.list.itemChanged.connect(lambda _item: self._update_count())
        self.list.verticalScrollBar().valueChanged.connect(lambda _value: self._defer_avatar_load())
        self.finished.connect(self._cancel_avatar_tasks)
        self._apply_filter()
        self._defer_avatar_load()

    def _defer_avatar_load(self) -> None:
        QTimer.singleShot(20, self._queue_visible_avatars)

    def _apply_filter(self, *_args) -> None:
        needle = self.search.text().strip().casefold()
        folder_id = self.folder.currentData()
        for row in range(self.list.count()):
            item = self.list.item(row)
            haystack = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
            folder_ids = item.data(Qt.ItemDataRole.UserRole + 2) or []
            matches_text = not needle or needle in haystack
            matches_folder = folder_id is None or int(folder_id) in {int(value) for value in folder_ids}
            item.setHidden(not (matches_text and matches_folder))
        self._update_count()
        self._defer_avatar_load()

    def _set_visible(self, state: Qt.CheckState) -> None:
        self.list.blockSignals(True)
        try:
            for row in range(self.list.count()):
                item = self.list.item(row)
                if not item.isHidden():
                    item.setCheckState(state)
        finally:
            self.list.blockSignals(False)
        self._update_count()

    def _visible_rows(self) -> list[int]:
        if self.list.count() == 0:
            return []
        viewport = self.list.viewport()
        top = self.list.indexAt(QPoint(4, 4))
        bottom = self.list.indexAt(QPoint(4, max(4, viewport.height() - 4)))
        start = top.row() if top.isValid() else 0
        end = bottom.row() if bottom.isValid() else min(self.list.count() - 1, start + 18)
        start = max(0, start - 3)
        end = min(self.list.count() - 1, end + 5)
        return [row for row in range(start, end + 1) if not self.list.item(row).isHidden()]

    def _queue_visible_avatars(self) -> None:
        if self._avatar_loader is None or not self.isVisible():
            return
        for row in self._visible_rows():
            item = self.list.item(row)
            chat_id = int(item.data(Qt.ItemDataRole.UserRole))
            group = self._groups_by_id.get(chat_id)
            if (
                group is None
                or not group.has_photo
                or chat_id in self._avatar_attempted
                or chat_id in self._avatar_tasks
            ):
                continue
            task = asyncio.create_task(self._load_avatar(group, item))
            self._avatar_tasks[chat_id] = task

    async def _load_avatar(self, group: GroupInfo, item: QListWidgetItem) -> None:
        try:
            assert self._avatar_loader is not None
            async with self._avatar_semaphore:
                data = await self._avatar_loader(group)
            self._avatar_attempted.add(group.chat_id)
            if data and self.isVisible():
                icon = _circular_icon(data)
                if icon is not None:
                    item.setIcon(icon)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Avatars are decoration only. Keep the deterministic placeholder.
            self._avatar_attempted.add(group.chat_id)
        finally:
            self._avatar_tasks.pop(group.chat_id, None)

    def _cancel_avatar_tasks(self, *_args) -> None:
        for task in tuple(self._avatar_tasks.values()):
            task.cancel()
        self._avatar_tasks.clear()

    def _update_count(self) -> None:
        selected = sum(
            1
            for row in range(self.list.count())
            if self.list.item(row).checkState() == Qt.CheckState.Checked
        )
        visible = sum(1 for row in range(self.list.count()) if not self.list.item(row).isHidden())
        self.count_label.setText(f"已选 {selected} / {self.list.count()} · 当前显示 {visible}")

    def selected_ids(self) -> set[int]:
        return {
            int(self.list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.list.count())
            if self.list.item(row).checkState() == Qt.CheckState.Checked
        }
