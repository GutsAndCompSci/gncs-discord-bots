import discord
from discord import app_commands
import random
import json
import asyncio
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

ALLOWED_CHANNEL_ID = 0

intents = discord.Intents.default()
intents.message_content = True

activity = discord.Activity(type=discord.ActivityType.playing, name="With a Flintlock")
client = discord.Client(intents=intents, activity=activity)
tree = app_commands.CommandTree(client)

users = {}
rob_cooldowns = {}
coinflip_cooldowns = {}
job_cooldowns = {}
bank_cooldowns = {}

JOBS = {
    "Peasant": {"salary": 50, "xp_required": 0},
    "Merchant": {"salary": 100, "xp_required": 50},
    "Craftsman": {"salary": 200, "xp_required": 100},
    "Noble": {"salary": 500, "xp_required": 250}
}

def save_users():
    with open('users.json', 'w') as f:
        json.dump(users, f)

def load_users():
    global users
    try:
        with open('users.json', 'r') as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}

def initialize_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = {
            "balance": 100,
            "bank_balance": 0,
            "job": None,
            "xp": 0,
            "bank_space": 500
        }
        save_users()

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}!')
    load_users()
    client.loop.create_task(lootbox_loop())

async def check_channel(interaction: discord.Interaction) -> bool:
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message("You can only use economy commands in the designated channel.", ephemeral=True)
        return False
    return True

@tree.command(name="bal", description="Check your balance and bank details.")
async def bal(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]
    embed = discord.Embed(title=f"{interaction.user.name}'s Financial Status", color=discord.Color.green())
    embed.add_field(name="Wallet Balance", value=f"{user_data['balance']} francs", inline=False)
    embed.add_field(name="Bank Balance", value=f"{user_data['bank_balance']} francs", inline=False)
    embed.add_field(name="Bank Capacity", value=f"{user_data['bank_space']} francs", inline=False)

    if user_data['job']:
        embed.add_field(name="Current Job", value=f"{user_data['job']} (XP: {user_data['xp']})", inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="deposit", description="Deposit money into your bank.")
async def deposit(interaction: discord.Interaction, amount: int):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    if amount <= 0:
        await interaction.response.send_message("You must deposit a positive amount.", ephemeral=True)
        return

    if amount > user_data['balance']:
        await interaction.response.send_message("You don't have enough francs in your wallet.", ephemeral=True)
        return

    total_bank_balance = user_data['bank_balance'] + amount
    if total_bank_balance > user_data['bank_space']:
        await interaction.response.send_message(f"Your deposit would exceed your bank capacity of {user_data['bank_space']} francs.", ephemeral=True)
        return

    user_data['balance'] -= amount
    user_data['bank_balance'] += amount
    save_users()

    await interaction.response.send_message(f"Deposited {amount} francs. Bank balance: {user_data['bank_balance']} francs.")

@tree.command(name="withdraw", description="Withdraw money from your bank.")
async def withdraw(interaction: discord.Interaction, amount: int):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    if amount <= 0:
        await interaction.response.send_message("You must withdraw a positive amount.", ephemeral=True)
        return

    if amount > user_data['bank_balance']:
        await interaction.response.send_message("You don't have enough francs in your bank.", ephemeral=True)
        return

    user_data['balance'] += amount
    user_data['bank_balance'] -= amount
    save_users()

    await interaction.response.send_message(f"Withdrew {amount} francs. Wallet balance: {user_data['balance']} francs.")

    @tree.command(name="slots", description="Play the slot machine!")
    async def slots(interaction: discord.Interaction, bet: int):
        if not await check_channel(interaction):
            return

        user_id = str(interaction.user.id)
        initialize_user(user_id)

        user_data = users[user_id]

        current_time = asyncio.get_event_loop().time()
        if user_id in bank_cooldowns and bank_cooldowns[user_id] > current_time:
            remaining_time = int(bank_cooldowns[user_id] - current_time)
            seconds = remaining_time % 60
            await interaction.response.send_message(f"Hold your horses! Wait {seconds}s before spinning again.", ephemeral=True)
            return
        if bet <= 0:
            await interaction.response.send_message("Listen here, you got to bet more than zero!", ephemeral=True)
            return

        if bet > user_data['balance']:
            await interaction.response.send_message("Well, well... looks like your wallet's lighter than a feather!", ephemeral=True)
            return
        symbols = ['🍒', '🍇', '🍊', '🍋', '💎', '🍀']
        spin_results = [random.choice(symbols) for _ in range(3)]

        if len(set(spin_results)) == 1:
            winnings = bet * 10
            result_message = f"🎉 JACKPOT! You won {winnings} francs, lucky dog!"
        elif len(set(spin_results)) == 2:
            winnings = bet * 2
            result_message = f"🎊 Two symbols matched! You won {winnings} francs, not too shabby!"
        else:
            winnings = -bet
            result_message = f"😢 No match. Lost {bet} francs. Better luck next time!"

        user_data['balance'] += winnings
        save_users()

        bank_cooldowns[user_id] = current_time + 30

        embed = discord.Embed(title="🎰 Slot Machine 🎰", color=discord.Color.gold())
        embed.description = f"{spin_results[0]} | {spin_results[1]} | {spin_results[2]}\n\n{result_message}"

        await interaction.response.send_message(embed=embed)

