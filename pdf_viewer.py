import sys
import os
import math
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem,
    QRubberBand, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsItemGroup,QGraphicsPolygonItem
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont, QMouseEvent, QBrush, QPolygonF

import fitz

# Predefined colors for annotations
COLORS = [
    "#FF4444",  # Red
    "#44FF44",  # Green  
    "#4444FF",  # Blue
    "#FFAA00",  # Orange
    "#AA44FF",  # Purple
    "#00FFAA",  # Teal
    "#FF0088",  # Pink
    "#88FF00",  # Lime
    "#0088FF",  # Sky Blue
    "#FF8800"   # Dark Orange
]

class DraggableAnnotation(QGraphicsItemGroup):
    """Complete annotation system with tethered pointer, circle, and line"""
    
    def __init__(self, rect: QRectF, number: int, color: str):
        super().__init__()
        self.rect = rect
        self.number = number
        self.color = color
        self.default_circle_pos = rect.topRight() + QPointF(30, -20)
    
        # Create components
        self.highlight_box = self.create_highlight_box()
        self.circle = self.create_number_circle()
        self.line = self.create_connecting_line()
        self.arrow = self.create_arrow_head()
    
    # Add to group
        self.addToGroup(self.highlight_box)
        self.addToGroup(self.line)
        self.addToGroup(self.arrow)
    
    # DON'T add circle to group - keep it separate so it stays draggable
    # Instead, make it a child of the scene directly
    
    # Make the group non-movable
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, False)

    # Set initial position for circle
        self.circle.setPos(self.default_circle_pos)
        self.update_connections()

    def create_highlight_box(self):
        """Create colored highlight box"""
        box = QGraphicsRectItem(self.rect)
        color = QColor(self.color)
        color.setAlpha(100)  # Semi-transparent
        box.setBrush(QBrush(color))
        box.setPen(QPen(QColor(self.color), 2))
        box.setZValue(-1)  # Behind other items
        return box

    def create_number_circle(self):
        """Create draggable circle with number"""
        class DraggableCircle(QGraphicsEllipseItem):
            def __init__(self, rect, annotation_parent):
                super().__init__(rect)
                self.annotation_parent = annotation_parent

            def itemChange(self, change, value):
                if change == self.GraphicsItemChange.ItemPositionHasChanged:
                    if self.annotation_parent:
                        self.annotation_parent.update_connections()
                return super().itemChange(change, value)
    
        circle = DraggableCircle(QRectF(-15, -15, 30, 30), self)
        circle.setBrush(QBrush(QColor(self.color)))
        circle.setPen(QPen(QColor(self.color).darker(150), 2))
        circle.setZValue(2)
    
    # Enable dragging
        circle.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        circle.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
    
        # Add number text
        self.number_text = QGraphicsTextItem(str(self.number))
        self.number_text.setDefaultTextColor(QColor("white"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        self.number_text.setFont(font)
    
        text_rect = self.number_text.boundingRect()
        self.number_text.setPos(-text_rect.width()/2, -text_rect.height()/2)
        self.number_text.setParentItem(circle)
    
        return circle

    def create_connecting_line(self):
        """Create line connecting circle to box"""
        self.line_item = QGraphicsLineItem()
        self.line_item.setPen(QPen(QColor(self.color), 2))
        self.line_item.setZValue(1)
        return self.line_item

    def create_arrow_head(self):
        """Create arrow head pointing to box"""
        self.arrow_polygon = QGraphicsPolygonItem()
        self.arrow_polygon.setBrush(QBrush(QColor(self.color)))
        self.arrow_polygon.setPen(QPen(QColor(self.color), 1))
        self.arrow_polygon.setZValue(1)
        return self.arrow_polygon

    def update_connections(self):
        """Update line and arrow to connect circle to nearest point on box"""
        circle_center = self.circle.pos()
        box_center = self.rect.center()
        
        # Find closest point on box perimeter to circle
        closest_point = self.get_closest_point_on_rect(circle_center, self.rect)
        
        # Update line
        self.line_item.setLine(circle_center.x(), circle_center.y(), 
                              closest_point.x(), closest_point.y())
        
        # Update arrow head
        self.update_arrow_head(circle_center, closest_point)

    def get_closest_point_on_rect(self, point: QPointF, rect: QRectF) -> QPointF:
        """Find closest point on rectangle perimeter to given point"""
        x = max(rect.left(), min(point.x(), rect.right()))
        y = max(rect.top(), min(point.y(), rect.bottom()))
        
        # If point is inside rect, find closest edge
        if rect.contains(point):
            distances = [
                abs(point.x() - rect.left()),    # Left edge
                abs(point.x() - rect.right()),   # Right edge  
                abs(point.y() - rect.top()),     # Top edge
                abs(point.y() - rect.bottom())   # Bottom edge
            ]
            min_dist_idx = distances.index(min(distances))
            
            if min_dist_idx == 0:    # Left edge
                x = rect.left()
            elif min_dist_idx == 1:  # Right edge  
                x = rect.right()
            elif min_dist_idx == 2:  # Top edge
                y = rect.top()
            else:                    # Bottom edge
                y = rect.bottom()
        
        return QPointF(x, y)

    def update_arrow_head(self, start: QPointF, end: QPointF):
        """Create arrow head pointing from start to end"""
        # Calculate angle
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return  # No arrow if points are too close
            
        angle = math.atan2(dy, dx)
        
        # Arrow head size
        arrow_length = 12
        arrow_width = 6
        
        # Calculate arrow points
        tip = end
        
        # Back points of arrow
        back_angle1 = angle + 2.8  # ~160 degrees
        back_angle2 = angle - 2.8  # ~160 degrees
        
        p1 = QPointF(tip.x() + arrow_length * math.cos(back_angle1),
                     tip.y() + arrow_length * math.sin(back_angle1))
        p2 = QPointF(tip.x() + arrow_length * math.cos(back_angle2),
                     tip.y() + arrow_length * math.sin(back_angle2))
        
        # Create arrow polygon
        arrow_points = QPolygonF([tip, p1, p2])
        self.arrow_polygon.setPolygon(arrow_points)

    

    def get_circle_position(self) -> QPointF:
        """Get current circle position in scene coordinates"""
        return self.circle.scenePos()

    def set_circle_position(self, pos: QPointF):
        """Set circle position and update connections"""
        self.circle.setPos(pos)
        self.update_connections()


class PDFViewer(QGraphicsView):
    """Enhanced PDF viewer with advanced annotation support"""
    
    areaSelected = pyqtSignal(QRectF)
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._pan_start = QPointF()
        self._panning = False
        self.selection_mode = False
        self.rubberBand = None
        self.origin = None
        self.pdf_doc = None
        self.current_page = 0
        self.annotations = []
        
        # Setup view
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setStyleSheet("""
            QGraphicsView {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

    def enable_selection(self, enabled: bool):
        """Enable or disable area selection mode"""
        self.selection_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def load_pdf(self, file_path):
        """Load PDF document"""
        try:
            if self.pdf_doc:
                self.pdf_doc.close()
            
            self.pdf_doc = fitz.open(file_path)
            self.current_page = 0
            self.display_page()
            return True
            
        except Exception as e:
            print(f"Error loading PDF: {e}")
            return False

    def display_page(self):
        """Display current page in the viewer"""
        if not self.pdf_doc:
            return
        
        try:
            page = self.pdf_doc[self.current_page]
            mat = fitz.Matrix(2.0, 2.0)  # High resolution
            pix = page.get_pixmap(matrix=mat)
            
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            
            self.scene.clear()
            pixmap_item = self.scene.addPixmap(pixmap)
            pixmap_item.setZValue(-2)  # PDF content at bottom
            
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
            self.redraw_annotations_for_current_page(self.annotations)
            
        except Exception as e:
            print(f"Error displaying page: {e}")

    def go_to_page(self, page_index):
        """Navigate to specific page (0-based index)"""
        if self.pdf_doc and 0 <= page_index < len(self.pdf_doc):
            self.current_page = page_index
            self.display_page()
            return True
        return False

    def next_page(self):
        """Navigate to next page"""
        if self.pdf_doc and self.current_page < len(self.pdf_doc) - 1:
            self.current_page += 1
            self.display_page()
            return True
        return False

    def prev_page(self):
        """Navigate to previous page"""
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self.display_page()
            return True
        return False

    def get_page_info(self):
        """Get current page information"""
        if self.pdf_doc:
            return self.current_page + 1, len(self.pdf_doc)
        return 0, 0

    def zoom_to_level(self, level):
        """Set zoom to specific percentage level"""
        self.resetTransform()
        if self.pdf_doc:
            scale = level / 100.0
            self.scale(scale, scale)

    def zoom_by_factor(self, factor):
        """Zoom by multiplication factor"""
        self.scale(factor, factor)

    def create_annotation(self, rect: QRectF, number: int, color: str):
        """Create a complete tethered annotation"""
        annotation = DraggableAnnotation(rect, number, color)
        self.scene.addItem(annotation)
        return annotation

    def remove_annotation_graphics(self, ann: dict):
        """Remove graphics for an annotation"""
        if "annotation_item" in ann and ann["annotation_item"] is not None:
            item = ann["annotation_item"]
            if item.scene() is not None:
                self.scene.removeItem(item)
            ann["annotation_item"] = None

    def redraw_annotations_for_current_page(self, annotations: list):
        """Redraw annotations for the current page"""
        current_page = self.current_page
    
    # Remove existing annotation graphics
        items_to_remove = []
        for item in self.scene.items():
            if isinstance(item, DraggableAnnotation) or hasattr(item, 'annotation_parent'):
                items_to_remove.append(item)
    
        for item in items_to_remove:
            self.scene.removeItem(item)
    
    # Clear references
        for ann in annotations:
            ann["annotation_item"] = None
    
    # Recreate annotations for current page
        for ann in annotations:
            if ann["page"] == current_page:
                annotation_item = self.create_annotation(ann["rect"], ann["number"], ann["color"])
            
                # Add the group to scene
                self.scene.addItem(annotation_item)

                # Add the circle separately to scene so it stays draggable
                self.scene.addItem(annotation_item.circle)
            
                ann["annotation_item"] = annotation_item

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for selection and panning"""
        if self.selection_mode and event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            if not self.rubberBand:
                self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
        elif event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for selection and panning"""
        if self.selection_mode and self.rubberBand and self.origin:
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            self.rubberBand.setGeometry(rect)
        elif self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release for selection and panning"""
        if self.selection_mode and self.rubberBand and event.button() == Qt.MouseButton.LeftButton:
            self.rubberBand.hide()
            rect = self.rubberBand.geometry()
            
            # Only create annotation if selection is large enough
            if rect.width() > 10 and rect.height() > 10:
                scene_rect = self.mapToScene(rect).boundingRect()
                self.areaSelected.emit(scene_rect)
                
        elif event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor if self.selection_mode else Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(zoom_factor, zoom_factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def closeEvent(self, event):
        """Clean up when closing"""
        if self.pdf_doc:
            self.pdf_doc.close()
        event.accept()