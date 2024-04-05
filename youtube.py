from flask import Flask, request, jsonify, render_template, send_from_directory
from google.cloud import translate_v2 as translate
from google.cloud import exceptions
from pytube import YouTube
from pytube.exceptions import AgeRestrictedError
import traceback
from lit import extract_audio, summarize_video, transcribe_in_chunks
import os
from open import text_to_speech
import pathlib as Path

#! Still need to debug on the embed video
def cleanup_files(directory, file_extensions):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(tuple(file_extensions)):
                os.remove(os.path.join(root, file))

#! YouTube short podcast 1: https://www.youtube.com/watch?v=rLXcLBfDwvE
#! YouTube short podcast 2: https://www.youtube.com/watch?v=_qtpmi4yzSs
#! YouTube Ted short podcast: https://www.youtube.com/watch?v=8S0FDjFBj8o

                
current_dir = os.path.dirname(os.path.realpath(__file__))
credential_path = os.path.join(current_dir, 'JSON/google_key.json')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path

app = Flask(__name__, template_folder='Front_end')

@app.route('/audio/<filename>')
def serve_audio(filename):
    # Serve the audio file from the root directory of the Flask app
    directory = os.path.join(app.root_path)  # The directory where your app.py is located.
    return send_from_directory(directory, filename)

@app.route('/')
def index():
    return render_template('app.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    # Expecting a JSON payload with the video URL
    if not request.is_json:
        return jsonify({'error': 'Missing JSON in request'}), 400
    
    data = request.get_json()
    video_url = data['video_url']
    yt = YouTube(video_url)

    video_id = yt.video_id
    
    # Construct the YouTube embed URL
    embed_url = f"https://www.youtube.com/embed/{video_id}"

    # Summary style selection
    summary_style = data.get('summary_style')

    # Langauge selection
    language = data.get('language', 'en')

    try:
        # Call the cleanup function
        current_dir = os.path.dirname(os.path.realpath(__file__))
        subdirectory = '.'
        full_cleanup_path = os.path.join(current_dir, subdirectory)

        cleanup_files(full_cleanup_path, ['wav', 'mp3', 'mp4'])

        # Generate the necessary data, such as downloading the video, generating captions, etc.
        video_path = download_video_with_audio(video_url)

        if not video_path:
            raise Exception("Failed to download video.")

        """
        #* Feature extraction function
        summary_video_path = generate_video_summary(video_path)

        #* Speech-to-text function
        #transcription = video_to_text_transcription(summary_video_path)
        model = whisper.load_model("base")
        result = model.transcribe(summary_video_path)
        transcription = result['text']
        """

        # Initialize translated_transcription
        translated_transcription = ""
        # Initialize audio url
        audio_url = ""

        #! Transcription only
        if summary_style == 'Transcribe':
            audio = extract_audio(video_path)
            transcription = transcribe_in_chunks(audio)
            if transcription:
                # If transcription is not empty, proceed to translate
                try:
                    translated_transcription = translate_text(transcription, language)

                    audio_url = text_to_speech(translated_transcription)
                except Exception as e:
                    app.logger.error('Translation failed: %s', str(e))
                    return jsonify({'error': 'Translation failed'}), 500
            else:
                # If transcription is empty, handle the case appropriately
                app.logger.error('Transcription is empty, nothing to translate.')
                return jsonify({'error': 'Transcription is empty'}), 500
        #! Summary only
        elif summary_style == 'Summarize':
            #* HuggingFace Model (Summary)
            audio = extract_audio(video_path)
            transcription = summarize_video(audio)
            if transcription:
                # If transcription is not empty, proceed to translate
                try:
                    translated_transcription = translate_text(transcription, language)

                    speech_file_path = text_to_speech(translated_transcription)

                    audio_file = speech_file_path.name

                    # Convert the Path object to a string for the full path
                    audio_url = f"/audio/{audio_file}"
                except Exception as e:
                    app.logger.error('Translation failed: %s', str(e))
                    return jsonify({'error': 'Translation failed'}), 500
            else:
                # If transcription is empty, handle the case appropriately
                app.logger.error('Transcription is empty, nothing to translate.')
                return jsonify({'error': 'Transcription is empty'}), 500
        else:
            return jsonify({'error': 'Invalid action specified'}), 400

        # Construct the response
        response_data = {
            'title': yt.title,
            #'thumbnail_url': yt.thumbnail_url,
            'embed_video': embed_url,
            'video_path': video_path,
            'transcription': translated_transcription,
            'audio': audio_url
        }
        
        # Return the response before cleanup
        response = jsonify(response_data)

        return response
    
    #! Still not able to recognize as 403, is 500
    except AgeRestrictedError as e:
            app.logger.error('An error occurred: %s', e)
            return jsonify({'message': 'Sorry, this video is restricted by YouTube policy and cannot be summarized without logging in.'}), 403

    except Exception as e:
        error_message = str(e)
        app.logger.error('An error occurred: %s', error_message)
        return jsonify({'error': 'An unexpected error occurred while processing your request.'}), 500
    
def set_up_credentials():
    current_dir = os.path.dirname(os.path.realpath(__file__))
    credential_path = os.path.join(current_dir, 'JSON/google_key.json')
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path

def translate_text(text, target_language='zh'):
    set_up_credentials()

    if not text:
        # Log an informative error message and raise an exception or return an error
        app.logger.error('No text provided for translation.')
        raise ValueError("No text provided for translation.")

    try:
        translate_client = translate.Client()
        result = translate_client.translate(text, target_language=target_language)
        return result['translatedText']
    except exceptions.BadRequest as e:
        app.logger.error('Translation failed: %s', str(e), exc_info=True)
        raise
    
# Download the YouTube Video
def download_video_with_audio(url: str) -> str:
    try:
        yt = YouTube(url)

        # Try getting the highest resolution progressive stream available
        stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        # If not available, download the highest video-only stream and audio stream and then merge them
        if not stream:
            video_stream = yt.streams.filter(only_video=True, file_extension='mp4').order_by('resolution').desc().first()
            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            
            video_file = video_stream.download(filename_prefix='video_')
            audio_file = audio_stream.download(filename_prefix='audio_')
            
            merged_file = 'merged_video.mp4'
            
            # Use ffmpeg to merge video and audio
            cmd = f'ffmpeg -i "{video_file}" -i "{audio_file}" -c:v copy -c:a aac "{merged_file}"'
            os.system(cmd)
            
            # Remove the separate video and audio files after merging
            os.remove(video_file)
            os.remove(audio_file)
            
            return merged_file
        else:
            # If a progressive stream is available, download it directly
            out_file = stream.download()
            return out_file

    except Exception as e:
        print(f"An error occurred: {e}")
        return ""

def download_video():
    video_url = request.json.get('video_url')  # Get the URL from the AJAX request

    try:
        # Create a YouTube object
        yt = YouTube(video_url)
        video_path = download_video_with_audio(yt)  # Your existing function
        # Need to define how you're sending the file back
        return jsonify({'message': 'Video downloaded successfully.', 'path': video_path})
    except Exception:
        error_trace = traceback.format_exc()
        return jsonify({'error': str(error_trace)}), 500

if __name__ == '__main__':
    app.run(debug=True)
