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
