"""
Standalone OCR Processor for PDF Auto-Ballooning Tool
Integrates with main.py and pdf_viewer.py with minimal changes
"""

import sys
import io
from PyQt6.QtCore import QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QImage
import fitz

# OCR Libraries - Install with: pip install pytesseract pillow
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
    
    # Set tesseract path if needed (Windows)
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
except ImportError:
    OCR_AVAILABLE = False
    print("OCR libraries not available. Install with: pip install pytesseract pillow")

class OCRWorker(QThread):
    """Background OCR processing to avoid UI freezing"""
    
    ocr_completed = pyqtSignal(int, dict)  # annotation_number, results_dict
    
    ocr_failed = pyqtSignal(int, str)     # annotation_number, error_message
    
    def __init__(self):
        super().__init__()
        self.tasks = []  # Queue of (annotation_number, pdf_path, page_num, rect) tuples
        
    def add_ocr_task(self, annotation_number: int, pdf_path: str, page_num: int, rect: QRectF):
        """Add OCR task to queue"""
        self.tasks.append((annotation_number, pdf_path, page_num, rect))
        
        
    def extract_with_multiple_modes(self, pil_image) -> dict:
        """Try different OCR modes and return structured results"""
        if not OCR_AVAILABLE:
            return {"error": "OCR not available"}
    
        results = {}
    
    # Mode 1: General text detection
        try:
            config1 = r'--oem 3 --psm 6'
            text1 = pytesseract.image_to_string(pil_image, config=config1).strip()
            results["text_mode"] = text1 if text1 else "No text detected"
        except:
            results["text_mode"] = "Detection failed"
    
    # Mode 2: Number detection
        try:
            config2 = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.,-+='
            text2 = pytesseract.image_to_string(pil_image, config=config2).strip()
            results["number_mode"] = text2 if text2 else "No numbers detected"
        except:
            results["number_mode"] = "Detection failed"
    
    # Mode 3: Symbol/Character detection
        try:
            config3 = r'--oem 3 --psm 8'
            text3 = pytesseract.image_to_string(pil_image, config=config3).strip()
            # Filter for likely symbols/special chars
            import re
            symbols = re.findall(r'[^\w\s]', text3)
            results["symbol_mode"] = ''.join(set(symbols)) if symbols else "No symbols detected"
        except:
            results["symbol_mode"] = "Detection failed"
    
    # Mode 4: Raw extraction (everything)
        try:
            config4 = r'--oem 3 --psm 6'
            text4 = pytesseract.image_to_string(pil_image, config=config4).strip()
            results["raw_content"] = text4 if text4 else "No content detected"
        except:
            results["raw_content"] = "Detection failed"
    
        return results
        
    def run(self):
        """Process all queued OCR tasks"""
        while self.tasks:
            annotation_number, pdf_path, page_num, rect = self.tasks.pop(0)
            
            try:
                # Extract text from the specified region
                text = self.extract_text_from_region(pdf_path, page_num, rect)
                self.ocr_completed.emit(annotation_number, text)
                
            except Exception as e:
                error_msg = f"OCR failed: {str(e)}"
                self.ocr_failed.emit(annotation_number, error_msg)
                
    def extract_text_from_region(self, pdf_path: str, page_num: int, rect: QRectF) -> str:
        """Extract text from specific region of PDF page using OCR"""
        if not OCR_AVAILABLE:
            return "OCR not available - install pytesseract and pillow"
            
        try:
            # Open PDF and get the page
            doc = fitz.open(pdf_path)
            page = doc[page_num]
            
            # Convert rect coordinates (scene coordinates are 2x scaled)
            # Scale down by factor of 2 to match original PDF coordinates
            pdf_rect = fitz.Rect(
                rect.x() / 2.0,
                rect.y() / 2.0, 
                (rect.x() + rect.width()) / 2.0,
                (rect.y() + rect.height()) / 2.0
            )
            
            # Get pixmap of the cropped region at high resolution
            mat = fitz.Matrix(3.0, 3.0)  # Higher resolution for better OCR
            pix = page.get_pixmap(matrix=mat, clip=pdf_rect)
            
            # Convert to PIL Image
            img_data = pix.tobytes("png")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Enhance image for better OCR (optional preprocessing)
            pil_image = self.preprocess_image_for_ocr(pil_image)
            
            # Run OCR with multiple modes for comprehensive extraction
            ocr_results = self.extract_with_multiple_modes(pil_image)

            # Return structured results instead of single text
            doc.close()
            return ocr_results
            
        except Exception as e:
            raise Exception(f"Failed to extract text: {str(e)}")
    
    def preprocess_image_for_ocr(self, pil_image):
        """Enhance image for capturing text, numbers, symbols, and diagram elements"""
        try:
            from PIL import ImageEnhance, ImageFilter, ImageOps
        
            # Keep original for comparison
            original = pil_image.copy()
        
            # Convert to grayscale if needed
            if pil_image.mode != 'L':
                pil_image = pil_image.convert('L')
        
        # Enhance contrast more aggressively
            enhancer = ImageEnhance.Contrast(pil_image)
            pil_image = enhancer.enhance(2.0)  # Higher contrast
        
        # Enhance sharpness for better edge detection
            sharpness = ImageEnhance.Sharpness(pil_image)
            pil_image = sharpness.enhance(2.0)
        
        # Apply unsharp mask for better detail
            pil_image = pil_image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        
            return pil_image
        
        except ImportError:
            return pil_image
    
    def clean_extracted_text(self, text: str) -> str:
        """Clean extracted text while preserving all characters including symbols"""
        if not text:
            return "No content detected"
    
        # Preserve all characters, just clean up spacing
        lines = []
        for line in text.split('\n'):
            cleaned_line = line.strip()
            if cleaned_line:  # Keep any line with content
                lines.append(cleaned_line)
    
        if not lines:
            return "No readable content found"
    
    # Join with spaces but preserve line structure for diagrams
        if len(lines) == 1:
            result = lines[0]
        else:
            # For multi-line content, preserve some structure
            result = ' | '.join(lines)  # Use | to separate lines
    
        # Clean excessive spaces but keep all characters
        import re
        result = re.sub(r' +', ' ', result)  # Replace multiple spaces with single space
    
        return result.strip()


