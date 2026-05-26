import sys
import xml.etree.ElementTree as ET
from tinytag import TinyTag
import librosa
import numpy as np

# Map for MusicXML fifths (Circle of Fifths lookup)
KEY_TO_FIFTHS = {
    'C Major': (0, 'major'), 'G Major': (1, 'major'), 'D Major': (2, 'major'), 'A Major': (3, 'major'),
    'E Major': (4, 'major'), 'B Major': (5, 'major'), 'F# Major': (6, 'major'), 'C# Major': (7, 'major'),
    'F Major': (-1, 'major'), 'Bb Major': (-2, 'major'), 'Eb Major': (-3, 'major'), 'Ab Major': (-4, 'major'),
    'Db Major': (-5, 'major'), 'Gb Major': (-6, 'major'), 'Cb Major': (-7, 'major'),
    
    'A Minor': (0, 'minor'), 'E Minor': (1, 'minor'), 'B Minor': (2, 'minor'), 'F# Minor': (3, 'minor'),
    'C# Minor': (4, 'minor'), 'G# Minor': (5, 'minor'), 'D# Minor': (6, 'minor'), 'A# Minor': (7, 'minor'),
    'D Minor': (-1, 'minor'), 'G Minor': (-2, 'minor'), 'C Minor': (-3, 'minor'), 'F Minor': (-4, 'minor'),
    'Bb Minor': (-5, 'minor'), 'Eb Minor': (-6, 'minor'), 'Ab Minor': (-7, 'minor')
}

def detect_meter(y, sr, bpm):
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        if len(beats) < 8: return "4/4"
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        beat_chroma = librosa.util.sync(chroma, beats, aggregate=np.median)
        lag_3 = np.mean([np.corrcoef(beat_chroma[:, i], beat_chroma[:, i+3])[0,1] for i in range(beat_chroma.shape[1]-3) if i%3==0])
        lag_4 = np.mean([np.corrcoef(beat_chroma[:, i], beat_chroma[:, i+4])[0,1] for i in range(beat_chroma.shape[1]-4) if i%4==0])
        if lag_3 > lag_4 * 1.1:
            return "3/4" if bpm < 110 else "6/8"
        else:
            return "4/4"
    except: return "4/4"

def analyze_audio(audio_path):
    info = {}
    
    # 1. Read Metadata
    tag = TinyTag.get(audio_path)
    info['title'] = (tag.title[0] if isinstance(tag.title, list) else tag.title) or "UNKNOWN TITLE"
    info['author'] = (tag.artist[0] if isinstance(tag.artist, list) else tag.artist) or "UNKNOWN"
    info['style'] = (tag.genre[0] if isinstance(tag.genre, list) else tag.genre) or "UNKNOWN STYLE"
    raw_lyricist = getattr(tag, 'lyricist', None)
    info['lyricist'] = (raw_lyricist[0] if isinstance(raw_lyricist, list) else raw_lyricist) or ""

    # 2. Extract Audio Features
    y, sr = librosa.load(audio_path, sr=None)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = tempo[0] if isinstance(tempo, np.ndarray) else tempo
    info['tempo'] = str(round(bpm))
    info['meter'] = detect_meter(y, sr, bpm)

    # 3. Key Detection
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_vals = np.sum(chroma, axis=1)
    maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    min_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    notes_map = {'C#': 'C#', 'D#': 'Eb', 'F#': 'F#', 'G#': 'Ab', 'A#': 'Bb'}
    
    best_score = -float('inf')
    best_key = ""
    for i in range(12):
        maj_score = np.corrcoef(chroma_vals, np.roll(maj_profile, i))[0, 1]
        min_score = np.corrcoef(chroma_vals, np.roll(min_profile, i))[0, 1]
        if maj_score > best_score: best_score, best_key = maj_score, f"{notes[i]} Major"
        if min_score > best_score: best_score, best_key = min_score, f"{notes[i]} Minor"
            
    root_note = best_key.split()[0]
    mode = best_key.split()[1]
    info['key'] = f"{notes_map.get(root_note, root_note)} {mode}"
    return info

def update_musicxml(xml_path, info):
    # First update structural XML fields (Tempo, Time Sig, Key Sig) using the XML parser
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Update structural Title if present
    mov_title = root.find('movement-title')
    if mov_title is not None: mov_title.text = info['title']

    # Update structural Composer/Lyricist tags if present
    id_tag = root.find('identification')
    if id_tag is not None:
        comp = id_tag.find("./creator[@type='composer']")
        if comp is not None: comp.text = info['author']
        lyr = id_tag.find("./creator[@type='lyricist']")
        if lyr is not None: lyr.text = info['lyricist']

    # Update Playback Tempo
    sound_tag = root.find(".//sound")
    if sound_tag is not None and 'tempo' in sound_tag.attrib:
        sound_tag.set('tempo', info['tempo'])

    per_minute_tag = root.find(".//per-minute")
    if per_minute_tag is not None:
        per_minute_tag.text = info['tempo']

    # Update System Time Signature
    num_beats, beat_type = info['meter'].split('/')
    time_tag = root.find(".//time")
    if time_tag is not None:
        beats = time_tag.find('beats')
        b_type = time_tag.find('beat-type')
        if beats is not None: beats.text = num_beats
        if b_type is not None: b_type.text = beat_type

    # Update System Key Signature
    fifths_val, mode_val = KEY_TO_FIFTHS.get(info['key'], (0, 'major'))
    for key_tag in root.iter("key"):
        fifths = key_tag.find('fifths')
        mode = key_tag.find('mode')
        if fifths is not None: 
            fifths.text = str(fifths_val)
        if mode is not None: 
            mode.text = mode_val
    # Write out structural edits back to file string
    tree.write(xml_path, encoding='utf-8', xml_declaration=True)
    # NOW: Handle text-level replacement for your exact credit placeholders!
    with open(xml_path, 'r', encoding='utf-8') as file:
        xml_content = file.read()
    # Swap your placeholder tokens directly with the calculated audio values
    xml_content = xml_content.replace('$TITLE', info['title'].upper())
    xml_content = xml_content.replace('$STYLE', info['style'].upper())
    xml_content = xml_content.replace('$COMPOSER', info['author'].upper())
    xml_content = xml_content.replace('$LYRICIST', info['lyricist'].upper())
    # Save completely polished file
    with open(xml_path, 'w', encoding='utf-8') as file:
        file.write(xml_content)
        

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 detect_all.py <song.mp3> <score.musicxml>")
    else:
        song_data = analyze_audio(sys.argv[1])
        update_musicxml(sys.argv[2], song_data)
