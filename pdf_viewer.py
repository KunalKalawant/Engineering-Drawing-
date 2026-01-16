import sys
import os
import math
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem,
    QRubberBand, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsItemGroup, QGraphicsPolygonItem
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont, QMouseEvent, QBrush, QPolygonF, QCursor
import fitz

COLORS = [
    "#FF4444", "#44FF44", "#4444FF", "#FFAA00", "#AA44FF",
    "#00FFAA", "#FF0088", "#88FF00", "#0088FF", "#FF8800"
]

class DraggableAnnotation(QGraphicsItemGroup):
    """Complete annotation system with tethered pointer, circle, and line"""
    
    def __init__(self, rect: QRectF, number: int, color: str):
        super().__init__()
        self.rect = rect
        self.number = number
        self.color = color
        self.default_circle_pos = rect.topRight() + QPointF(30, -20)
        self.annotation_index = -1
        self.deletion_mode = False
    
        self.highlight_box = self.create_highlight_box()
        self.circle = self.create_number_circle()
        self.line = self.create_connecting_line()
        self.arrow = self.create_arrow_head()
    
        self.addToGroup(self.highlight_box)
        self.addToGroup(self.line)
        self.addToGroup(self.arrow)
    
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItemGroup.GraphicsItemFlag.ItemIsSelectable, True)

        self.circle.setPos(self.default_circle_pos)
        self.update_connections()

    def set_deletion_mode(self, enabled: bool):
        """Enable/disable deletion mode for this annotation"""
        self.deletion_mode = enabled
        if hasattr(self, 'circle') and self.circle:
            self.circle.set_deletion_mode(enabled)

    def create_highlight_box(self):
        box = QGraphicsRectItem(self.rect)
        color = QColor(self.color)
        color.setAlpha(100)
        box.setBrush(QBrush(color))
        box.setPen(QPen(QColor(self.color), 2))
        box.setZValue(-1)
        return box

    def create_number_circle(self):
        class DraggableCircle(QGraphicsEllipseItem):
            def __init__(self, rect, annotation_parent):
                super().__init__(rect)
                self.annotation_parent = annotation_parent
                self.deletion_mode = False
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

            def set_deletion_mode(self, enabled: bool):
                """Change cursor based on deletion mode"""
                self.deletion_mode = enabled
                if enabled:
                    self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                else:
                    self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

            def mousePressEvent(self, event):
                """Handle click on circle"""
                if self.deletion_mode and event.button() == Qt.MouseButton.LeftButton:
                    # Notify parent viewer about deletion request
                    if self.annotation_parent and hasattr(self.annotation_parent, 'annotation_index'):
                        scene_view = self.scene().views()[0] if self.scene() and self.scene().views() else None
                        if scene_view:
                            scene_view.annotation_clicked.emit(self.annotation_parent.annotation_index)
                    event.accept()
                else:
                    super().mousePressEvent(event)

            def itemChange(self, change, value):
                if change == self.GraphicsItemChange.ItemPositionHasChanged:
                    if self.annotation_parent:
                        self.annotation_parent.update_connections()
                return super().itemChange(change, value)
    
        circle = DraggableCircle(QRectF(-15, -15, 30, 30), self)
        circle.setBrush(QBrush(QColor(self.color)))
        circle.setPen(QPen(QColor(self.color).darker(150), 2))
        circle.setZValue(2)
        circle.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        circle.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
    
        self.number_text = QGraphicsTextItem(str(self.number))
        self.number_text.setDefaultTextColor(QColor("white"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        self.number_text.setFont(font)
    
        text_rect = self.number_text.boundingRect()
        self.number_text.setPos(-text_rect.width()/2, -text_rect.height()/2)
        self.number_text.setParentItem(circle)
    
        return circle

    def create_connecting_line(self):
        self.line_item = QGraphicsLineItem()
        self.line_item.setPen(QPen(QColor(self.color), 2))
        self.line_item.setZValue(1)
        return self.line_item

    def create_arrow_head(self):
        self.arrow_polygon = QGraphicsPolygonItem()
        self.arrow_polygon.setBrush(QBrush(QColor(self.color)))
        self.arrow_polygon.setPen(QPen(QColor(self.color), 1))
        self.arrow_polygon.setZValue(1)
        return self.arrow_polygon

    def update_connections(self):
        circle_center = self.circle.pos()
        closest_point = self.get_closest_point_on_rect(circle_center, self.rect)
        self.line_item.setLine(circle_center.x(), circle_center.y(), 
                              closest_point.x(), closest_point.y())
        self.update_arrow_head(circle_center, closest_point)

    def get_closest_point_on_rect(self, point: QPointF, rect: QRectF) -> QPointF:
        x = max(rect.left(), min(point.x(), rect.right()))
        y = max(rect.top(), min(point.y(), rect.bottom()))
        
        if rect.contains(point):
            distances = [
                abs(point.x() - rect.left()),
                abs(point.x() - rect.right()),
                abs(point.y() - rect.top()),
                abs(point.y() - rect.bottom())
            ]
            min_dist_idx = distances.index(min(distances))
            
            if min_dist_idx == 0:
                x = rect.left()
            elif min_dist_idx == 1:
                x = rect.right()
            elif min_dist_idx == 2:
                y = rect.top()
            else:
                y = rect.bottom()
        
        return QPointF(x, y)

    def update_arrow_head(self, start: QPointF, end: QPointF):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return
            
        angle = math.atan2(dy, dx)
        arrow_length = 12
        
        tip = end
        back_angle1 = angle + 2.8
        back_angle2 = angle - 2.8
        
        p1 = QPointF(tip.x() + arrow_length * math.cos(back_angle1),
                     tip.y() + arrow_length * math.sin(back_angle1))
        p2 = QPointF(tip.x() + arrow_length * math.cos(back_angle2),
                     tip.y() + arrow_length * math.sin(back_angle2))
        
        arrow_points = QPolygonF([tip, p1, p2])
        self.arrow_polygon.setPolygon(arrow_points)


class PreviewAnnotation(QGraphicsItemGroup):
    """Preview annotation for auto-detection"""
    
    def __init__(self, rect: QRectF, number: int, color: str, selected: bool = True):
        super().__init__()
        self.rect = rect
        self.number = number
        self.color = color
        self.selected = selected
        
        self.highlight_box = self.create_preview_box()
        self.number_label = self.create_number_label()
        
        self.addToGroup(self.highlight_box)
        self.addToGroup(self.number_label)
        
        self.setOpacity(0.8 if selected else 0.3)

    def create_preview_box(self):
        box = QGraphicsRectItem(self.rect)
        color = QColor(self.color)
        
        if self.selected:
            color.setAlpha(120)
            box.setPen(QPen(QColor(self.color), 3))
        else:
            color.setAlpha(60)
            box.setPen(QPen(QColor(self.color), 1))
            
        box.setBrush(QBrush(color))
        box.setZValue(-1)
        return box

    def create_number_label(self):
        label_pos = self.rect.topLeft() + QPointF(5, 5)
        
        circle = QGraphicsEllipseItem(0, 0, 25, 25)
        circle.setPos(label_pos)
        circle.setBrush(QBrush(QColor(self.color)))
        circle.setPen(QPen(QColor(self.color).darker(150), 1))
        circle.setZValue(1)
        
        text = QGraphicsTextItem(str(self.number))
        text.setDefaultTextColor(QColor("white"))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        text.setFont(font)
        
        text_rect = text.boundingRect()
        text.setPos(label_pos + QPointF(12.5 - text_rect.width()/2, 12.5 - text_rect.height()/2))
        text.setZValue(2)
        
        group = QGraphicsItemGroup()
        group.addToGroup(circle)
        group.addToGroup(text)
        return group

    def update_selection(self, selected: bool):
        self.selected = selected
        self.setOpacity(0.8 if selected else 0.3)
        
        color = QColor(self.color)
        if selected:
            color.setAlpha(120)
            self.highlight_box.setPen(QPen(QColor(self.color), 3))
        else:
            color.setAlpha(60)
            self.highlight_box.setPen(QPen(QColor(self.color), 1))
        
        self.highlight_box.setBrush(QBrush(color))


class PDFViewer(QGraphicsView):
    """Enhanced PDF viewer with deletion mode support"""
    
    areaSelected = pyqtSignal(QRectF)
    annotation_clicked = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._pan_start = QPointF()
        self._panning = False
        self.selection_mode = False
        self.deletion_mode = False
        self.rubberBand = None
        self.origin = None
        self.pdf_doc = None
        self.current_page = 0
        self.annotations = []
        self.preview_annotations = []
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    def enable_selection(self, enabled: bool):
        self.selection_mode = enabled
        if enabled:
            self.deletion_mode = False  # Disable deletion when selection is enabled
        self.update_cursor()

    def set_deletion_mode(self, enabled: bool):
        """Enable/disable deletion mode"""
        self.deletion_mode = enabled
        if enabled:
            self.selection_mode = False  # Disable selection when deletion is enabled
        
        # Update all annotation circles
        for item in self.scene.items():
            if isinstance(item, DraggableAnnotation):
                item.set_deletion_mode(enabled)
        
        self.update_cursor()

    def update_cursor(self):
        """Update cursor based on current mode"""
        if self.deletion_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.selection_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def load_pdf(self, file_path):
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
        if not self.pdf_doc:
            return
        
        try:
            page = self.pdf_doc[self.current_page]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            
            self.scene.clear()
            pixmap_item = self.scene.addPixmap(pixmap)
            pixmap_item.setZValue(-2)
            
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
            self.redraw_annotations_for_current_page(self.annotations)
            
        except Exception as e:
            print(f"Error displaying page: {e}")

    def go_to_page(self, page_index):
        if self.pdf_doc and 0 <= page_index < len(self.pdf_doc):
            self.current_page = page_index
            self.display_page()
            return True
        return False

    def next_page(self):
        if self.pdf_doc and self.current_page < len(self.pdf_doc) - 1:
            self.current_page += 1
            self.display_page()
            return True
        return False

    def prev_page(self):
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self.display_page()
            return True
        return False

    def get_page_info(self):
        if self.pdf_doc:
            return self.current_page + 1, len(self.pdf_doc)
        return 0, 0

    def zoom_to_level(self, level):
        self.resetTransform()
        if self.pdf_doc:
            scale = level / 100.0
            self.scale(scale, scale)

    def zoom_by_factor(self, factor):
        self.scale(factor, factor)

    def preview_auto_annotations(self, auto_annotations: list):
        self.clear_preview_annotations()
        
        current_page = self.current_page
        for ann in auto_annotations:
            if ann["page"] == current_page:
                preview_item = PreviewAnnotation(
                    ann["rect"], 
                    ann["number"], 
                    ann["color"], 
                    ann.get("selected", True)
                )
                self.scene.addItem(preview_item)
                self.preview_annotations.append(preview_item)

    def clear_preview_annotations(self):
        for item in self.preview_annotations:
            if item.scene():
                self.scene.removeItem(item)
        self.preview_annotations.clear()

    def remove_annotation_graphics(self, ann: dict):
        if "annotation_item" in ann and ann["annotation_item"] is not None:
            item = ann["annotation_item"]
            if item.scene() is not None:
                self.scene.removeItem(item)
                if hasattr(item, 'circle') and item.circle.scene():
                    self.scene.removeItem(item.circle)
            ann["annotation_item"] = None

    def redraw_annotations_for_current_page(self, annotations: list):
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
        for i, ann in enumerate(annotations):
            if ann["page"] == current_page:
                annotation_item = DraggableAnnotation(ann["rect"], ann["number"], ann["color"])
                annotation_item.annotation_index = i
                annotation_item.set_deletion_mode(self.deletion_mode)
            
                self.scene.addItem(annotation_item)
                self.scene.addItem(annotation_item.circle)
            
                ann["annotation_item"] = annotation_item

    def mousePressEvent(self, event: QMouseEvent):
        # In deletion mode, let the circle handle clicks
        if self.deletion_mode:
            super().mousePressEvent(event)
            return
        
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
        if self.selection_mode and self.rubberBand and event.button() == Qt.MouseButton.LeftButton:
            self.rubberBand.hide()
            rect = self.rubberBand.geometry()
            
            if rect.width() > 10 and rect.height() > 10:
                scene_rect = self.mapToScene(rect).boundingRect()
                self.areaSelected.emit(scene_rect)
                
        elif event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.update_cursor()
        
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(zoom_factor, zoom_factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    def closeEvent(self, event):
        if self.pdf_doc:
            self.pdf_doc.close()
        event.accept()
