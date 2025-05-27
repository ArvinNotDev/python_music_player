from os import path
import os


class file_manager:
    def search(self):
        music_folder = path.join(os.environ['USERPROFILE'], 'Music')
        
        music_files = []
        for root, dirs, files in os.walk(music_folder):
            for file in files:
                if file.lower().endswith(('.mp3', '.wav', '.flac', '.aac', '.ogg')):
                    full_path = path.join(root, file)
                    music_files.append(full_path)
        
        return music_files

    def delete(self):
        pass