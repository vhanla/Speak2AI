import platform
import mutagen.mp3
import asyncio
import tempfile
import os
import time
import keyboard
import speech_recognition as sr
import edge_tts
from gtts import gTTS
import re
import openai
import pyttsx3
from EdgeGPT import Chatbot
import random

from threading import Thread, Lock
from queue import Queue


WIN32 = platform.system() == 'Windows'
lock = Lock()

if WIN32:
    from pybass3 import Song
else:
    import fcntl
    import playsound

async def starts_with(phrases, string):
    for phrase in phrases:
        if string.startswith(phrase):
            return True
    return False


async def tts(text, engine = 'sapi5', lang = 'en'):
    if WIN32 and (engine == 'sapi5'):
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    elif (engine == 'gtts'):
        engine = gTTS(text = text, lang = lang)
        r = random.randint(1, 20000000)
        audio_file = 'temp' + str(r) + '.mp3'
        engine.save(audio_file)
        await playAudio(audio_file)

    elif engine == 'edge':
        with tempfile.NamedTemporaryFile(suffix='.mp3') as temporary_file:
            communicate = edge_tts.Communicate(text, voice='en-US-AriaNeural')
            async for chunk in communicate.stream():
               if chunk["type"] == "audio":
                    temporary_file.write(chunk["data"])

            await playAudio(temporary_file.name)

def split_text(text, max_chars_per_chunk):
    # Split the input text into chunks
    chunks = []
    current_chunk = ''
    for paragraph in text.split('\n\n'):
        if len(paragraph) < max_chars_per_chunk:
            chunks.append(paragraph)
            current_chunk =  ''
        elif len(current_chunk) + len(paragraph) > max_chars_per_chunk:
            chunks.append(current_chunk)
            current_chunk = ''
        else:
            current_chunk += paragraph + '\n\n'
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

async def is_valid_mp3(filename):
    try:
        mutagen.mp3.MP3(filename)
        return True
    except mutagen.mp3.HeaderNotFoundError:
        return False

async def is_file_unlocked(file_path):
    try:
        # Open the file in exclusive mode
        with open(file_path, 'w') as file:
            if WIN32:
                pass
            else:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        # File is locked by another process
        return False
    else:
        # File is not locked
        return True

async def playAudio(file):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if WIN32:
            #try:
            if await is_valid_mp3(file):
                with lock:
                    song = Song(file)
                    song.play()
                    len_bytes = song.duration_bytes
                    position_bytes = song.position_bytes
                    while position_bytes < len_bytes:
                        #print(song.position, song.duration)
                        if keyboard.is_pressed("s"):
                            song.stop()
                            break
                        await asyncio.sleep(1)
                        position_bytes = song.position_bytes
                    #except Exception as e:
                        #print("Error playing sound:", e)
                    os.remove(file)
        else:
            with lock:
                playsound.playsound(file)
                os.remove(file)
    finally:
        loop.close()

# función para procesar los elementos de la cola
async def process_queue(text):
    r = random.randint(1, 20000000)
    audio_file = 'temp' + str(r) + '.mp3'
    try:
        with open(audio_file, "wb") as temporary_file:
            communicate = edge_tts.Communicate(text, voice='es-MX-DaliaNeural')
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    temporary_file.write(chunk["data"])
        await asyncio.sleep(1)
        output_queue.put(audio_file)
    except Exception:
        if os.path.exists(audio_file):
            os.remove(audio_file)
        #raise

# función para reproducir los elementos convertidos a audio
def play_queue():
    while True:
        # tomar un elemento de la cola de elementos convertidos
        audio_file = output_queue.get()
        #if audio_file != None:

        print(f"Reproduciendo {audio_file}")
        if os.path.exists(audio_file):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(playAudio(audio_file))
            #playAudio(audio_file)
        # marcar la tarea de la cola como completada
        output_queue.task_done()
        #else:
        #    output_queue.queue.clear()


def procesa():
    while True:
        element = input_queue.get()
        #if element != None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_queue(element))
        input_queue.task_done()
        #else:
        #    input_queue.queue.clear()


