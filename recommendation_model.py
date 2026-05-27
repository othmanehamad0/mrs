"""
recommendation_model.py
------------------------
Content-based music recommendation engine.

Strategy:
  1. Extract text metadata (artist, album, genre, title) from local audio files
     via mutagen and build a TF-IDF matrix.
  2. Optionally blend numeric Spotify audio features (energy, danceability, …)
     from the bundled CSV datasets using cosine similarity on a normalised
     feature vector.
  3. Combine both similarity scores and return the top-N recommendations.
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SongFeatures:
    """Holds extracted features for a single local audio file."""
    path: str
    title: str = "Unknown Title"
    artist: str = "Unknown Artist"
    album: str = "Unknown Album"
    genre: str = "Unknown"
    year: int = field(default_factory=lambda: datetime.now().year)
    duration: float = 0.0

    def to_text(self) -> str:
        """Return a single string representation for TF-IDF vectorisation."""
        return " ".join([
            self.artist.lower(),
            self.album.lower(),
            self.genre.lower(),
            self.title.lower(),
        ])


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

def _extract_tag(audio, *keys: str, default: str = "") -> str:
    """Try multiple mutagen tag keys and return the first non-empty value."""
    for key in keys:
        try:
            value = audio.get(key)
            if value:
                return str(value[0]) if isinstance(value, list) else str(value)
        except Exception:
            continue
    return default


def extract_song_features(song_path: str) -> Optional[SongFeatures]:
    """
    Extract metadata from an audio file using mutagen.

    Returns a SongFeatures instance, or None if the file cannot be read.
    """
    try:
        import mutagen
        audio = mutagen.File(song_path)
    except Exception as exc:
        logger.warning("Could not open %s: %s", song_path, exc)
        return None

    features = SongFeatures(path=song_path)

    # Populate filename as fallback title (strip extension)
    features.title = os.path.splitext(os.path.basename(song_path))[0]

    if audio is None:
        return features

    # Title — Vorbis / MP3 ID3 / MP4
    features.title  = _extract_tag(audio, "title",  "TIT2", "\xa9nam") or features.title
    features.artist = _extract_tag(audio, "artist", "TPE1", "\xa9ART") or features.artist
    features.album  = _extract_tag(audio, "album",  "TALB", "\xa9alb") or features.album
    features.genre  = _extract_tag(audio, "genre",  "TCON")            or features.genre

    if hasattr(audio, "info"):
        features.duration = getattr(audio.info, "length", 0.0)

    # Year — try multiple date fields
    for date_key in ("date", "TDRC", "year"):
        raw = _extract_tag(audio, date_key)
        if raw and len(raw) >= 4:
            try:
                features.year = int(raw[:4])
                break
            except ValueError:
                continue

    return features


# ---------------------------------------------------------------------------
# Recommendation model
# ---------------------------------------------------------------------------

class RecommendationModel:
    """
    Content-based music recommendation model.

    Uses TF-IDF on text metadata for similarity scoring.
    If a genres CSV is available, numeric audio features are blended in.
    """

    # Numeric columns in data_w_genres.csv used for blending
    AUDIO_FEATURE_COLS = [
        "acousticness", "danceability", "energy",
        "instrumentalness", "liveness", "loudness",
        "speechiness", "tempo", "valence", "popularity",
    ]
    TEXT_WEIGHT  = 0.7
    AUDIO_WEIGHT = 0.3

    def __init__(self, csv_path: Optional[str] = None) -> None:
        self._song_features: dict[str, SongFeatures] = {}
        self._song_ids: list[str] = []          # basename of each file
        self._tfidf_matrix = None
        self._audio_sim_matrix: Optional[np.ndarray] = None
        self._vectorizer = TfidfVectorizer(min_df=1, analyzer="word")
        self._is_trained = False
        self._csv_path = csv_path

        self._load_audio_features_from_csv()

    # ------------------------------------------------------------------
    # CSV-based audio features (optional enhancement)
    # ------------------------------------------------------------------

    def _load_audio_features_from_csv(self) -> None:
        """Pre-compute a genre-level audio feature lookup from the CSV."""
        self._genre_audio_features: dict[str, np.ndarray] = {}
        # BUG FIX: track counts per genre so the running average is correct
        self._genre_audio_counts: dict[str, int] = {}

        if not self._csv_path or not os.path.exists(self._csv_path):
            return
        try:
            df = pd.read_csv(self._csv_path, usecols=["genres"] + self.AUDIO_FEATURE_COLS)
            df.dropna(subset=self.AUDIO_FEATURE_COLS, inplace=True)
            scaler = MinMaxScaler()
            df[self.AUDIO_FEATURE_COLS] = scaler.fit_transform(df[self.AUDIO_FEATURE_COLS])

            for _, row in df.iterrows():
                genre_str = str(row.get("genres", "")).strip("[]'\" ")
                if not genre_str:
                    continue
                vec = row[self.AUDIO_FEATURE_COLS].values.astype(float)
                if genre_str in self._genre_audio_features:
                    # BUG FIX: proper incremental mean (was: (existing + vec) / 2
                    # which converges toward the last value instead of the true mean)
                    n = self._genre_audio_counts[genre_str]
                    self._genre_audio_features[genre_str] = (
                        (self._genre_audio_features[genre_str] * n + vec) / (n + 1)
                    )
                    self._genre_audio_counts[genre_str] = n + 1
                else:
                    self._genre_audio_features[genre_str] = vec
                    self._genre_audio_counts[genre_str] = 1

            logger.info(
                "Loaded audio features for %d genres from CSV.",
                len(self._genre_audio_features),
            )
        except Exception as exc:
            logger.warning("Could not load audio feature CSV: %s", exc)

    def _get_audio_vector(self, features: SongFeatures) -> Optional[np.ndarray]:
        """Return a normalised audio feature vector for a song, if available."""
        return self._genre_audio_features.get(features.genre.lower())

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, playlist: list[str]) -> None:
        """
        Build the TF-IDF model from a list of file paths.

        Safe to call multiple times; re-trains from scratch each call.
        """
        if not playlist:
            logger.warning("Cannot train: playlist is empty.")
            return

        self._song_features.clear()
        self._song_ids.clear()
        self._is_trained = False

        texts: list[str] = []
        audio_vecs: list[Optional[np.ndarray]] = []

        for path in playlist:
            feat = extract_song_features(path)
            if feat is None:
                continue
            song_id = os.path.basename(path)
            self._song_features[song_id] = feat
            self._song_ids.append(song_id)
            texts.append(feat.to_text())
            audio_vecs.append(self._get_audio_vector(feat))

        if not texts:
            logger.warning("No valid songs found; model not trained.")
            return

        self._tfidf_matrix = self._vectorizer.fit_transform(texts)
        self._build_audio_similarity(audio_vecs)
        self._is_trained = True
        logger.info("Model trained on %d songs.", len(self._song_ids))

    def _build_audio_similarity(self, audio_vecs: list[Optional[np.ndarray]]) -> None:
        """Pre-compute pairwise audio similarity if vectors are available."""
        filled = [v for v in audio_vecs if v is not None]
        if len(filled) < 2:
            self._audio_sim_matrix = None
            return

        # Use zeros for songs without an audio vector
        dim = filled[0].shape[0]
        matrix = np.array(
            [v if v is not None else np.zeros(dim) for v in audio_vecs]
        )
        self._audio_sim_matrix = cosine_similarity(matrix)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def get_recommendations(
        self,
        playlist: list[str],
        current_song_title: Optional[str] = None,
        n: int = 5,
    ) -> list[str]:
        """
        Return up to *n* recommended file paths from *playlist*.

        If *current_song_title* is given, recommendations are based on
        similarity to that song. Otherwise a random selection is returned.
        """
        if not self._is_trained:
            self.train(playlist)

        if not self._is_trained or not playlist:
            return playlist[:n]

        if current_song_title:
            return self._recommend_by_song(playlist, current_song_title, n)

        shuffled = playlist[:]
        random.shuffle(shuffled)
        return shuffled[:n]

    def _recommend_by_song(
        self,
        playlist: list[str],
        song_title: str,
        n: int,
    ) -> list[str]:
        """Return recommendations similar to *song_title*."""
        title_lower = song_title.lower()
        current_id: Optional[str] = next(
            (
                os.path.basename(p)
                for p in playlist
                if title_lower in os.path.basename(p).lower()
            ),
            None,
        )

        if current_id is None or current_id not in self._song_ids:
            return playlist[:n]

        idx = self._song_ids.index(current_id)
        text_sim = cosine_similarity(
            self._tfidf_matrix[idx : idx + 1], self._tfidf_matrix
        ).flatten()

        if self._audio_sim_matrix is not None:
            combined = (
                self.TEXT_WEIGHT  * text_sim
                + self.AUDIO_WEIGHT * self._audio_sim_matrix[idx]
            )
        else:
            combined = text_sim

        # Exclude the song itself; take top-n
        combined[idx] = -1.0
        top_indices = combined.argsort()[::-1][:n]

        path_lookup = {os.path.basename(p): p for p in playlist}
        return [
            path_lookup[self._song_ids[i]]
            for i in top_indices
            if self._song_ids[i] in path_lookup
        ]

    def song_similarity(self, path1: str, path2: str) -> float:
        """Return cosine similarity (0–1) between two songs in the trained model."""
        if not self._is_trained:
            return 0.0
        id1, id2 = os.path.basename(path1), os.path.basename(path2)
        if id1 not in self._song_ids or id2 not in self._song_ids:
            return 0.0
        i1, i2 = self._song_ids.index(id1), self._song_ids.index(id2)
        return float(
            cosine_similarity(
                self._tfidf_matrix[i1 : i1 + 1],
                self._tfidf_matrix[i2 : i2 + 1],
            )[0][0]
        )
