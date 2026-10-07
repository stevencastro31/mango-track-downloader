import pathlib
import acoustid
from enum import Enum
from mutagen.mp4 import MP4
from dataclasses import dataclass

class Tag(Enum):
    Name = '\xa9nam'
    Artist = '\xa9ART'
    Album = '\xa9alb'
    AlbumArtist = 'aART'
    Genre = '\xa9gen'
    Year = '\xa9day'
    TrackNumber = 'trkn'

    def get(self, file):
        return file.get(self.value)

class TrackProfile:
    def __init__(self, file_path: pathlib.Path):
        self._Path = file_path

        mp4 = MP4(file_path)
        self._Name = Tag.Name.get(mp4)
        self._Artist = Tag.Artist.get(mp4)
        self._Album = Tag.Album.get(mp4)
        self._AlbumArtist = Tag.AlbumArtist.get(mp4)
        self._Genre = Tag.Genre.get(mp4)
        self._Year = Tag.Year.get(mp4)
        self._TrackNumber = Tag.TrackNumber.get(mp4)

        duration, fingerprint = acoustid.fingerprint_file(str(file_path))
        self._Duration = duration
        self._Fingerprint = fingerprint

    @property
    def Path(self):
        return self._Path

    @property
    def Name(self):
        return self._Name

    @property
    def Artist(self):
        return self._Artist

    @property
    def Album(self):
        return self._Album

    @property
    def AlbumArtist(self):
        return self._AlbumArtist

    @property
    def Genre(self):
        return self._Genre

    @property
    def Year(self):
        return self._Year

    @property
    def TrackNumber(self):
        return self._TrackNumber

    @property
    def Duration(self):
        return self._Duration

    @property
    def Fingerprint(self):
        return self._Fingerprint


@dataclass
class TrackCandidate:
    recording_id: str                   # MusicBrainz recording MBID (the song itself)
    title: str                          # recording title
    artist: str                         # artist credit as one string, e.g. "A feat. B"
    length: float | None                # recording length in SECONDS, if known
    confidence: float = 1.0             
    release_id: str | None = None       # release MBID; None = recording-only candidate
    album: str = ""                     # release title
    year: int | None = None             # release year
    tracknumber: int | None = None      # position on that release
    release_type: str | None = None     # "Album", "Single", "Compilation", ...
    score: float = 0.0                  # filled in later by pick_best()