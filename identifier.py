import os
import re
import json
import requests
import acoustid
from dotenv import load_dotenv
from classes import TrackCandidate, TrackProfile

# 0. settings
load_dotenv()
ACOUSTID_API_KEY = os.getenv('ACOUSTID_API')
USER_AGENT = os.getenv('USER_AGENT')

# 1. constants
MB = "https://musicbrainz.org/ws/2"
WEIGHTS = {
    "title": 13,
    "length": 10,
    "album": 5,
    "artist": 4,
    "date": 4,
    "tracknumber": 4,
    "releasetype": 14,
}
TYPE_PREF = {"Album": 1.0, "Single": 0.7, "EP": 0.7, "Compilation": 0.2}
MIN_SIMILARITY = 0.25
MIN_MARGIN = 0.02
LENGTH_WINDOW_S = 30

# 2. search

# 2.1 use pyacoustid to fetch metadata using audio fingerprint 
def lookup_acoustid(duration: float, fingerprint: str) -> list[TrackCandidate]:
    document = acoustid.lookup(ACOUSTID_API_KEY, fingerprint, duration, meta=["recordings", "releasegroups", "releases", "tracks", "sources"], timeout=30)
    if document.get('status') != 'ok':
        raise acoustid.WebServiceError(str(document.get('error')))
    else:
        return list(parse_acoustid_to_candidate(document))   

# 2.2 use musicbrainz api to fetch meta data using existing track metadata
def lookup_musicbrainz(profile: TrackProfile) -> list[TrackCandidate]:
    # build query
    fields = {
        "track": profile.Name,
        "artist": profile.Artist,
        "release": profile.Album,
        "qdur": str(int(profile.Duration * 1000) // 2000) if profile.Duration else "",
    }
    query = " ".join(f"{k}:({_escape_lucene(str(v))})" for k, v in fields.items() if v)

    # request
    res = requests.get(
        f"{MB}/recording",
        params={"query": query, "limit": 25, "fmt": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    res.raise_for_status()

    output = []

    for rec in res.json().get('recordings', []):
        base = dict(
            recording_id=rec["id"],
            title=rec.get("title", ""),
            artist=_build_credit([{"name": c["name"], "joinphrase": c.get("joinphrase", "")} for c in rec.get("artist-credit", [])]),
            length=(rec["length"] / 1000) if rec.get("length") else None,
            confidence=rec.get("score", 100) / 100,
        )
        for rel in rec.get("releases", []):
            output.append(TrackCandidate(
                **base,
                release_id=rel["id"],
                album=rel.get("title", ""),
                year=_build_year(rel.get("date")),
                release_type=(rel.get("release-group") or {}).get("primary-type"),
            ))
    return output

# 3. process

# 3.1 parse acoustid results into TrackCandidate objects
def parse_acoustid_to_candidate(document: dict):
    for result in document.get('results', []):                              # each result has an list of recordings
        recs = result.get('recordings', [])
        max_sources = max([rec.get("sources", 1) for rec in recs] + [1])    # each recording has a field 'source' that denotes how many submissions this particular recording has (a good indicator for what metadata is likely a match)

        for rec in recs:
            conf = min(rec.get("sources", 1) / max_sources, 1.0) * result.get("score", 1.0)     # compute the score of the current record against the total sources, multiply it as well to the results' score
            print(conf, rec.get("sources", 1))

            base = dict(
                recording_id=rec["id"],
                title=rec.get("title", ""),
                artist=_build_credit(rec.get("artists", [])),
                length=rec.get("duration"),  # seconds (AcoustID reports seconds)
                confidence=conf,
            )

            emitted = False # did this recording produce any release-level TrackCandidate?
            for rg in rec.get('releasegroups', []):
                for rel in rg.get('releases', []):
                    emitted = True
                    pos = None

                    # locate track number
                    for medium in rel.get('mediums', []):
                        for tr in medium.get('tracks', []):
                            pos = tr.get('position')
                            break
                        if pos:
                            break

                    # create a candidate for the list
                    yield TrackCandidate(
                        **base,
                        release_id=rel["id"],
                        album=rel.get("title", rg.get("title", "")),
                        year=_build_year((rel.get("date") or {}).get("year")),
                        tracknumber=_build_tracknumber(pos),
                        release_type=rg.get("type"),  # "Album", "Single", ...
                    )
            if not emitted: # still offer track candidate w/ no release info (album) 
                yield TrackCandidate(**base)

def parse_musicbrainz_to_candidate():
    return


# 4. helpers
def _build_credit(artists: list[dict]) -> str:
    # join an artist-credit list into the string shown on MusicBrainz
    # MusicBrainz includes pieces of information like 'join phrases'
    return "".join(a.get("name", "") + a.get("joinphrase", "") for a in artists)

def _build_year(value) -> int | None:
    # extract 4 digit year
    if value is None:
        return None
    match = re.match(r"\s*(\d{4})", str(value))
    return int(match.group(1)) if match else None

def _build_tracknumber(value) -> int | None:
    # converst varying formats of track number to a single integer
    if isinstance(value, (tuple, list)):          # MP4 style: (11, 12)
        value = value[0] if value else None
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    match = re.match(r"\s*(\d+)", str(value))     # "11" or "11/12" -> 11
    return int(match.group(1)) if match else None

def _escape_lucene(text: str) -> str:
    # MusisBrainz uses lucene, add escape character for operators that exist in track data
    return re.sub(r'([+\-&|!(){}\[\]\^"~*?:\\/])', r"\\\1", text)

# 5. methods - function you are suppose to use
