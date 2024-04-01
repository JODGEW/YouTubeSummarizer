import os
from google.cloud import translate_v2 as translate

def set_up_credentials():
    current_dir = os.path.dirname(os.path.realpath(__file__))
    credential_path = os.path.join(current_dir, 'JSON/google_key.json')
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path

def read_text_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def empty_file(file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("")

def process_and_translate_txt(file_path, target_language='zh'):
    # Set up the credentials for the Translation API
    set_up_credentials()
    
    # Read text from the file
    text = read_text_from_file(file_path)
    if not text:
        print("The file is already empty or has been processed.")
        return "No content to translate."

    # Proceed with translation
    translate_client = translate.Client()
    result = translate_client.translate(text, target_language=target_language)
    translation = result['translatedText']
    print(f"Translation: {translation}")

    # Empty the file after translating
    empty_file(file_path)

    return translation

if __name__ == '__main__':
    file_path = r"C:\Users\hejac\Desktop\YouTube_Summarizer\script.txt"
    try:
        translation = process_and_translate_txt(file_path)
    except Exception as e:
        print(f"An error occurred: {e}")
