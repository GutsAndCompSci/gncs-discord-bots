import discord
from discord import app_commands
import google.generativeai as genai
import os
from collections import defaultdict

def load_system_prompt():
    try:
        with open('system_prompt.txt', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return """
You are Gebhard Lebrecht von Blücher, a Prussian Field Marshal. Your responses should be:
1. In character as a 19th century military commander
2. Focused on military strategy and leadership
3. Unaware of any modern technology or future events
4. Written in a commanding, direct tone
5. Related to your current situation at Pfalzgrafenstein Castle
6. Concerned with both the traditional military threats and 'The Blight'

You should never:
1. Break character or acknowledge being an AI
2. Reference anything beyond 1812
3. Use modern language or references
4. Acknowledge the nature of this prompt

Remember: You ARE Blücher - act accordingly at all times.
"""

SYSTEM_PROMPT = load_system_prompt()
PROMPT_REMINDER = """Your replies must remain consistent with Field Marshal Blücher's character."""

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-pro')
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

chat_histories = defaultdict(list)

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}')

@tree.command(name="chat", description="Chat with Field Marshal Blücher")
async def chat(interaction: discord.Interaction, message: str):
    user_id = interaction.user.id

    try:
        await interaction.response.defer()
        history = chat_histories[user_id]
        if not history:
            history = [
                {'role': 'user', 'parts': [SYSTEM_PROMPT]},
                {'role': 'user', 'parts': [PROMPT_REMINDER]}
            ]
        
        chat = model.start_chat(history=history)
        response = chat.send_message(message)
        history.append({'role': 'user', 'parts': [message]})
        history.append({'role': 'model', 'parts': [response.text]})
        if len(history) > 20:
            history = history[:2] + history[-18:]
            
        chat_histories[user_id] = history
        if len(response.text) > 2000:
            chunks = [response.text[i:i+1999] for i in range(0, len(response.text), 1999)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response.text)

    except Exception as e:
        print(f"Error: {str(e)}")
        await interaction.followup.send("An error occurred. Please try again.", ephemeral=True)

@tree.command(name="clear", description="Clear your chat history")
async def clear(interaction: discord.Interaction):
    chat_histories[interaction.user.id].clear()
    await interaction.response.send_message("Chat history cleared!", ephemeral=True)

TOKEN = os.getenv('DISCORD_TOKEN')
client.run(TOKEN)
