import pdfplumber

def extract_first_pdf(file_path):
    try:
        text = ""

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        with open("Apex_Global_Technologies_Enterprise_Knowledge_Base.txt", "w", encoding="utf-8") as f:
            f.write(text)

        return text.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF: {e}")

extract_first_pdf("Apex_Global_Technologies_Enterprise_Knowledge_Base.pdf")