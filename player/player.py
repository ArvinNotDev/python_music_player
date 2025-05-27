import pygame
import random
import threading
import time
from player.audio_controls import Audio_controls

class Music_player:
    def __init__(self):
        pygame.mixer.init()
        pygame.init()
        self.audio_controls = Audio_controls()
        self.current_volume = 0.5
        self.is_next_or_prev = False
        self.SONG_END = pygame.USEREVENT + 1
        self.stop_event = threading.Event()
        self.thread = None
        pygame.mixer.music.set_volume(self.current_volume)

    def playnext(self, song, pointer):
        queue = self.audio_controls.queue
        if pointer < 0 or pointer >= len(queue):
            print("Pointer out of range.")
            return
        if song in queue:
            return
        before_p = queue[:pointer + 1]
        after_p = queue[pointer + 1:]
        queue = before_p + [song] + after_p
        self.audio_controls.queue = queue
        print("Queue after adding song:", self.audio_controls.queue)

    def remove_from_queue(self, song):
        queue = self.audio_controls.queue
        if song in queue:
            queue.remove(song)
            print(f"Removed '{song}' from queue.")
        else:
            print(f"'{song}' not found in queue.")

    def volume_up(self):
        self.current_volume = min(1.0, self.current_volume + 0.1)
        pygame.mixer.music.set_volume(self.current_volume)
        print(f"Volume increased to: {int(self.current_volume * 100)}%")

    def volume_down(self):
        self.current_volume = max(0.0, self.current_volume - 0.1)
        pygame.mixer.music.set_volume(self.current_volume)
        print(f"Volume decreased to: {int(self.current_volume * 100)}%")

    def pause(self):
        pygame.mixer.music.pause()
        self.audio_controls.is_paused = True
        print("Playback paused.")

    def start(self):
        queue = self.audio_controls.queue
        pointer = self.audio_controls.song_pointer
        if pointer < len(queue):
            song = queue[pointer]
            try:
                if self.audio_controls.is_paused:
                    pygame.mixer.music.unpause()
                    self.audio_controls.is_paused = False
                    print("Resumed")
                else:
                    pygame.mixer.music.load(song)
                    pygame.mixer.music.set_endevent(self.SONG_END)
                    pygame.mixer.music.play()
                    print(f"Now playing: {song}")

                if self.thread and self.thread.is_alive():
                    self.stop_event.set()
                    self.thread.join()

                self.stop_event.clear()
                self.thread = threading.Thread(target=self.listen_to_end, daemon=True)
                self.thread.start()

            except pygame.error as e:
                print(f"Error playing {song}: {e}")
        else:
            print("No song to play at current pointer.")

    def next_song(self):
        self.audio_controls.is_paused = False
        self.audio_controls.song_pointer += 1
        if self.audio_controls.song_pointer < len(self.audio_controls.queue):
            self.start()
        else:
            self.audio_controls.song_pointer -= 1
            print("End of queue.")

    def prev_song(self):
        self.audio_controls.is_paused = False
        if self.audio_controls.song_pointer > 0:
            self.audio_controls.song_pointer -= 1
            self.start()
        else:
            print("no previous song!")

    def toggle_repeat(self):
        self.audio_controls.repeat = (self.audio_controls.repeat % 3) + 1
        if self.audio_controls.repeat == 1: # repeat all
            self.audio_controls.queue = self.audio_controls.file_manager_.search()
            self.audio_controls.song_pointer = 0
        elif self.audio_controls.repeat == 2: # repeat one
            current_song = self.audio_controls.queue[self.audio_controls.song_pointer]
            self.audio_controls.queue = [current_song]
            self.audio_controls.song_pointer = 0
        elif self.audio_controls.repeat == 3: # shuffle
            self.audio_controls.queue = self.audio_controls.file_manager_.search()
            random.shuffle(self.audio_controls.queue)
            self.audio_controls.song_pointer = 0
            self.start()

            
    def listen_to_end(self):
        if self.is_next_or_prev:
            self.is_next_or_prev = False
            return
        while not self.stop_event.is_set():
            for event in pygame.event.get():
                if event.type == self.SONG_END:
                    print("Song finished!")
                    self.audio_controls.song_pointer += 1
                    self.start()
                    return
            time.sleep(0.1)