async def speak(text, engine = 'sapi5', lang = 'en'):

    #input_queue.put(None)
    #output_queue.put(None)
    #input_queue.queue.clear()
    #output_queue.queue.clear()

    #chunks = split_text(text, 1000)
    #for i, chunk in enumerate(chunks):
    #    print('# ' + chunk + '\n')

    #lang = 'es'
    max_chars_per_chunk = 1000

    # crear el hilo para procesar la cola
    processing_thread = Thread(target=procesa)
    processing_thread.daemon = True
    processing_thread.start()

    # crear el hilo para reproducir la cola
    play_thread = Thread(target=play_queue)
    play_thread.daemon = True
    play_thread.start()

    # agregar elementos a la cola
    chunks = split_text(text, max_chars_per_chunk)
    for i, chunk in enumerate(chunks):
        input_queue.put(chunk)


    # esperar a que se completen todas las tareas en ambas colas
    input_queue.join()
    output_queue.join()

    while not output_queue.empty():
        await asyncio.sleep(1)



async def askBing(question):
    bot = Chatbot(cookiePath='./cookies.json')
    print("Asking Bing")
    print("Please wait a moment...")
    response = (await bot.ask(prompt=question))["item"]["messages"][1]["adaptiveCards"][0]["body"][0]["text"]

    clean = re.sub(r'\[[0-9]\]:\s(https\S+|www\S+)\s\".*?\"', '', response)
    clean = re.sub(r"http\S+", "", clean)
    clean = re.sub(r"\[.*?\]", "", clean)
    clean = clean.replace("Hi, this is Bing.", "")
    clean = clean.replace("Hello, this is Bing.", "")
    clean = clean.replace("*", "")
    return clean

async def askChatGPT(question):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "user",
                "content": f"{question}"
            }
        ],
        max_tokens=1024,
        temperature=0.5,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return str(response.choices[0].message.content)

input_queue = Queue()
output_queue = Queue()
async def main():
    GREETING = True
    CHATGPT = False
    SPANISH = True
    while True:
        #bot = Chatbot(cookiePath='./cookies.json')
        respuesta = ""
        if keyboard.is_pressed("q"):
            loop.stop()
        r = sr.Recognizer()

        if GREETING:
            GREETING  = False
            #await tts('Hello, what do you want to talk about?', engine = 'gtts', lang='es')
            await speak('Hola, soy una inteligencia artificial platicadora', engine = 'gtts', lang='es')
        else:
            if SPANISH:
                await speak('¿Qué quieres saber?:', engine = 'gtts', lang='es')
            else:
                await speak('Ask me more:', engine = 'gtts', lang='en')

        print("Commands: 'Switch to GPT', 'Switch to B', 'Switch to Spanish', 'Hablemos en Inglés', 'Salir', 'Exit'")
        if SPANISH:
            print("Pregunta:")
        else:
            print("Ask me anything: ")
        with sr.Microphone() as source:
            audio = r.listen(source)

        opa = True
        try:
            if SPANISH:
                command = r.recognize_google(audio,language="es-ES")
            else:
                command = r.recognize_google(audio,language="en-US")
            print("Question: " + command)

        except:
            opa = False
            if SPANISH:
                print("No te entendí, inténtalo de nuevo")
            else:
                print("I couldn't get that, try again")
            command = ""

        if opa:
            answer = ""
            if command.lower().startswith("switch to g"):
                CHATGPT = True
                print("Switched to ChatGPT")
            elif command.lower().startswith("switch to b"):
                CHATGPT = False # Use Bing
                print("Switched to Bing Chat")
            elif command.lower().startswith("switch to spanish"):
                SPANISH = True
                print("Háblemos en español :)")
            elif command.lower().startswith("hablemos en inglés"):
                SPANISH = False
            elif command.strip() == "exit" or command.strip() == "salir":
                exit()
            else:
                if CHATGPT:
                    answer = await askChatGPT(command)
                else:
                    answer = await askBing(command)

            if answer.strip() != "":
                print(answer)
                if SPANISH:
                    await speak(answer, engine='gtts', lang='es')
                else:
                    await speak(answer, engine='gtts', lang='en')

if __name__ == "__main__":
    openai.api_key = os.getenv('OPENAI_API_KEY')
    asyncio.get_event_loop().run_until_complete(main())