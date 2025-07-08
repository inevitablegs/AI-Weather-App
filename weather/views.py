from django.shortcuts import render

# Create your views here.
import google.generativeai as genai
import requests
from django.shortcuts import render
import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEATHER_API_KEY = "3c487a963733c205c52caed7dba21c87"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

def chatbot_view(request):
    if 'chat_history' not in request.session:
        request.session['chat_history'] = []

    if request.method == 'POST':
        user_input = request.POST.get('query')
        chat_history = request.session['chat_history']
        chat_history.append({'sender': 'user', 'text': user_input})

        # Step 1: Let Gemini decide what to do
        weather_check_prompt = f"""
        User said: "{user_input}"

        If this message requires weather info, reply with: WEATHER:<city>
        If not, reply: CHAT
        If city is unknown, reply: UNKNOWN
        """
        check_response = model.generate_content(weather_check_prompt).text.strip()

        if check_response.startswith("WEATHER:"):
            city = check_response.split("WEATHER:")[1].strip()
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
            data = requests.get(url).json()

            if data.get("cod") == 200:
                temp = data["main"]["temp"]
                desc = data["weather"][0]["description"]

                # Step 2: Now ask Gemini to respond naturally
                prompt = f"""
                The user asked: "{user_input}"
                Current weather in {city}: {temp}°C, {desc}

                Reply in a friendly, human tone with this info.
                """
                smart_response = model.generate_content(prompt).text.strip()
            else:
                smart_response = f"Sorry, I couldn't find weather for {city}."
        elif check_response == "UNKNOWN":
            smart_response = "I need the city name to get weather details. Can you mention the city?"
        else:
            # Generic chat
            chat_prompt = f"""You're a helpful weather chatbot.
User said: {user_input}
Reply casually but helpfully."""
            smart_response = model.generate_content(chat_prompt).text.strip()

        chat_history.append({'sender': 'bot', 'text': smart_response})
        request.session['chat_history'] = chat_history
        request.session.modified = True

    return render(request, 'weather.html', {
        'chat_history': request.session.get('chat_history', [])
    })
    
from django.shortcuts import redirect

def clear_chat(request):
    if 'chat_history' in request.session:
        del request.session['chat_history']
    return redirect('chatbot')
