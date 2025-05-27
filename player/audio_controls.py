from dataclasses import dataclass, field
from utils.file_manager import file_manager

@dataclass
class Audio_controls:
    file_manager_ = file_manager()
    queue: list = field(default_factory=lambda: file_manager().search())
    song_pointer: int = 0
    repeat: int = 1
    music_time: float = 0
    is_paused: bool = False
