import sys
import pandas as pd
import os
import time
import requests
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QTableView,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QProgressBar, 
    QMessageBox, QStatusBar, QDialog, QFormLayout, QDialogButtonBox,
    QGroupBox, QGridLayout, QAction, QMenu, QAbstractItemView
)
from PyQt5.QtCore import Qt, QAbstractTableModel, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from typing import Callable, Optional, Dict, List, Tuple
from urllib.parse import parse_qs

# Add src/ to Python path to import the screenshot function
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, '..')
sys.path.insert(0, SRC_DIR)

# Import the modified function
from src.tools.csv_screenshots import process_csv_screenshots

# --- Parameter Dialog ---
class ParameterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres de capture")
        self.setModal(True)
        self.resize(400, 350)
        
        layout = QVBoxLayout(self)
        
        # Create group boxes for organization
        processing_group = QGroupBox("Paramètres de traitement")
        processing_layout = QGridLayout()
        
        # Batch size
        processing_layout.addWidget(QLabel("Batch size:"), 0, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setValue(10)
        self.batch_size_spin.setRange(1, 1000)
        processing_layout.addWidget(self.batch_size_spin, 0, 1)
        
        # Max workers
        processing_layout.addWidget(QLabel("Max workers:"), 1, 0)
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setValue(3)
        self.max_workers_spin.setRange(1, 50)
        processing_layout.addWidget(self.max_workers_spin, 1, 1)
        
        # Delay
        processing_layout.addWidget(QLabel("Delay (s):"), 2, 0)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setValue(0.5)
        self.delay_spin.setRange(0, 10)
        self.delay_spin.setSingleStep(0.1)
        processing_layout.addWidget(self.delay_spin, 2, 1)
        
        # Start row
        processing_layout.addWidget(QLabel("Start row:"), 3, 0)
        self.start_row_spin = QSpinBox()
        self.start_row_spin.setMinimum(0)
        self.start_row_spin.setMaximum(1000000)
        self.start_row_spin.setValue(0)
        processing_layout.addWidget(self.start_row_spin, 3, 1)
        
        # Screenshot type
        processing_layout.addWidget(QLabel("Screenshot type:"), 4, 0)
        self.screenshot_type_combo = QComboBox()
        self.screenshot_type_combo.addItems(["fullpage", "content", "both"])
        processing_layout.addWidget(self.screenshot_type_combo, 4, 1)
        
        # NEW: Image format selection
        processing_layout.addWidget(QLabel("Format image:"), 5, 0)
        self.image_format_combo = QComboBox()
        self.image_format_combo.addItems(["png", "jpeg", "webp"])
        processing_layout.addWidget(self.image_format_combo, 5, 1)
        
        processing_group.setLayout(processing_layout)
        layout.addWidget(processing_group)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Check if parent has dark mode enabled
        if parent and hasattr(parent, 'dark_mode_enabled') and parent.dark_mode_enabled:
            self.setStyleSheet(parent.get_dark_mode_stylesheet())
    
    def get_parameters(self):
        return {
            'batch_size': self.batch_size_spin.value(),
            'max_workers': self.max_workers_spin.value(),
            'delay': self.delay_spin.value(),
            'start_row': self.start_row_spin.value(),
            'screenshot_type': self.screenshot_type_combo.currentText(),
            'image_format': self.image_format_combo.currentText()
        }

# --- API Connection Dialog ---
class APIConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connexion API")
        self.setModal(True)
        self.resize(500, 300)
        
        layout = QFormLayout(self)
        
        # API URL
        self.api_url_input = QLineEdit()
        self.api_url_input.setPlaceholderText("https://api.example.com/endpoint")
        layout.addRow("URL de l'API:", self.api_url_input)
        
        # API Key (optional)
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Clé API (optionnel)")
        layout.addRow("Clé API:", self.api_key_input)
        
        # Parameters
        self.params_input = QLineEdit()
        self.params_input.setPlaceholderText("param1=value1&param2=value2")
        layout.addRow("Paramètres:", self.params_input)
        
        # Demo button
        self.demo_button = QPushButton("Utiliser les données de démonstration")
        self.demo_button.clicked.connect(self.use_demo_data)
        layout.addRow(self.demo_button)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_connection_data(self):
        return {
            'url': self.api_url_input.text(),
            'api_key': self.api_key_input.text(),
            'params': self.params_input.text(),
            'is_demo': False
        }
    
    def use_demo_data(self):
        """Prefill with demo data"""
        self.api_url_input.setText("demo")
        self.api_key_input.setText("")
        self.params_input.setText("")
        self.accept()

# --- API Worker Thread ---
class APIWorker(QThread):
    finished = pyqtSignal(pd.DataFrame)  # Emits the fetched data as DataFrame
    error = pyqtSignal(str)  # Emits error message
    
    def __init__(self, api_url, api_key=None, params=None, is_demo=False):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.params = params
        self.is_demo = is_demo
    
    def run(self):
        try:
            if self.is_demo:
                # Use demo data instead of real API call
                df = self.get_demo_data()
                self.finished.emit(df)
                return
                
            # Prepare headers
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
                headers['X-API-Key'] = self.api_key
            
            # Prepare parameters
            params_dict = {}
            if self.params:
                params_dict = parse_qs(self.params)
                # Convert single-item lists to values
                params_dict = {k: v[0] if len(v) == 1 else v for k, v in params_dict.items()}
            
            # Make API request
            response = requests.get(
                self.api_url, 
                headers=headers, 
                params=params_dict,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Convert to DataFrame (handle different response formats)
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                elif isinstance(data, dict) and 'results' in data:
                    df = pd.DataFrame(data['results'])
                elif isinstance(data, dict) and 'data' in data:
                    df = pd.DataFrame(data['data'])
                elif isinstance(data, dict) and 'articles' in data:
                    df = pd.DataFrame(data['articles'])
                else:
                    df = pd.DataFrame([data])
                
                self.finished.emit(df)
            else:
                self.error.emit(f"Erreur API: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.error.emit(f"Erreur de connexion: {str(e)}")
    
    def get_demo_data(self):
        """Return demo data with real websites for testing"""
        demo_data = {
            'lien_web': [
                'https://www.google.com',
                'https://www.github.com',
                'https://www.wikipedia.org',
                'https://www.stackoverflow.com',
                'https://www.python.org',
                'https://www.wikipedia.org/wiki/Artificial_intelligence',
                'https://www.github.com/topics/python',
                'https://stackoverflow.com/questions',
                'https://www.python.org/doc/',
                'https://www.google.com/search?q=python+programming'
            ],
            'id': ['google', 'github', 'wikipedia', 'stackoverflow', 'python', 
                  'ai_wiki', 'python_topics', 'so_questions', 'python_docs', 'google_python'],
            'support_titre': ['moteur_recherche', 'developpement', 'encyclopedie', 
                            'programmation', 'programmation', 'technologie', 
                            'developpement', 'programmation', 'documentation', 'recherche']
        }
        return pd.DataFrame(demo_data)

# --- CSV Processor Worker Thread ---
class CSVProcessorWorker(QThread):
    progress_updated = pyqtSignal(int, int, int, dict)  # processed, total, success, row_status
    finished = pyqtSignal(str)  # results path
    error_occurred = pyqtSignal(str)  # error message

    def __init__(self, csv_path: str, url_column: str, output_dir: str, 
                 filename_column: Optional[str], support_column: Optional[str],
                 batch_size: int, delay: float, max_workers: int, 
                 screenshot_type: str, start_row: int, selected_rows: List[int],
                 row_mapping: Dict[str, int], image_format: str = "png"):
        super().__init__()
        self.csv_path = csv_path
        self.url_column = url_column
        self.output_dir = output_dir
        self.filename_column = filename_column
        self.support_column = support_column
        self.batch_size = batch_size
        self.delay = delay
        self.max_workers = max_workers
        self.screenshot_type = screenshot_type
        self.start_row = start_row
        self.selected_rows = selected_rows
        self.row_mapping = row_mapping
        self.image_format = image_format
        self.row_status = {}  # {row_index: (success_status, error_message)}
        self.df = None  # Store the dataframe for real-time mapping

    def run(self):
        try:
            # Read the CSV file
            self.df = pd.read_csv(self.csv_path)
            
            # Filter to only selected rows if any are selected
            if self.selected_rows:
                self.df = self.df.iloc[self.selected_rows]
            
            # Apply start row and batch size
            total_rows = len(self.df)
            
            # Adjust start_row if it's beyond the dataframe length
            if self.start_row >= total_rows:
                self.error_occurred.emit(f"La ligne de départ ({self.start_row}) dépasse le nombre de lignes disponibles ({total_rows})")
                return
                
            # Apply start row (convert from 1-based to 0-based indexing)
            start_index = self.start_row - 1 if self.start_row > 0 else 0
            self.df = self.df.iloc[start_index:]
            
            # Apply batch size limit
            if self.batch_size and self.batch_size < len(self.df):
                self.df = self.df.head(self.batch_size)
            
            # Save filtered CSV to temporary file
            os.makedirs(self.output_dir, exist_ok=True)
            temp_csv_path = os.path.join(self.output_dir, "temp_selected_data.csv")
            self.df.to_csv(temp_csv_path, index=False)
            
            # REAL-TIME progress callback function
            def progress_callback(processed: int, total: int, success: int, row_status: dict):
                # Convert row indices from the chunk to global indices
                global_row_status = {}
                
                for chunk_index, (success_status, error_msg) in row_status.items():
                    # Get the URL for this chunk index
                    if chunk_index < len(self.df):
                        url = self.df.iloc[chunk_index][self.url_column]
                        if pd.notna(url) and str(url) in self.row_mapping:
                            global_index = self.row_mapping[str(url)]
                            global_row_status[global_index] = (success_status, error_msg)
                
                # Emit progress update with global row indices
                self.progress_updated.emit(processed, total, success, global_row_status)

            # Call the screenshot function with REAL progress callback
            results_path = process_csv_screenshots(
                csv_path=temp_csv_path,
                url_column=self.url_column,
                output_dir=self.output_dir,
                filename_column=self.filename_column,
                support_column=self.support_column,
                batch_size=len(self.df),
                delay=self.delay,
                max_workers=self.max_workers,
                screenshot_type=self.screenshot_type,
                start_row=0,
                progress_callback=progress_callback,  # REAL-TIME callback!
                image_format=self.image_format
            )
            
            # After processing, read the results to get final status
            if results_path and os.path.exists(results_path):
                results_df = pd.read_csv(results_path)
                for _, row in results_df.iterrows():
                    url = row.get(self.url_column, '')
                    if url in self.row_mapping:
                        row_idx = self.row_mapping[url]
                        success = row.get('screenshot_success', False) or row.get('content_screenshot_success', False)
                        error_msg = row.get('error', '') if not success else ""
                        
                        self.row_status[row_idx] = (success, error_msg)
                
                # Send final update with actual status
                success_count = sum(1 for status in self.row_status.values() if status[0])
                self.progress_updated.emit(len(self.df), len(self.df), success_count, self.row_status)
            
            # Clean up temporary file
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)
            
            self.finished.emit(results_path)
            
        except Exception as e:
            self.error_occurred.emit(str(e))

# --- Colorized Pandas DataFrame Model ---
class ColorizedPandasModel(QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df
        self._df_full = df.copy()
        self.processed_rows = {}  # {row_index: (success_status, error_message)}
        self.selected_rows = set()

    def rowCount(self, parent=None):
        return len(self._df)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        col = index.column()
        
        if role == Qt.DisplayRole:
            return str(self._df.iloc[row, col])
            
        # Color coding based on processing status
        elif role == Qt.BackgroundRole:
            if row in self.processed_rows:
                success_status, _ = self.processed_rows[row]
                if success_status:
                    # Light green for success (adjust for dark mode)
                    return QBrush(QColor(76, 175, 80))  # Brighter green
                else:
                    # Light red for failure (adjust for dark mode)
                    return QBrush(QColor(244, 67, 54))  # Brighter red
            elif row in self.selected_rows:
                # Light blue for selected (adjust for dark mode)
                return QBrush(QColor(66, 133, 244))  # Brighter blue
                
        # Add tooltip for error messages
        elif role == Qt.ToolTipRole:
            if row in self.processed_rows:
                success_status, error_message = self.processed_rows[row]
                if not success_status and error_message:
                    return f"Erreur: {error_message}"
                    
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            else:
                return str(section + 1)
        return None

    def update_processing_status(self, row_status):
        """Update the processing status of rows"""
        self.processed_rows.update(row_status)
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))

    def toggle_row_selection(self, row_index):
        """Toggle selection of a row"""
        if row_index in self.selected_rows:
            self.selected_rows.remove(row_index)
        else:
            self.selected_rows.add(row_index)
        self.dataChanged.emit(self.index(row_index, 0), self.index(row_index, self.columnCount()-1))

    def select_all_rows(self):
        """Select all rows"""
        self.selected_rows = set(range(self.rowCount()))
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))

    def deselect_all_rows(self):
        """Deselect all rows"""
        self.selected_rows = set()
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))

    def get_selected_rows(self):
        """Get list of selected row indices"""
        return list(self.selected_rows)

    def remove_selected_rows(self):
        """Remove selected rows from the dataframe"""
        if not self.selected_rows:
            return False
            
        # Remove selected rows
        self._df = self._df.drop(self._df.index[list(self.selected_rows)]).reset_index(drop=True)
        self._df_full = self._df_full.drop(self._df_full.index[list(self.selected_rows)]).reset_index(drop=True)
        
        # Clear selections and update
        self.selected_rows = set()
        self.layoutChanged.emit()
        return True

    def filter(self, text):
        """Filter dataframe by text search"""
        if text == "":
            self._df = self._df_full
        else:
            mask = self._df_full.apply(lambda row: row.astype(str).str.contains(text, case=False).any(), axis=1)
            self._df = self._df_full[mask]
        self.layoutChanged.emit()

