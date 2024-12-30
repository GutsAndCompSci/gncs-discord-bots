import discord
from discord import app_commands
import google.generativeai as genai
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

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

@tree.command(name="chat", description="Chat with the bot")
async def chat(interaction: discord.Interaction, message: str):
    user_id = interaction.user.id
    
    try:
        history = chat_histories[user_id]
        chat = model.start_chat(history=history)
        response = chat.send_message(message)
        history.append({'role': 'user', 'parts': [message]})
        history.append({'role': 'model', 'parts': [response.text]})
        if len(history) > 20:
            history = history[-20:]
        chat_histories[user_id] = history
        
        await interaction.response.send_message(f"{response.text}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        await interaction.response.send_message("Sorry, I encountered an error. Please try again later.")

@tree.command(name="clear", description="Clear your chat history")
async def clear(interaction: discord.Interaction):
    chat_histories[interaction.user.id].clear()
    await interaction.response.send_message("Chat history cleared!")

client.run(os.getenv('CHAT_TOKEN'))
