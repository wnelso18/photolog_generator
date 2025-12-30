import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from PIL import Image, ImageTk
import os
from datetime import datetime
import exifread
from reportlab.lib import colors
from reportlab.pdfbase.acroform import AcroForm
import requests
import threading
import shutil


# Optional HEIC support
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

# --- THEME COLORS ---
BG = "#1e1e1e"
PANEL_BG = "#252526"
FG = "#f5f5f5"
ACCENT = "#4CAF50"

# Conversion factors (1 inch = 72 points in PDF)
INCH = 72
PHOTO_WIDTH = 4.5 * INCH
PHOTO_HEIGHT = 3.3 * INCH
MARGIN = 0.5 * INCH
BOX_HEIGHT = 1.125 * INCH


# ----------------- METADATA (ORIGINAL STYLE) -----------------
def get_photo_metadata(photo_path):
    """
    Returns (datetime, coords_str_or_None)

    - Uses EXIF for JPG/JPEG/TIFF when available
    - Falls back to file modification time
    - HEIC/PNG still get a timestamp but usually no coords
    """
    ext = os.path.splitext(photo_path)[1].lower()
    # Default: use file modification time
    dt = datetime.fromtimestamp(os.path.getmtime(photo_path))
    coords = None

    # Only bother with EXIF on formats that usually have it in a way exifread can handle
    if ext in ('.jpg', '.jpeg', '.tif', '.tiff'):
        try:
            with open(photo_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)

            # Timestamp
            ts_tag = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime')
            if ts_tag:
                try:
                    dt = datetime.strptime(str(ts_tag), '%Y:%m:%d %H:%M:%S')
                except Exception:
                    # If parsing fails, just keep file mtime
                    pass

            # GPS
            lat_tag = tags.get('GPS GPSLatitude')
            lon_tag = tags.get('GPS GPSLongitude')
            lat_ref_tag = tags.get('GPS GPSLatitudeRef')
            lon_ref_tag = tags.get('GPS GPSLongitudeRef')

            if lat_tag and lon_tag and lat_ref_tag and lon_ref_tag:
                # exifread gives numeric ratios in .values; the ref tags are usually "N","S","E","W"
                lat_ref = str(lat_ref_tag).strip()
                lon_ref = str(lon_ref_tag).strip()
                lat_deg = convert_to_degrees(lat_tag.values, lat_ref)
                lon_deg = convert_to_degrees(lon_tag.values, lon_ref)
                coords = f"{lat_deg:.6f}, {lon_deg:.6f}"
        except Exception as e:
            # Don't crash if EXIF is weird, just log and fall back
            print(f"EXIF read failed for {photo_path}: {e}")

    # For HEIC/PNG/etc we keep dt from file mtime and coords=None
    return dt, coords


def convert_to_degrees(value, ref):
    d = float(value[0].num) / float(value[0].den)
    m = float(value[1].num) / float(value[1].den)
    s = float(value[2].num) / float(value[2].den)
    degrees = d + (m / 60.0) + (s / 3600.0)
    ref = ref.upper()
    return -degrees if ref in ('S', 'W') else degrees



def open_image_for_pillow(path):
    try:
        img = Image.open(path)
        return img
    except Exception as e:
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.heic', '.heif') and pillow_heif is None:
            raise RuntimeError(
                f"Unable to open HEIC image '{os.path.basename(path)}'. "
                "Install HEIC support with: pip install pillow-heif"
            ) from e
        raise


def compress_image(photo_path, max_size=(800, 600)):
    img = open_image_for_pillow(photo_path)
    img = img.convert('RGB')
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    temp_path = photo_path + "_compressed.jpg"
    img.save(temp_path, "JPEG", quality=85, optimize=True)
    return temp_path