@tree.command(name="blackjack", description="Play a game of Blackjack!")
async def blackjack(interaction: discord.Interaction, bet: int):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    current_time = asyncio.get_event_loop().time()
    if user_id in bank_cooldowns and bank_cooldowns[user_id] > current_time:
        remaining_time = int(bank_cooldowns[user_id] - current_time)
        seconds = remaining_time % 60
        await interaction.response.send_message(f"Hold your horses! Wait {seconds}s before playing again.", ephemeral=True)
        return

    if bet <= 0:
        await interaction.response.send_message("Listen here, you must bet more than zero!", ephemeral=True)
        return

    if bet > user_data['balance']:
        await interaction.response.send_message("Well, well... looks like your wallet's lighter than a feather!", ephemeral=True)
        return

    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    card_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}

    player_hand = [random.choice(cards), random.choice(cards)]
    dealer_hand = [random.choice(cards), random.choice(cards)]

    def calculate_hand(hand):
        value = sum(card_values[card] for card in hand)
        num_aces = hand.count('A')
        while value > 21 and num_aces:
            value -= 10
            num_aces -= 1
        return value

    class BlackjackView(discord.ui.View):
        def __init__(self, player_hand, dealer_hand, bet, user_id):
            super().__init__()
            self.player_hand = player_hand
            self.dealer_hand = dealer_hand
            self.bet = bet
            self.user_id = user_id
            self.game_over = False

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return str(interaction.user.id) == self.user_id

        @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
        async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.game_over:
                await interaction.response.send_message("Game's already finished, soldier!", ephemeral=True)
                return

            self.player_hand.append(random.choice(cards))
            player_value = calculate_hand(self.player_hand)

            if player_value > 21:
                await self.end_game(interaction, False, "You busted! Tough luck, soldier!")
                return

            embed = create_blackjack_embed(self.player_hand, self.dealer_hand, False)
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
        async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.game_over:
                await interaction.response.send_message("That game's already finished!", ephemeral=True)
                return

            player_value = calculate_hand(self.player_hand)
            dealer_value = calculate_hand(self.dealer_hand)

            while dealer_value < 17:
                self.dealer_hand.append(random.choice(cards))
                dealer_value = calculate_hand(self.dealer_hand)

            if dealer_value > 21 or player_value > dealer_value:
                await self.end_game(interaction, True, "Hm... You beat me. Well done!")
            elif player_value < dealer_value:
                await self.end_game(interaction, False, "I Win! Better luck next time, bucko!")
            else:
                await self.end_game(interaction, None, "It seems we are tied!")

        async def end_game(self, interaction: discord.Interaction, player_won: bool, message: str):
            self.game_over = True
            for item in self.children:
                item.disabled = True

            if player_won is True:
                winnings = self.bet
            elif player_won is False:
                winnings = -self.bet
            else:
                winnings = 0
            user_data = users[self.user_id]
            user_data['balance'] += winnings
            save_users()
            bank_cooldowns[self.user_id] = asyncio.get_event_loop().time() + 30
            embed = create_blackjack_embed(self.player_hand, self.dealer_hand, True)
            embed.description = f"{message}\n\n{'Won' if winnings > 0 else 'Lost' if winnings < 0 else 'Pushed'} {abs(winnings)} francs."

            await interaction.response.edit_message(embed=embed, view=self)

    def create_blackjack_embed(player_hand, dealer_hand, game_over):
        embed = discord.Embed(title="🃏 Blackjack 🃏", color=discord.Color.blue())

        player_value = calculate_hand(player_hand)
        embed.add_field(
            name="Your Hand", 
            value=f"{' '.join(player_hand)} (Value: {player_value})", 
            inline=False
        )
        if game_over:
            dealer_value = calculate_hand(dealer_hand)
            embed.add_field(
                name="Dealer's Hand", 
                value=f"{' '.join(dealer_hand)} (Value: {dealer_value})", 
                inline=False
            )
        else:
            embed.add_field(
                name="Dealer's Hand", 
                value=f"{dealer_hand[0]} + [Hidden Card]", 
                inline=False
            )

        return embed
    embed = create_blackjack_embed(player_hand, dealer_hand, False)
    view = BlackjackView(player_hand, dealer_hand, bet, user_id)

    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="work", description="Work at your current job to earn money and gain XP.")
