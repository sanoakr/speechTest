from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import azure.cognitiveservices.speech as speechsdk
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
import threading
import os
import json
import asyncio

app = Flask(__name__)
socketio = SocketIO(app)

# 設定ファイルを読み込む
with open("config.json", "r") as config_file:
    config = json.load(config_file)
    SPEECH_KEY = config.get("AZURE_SPEECH_KEY")
    SERVICE_REGION = config.get("AZURE_SERVICE_REGION")
    LANGUAGE_KEY = config.get("AZURE_LANGUAGE_KEY")

if not SPEECH_KEY or not SERVICE_REGION or not LANGUAGE_KEY:
    raise ValueError("Azure サービスのキーまたはリージョンが設定ファイルに存在しません。")

# Language Clientの初期化
text_analytics_client = TextAnalyticsClient(
    endpoint=f"https://{SERVICE_REGION}.api.cognitive.microsoft.com/",
    credential=AzureKeyCredential(LANGUAGE_KEY)
)

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

@socketio.on('summarize_text')
def handle_summarize(data):
    try:
        text = data.get('text', '')
        if not text:
            emit('summary_result', {'error': '要約するテキストがありません。'})
            return

        # 要約処理を実行
        try:
            # begin_extract_summaryを使用して要約を開始
            poller = text_analytics_client.begin_extract_summary([text])
            extract_summary_results = poller.result()

            for result in extract_summary_results:
                if result.kind == "ExtractiveSummarization":
                    # 要約文を結合
                    summary = " ".join([sentence.text for sentence in result.sentences])
                    emit('summary_result', {'summary': summary})
                elif result.is_error:
                    emit('summary_result', {
                        'error': f'要約エラー: {result.error.code} - {result.error.message}'
                    })
                    return

        except Exception as api_error:
            emit('summary_result', {'error': f'要約APIエラー: {str(api_error)}'})

    except Exception as e:
        emit('summary_result', {'error': f'要約処理中にエラーが発生しました: {str(e)}'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
