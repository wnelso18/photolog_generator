# Photolog Generator

A lightweight desktop app that turns a folder of site photos into a clean, two-photos-per-page **PDF photolog** with **fillable note fields**, optional **GPS coordinates**, a **logo header**, a **progress bar**, and a **photo preview + ordering** interface (drag/drop, remove, sort).

Built with **Tkinter** for the UI and **ReportLab** for PDF generation.

---

## Features

- **Folder → Photolog PDF** (`photolog.pdf`)
- **2 photos per page** with a consistent “SITE PHOTOGRAPHS” header and company **logo**
- **Fillable note fields** under each photo (two lines per photo)
- **EXIF timestamp + GPS extraction** (when available)
  - Reads GPS from JPG/JPEG/TIFF when embedded
  - Falls back to file modified time if EXIF is missing
- **Preview window** to:
  - View thumbnails in a grid
  - **Drag-and-drop reorder**
  - **Remove** unwanted photos
  - **Preview** full-size photos
  - Sort by **Name (default)** or **Timestamp**
- **Progress bar** and status label during generation
- **Dad joke** shown in the main window and on completion 😄
- Optional **HEIC/HEIF support** via `pillow-heif`

---

## Screens / Workflow

1. **Select Photo Folder**
2. **Select Output Location**
3. **Select Logo File** (PNG/JPG/JPEG)
4. Click **Preview Photos**
   - Reorder (drag/drop), remove, preview, sort
5. Click **Generate PDF**
   - Output file: `photolog.pdf` (saved in your chosen output folder)

> Note: When you generate the PDF, the app will rename photos in the selected folder to `Photo 1`, `Photo 2`, etc. (preserving extensions). See **Important Notes** below.

---

## Requirements

- Python 3.9+ recommended
- Windows/macOS/Linux (Tkinter required)

### Dependencies

- `reportlab`
- `pillow`
- `exifread`
- `requests`

Optional:
- `pillow-heif` (for HEIC/HEIF)

---

## Installation

### 1) Clone the repo

```bash
git clone https://github.com/wnelso18/photolog_generator.git
cd photolog_generator