# ----------------- PDF CREATION (UNCHANGED LAYOUT) -----------------
def create_photolog(photos, output_path, logo_path, progress_callback):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    if not os.path.exists(logo_path):
        raise FileNotFoundError(f"Logo file not found: {logo_path}")
    
    output_pdf = os.path.join(output_path, "photolog.pdf")
    if not photos:
        raise ValueError("No photos provided")
    
    c = canvas.Canvas(output_pdf, pagesize=letter)
    form = c.acroForm
    width, height = letter
    
    total_steps = len(photos) + 2
    current_step = 0
    
    for i in range(0, len(photos), 2):
        c.setFont("Helvetica-Bold", 12)
        text_width = stringWidth("SITE PHOTOGRAPHS", "Helvetica-Bold", 12)
        c.drawString(width - MARGIN - text_width, height - MARGIN - 0.25*INCH, "SITE PHOTOGRAPHS")
        
        if os.path.exists(logo_path):
            logo = ImageReader(logo_path)
            c.drawImage(logo, MARGIN, height - MARGIN - 0.4*INCH,
                       width=1.25*INCH, height=0.625*INCH,
                       preserveAspectRatio=True)
        
        current_step += 1
        progress_callback(current_step / total_steps * 100)
        
        page_center = width / 2
        photo_x = page_center - (PHOTO_WIDTH / 2)
        
        y_pos = height - 1.0*INCH
        
        for j in range(2):
            if i + j >= len(photos):
                break
                
            photo_path, _, coords = photos[i + j]
            
            compressed_path = compress_image(photo_path)
            c.drawImage(compressed_path, photo_x, y_pos - PHOTO_HEIGHT, 
                       PHOTO_WIDTH, PHOTO_HEIGHT)
            os.remove(compressed_path)
            
            c.setStrokeColor(colors.black)
            c.setFillColor(colors.white)
            box_y = y_pos - PHOTO_HEIGHT - BOX_HEIGHT
            c.rect(photo_x, box_y, PHOTO_WIDTH, BOX_HEIGHT, fill=1)
            
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.black)
            photo_num = i + j + 1
            photo_label = f"Photo {photo_num}"
            c.drawString(photo_x + 10, y_pos - PHOTO_HEIGHT - 20, photo_label)
            
            if coords:
                c.setFont("Helvetica", 10)
                coord_text = f"({coords})"
                coord_width = stringWidth(coord_text, "Helvetica", 10)
                c.drawString(photo_x + PHOTO_WIDTH - coord_width - 10, y_pos - PHOTO_HEIGHT - 20, coord_text)
            
            form.textfield(
                name=f"notes_photo_{photo_num}_1",
                x=photo_x + 10, 
                y=box_y + 30,
                width=PHOTO_WIDTH - 20,
                height=15,
                fontName="Helvetica",
                fontSize=9,
                borderStyle="solid",
                borderWidth=0,
                borderColor=colors.black,
                fillColor=colors.white
            )
            form.textfield(
                name=f"notes_photo_{photo_num}_2",
                x=photo_x + 10, 
                y=box_y + 10,
                width=PHOTO_WIDTH - 20,
                height=15,
                fontName="Helvetica",
                fontSize=9,
                borderStyle="solid",
                borderWidth=0,
                borderColor=colors.black,
                fillColor=colors.white
            )
            
            c.setStrokeColor(colors.black)
            c.line(photo_x + 10, box_y + 28, photo_x + PHOTO_WIDTH - 10, box_y + 28)
            c.line(photo_x + 10, box_y + 8, photo_x + PHOTO_WIDTH - 10, box_y + 8)
            
            y_pos -= (PHOTO_HEIGHT + BOX_HEIGHT + 0.4*INCH)
            current_step += 1
            progress_callback(current_step / total_steps * 100)
        
        c.showPage()
    
    c.save()
    progress_callback(100)


