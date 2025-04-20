import sys
import os
import shutil
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QScrollArea, QGridLayout, # Keep QGridLayout
    QSplitter, QTextEdit, QFrame, QSizePolicy, QSpacerItem,
    QListWidget, QListWidgetItem, QAbstractItemView, QProgressBar # Keep QListWidget/Item
)
from PySide6.QtGui import (
    QPixmap, QPixmapCache, QAction, QKeySequence, QPalette, QColor,
    QTextCursor, QIcon, QPainter, QPen
)
from PySide6.QtCore import (
    Qt, QSize, QTimer, Slot, QStandardPaths
)

# Constants
THUMBNAIL_SIZES = {
    "small": 80,
    "medium": 150,
    "large": 250,
    "xlarge": 400
}
DEFAULT_THUMBNAIL_SIZE = "medium"
LOG_SAVE_INTERVAL = 2000
MAX_LOG_LINES = 1000
PATH_AREA_WIDTH = 350
ROW_VERTICAL_PADDING = 10
# Custom data role for storing image path in QListWidgetItem
ImagePathRole = Qt.ItemDataRole.UserRole + 1

# --- ImageLabelWidget (No changes needed) ---
class ImageLabelWidget(QWidget):
    """Widget to display an image thumbnail with a fixed size based on scaled pixmap."""
    def __init__(self, image_path, thumbnail_size_bound, parent_row):
        super().__init__(parent_row)
        self.image_path = image_path
        self.thumbnail_size_bound = thumbnail_size_bound # Store the bound
        self.parent_row = parent_row
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout.addWidget(self.image_label)
        self.set_thumbnail()

    def set_thumbnail(self):
        cache_key = f"{self.image_path}_{self.thumbnail_size_bound}"
        pixmap = QPixmapCache.find(cache_key)
        scaled_size = QSize(self.thumbnail_size_bound, self.thumbnail_size_bound)

        if not pixmap:
            original_pixmap = QPixmap(self.image_path)
            if not original_pixmap.isNull():
                pixmap = original_pixmap.scaled(scaled_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                if not pixmap.isNull(): # Check if scaling was successful
                    QPixmapCache.insert(cache_key, pixmap)
                else:
                     print(f"Warning: Failed to scale pixmap for {os.path.basename(self.image_path)}")
                     pixmap = None # Indicate failure to trigger error display
            else:
                print(f"Warning: Failed to load pixmap for {os.path.basename(self.image_path)}")
                pixmap = None # Indicate failure

        if pixmap and not pixmap.isNull():
            actual_pixmap_size = pixmap.size()
            self.image_label.setPixmap(pixmap)
            self.image_label.setFixedSize(actual_pixmap_size)
            self.setFixedSize(actual_pixmap_size)
        else:
             # Final fallback / error display
             error_size = QSize(self.thumbnail_size_bound // 2, self.thumbnail_size_bound // 2)
             pixmap = QPixmap(error_size)
             pixmap.fill(Qt.GlobalColor.lightGray)
             try:
                 painter = QPainter(pixmap)
                 pen = QPen(Qt.GlobalColor.red)
                 painter.setPen(pen)
                 painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Load\nError")
                 painter.end()
             except Exception as paint_error:
                 print(f"Error drawing placeholder text: {paint_error}")

             self.image_label.setPixmap(pixmap)
             self.image_label.setFixedSize(error_size)
             self.setFixedSize(error_size)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Tell the parent row (ImageRowWidget) about the click
            self.parent_row.handle_thumbnail_click()
        super().mousePressEvent(event)

    def update_thumbnail_size(self, new_size_bound):
        """Updates the target bounding size and regenerates the thumbnail."""
        if self.thumbnail_size_bound != new_size_bound:
            old_cache_key = f"{self.image_path}_{self.thumbnail_size_bound}"
            QPixmapCache.remove(old_cache_key)
            self.thumbnail_size_bound = new_size_bound
            self.set_thumbnail()


# --- ImageRowWidget (Adjusted for QListWidget context) ---
class ImageRowWidget(QWidget):
    """Represents the visual content of a single row within a QListWidgetItem."""
    def __init__(self, image_path, initial_label, thumbnail_size_bound, main_window, list_item, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageRowWidget") # For styling if needed
        self.image_path = image_path
        self.current_label = initial_label
        self.thumbnail_size_bound = thumbnail_size_bound
        self.main_window = main_window
        self.list_item = list_item # Keep reference to the list item
        self.selected = False # Internal state for styling
        # Let QListWidget manage the overall size policy

        self.row_layout = QHBoxLayout(self)
        self.row_layout.setContentsMargins(5, 2, 5, 2)
        self.row_layout.setSpacing(10)

        # Path Label
        self.path_label = QLabel(os.path.basename(image_path))
        self.path_label.setToolTip(image_path)
        self.path_label.setFixedWidth(PATH_AREA_WIDTH)
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.path_label.setWordWrap(True)
        self.row_layout.addWidget(self.path_label, 0)

        # Spacers and Thumbnail
        self.left_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.row_layout.addSpacerItem(self.left_spacer)
        self.thumbnail_widget = ImageLabelWidget(image_path, thumbnail_size_bound, self)
        self.row_layout.addWidget(self.thumbnail_widget, 0, Qt.AlignmentFlag.AlignCenter)
        self.right_spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.row_layout.addSpacerItem(self.right_spacer)

        self.update_thumbnail_position()
        self._adjust_widget_height() # Adjust initial height based on content

    def _adjust_widget_height(self):
        """Adjusts the height hint for this widget based on content."""
        thumb_height = self.thumbnail_widget.height()
        path_height = self.path_label.sizeHint().height()
        # Use dynamic padding like before
        dynamic_padding = max(ROW_VERTICAL_PADDING, int(self.thumbnail_widget.thumbnail_size_bound * 0.30))
        target_height = max(thumb_height + dynamic_padding, path_height + dynamic_padding)
        # Set fixed height for THIS widget, QListWidgetItem will use its sizeHint
        self.setFixedHeight(target_height)
        # Crucially, update the list item's size hint
        if self.list_item:
            self.list_item.setSizeHint(self.sizeHint()) # Use sizeHint which respects fixed height

    def update_thumbnail_position(self):
        """Sets stretch factors for alignment."""
        if self.current_label == 'center':
            self.row_layout.setStretch(1, 1)
            self.row_layout.setStretch(3, 1)
        else: # 'not_center'
            self.row_layout.setStretch(1, 0)
            self.row_layout.setStretch(3, 1)
        self.row_layout.setStretch(2, 0) # Thumbnail never stretches
        self.row_layout.activate()

    def set_label(self, new_label):
        """Updates the internal label and repositions the thumbnail."""
        if self.current_label != new_label:
            self.current_label = new_label
            self.update_thumbnail_position()

    def handle_thumbnail_click(self):
        """Handles clicks on the thumbnail, tells MainWindow to toggle."""
        self.main_window.handle_row_interaction(self.list_item, toggle_label=True)

    def set_selected_style(self, selected):
         """Applies visual styling based on the selection state (called by MainWindow)."""
         self.selected = selected
         if self.selected:
              # Use a simpler style that doesn't rely on objectName for QListWidget context
              self.setStyleSheet("QWidget { border: 2px solid dodgerblue; background-color: #e0e8f0; }")
         else:
              self.setStyleSheet("QWidget { border: none; background-color: transparent; }")

    def update_thumbnail_size(self, new_size_bound):
        """Updates the thumbnail size and adjusts widget height."""
        if self.thumbnail_size_bound != new_size_bound:
            self.thumbnail_size_bound = new_size_bound
            self.thumbnail_widget.update_thumbnail_size(new_size_bound)
            self._adjust_widget_height() # Recalculate height and update list item hint

    def mousePressEvent(self, event):
        """Handles clicks directly on the row's background area."""
        if event.button() == Qt.MouseButton.LeftButton:
             # Tell MainWindow to select this item
             self.main_window.handle_row_interaction(self.list_item, toggle_label=False)
        super().mousePressEvent(event)


# --- MainWindow (Refactored to use QListWidget) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("High-Throughput Image Review Tool")
        self.setGeometry(100, 100, 1200, 800)

        # --- Internal State ---
        # image_data: {path: {'initial_label': str, 'current_label': str}}
        # We no longer store the widget directly here, we get it from the QListWidget item
        self.image_data = {}
        self.root_folder = None
        self.current_thumbnail_size_key = DEFAULT_THUMBNAIL_SIZE
        self.current_thumbnail_bound_px = THUMBNAIL_SIZES[self.current_thumbnail_size_key]
        self.pending_changes = 0
        self.log_entries = []
        self.log_save_timer = QTimer(self)
        self.log_save_timer.timeout.connect(self.save_log_file)
        self.log_needs_saving = False
        self.selected_image_path = None
        # self.ordered_paths = [] # No longer needed, QListWidget maintains order

        # --- Main UI Structure ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5,5,5,5)
        self.main_layout.setSpacing(5)

        # --- Top Bar Elements ---
        self.setup_top_bar()

        # --- List Widget for Image Rows ---
        self.setup_list_widget() # Changed from setup_scroll_area

        # --- Log Console ---
        self.setup_log_console()

        # --- Initialize Image Cache ---
        QPixmapCache.setCacheLimit(200 * 1024 * 1024)

        # --- Initial Status ---
        self.log_action("Application started.")
        self.update_counters()

    # setup_top_bar remains the same
    def setup_top_bar(self):
        """Creates and configures the top bar widgets."""
        self.top_bar = QWidget()
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(0,0,0,0)
        self.top_bar_layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setTextVisible(False)
        self.top_bar_layout.addWidget(self.progress_bar)

        self.btn_select_folder = QPushButton("Select Input Folder")
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.top_bar_layout.addWidget(self.btn_select_folder)

        self.lbl_folder_path = QLabel("No folder selected")
        self.lbl_folder_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.top_bar_layout.addWidget(self.lbl_folder_path)

        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_zoom_out.clicked.connect(lambda: self.set_zoom("out"))
        self.top_bar_layout.addWidget(self.btn_zoom_out)

        self.lbl_zoom_level = QLabel(f"Zoom: {self.current_thumbnail_size_key}")
        self.top_bar_layout.addWidget(self.lbl_zoom_level)

        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_in.clicked.connect(lambda: self.set_zoom("in"))
        self.top_bar_layout.addWidget(self.btn_zoom_in)

        self.lbl_image_count = QLabel("Image - / -")
        self.top_bar_layout.addWidget(self.lbl_image_count)

        self.lbl_pending_changes = QLabel("0 changes pending")
        self.top_bar_layout.addWidget(self.lbl_pending_changes)

        self.btn_apply_changes = QPushButton("Apply Changes")
        self.btn_apply_changes.clicked.connect(self.apply_changes)
        self.btn_apply_changes.setEnabled(False)
        self.top_bar_layout.addWidget(self.btn_apply_changes)

        self.main_layout.addWidget(self.top_bar)

    # Refactored to use QListWidget
    def setup_list_widget(self):
        """Creates and configures the QListWidget for image rows."""
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4) # Spacing between items
        self.list_widget.setStyleSheet("QListWidget { border: none; background-color: #f0f0f0; }")
        # Ensure vertical scrollbar appears when needed
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Connect selection signal
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        # Optional: Connect click signal if needed for specific interaction
        # self.list_widget.itemClicked.connect(self.on_item_clicked)

        self.main_layout.addWidget(self.list_widget, 1) # List widget takes expanding space

    # setup_log_console remains the same
    def setup_log_console(self):
        """Creates and configures the log console widget."""
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(100)
        self.log_console.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_console.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.main_layout.addWidget(self.log_console)

    # log_action and save_log_file remain the same
    def log_action(self, message, is_error=False):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {'ERROR: ' if is_error else ''}{message}"
        self.log_entries.append(log_entry)
        if hasattr(self, 'log_console') and self.log_console:
             self.log_console.append(log_entry)
             doc = self.log_console.document()
             if doc.blockCount() > MAX_LOG_LINES * 1.1:
                  cursor = self.log_console.textCursor()
                  cursor.movePosition(QTextCursor.MoveOperation.Start)
                  cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, doc.blockCount() - MAX_LOG_LINES)
                  cursor.removeSelectedText()
                  cursor.movePosition(QTextCursor.MoveOperation.End)
                  self.log_console.setTextCursor(cursor)
             self.log_console.ensureCursorVisible()
        self.log_needs_saving = True
        if hasattr(self, 'log_save_timer') and not self.log_save_timer.isActive():
            self.log_save_timer.start(LOG_SAVE_INTERVAL)

    @Slot()
    def save_log_file(self):
        if not self.root_folder or not self.log_needs_saving:
            if hasattr(self, 'log_save_timer'): self.log_save_timer.stop()
            return
        log_file_path = os.path.join(self.root_folder, "image_review_log.json")
        try:
            entries_to_save = self.log_entries[-MAX_LOG_LINES:]
            with open(log_file_path, 'w') as f: json.dump(entries_to_save, f, indent=2)
            self.log_needs_saving = False
        except Exception as e:
            self.log_action(f"Failed to save log file to {log_file_path}: {e}", is_error=True)
        finally:
            if hasattr(self, 'log_save_timer'): self.log_save_timer.stop()

    # select_folder remains the same
    @Slot()
    def select_folder(self):
        start_dir = self.root_folder if self.root_folder else QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        if not start_dir or not os.path.isdir(start_dir): start_dir = os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Image Folder", start_dir)
        if dir_path:
            center_path = os.path.join(dir_path, "center")
            not_center_path = os.path.join(dir_path, "not_center")
            if os.path.isdir(center_path) and os.path.isdir(not_center_path):
                if dir_path == self.root_folder:
                    self.log_action("Selected folder is already loaded.")
                    return
                self.root_folder = dir_path
                self.lbl_folder_path.setText(self.root_folder)
                self.lbl_folder_path.setToolTip(self.root_folder)
                self.log_action(f"Selected folder: {self.root_folder}")
                self.load_images()
            else:
                self.log_action("Selected folder must contain 'center' AND 'not_center' subdirectories.", is_error=True)
                self.root_folder = None
                self.lbl_folder_path.setText("Invalid folder selected")
                self.lbl_folder_path.setToolTip("")
                self.clear_images()

    # clear_layout is no longer needed for rows

    # Refactored clear_images for QListWidget
    def clear_images(self):
        """Clears all loaded image data, UI list items, and resets related state."""
        if hasattr(self, 'log_save_timer') and self.log_save_timer.isActive():
            self.log_save_timer.stop()

        # Block signals during clear to avoid triggering selection changes
        if hasattr(self, 'list_widget'):
            self.list_widget.blockSignals(True)
            self.list_widget.clear() # Clears items and removes item widgets
            self.list_widget.blockSignals(False)

        self.image_data = {}
        self.selected_image_path = None
        self.pending_changes = 0
        QPixmapCache.clear()
        self.update_counters()
        if hasattr(self, 'btn_apply_changes'):
            self.btn_apply_changes.setEnabled(False)
        self.log_action("Image cache and UI cleared.")

    # Refactored load_images for QListWidget
    def load_images(self):
        """Scans the selected folder, loads images, and populates the QListWidget."""
        if not self.root_folder:
            self.log_action("Cannot load images, no root folder selected.", is_error=True)
            return

        self.clear_images() # Start fresh
        self.log_action("Loading images...")
        center_dir = os.path.join(self.root_folder, "center")
        not_center_dir = os.path.join(self.root_folder, "not_center")
        image_files = []

        supported_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff')
        for label, directory in [("center", center_dir), ("not_center", not_center_dir)]:
            try:
                if not os.path.isdir(directory):
                    self.log_action(f"Directory not found: {directory}", is_error=True)
                    continue
                for filename in os.listdir(directory):
                    if filename.lower().endswith(supported_extensions):
                        full_path = os.path.abspath(os.path.join(directory, filename))
                        image_files.append((full_path, label))
            except Exception as e:
                 self.log_action(f"Error reading directory {directory}: {e}", is_error=True)

        if not image_files:
            self.log_action("No compatible image files found in 'center' or 'not_center'.")
            self.update_counters()
            return

        image_files.sort(key=lambda item: os.path.basename(item[0]))

        # --- Populate UI with QListWidgetItems ---
        self.list_widget.blockSignals(True) # Block signals during population
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        total_files = len(image_files)
        try:
            for i, (full_path, label) in enumerate(image_files):
                if full_path not in self.image_data:
                    # Store image info (without widget ref now)
                    self.image_data[full_path] = {
                        'initial_label': label,
                        'current_label': label
                    }

                    # Create List Item and store path
                    list_item = QListWidgetItem(self.list_widget) # Add item to list
                    list_item.setData(ImagePathRole, full_path)

                    # Create the custom widget for the item
                    row_widget = ImageRowWidget(
                        full_path, label, self.current_thumbnail_bound_px, self, list_item
                    )

                    # Set item's size hint based on widget's initial size
                    list_item.setSizeHint(row_widget.sizeHint())

                    # Associate the widget with the item
                    self.list_widget.setItemWidget(list_item, row_widget)

                    if i % 50 == 0 or i == total_files - 1:
                         progress = int(((i + 1) / total_files) * 100)
                         self.progress_bar.setValue(progress)
                         QApplication.processEvents()
        finally:
            self.list_widget.blockSignals(False) # Re-enable signals
            QApplication.restoreOverrideCursor()

        self.update_counters()
        self.log_action(f"Loaded {len(self.image_data)} images.")
        # Select the first item if list is not empty
        if self.list_widget.count() > 0:
             QTimer.singleShot(0, lambda: self.list_widget.setCurrentRow(0)) # Triggers on_current_item_changed

    # Slot for QListWidget's currentItemChanged signal
    @Slot(QListWidgetItem, QListWidgetItem)
    def on_current_item_changed(self, current_item, previous_item):
        """Handles selection changes in the QListWidget."""
        if previous_item:
            prev_widget = self.list_widget.itemWidget(previous_item)
            if isinstance(prev_widget, ImageRowWidget):
                prev_widget.set_selected_style(False)

        if current_item:
            current_path = current_item.data(ImagePathRole)
            current_widget = self.list_widget.itemWidget(current_item)
            if isinstance(current_widget, ImageRowWidget):
                 current_widget.set_selected_style(True)
                 # Ensure the newly selected item is visible
                 self.list_widget.scrollToItem(current_item, QAbstractItemView.ScrollHint.EnsureVisible)

            if current_path != self.selected_image_path:
                self.selected_image_path = current_path
                self.update_counters() # Update counters based on new selection
        else:
            self.selected_image_path = None
            self.update_counters()

    # Combined handler for clicks on row background or thumbnail
    def handle_row_interaction(self, list_item, toggle_label):
        """Handles clicks originating from ImageRowWidget or its thumbnail."""
        if not list_item: return
        path = list_item.data(ImagePathRole)
        if path not in self.image_data: return

        is_already_selected = (list_item == self.list_widget.currentItem())

        if is_already_selected and toggle_label:
             self.toggle_image_label(path) # Clicked thumbnail of selected -> toggle
        elif not is_already_selected:
             self.list_widget.setCurrentItem(list_item) # Clicked different row -> select
        # Else (clicked background of already selected and toggle_label=False) -> do nothing

    # Refactored toggle_image_label for QListWidget context
    def toggle_image_label(self, path):
        """Toggles the current_label of the image and updates UI + pending changes."""
        if path in self.image_data:
            img_info = self.image_data[path]
            # Find the list item and its widget
            list_item = self.find_list_item_by_path(path)
            if not list_item: return
            row_widget = self.list_widget.itemWidget(list_item)
            if not isinstance(row_widget, ImageRowWidget): return

            old_label = img_info['current_label']
            new_label = 'not_center' if old_label == 'center' else 'center'

            img_info['current_label'] = new_label
            row_widget.set_label(new_label) # Update row widget's state/layout
            self.log_action(f"Toggled '{os.path.basename(path)}' from '{old_label}' to '{new_label}'")

            # Update Pending Changes Count (logic remains the same)
            is_now_different = (img_info['current_label'] != img_info['initial_label'])
            was_different_before = (old_label != img_info['initial_label'])
            pending_change_updated = False
            if is_now_different and not was_different_before:
                self.pending_changes += 1; pending_change_updated = True
            elif not is_now_different and was_different_before:
                 self.pending_changes -= 1; pending_change_updated = True

            if pending_change_updated:
                self.update_counters()
                if hasattr(self, 'btn_apply_changes'):
                    self.btn_apply_changes.setEnabled(self.pending_changes > 0)

    # Refactored update_counters for QListWidget
    def update_counters(self):
        """Updates the image count label, pending changes label, and progress bar."""
        total_images = self.list_widget.count() # Get count from list widget
        current_index_display = "-"
        progress_value = 0

        current_item = self.list_widget.currentItem()
        if total_images > 0 and current_item:
            current_row = self.list_widget.row(current_item)
            current_index_display = current_row + 1
            progress_value = int(((current_row + 1) / total_images) * 100)
        elif total_images > 0:
            # Handle case where there are items but none selected (e.g., after clear)
            current_index_display = "-"
        # else: No images loaded

        if hasattr(self, 'lbl_image_count'):
            self.lbl_image_count.setText(f"Image {current_index_display} / {total_images}")
        if hasattr(self, 'lbl_pending_changes'):
            self.lbl_pending_changes.setText(f"{self.pending_changes} changes pending")
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(progress_value)

    # Helper to find QListWidgetItem by stored path
    def find_list_item_by_path(self, path):
        """Finds the QListWidgetItem associated with a given image path."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(ImagePathRole) == path:
                return item
        return None

    # Refactored select_image_by_path for QListWidget
    def select_image_by_path(self, path):
        """Selects the list item corresponding to the given path."""
        item_to_select = self.find_list_item_by_path(path)
        if item_to_select:
            # Setting current item triggers on_current_item_changed, which handles styling and state updates
            self.list_widget.setCurrentItem(item_to_select)
        else:
             self.log_action(f"Error: Could not find list item for path: {path}", is_error=True)


    # Refactored select_next/previous_image for QListWidget
    def select_next_image(self):
        """Selects the next item in the QListWidget."""
        current_row = self.list_widget.currentRow()
        next_row = current_row + 1
        if 0 <= next_row < self.list_widget.count():
            self.list_widget.setCurrentRow(next_row)
        elif self.list_widget.count() > 0:
             self.log_action("Reached the last image.")
             # Optionally wrap around: self.list_widget.setCurrentRow(0)

    def select_previous_image(self):
        """Selects the previous item in the QListWidget."""
        current_row = self.list_widget.currentRow()
        prev_row = current_row - 1
        if prev_row >= 0:
            self.list_widget.setCurrentRow(prev_row)
        elif current_row == 0 and self.list_widget.count() > 0:
             self.log_action("Reached the first image.")
             # Optionally wrap around: self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    # change_selected_label remains conceptually the same (operates on self.selected_image_path)
    def change_selected_label(self, target_label):
         """Changes the label of the currently selected image."""
         current_item = self.list_widget.currentItem()
         if current_item:
             path = current_item.data(ImagePathRole)
             if path and path in self.image_data:
                 img_info = self.image_data[path]
                 if img_info['current_label'] != target_label:
                     self.toggle_image_label(path) # toggle_image_label handles UI and state

    # Refactored apply_changes for QListWidget
    @Slot()
    def apply_changes(self):
        """Moves files and updates internal state and QListWidget items."""
        if not self.root_folder or self.pending_changes == 0:
            if self.pending_changes == 0: self.log_action("No pending changes to apply.")
            return

        self.log_action(f"Applying {self.pending_changes} changes...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.list_widget.blockSignals(True) # Block signals during update

        moved_count = 0
        error_count = 0
        paths_to_update_in_data = {} # {old_path: new_path}

        items_to_process = list(self.image_data.items()) # Process a copy

        for path, img_info in items_to_process:
            if img_info['current_label'] != img_info['initial_label']:
                # File move logic (same as before)
                initial_dir = os.path.join(self.root_folder, img_info['initial_label'])
                target_dir = os.path.join(self.root_folder, img_info['current_label'])
                filename = os.path.basename(path)
                actual_source_path = path
                destination_path = os.path.join(target_dir, filename)

                if not os.path.exists(actual_source_path):
                     self.log_action(f"Error: Source file not found: {actual_source_path}. Skipping.", is_error=True)
                     error_count += 1
                     continue
                if os.path.abspath(actual_source_path) == os.path.abspath(destination_path):
                     self.log_action(f"Warning: Skipping move for '{filename}', source/destination identical.", is_error=True)
                     img_info['initial_label'] = img_info['current_label']
                     moved_count += 1
                     continue
                try:
                    os.makedirs(target_dir, exist_ok=True)
                    shutil.move(actual_source_path, destination_path)
                    self.log_action(f"Moved '{filename}' from '{img_info['initial_label']}' to '{img_info['current_label']}'")
                    new_path = os.path.abspath(destination_path)
                    paths_to_update_in_data[path] = new_path # Record success
                    moved_count += 1
                except Exception as e:
                    self.log_action(f"Error: Failed to move '{filename}': {e}", is_error=True)
                    error_count += 1

        # --- Batch Update Internal State and List Items After All Moves ---
        if paths_to_update_in_data:
            new_image_data = {}
            current_selection_final_path = self.selected_image_path

            # Iterate through list items to update paths and data
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                old_path = item.data(ImagePathRole)

                if old_path in paths_to_update_in_data:
                    new_path = paths_to_update_in_data[old_path]
                    # Update item data
                    item.setData(ImagePathRole, new_path)
                    # Update widget paths
                    widget = self.list_widget.itemWidget(item)
                    if isinstance(widget, ImageRowWidget):
                        widget.image_path = new_path
                        widget.path_label.setToolTip(new_path)
                        if hasattr(widget, 'thumbnail_widget'):
                            widget.thumbnail_widget.image_path = new_path
                        QPixmapCache.remove(f"{old_path}_{widget.thumbnail_size_bound}")

                    # Update image_data dictionary key and reset initial label
                    img_info = self.image_data.pop(old_path) # Remove old entry
                    img_info['initial_label'] = img_info['current_label'] # Mark as applied
                    new_image_data[new_path] = img_info # Add new entry

                    # Track if selection path changed
                    if old_path == self.selected_image_path:
                        current_selection_final_path = new_path
                elif old_path in self.image_data:
                    # If not moved, just transfer existing data to new dict
                    new_image_data[old_path] = self.image_data[old_path]

            # Replace internal data store
            self.image_data = new_image_data
            self.selected_image_path = current_selection_final_path

        # --- Final Logging and UI Update ---
        self.list_widget.blockSignals(False) # Re-enable signals
        QApplication.restoreOverrideCursor()
        self.log_action(f"Apply changes finished. Moved: {moved_count}, Errors: {error_count}")

        self.pending_changes -= moved_count
        if self.pending_changes < 0: self.pending_changes = 0

        self.update_counters()
        if hasattr(self, 'btn_apply_changes'):
            self.btn_apply_changes.setEnabled(self.pending_changes > 0)

        # Re-select the current item if its path changed, to ensure UI consistency
        if self.selected_image_path:
            self.select_image_by_path(self.selected_image_path)

        self.save_log_file()


    # Refactored set_zoom for QListWidget
    def set_zoom(self, direction):
        """Changes the thumbnail size and updates all list items/widgets."""
        keys = list(THUMBNAIL_SIZES.keys())
        try: current_index = keys.index(self.current_thumbnail_size_key)
        except ValueError: current_index = keys.index(DEFAULT_THUMBNAIL_SIZE)

        new_index = current_index
        if direction == "in": new_index = min(len(keys) - 1, current_index + 1)
        elif direction == "out": new_index = max(0, current_index - 1)

        if new_index != current_index:
            self.current_thumbnail_size_key = keys[new_index]
            new_bound_px = THUMBNAIL_SIZES[self.current_thumbnail_size_key]

            if new_bound_px == self.current_thumbnail_bound_px: return

            self.current_thumbnail_bound_px = new_bound_px
            self.lbl_zoom_level.setText(f"Zoom: {self.current_thumbnail_size_key}")
            self.log_action(f"Zoom set to {self.current_thumbnail_size_key} (max {self.current_thumbnail_bound_px}px)")

            # --- Perform bulk update of Row Widgets and Item Size Hints ---
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.list_widget.setUpdatesEnabled(False) # Prevent flicker
            try:
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    widget = self.list_widget.itemWidget(item)
                    if isinstance(widget, ImageRowWidget):
                        # Update widget's thumbnail and height
                        widget.update_thumbnail_size(self.current_thumbnail_bound_px)
                        # *** CRITICAL: Update the item's size hint ***
                        item.setSizeHint(widget.sizeHint())
            finally:
                 self.list_widget.setUpdatesEnabled(True) # Re-enable updates
                 QApplication.restoreOverrideCursor()

            # Ensure selection remains visible after potential size changes
            current_item = self.list_widget.currentItem()
            if current_item:
                 QTimer.singleShot(0, lambda: self.list_widget.scrollToItem(current_item, QAbstractItemView.ScrollHint.EnsureVisible))


    # resizeEvent remains the same
    def resizeEvent(self, event):
        super().resizeEvent(event)

    # closeEvent remains the same
    def closeEvent(self, event):
        if self.pending_changes > 0:
            self.log_action(f"Application closing with {self.pending_changes} pending changes.")
        else:
             self.log_action("Application closed.")
        self.save_log_file()
        QPixmapCache.clear()
        super().closeEvent(event)

    # Refactored keyPressEvent for QListWidget
    def keyPressEvent(self, event):
        """Handles keyboard shortcuts for navigation and actions."""
        key = event.key()
        mods = event.modifiers()

        # Global shortcuts (remain the same)
        if key == Qt.Key.Key_O and mods == Qt.KeyboardModifier.ControlModifier:
             self.select_folder(); event.accept(); return
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) or \
             (key == Qt.Key.Key_Plus and mods == Qt.KeyboardModifier.KeypadModifier):
             self.set_zoom("in"); event.accept(); return
        elif key == Qt.Key.Key_Minus or \
             (key == Qt.Key.Key_Minus and mods == Qt.KeyboardModifier.KeypadModifier):
              self.set_zoom("out"); event.accept(); return
        elif key == Qt.Key.Key_S and mods == Qt.KeyboardModifier.ControlModifier:
             self.apply_changes(); event.accept(); return

        # Shortcuts requiring selection
        current_item = self.list_widget.currentItem()
        if not current_item:
             super().keyPressEvent(event) # No item selected, pass event up
             return

        path = current_item.data(ImagePathRole)
        if not path:
             super().keyPressEvent(event) # Item has no path data, pass event up
             return

        accepted = True
        # Navigation is handled by QListWidget automatically (Up/Down/Space)
        # We just need to handle the labeling actions
        if key == Qt.Key.Key_A or key == Qt.Key.Key_Left: # A or Left -> not_center
             self.change_selected_label('not_center')
        elif key == Qt.Key.Key_D or key == Qt.Key.Key_Right: # D or Right -> center
              self.change_selected_label('center')
        elif key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
             self.toggle_image_label(path) # Toggle the current item's label
        else:
            # Let QListWidget handle default navigation (Up, Down, PageUp, PageDown, Home, End, Space)
            accepted = False
            super().keyPressEvent(event)

        if accepted: event.accept()


if __name__ == '__main__':
    # High DPI scaling is generally handled automatically in Qt6/PySide6
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())
