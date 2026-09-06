import inspect

from telegram_exporter import gui_async
from telegram_exporter.gui import MainWindow as BaseMainWindow


def test_qasync_safe_window_extends_base_gui():
    assert issubclass(gui_async.MainWindow, BaseMainWindow)


def test_async_gui_does_not_use_nested_modal_event_loops():
    source = inspect.getsource(gui_async)
    assert ".exec(" not in source
    assert "QInputDialog.getText" not in source
    assert "QMessageBox.question" not in source
    assert "dialog.open()" in source
