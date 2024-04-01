from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor, BartTokenizer, BartForConditionalGeneration
import torch
import soundfile as sf
import librosa
import re
import time

# Start timing
start_time = time.time()

def extract_audio(video_path, audio_path="temp_audio.wav"):
    from moviepy.editor import VideoFileClip
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path)
    return audio_path

# Note: Renamed variables for clarity
processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
wav2vec_model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")

def transcribe_in_chunks(path, chunk_duration=10, min_duration=1):
    speech, original_sample_rate = sf.read(path)
    
    # Ensure speech is mono
    if speech.ndim > 1:
        speech = speech.mean(axis=1)
    
    # Resample speech to 16kHz if it's not already
    if original_sample_rate != 16000:
        speech = librosa.resample(speech, original_sample_rate, 16000)
    
    total_samples = len(speech)
    chunk_samples = int(chunk_duration * 16000)  # Now directly using 16kHz after resampling
    min_samples = int(min_duration * 16000)  # Calculate min_samples based on min_duration and 16kHz
    
    transcriptions = []

    for start in range(0, total_samples, chunk_samples):
        end = start + chunk_samples
        chunk = speech[start:end]
        
        # Process chunk only if it's longer than min_samples
        if len(chunk) >= min_samples:  # Corrected condition
            input_values = processor(chunk, sampling_rate=16000, return_tensors="pt").input_values
            with torch.no_grad():
                logits = wav2vec_model(input_values).logits
            predicted_ids = torch.argmax(logits, dim=-1)
            transcription = processor.batch_decode(predicted_ids)[0]
            transcriptions.append(transcription)
        else:
            print(f"Skipping a short chunk with {len(chunk)} samples.")

    return " ".join(transcriptions)

def summarize_video(audio_path):
    bart_tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
    bart_model = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")

    transcription = transcribe_in_chunks(audio_path)

    inputs = bart_tokenizer.encode_plus(transcription, return_tensors="pt", truncation=True, padding="max_length", max_length=1024)
    input_ids = inputs["input_ids"].long()  # Convert to long to avoid dtype issues

    summary_ids = bart_model.generate(input_ids, max_length=150, min_length=40, length_penalty=2.0, num_beams=4, early_stopping=True)
    summary = bart_tokenizer.decode(summary_ids[0], skip_special_tokens=True)

    #! Sentences letter issue
    sentences = re.split('(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', summary)

    # Ensure each sentence ends with a period and capitalize it
    capitalized_sentences = []
    for sentence in sentences:
        # Trim whitespace and check if the sentence ends with a period or question mark
        sentence = sentence.strip()
        if not sentence.endswith('.') and not sentence.endswith('?'):
            # Add a period if it doesn't already end with one
            sentence += '.'
        capitalized_sentences.append(sentence.capitalize())

    # Join the sentences back into a single string
    capitalized_summary = ' '.join(capitalized_sentences)

    print("Summary:", capitalized_summary)

    end_time = time.time()  # Timing end
    print(f"Process took {end_time - start_time:.2f} seconds.")

    return capitalized_summary