# ----------------- JOKES -----------------
def get_dad_joke():
    try:
        response = requests.get("https://icanhazdadjoke.com/", headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()["joke"]
    except Exception:
        return "Why don’t skeletons fight each other? Because they don’t have the guts!"


# ----------------- PREVIEW WINDOW -----------------
class PhotoPreviewWindow:
    def __init__(self, parent, photos, output_path, logo_path, on_generate):
        self.parent = parent
        self.photos = photos.copy()
        self.output_path = output_path
        self.logo_path = logo_path
        self.on_generate = on_generate
        
        self.window = tk.Toplevel(parent)
        self.window.title("Preview and Order Photos")
        self.window.state("zoomed")
        self.window.configure(bg=BG)
        
        self.canvas = tk.Canvas(self.window, bg=PANEL_BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        self.scrollbar = tk.Scrollbar(self.window, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.config(yscrollcommand=self.scrollbar.set)
        
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        
        # Grid appearance
        self.thumb_size = (220, 160)
        self.margin_x = 40
        self.margin_y = 40
        self.spacing_x = 80
        self.spacing_y = 140  # spacing to avoid overlap

        self.photo_items = []  # (image_id, text_id, photo, path, button_window_id)
        self.thumb_cache = {}  # path -> PhotoImage (cache for speed)

        # Drag-and-drop state
        self.dragged_index = None
        self.last_drag_x = None
        self.last_drag_y = None
        self.drop_indicator = None

        self.load_photos()
        
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.button_frame = tk.Frame(self.window, bg=BG)
        self.button_frame.pack(pady=5, side=tk.BOTTOM, fill=tk.X)

        self.sort_name_button = ttk.Button(
            self.button_frame,
            text="Arrange by Name (Default)",
            command=self.sort_by_name
        )
        self.sort_name_button.pack(side=tk.LEFT, padx=10, pady=10)

        self.sort_time_button = ttk.Button(
            self.button_frame,
            text="Arrange by Timestamp",
            command=self.sort_by_timestamp
        )
        self.sort_time_button.pack(side=tk.LEFT, padx=10, pady=10)
        
        self.generate_button = ttk.Button(
            self.button_frame,
            text="Generate PDF",
            style="Accent.TButton",
            command=self.generate_pdf
        )
        self.generate_button.pack(side=tk.RIGHT, padx=10, pady=10)

        self.update_sort_button_styles("name")

    # ---- SORT BUTTON STYLE TOGGLING ----
    def update_sort_button_styles(self, mode):
        if mode == "name":
            self.sort_name_button.configure(style="Accent.TButton")
            self.sort_time_button.configure(style="TButton")
        else:
            self.sort_name_button.configure(style="TButton")
            self.sort_time_button.configure(style="Accent.TButton")

    # ---- GRID HELPERS ----
    def get_grid_params(self):
        canvas_width = self.canvas.winfo_width() or 800
        per_tile_width = self.thumb_size[0] + self.spacing_x
        cols = max(1, (canvas_width - self.margin_x * 2) // per_tile_width)
        per_tile_height = self.thumb_size[1] + self.spacing_y
        return canvas_width, per_tile_width, per_tile_height, cols

    def load_photos(self):
        self.canvas.delete("all")
        self.photo_items.clear()

        _, per_tile_width, per_tile_height, cols = self.get_grid_params()

        for idx, (path, _, _) in enumerate(self.photos):
            row = idx // cols
            col = idx % cols
            x = self.margin_x + col * per_tile_width
            y = self.margin_y + row * per_tile_height

            # Use cached thumbnail if available
            if path in self.thumb_cache:
                photo = self.thumb_cache[path]
            else:
                try:
                    img = open_image_for_pillow(path)
                    img.thumbnail(self.thumb_size, Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumb_cache[path] = photo
                except Exception as e:
                    print(f"Failed to load {path}: {e}")
                    continue

            image_id = self.canvas.create_image(x, y, image=photo, anchor="nw")
            text = f"{idx + 1}. {os.path.basename(path)}"
            text_id = self.canvas.create_text(
                x + self.thumb_size[0] / 2,
                y + self.thumb_size[1] + 20,
                text=text,
                anchor="n",
                font=("Segoe UI", 10),
                fill=FG
            )

            # Frame with Remove + Preview buttons
            btn_frame = tk.Frame(self.canvas, bg=PANEL_BG)
            remove_btn = ttk.Button(btn_frame, text="Remove", command=lambda p=path: self.remove_photo(p))
            remove_btn.pack(side=tk.LEFT, padx=(0, 5))
            preview_btn = ttk.Button(btn_frame, text="Preview", command=lambda p=path: self.show_photo_preview(p))
            preview_btn.pack(side=tk.LEFT)

            button_window_id = self.canvas.create_window(
                x + self.thumb_size[0] / 2,
                y + self.thumb_size[1] + 50,
                window=btn_frame,
                anchor="n"
            )

            self.photo_items.append((image_id, text_id, photo, path, button_window_id))

        if self.photo_items:
            bbox = self.canvas.bbox("all")
            self.canvas.config(scrollregion=bbox)
        else:
            canvas_width = self.canvas.winfo_width() or 800
            self.canvas.config(scrollregion=(0, 0, canvas_width, 0))

    def remove_photo(self, path):
        self.photos = [p for p in self.photos if p[0] != path]
        self.load_photos()

    def sort_by_name(self):
        self.photos.sort(key=lambda x: os.path.basename(x[0]).lower())
        self.update_sort_button_styles("name")
        self.load_photos()

    def sort_by_timestamp(self):
        self.photos.sort(key=lambda x: x[1])
        self.update_sort_button_styles("time")
        self.load_photos()

    # ---- FULL-PHOTO PREVIEW ----
    def show_photo_preview(self, path):
        win = tk.Toplevel(self.window)
        win.title(os.path.basename(path))
        win.configure(bg=BG)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        max_w = int(sw * 0.8)
        max_h = int(sh * 0.8)

        try:
            img = open_image_for_pillow(path)
            img_ratio = img.width / img.height
            max_ratio = max_w / max_h

            if img.width > max_w or img.height > max_h:
                if img_ratio > max_ratio:
                    new_w = max_w
                    new_h = int(max_w / img_ratio)
                else:
                    new_h = max_h
                    new_w = int(max_h * img_ratio)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")
            win.destroy()
            return

        lbl = tk.Label(win, image=photo, bg=BG)
        lbl.pack(padx=10, pady=10)
        win.image = photo  # keep reference

    # ---- SCROLLING ----
    def on_mouse_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_canvas_resize(self, event):
        # Reflow the grid when the window is resized
        self.load_photos()
        if self.canvas.bbox("all"):
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    # ---- DRAG & DROP ----
    def find_photo_at(self, x, y):
        for idx, (image_id, text_id, photo, path, button_id) in enumerate(self.photo_items):
            ix, iy = self.canvas.coords(image_id)
            x1, y1 = ix, iy
            x2 = x1 + self.thumb_size[0]
            y2 = y1 + self.thumb_size[1]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx
        return None

    def on_press(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        idx = self.find_photo_at(cx, cy)
        if idx is not None:
            self.dragged_index = idx
            self.last_drag_x = cx
            self.last_drag_y = cy
            if self.drop_indicator:
                self.canvas.delete(self.drop_indicator)
                self.drop_indicator = None

    def on_drag(self, event):
        if self.dragged_index is None:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        dx = cx - self.last_drag_x
        dy = cy - self.last_drag_y
        self.last_drag_x = cx
        self.last_drag_y = cy

        image_id, text_id, photo, path, button_id = self.photo_items[self.dragged_index]
        self.canvas.move(image_id, dx, dy)
        self.canvas.move(text_id, dx, dy)
        self.canvas.move(button_id, dx, dy)

        # Compute where we are in the grid
        canvas_width, per_tile_width, per_tile_height, cols = self.get_grid_params()
        ix, iy = self.canvas.coords(image_id)
        center_x = ix + self.thumb_size[0] / 2
        center_y = iy + self.thumb_size[1] / 2

        col = int((center_x - self.margin_x) // per_tile_width)
        row = int((center_y - self.margin_y) // per_tile_height)
        col = max(0, min(cols - 1, col))
        new_index = max(0, min(row * cols + col, len(self.photos) - 1))

        target_row = new_index // cols
        target_col = new_index % cols
        tx = self.margin_x + target_col * per_tile_width
        ty = self.margin_y + target_row * per_tile_height

        # Vertical line between tiles (before/after)
        if center_x < tx + self.thumb_size[0] / 2:
            line_x = tx - 5  # before tile
        else:
            line_x = tx + self.thumb_size[0] + 5  # after tile

        line_y1 = ty
        line_y2 = ty + self.thumb_size[1]

        if self.drop_indicator:
            self.canvas.delete(self.drop_indicator)
        self.drop_indicator = self.canvas.create_line(
            line_x, line_y1, line_x, line_y2,
            fill="red", width=3, dash=(4, 4)
        )

    def on_release(self, event):
        if self.dragged_index is None:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        canvas_width, per_tile_width, per_tile_height, cols = self.get_grid_params()
        col = int((cx - self.margin_x) // per_tile_width)
        row = int((cy - self.margin_y) // per_tile_height)
        col = max(0, min(cols - 1, col))
        new_index = max(0, min(row * cols + col, len(self.photos) - 1))

        if new_index != self.dragged_index:
            item = self.photos.pop(self.dragged_index)
            self.photos.insert(new_index, item)

        self.dragged_index = None
        self.last_drag_x = None
        self.last_drag_y = None
        if self.drop_indicator:
            self.canvas.delete(self.drop_indicator)
            self.drop_indicator = None

        self.load_photos()

    # ---- RENAME & GENERATE ----
    def rename_photos(self):
        if not self.photos:
            return
        photo_folder = os.path.dirname(self.photos[0][0])
        temp_photos = []
        
        for idx, (path, ts, coords) in enumerate(self.photos):
            ext = os.path.splitext(path)[1]
            temp_path = os.path.join(photo_folder, f"temp_{idx}{ext}")
            shutil.move(path, temp_path)
            temp_photos.append((temp_path, ts, coords))
        
        new_photos = []
        for idx, (temp_path, ts, coords) in enumerate(temp_photos):
            ext = os.path.splitext(temp_path)[1]
            new_path = os.path.join(photo_folder, f"Photo {idx + 1}{ext}")
            shutil.move(temp_path, new_path)
            new_photos.append((new_path, ts, coords))
        
        self.photos = new_photos

    def generate_pdf(self):
        self.rename_photos()
        self.window.destroy()
        self.on_generate(self.photos, self.output_path, self.logo_path)


# ----------------- MAIN APP -----------------
class PhotologApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photolog Generator")
        self.root.geometry("520x480")
        self.root.configure(bg=BG)

        # ttk style
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("TEntry", fieldbackground=PANEL_BG, foreground=FG)
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT), ("!disabled", ACCENT)],
            foreground=[("!disabled", "white")]
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=PANEL_BG,
            bordercolor=PANEL_BG,
            background=ACCENT
        )

        container = tk.Frame(root, bg=BG)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.photo_label = ttk.Label(container, text="Photo Folder:")
        self.photo_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.photo_entry = ttk.Entry(container, width=40)
        self.photo_entry.grid(row=1, column=0, sticky="we")
        self.photo_button = ttk.Button(container, text="Browse", command=self.browse_photo_folder)
        self.photo_button.grid(row=1, column=1, padx=(8, 0))

        self.output_label = ttk.Label(container, text="Output Location:")
        self.output_label.grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.output_entry = ttk.Entry(container, width=40)
        self.output_entry.grid(row=3, column=0, sticky="we")
        self.output_button = ttk.Button(container, text="Browse", command=self.browse_output_location)
        self.output_button.grid(row=3, column=1, padx=(8, 0))

        self.logo_label = ttk.Label(container, text="Logo File:")
        self.logo_label.grid(row=4, column=0, sticky="w", pady=(12, 4))
        self.logo_entry = ttk.Entry(container, width=40)
        self.logo_entry.grid(row=5, column=0, sticky="we")
        self.logo_button = ttk.Button(container, text="Browse", command=self.browse_logo_file)
        self.logo_button.grid(row=5, column=1, padx=(8, 0))

        container.columnconfigure(0, weight=1)

        self.progress = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(container, variable=self.progress, maximum=100, mode="determinate")
        self.progress_bar.grid(row=6, column=0, columnspan=2, sticky="we", pady=(18, 4))
        self.progress_label = ttk.Label(container, text="Progress: 0%")
        self.progress_label.grid(row=7, column=0, columnspan=2, sticky="w")

        self.preview_button = ttk.Button(
            container,
            text="Preview Photos",
            style="Accent.TButton",
            command=self.preview_photos
        )
        self.preview_button.grid(row=8, column=0, columnspan=2, pady=(16, 10))

        self.joke_label = ttk.Label(
            container,
            text=get_dad_joke(),
            wraplength=420,
            anchor="center",
            justify="center"
        )
        self.joke_label.grid(row=9, column=0, columnspan=2, pady=(10, 0))

    def browse_photo_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.photo_entry.delete(0, tk.END)
            self.photo_entry.insert(0, folder)

    def browse_output_location(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, folder)

    def browse_logo_file(self):
        file = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if file:
            self.logo_entry.delete(0, tk.END)
            self.logo_entry.insert(0, file)

    def update_progress(self, percentage):
        self.progress.set(percentage)
        self.progress_label.config(text=f"Progress: {int(percentage)}%")
        self.root.update_idletasks()

    def preview_photos(self):
        photo_folder = self.photo_entry.get()
        output_path = self.output_entry.get()
        logo_path = self.logo_entry.get()

        if not photo_folder or not output_path or not logo_path:
            messagebox.showerror("Error", "Please fill in all fields.")
            return

        if not os.path.exists(photo_folder):
            messagebox.showerror("Error", f"Photo folder not found: {photo_folder}")
            return

        photos = []
        for filename in os.listdir(photo_folder):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.heif')):
                path = os.path.join(photo_folder, filename)
                try:
                    timestamp, coords = get_photo_metadata(path)
                except Exception as e:
                    print(f"Metadata read failed for {path}: {e}")
                    timestamp = datetime.fromtimestamp(os.path.getmtime(path))
                    coords = None
                photos.append((path, timestamp, coords))

        if not photos:
            messagebox.showerror("Error", "No supported images found in the selected folder.")
            return

        photos.sort(key=lambda x: os.path.basename(x[0]).lower())

        PhotoPreviewWindow(self.root, photos, output_path, logo_path, self.start_generate_photolog)

    def start_generate_photolog(self, photos, output_path, logo_path):
        self.preview_button.config(state="disabled")
        self.progress.set(0)
        threading.Thread(target=self.generate_photolog, args=(photos, output_path, logo_path), daemon=True).start()

    def generate_photolog(self, photos, output_path, logo_path):
        try:
            create_photolog(photos, output_path, logo_path, self.update_progress)
            self.root.after(0, self.show_success)
        except Exception as e:
            self.root.after(0, lambda err=e: messagebox.showerror("Error", f"An error occurred: {str(err)}"))
        finally:
            self.root.after(0, lambda: self.preview_button.config(state="normal"))

    def show_success(self):
        top = tk.Toplevel(self.root)
        top.title("Success")
        top.geometry("400x200")
        top.configure(bg=BG)
        
        label = ttk.Label(top, text="Photolog created successfully!")
        label.pack(pady=10)
        
        joke = get_dad_joke()
        joke_label = ttk.Label(top, text=joke, wraplength=380, justify="center")
        joke_label.pack(pady=10)
        
        close_button = ttk.Button(top, text="Close", command=top.destroy)
        close_button.pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotologApp(root)
    root.mainloop()
