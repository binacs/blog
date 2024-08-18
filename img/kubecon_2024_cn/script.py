import os
from pdf2image import convert_from_path

print(os.getenv("PDF_FILE_PATH"))

pages = convert_from_path(os.getenv("PDF_FILE_PATH"), 150, thread_count=8)

for count, page in enumerate(pages):
    page.save(f'P{count + 1}.png', 'PNG')