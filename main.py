import sys
import os
import csv
import fitz
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QSlider, QFileDialog, QStatusBar, QMessageBox, QFrame,
    QToolBar, QSplitter, QDockWidget, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QColorDialog
)
from PyQt6.QtGui import QFont, QIcon, QAction, QColor
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF
from pdf_viewer import PDFViewer, COLORS, DraggableAnnotation  # your PDFViewer module
from ocr_processor import OCRManager

class BalloonTool(QMainWindow):
    """Professional PDF Auto-Ballooning Tool with Annotation Features"""

    def __init__(self):
        super().__init__()
        self.pdf_path = ""
        self.annotations = []  # List of annotation dictionaries
        self.current_color = "#007bff"  # Default blue
        self.ocr_manager = None  # Will initialize after UI setup

        # Window setup
        self.setWindowTitle("PDF Auto-Ballooning Tool")
        self.setGeometry(100, 100, 1280, 820)
        self.setStyleSheet(self.get_stylesheet())

        # UI setup
        self.init_ui()
        self.setup_status_bar()
        self.setup_toolbar()
        self.create_annotation_dock()

    def get_stylesheet(self):
        """Professional modern look with better contrast"""
        return f"""
            QMainWindow {{
                background-color: #f8f9fa;
                color: #212529;
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QPushButton {{
                background-color: #495057;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: #6c757d;
            }}
            QPushButton:disabled {{
                background-color: #ced4da;
                color: #6c757d;
            }}
            QPushButton:checked {{
                background-color: #007bff;
                color: #ffffff;
            }}
            QLabel {{
                color: #212529;
                font-size: 13px;
            }}
            QFrame {{
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }}
            QSlider::groove:horizontal {{
                background: #dee2e6;
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #495057;
                width: 18px;
                border-radius: 9px;
                margin: -6px 0;
            }}
            QStatusBar {{
                background-color: #e9ecef;
                color: #495057;
                font-size: 11px;
                border-top: 1px solid #dee2e6;
            }}
            QDockWidget {{
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                font-size: 13px;
            }}
            QListWidget {{
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 4px;
                color: #212529;
            }}
            QListWidget::item {{
                padding: 8px;
                margin: 2px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: #007bff;
                color: #ffffff;
            }}
            QLineEdit {{
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 8px;
                color: #212529;
            }}
        """

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(28, 28))
        toolbar.setStyleSheet("QToolBar { background-color: #ffffff; border-bottom: 1px solid #dee2e6; }")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        open_action = QAction("📁 Open PDF", self)
        open_action.triggered.connect(self.select_pdf)
        toolbar.addAction(open_action)

        save_action = QAction("💾 Save PDF", self)
        save_action.triggered.connect(self.save_pdf)
        toolbar.addAction(save_action)

        annotate_action = QAction("✏️ Annotate", self)
        annotate_action.triggered.connect(self.toggle_annotation_from_toolbar)
        toolbar.addAction(annotate_action)

        export_action = QAction("📊 Export CSV", self)
        export_action.triggered.connect(self.export_csv)
        toolbar.addAction(export_action)

        toolbar.addSeparator()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.file_area = self.create_file_area()
        main_layout.addWidget(self.file_area, 1)

        self.workspace = self.create_workspace()
        self.workspace.setVisible(False)
        main_layout.addWidget(self.workspace, 1)

    def create_file_area(self):
        widget = QWidget()
        widget.setStyleSheet("background-color: #f8f9fa;")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("PDF Auto-Ballooning Tool")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #007bff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        upload_frame = QFrame()
        upload_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px dashed #007bff;
                border-radius: 12px;
                padding: 60px;
                max-width: 480px;
            }
            QFrame:hover {
                border-color: #0056b3;
                background-color: #f0f8ff;
            }
        """)
        upload_layout = QVBoxLayout(upload_frame)
        upload_layout.setSpacing(15)

        file_icon = QLabel("📂")
        file_icon.setStyleSheet("font-size: 56px;")
        file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.addWidget(file_icon)

        upload_btn = QPushButton("Select PDF")
        upload_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; 
                padding: 14px 32px; 
                min-width: 200px;
                background-color: #007bff;
                color: white;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        upload_btn.clicked.connect(self.select_pdf)
        upload_layout.addWidget(upload_btn)
        layout.addWidget(upload_frame, 0, Qt.AlignmentFlag.AlignCenter)
        return widget

    def create_workspace(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        controls_panel = self.create_controls_panel()
        controls_panel.setMaximumWidth(260)
        splitter.addWidget(controls_panel)

        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.setStyleSheet("background-color: white; border: 1px solid #dee2e6; border-radius: 8px;")
        self.pdf_viewer.areaSelected.connect(self.add_balloon_from_selection)
        splitter.addWidget(self.pdf_viewer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(2)
        return splitter

    def create_controls_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        panel.setStyleSheet("background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 8px;")

        title = QLabel("Controls")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #007bff; margin-bottom: 10px;")
        layout.addWidget(title)
        
        self.color_btn = QPushButton("🎨 Color")
        self.color_btn.clicked.connect(self.choose_color)
        layout.addWidget(self.color_btn)

        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("0 / 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("font-weight: bold; color: #212529;")
        nav_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(32, 32)
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)
        layout.addWidget(self.make_separator())

        zoom_layout = QHBoxLayout()
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("color: #495057; font-weight: bold;")
        zoom_layout.addWidget(zoom_label)

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedSize(28, 28)
        zoom_out_btn.clicked.connect(lambda: self.zoom(0.8))
        zoom_layout.addWidget(zoom_out_btn)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setMinimumWidth(120)
        self.zoom_slider.valueChanged.connect(self.zoom_changed)
        zoom_layout.addWidget(self.zoom_slider)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(28, 28)
        zoom_in_btn.clicked.connect(lambda: self.zoom(1.2))
        zoom_layout.addWidget(zoom_in_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: #495057; font-weight: bold; min-width: 40px;")
        zoom_layout.addWidget(self.zoom_label)
        layout.addLayout(zoom_layout)
        layout.addWidget(self.make_separator())

        self.annotate_btn = QPushButton("✏️ Annotate")
        self.annotate_btn.setCheckable(True)
        self.annotate_btn.toggled.connect(self.toggle_area_selection)
        layout.addWidget(self.annotate_btn)

        layout.addWidget(self.make_separator())

        self.save_pdf_btn = QPushButton("💾 Save PDF")
        self.save_pdf_btn.setEnabled(False)
        self.save_pdf_btn.clicked.connect(self.save_pdf)
        layout.addWidget(self.save_pdf_btn)

        self.export_csv_btn = QPushButton("📊 Export CSV")
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.clicked.connect(self.export_csv)
        layout.addWidget(self.export_csv_btn)

        layout.addStretch()
        return panel

    def create_annotation_dock(self):
        self.dock = QDockWidget("Annotations", self)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock_widget = QWidget()
        dock_layout = QVBoxLayout(dock_widget)
        dock_layout.setSpacing(8)
        dock_layout.setContentsMargins(8, 8, 8, 8)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search annotations...")
        self.search_bar.textChanged.connect(self.filter_annotations)
        dock_layout.addWidget(self.search_bar)

        self.annotation_list = QListWidget()
        self.annotation_list.itemDoubleClicked.connect(self.focus_annotation_from_item)
        self.annotation_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.annotation_list.customContextMenuRequested.connect(self.show_annotation_context_menu)
        dock_layout.addWidget(self.annotation_list)

        self.dock.setWidget(dock_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setVisible(False)

    def make_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #dee2e6; margin: 6px 0;")
        return line
    
    def choose_color(self):
        """Open color picker dialog"""
        color = QColorDialog.getColor(QColor(self.current_color), self, "Choose Annotation Color")
        if color.isValid():
            self.current_color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {self.current_color}; color: white;")

    def setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Select a PDF to begin")

    # === Actions ===
    def select_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path):
        if self.pdf_viewer.load_pdf(file_path):
            self.pdf_path = file_path
            
            # Reset annotations
            self.annotations.clear()
            self.pdf_viewer.annotations.clear()
            self.annotation_list.clear()
            
            # Switch UI
            self.file_area.setVisible(False)
            self.workspace.setVisible(True)
            self.dock.setVisible(True)
            
            self.save_pdf_btn.setEnabled(True)
            self.export_csv_btn.setEnabled(True)
            self.update_navigation()
            self.status_bar.showMessage(f"Loaded: {os.path.basename(file_path)}")
            # Initialize OCR manager
            if not self.ocr_manager:
                self.ocr_manager = OCRManager(self)
        else:
            QMessageBox.critical(self, "Error", "Failed to load PDF")

    def update_navigation(self):
        current_page, total_pages = self.pdf_viewer.get_page_info()
        self.page_label.setText(f"{current_page} / {total_pages}")
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(current_page < total_pages)

    def prev_page(self):
        if self.pdf_viewer.prev_page():
            self.update_navigation()

    def next_page(self):
        if self.pdf_viewer.next_page():
            self.update_navigation()

    def zoom(self, factor):
        self.pdf_viewer.zoom_by_factor(factor)
        value = int(self.zoom_slider.value() * factor)
        self.zoom_slider.setValue(max(25, min(300, value)))

    def zoom_changed(self, value):
        self.zoom_label.setText(f"{value}%")
        self.pdf_viewer.zoom_to_level(value)

    def toggle_area_selection(self, checked):
        """Toggle annotation mode"""
        self.pdf_viewer.enable_selection(checked)
        if checked:
            self.annotate_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            self.status_bar.showMessage("Annotation Mode ON - Click and drag to select areas")
        else:
            self.annotate_btn.setStyleSheet("")
            self.status_bar.showMessage("Annotation Mode OFF")

    def toggle_annotation_from_toolbar(self):
        """Toggle annotation from toolbar"""
        self.annotate_btn.toggle()

    def add_balloon_from_selection(self, rect: QRectF):
        """Add a new annotation balloon from selected area"""
        number = len(self.annotations) + 1
        current_page, _ = self.pdf_viewer.get_page_info()
        
        ann = {
            "number": number,
            "page": current_page - 1,
            "rect": QRectF(rect),
            "color": self.current_color,
            "annotation_item": None
        }
        
        self.annotations.append(ann)
        self.pdf_viewer.annotations.append(ann)
        
        self.pdf_viewer.redraw_annotations_for_current_page(self.annotations)
        
        # Add to annotation list
        self.annotation_list.clear()
        for i, a in enumerate(self.annotations):
            item = QListWidgetItem(f"Annotation {a['number']} (p{a['page']+1})")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.annotation_list.addItem(item)
            
        # Start OCR processing for the new annotation
        if self.ocr_manager:
            current_page, _ = self.pdf_viewer.get_page_info()
            self.ocr_manager.process_annotation_ocr(number, self.pdf_path, current_page - 1, rect)
        
        self.status_bar.showMessage(f"Added annotation {number}")

    def focus_annotation_from_item(self, item: QListWidgetItem):
        """Focus on annotation when double-clicked in list"""
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int) or idx < 0 or idx >= len(self.annotations):
            return
        
        ann = self.annotations[idx]
        target_page = ann["page"]
        
        if target_page != self.pdf_viewer.current_page:
            self.pdf_viewer.go_to_page(target_page)
            self.update_navigation()
        
        pos_center = ann["rect"].center()
        self.pdf_viewer.centerOn(pos_center)

    def filter_annotations(self, text: str):
        """Filter annotation list based on search text"""
        query = text.strip().lower()
        self.annotation_list.clear()
        
        for i, ann in enumerate(self.annotations):
            label = f"Annotation {ann['number']} (p{ann['page']+1})"
            if not query or query in label.lower():
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.annotation_list.addItem(item)

    def show_annotation_context_menu(self, position):
        """Show context menu for annotation list items"""
        item = self.annotation_list.itemAt(position)
        if not item:
            return
        
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int):
            return
        
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        action = menu.exec(self.annotation_list.viewport().mapToGlobal(position))
        
        if action == delete_action:
            self.delete_annotation_by_index(idx)

    def delete_annotation_by_index(self, idx: int):
        """Delete annotation by index"""
        if idx < 0 or idx >= len(self.annotations):
            return
        
        ann = self.annotations.pop(idx)
        self.pdf_viewer.remove_annotation_graphics(ann)
        
        # Renumber remaining annotations
        for i, a in enumerate(self.annotations):
            a["number"] = i + 1
        
        # Rebuild list and refresh display
        self.annotation_list.clear()
        for i, a in enumerate(self.annotations):
            item = QListWidgetItem(f"Annotation {a['number']} (p{a['page']+1})")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.annotation_list.addItem(item)
        
        self.pdf_viewer.redraw_annotations_for_current_page(self.annotations)
        self.status_bar.showMessage("Deleted annotation")

    def save_pdf(self):
        if not self.pdf_path:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if file_path:
            try:
                doc = fitz.open(self.pdf_path)
                doc.save(file_path)
                doc.close()
                QMessageBox.information(self, "Success", f"PDF saved to: {file_path}")
                self.status_bar.showMessage("PDF saved successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save PDF: {str(e)}")

    def export_csv(self):
        """Export annotations with OCR text to CSV"""
        if not self.annotations:
            QMessageBox.information(self, "No annotations", "No annotations to export.")
            return
    
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Annotations", "", "CSV Files (*.csv)")
        if file_path:
            if self.ocr_manager and self.ocr_manager.export_annotations_with_ocr(file_path):
                QMessageBox.information(self, "Success", f"Annotations with OCR text exported to: {file_path}")
                self.status_bar.showMessage("Annotations exported successfully with OCR text")
            else:
                QMessageBox.critical(self, "Error", "Export failed")

    def closeEvent(self, event):
        if hasattr(self, "pdf_viewer"):
            self.pdf_viewer.closeEvent(event)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Auto-Ballooning Tool")
    app.setApplicationVersion("1.0")
    app.setFont(QFont("Segoe UI", 10))
    window = BalloonTool()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()