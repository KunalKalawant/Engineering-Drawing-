# Engineering-Drawing analyzer-
Developed a desktop-based engineering drawing analyzer with OCR-driven text extraction, interactive PDF annotation, zoom tools, and CSV export using a modular multi-threaded architecture

## 📁 Project Structure

```
BASE WORKING OCR/
│
├── main.py
├── ocr_processor.py
├── pdf_viewer.py
├── requirements.txt
├── Annoted Sample.pdf
├── Sample_csv.csv
├── sample.pdf
└── Tesseract OCR/        ← contains Tesseract installer or binaries
```

---

## ⚙️ Prerequisites

* **Python 3.10**
* **Windows OS**
* **Tesseract OCR** (already included in `Tesseract OCR/` folder)

---

## 🧩 Setup Instructions

### 1️⃣ Create Virtual Environment

```bash
python -m venv venv
```

### 2️⃣ Activate Virtual Environment

```bash
venv\Scripts\activate
```

### 3️⃣ Install Required Packages

```bash
pip install -r requirements.txt
```

---

## 🔍 Configure Tesseract Path

### Option 1 (Recommended) — Update Code

Open `ocr_processor.py`, go to **line 20**, and update this line:

```python
pytesseract.pytesseract.tesseract_cmd = r"~\Tesseract OCR\tesseract.exe"
```

Make sure the path exactly matches your system path to `tesseract.exe`.

### Option 2 — Set Environment Variable

You can alternatively add the path to your Windows environment variables:

```
TESSERACT_PATH = ~\Tesseract OCR
```

Then restart your terminal.

---

## 🚀 Run the Application

Once setup is complete, run:

```bash
python main.py
```

This will start the OCR processor and automatically read the PDF files in your working directory.

---

## ✅ Notes

* Make sure your `venv` is **activated** before running.
* You can test the setup using `sample.pdf` or `Annoted Sample.pdf`.
* Output CSV (`Sample_csv.csv`) will be updated or created automatically after processing.

---
