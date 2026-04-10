from flask import Flask, request
import requests
import anthropic
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

def reply_to_line(reply_token, message):
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'
    }
    data = {
        'replyToken': reply_token,
        'messages': [{'type': 'text', 'text': message}]
    }
    requests.post(url, headers=headers, json=data, timeout=10)

def ask_claude(user_message):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="""คุณเป็นผู้ช่วยวิเคราะห์หุ้นส่วนตัว ตอบภาษาไทยสั้นกระชับ
เชี่ยวชาญด้านการลงทุนระยะกลาง-ยาว เทคนิคอล และปัจจัยพื้นฐาน
ตอบไม่เกิน 5 บรรทัด ถ้าถามนอกเรื่องหุ้นให้บอกว่าตอบได้เฉพาะเรื่องการลงทุน""",
            messages=[{"role": "user", "content": user_message}]
        )
        return message.content[0].text
    except Exception as e:
        return f"ขออภัย เกิดข้อผิดพลาด: {str(e)}"

@app.route('/', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def index():
    print(f"[/] Method: {request.method}")
    if request.method == 'POST':
        try:
            body = request.get_json(force=True, silent=True)
            print(f"[/] Body: {body}")
            if body and 'events' in body:
                for event in body['events']:
                    if event.get('type') == 'message' and event['message'].get('type') == 'text':
                        reply_token = event['replyToken']
                        user_text = event['message']['text']
                        print(f"[USER] {user_text}")
                        response = ask_claude(user_text)
                        print(f"[CLAUDE] {response}")
                        reply_to_line(reply_token, response)
        except Exception as e:
            print(f"[ERROR] {e}")
    return 'OK', 200

@app.route('/webhook', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def webhook():
    print(f"[/webhook] Method: {request.method}")
    if request.method == 'POST':
        try:
            body = request.get_json(force=True, silent=True)
            print(f"[/webhook] Body: {body}")
            if body and 'events' in body:
                for event in body['events']:
                    if event.get('type') == 'message' and event['message'].get('type') == 'text':
                        reply_token = event['replyToken']
                        user_text = event['message']['text']
                        print(f"[USER] {user_text}")
                        response = ask_claude(user_text)
                        print(f"[CLAUDE] {response}")
                        reply_to_line(reply_token, response)
        except Exception as e:
            print(f"[ERROR] {e}")
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
