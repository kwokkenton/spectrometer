"""
Copyright 2025 Kenton Kwok.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
import csv
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import serial
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from model import compute_absorbance, make_db, wavelengths_nm

labels = ['F1', 'F2', 'FZ', 'F3', 'F4', 'F5', 'FY', 'FXL', 'F6', 'F7', 'F8', 'NIR']
csv_filename = "spectrum_data.csv"
# Edit this if it is different
COMPORT = '/dev/cu.usbmodem1201'

# Load templates
db = make_db()

class SerialWorker(QObject):
    """
    SerialWorker designed specifically for the SpectrometerGUI.
    Runs inside a QThread and emits data via Qt signals.
    """

    data_received = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)

    def __init__(self, comport='/dev/cu.usbmodem11201', baudrate=115200):
        super().__init__()
        self.comport = comport
        self.baudrate = baudrate
        self._running = False
        self.ser = None

    def run(self):
        """This function runs inside the QThread."""
        try:
            self.ser = serial.Serial(self.comport, self.baudrate, timeout=0.1)
        except Exception as e:
            self.error_occurred.emit(f"Failed to open serial port '{self.comport}': {e}")
            return

        self._running = True

        while self._running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
            except Exception as e:
                self.error_occurred.emit(f"Serial read error: {e}")
                continue

            if not line:
                continue

            # Parse CSV-style integers
            try:
                arr = np.array([int(x) for x in line.split(',') if x != ""])
            except ValueError:
                self.error_occurred.emit(f"Invalid data received: '{line}'")
                continue

            # Emit data to GUI
            self.data_received.emit(arr)

        # Cleanup when loop stops
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except:
            pass

    def stop(self):
        """Stop the worker loop safely."""
        self._running = False


class SpectrometerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Spectrometer Data Viewer')
        self.setGeometry(100, 100, 1000, 700) 

        self.latest_spectrum_data = None # Store the last received spectrum for saving
        self.display_radiance = True
        self.blank = None
        self.latest_result = None

        self._create_ui()
        self._init_serial_worker()

    def _create_ui(self):
        """Sets up the main user interface layout and widgets."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Left Panel: Controls ---
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setFixedWidth(250)
        control_panel.setStyleSheet("background-color: #000000; padding: 10px;")

        # Title for control panel
        title_label = QLabel("Data Controls")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 15px;")
        control_layout.addWidget(title_label)

        # Form Layout for inputs
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 10, 0, 10) # Add some padding to the form

        # Juice Identity Dropdown
        self.juice_combo_label = QLabel("Juice Identity:")
        self.juice_combo = QComboBox()
        # Pre-populate with common options
        self.juice_combo.addItems(["Apple", "Orange", "Tomato", "Pineapple", "Mango", "Blueberry", "Water", "Custom"])
        form_layout.addRow(self.juice_combo_label, self.juice_combo)

        # Concentration Input
        self.concentration_label = QLabel("Concentration:")
        self.concentration_input = QLineEdit()
        self.concentration_input.setPlaceholderText("e.g., 10%, 0.5M, Pure, N/A")
        form_layout.addRow(self.concentration_label, self.concentration_input)

        control_layout.addLayout(form_layout)

        # Save Button
        self.save_button = QPushButton("Save Data to CSV")
        self.save_button.clicked.connect(self._save_data_to_csv)
        self.save_button.setStyleSheet("padding: 10px; font-size: 12pt; background-color: #4CAF50; color: white; border-radius: 5px;")
        control_layout.addWidget(self.save_button)
        # control_layout.addStretch() # Push everything to the top
        # main_layout.addWidget(control_panel)

        # Capture blank
        self.save_blank_button = QPushButton("Capture reference curve")
        self.save_blank_button.clicked.connect(self._save_blank)
        self.save_blank_button.setStyleSheet("padding: 10px; font-size: 12pt; background-color: #4CAF50; color: white; border-radius: 5px;")
        control_layout.addWidget(self.save_blank_button)
        # control_layout.addStretch() # Push everything to the top
        # main_layout.addWidget(control_panel)

        self.change_display_mode = QPushButton("Change display mode")
        self.change_display_mode.clicked.connect(self._change_display_mode)
        self.change_display_mode.setStyleSheet("padding: 10px; font-size: 12pt; background-color: #4CAF50; color: white; border-radius: 5px;")
        control_layout.addWidget(self.change_display_mode)

        self.classification_result = QLabel(f"Result: {self.latest_result}")
        control_layout.addWidget(self.classification_result)

        control_layout.addStretch() # Push everything to the top
        main_layout.addWidget(control_panel)

        # --- Right Panel: Plot ---
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_panel.setStyleSheet("background-color: white; border: 1px solid #ddd;")

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_ylim(0, 1024) # Typical 10-bit ADC range for spectrometer
        self.ax.set_xlabel('Wavelengths [nm]', fontsize=12)
        self.ax.set_ylabel('Intensity', fontsize=12)
        self.ax.set_title('Spectrometer Live Data', fontsize=14)
        self.ax.grid(True, linestyle='--', alpha=0.7)
        # Initialize an empty plot for the live data using 'o-' for markers and lines
        self.line, = self.ax.plot([], [], 'o-', color='blue', markersize=6, linewidth=2)

        self.toolbar = NavigationToolbar(self.canvas, self) # Matplotlib navigation toolbar

        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)

        main_layout.addWidget(plot_panel)

    def _init_serial_worker(self):
        """Initializes the SerialWorker in a separate thread."""
        self.serial_thread = QThread()

        self.worker = SerialWorker(comport=COMPORT)
        self.worker.moveToThread(self.serial_thread)

        # Connect signals and slots
        self.serial_thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self._update_plot)
        self.worker.error_occurred.connect(self._handle_serial_error)

        # Start the thread
        self.serial_thread.start()
        print("SerialWorker thread started.")

    @pyqtSlot(np.ndarray)
    def _update_plot(self, data_array):
        """
        Slot to receive data from the SerialWorker and update the plot.
        """
        if len(data_array) != len(wavelengths_nm):
            print(f"Warning: Received data length ({len(data_array)}) does not match expected wavelengths length ({len(wavelengths_nm)}). Skipping plot update.")
            return
        
        self.latest_spectrum_data = data_array # Store for saving
        
        if not self.display_radiance:
            transmission = data_array/self.blank
            absorbance = compute_absorbance(transmission)
            self.line.set_data(wavelengths_nm, transmission)
            result = db.search(absorbance)
            self.latest_result = result
            self.classification_result.setText(f'Result: {self.latest_result[0]}, {self.latest_result[1]}')

        else:
            self.line.set_data(wavelengths_nm, data_array)
        self.ax.relim() # Recalculate axes limits
        self.ax.autoscale_view(True, True, True) # Rescale axes if necessary
        self.canvas.draw() # Redraw the canvas

    @pyqtSlot(str)
    def _handle_serial_error(self, message):
        """
        Slot to handle errors emitted by the SerialWorker.
        Displays a critical message box and stops the worker/thread.
        """
        QMessageBox.critical(self, "Serial Port Error", message)
        self.worker.stop()
        self.serial_thread.quit()
        self.serial_thread.wait() # Wait for the thread to finish cleanly

    def _save_blank(self):
        self.blank = np.array(self.latest_spectrum_data)
        print(self.blank)

    def _change_display_mode(self):
        self.display_radiance = not self.display_radiance

        if self.display_radiance:
            self.ax.set_ylabel('Intensity (counts)', fontsize=12)
            self.ax.set_ylim(0, 1024) # Typical 10-bit ADC range for spectrometer
        else:
            self.ax.set_ylabel('Transmission', fontsize=12)
            self.ax.set_ylim(0, 1)
 



    def _save_data_to_csv(self):
        """
        Saves the latest spectral data along with juice identity and concentration to a CSV file.
        """
        if self.latest_spectrum_data is None:
            QMessageBox.warning(self, "Save Data", "No spectral data available to save. Please wait for data to appear.")
            return

        juice_identity = self.juice_combo.currentText()
        concentration = self.concentration_input.text().strip()

        if not concentration:
            # Optionally make concentration mandatory, or allow "N/A"
            reply = QMessageBox.question(self, "Concentration Missing",
                                        "Concentration field is empty. Do you want to save anyway?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return

        # Prepare header if the file does not exist or is empty
        file_exists = os.path.exists(csv_filename) and os.path.getsize(csv_filename) > 0

        try:
            with open(csv_filename, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    # Write header: wavelengths, then 'Juice', 'Concentration', 'Timestamp'
                    header = [f"{l}" for l in labels] + ['Juice', 'Concentration [%]', 'Timestamp']
                    writer.writerow(header)

                # Prepare row data
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Ensure data is converted to a list for CSV writer
                row_data = list(self.latest_spectrum_data) + [juice_identity, concentration, timestamp]
                writer.writerow(row_data)

            QMessageBox.information(self, "Save Data", f"Data successfully saved to {csv_filename}")
        except IOError as e:
            QMessageBox.critical(self, "Save Data Error", f"Could not write to CSV file '{csv_filename}': {e}")
        except Exception as e:
            QMessageBox.critical(self, "Save Data Error", f"An unexpected error occurred while saving: {e}")

    def closeEvent(self, event):
        """
        Handles the window close event. Stops the serial worker thread gracefully.
        """
        if self.serial_thread.isRunning():
            print("Stopping serial worker and waiting for thread to finish...")
            self.worker.stop()
            self.serial_thread.quit()
            self.serial_thread.wait() # Wait for the thread to terminate
        event.accept() # Accept the close event

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = SpectrometerGUI()
    gui.show()
    sys.exit(app.exec_())
