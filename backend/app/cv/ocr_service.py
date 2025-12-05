"""
OCR Service - Text Recognition

Supports multiple OCR engines:
- EasyOCR: Good accuracy, GPU support, multi-language
- PaddleOCR: Fast, best for non-English text, lightweight
- Tesseract: Classic OCR, fast, good for simple text

Automatically cleans and processes recognized text for database storage.
"""

import re
import time
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import numpy as np
import threading

try:
    import cv2
except ImportError:
    cv2 = None

from .config import cv_settings, OCREngine
from .cv_logger import cv_logger, LogLevel
from .vision_service import TextRegion


@dataclass
class OCRResult:
    """Single OCR recognition result"""
    raw_text: str
    cleaned_text: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]] = None
    language: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "cleaned_text": self.cleaned_text,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox) if self.bbox else None,
            "language": self.language,
        }


@dataclass
class OCRBatchResult:
    """Batch OCR processing result"""
    frame_number: int
    timestamp: float
    results: List[OCRResult] = field(default_factory=list)
    processing_time_ms: float = 0.0
    engine: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
            "processing_time_ms": round(self.processing_time_ms, 2),
            "engine": self.engine,
            "result_count": len(self.results),
        }


class BaseOCREngine(ABC):
    """Abstract base class for OCR engines"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the OCR engine"""
        pass
    
    @abstractmethod
    def recognize(self, image: np.ndarray) -> List[OCRResult]:
        """Recognize text in image"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get engine name"""
        pass


class EasyOCREngine(BaseOCREngine):
    """EasyOCR implementation"""
    
    def __init__(self, languages: List[str], gpu: bool = False):
        self._languages = languages
        self._gpu = gpu
        self._reader = None
    
    def initialize(self) -> bool:
        try:
            import easyocr
            self._reader = easyocr.Reader(
                self._languages,
                gpu=self._gpu,
                verbose=False,
            )
            cv_logger.ocr(f"EasyOCR initialized with languages: {self._languages}")
            return True
        except ImportError:
            cv_logger.ocr("EasyOCR not installed. Install with: pip install easyocr", level=LogLevel.ERROR)
            return False
        except Exception as e:
            cv_logger.ocr(f"Failed to initialize EasyOCR: {e}", level=LogLevel.ERROR)
            return False
    
    def recognize(self, image: np.ndarray) -> List[OCRResult]:
        if self._reader is None:
            return []
        
        try:
            results = self._reader.readtext(image)
            ocr_results = []
            
            for bbox, text, confidence in results:
                if confidence < cv_settings.ocr_confidence_threshold:
                    continue
                
                # Convert bbox to tuple
                if len(bbox) >= 4:
                    x1 = int(min(p[0] for p in bbox))
                    y1 = int(min(p[1] for p in bbox))
                    x2 = int(max(p[0] for p in bbox))
                    y2 = int(max(p[1] for p in bbox))
                    bbox_tuple = (x1, y1, x2, y2)
                else:
                    bbox_tuple = None
                
                ocr_results.append(OCRResult(
                    raw_text=text,
                    cleaned_text=self._clean_text(text),
                    confidence=confidence,
                    bbox=bbox_tuple,
                ))
            
            return ocr_results
            
        except Exception as e:
            cv_logger.ocr(f"EasyOCR recognition error: {e}", level=LogLevel.ERROR)
            return []
    
    def _clean_text(self, text: str) -> str:
        """Clean recognized text"""
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove non-printable characters
        text = ''.join(char for char in text if char.isprintable())
        return text.strip()
    
    def get_name(self) -> str:
        return "EasyOCR"


