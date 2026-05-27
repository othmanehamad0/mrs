# Music Recommendation System

This repository contains a Music Recommendation System that enables users to play/pause local songs, view and play songs in their playlist, view song lyrics from local metadata or text files, and generate music recommendations based on the songs in their playlist. The system is built using Python and PyQt6 for the GUI, along with a recommendation model utilizing TF-IDF Vectorizer and Cosine Similarity.

## Table of Contents

* [Introduction](#introduction)
* [Features](#features)
* [Technologies Used](#technologies-used)
* [Dependencies](#dependencies)
* [Setup and Installation](#setup-and-installation)
* [Usage](#usage)

## Introduction

The Music Recommendation System is a desktop software application that allows users to manage and listen to their local music collection, display song lyrics stored locally, and receive music recommendations based on the songs available in their playlist. The recommendation engine analyzes song metadata and text features to suggest similar songs.

## Features

* **Play/Pause Songs**: Play and pause local audio files.
* **View/Play Songs in Playlist**: Browse and play songs stored on your computer.
* **View Song Lyrics**: Display lyrics from local `.txt` files or embedded metadata.
* **Generate Recommendations**: Recommend similar songs using machine learning techniques.
* **Local Music Library Support**: No internet connection or external APIs required.

## Technologies Used

* **PyQt6** — GUI framework for desktop applications.
* **Pygame / PyQt Multimedia** — Audio playback.
* **Pandas** — Data handling and preprocessing.
* **Scikit-learn** — TF-IDF Vectorizer and Cosine Similarity for recommendations.
* **NumPy** — Numerical operations.
* **Mutagen** — Read metadata from local audio files.
* **SQLite3** — Optional local database for playlists and song storage.

## Dependencies

Install all required dependencies using:

```bash
pip install pyqt6 pygame pandas numpy scikit-learn mutagen
```

Optional dependencies:

```bash
pip install lyricsgenius
```

## Setup and Installation

1. Clone the repository:

```bash
git clone https://github.com/othmanehamad0/mrs
```

2. Navigate to the project folder:

```bash
cd mrs
```

3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

4. Add your local music files to the `songs/` directory.

5. (Optional) Add lyrics text files to the `lyrics/` directory.

6. Run the application:

```bash
python main.py
```

## Usage

1. Open the application.

2. Load or scan your local music folder.

3. Play/pause songs and manage your playlist.

4. View song lyrics if available locally.

5. Open the Recommendations tab to receive song suggestions based on your playlist.

