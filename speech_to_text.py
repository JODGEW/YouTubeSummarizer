from transformers import Wav2Vec2ForCTC, Wav2Vec2Tokenizer
import soundfile as sf
from pydub import AudioSegment
import torch
import subprocess

def video_to_text_transcription(video_file_path, output_text_file='script.txt'):
    # Convert video to audio
    command = f'ffmpeg -i "{video_file_path}" -ac 1 -ar 16000 "output.wav" -y'
    command = r'ffmpeg -i "C:\Users\hejac\Desktop\YouTube_Summarizer\summary_video.mp4" -ac 1 -ar 16000 "output.wav" -y'
    subprocess.run(command, shell=True)

    # Load pre-trained model and tokenizer
    tokenizer = Wav2Vec2Tokenizer.from_pretrained("facebook/wav2vec2-base-960h")
    model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")

    # Split and process audio
    audio = AudioSegment.from_wav("output.wav")
    segment_length = 30000  # 30 seconds
    segments = [audio[i:i + segment_length] for i in range(0, len(audio), segment_length)]
    transcriptions = []

    for i, segment in enumerate(segments):
        segment_filename = f"segment_{i}.wav"
        segment.export(segment_filename, format="wav")
        audio_input, sample_rate = sf.read(segment_filename)
        input_values = tokenizer(audio_input, return_tensors="pt").input_values
        with torch.no_grad():
            logits = model(input_values).logits
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = tokenizer.decode(predicted_ids[0])
        transcriptions.append(transcription)

    # Combine transcriptions
    final_transcription = " ".join(transcriptions)

    with open(output_text_file, 'w') as f:
        f.write(final_transcription)
    
    return final_transcription

# Example
#video_to_text_transcription("./summary_video.mp4")