class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR implementation"""
    
    def __init__(self, languages: List[str], gpu: bool = False):
        self._lang = 'en' if 'en' in languages else languages[0] if languages else 'en'
        self._gpu = gpu
        self._ocr = None
    
    def initialize(self) -> bool:
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._lang,
                use_gpu=self._gpu,
                show_log=False,
            )
            cv_logger.ocr(f"PaddleOCR initialized with language: {self._lang}")
            return True
        except ImportError:
            cv_logger.ocr("PaddleOCR not installed. Install with: pip install paddlepaddle paddleocr", level=LogLevel.ERROR)
            return False
        except Exception as e:
            cv_logger.ocr(f"Failed to initialize PaddleOCR: {e}", level=LogLevel.ERROR)
            return False
    
    def recognize(self, image: np.ndarray) -> List[OCRResult]:
        if self._ocr is None:
            return []
        
        try:
            results = self._ocr.ocr(image, cls=True)
            ocr_results = []
            
            if results and results[0]:
                for line in results[0]:
                    bbox, (text, confidence) = line
                    
                    if confidence < cv_settings.ocr_confidence_threshold:
                        continue
                    
                    # Convert bbox
                    if bbox and len(bbox) >= 4:
                        x1 = int(min(p[0] for p in bbox))
                        y1 = int(min(p[1] for p in bbox))
                        x2 = int(max(p[0] for p in bbox))
                        y2 = int(max(p[1] for p in bbox))
                        bbox_tuple = (x1, y1, x2, y2)
                    else:
                        bbox_tuple = None
                    
                    ocr_results.append(OCRResult(
                        raw_text=text,
                        cleaned_text=self._clean_text(text),
                        confidence=confidence,
                        bbox=bbox_tuple,
                    ))
            
            return ocr_results
            
        except Exception as e:
            cv_logger.ocr(f"PaddleOCR recognition error: {e}", level=LogLevel.ERROR)
            return []
    
    def _clean_text(self, text: str) -> str:
        text = ' '.join(text.split())
        text = ''.join(char for char in text if char.isprintable())
        return text.strip()
    
    def get_name(self) -> str:
        return "PaddleOCR"


class TesseractEngine(BaseOCREngine):
    """Tesseract OCR implementation"""
    
    def __init__(self, languages: List[str]):
        self._lang = '+'.join(languages) if languages else 'eng'
        self._pytesseract = None
    
    def initialize(self) -> bool:
        try:
            import pytesseract
            # Test if tesseract is installed
            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
            cv_logger.ocr(f"Tesseract OCR initialized with languages: {self._lang}")
            return True
        except ImportError:
            cv_logger.ocr("pytesseract not installed. Install with: pip install pytesseract", level=LogLevel.ERROR)
            return False
        except Exception as e:
            cv_logger.ocr(f"Failed to initialize Tesseract: {e}", level=LogLevel.ERROR)
            return False
    
    def recognize(self, image: np.ndarray) -> List[OCRResult]:
        if self._pytesseract is None:
            return []
        
        try:
            # Get detailed data with confidence
            data = self._pytesseract.image_to_data(
                image,
                lang=self._lang,
                output_type=self._pytesseract.Output.DICT,
            )
            
            ocr_results = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = float(data['conf'][i]) / 100.0  # Convert to 0-1
                
                if not text or conf < cv_settings.ocr_confidence_threshold:
                    continue
                
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                ocr_results.append(OCRResult(
                    raw_text=text,
                    cleaned_text=self._clean_text(text),
                    confidence=conf,
                    bbox=(x, y, x + w, y + h),
                ))
            
            return ocr_results
            
        except Exception as e:
            cv_logger.ocr(f"Tesseract recognition error: {e}", level=LogLevel.ERROR)
            return []
    
    def _clean_text(self, text: str) -> str:
        text = ' '.join(text.split())
        text = ''.join(char for char in text if char.isprintable())
        return text.strip()
    
    def get_name(self) -> str:
        return "Tesseract"


class OCRService:
    """
    OCR Service - Unified text recognition interface
    
    Features:
    - Multiple engine support (EasyOCR, PaddleOCR, Tesseract)
    - Automatic text cleaning and normalization
    - Code/ID pattern detection
    - Batch processing
    - Confidence filtering
    """
    
    def __init__(self):
        self._engine: Optional[BaseOCREngine] = None
        self._initialized: bool = False
        self._lock = threading.Lock()
        
        # Pattern matchers for common codes/IDs
        self._patterns = {
            "sku": re.compile(r'^[A-Z0-9]{4,20}$', re.IGNORECASE),
            "barcode": re.compile(r'^\d{8,14}$'),
            "serial": re.compile(r'^[A-Z0-9\-]{6,30}$', re.IGNORECASE),
            "part_number": re.compile(r'^[A-Z]{1,3}[\-\s]?\d{3,10}$', re.IGNORECASE),
        }
        
        # Statistics
        self._total_processed: int = 0
        self._total_recognized: int = 0
        self._avg_processing_time: float = 0.0
    
    def initialize(self, engine: Optional[OCREngine] = None) -> bool:
        """Initialize OCR engine with automatic fallback"""
        engine = engine or cv_settings.ocr_engine
        
        cv_logger.ocr(f"Initializing OCR with engine: {engine.value}")
        
        # Try primary engine first
        engines_to_try = [engine]
        
        # Automatic fallback chain: EasyOCR -> Tesseract -> PaddleOCR
        if engine == OCREngine.EASYOCR:
            engines_to_try = [OCREngine.EASYOCR, OCREngine.TESSERACT, OCREngine.PADDLEOCR]
        elif engine == OCREngine.PADDLEOCR:
            engines_to_try = [OCREngine.PADDLEOCR, OCREngine.TESSERACT, OCREngine.EASYOCR]
        elif engine == OCREngine.TESSERACT:
            engines_to_try = [OCREngine.TESSERACT, OCREngine.EASYOCR, OCREngine.PADDLEOCR]
        
        for attempt_engine in engines_to_try:
            try:
                if attempt_engine == OCREngine.EASYOCR:
                    self._engine = EasyOCREngine(
                        languages=cv_settings.ocr_languages,
                        gpu=cv_settings.ocr_gpu,
                    )
                elif attempt_engine == OCREngine.PADDLEOCR:
                    self._engine = PaddleOCREngine(
                        languages=cv_settings.ocr_languages,
                        gpu=cv_settings.ocr_gpu,
                    )
                elif attempt_engine == OCREngine.TESSERACT:
                    self._engine = TesseractEngine(
                        languages=cv_settings.ocr_languages,
                    )
                else:
                    continue
                
                self._initialized = self._engine.initialize()
                
                if self._initialized:
                    if attempt_engine != engine:
                        cv_logger.ocr(
                            f"Primary engine {engine.value} unavailable, using {attempt_engine.value}",
                            level=LogLevel.WARNING
                        )
                    cv_logger.set_status("ocr", "ready")
                    cv_logger.ocr(f"OCR service initialized with {self._engine.get_name()}")
                    return True
                    
            except Exception as e:
                cv_logger.ocr(
                    f"Failed to initialize {attempt_engine.value}: {e}",
                    level=LogLevel.WARNING if attempt_engine != engine else LogLevel.ERROR
                )
                continue
        
        # All engines failed
        cv_logger.ocr(
            "All OCR engines failed to initialize. OCR will be disabled.",
            level=LogLevel.WARNING
        )
        return False
    
    def recognize_image(self, image: np.ndarray) -> List[OCRResult]:
        """Recognize text in image"""
        if not self._initialized or self._engine is None:
            return []
        
        with self._lock:
            return self._engine.recognize(image)
    
    def process_text_regions(
        self,
        regions: List[TextRegion],
        frame_number: int,
        timestamp: float,
    ) -> OCRBatchResult:
        """Process multiple text regions"""
        start_time = time.time()
        
        result = OCRBatchResult(
            frame_number=frame_number,
            timestamp=timestamp,
            engine=self._engine.get_name() if self._engine else "",
        )
        
        for region in regions:
            if region.cropped_image is None:
                continue
            
            # Preprocess image for better OCR
            processed = self._preprocess_for_ocr(region.cropped_image)
            
            # Recognize text
            ocr_results = self.recognize_image(processed)
            
            # Adjust bbox coordinates to frame coordinates
            for ocr_result in ocr_results:
                if ocr_result.bbox and region.bbox:
                    x1, y1, x2, y2 = ocr_result.bbox
                    rx1, ry1, _, _ = region.bbox
                    ocr_result.bbox = (x1 + rx1, y1 + ry1, x2 + rx1, y2 + ry1)
            
            result.results.extend(ocr_results)
        
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        # Update statistics
        self._total_processed += 1
        self._total_recognized += len(result.results)
        self._avg_processing_time = (
            (self._avg_processing_time * (self._total_processed - 1) + result.processing_time_ms)
            / self._total_processed
        )
        
        if result.results:
            cv_logger.increment_ocr()
            cv_logger.ocr(
                f"Frame {frame_number}: Recognized {len(result.results)} text items",
                level=LogLevel.DEBUG,
                payload=result.to_dict(),
            )
        
        return result
    
    def _preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR accuracy"""
        if cv2 is None:
            return image
        
        try:
            # Convert to grayscale if color
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            
            # Resize if too small
            h, w = gray.shape[:2]
            if h < 50:
                scale = 50 / h
                gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            
            # Apply adaptive thresholding
            # binary = cv2.adaptiveThreshold(
            #     gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            #     cv2.THRESH_BINARY, 11, 2
            # )
            
            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            
            return denoised
            
        except Exception as e:
            cv_logger.ocr(f"Preprocessing error: {e}", level=LogLevel.WARNING)
            return image
    
    def identify_pattern(self, text: str) -> Optional[str]:
        """Identify if text matches known patterns (SKU, barcode, etc.)"""
        cleaned = text.strip().upper()
        
        for pattern_name, pattern in self._patterns.items():
            if pattern.match(cleaned):
                return pattern_name
        
        return None
    
    def extract_codes(self, results: List[OCRResult]) -> List[Dict[str, Any]]:
        """Extract recognized codes/IDs with pattern matching"""
        codes = []
        
        for result in results:
            pattern = self.identify_pattern(result.cleaned_text)
            if pattern:
                codes.append({
                    "text": result.cleaned_text,
                    "pattern": pattern,
                    "confidence": result.confidence,
                    "bbox": result.bbox,
                })
        
        return codes
    
    def get_stats(self) -> Dict[str, Any]:
        """Get OCR statistics"""
        return {
            "initialized": self._initialized,
            "engine": self._engine.get_name() if self._engine else None,
            "total_processed": self._total_processed,
            "total_recognized": self._total_recognized,
            "avg_processing_time_ms": round(self._avg_processing_time, 2),
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        return {
            "initialized": self._initialized,
            "status": "ready" if self._initialized else "not_initialized",
            **self.get_stats(),
        }

