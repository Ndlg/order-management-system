import traceback

from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        try:
            self.finished_ok.emit(self.task())
        except Exception:
            self.failed.emit(traceback.format_exc())

