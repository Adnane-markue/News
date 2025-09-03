import os
import shutil

# Path to the main folder after extracting zip
base_folder = "data/csv_screenshots_content"

# Loop through subfolders
for folder in os.listdir(base_folder):
    folder_path = os.path.join(base_folder, folder)

    if os.path.isdir(folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith(".png"):
                src = os.path.join(folder_path, file)
                dst = os.path.join(base_folder, file)

                # If a file with the same name already exists, add a suffix
                if os.path.exists(dst):
                    name, ext = os.path.splitext(file)
                    i = 1
                    while os.path.exists(os.path.join(base_folder, f"{name}_{i}{ext}")):
                        i += 1
                    dst = os.path.join(base_folder, f"{name}_{i}{ext}")

                shutil.move(src, dst)

        # Optionally remove the empty subfolder
        os.rmdir(folder_path)
