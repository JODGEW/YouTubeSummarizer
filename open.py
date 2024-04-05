from pathlib import Path
from openai import OpenAI
import yaml
import os
import warnings

"""
with open('api.yaml', 'r') as file:
    keys = yaml.safe_load(file)

client = OpenAI(api_key=keys['OPENAI_API_KEY'])
"""

def text_to_speech(text):

  # Ignore DeprecationWarning
  warnings.filterwarnings("ignore", category=DeprecationWarning)

  openai_key = os.getenv('OPENAI_API_KEY')

  client = OpenAI(api_key=openai_key)

  speech_file_path = Path(__file__).parent / "speech.mp3"

  response = client.audio.speech.create(
    model="tts-1",
    voice="nova",
    input=text
  )

  response.stream_to_file(speech_file_path)

  return speech_file_path