# --- Main Window ---
class ScreenshotUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV Screenshots Tool")
        self.resize(1200, 750)

        # Keep CSV path and data source
        self.csv_path = None
        self.api_data = None
        self.data_source = None
        self.worker = None
        self.api_worker = None
        self.output_dir = None
        self.row_mapping = {}

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Tout sélectionner")
        self.deselect_button = QPushButton("Désélectionner")
        self.remove_selected_button = QPushButton("Supprimer sélection")
        self.start_button = QPushButton("Démarrer capture")
        self.export_button = QPushButton("Exporter résultat")

        # ADD DARK MODE BUTTON
        self.dark_mode_button = QPushButton("🌙 Mode Sombre")

        button_layout.addWidget(self.select_all_button)
        button_layout.addWidget(self.deselect_button)
        button_layout.addWidget(self.remove_selected_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.dark_mode_button)  # ADD THIS LINE

        layout.addLayout(button_layout)

        # --- Filter box ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filtre:"))
        self.filter_input = QLineEdit()
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)

        # --- Table view ---
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table.clicked.connect(self.on_table_click)
        layout.addWidget(self.table)

        # --- Progress bar ---
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt")
        
        # Initialize dark mode state
        self.dark_mode_enabled = False

        # Setup menu bar
        self.setup_menus()

        # Connect signals
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_button.clicked.connect(self.deselect_all)
        self.remove_selected_button.clicked.connect(self.remove_selected)
        self.start_button.clicked.connect(self.run_capture)
        self.export_button.clicked.connect(self.export_results)
        self.filter_input.textChanged.connect(self.apply_filter)
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)

        # Placeholder model
        self.model = None

    def setup_menus(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # Fichier menu
        file_menu = menubar.addMenu("Configuration")
        
        # Import CSV action
        import_csv_action = file_menu.addAction("Importer CSV")
        import_csv_action.triggered.connect(self.import_csv)
        
        # Import API action
        import_api_action = file_menu.addAction("Importer depuis API")
        import_api_action.triggered.connect(self.import_from_api)
        
        # Export ORIGINAL data action
        export_original_action = file_menu.addAction("Exporter données originales")
        export_original_action.triggered.connect(self.export_original_data)
        
        # Separator
        file_menu.addSeparator()
        
        # Export RESULTS action
        export_results_action = file_menu.addAction("Exporter résultats traités")
        export_results_action.triggered.connect(self.export_results)
        
        # Separator
        file_menu.addSeparator()
        
        # Quit action
        quit_action = file_menu.addAction("Quitter")
        quit_action.triggered.connect(self.close)

    def on_table_click(self, index):
        """Handle table click to toggle row selection"""
        if self.model:
            self.model.toggle_row_selection(index.row())

    def transform_api_data(self, df):
        """Transform API data to match our required column structure"""
        transformed_df = df.copy()
        
        # Map common API column names to our required columns
        column_mappings = {
            'lien_web': ['url', 'link', 'web_url', 'article_url', 'source_url'],
            'id': ['id', '_id', 'identifier', 'post_id', 'article_id'],
            'support_titre': ['category', 'source', 'type', 'site', 'domain']
        }
        
        # Try to map existing columns
        for target_col, possible_source_cols in column_mappings.items():
            if target_col not in transformed_df.columns:
                for source_col in possible_source_cols:
                    if source_col in transformed_df.columns:
                        transformed_df[target_col] = transformed_df[source_col]
                        break
        
        # Create missing required columns with default values
        if 'lien_web' not in transformed_df.columns:
            if 'id' in transformed_df.columns:
                transformed_df['lien_web'] = transformed_df['id'].apply(
                    lambda x: f'https://example.com/item/{x}' if pd.notna(x) else 'https://example.com'
                )
            elif 'title' in transformed_df.columns:
                transformed_df['lien_web'] = transformed_df['title'].apply(
                    lambda x: f'https://example.com/{str(x).lower().replace(" ", "-")[:20]}' if pd.notna(x) else 'https://example.com'
                )
            else:
                transformed_df['lien_web'] = [f'https://example.com/item/{i}' for i in range(len(transformed_df))]
        
        if 'id' not in transformed_df.columns:
            transformed_df['id'] = [f'item_{i}' for i in range(len(transformed_df))]
        
        if 'support_titre' not in transformed_df.columns:
            transformed_df['support_titre'] = 'api_import'
        
        # Select only the columns we need for screenshot processing
        required_columns = ['lien_web', 'id', 'support_titre']
        return transformed_df[required_columns]

    def import_csv(self):
        """Open file dialog and load CSV into table"""
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                self.csv_path = path
                df = pd.read_csv(path)
                
                # Validate required columns
                required_columns = ['lien_web', 'id', 'support_titre']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    QMessageBox.warning(self, "Colonnes manquantes", 
                                      f"Le CSV doit contenir les colonnes: {', '.join(required_columns)}\n"
                                      f"Colonnes manquantes: {', '.join(missing_columns)}")
                    return
                
                # Create mapping from URLs to row indices for color coding
                self.row_mapping = {}
                for idx, url in enumerate(df['lien_web']):
                    if pd.notna(url):
                        self.row_mapping[str(url)] = idx
                
                self.model = ColorizedPandasModel(df)
                self.table.setModel(self.model)
                
                # Clear API data and set data source
                self.api_data = None
                self.data_source = 'csv'
                
                self.status_bar.showMessage(f"CSV chargé: {len(df)} lignes")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors du chargement du CSV: {str(e)}")

    def import_from_api(self):
        """Open API connection dialog and fetch data"""
        dialog = APIConnectionDialog(self)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            connection_data = dialog.get_connection_data()
            
            # Show progress
            self.status_bar.showMessage("Connexion à l'API en cours...")
            
            # Create and start API worker
            self.api_worker = APIWorker(
                connection_data['url'],
                connection_data['api_key'],
                connection_data['params'],
                is_demo=(connection_data['url'] == 'demo')
            )
            self.api_worker.finished.connect(self.on_api_data_received)
            self.api_worker.error.connect(self.on_api_error)
            self.api_worker.start()

    def on_api_data_received(self, df):
        """Handle API data received successfully"""
        if df.empty:
            QMessageBox.warning(self, "Avertissement", "Aucune donnée reçue de l'API")
            self.status_bar.showMessage("Aucune donnée API")
            return
        
        # Transform API data to match our required structure
        transformed_df = self.transform_api_data(df)
        
        # Create mapping from URLs to row indices for color coding
        self.row_mapping = {}
        for idx, url in enumerate(transformed_df['lien_web']):
            if pd.notna(url):
                self.row_mapping[str(url)] = idx
        
        self.model = ColorizedPandasModel(transformed_df)
        self.table.setModel(self.model)
        
        # Store API data and set data source
        self.api_data = transformed_df
        self.csv_path = None
        self.data_source = 'api'
        
        self.status_bar.showMessage(f"Données API chargées: {len(transformed_df)} lignes")
        QMessageBox.information(self, "Succès", f"Données importées depuis l'API avec succès! ({len(transformed_df)} lignes)")

    def on_api_error(self, error_message):
        """Handle API error"""
        QMessageBox.critical(self, "Erreur API", error_message)
        self.status_bar.showMessage("Erreur de connexion API")

    def apply_filter(self, text):
        if self.model:
            self.model.filter(text)

    def select_all(self):
        """Tout sélectionner - Select all rows for processing"""
        if self.model:
            self.model.select_all_rows()
            selected_count = len(self.model.get_selected_rows())
            self.status_bar.showMessage(f"{selected_count} éléments sélectionnés")
        else:
            QMessageBox.warning(self, "Erreur", "Aucune donnée à sélectionner")

    def deselect_all(self):
        """Désélectionner tout - Deselect all rows"""
        if self.model:
            self.model.deselect_all_rows()
            self.status_bar.showMessage("Tous les éléments désélectionnés")
        else:
            QMessageBox.warning(self, "Erreur", "Aucune donnée à désélectionner")

    def remove_selected(self):
        """Supprimer les éléments sélectionnés"""
        if self.model:
            if self.model.remove_selected_rows():
                self.status_bar.showMessage("Éléments sélectionnés supprimés")
            else:
                self.status_bar.showMessage("Aucun élément sélectionné à supprimer")
        else:
            QMessageBox.warning(self, "Erreur", "Aucune donnée à modifier")

    def set_ui_enabled(self, enabled):
        """Enable/disable UI controls during processing"""
        self.select_all_button.setEnabled(enabled)
        self.deselect_button.setEnabled(enabled)
        self.remove_selected_button.setEnabled(enabled)
        self.start_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def update_progress(self, processed, total, success, row_status):
        """Update progress bar based on worker thread feedback"""
        if total > 0:
            progress_percent = int((processed / total) * 100)
            self.progress.setValue(progress_percent)
            
            # Update row colors based on processing status
            if self.model and row_status:
                self.model.update_processing_status(row_status)
            
            # Update status text
            failed = processed - success
            status_text = f"Traité: {processed}/{total} | Réussis: {success} | Échoués: {failed}"
            self.status_bar.showMessage(status_text)

    def process_finished(self, results_path):
        """Handle completion of screenshot process"""
        self.set_ui_enabled(True)
        self.progress.setValue(100)
        
        # Clean up temporary API CSV file if it exists
        if hasattr(self, 'api_data') and self.api_data is not None and hasattr(self, 'output_dir'):
            temp_csv_path = os.path.join(self.output_dir, "temp_api_data.csv")
            if os.path.exists(temp_csv_path):
                try:
                    os.remove(temp_csv_path)
                except:
                    pass
        
        if results_path:
            QMessageBox.information(self, "Terminé", 
                                  f"Capture terminée avec succès!\nRésultats sauvegardés dans: {results_path}")
            self.status_bar.showMessage("Capture terminée avec succès")
        else:
            QMessageBox.warning(self, "Erreur", "La capture a échoué ou a été annulée.")
            self.status_bar.showMessage("Capture échouée")

    def process_error(self, error_message):
        """Handle errors from worker thread"""
        self.set_ui_enabled(True)
        QMessageBox.critical(self, "Erreur", f"Erreur lors de la capture: {error_message}")
        self.status_bar.showMessage(f"Erreur: {error_message}")

    def run_capture(self):
        """Launch the screenshot process with selected options"""
        # Check if we have data to process (either CSV or API)
        if not self.csv_path and not hasattr(self, 'api_data'):
            QMessageBox.warning(self, "Erreur", "Veuillez importer des données d'abord (CSV ou API).")
            return

        # Show parameter dialog
        param_dialog = ParameterDialog(self)
        result = param_dialog.exec_()
        
        if result != QDialog.Accepted:
            return  # User cancelled
        
        parameters = param_dialog.get_parameters()
        
        # Standard column names (no longer user-selectable)
        url_col = 'lien_web'
        filename_col = 'id'
        support_col = 'support_titre'

        # Dynamic output directory based on type
        self.output_dir = f"data/csv_screenshots_{parameters['screenshot_type']}"

        # Get selected rows if any
        selected_rows = []
        if self.model:
            selected_rows = self.model.get_selected_rows()
        
        # If no rows are selected, process all rows
        process_all = len(selected_rows) == 0

        # Show confirmation message
        if process_all:
            confirm_msg = f"Traiter toutes les lignes ({self.model.rowCount()} éléments) avec batch size {parameters['batch_size']} ?"
        else:
            confirm_msg = f"Traiter {len(selected_rows)} éléments sélectionnés avec batch size {parameters['batch_size']} ?"
            
        reply = QMessageBox.question(self, "Confirmation", confirm_msg, 
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return

        # Show success message BEFORE starting the process
        QMessageBox.information(self, "Lancement", "Capture démarrée avec succès 🚀")

        # Disable UI during processing
        self.set_ui_enabled(False)
        self.progress.setValue(0)
        self.status_bar.showMessage("Démarrage de la capture...")

        # For API data, we need to save it to a temporary CSV first
        if hasattr(self, 'api_data') and self.api_data is not None:
            # Create a temporary CSV file for API data
            os.makedirs(self.output_dir, exist_ok=True)
            temp_csv_path = os.path.join(self.output_dir, "temp_api_data.csv")
            self.api_data.to_csv(temp_csv_path, index=False)
            data_source_path = temp_csv_path
        else:
            # Use the existing CSV path
            data_source_path = self.csv_path

        # Create and start CSV processor worker
        self.worker = CSVProcessorWorker(
            csv_path=data_source_path,
            url_column=url_col,
            output_dir=self.output_dir,
            filename_column=filename_col,
            support_column=support_col,
            batch_size=parameters['batch_size'],
            delay=parameters['delay'],
            max_workers=parameters['max_workers'],
            screenshot_type=parameters['screenshot_type'],
            start_row=parameters['start_row'],
            selected_rows=selected_rows if not process_all else [],
            row_mapping=self.row_mapping,
            image_format=parameters['image_format']
        )
        
        # Connect worker signals
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.finished.connect(self.process_finished)
        self.worker.error_occurred.connect(self.process_error)
        
        # Start the worker
        self.worker.start()

    def get_latest_results_file(self):
        """Find the most recent results CSV file"""
        if not hasattr(self, 'output_dir') or not self.output_dir or not os.path.exists(self.output_dir):
            return None
        
        try:
            results_files = []
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    if file.startswith('screenshot_results_') and file.endswith('.csv'):
                        results_files.append(os.path.join(root, file))
            
            if not results_files:
                return None
            
            # Get the most recent file
            latest_file = max(results_files, key=os.path.getmtime)
            return latest_file
            
        except Exception:
            return None

    def export_results(self):
        """Exporter résultats - Export only processed results"""
        # Check if we have results from screenshot processing
        results_path = self.get_latest_results_file()
        
        if not results_path or not os.path.exists(results_path):
            QMessageBox.warning(self, "Erreur", "Aucun résultat de traitement à exporter. Veuillez d'abord démarrer une capture.")
            return
        
        try:
            # Load the results CSV
            results_df = pd.read_csv(results_path)
            
            # Filter only rows that were actually processed (have screenshot data)
            processed_df = results_df[
                (results_df['screenshot_success'] == True) | 
                (results_df['content_screenshot_success'] == True) |
                (results_df['screenshot_path'].notna()) |
                (results_df['content_screenshot_path'].notna())
            ]
            
            if processed_df.empty:
                QMessageBox.warning(self, "Aucun résultat", "Aucune capture n'a été effectuée avec succès.")
                return
            
            # Get export file path
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Exporter les résultats traités", 
                f"resultats_traites_{datetime.now().strftime('%Y%m%d_%H%M%S')}", 
                "CSV Files (*.csv);;Excel Files (*.xlsx);;JSON Files (*.json)"
            )
            
            if file_path:
                if file_path.endswith('.csv'):
                    processed_df.to_csv(file_path, index=False)
                elif file_path.endswith('.xlsx'):
                    processed_df.to_excel(file_path, index=False)
                elif file_path.endswith('.json'):
                    processed_df.to_json(file_path, orient='records', indent=2)
                
                QMessageBox.information(self, "Succès", 
                                      f"{len(processed_df)} résultats traités exportés vers: {file_path}")
                self.status_bar.showMessage(f"Exporté: {len(processed_df)} résultats traités")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'export des résultats: {str(e)}")

    def export_original_data(self):
        """Exporter - Export original loaded data (menu option)"""
        if hasattr(self, 'api_data') and self.api_data is not None:
            # Export API data
            df_to_export = self.api_data
            source_type = "API"
        elif hasattr(self, 'model') and self.model and not self.model._df.empty:
            # Export CSV data
            df_to_export = self.model._df
            source_type = "CSV"
        else:
            QMessageBox.warning(self, "Erreur", "Aucune donnée originale à exporter")
            return
        
        # Get export file path
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            f"Exporter les données originales ({source_type})", 
            f"donnees_originales_{datetime.now().strftime('%Y%m%d_%H%M%S')}", 
            "CSV Files (*.csv);;Excel Files (*.xlsx);;JSON Files (*.json)"
        )
        
        if file_path:
            try:
                if file_path.endswith('.csv'):
                    df_to_export.to_csv(file_path, index=False)
                elif file_path.endswith('.xlsx'):
                    df_to_export.to_excel(file_path, index=False)
                elif file_path.endswith('.json'):
                    df_to_export.to_json(file_path, orient='records', indent=2)
                
                total_rows = len(df_to_export)
                QMessageBox.information(self, "Succès", 
                                      f"{total_rows} données originales ({source_type}) exportées vers: {file_path}")
                self.status_bar.showMessage(f"Exporté: {total_rows} données originales")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'export: {str(e)}")
                
    def get_dark_mode_stylesheet(self):
        """Return dark mode stylesheet"""
        return """
        QMainWindow, QDialog, QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            border: none;
        }
        
        QTableView {
            background-color: #3c3c3c;
            color: #ffffff;
            gridline-color: #555555;
            alternate-background-color: #353535;
        }
        
        QTableView::item:selected {
            background-color: #4a76b8;
            color: #ffffff;
        }
        
        QHeaderView::section {
            background-color: #353535;
            color: #ffffff;
            padding: 4px;
            border: 1px solid #555555;
        }
        
        QPushButton {
            background-color: #4a4a4a;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 5px;
            border-radius: 3px;
        }
        
        QPushButton:hover {
            background-color: #5a5a5a;
            border: 1px solid #666666;
        }
        
        QPushButton:pressed {
            background-color: #3a3a3a;
        }
        
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 3px;
            border-radius: 3px;
        }
        
        QComboBox QAbstractItemView {
            background-color: #3c3c3c;
            color: #ffffff;
            selection-background-color: #4a76b8;
        }
        
        QProgressBar {
            border: 1px solid #555555;
            border-radius: 3px;
            text-align: center;
            color: #ffffff;
        }
        
        QProgressBar::chunk {
            background-color: #4a76b8;
            width: 10px;
        }
        
        QGroupBox {
            font-weight: bold;
            border: 1px solid #555555;
            border-radius: 5px;
            margin-top: 1ex;
            padding-top: 10px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: #ffffff;
        }
        
        QStatusBar {
            background-color: #353535;
            color: #ffffff;
        }
        
        QMenuBar {
            background-color: #353535;
            color: #ffffff;
        }
        
        QMenuBar::item:selected {
            background-color: #4a76b8;
        }
        
        QMenu {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
        }
        
        QMenu::item:selected {
            background-color: #4a76b8;
        }
        """
    
    def toggle_dark_mode(self):
        """Toggle between light and dark mode"""
        self.dark_mode_enabled = not self.dark_mode_enabled
        
        if self.dark_mode_enabled:
            self.setStyleSheet(self.get_dark_mode_stylesheet())
            self.dark_mode_button.setText("☀️ Mode Clair")
            self.status_bar.showMessage("Mode sombre activé")
        else:
            self.setStyleSheet("")  # Reset to default light theme
            self.dark_mode_button.setText("🌙 Mode Sombre")
            self.status_bar.showMessage("Mode clair activé")

    def closeEvent(self, event):
        """Handle window close event - stop worker if running"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        if self.api_worker and self.api_worker.isRunning():
            self.api_worker.terminate()
            self.api_worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScreenshotUI()
    window.show()
    sys.exit(app.exec_())