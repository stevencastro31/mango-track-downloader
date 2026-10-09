import os
import re
import time
import requests
import acoustid
import difflib
from dotenv import load_dotenv
from classes import TrackCandidate, TrackProfile
from collections import Counter

# 0. env settings
load_dotenv()
ACOUSTID_API_KEY = os.getenv('ACOUSTID_API')
USER_AGENT = os.getenv('USER_AGENT')

# 1. constants
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2"
COVER_ART_ARCHIVE_URL = 'https://coverartarchive.org/release/'
WEIGHTS = {
    "title": 13,
    "length": 10,
    "album": 7,
    "artist": 4,
    "date": 4,
    "tracknumber": 4,
    "releasetype": 14,
}
TYPE_PREF = {"Album": 0.7, "Single": 1.0, "EP": 0.7, "Compilation": 0.2}
MIN_SIMILARITY = 0.25
MIN_ACOUSTID_CONFIDENCE = 0.25
MIN_MARGIN = 0.02
LENGTH_WINDOW_S = 30
MAX_GENRES = 5
MIN_GENRE_USAGE = 90 


# 2. search

# 2.1 use pyacoustid to fetch metadata using audio fingerprint 
def _lookup_acoustid(duration: float, fingerprint: str) -> list[TrackCandidate]:
    document = acoustid.lookup(ACOUSTID_API_KEY, fingerprint, duration, meta=["recordings", "releasegroups", "releases", "tracks", "sources"], timeout=30)
    if document.get('status') != 'ok':
        raise acoustid.WebServiceError(str(document.get('error')))
    else:
        return list(_parse_acoustid_to_candidate(document))   

