import pdfplumber
from pathlib import Path

# Keep the output next to this script (and the source PDF), so the file is
# found no matter which directory the script is run from.
BASE_DIR = Path(__file__).resolve().parent
PDF_FILE = BASE_DIR / "Apex_Global_Technologies_Enterprise_Knowledge_Base.pdf"
TXT_FILE = BASE_DIR / "Apex_Global_Technologies_Enterprise_Knowledge_Base.txt"


def extract_first_pdf(file_path):
    try:
        text = ""

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        with open(TXT_FILE, "w", encoding="utf-8") as f:
            f.write(text)

        return text.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF: {e}")


if __name__ == "__main__":
    extract_first_pdf(PDF_FILE)