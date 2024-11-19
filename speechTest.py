from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import azure.cognitiveservices.speech as speechsdk
import threading
import os
import json

app = Flask(__name__)
socketio = SocketIO(app)

# 設定ファイルを読み込む
with open("config.json", "r") as config_file:
    config = json.load(config_file)
    SPEECH_KEY = config.get("AZURE_SPEECH_KEY")
    SERVICE_REGION = config.get("AZURE_SERVICE_REGION")

if not SPEECH_KEY or not SERVICE_REGION:
    raise ValueError("Azure Speech Serviceのキーまたはリージョンが設定ファイルに存在しません。")

recognizer = None
recognizing = False

def start_recognition():
    global recognizing, recognizer

    recognizing = True
    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SERVICE_REGION)
    speech_config.speech_recognition_language = "ja-JP"
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    def handle_result(evt):
        # 最終結果を送信
        socketio.emit('update_text', {'text': evt.result.text, 'final': True})

    def handle_recognizing(evt):
        # 中間結果を送信
        socketio.emit('update_text', {'text': evt.result.text, 'final': False})

    recognizer.recognized.connect(handle_result)
    recognizer.recognizing.connect(handle_recognizing)

    # セッションの開始と終了を検知
    def session_started_handler(evt):
        socketio.emit('status', {'status': 'listening'})
    def session_stopped_handler(evt):
        socketio.emit('status', {'status': 'stopped'})
        
    recognizer.session_started.connect(session_started_handler)
    recognizer.session_stopped.connect(session_stopped_handler)

    recognizer.start_continuous_recognition()

    while recognizing:
        pass

def stop_recognition():
    global recognizing, recognizer
    recognizing = False
    if recognizer:
        recognizer.stop_continuous_recognition()
        recognizer = None

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('start_recognition')
def handle_start():
    global recognizing
    if not recognizing:
        threading.Thread(target=start_recognition).start()
        emit('status', {'status': 'started'})

@socketio.on('stop_recognition')
def handle_stop():
    if recognizing:
        stop_recognition()
        emit('status', {'status': 'stopped'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
