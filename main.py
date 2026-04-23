import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MDB Reader")
    app.setOrganizationName("mdb-reader")

    win = MainWindow()
    win.show()

    # Support opening a file passed as CLI argument
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if path.lower().endswith(".mdb"):
            win._load_file(path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
