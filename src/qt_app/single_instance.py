from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    activated = Signal()

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = f"order-sorter-{name}"
        self.server = None

    def start_or_notify(self):
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(180):
            socket.write(b"activate")
            socket.flush()
            socket.waitForBytesWritten(180)
            socket.disconnectFromServer()
            return False

        QLocalServer.removeServer(self.name)
        self.server = QLocalServer(self)
        if not self.server.listen(self.name):
            return True
        self.server.newConnection.connect(self._on_new_connection)
        return True

    def _on_new_connection(self):
        while self.server and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readAll()
            socket.disconnectFromServer()
            socket.deleteLater()
            self.activated.emit()


def activate_window(window):
    if window.isMinimized():
        window.showNormal()
    window.setWindowState((window.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
