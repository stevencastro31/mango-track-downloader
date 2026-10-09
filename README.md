# mango-track-downloader

A Python script that downloads audio using `yt-dlp` and automatically tags tracks with metadata from MusicBrainz, using AcoustID for audio identification.

## How to Run

### 1. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 2. Configure the Tracklist

Edit `tracklist.txt` and add the URLs of tracks you want to download.

```txt
https://music.youtube.com/watch?v=lYBUbBu4W08
https://music.youtube.com/watch?v=0FCvzsVlXpQ
...
```

### 3. Configure AcoustID

Obtain an AcoustID API key by registering a new application at [AcoustID](https://acoustid.org/new-application).

Create a local `.env` file to configure your AcoustID API key and any other required environment variables before running the script.

```txt
ACOUSTID_API={YOUR KEY}
USER_AGENT=mango-track-downloader
```

### 4. Run the Script

Execute the downloader:

```bash
python download.py
```

## Features

* Identifies tracks using AcoustID.
* Fetches track and release metadata from MusicBrainz.
* Applies metadata tags to downloaded audio files.
* Retrieves album artwork from Cover Art Archive.

## Attribution

This project uses the following services to identify tracks and retrieve metadata and album artwork:

* [AcoustID](https://acoustid.org/) - Audio fingerprinting and track identification.
* [MusicBrainz](https://musicbrainz.org/) - Music metadata and release information.
* [Cover Art Archive](https://coverartarchive.org/) - Album artwork.

An AcoustID API key is required to identify tracks. Registration is free.

## Disclaimer

Metadata tagging is not always accurate. The script selects the best available candidate based on similarity and applies its metadata when a suitable match is found. It is primarily intended for convenience in obvious cases, and manual review or correction may still be necessary.