class OCRManager:
    """Main OCR management class - integrates with the annotation system"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.ocr_worker = OCRWorker()
        self.annotation_texts = {}  # annotation_number -> extracted_text mapping
        
        # Connect OCR worker signals
        self.ocr_worker.ocr_completed.connect(self.on_ocr_completed)
        self.ocr_worker.ocr_failed.connect(self.on_ocr_failed)
        
    def process_annotation_ocr(self, annotation_number: int, pdf_path: str, page_num: int, rect: QRectF):
        """Start OCR processing for an annotation"""
        if not OCR_AVAILABLE:
            self.annotation_texts[annotation_number] = "OCR not available"
            self.update_annotation_display()
            return
            
        # Add to OCR queue and start processing
        self.ocr_worker.add_ocr_task(annotation_number, pdf_path, page_num, rect)
        
        # Show processing status
        self.annotation_texts[annotation_number] = "Processing OCR..."
        self.update_annotation_display()
        
        if not self.ocr_worker.isRunning():
            self.ocr_worker.start()
    
    def on_ocr_failed(self, annotation_number: int, error_message: str):
        """Handle OCR failure"""
        self.annotation_texts[annotation_number] = {"error": error_message}
        self.update_annotation_display()
        self.main_window.status_bar.showMessage(f"OCR failed for annotation {annotation_number}")
        
    def on_ocr_completed(self, annotation_number: int, ocr_results: dict):
        """Handle successful OCR completion with structured results"""
        self.annotation_texts[annotation_number] = ocr_results
        self.update_annotation_display()
        self.main_window.status_bar.showMessage(f"OCR completed for annotation {annotation_number}")
        
        
    def analyze_content_type(self, pil_image) -> str:
        """Analyze what type of content the image contains"""
        try:
            import numpy as np
        
        # Convert to numpy array for analysis
            img_array = np.array(pil_image)

        # Calculate edge density (high = likely diagram/shape)
            from PIL import ImageFilter
            edges = pil_image.filter(ImageFilter.FIND_EDGES)
            edge_array = np.array(edges)
            edge_density = np.mean(edge_array) / 255.0
        
        # Analyze pixel variance (low = likely text, high = complex image)
            variance = np.var(img_array) / 255.0
        
            content_type = "Mixed Content"
            if edge_density > 0.3:
                content_type = "Diagram/Shape"
            elif variance < 0.1:
                content_type = "Text/Numbers"
        
            return content_type
        
        except ImportError:
            return "Unknown Content"
    
    def on_ocr_failed(self, annotation_number: int, error_message: str):
        """Handle OCR failure"""
        self.annotation_texts[annotation_number] = f"Error: {error_message}"
        self.update_annotation_display()
        
        # Update status
        self.main_window.status_bar.showMessage(f"OCR failed for annotation {annotation_number}")
    
    def update_annotation_display(self):
        """Update the annotation list to show primary OCR content"""
        self.main_window.annotation_list.clear()
    
        for i, ann in enumerate(self.main_window.annotations):
            annotation_num = ann['number']
            page_num = ann['page'] + 1
        
            ocr_data = self.annotation_texts.get(annotation_num, {})
        
            if isinstance(ocr_data, dict):
                # Show the most relevant content (raw_content first, then text_mode)
                display_text = ocr_data.get("raw_content", "") or ocr_data.get("text_mode", "")
                if display_text and display_text != "No content detected":
                    display_text = display_text[:30] + "..." if len(display_text) > 30 else display_text
                    label = f"#{annotation_num} (p{page_num}): {display_text}"
                else:
                    label = f"#{annotation_num} (p{page_num}): Processing..."
            else:
                label = f"Annotation {annotation_num} (p{page_num})"
        
            from PyQt6.QtWidgets import QListWidgetItem
            from PyQt6.QtCore import Qt
        
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i)
        
            # Set detailed tooltip
            if isinstance(ocr_data, dict):
                tooltip_parts = []
                for mode, content in ocr_data.items():
                    tooltip_parts.append(f"{mode.replace('_', ' ').title()}: {content}")
                item.setToolTip("\n".join(tooltip_parts))

            self.main_window.annotation_list.addItem(item)

    def get_annotation_text(self, annotation_number: int) -> str:
        """Get extracted text for specific annotation"""
        return self.annotation_texts.get(annotation_number, "")
    
    
    def export_annotations_with_ocr(self, file_path: str):
        """Export annotations with clean, meaningful OCR results"""
        import csv
    
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)

            # Simplified, meaningful header
                header = [
                    "Item_No",
                    "Page", 
                    "Detected_Text",
                    "Numbers_Found",
                    "Special_Characters",
                    "Content_Type",
                    "Confidence"
            ]   
                writer.writerow(header)

            # Write clean data rows
                for sr_no, ann in enumerate(self.main_window.annotations, 1):
                    annotation_num = ann["number"]
                    page_num = ann["page"] + 1
                    ocr_data = self.annotation_texts.get(annotation_num, {})
                
                    if isinstance(ocr_data, dict):
                        # Clean and combine meaningful content
                        text_content = self.clean_content(ocr_data.get("text_mode", ""))
                        number_content = self.extract_numbers(ocr_data.get("number_mode", ""))
                        symbol_content = self.extract_symbols(ocr_data.get("symbol_mode", ""))
                    
                        # Determine primary content and type
                        primary_content, content_type = self.determine_primary_content(
                            text_content, number_content, symbol_content
                        )
                    
                        # Calculate confidence based on detection success
                        confidence = self.calculate_confidence(ocr_data)
                    
                    else:
                        primary_content = "Processing..."
                        number_content = ""
                        symbol_content = ""
                        content_type = "Unknown"
                        confidence = "0%"
                
                    row = [
                        sr_no,
                        page_num,
                        primary_content,
                        number_content,
                        symbol_content,
                        content_type,
                        confidence
                    ]
                    writer.writerow(row)
                
            return True
        except Exception as e:
            print(f"Export failed: {e}")
            return False

    def clean_content(self, content: str) -> str:
        """Clean content for meaningful display"""
        if not content or content in ["No text detected", "Detection failed", "No data"]:
            return ""
    
        # Remove common OCR noise
        import re
        content = re.sub(r'[|]{2,}', ' ', content)  # Remove multiple pipes
        content = re.sub(r'\s+', ' ', content)      # Clean multiple spaces
        content = content.strip()
    
        # Limit length for readability
        if len(content) > 50:
            content = content[:47] + "..."

        return content

    def extract_numbers(self, content: str) -> str:
        """Extract and clean numbers"""
        if not content or "No numbers detected" in content:
            return ""
    
        import re
        numbers = re.findall(r'\d+\.?\d*', content)
        return ', '.join(numbers[:5]) if numbers else ""  # Limit to first 5 numbers

    def extract_symbols(self, content: str) -> str:
        """Extract meaningful symbols"""
        if not content or "No symbols detected" in content:
            return ""
    
        # Filter out common noise, keep meaningful symbols
        meaningful_symbols = []
        for char in content:
            if char in "°±×÷√∞≈≤≥≠→←↑↓∑∏∫∂∆Ω°%$#@&":
                if char not in meaningful_symbols:
                    meaningful_symbols.append(char)

        return ''.join(meaningful_symbols[:10]) if meaningful_symbols else ""

    def determine_primary_content(self, text: str, numbers: str, symbols: str) -> tuple:
        """Determine what the primary content is and its type"""
        if text and len(text) > 10:
            return text, "Text Document"
        elif numbers and not text:
            return numbers, "Numerical Data"
        elif symbols and not text and not numbers:
            return symbols, "Symbols/Diagrams"
        elif text and numbers:
            return f"{text} [{numbers}]", "Mixed Content"
        elif text:
            return text, "Short Text"
        else:   
            return "No readable content", "Unknown"

    def calculate_confidence(self, ocr_data: dict) -> str:
        """Calculate confidence based on detection success"""
        successful_modes = 0
        total_modes = 4
    
        for mode in ["text_mode", "number_mode", "symbol_mode", "raw_content"]:
            content = ocr_data.get(mode, "")
            if content and content not in ["No text detected", "No numbers detected", 
                                        "No symbols detected", "No content detected", 
                                        "Detection failed"]:
                successful_modes += 1

        confidence = (successful_modes / total_modes) * 100
        return f"{int(confidence)}%"
    
    
    
    
    
    
    
    
    


def check_ocr_requirements():
    """Check if OCR requirements are installed"""
    missing_deps = []
    
    try:
        import pytesseract
    except ImportError:
        missing_deps.append("pytesseract")
        
    try:
        from PIL import Image
    except ImportError:
        missing_deps.append("pillow")
    
    if missing_deps:
        print(f"Missing OCR dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        return False
    
    # Check if tesseract binary is available
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        print("Tesseract OCR not found. Please install:")
        print("Windows: https://github.com/UB-Mannheim/tesseract/wiki")
        print("Linux: sudo apt install tesseract-ocr")
        print("Mac: brew install tesseract")
        return False


if __name__ == "__main__":
    # Test OCR functionality
    print("Testing OCR requirements...")
    if check_ocr_requirements():
        print("OCR is ready to use!")
    else:
        print("Please install required OCR components.")