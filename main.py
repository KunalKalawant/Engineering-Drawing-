import sys
import os
import csv
import fitz
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QSlider, QFileDialog, QStatusBar, QMessageBox, QFrame,
    QToolBar, QSplitter, QDockWidget, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QColorDialog, QProgressBar, QCheckBox, QScrollArea
)
from PyQt6.QtGui import QFont, QIcon, QAction, QColor
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF, QThread, pyqtSignal
from pdf_viewer import PDFViewer, COLORS, DraggableAnnotation
from ocr_processor import OCRManager

class AutoAnnotationWorker(QThread):
    """Background thread for automatic text detection with padding tolerance"""
    
    progress_updated = pyqtSignal(int, str)
    annotations_found = pyqtSignal(list)
    finished = pyqtSignal()
    
    def __init__(self, pdf_path, page_num):
        super().__init__()
        self.pdf_path = pdf_path
        self.page_num = page_num
        self.detected_annotations = []
        self.vertical_padding = 15
        self.horizontal_padding = 10
        
    def run(self):
        try:
            self.progress_updated.emit(10, "Opening PDF...")
            doc = fitz.open(self.pdf_path)
            page = doc[self.page_num]
            page_rect = page.rect
            
            self.progress_updated.emit(30, "Detecting text blocks...")
            blocks = page.get_text("dict")["blocks"]
            
            text_regions = []
            for block in blocks:
                if "lines" in block:
                    original_bbox = block["bbox"]
                    padded_bbox = self.apply_padding_with_boundaries(original_bbox, page_rect)
                    
                    rect = QRectF(
                        padded_bbox[0] * 2, 
                        padded_bbox[1] * 2, 
                        (padded_bbox[2] - padded_bbox[0]) * 2, 
                        (padded_bbox[3] - padded_bbox[1]) * 2
                    )
                    
                    text_content = ""
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text_content += span["text"] + " "
                    
                    text_regions.append({
                        "rect": rect,
                        "text": text_content.strip(),
                        "confidence": len(text_content.strip()),
                        "original_bbox": original_bbox,
                        "padded_bbox": padded_bbox
                    })
            
            self.progress_updated.emit(60, f"Found {len(text_regions)} regions...")
            merged_regions = self.merge_overlapping_regions(text_regions, page_rect)
            self.progress_updated.emit(70, f"Merged to {len(merged_regions)} regions...")
            
            merged_regions.sort(key=lambda r: (r["rect"].top(), r["rect"].left()))
            
            for i, region in enumerate(merged_regions):
                if len(region["text"]) > 2:
                    ann = {
                        "number": i + 1,
                        "page": self.page_num,
                        "rect": region["rect"],
                        "color": COLORS[i % len(COLORS)],
                        "annotation_item": None,
                        "auto_detected": True,
                        "detected_text": region["text"],
                        "selected": True,
                        "has_padding": True,
                        "padding_info": {
                            "vertical": self.vertical_padding,
                            "horizontal": self.horizontal_padding
                        }
                    }
                    self.detected_annotations.append(ann)
            
            self.progress_updated.emit(90, "Processing complete...")
            doc.close()
            
            self.annotations_found.emit(self.detected_annotations)
            self.progress_updated.emit(100, "Auto-annotation complete!")
            
        except Exception as e:
            self.progress_updated.emit(0, f"Error: {str(e)}")
        finally:
            self.finished.emit()

    def apply_padding_with_boundaries(self, bbox, page_rect):
        x0, y0, x1, y1 = bbox
        padded_x0 = max(page_rect.x0, x0 - self.horizontal_padding)
        padded_y0 = max(page_rect.y0, y0 - self.vertical_padding)
        padded_x1 = min(page_rect.x1, x1 + self.horizontal_padding)
        padded_y1 = min(page_rect.y1, y1 + self.vertical_padding)
        return [padded_x0, padded_y0, padded_x1, padded_y1]

    def merge_overlapping_regions(self, regions, page_rect):
        if not regions:
            return regions
        regions.sort(key=lambda r: (r["rect"].top(), r["rect"].left()))
        merged = []
        current_region = regions[0].copy()
        
        for next_region in regions[1:]:
            if self.rectangles_overlap(current_region["rect"], next_region["rect"], 0.3):
                merged_rect = current_region["rect"].united(next_region["rect"])
                current_region = {
                    "rect": merged_rect,
                    "text": (current_region["text"] + " " + next_region["text"]).strip(),
                    "confidence": len(current_region["text"]),
                    "original_bbox": current_region.get("original_bbox"),
                    "padded_bbox": [merged_rect.x()/2, merged_rect.y()/2,
                                   (merged_rect.x()+merged_rect.width())/2,
                                   (merged_rect.y()+merged_rect.height())/2]
                }
            else:
                merged.append(current_region)
                current_region = next_region.copy()
        merged.append(current_region)
        return merged

    def rectangles_overlap(self, rect1, rect2, threshold=0.3):
        intersection = rect1.intersected(rect2)
        if intersection.isEmpty():
            return False
        smaller_area = min(rect1.width() * rect1.height(), rect2.width() * rect2.height())
        if smaller_area == 0:
            return False
        return (intersection.width() * intersection.height() / smaller_area) > threshold


class BalloonTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pdf_path = ""
        self.annotations = []
        self.current_color = "#007bff"
        self.ocr_manager = None
        self.auto_worker = None
        self.auto_annotations_temp = []
        self.deletion_mode = False

        self.setWindowTitle("PDF Auto-Ballooning Tool")
        self.setGeometry(100, 100, 1280, 820)
        self.setStyleSheet(self.get_stylesheet())

        self.init_ui()
        self.setup_status_bar()
        self.setup_toolbar()
        self.create_annotation_dock()

    def get_stylesheet(self):
        return """
            /* Main Window */
            QMainWindow { 
                background-color: #f5f7fa; 
            }
            
            /* Buttons */
            QPushButton { 
                background-color: #2563eb; 
                color: #ffffff; 
                border: none;
                padding: 10px 20px; 
                border-radius: 8px; 
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { 
                background-color: #1d4ed8; 
            }
            QPushButton:disabled { 
                background-color: #e5e7eb; 
                color: #9ca3af; 
            }
            QPushButton:checked { 
                background-color: #059669;
                border: 2px solid #047857;
            }
            
            /* Labels - FIX: Ensure dark text everywhere */
            QLabel { 
                color: #1f2937; 
                font-size: 14px;
                background-color: transparent;
            }
            
            /* Frames */
            QFrame { 
                background-color: #ffffff; 
                border: 1px solid #e5e7eb; 
                border-radius: 10px;
                padding: 12px;
            }
            
            /* List Widget - FIXED */
            QListWidget { 
                background-color: #ffffff; 
                border: 1px solid #d1d5db; 
                border-radius: 8px;
                color: #1f2937;
                font-size: 13px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { 
                padding: 8px;
                margin: 3px 2px;
                border-radius: 6px;
                background-color: #f9fafb;
                color: #374151;
                border: 1px solid transparent;
            }
            QListWidget::item:hover { 
                background-color: #e5e7eb;
                color: #1f2937;
                border: 1px solid #d1d5db;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #1e40af;
                border: 1px solid #3b82f6;
            }
            
            /* Line Edit (Search bar) */
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 12px;
                color: #1f2937;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
                background-color: #f0f9ff;
            }
            
            /* Checkbox */
            QCheckBox {
                color: #374151;
                spacing: 8px;
                background-color: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #d1d5db;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #2563eb;
            }
            
            /* Progress Bar */
            QProgressBar { 
                border: 2px solid #e5e7eb; 
                border-radius: 8px;
                text-align: center;
                color: #1f2937;
                background-color: #f3f4f6;
            }
            QProgressBar::chunk { 
                background-color: #10b981; 
                border-radius: 6px; 
            }
            
            /* Dock Widget */
            QDockWidget {
                background-color: #ffffff;
                color: #1f2937;
            }
            QDockWidget::title {
                background-color: #f3f4f6;
                padding: 8px;
                border-radius: 6px 6px 0 0;
                color: #1f2937;
                font-weight: 600;
                font-size: 14px;
            }
            
            /* Toolbar */
            QToolBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e5e7eb;
                padding: 6px;
                spacing: 8px;
            }
            QToolBar QToolButton {
                background-color: transparent;
                color: #374151;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QToolBar QToolButton:hover {
                background-color: #f3f4f6;
                border-color: #e5e7eb;
            }
            
            /* Slider */
            QSlider::groove:horizontal {
                height: 6px;
                background: #e5e7eb;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #2563eb;
                width: 16px;
                height: 16px;
                border-radius: 8px;
                margin: -5px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #1d4ed8;
            }
            
            /* Status Bar */
            QStatusBar {
                background-color: #f9fafb;
                color: #6b7280;
                border-top: 1px solid #e5e7eb;
            }
            
            /* Scroll Area */
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #f1f5f9;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #cbd5e1;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """

    def setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        
        open_action = QAction("📁 Open PDF", self)
        open_action.triggered.connect(self.select_pdf)
        toolbar.addAction(open_action)
        
        save_action = QAction("💾 Save PDF", self)
        save_action.triggered.connect(self.save_pdf)
        toolbar.addAction(save_action)
        
        auto_action = QAction("🤖 Auto Annotate", self)
        auto_action.triggered.connect(self.start_auto_annotation)
        toolbar.addAction(auto_action)
        
        export_action = QAction("📊 Export CSV", self)
        export_action.triggered.connect(self.export_csv)
        toolbar.addAction(export_action)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.file_area = self.create_file_area()
        main_layout.addWidget(self.file_area)

        self.workspace = self.create_workspace()
        self.workspace.setVisible(False)
        main_layout.addWidget(self.workspace)

    def create_file_area(self):
        widget = QWidget()
        widget.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f0f9ff, stop:1 #e0f2fe);")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("PDF Auto-Ballooning Tool")
        title.setStyleSheet("font-size: 36px; font-weight: bold; color: #0369a1; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Intelligent PDF annotation with automatic text detection")
        subtitle.setStyleSheet("font-size: 15px; color: #0c4a6e; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        upload_frame = QFrame()
        upload_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 3px dashed #0ea5e9;
                border-radius: 16px;
                padding: 70px;
                max-width: 500px;
            }
            QFrame:hover {
                border-color: #0284c7;
                background-color: #f0f9ff;
            }
        """)
        upload_layout = QVBoxLayout(upload_frame)
        upload_layout.setSpacing(20)

        file_icon = QLabel("📂")
        file_icon.setStyleSheet("font-size: 64px; background: transparent;")
        file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.addWidget(file_icon)

        upload_btn = QPushButton("Select PDF File")
        upload_btn.setStyleSheet("""
            QPushButton {
                font-size: 17px; 
                padding: 16px 40px; 
                min-width: 220px;
                background-color: #0ea5e9;
                color: white;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
        """)
        upload_btn.clicked.connect(self.select_pdf)
        upload_layout.addWidget(upload_btn)
        layout.addWidget(upload_frame, 0, Qt.AlignmentFlag.AlignCenter)
        return widget

    def create_workspace(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        controls_panel = self.create_controls_panel()
        controls_panel.setMaximumWidth(280)
        splitter.addWidget(controls_panel)

        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.areaSelected.connect(self.add_balloon_from_selection)
        self.pdf_viewer.annotation_clicked.connect(self.handle_annotation_click)
        splitter.addWidget(self.pdf_viewer)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        return splitter

    def create_controls_panel(self):
        # Create scroll area to contain all controls
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        panel = QWidget()
        panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #d7f0f7, stop:1 #f8fafc);
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 20, 16, 16)

        # Elegant Header with divider
        header_widget = QWidget()
        header_widget.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(0, 0, 0, 12)
        
        header = QLabel("Controls")
        header.setStyleSheet("""
            font-size: 20px; 
            font-weight: 600; 
            color: #0f172a; 
            background: transparent;
            letter-spacing: -0.5px;
        """)
        header_layout.addWidget(header)
        
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #e2e8f0; max-height: 2px;")
        header_layout.addWidget(divider)
        layout.addWidget(header_widget)

        # Navigation Section
        nav_frame = QFrame()
        nav_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setSpacing(12)
        
        nav_label = QLabel("Navigation")
        nav_label.setStyleSheet("""
            font-weight: 600; 
            color: #475569; 
            background: transparent;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        nav_layout.addWidget(nav_label)
        
        nav_controls = QHBoxLayout()
        nav_controls.setSpacing(8)
        
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(44, 44)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 16px;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #cbd5e1;
            }
        """)
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        nav_controls.addWidget(self.prev_btn)

        page_container = QWidget()
        page_container.setStyleSheet("background: transparent;")
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(2)
        
        self.page_label = QLabel("0 / 0")
        self.page_label.setStyleSheet("""
            font-weight: 600; 
            font-size: 18px; 
            background: transparent; 
            color: #0f172a;
        """)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(self.page_label)
        
        page_text = QLabel("Page")
        page_text.setStyleSheet("""
            font-size: 10px;
            color: #94a3b8;
            background: transparent;
        """)
        page_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(page_text)
        nav_controls.addWidget(page_container, 1)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(44, 44)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 16px;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #cbd5e1;
            }
        """)
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        nav_controls.addWidget(self.next_btn)
        nav_layout.addLayout(nav_controls)
        layout.addWidget(nav_frame)

        # Zoom Section
        zoom_frame = QFrame()
        zoom_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        zoom_layout = QVBoxLayout(zoom_frame)
        zoom_layout.setSpacing(12)
        
        zoom_header = QHBoxLayout()
        zoom_label = QLabel("Zoom")
        zoom_label.setStyleSheet("""
            font-weight: 600; 
            color: #475569; 
            background: transparent;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        zoom_header.addWidget(zoom_label)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("""
            font-weight: 600; 
            background: transparent; 
            color: #2563eb;
            font-size: 13px;
        """)
        zoom_header.addWidget(self.zoom_label)
        zoom_layout.addLayout(zoom_header)
        
        zoom_controls = QHBoxLayout()
        zoom_controls.setSpacing(8)
        
        zoom_out = QPushButton("−")
        zoom_out.setFixedSize(36, 36)
        zoom_out.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 18px;
                color: #475569;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        zoom_out.clicked.connect(lambda: self.zoom(0.8))
        zoom_controls.addWidget(zoom_out)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.zoom_changed)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #e2e8f0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2563eb;
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -6px 0;
                border: 2px solid #ffffff;
            }
            QSlider::handle:horizontal:hover {
                background: #1d4ed8;
            }
        """)
        zoom_controls.addWidget(self.zoom_slider, 1)

        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(36, 36)
        zoom_in.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-size: 18px;
                color: #475569;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        zoom_in.clicked.connect(lambda: self.zoom(1.2))
        zoom_controls.addWidget(zoom_in)
        zoom_layout.addLayout(zoom_controls)
        layout.addWidget(zoom_frame)

        # Tools Section
        tools_frame = QFrame()
        tools_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        tools_layout = QVBoxLayout(tools_frame)
        tools_layout.setSpacing(10)
        
        tools_label = QLabel("Tools")
        tools_label.setStyleSheet("""
            font-weight: 600; 
            color: #475569; 
            background: transparent;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        """)
        tools_layout.addWidget(tools_label)
        
        # Color picker with elegant style
        self.color_btn = QPushButton("🎨  Choose Color")
        self.color_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 16px;
                text-align: left;
                font-size: 13px;
                font-weight: 500;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #cbd5e1;
            }
        """)
        self.color_btn.clicked.connect(self.choose_color)
        tools_layout.addWidget(self.color_btn)
        
        self.annotate_btn = QPushButton("✏️  Manual")
        self.annotate_btn.setCheckable(True)
        self.annotate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                font-weight: 600;
                color: white;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:checked {
                background-color: #059669;
                border: 2px solid #047857;
            }
        """)
        self.annotate_btn.toggled.connect(self.toggle_area_selection)
        tools_layout.addWidget(self.annotate_btn)

        self.auto_annotate_btn = QPushButton("🤖  Auto Detect")
        self.auto_annotate_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b5cf6;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                font-weight: 600;
                color: white;
            }
            QPushButton:hover {
                background-color: #7c3aed;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
        """)
        self.auto_annotate_btn.clicked.connect(self.start_auto_annotation)
        self.auto_annotate_btn.setEnabled(False)
        tools_layout.addWidget(self.auto_annotate_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #f1f5f9;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #8b5cf6;
                border-radius: 3px;
            }
        """)
        tools_layout.addWidget(self.progress_bar)
        
        self.deletion_mode_btn = QPushButton("🗑️  Delete")
        self.deletion_mode_btn.setCheckable(True)
        self.deletion_mode_btn.setStyleSheet("""
            QPushButton { 
                background-color: #dc2626;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                font-weight: 600;
                color: white;
            }
            QPushButton:hover { 
                background-color: #b91c1c; 
            }
            QPushButton:checked { 
                background-color: #991b1b; 
                border: 2px solid #7f1d1d;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
        """)
        self.deletion_mode_btn.toggled.connect(self.toggle_deletion_mode)
        self.deletion_mode_btn.setEnabled(False)
        tools_layout.addWidget(self.deletion_mode_btn)
        
        layout.addWidget(tools_frame)

        # Export Section
        export_frame = QFrame()
        export_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        export_layout = QVBoxLayout(export_frame)
        export_layout.setSpacing(10)
        
        export_label = QLabel("Export")
        export_label.setStyleSheet("""
            font-weight: 600; 
            color: #475569; 
            background: transparent;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        """)
        export_layout.addWidget(export_label)
        
        self.save_pdf_btn = QPushButton("💾  Save PDF")
        self.save_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 16px;
                text-align: left;
                font-size: 13px;
                font-weight: 500;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #cbd5e1;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #cbd5e1;
                border-color: #f1f5f9;
            }
        """)
        self.save_pdf_btn.setEnabled(False)
        self.save_pdf_btn.clicked.connect(self.save_pdf)
        export_layout.addWidget(self.save_pdf_btn)

        self.export_csv_btn = QPushButton("📊  Export CSV")
        self.export_csv_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8fafc;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 16px;
                text-align: left;
                font-size: 13px;
                font-weight: 500;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #cbd5e1;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #cbd5e1;
                border-color: #f1f5f9;
            }
        """)
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.clicked.connect(self.export_csv)
        export_layout.addWidget(self.export_csv_btn)
        layout.addWidget(export_frame)
        
        layout.addStretch()
        
        # Set the panel as the scroll area's widget
        scroll_area.setWidget(panel)
        return scroll_area

    def create_annotation_dock(self):
        self.dock = QDockWidget("Annotations", self)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock_widget = QWidget()
        dock_widget.setStyleSheet("background-color: #d7f0f7;")
        dock_layout = QVBoxLayout(dock_widget)
        dock_layout.setContentsMargins(12, 12, 12, 12)
        dock_layout.setSpacing(12)

        # Header
        header = QLabel("📋 Annotation Manager")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #1f2937; background: transparent;")
        dock_layout.addWidget(header)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search annotations...")
        self.search_bar.textChanged.connect(self.filter_annotations)
        dock_layout.addWidget(self.search_bar)

        # Auto controls
        self.auto_controls = QFrame()
        self.auto_controls.setVisible(False)
        self.auto_controls.setStyleSheet("background-color: #eff6ff; border: 2px solid #3b82f6;")
        auto_layout = QVBoxLayout(self.auto_controls)
        
        auto_title = QLabel("🤖 Auto-Detected Annotations")
        auto_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #1e40af; background: transparent;")
        auto_layout.addWidget(auto_title)
        
        auto_btns = QHBoxLayout()
        self.select_all_btn = QPushButton("✓ Select All")
        self.select_all_btn.clicked.connect(self.select_all_auto_annotations)
        auto_btns.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("✗ Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all_auto_annotations)
        auto_btns.addWidget(self.deselect_all_btn)
        auto_layout.addLayout(auto_btns)
        
        self.apply_auto_btn = QPushButton("✓ Apply Selected")
        self.apply_auto_btn.setStyleSheet("background-color: #10b981;")
        self.apply_auto_btn.clicked.connect(self.apply_selected_auto_annotations)
        auto_layout.addWidget(self.apply_auto_btn)
        
        self.cancel_auto_btn = QPushButton("✗ Cancel")
        self.cancel_auto_btn.setStyleSheet("background-color: #6b7280;")
        self.cancel_auto_btn.clicked.connect(self.cancel_auto_annotation)
        auto_layout.addWidget(self.cancel_auto_btn)
        dock_layout.addWidget(self.auto_controls)

        self.annotation_list = QListWidget()
        self.annotation_list.itemDoubleClicked.connect(self.focus_annotation_from_item)
        self.annotation_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.annotation_list.customContextMenuRequested.connect(self.show_annotation_context_menu)
        dock_layout.addWidget(self.annotation_list)

        self.dock.setWidget(dock_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.setVisible(False)

    def toggle_deletion_mode(self, checked):
        """Toggle deletion mode - click circles to delete"""
        self.deletion_mode = checked
        self.pdf_viewer.set_deletion_mode(checked)
        
        if checked:
            self.status_bar.showMessage("🗑️ DELETION MODE: Click on circles to delete annotations")
            if self.annotate_btn.isChecked():
                self.annotate_btn.setChecked(False)
        else:
            self.status_bar.showMessage("Deletion mode OFF")

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.current_color), self)
        if color.isValid():
            self.current_color = color.name()

    def setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def select_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path):
        if self.pdf_viewer.load_pdf(file_path):
            self.pdf_path = file_path
            self.annotations.clear()
            self.pdf_viewer.annotations.clear()
            self.annotation_list.clear()
            
            self.file_area.setVisible(False)
            self.workspace.setVisible(True)
            self.dock.setVisible(True)
            
            self.save_pdf_btn.setEnabled(True)
            self.export_csv_btn.setEnabled(True)
            self.auto_annotate_btn.setEnabled(True)
            self.deletion_mode_btn.setEnabled(True)
            self.update_navigation()
            
            if not self.ocr_manager:
                self.ocr_manager = OCRManager(self)

    def handle_annotation_click(self, annotation_index):
        """Handle clicking on annotation - used for deletion"""
        if self.deletion_mode and 0 <= annotation_index < len(self.annotations):
            self.delete_annotation_by_index(annotation_index)

    def update_navigation(self):
        current_page, total_pages = self.pdf_viewer.get_page_info()
        self.page_label.setText(f"{current_page} / {total_pages}")
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(current_page < total_pages)

    def prev_page(self):
        if self.pdf_viewer.prev_page():
            self.update_navigation()
            self.cancel_auto_annotation()

    def next_page(self):
        if self.pdf_viewer.next_page():
            self.update_navigation()
            self.cancel_auto_annotation()

    def zoom(self, factor):
        self.pdf_viewer.zoom_by_factor(factor)
        value = int(self.zoom_slider.value() * factor)
        self.zoom_slider.setValue(max(25, min(300, value)))

    def zoom_changed(self, value):
        self.zoom_label.setText(f"{value}%")
        self.pdf_viewer.zoom_to_level(value)

    def toggle_area_selection(self, checked):
        self.pdf_viewer.enable_selection(checked)
        if checked:
            self.status_bar.showMessage("✏️ Manual Annotation Mode: Drag to select area")
            if self.deletion_mode_btn.isChecked():
                self.deletion_mode_btn.setChecked(False)
        else:
            self.status_bar.showMessage("Manual Annotation Mode OFF")

    def start_auto_annotation(self):
        if not self.pdf_path:
            return
        
        current_page, _ = self.pdf_viewer.get_page_info()
        self.auto_annotate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.auto_worker = AutoAnnotationWorker(self.pdf_path, current_page - 1)
        self.auto_worker.progress_updated.connect(self.update_auto_progress)
        self.auto_worker.annotations_found.connect(self.show_auto_annotations_preview)
        self.auto_worker.finished.connect(self.auto_annotation_finished)
        self.auto_worker.start()
        
        self.status_bar.showMessage("🤖 Auto-detecting text regions...")

    def update_auto_progress(self, progress, message):
        self.progress_bar.setValue(progress)
        self.status_bar.showMessage(message)

    def show_auto_annotations_preview(self, detected_annotations):
        self.auto_annotations_temp = detected_annotations
        self.auto_controls.setVisible(True)
        self.display_auto_annotations_preview()
        self.pdf_viewer.preview_auto_annotations(detected_annotations)

    def display_auto_annotations_preview(self):
        self.annotation_list.clear()
        
        for i, ann in enumerate(self.auto_annotations_temp):
            item = QListWidgetItem()
            widget = QWidget()
            widget.setStyleSheet("background-color: transparent;")
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(6, 4, 6, 4)
            
            checkbox = QCheckBox()
            checkbox.setChecked(ann.get("selected", True))
            checkbox.stateChanged.connect(lambda state, idx=i: self.toggle_auto_annotation_selection(idx, state))
            layout.addWidget(checkbox)
            
            text_preview = ann.get("detected_text", "")[:35]
            if len(ann.get("detected_text", "")) > 35:
                text_preview += "..."
            padding_indicator = " [+P]" if ann.get("has_padding") else ""
            label = QLabel(f"#{ann['number']}: {text_preview}{padding_indicator}")
            label.setStyleSheet("color: #374151; background: transparent; font-size: 12px;")
            label.setToolTip(ann.get("detected_text", ""))
            layout.addWidget(label, 1)
            
            widget.setLayout(layout)
            item.setSizeHint(widget.sizeHint())
            self.annotation_list.addItem(item)
            self.annotation_list.setItemWidget(item, widget)

    def toggle_auto_annotation_selection(self, index, state):
        if 0 <= index < len(self.auto_annotations_temp):
            self.auto_annotations_temp[index]["selected"] = (state == Qt.CheckState.Checked.value)
            self.pdf_viewer.preview_auto_annotations(self.auto_annotations_temp)

    def select_all_auto_annotations(self):
        for ann in self.auto_annotations_temp:
            ann["selected"] = True
        self.display_auto_annotations_preview()
        self.pdf_viewer.preview_auto_annotations(self.auto_annotations_temp)

    def deselect_all_auto_annotations(self):
        for ann in self.auto_annotations_temp:
            ann["selected"] = False
        self.display_auto_annotations_preview()
        self.pdf_viewer.preview_auto_annotations(self.auto_annotations_temp)

    def apply_selected_auto_annotations(self):
        selected = [ann for ann in self.auto_annotations_temp if ann.get("selected", False)]
        
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select at least one annotation.")
            return
        
        base_number = len(self.annotations) + 1
        for i, ann in enumerate(selected):
            ann["number"] = base_number + i
            ann["color"] = COLORS[(base_number + i - 1) % len(COLORS)]
            if "selected" in ann:
                del ann["selected"]
            if "auto_detected" in ann:
                del ann["auto_detected"]
            
        self.annotations.extend(selected)
        self.pdf_viewer.annotations.extend(selected)
        
        self.pdf_viewer.clear_preview_annotations()
        self.pdf_viewer.redraw_annotations_for_current_page(self.annotations)
        
        if self.ocr_manager:
            for ann in selected:
                self.ocr_manager.process_annotation_ocr(ann["number"], self.pdf_path, ann["page"], ann["rect"])
        
        self.cancel_auto_annotation()
        self.display_annotations_list()  # FIX: Refresh the list after applying
        self.status_bar.showMessage(f"✓ Applied {len(selected)} annotations")

    def cancel_auto_annotation(self):
        self.auto_controls.setVisible(False)
        self.auto_annotations_temp.clear()
        self.pdf_viewer.clear_preview_annotations()
        self.display_annotations_list()

    def auto_annotation_finished(self):
        self.progress_bar.setVisible(False)
        self.auto_annotate_btn.setEnabled(True)
        if self.auto_worker:
            self.auto_worker.quit()
            self.auto_worker.wait()
            self.auto_worker = None

    def add_balloon_from_selection(self, rect: QRectF):
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
        self.display_annotations_list()
        
        if self.ocr_manager:
            self.ocr_manager.process_annotation_ocr(number, self.pdf_path, current_page - 1, rect)
        
        self.status_bar.showMessage(f"✓ Added annotation #{number}")

    def display_annotations_list(self):
        # FIX: Don't clear if in auto mode, but always show current annotations
        if self.auto_controls.isVisible():
            return
        
        self.annotation_list.clear()
        
        for i, a in enumerate(self.annotations):
            item = QListWidgetItem()
            widget = QWidget()
            widget.setStyleSheet("background-color: transparent;")
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(6, 4, 6, 4)
            
            padding_indicator = " [+P]" if a.get("has_padding") else ""
            label = QLabel(f"Annotation #{a['number']} (Page {a['page']+1}){padding_indicator}")
            label.setStyleSheet("color: #374151; background: transparent; font-size: 13px;")
            layout.addWidget(label, 1)
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedSize(28, 28)
            delete_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ef4444; 
                    color: white; 
                    padding: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
            """)
            delete_btn.setToolTip("Delete this annotation")
            delete_btn.clicked.connect(lambda checked, idx=i: self.delete_annotation_by_index(idx))
            layout.addWidget(delete_btn)
            
            widget.setLayout(layout)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, i)
            
            self.annotation_list.addItem(item)
            self.annotation_list.setItemWidget(item, widget)

    def focus_annotation_from_item(self, item: QListWidgetItem):
        if self.auto_controls.isVisible():
            return
        
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int) or idx < 0 or idx >= len(self.annotations):
            return
        
        ann = self.annotations[idx]
        if ann["page"] != self.pdf_viewer.current_page:
            self.pdf_viewer.go_to_page(ann["page"])
            self.update_navigation()
        
        self.pdf_viewer.centerOn(ann["rect"].center())
        self.status_bar.showMessage(f"Focused on annotation #{ann['number']}")

    def filter_annotations(self, text: str):
        if self.auto_controls.isVisible():
            return
        
        query = text.strip().lower()
        
        for i in range(self.annotation_list.count()):
            item = self.annotation_list.item(i)
            widget = self.annotation_list.itemWidget(item)
            if widget:
                label = widget.findChild(QLabel)
                if label:
                    should_show = not query or query in label.text().lower()
                    item.setHidden(not should_show)

    def show_annotation_context_menu(self, position):
        if self.auto_controls.isVisible():
            return
        
        item = self.annotation_list.itemAt(position)
        if not item or item.isHidden():
            return
        
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int):
            return
        
        menu = QMenu(self)
        delete_action = menu.addAction("⚠️ DELETE (Permanent)")
        action = menu.exec(self.annotation_list.viewport().mapToGlobal(position))
        
        if action == delete_action:
            self.delete_annotation_by_index(idx)

    def delete_annotation_by_index(self, idx: int):
        """Permanently delete annotation - FIXED to refresh list properly"""
        if idx < 0 or idx >= len(self.annotations):
            return
        
        ann = self.annotations[idx]
        reply = QMessageBox.question(
            self, "Delete Annotation", 
            f"Permanently delete Annotation #{ann['number']}?\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        deleted_ann = self.annotations.pop(idx)
        self.pdf_viewer.remove_annotation_graphics(deleted_ann)
        
        if self.ocr_manager and deleted_ann.get("number") in self.ocr_manager.annotation_texts:
            del self.ocr_manager.annotation_texts[deleted_ann["number"]]
        
        for i, a in enumerate(self.annotations):
            old_number = a["number"]
            a["number"] = i + 1
            
            if self.ocr_manager and old_number in self.ocr_manager.annotation_texts:
                self.ocr_manager.annotation_texts[a["number"]] = self.ocr_manager.annotation_texts.pop(old_number)
        
        # FIX: Always refresh the list after deletion
        self.pdf_viewer.redraw_annotations_for_current_page(self.annotations)
        self.display_annotations_list()
        self.status_bar.showMessage(f"✓ Deleted annotation #{deleted_ann['number']}")

    def save_pdf(self):
        """Save PDF with annotations rendered onto it"""
        if not self.pdf_path:
            QMessageBox.warning(self, "No PDF", "Please open a PDF file first.")
            return
        
        if not self.annotations:
            QMessageBox.information(self, "No Annotations", 
                                    "No annotations to save. The PDF has no annotations yet.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return
            
        try:
            doc = fitz.open(self.pdf_path)
            
            for ann in self.annotations:
                page = doc[ann["page"]]
                
                rect = fitz.Rect(
                    ann["rect"].x() / 2,
                    ann["rect"].y() / 2,
                    (ann["rect"].x() + ann["rect"].width()) / 2,
                    (ann["rect"].y() + ann["rect"].height()) / 2
                )
                
                color = QColor(ann["color"])
                rgb = (color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0)
                
                circle_rect = fitz.Rect(
                    rect.x0 - 15,
                    rect.y0 - 15,
                    rect.x0 + 15,
                    rect.y0 + 15
                )
                
                rect_annot = page.add_rect_annot(rect)
                rect_annot.set_colors(stroke=rgb)
                rect_annot.set_border(width=2)
                rect_annot.update()
                
                circle_annot = page.add_circle_annot(circle_rect)
                circle_annot.set_colors(stroke=rgb, fill=rgb)
                circle_annot.set_border(width=2)
                circle_annot.update()
                
                text_annot = page.add_freetext_annot(
                    fitz.Rect(circle_rect.x0, circle_rect.y0 + 5, 
                             circle_rect.x1, circle_rect.y1),
                    str(ann["number"]),
                    fontsize=12,
                    text_color=(1, 1, 1),
                    fill_color=rgb,
                    align=1
                )
                text_annot.set_border(width=0)
                text_annot.update()
            
            doc.save(file_path, garbage=4, deflate=True, clean=True)
            doc.close()
            
            QMessageBox.information(self, "Success", 
                                    f"PDF saved with {len(self.annotations)} annotations to:\n{file_path}")
            self.status_bar.showMessage(f"✓ PDF saved successfully with {len(self.annotations)} annotations")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save PDF:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def export_csv(self):
        if not self.annotations:
            QMessageBox.information(self, "No Annotations", "No annotations to export.")
            return
    
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Annotations", "", "CSV Files (*.csv)")
        if file_path:
            if self.ocr_manager and self.ocr_manager.export_annotations_with_ocr(file_path):
                QMessageBox.information(self, "Success", f"Annotations exported to:\n{file_path}")
                self.status_bar.showMessage("✓ Annotations exported successfully")
            else:
                QMessageBox.critical(self, "Error", "Export failed")

    def closeEvent(self, event):
        if hasattr(self, "pdf_viewer"):
            self.pdf_viewer.closeEvent(event)
        if self.auto_worker and self.auto_worker.isRunning():
            self.auto_worker.quit()
            self.auto_worker.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Auto-Ballooning Tool")
    
    # Use system font instead of Segoe UI
    if sys.platform == "darwin":  # macOS
        app.setFont(QFont("SF Pro Text", 10))
    else:
        app.setFont(QFont("Arial", 10))
    
    window = BalloonTool()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
