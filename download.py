import os
import re
import time
import yt_dlp
import pathlib
from dotenv import load_dotenv

import identifier
from classes import TrackProfile

# 0. Settings
load_dotenv()
os.environ['FPCALC'] = './exec/fpcalc.exe'

skip_download = True
skip_sanitize = True
directory = pathlib.Path("tracks")
if not any(directory.iterdir()):
    skip_download = False
    skip_sanitize = False

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

        os.rename(track_file_path, f"./tracks/{new_artist_name} - {new_title_name}{track_file_path.suffix}")

# 4. determine track meta data and apply tags
downloaded_track_file_paths = [pathlib.Path(os.path.join('.\\tracks', file)) for file in os.listdir('./tracks')]


for track_file_path in downloaded_track_file_paths:
    print('[mango td] Creating track profile...')
    profile = TrackProfile(track_file_path)

    print(f'[mango td] Identifying: {profile.Path}')
    try:
        tags, reason = identifier.identify(profile)
        profile.apply_tags(tags)
    except Exception as ex:
        print(f'[mango td] An error occured {ex}...')
        print(f'[mango td] Skipping track: {profile.Path}')

    time.sleep(1.0)

print('[mango td] SCRIPT COMPLETE!')

