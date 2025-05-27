from playlist.playlists import Playlist

class PlaylistManager:
    def __init__(self):
        self.playlist_obj = Playlist()

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
        if song not in songs:
            songs.append(song)
            self.playlist_obj.new_playlist(playlist_name, songs)

    def remove_song_from_playlist(self, playlist_name, song):
        songs = self.get_songs(playlist_name)
        if song in songs:
            songs.remove(song)
            self.playlist_obj.new_playlist(playlist_name, songs)