# 2.2 use musicbrainz api to fetch meta data using existing track metadata
def _lookup_musicbrainz(profile: TrackProfile) -> list[TrackCandidate]:
    fields = {
        "track": profile.Name,
        "artist": profile.Artist,
        "release": profile.Album,
        "qdur": str(int(profile.Duration * 1000) // 2000) if profile.Duration else "",
    }
    query = " ".join(f"{k}:({_escape_lucene(str(v))})" for k, v in fields.items() if v)

    # request
    res = requests.get(
        f"{MUSICBRAINZ_URL}/recording",
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
def _parse_acoustid_to_candidate(document: dict):
    for result in document.get('results', []):                              # each result has an list of recordings
        recs = result.get('recordings', [])
        max_sources = max([rec.get("sources", 1) for rec in recs] + [1])    # each recording has a field 'source' that denotes how many submissions this particular recording has (a good indicator for what metadata is likely a match)

        for rec in recs:
            conf = min(rec.get("sources", 1) / max_sources, 1.0) * result.get("score", 1.0)     # compute the score of the current record against the total sources, multiply it as well to the results' score
            base = dict(
                recording_id=rec["id"],
                title=rec.get("title", ""),
                artist=_build_credit(rec.get("artists", [])),
                length=rec.get("duration"),  # seconds (AcoustID reports seconds)
                confidence=conf,
            )

            if base['confidence'] < MIN_ACOUSTID_CONFIDENCE:    # don't add candidate that are far off (confidence levels)
                continue

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

# 3.2 score a track candidate 
def _score_track_candidate(profile: TrackProfile, candidate: TrackCandidate) -> float:
    parts: list[tuple[float, int]] = []     # list of scores and their corresponding weights (similarity score, score weight)

    def add_score(score, key):
        if score is not None:
            parts.append((score, WEIGHTS[key]))

    # text
    add_score(_similarity(profile.Name, candidate.title), "title")
    add_score(_similarity(profile.Artist, candidate.artist), "artist")
    add_score(_similarity(profile.Album, candidate.album), "album")

    # duration
    if profile.Duration and candidate.length:
        diff = min(abs(profile.Duration - candidate.length), LENGTH_WINDOW_S)
        add_score(1.0 - diff / LENGTH_WINDOW_S, "length")

    # track number
    profile_tracknumber = _build_tracknumber(profile.TrackNumber)
    if profile_tracknumber and candidate.tracknumber:
        add_score(float(profile_tracknumber == candidate.tracknumber), "tracknumber")

    # year
    profile_year = _build_year(profile.Year)
    if profile_year and candidate.year:
        add_score(1.0 if profile_year == candidate.year else 0.0, "date")

    # release type
    if candidate.release_type:
        add_score(TYPE_PREF.get(candidate.release_type, 0.5), "releasetype")

    if not parts:
        return 0.0

    weighted_average = sum(score * weight for score, weight in parts) / sum(weight for _, weight in parts)
    return weighted_average * candidate.confidence

# 3.3 select the best track candidate
def _pick_top_candidate(profile: TrackProfile, candidates: list[TrackCandidate]) -> tuple[TrackCandidate, str]:
    # score track candidates based on the profile
    for c in candidates:
        c.score = _score_track_candidate(profile, c)

    # sort track candidate by score
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    
    #  return no track candidate if the similarity score does not reach the minimum threshold
    if not ranked or ranked[0].score < MIN_SIMILARITY:
        return None, "below_floor"

    # get top 10 candidates (select the first top most w/ album cover)
    for i in range(10):
        try:
            release_id = ranked[i].release_id
            print(f"[mango td] Checking Candidate #{i} for cover art: {COVER_ART_ARCHIVE_URL}/{release_id}/front")
            res = requests.get(f"{COVER_ART_ARCHIVE_URL}{release_id}/front", headers={"User-Agent": USER_AGENT}, timeout=15,allow_redirects=False) # check statust (if an album cover exists)
            if res.status_code == 404:
                continue
            if res.status_code in (301, 302, 303, 307, 308):
                return ranked[i], None
        except IndexError:
            print('[mang td] No more candidates...')
            
    return ranked[0], None

# 3.4 fetch release from MusicBrainz base on candidate release Id
def _fetch_release(release_id: str):
    inc = "+".join(sorted([
        'artist-credits', 'labels', 'media', 'recordings', 'release-groups', 'genres',
    ]))
    url = f"{MUSICBRAINZ_URL}/release/{release_id}?inc={inc}&fmt=json"

    res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    res.raise_for_status()

    return res.json()

# 3.5 parse release json
def _parse_release_to_dict(release: dict, recording_id: str):
    label_info = (release.get("label-info") or [{}])[0]
    label_name = (label_info.get("label") or {}).get("name")

    tags = {
        "album": release.get("title"),
        "albumartist": _build_credit([
            {"name": c["name"], "joinphrase": c.get("joinphrase", "")}
            for c in release.get("artist-credit", [])
        ]),
        "date": release.get("date"),             
        "releasecountry": release.get("country"),  
        "barcode": release.get("barcode"),
        "musicbrainz_albumid": release["id"],
        "label": label_name,
    }

    for medium in release.get("media", []):
        for t in medium.get("tracks", []):
            if t["recording"]["id"] == recording_id:
                tags.update({
                    "title": t["recording"]["title"],   # prefer the recording's own title (the canonical one),
                    "artist": _build_credit([{"name": c["name"], "joinphrase": c.get("joinphrase", "")} for c in t.get("artist-credit", [])]),
                    "tracknumber": t["position"],          # position on this disc
                    "totaltracks": medium["track-count"],  # tracks on this disc
                    "discnumber": medium["position"],      # which disc
                    "musicbrainz_recordingid": recording_id,
                    "musicbrainz_trackid": t["id"],        # this track entry's MBID
                    "genre": _determine_genre(release, t["recording"]),
                })
                return tags  # recording found, stop search
            
    tags["genre"] = _determine_genre(release, None)
    return tags

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

def _normalize(s) -> str:
    # normalize text for fuzzy matching
    return re.sub(r"[^\w]+", " ", str(s).lower()).strip()

def _similarity(a, b) -> float | None:
    # fuzzy text matching
    if not a or not b:
        return None
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()

def _count_genres(counts: Counter, node: dict | None):
    for g in (node or {}).get("genres") or []:
        counts[g["name"]] += g.get("count", 1)
 
def _select_top_genre(counts: Counter, limit=MAX_GENRES, min_usage=MIN_GENRE_USAGE) -> list[str]:
    counts = +counts  # unary plus drops zero/negative counts
    if not counts:
        return []
    top = max(counts.values())
    # keep only genres with >= min_usage % of the top vote count
    kept = {n: item for n, item in counts.items() if 100 * item // top >= min_usage}
    # most votes first (ties alphabetical)
    best = sorted(kept.items(), key=lambda x: (-x[1], x[0]))[:limit]
    # ...then title-case and sort alphabetically for the final tag value
    return sorted(name.title() for name, _ in best)
 
def _determine_genre(release: dict, recording_node: dict | None) -> list[str]:
    counts: Counter = Counter()
    _count_genres(counts, recording_node)
    _count_genres(counts, release)
    _count_genres(counts, release.get("release-group"))
    return _select_top_genre(counts)


# 5. methods - function you are suppose to use
def identify(profile: TrackProfile) -> tuple[dict, str]:
    candidates: list[TrackCandidate] = []

    # get from acoustid (preffered method)
    if profile.Fingerprint:
        try:
            print('[mango td] Looking up metadata from AcoustID...')
            candidates = _lookup_acoustid(profile.Duration, profile.Fingerprint)
        except acoustid.WebServiceError as exc:
            print('[mango td] Web Error: Not found in AcoustID...')

    # if not result from acoustid, search MusicBrainz
    if not candidates:
        print('[mango td] Looking up metadata from MusicBrainz...')
        candidates = _lookup_musicbrainz(profile)
        time.sleep(1.0)  # add delays

    print('[mango td] Scoring track candidates...')
    best, reason = _pick_top_candidate(profile, candidates)
    if best is None:
        return None, reason

    if best.release_id is None:
        return {
            "title": best.title,
            "artist": best.artist,
            "musicbrainz_recordingid": best.recording_id,
        }, reason    

    # fetch official MusicBrainz release data
    print('[mango td] Fetching best track candidates\' metadata...')
    release = _fetch_release(best.release_id)
    print('[mango td] Track metadata acquired...')
    time.sleep(0)

    return _parse_release_to_dict(release, best.recording_id), reason