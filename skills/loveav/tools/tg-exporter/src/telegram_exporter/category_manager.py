from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from .export_categories import normalize_categories, validate_category_name
from .models import DEFAULT_EXPORT_CATEGORY


class CategoryManagerDialog(QDialog):
    """Non-blocking-friendly editor for software-side export categories.

    Deleting a category only removes it from future software choices. Historical
    folders/files on disk are deliberately never deleted by this dialog.
    """

    def __init__(self, categories: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理导出分类")
        self.resize(520, 430)
        self._categories = normalize_categories(categories)

        root = QVBoxLayout(self)
        intro = QLabel(
            "分类由 TG Exporter 管理，并对应总输出目录下的一级文件夹。"
            "新建分类会自动创建文件夹；删除这里只取消软件中的分类，不删除历史导出文件。"
            "『未分类』是内置默认项，无需手动创建。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.list = QListWidget()
        root.addWidget(self.list, 1)

        add_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入新分类名称，例如：保研 / AI / 资料")
        self.add_btn = QPushButton("新建分类")
        add_row.addWidget(self.name_edit, 1)
        add_row.addWidget(self.add_btn)
        root.addLayout(add_row)

        self.delete_btn = QPushButton("删除所选分类（不删磁盘文件）")
        root.addWidget(self.delete_btn)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        root.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.add_btn.clicked.connect(self._add)
        self.delete_btn.clicked.connect(self._delete)
        self.name_edit.returnPressed.connect(self._add)
        self._refresh()

    def _refresh(self) -> None:
        current = self.list.currentRow()
        self.list.clear()
        self.list.addItems(self._categories)
        if self._categories:
            self.list.setCurrentRow(min(max(current, 0), len(self._categories) - 1))

    def _add(self) -> None:
        try:
            name = validate_category_name(self.name_edit.text())
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        if name == DEFAULT_EXPORT_CATEGORY:
            self.error.setText("『未分类』是内置默认分类，无需重复创建。")
            return
        if any(existing.casefold() == name.casefold() for existing in self._categories):
            self.error.setText("这个分类已经存在。")
            return
        self._categories.append(name)
        self.name_edit.clear()
        self.error.clear()
        self._refresh()
        self.list.setCurrentRow(len(self._categories) - 1)

    def _delete(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._categories):
            self.error.setText("请先选择一个分类。")
            return
        self._categories.pop(row)
        self.error.clear()
        self._refresh()

    def categories(self) -> list[str]:
        return list(self._categories)
