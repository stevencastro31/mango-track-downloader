import pathlib
import acoustid
import requests
import os
from enum import Enum
from mutagen.mp4 import MP4, MP4Cover
from dataclasses import dataclass

class Tag(Enum):
    Name = '\xa9nam'
    Artist = '\xa9ART'
    Album = '\xa9alb'
    AlbumArtist = 'aART'
    Genre = '\xa9gen'
    Year = '\xa9day'
    TrackNumber = 'trkn'
    Cover = 'covr'
    Disk = 'disk'

    def get(self, file):
        return file.get(self.value)

    def set(self, file, value):
        try:
            # print(f'[mango td] Setting {self.value} tag...')
            file[self.value] = value
        except Exception as ex:
            print(f'[mango td] Tag Error: {self.value} {value} {ex}')

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

    def apply_tags(self, tags: dict):
        print('[mango td] Applying new metadata/tags...')

        mp4 = MP4(self.Path)

        # Set Tags
        Tag.Name.set(mp4, tags.get('title', ''))
        Tag.Artist.set(mp4, tags.get('artist', ''))
        Tag.Album.set(mp4, tags.get('album', ''))
        Tag.AlbumArtist.set(mp4, [tags.get('albumartist', '')])
        genre = tags.get('genre', '')
        Tag.Genre.set(mp4, genre[0] if genre else '')
        Tag.TrackNumber.set(mp4, [(tags.get('tracknumber'), tags.get('totaltracks'))])
        Tag.Disk.set(mp4, [(tags.get('discnumber'), tags.get('discnumber'))])

        date = tags.get('date')
        if date:
            Tag.Year.set(mp4, date[:4])

        # Get & Set Cover Art from CoverArtArchive
        if tags['musicbrainz_albumid']:
            url = f"https://coverartarchive.org/release/{tags['musicbrainz_albumid']}/front-500"
            # print(url)
            # print(tags['musicbrainz_albumid'])
            res = requests.get(url, headers={"User-Agent": os.getenv('USER_AGENT')}, timeout=30) 
            if res.ok:
                Tag.Cover.set(mp4, [MP4Cover(res.content, imageformat=MP4Cover.FORMAT_JPEG)])
            else:
                print('[mango td] Tag Error: No Cover Art')
        mp4.save()
        print('[mango td] Metadata/Tags Saved...')

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
    score: float = 0.0                  # filled in later by scoring