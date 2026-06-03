#!/bin/bash
export PYTHONWARNINGS="ignore::UserWarning"
export PYTHONHTTPSVERIFY=0
STEM_MODEL=${2:-""}
SPOTIFY_LINK="$1"
echo "Downloading track..."
python -m spotdl $1 --output "{artist}-{title}/in/{artist}-{title}.{output-ext}"
FOLDER=$(ls -td */ | head -n 1) 
FOLDER=${FOLDER%?}
SLUG=$(python -m slugify $FOLDER)
mv "$FOLDER" "$SLUG"
mv "$SLUG/in/$FOLDER.mp3" "$SLUG/in/$SLUG.mp3"
echo "Track downloaded."
echo "$SLUG.mp3"
echo "Separating stems..."
cd "$SLUG/in"
models=(
	""
	"--two-stems vocals -n htdemucs"
	"-n htdemucs"
	"-n htdemucs_ft"
	"-n htdemucs_6s"
)
model_folders=(
	""
	"htdemucs"
	"htdemucs"
	"htdemucs_ft"
	"htdemucs_6s"
)
menu_options=(
	"1. 2-Part band (Vocals, Other)"
	"2. 4-Part band (Vocals, Other, Bass, Drums) [Fast]"
	"3. 4-Part band (Vocals, Other, Bass, Drums) [Slow]"
	"4. 6-Part band (Vocals, Other, Piano, Guitar, Bass, Drums)"
)
STEM_MODEL=""
if [ -z "$STEM_MODEL" ]; then 
	echo "Choose your stem separation method (1-4):" 
	echo "--------------------------------------------------" 
	select choice in "${menu_options[@]}" "Quit"; do 
		case "$choice" in 
			"Quit") 
				echo "Operation cancelled." 
				exit 0 
				;; 
			"") 
				echo "Invalid choice. Please enter a number from the menu." 
				;; 
			*) 
				index="${choice:0:1}"
				STEM_MODEL="${models[$index]}" 
				STEM_FOLDER="${model_folders[$index]}" 
			 	break 
				;; 
		esac 
	done 
fi 
python -m demucs $STEM_MODEL --filename "{track}-{stem}.{ext}" "$SLUG.mp3"
mv separated/$STEM_FOLDER/*.* .
rm -rf separated
echo "Stems separated."
ls -1 *.wav
echo "Generating MIDI files..."
for f in *.wav; do python -m transkun.transcribe "$f" "${f%.wav}.mid"; done
mkdir ../out
mkdir ../src
mv *.mid ../src
echo "Created MIDI files."
cd ../src
ls -1 *.mid
echo "Generating score..."
cp ../../template.musicxml "$SLUG.musicxml"
python3 ../../update_musicxml.py "../in/$SLUG.mp3" "$SLUG.musicxml"
echo "Created score."
ls -1 *.musicxml
echo "Generating Reaper file"
cp ../../template.RPP "$SLUG.RPP"
echo "Generated Reaper file"
