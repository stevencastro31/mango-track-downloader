import os
import re
import json
import yt_dlp
import acoustid
import pathlib
from dotenv import load_dotenv
from classes import TrackProfile
from mutagen.mp4 import MP4

import test
import identifier


# 0. Settings
load_dotenv()
os.environ['FPCALC'] = './exec/fpcalc.exe'

os.getenv('')

skip_download = True
skip_sanitize = True

if not skip_download:
    # 1. read download track list links
    track_links = []
    with open('tracklist.txt', 'r') as tracklist_file:
        track_links = [line.strip() for line in tracklist_file.readlines()]

    # 2. download tracks w/ yt-dlp
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'outtmpl': './tracks/%(artist)s - %(title)s.%(ext)s',
        'postprocessors': [{
                'key': 'FFmpegMetadata',
            },
        ],
        'addmetadata': True,
        'ignoreerrors': 'only_downloads',
    }
    with yt_dlp.YoutubeDL(opts) as ytd:
        ytd.download(track_links)

if not skip_sanitize:
    # 3. sanitize track file names (sometimes yt-dlp sets duplicate names)
    downloaded_track_file_paths = [pathlib.Path(os.path.join('.\\tracks', file)) for file in os.listdir('./tracks')]

    for track_file_path in downloaded_track_file_paths:
        filename = track_file_path.stem
        filename_detail = filename.split('-')

        if len(filename_detail) > 2:
            continue

        artist_name = filename_detail[0].strip()
        title_name = filename_detail[1].strip()

        new_artist_name = ', '.join(dict.fromkeys(artist.strip() for artist in artist_name.split(','))) # remove duplicate names
        new_title_name = re.sub(r'\s*\((?:feat\.|ft\.)[^)]*\)', '', title_name, flags=re.IGNORECASE)    # remove feat. ft.

        os.rename(track_file_path, f"./tracks/{new_artist_name} - {new_title_name}.{track_file_path.suffix}")

# 4. determine track meta data
downloaded_track_file_paths = [pathlib.Path(os.path.join('.\\tracks', file)) for file in os.listdir('./tracks')]


# for track_file_path in downloaded_track_file_paths:
#     track_profile = TrackProfile(track_file_path)

#     res = acoustid.lookup(config.get('ACOUSTID_API'), track_profile.Fingerprint, track_profile.Duration, meta=["recordings", "releasegroups", "releases", "tracks", "sources"], timeout=30)

#     cands = _candidates_from_acoustid(res)


#     for x in cands:
#         print(x)

#     break


# with open("test.json", "r", encoding="utf-8") as f:
#     data = json.load(f)
#     candidates = identifier.parse_acoustid_to_candidate(data)
#     for cand in candidates:
#         print(cand.confidence, cand.artist, cand.title, cand.album)


profile = TrackProfile(downloaded_track_file_paths[0])
# identifier.lookup_acoustid(profile.Duration, profile.Fingerprint)

for x in identifier.lookup_musicbrainz(profile):
    print(x.artist, x.album, x.title, x.tracknumber, x.confidence)




# for path in downloaded_track_file_paths:
#     try:
#         profile = TrackProfile(path)
#     except acoustid.FingerprintGenerationError as exc:
#         # fpcalc missing (NoBackendError is a subclass) or the audio is corrupt
#         print(f"{path.name}: could not fingerprint ({exc})")
#         continue

#     tags, reason = test.identify(profile)

#     print(json.dumps(tags))

#     if tags is None:
#         print(f"{path.name}: no match ({reason})")
#     else:
#         if reason == "ambiguous":
#             print(f"{path.name}: best match is ambiguous, review it")
#         # write `tags` into the file here using your Tag.* classes / mutagen

#     break


# print(downloaded_track_file_paths)