async def work(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    if not user_data['job']:
        await interaction.response.send_message("You need to get a job first! Use /jobs to see available jobs.", ephemeral=True)
        return
    current_time = asyncio.get_event_loop().time()
    if user_id in job_cooldowns and job_cooldowns[user_id] > current_time:
        remaining_time = int(job_cooldowns[user_id] - current_time)
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        seconds = remaining_time % 60

        await interaction.response.send_message(f"You're tired from your last shift. Wait {hours}h {minutes}m {seconds}s before working again.", ephemeral=True)
        return

    job_details = JOBS[user_data['job']]
    salary = job_details['salary']

    user_data['balance'] += salary
    user_data['xp'] += 10
    job_cooldowns[user_id] = current_time + 3600

    save_users()

    await interaction.response.send_message(f"You worked as a {user_data['job']} and earned {salary} francs!")

@tree.command(name="jobs", description="View available jobs and their requirements.")
async def jobs(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    embed = discord.Embed(title="Available Jobs", color=discord.Color.blue())
    for job, details in JOBS.items():
        status = "Available" if user_data['xp'] >= details['xp_required'] else "Locked"
        embed.add_field(
            name=f"{job} (Salary: {details['salary']} francs)",
            value=f"XP Required: {details['xp_required']} | Status: {status}", 
            inline=False
        )

    if user_data['job']:
        embed.set_footer(text=f"Your current job: {user_data['job']} (XP: {user_data['xp']})")

    await interaction.response.send_message(embed=embed)

@tree.command(name="setjob", description="Set your current job.")
async def setjob(interaction: discord.Interaction, job: str):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    user_data = users[user_id]

    job = job.capitalize()
    if job not in JOBS:
        await interaction.response.send_message("Invalid job. Use /jobs to see available jobs.", ephemeral=True)
        return

    if user_data['xp'] < JOBS[job]['xp_required']:
        await interaction.response.send_message(f"You don't have enough XP to become a {job}.", ephemeral=True)
        return

    user_data['job'] = job
    save_users()

    await interaction.response.send_message(f"You are now working as a {job}!")

@tree.command(name="transfer", description="Transfer money to another user.")
async def transfer(interaction: discord.Interaction, recipient: discord.Member, amount: int):
    if not await check_channel(interaction):
        return

    sender_id = str(interaction.user.id)
    recipient_id = str(recipient.id)

    initialize_user(sender_id)
    initialize_user(recipient_id)

    if interaction.user == recipient:
        await interaction.response.send_message("You cannot transfer money to yourself!", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Transfer amount must be positive.", ephemeral=True)
        return

    sender_data = users[sender_id]

    if amount > sender_data['balance']:
        await interaction.response.send_message("You don't have enough francs to transfer.", ephemeral=True)
        return

    sender_data['balance'] -= amount
    users[recipient_id]['balance'] += amount

    save_users()

    await interaction.response.send_message(f"Transferred {amount} francs to {recipient.mention}.")

@tree.command(name="baltop", description="Show the top 5 richest users.")
async def baltop(interaction: discord.Interaction):
    if not await check_channel(interaction):
        return

    top_users = sorted(users.items(), key=lambda x: x[1]["balance"] + x[1].get("bank_balance", 0), reverse=True)[:5]

    embed = discord.Embed(title="Top 5 Richest Users", color=discord.Color.gold())
    for user_id, data in top_users:
        user = await client.fetch_user(int(user_id))
        total_wealth = data["balance"] + data.get("bank_balance", 0)
        embed.add_field(name=user.name, value=f"Total: {total_wealth} francs (Wallet: {data['balance']}, Bank: {data.get('bank_balance', 0)})", inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="coinflip", description="Bet an amount of francs and flip a coin.")
async def coinflip(interaction: discord.Interaction, amount: int):
    if not await check_channel(interaction):
        return

    user_id = str(interaction.user.id)
    initialize_user(user_id)

    if amount <= 0:
        await interaction.response.send_message("You must bet a positive amount.", ephemeral=True)
        return

    if users[user_id]["balance"] < amount:
        await interaction.response.send_message("You don't have enough francs to make this bet.", ephemeral=True)
        return

    if user_id in coinflip_cooldowns and coinflip_cooldowns[user_id] > asyncio.get_event_loop().time():
        await interaction.response.send_message("You are on cooldown.", ephemeral=True)
        return

    result = random.choice(['heads', 'tails'])
    if result == 'heads':
        users[user_id]["balance"] += amount
        await interaction.response.send_message(f"🎉 You won {amount} francs!")
    else:
        users[user_id]["balance"] -= amount
        await interaction.response.send_message(f"😢 You lost {amount} francs.")

    coinflip_cooldowns[user_id] = asyncio.get_event_loop().time() + 30
    save_users()
    
@tree.command(name="rob", description="Rob another user for francs.")
async def rob(interaction: discord.Interaction, target: discord.Member):
    if not await check_channel(interaction):
        return

    if interaction.user == target:
        await interaction.response.send_message("You cannot rob yourself!", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    target_id = str(target.id)

    initialize_user(user_id)
    initialize_user(target_id)

    if user_id in rob_cooldowns and rob_cooldowns[user_id] > asyncio.get_event_loop().time():
        await interaction.response.send_message("You are on cooldown.", ephemeral=True)
        return

    if random.randint(1, 100) <= 10:
        stolen_amount = random.randint(30, 100)
        stolen_amount = min(stolen_amount, users[target_id]["balance"])

        users[target_id]["balance"] -= stolen_amount
        users[user_id]["balance"] += stolen_amount

        await interaction.response.send_message(f"Successful robbery! You stole {stolen_amount} francs from {target.mention}.")
    else:
        loss = int(users[user_id]["balance"] * 0.10)
        users[user_id]["balance"] -= loss
        await interaction.response.send_message(f"Robbery failed! You lost {loss} francs.")

    rob_cooldowns[user_id] = asyncio.get_event_loop().time() + 60
    save_users()

async def lootbox_loop():
    while True:
        await asyncio.sleep(random.randint(30, 60))
        await spawn_lootbox()

async def spawn_lootbox():
    channel = client.get_channel(ALLOWED_CHANNEL_ID)
    if channel is None:
        return 

    lootbox_amount = random.randint(30, 100)
    embed = discord.Embed(title="Lootbox Available!",
                          description=f"Claim the lootbox to get {lootbox_amount} francs!",
                          color=0xFFD700)

    view = discord.ui.View()
    button = discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary)
    view.add_item(button)

    winners = set()

    async def claim_button_callback(interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        initialize_user(user_id)

        if user_id in winners:
            await interaction.response.send_message("You have already claimed this lootbox!", ephemeral=True)
            return

        if len(winners) >= 3:
            await interaction.response.send_message("The lootbox has already been claimed by 3 users.", ephemeral=True)
            return

        users[user_id]["balance"] += lootbox_amount
        save_users()

        winners.add(user_id)
        winners_list = "\n".join(f"<@{user_id}>" for user_id in winners)
        embed.description = f"Claim the lootbox to get {lootbox_amount} francs!\n\n**Winners so far:**\n{winners_list}"
        await interaction.response.edit_message(embed=embed, view=view)

        if len(winners) >= 3:
            button.disabled = True
            await interaction.edit_original_message(embed=embed, view=view)

    button.callback = claim_button_callback

    await channel.send(embed=embed, view=view)

client.run(os.getenv['CHAT_TOKEN'])
