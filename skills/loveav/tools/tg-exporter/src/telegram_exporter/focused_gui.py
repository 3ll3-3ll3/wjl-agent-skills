from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)
from qasync import asyncSlot

from .category_manager import CategoryManagerDialog
from .export_categories import all_categories, ensure_category_dirs, normalize_categories
from .exporter import export_group
from .group_selector import GroupSelectorDialog
from .gui import MODE_LABELS
from .gui_async import MainWindow as AsyncMainWindow
from .logging_setup import log_file_path
from .models import DEFAULT_EXPORT_CATEGORY, ExportMode, GroupExportPlan, GroupInfo
from .paths import settings_path
from .read_state import mark_unread_snapshot_read
from .storage import read_json, write_json_atomic

logger = logging.getLogger("telegram_exporter.focused_gui")

# checked, category, mode, start, end, mark-read
RowSettings = tuple[bool, str, str, QDate, QDate, bool]


class MainWindow(AsyncMainWindow):
    """qasync-safe focused workspace with per-group category and read policy."""

    def __init__(self):
        super().__init__()
        self.all_groups: list[GroupInfo] = []

        root = self.centralWidget().layout()
        top = root.itemAt(0).layout() if root is not None and root.count() else None
        self.select_groups_btn = QPushButton("选择群组")
        self.select_groups_btn.setEnabled(False)
        self.select_groups_btn.clicked.connect(self.select_groups)
        self.manage_categories_btn = QPushButton("管理分类")
        self.manage_categories_btn.clicked.connect(self.manage_categories)
        if top is not None:
            top.insertWidget(1, self.select_groups_btn)
            top.insertWidget(2, self.manage_categories_btn)

        self.refresh_btn.setText("刷新群组目录")

        workspace_hint = QLabel(
            "账号中的全部群组只作为后台目录；主编辑面板只显示你在『选择群组』里勾选的工作群。"
            "导出按『总输出目录 / 分类 / 群组 / 日期时间.json』保存；分类可在软件内直接创建。"
            "『导出后标已读』默认关闭，并且只在『当前未读』模式下生效。"
        )
        workspace_hint.setWordWrap(True)
        if root is not None:
            root.insertWidget(3, workspace_hint)

        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            [
                "导出",
                "群组",
                "分类",
                "导出方式",
                "开始日期",
                "结束日期",
                "未读",
                "导出后标已读",
                "状态",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)

    def _settings(self) -> dict:
        payload = read_json(settings_path(), {})
        return payload if isinstance(payload, dict) else {}

    def _update_settings(self, **updates) -> None:
        payload = self._settings()
        payload.update(updates)
        write_json_atomic(settings_path(), payload)

    def _selected_group_ids(self) -> set[int]:
        values = self._settings().get("selected_group_ids", [])
        if not isinstance(values, list):
            return set()
        result: set[int] = set()
        for value in values:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def _custom_categories(self) -> list[str]:
        return normalize_categories(self._settings().get("export_categories", []))

    def _category_preferences(self) -> dict[str, str]:
        raw = self._settings().get("group_export_categories", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, str] = {}
        allowed = set(all_categories(self._custom_categories()))
        for key, value in raw.items():
            category = str(value)
            if category in allowed:
                result[str(key)] = category
        return result

    def _saved_category(self, chat_id: int) -> str:
        return self._category_preferences().get(str(chat_id), DEFAULT_EXPORT_CATEGORY)

    def _save_category(self, chat_id: int, category: str) -> None:
        preferences = self._category_preferences()
        if category == DEFAULT_EXPORT_CATEGORY:
            preferences.pop(str(chat_id), None)
        else:
            preferences[str(chat_id)] = category
        self._update_settings(group_export_categories=preferences)

    def _mark_read_preferences(self) -> dict[str, bool]:
        raw = self._settings().get("mark_read_after_export", {})
        if not isinstance(raw, dict):
            return {}
        return {str(key): bool(value) for key, value in raw.items()}

    def _saved_mark_read(self, chat_id: int) -> bool:
        return self._mark_read_preferences().get(str(chat_id), False)

    def _save_mark_read(self, chat_id: int, checked: bool) -> None:
        preferences = self._mark_read_preferences()
        if checked:
            preferences[str(chat_id)] = True
        else:
            preferences.pop(str(chat_id), None)
        self._update_settings(mark_read_after_export=preferences)

    def _migrate_persisted_group_settings(self, groups: list[GroupInfo]) -> None:
        """Move UI-only settings from legacy basic Chat ids to current supergroups."""

        old_to_new = {
            group.migrated_from_chat_id: group.chat_id
            for group in groups
            if group.migrated_from_chat_id is not None
        }
        if not old_to_new:
            return

        payload = self._settings()
        changed = False

        selected = payload.get("selected_group_ids", [])
        if isinstance(selected, list):
            migrated_selected: list[int] = []
            seen: set[int] = set()
            for value in selected:
                try:
                    group_id = int(value)
                except (TypeError, ValueError):
                    continue
                group_id = old_to_new.get(group_id, group_id)
                if group_id not in seen:
                    seen.add(group_id)
                    migrated_selected.append(group_id)
            if migrated_selected != selected:
                payload["selected_group_ids"] = migrated_selected
                changed = True

        for key in ("mark_read_after_export", "group_export_categories"):
            raw = payload.get(key, {})
            if not isinstance(raw, dict):
                continue
            next_raw = dict(raw)
            for old_id, new_id in old_to_new.items():
                old_key = str(old_id)
                new_key = str(new_id)
                if old_key not in next_raw:
                    continue
                if new_key not in next_raw:
                    next_raw[new_key] = next_raw[old_key]
                next_raw.pop(old_key, None)
            if next_raw != raw:
                payload[key] = next_raw
                changed = True

        if changed:
            write_json_atomic(settings_path(), payload)
            logger.info("Migrated persisted workspace settings from legacy basic-group ids")

    @asyncSlot()
    async def choose_output(self) -> None:
        if self._busy:
            return
        dialog = QFileDialog(self, "选择导出目录", str(self._default_output_dir()))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        result = await self._await_dialog(dialog)
        if result == QDialog.Accepted:
            selected = dialog.selectedFiles()
            if selected:
                path = selected[0]
                try:
                    ensure_category_dirs(Path(path), self._custom_categories())
                except OSError as exc:
                    self._show_message(QMessageBox.Warning, "无法创建分类目录", str(exc))
                else:
                    self.output_label.setText(path)
                    self._update_settings(output_dir=path)
                    logger.info("Output directory changed to %s", path)
        dialog.deleteLater()

    @asyncSlot()
    async def manage_categories(self) -> None:
        if self._busy:
            return
        previous = self._capture_row_settings()
        dialog = CategoryManagerDialog(self._custom_categories(), self)
        result = await self._await_dialog(dialog)
        if result == QDialog.Accepted:
            categories = dialog.categories()
            allowed = set(all_categories(categories))
            preferences = self._category_preferences()
            preferences = {key: value for key, value in preferences.items() if value in allowed}
            try:
                ensure_category_dirs(Path(self.output_label.text()), categories)
            except OSError as exc:
                self._show_message(QMessageBox.Warning, "无法创建分类目录", str(exc))
            else:
                self._update_settings(
                    export_categories=categories,
                    group_export_categories=preferences,
                )
                self._render_groups(self.groups, previous)
                self.status.setText(f"已保存 {len(categories)} 个自定义导出分类。")
                logger.info("Export categories updated: count=%s", len(categories))
        dialog.deleteLater()

    @asyncSlot()
    async def select_groups(self) -> None:
        if self._busy:
            return
        if not self.all_groups:
            self._show_message(QMessageBox.Information, "群组目录为空", "请先连接 Telegram 并加载群组目录。")
            return

        previous = self._capture_row_settings()
        dialog = GroupSelectorDialog(self.all_groups, self._selected_group_ids(), self)
        result = await self._await_dialog(dialog)
        if result == QDialog.Accepted:
            selected_ids = dialog.selected_ids()
            self._update_settings(selected_group_ids=sorted(selected_ids))
            selected = [group for group in self.all_groups if group.chat_id in selected_ids]
            self._render_groups(selected, previous)
            logger.info(
                "Workspace group selection updated: selected=%s catalog=%s",
                len(selected),
                len(self.all_groups),
            )
            if selected:
                self.status.setText(f"群组目录共 {len(self.all_groups)} 个；编辑面板只显示已选 {len(selected)} 个。")
            else:
                self.status.setText(f"群组目录共 {len(self.all_groups)} 个；当前未选择工作群。")
        dialog.deleteLater()

    async def _refresh_groups_impl(self) -> None:
        assert self.service
        previous = self._capture_row_settings()
        self.all_groups = await self.service.list_groups()
        self._migrate_persisted_group_settings(self.all_groups)
        selected_ids = self._selected_group_ids()
        selected = [group for group in self.all_groups if group.chat_id in selected_ids]
        self._render_groups(selected, previous)
        self.select_groups_btn.setEnabled(True)
        if selected:
            self.status.setText(f"群组目录共 {len(self.all_groups)} 个；编辑面板只显示已选 {len(selected)} 个。")
        else:
            self.status.setText(f"已加载 {len(self.all_groups)} 个群组/频道。请点击『选择群组』挑选工作群。")

    def _capture_row_settings(self) -> dict[int, RowSettings]:
        result: dict[int, RowSettings] = {}
        for row, group in enumerate(self.groups):
            check = self.table.cellWidget(row, 0)
            category = self.table.cellWidget(row, 2)
            mode = self.table.cellWidget(row, 3)
            start = self.table.cellWidget(row, 4)
            end = self.table.cellWidget(row, 5)
            mark_read = self.table.cellWidget(row, 7)
            if not (
                isinstance(check, QCheckBox)
                and isinstance(category, QComboBox)
                and isinstance(mode, QComboBox)
                and isinstance(start, QDateEdit)
                and isinstance(end, QDateEdit)
                and isinstance(mark_read, QCheckBox)
            ):
                continue
            result[group.chat_id] = (
                check.isChecked(),
                category.currentText(),
                str(mode.currentData()),
                start.date(),
                end.date(),
                mark_read.isChecked(),
            )
        return result

    def _render_groups(
        self,
        groups: list[GroupInfo],
        previous: dict[int, RowSettings] | None = None,
    ) -> None:
        self.groups = groups
        self.table.setRowCount(len(groups))
        today = QDate.currentDate()
        previous = previous or {}
        categories = all_categories(self._custom_categories())

        for row, group in enumerate(groups):
            saved = previous.get(group.chat_id)

            check = QCheckBox()
            check.setChecked(saved[0] if saved else True)
            self.table.setCellWidget(row, 0, check)

            title = QTableWidgetItem(group.title)
            tooltip = f"Telegram peer id: {group.chat_id}"
            if group.migrated_from_chat_id is not None:
                tooltip += f"\n由旧普通群 {group.migrated_from_chat_id} 升级为超级群；旧行已合并。"
            title.setToolTip(tooltip)
            self.table.setItem(row, 1, title)

            category = QComboBox()
            category.addItems(categories)
            selected_category = saved[1] if saved else self._saved_category(group.chat_id)
            index = category.findText(selected_category)
            category.setCurrentIndex(index if index >= 0 else 0)
            self.table.setCellWidget(row, 2, category)

            mode = QComboBox()
            for export_mode, label in MODE_LABELS.items():
                mode.addItem(label, export_mode.value)
            if saved:
                index = mode.findData(saved[2])
                if index >= 0:
                    mode.setCurrentIndex(index)
            self.table.setCellWidget(row, 3, mode)

            start = QDateEdit(saved[3] if saved else today.addDays(-9))
            start.setCalendarPopup(True)
            start.setDisplayFormat("yyyy-MM-dd")
            end = QDateEdit(saved[4] if saved else today)
            end.setCalendarPopup(True)
            end.setDisplayFormat("yyyy-MM-dd")
            self.table.setCellWidget(row, 4, start)
            self.table.setCellWidget(row, 5, end)

            self.table.setItem(row, 6, QTableWidgetItem(str(group.unread_count)))

            mark_read = QCheckBox()
            mark_read.setChecked(saved[5] if saved else self._saved_mark_read(group.chat_id))
            mark_read.setToolTip(
                "仅『当前未读』模式可用。只有 JSON 成功写入后才会发送已读确认。\n"
                "Telegram 已读状态按消息 ID 推进，所以本快照内图片、文件、系统消息等非文本项也会一起变成已读。"
            )
            self.table.setCellWidget(row, 7, mark_read)
            self.table.setItem(row, 8, QTableWidgetItem("待导出"))

            category.currentTextChanged.connect(
                lambda text, gid=group.chat_id: self._category_changed(gid, text)
            )
            mode.currentTextChanged.connect(lambda _text, r=row: self._update_row_mode(r))
            mark_read.toggled.connect(
                lambda checked, gid=group.chat_id, r=row: self._mark_read_changed(gid, r, checked)
            )
            self._update_row_mode(row)

        self.export_btn.setEnabled(bool(groups) and self.service is not None and not self._busy)

    def _category_changed(self, chat_id: int, category: str) -> None:
        self._save_category(chat_id, category)

    def _mark_read_changed(self, chat_id: int, row: int, checked: bool) -> None:
        self._save_mark_read(chat_id, checked)
        self._update_row_mode(row)

    def _update_row_mode(self, row: int) -> None:
        mode = self.table.cellWidget(row, 3)
        start = self.table.cellWidget(row, 4)
        end = self.table.cellWidget(row, 5)
        mark_read = self.table.cellWidget(row, 7)
        assert (
            isinstance(mode, QComboBox)
            and isinstance(start, QDateEdit)
            and isinstance(end, QDateEdit)
            and isinstance(mark_read, QCheckBox)
        )

        export_mode = ExportMode(mode.currentData())
        is_range = export_mode is ExportMode.DATE_RANGE
        is_unread = export_mode is ExportMode.UNREAD
        start.setEnabled(is_range)
        end.setEnabled(is_range)
        mark_read.setEnabled(is_unread)

        status_item = self.table.item(row, 8)
        if not status_item:
            return
        if is_unread:
            if mark_read.isChecked():
                status_item.setText("导出成功后标已读（快照内非文本项也会一起已读）")
            else:
                status_item.setText("只读导出：不会改变 Telegram 已读状态")
        elif export_mode is ExportMode.SINCE_LAST_EXPORT:
            last_id = self.state.last_message_id(self.groups[row].chat_id)
            status_item.setText(f"上次位置：{last_id}" if last_id else "尚无上次导出记录")
        else:
            if self.groups[row].migrated_from_chat_id is not None:
                status_item.setText("指定时间范围会自动包含升级超级群前的旧群历史")
            else:
                status_item.setText("待导出")

    def bulk_recent_10(self) -> None:
        """Override the legacy base-table column indexes after adding 分类."""

        today = QDate.currentDate()
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if not isinstance(check, QCheckBox) or not check.isChecked():
                continue
            mode = self.table.cellWidget(row, 3)
            start = self.table.cellWidget(row, 4)
            end = self.table.cellWidget(row, 5)
            assert isinstance(mode, QComboBox) and isinstance(start, QDateEdit) and isinstance(end, QDateEdit)
            mode.setCurrentIndex(mode.findData(ExportMode.DATE_RANGE.value))
            start.setDate(today.addDays(-9))
            end.setDate(today)

    def _plans(self) -> list[tuple[int, GroupExportPlan, bool]]:
        plans: list[tuple[int, GroupExportPlan, bool]] = []
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc

        for row, group in enumerate(self.groups):
            check = self.table.cellWidget(row, 0)
            if not isinstance(check, QCheckBox) or not check.isChecked():
                continue

            category_box = self.table.cellWidget(row, 2)
            mode_box = self.table.cellWidget(row, 3)
            start_edit = self.table.cellWidget(row, 4)
            end_edit = self.table.cellWidget(row, 5)
            mark_read_box = self.table.cellWidget(row, 7)
            assert (
                isinstance(category_box, QComboBox)
                and isinstance(mode_box, QComboBox)
                and isinstance(mark_read_box, QCheckBox)
            )

            mode = ExportMode(mode_box.currentData())
            start_at = end_at = None
            if mode is ExportMode.DATE_RANGE:
                assert isinstance(start_edit, QDateEdit) and isinstance(end_edit, QDateEdit)
                start_at = datetime.combine(start_edit.date().toPython(), time.min, local_tz)
                end_at = datetime.combine(end_edit.date().toPython(), time.max, local_tz)

            plan = GroupExportPlan(
                group=group,
                mode=mode,
                category=category_box.currentText(),
                start_at=start_at,
                end_at=end_at,
                last_export_message_id=self.state.last_message_id(group.chat_id),
            )
            plan.validate()
            plans.append((row, plan, mode is ExportMode.UNREAD and mark_read_box.isChecked()))

        return plans

    @asyncSlot()
    async def start_export(self) -> None:
        if self._busy or not self.service:
            return
        try:
            plans = self._plans()
        except ValueError as exc:
            self._show_message(QMessageBox.Warning, "导出配置无效", str(exc))
            return
        if not plans:
            self._show_message(QMessageBox.Information, "没有选择群组", "请至少选择一个群组。")
            return

        output_root = Path(self.output_label.text())
        export_moment = datetime.now().astimezone()
        try:
            ensure_category_dirs(output_root, self._custom_categories())
        except OSError as exc:
            self._show_message(QMessageBox.Warning, "无法准备输出目录", str(exc))
            return

        self._set_busy(True, f"准备导出 {len(plans)} 个群组…")
        self.progress.setRange(0, len(plans))
        self.progress.setValue(0)
        results = []
        failures: list[tuple[str, str]] = []
        read_failures: list[tuple[str, str]] = []
        marked_read_count = 0
        logger.info(
            "Starting export run timestamp=%s groups=%s output_root=%s",
            export_moment.isoformat(timespec="seconds"),
            len(plans),
            output_root,
        )

        try:
            for done, (row, plan, mark_read_after_export) in enumerate(plans, start=1):
                status_item = self.table.item(row, 8)
                if status_item:
                    status_item.setText("导出中…")
                try:
                    logger.info(
                        "Exporting group '%s' category='%s' mode=%s mark_read_after_export=%s",
                        plan.group.title,
                        plan.category,
                        plan.mode.value,
                        mark_read_after_export,
                    )
                    result = await export_group(
                        self.service.client,
                        plan,
                        output_root,
                        export_moment=export_moment,
                    )
                    results.append(result)

                    if result.latest_message_id:
                        self.state.mark_success(
                            result.chat_id,
                            result.latest_message_id,
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                        )

                    suffix = ""
                    if mark_read_after_export:
                        try:
                            acknowledged_id = await mark_unread_snapshot_read(self.service.client, plan.group)
                            if acknowledged_id is not None:
                                marked_read_count += 1
                                plan.group.read_inbox_max_id = acknowledged_id
                                plan.group.unread_count = 0
                                unread_item = self.table.item(row, 6)
                                if unread_item:
                                    unread_item.setText("0")
                                    unread_item.setToolTip(
                                        "已处理刷新时的未读快照；请刷新群组目录获取之后到达的新消息。"
                                    )
                                suffix = "；已标已读"
                            else:
                                suffix = "；无未读需标记"
                        except Exception as read_exc:
                            logger.error(
                                "Read acknowledgement failed for group '%s' after successful export",
                                plan.group.title,
                                exc_info=(type(read_exc), read_exc, read_exc.__traceback__),
                            )
                            read_failures.append((plan.group.title, f"{type(read_exc).__name__}: {read_exc}"))
                            suffix = "；标已读失败"

                    if status_item:
                        status_item.setText(f"完成：{result.message_count} 条{suffix}")
                    logger.info(
                        "Exported group '%s': %s messages -> %s",
                        plan.group.title,
                        result.message_count,
                        result.result_path,
                    )
                except Exception as exc:
                    logger.error(
                        "Export failed for group '%s'",
                        plan.group.title,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    failures.append((plan.group.title, f"{type(exc).__name__}: {exc}"))
                    if status_item:
                        status_item.setText("失败；未改变已读状态")

                self.progress.setValue(done)
                self.status.setText(f"进度：{done}/{len(plans)} 个群组")
        finally:
            self._set_busy(False)

        total = sum(result.message_count for result in results)
        logger.info(
            "Export run completed: success=%s failed=%s messages=%s marked_read=%s read_failures=%s",
            len(results),
            len(failures),
            total,
            marked_read_count,
            len(read_failures),
        )

        if failures or read_failures:
            parts = [f"成功导出 {len(results)} 个群，共 {total} 条；导出失败 {len(failures)} 个。"]
            if marked_read_count:
                parts.append(f"其中 {marked_read_count} 个群已按你的设置同步标记已读。")
            if read_failures:
                parts.append(f"另有 {len(read_failures)} 个群 JSON 已成功，但『标已读』同步失败；文件仍然保留。")
            details = []
            details.extend(f"• 导出失败｜{name}: {err}" for name, err in failures[:6])
            details.extend(f"• 标已读失败｜{name}: {err}" for name, err in read_failures[:6])
            if details:
                parts.append("\n".join(details))
            parts.append(f"总输出目录：{output_root}")
            parts.append(f"日志：{log_file_path()}")
            self._show_message(
                QMessageBox.Warning,
                "本次导出完成（有需要注意的项目）",
                "\n\n".join(parts),
            )
        else:
            extra = f"\n其中 {marked_read_count} 个群已按设置标记为已读。" if marked_read_count else ""
            self._show_message(
                QMessageBox.Information,
                "导出完成",
                f"成功导出 {len(results)} 个群组，共 {total} 条纯文本消息。{extra}"
                f"\n\n文件已按『分类 / 群组 / 日期时间.json』写入：\n{output_root}",
            )

        self.status.setText(
            f"本次导出完成：成功 {len(results)}，失败 {len(failures)}，共 {total} 条文本；已标已读 {marked_read_count} 个群。"
        )

    def _mark_disconnected(self, clear_groups: bool = False) -> None:
        super()._mark_disconnected(clear_groups=clear_groups)
        self.select_groups_btn.setEnabled(False)
        if clear_groups:
            self.all_groups = []

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        super()._set_busy(busy, status)
        self.select_groups_btn.setEnabled(not busy and bool(self.all_groups))
        self.manage_categories_btn.setEnabled(not busy)
