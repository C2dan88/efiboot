import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class BootEntry:
    number: str
    label: str
    active: bool


def parse_efibootmgr(output: str) -> tuple[list[BootEntry], list[str]]:
    entries: dict[str, BootEntry] = {}
    boot_order: list[str] | None = None

    for line in output.splitlines():
        order_match = re.match(r"^BootOrder:\s*(.*)$", line)
        if order_match:
            boot_order = [number.upper() for number in re.findall(r"[0-9A-Fa-f]{4}", order_match.group(1))]
            continue

        entry_match = re.match(r"^Boot([0-9A-Fa-f]{4})(\*)?\s*(.*)$", line)
        if entry_match:
            number = entry_match.group(1).upper()
            entries[number] = BootEntry(number, entry_match.group(3).strip(), bool(entry_match.group(2)))

    if boot_order is None:
        raise ValueError("efibootmgr did not report a BootOrder.")

    ordered_numbers = [number for number in boot_order if number in entries]
    unordered_numbers = [number for number in entries if number not in ordered_numbers]
    return [entries[number] for number in ordered_numbers + unordered_numbers], ordered_numbers


class BootOrderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EFI Boot Order")
        self.resize(680, 480)
        self.process: QProcess | None = None

        root = QWidget()
        layout = QVBoxLayout(root)
        self.entries = QListWidget()
        self.entries.setAlternatingRowColors(True)
        layout.addWidget(self.entries)

        controls = QHBoxLayout()
        self.reload_button = QPushButton("Reload")
        self.up_button = QPushButton("Move up")
        self.down_button = QPushButton("Move down")
        self.apply_button = QPushButton("Apply order")
        controls.addWidget(self.reload_button)
        controls.addStretch(1)
        controls.addWidget(self.up_button)
        controls.addWidget(self.down_button)
        controls.addWidget(self.apply_button)
        layout.addLayout(controls)

        self.setCentralWidget(root)
        self.statusBar().showMessage(
            "Check entries to include them. Unchecked entries are not deleted, only left out of BootOrder."
        )

        self.reload_button.clicked.connect(self.load_entries)
        self.up_button.clicked.connect(lambda: self.move_entry(-1))
        self.down_button.clicked.connect(lambda: self.move_entry(1))
        self.apply_button.clicked.connect(self.apply_order)
        self.load_entries()

    def load_entries(self) -> None:
        executable = shutil.which("efibootmgr")
        if not executable:
            QMessageBox.critical(self, "efibootmgr not found", "Install efibootmgr and try again.")
            return

        try:
            result = subprocess.run(
                [executable, "-v"], capture_output=True, text=True, timeout=15, check=True
            )
            entries, current_order = parse_efibootmgr(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            detail = getattr(error, "stderr", None) or str(error)
            QMessageBox.critical(self, "Could not read boot entries", detail.strip())
            return

        self.entries.clear()
        for entry in entries:
            state = "" if entry.active else " [disabled]"
            item = QListWidgetItem(f"Boot{entry.number}{state}  {entry.label or '(no description)'}")
            item.setData(Qt.ItemDataRole.UserRole, entry.number)
            item.setToolTip(entry.label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if entry.number in current_order else Qt.CheckState.Unchecked
            )
            self.entries.addItem(item)

        self.statusBar().showMessage(f"Loaded {len(entries)} boot entries.")

    def move_entry(self, offset: int) -> None:
        current_row = self.entries.currentRow()
        target_row = current_row + offset
        if current_row < 0 or not 0 <= target_row < self.entries.count():
            return

        item = self.entries.takeItem(current_row)
        self.entries.insertItem(target_row, item)
        self.entries.setCurrentRow(target_row)

    def apply_order(self) -> None:
        order = [
            self.entries.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.entries.count())
            if self.entries.item(row).checkState() == Qt.CheckState.Checked
        ]
        if not order:
            QMessageBox.warning(self, "Empty boot order", "Select at least one boot entry.")
            return

        confirmation = QMessageBox.question(
            self,
            "Apply boot order?",
            "Set BootOrder to:\n\n" + ", ".join(order) + "\n\nThis requires administrator authorization.",
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmation != QMessageBox.StandardButton.Apply:
            return

        efibootmgr = shutil.which("efibootmgr")
        if not efibootmgr:
            QMessageBox.critical(self, "efibootmgr not found", "Install efibootmgr and try again.")
            return

        if os.geteuid() == 0:
            program, arguments = efibootmgr, ["-o", ",".join(order)]
        else:
            pkexec = shutil.which("pkexec")
            if not pkexec:
                QMessageBox.critical(
                    self,
                    "Authorization tool not found",
                    "Install polkit (pkexec), or launch this app with sudo.",
                )
                return
            program, arguments = pkexec, [efibootmgr, "-o", ",".join(order)]

        self.apply_button.setEnabled(False)
        self.statusBar().showMessage("Waiting for administrator authorization...")
        self.process = QProcess(self)
        self.process.finished.connect(self.apply_finished)
        self.process.errorOccurred.connect(self.apply_error)
        self.process.start(program, arguments)

    def apply_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        if self.process is None:
            return
        output = bytes(self.process.readAllStandardError()).decode(errors="replace").strip()
        self.apply_button.setEnabled(True)
        self.process = None

        if exit_code != 0:
            QMessageBox.critical(
                self, "Could not apply boot order", output or f"Command exited with status {exit_code}."
            )
            self.statusBar().showMessage("Boot order was not changed.")
            return

        QMessageBox.information(self, "Boot order updated", "The new BootOrder was applied.")
        self.load_entries()

    def apply_error(self, _error: QProcess.ProcessError) -> None:
        if self.process is None:
            return
        message = self.process.errorString()
        self.apply_button.setEnabled(True)
        self.process = None
        QMessageBox.critical(self, "Could not start command", message)
        self.statusBar().showMessage("Boot order was not changed.")


def main() -> int:
    app = QApplication(sys.argv)
    window = BootOrderWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())