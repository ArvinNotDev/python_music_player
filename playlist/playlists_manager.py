from playlist.playlists import Playlist

class PlaylistManager:
    def __init__(self):
        self.playlist_obj = Playlist()
        # Ensure "Favorites" playlist exists
        if "Favorites" not in self.get_all_playlists():
            self.add_playlist("Favorites")

    def get_all_playlists(self):
        return self.playlist_obj.get_playlist_names()

    def get_songs(self, playlist_name):
        return self.playlist_obj.get_songs(playlist_name)

    def add_playlist(self, name, songs=None):
        if songs is None:
            songs = []
        self.playlist_obj.new_playlist(name, songs)

    def delete_playlist(self, name):
        self.playlist_obj.delete_playlist(name)

    def rename_playlist(self, old_name, new_name):
        self.playlist_obj.rename_playlist(old_name, new_name)

    def add_song_to_playlist(self, playlist_name, song):
        songs = self.get_songs(playlist_name)
        if songs is None:
            # If playlist doesn't exist, create it with the song
            self.add_playlist(playlist_name, [song])
        else:
            if song not in songs:
                songs.append(song)
                self.playlist_obj.new_playlist(playlist_name, songs)

    def remove_song_from_playlist(self, playlist_name, song):
        songs = self.get_songs(playlist_name)
        if songs is not None and song in songs:
            songs.remove(song)
            self.playlist_obj.new_playlist(playlist_name, songs)

    # Favorites-specific methods
    def get_favorites(self):
        favorites = self.get_songs("Favorites")
        return favorites if favorites is not None else []

    def add_to_favorites(self, song):
        self.add_song_to_playlist("Favorites", song)

    def remove_from_favorites(self, song):
        self.remove_song_from_playlist("Favorites", song)

    def is_favorite(self, song):
        return song in self.get_favorites()