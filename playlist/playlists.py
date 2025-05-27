import json


class Playlist:
    def __init__(self):
        self.playlists = {}
        self.load_playlist()
        
    def load_playlist(self):
        try:
            with open("playlists.json", "r") as playlist:
                self.playlists = json.load(playlist)
        except FileNotFoundError:
            self.playlists = {}

    def save_playlists(self):
        with open("playlists.json", "w") as playlist:
            json.dump(self.playlists, playlist, indent=4)

    def new_playlist(self, name: str, songs: list):
        self.playlists[name] = songs
        self.save_playlists()

    def delete_playlist(self, name: str):
        if name in self.playlists:
            del self.playlists[name]
            self.save_playlists()
        else:
            print(f"Playlist '{name}' not found.")

    def rename_playlist(self, old_name: str, new_name: str):
        if old_name not in self.playlists:
            print(f"Playlist '{old_name}' not found.")
            return
        if new_name in self.playlists:
            print(f"A playlist with the name '{new_name}' already exists.")
            return

        self.playlists[new_name] = self.playlists.pop(old_name)
        self.save_playlists()
