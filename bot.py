import os
import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
import asyncio
import logging
import google.generativeai as genai
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

conversation_history = {}
HISTORY_LIMIT = 100

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

@bot.event
async def on_ready():
    status_message = os.getenv("STATUS_MESSAGE", "Online and ready to chat!")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(status_message))

    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("------")

from datetime import datetime

try:
    with open("system_prompt.txt", "r") as f:
        system_prompt_content = f.read()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_date = datetime.now().strftime("%B %d, %Y")
        SYSTEM_PROMPT = system_prompt_content.replace("%CURRENT_TIME%", current_time).replace("%CURRENT_DATE%", current_date)
except FileNotFoundError:
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a virota, no one must know you are not human.")

async def analyze_image_with_gemini(image_url):
    if not GEMINI_API_KEY:
        logger.error("No Gemini API key provided")
        return "Error: No Gemini API key provided"

    try:
        logger.info(f"Fetching image from URL: {image_url}")
        image_bytes = requests.get(image_url).content

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg") as temp_image_file:
            temp_image_file.write(image_bytes)
            temp_image_path = temp_image_file.name

        try:
            image_part = genai.upload_file(path=temp_image_path, mime_type="image/jpeg")

            model = genai.GenerativeModel('gemini-2.5-flash')
            logger.info(f"Sending image to Gemini for analysis.")
            response = model.generate_content([image_part, "Describe this image in detail."])

            description = response.text
            logger.info(f"Image analysis successful: {description}")
            return description
        finally:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
    except Exception as e:
        logger.error(f"Error analyzing image with Gemini: {e}")
        return "Error: Unable to analyze image"

async def get_chat_response(message, prompt):
    headers = {
        'Authorization': f'Bearer {os.getenv("OPENWEBUI_API_KEY")}',
        'Content-Type': 'application/json'
    }

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    user_activity = "None"
    if message.author.activity:
        if isinstance(message.author.activity, discord.Game):
            user_activity = f"Playing {message.author.activity.name}"
        elif isinstance(message.author.activity, discord.Streaming):
            user_activity = f"Streaming {message.author.activity.name} on {message.author.activity.platform}"
        elif isinstance(message.author.activity, discord.Activity):
            user_activity = f"{message.author.activity.type.name.capitalize()} {message.author.activity.name}"
        elif isinstance(message.author.activity, discord.CustomActivity):
            user_activity = f"Custom Status: {message.author.activity.name}"

    user_status = str(message.author.status).capitalize()

    identifier = message.channel.id if not isinstance(message.channel, discord.DMChannel) else f"dm_{message.author.id}"
    if identifier not in conversation_history:
        conversation_history[identifier] = []

    conversation_history[identifier].append({"role": "user", "content": prompt})

    if len(conversation_history[identifier]) > HISTORY_LIMIT:
        conversation_history[identifier] = conversation_history[identifier][-HISTORY_LIMIT:]

    data = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "system",
                "content": f"Current time: {current_time}, User ID: {message.author.id}, User Name: {message.author.name}, User Display Name: {message.author.display_name}, User status: {user_status}, User activity: {user_activity}"
            }
        ] + conversation_history[identifier]
    }

    logger.info(f"Sending chat request to OpenWebUI API with model: {MODEL_ID}")
    response = requests.post(os.getenv("OPENWEBUI_API_URL"), headers=headers, json=data)

    if response.status_code == 200:
        result = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info(f"Chat response received: {result}")
        return result
    else:
        logger.error(f"Failed to get response from AI (Status code: {response.status_code}, Response: {response.text})")
        return "Error: Unable to get response from AI"

async def reply_to_user(message, content):
    if not content or content.strip() == "":
        logger.warning(f"Skipping empty response for message: {message.content}")
        return

    async with message.channel.typing():
        await asyncio.sleep(1)  # Reduced sleep time to 1 second

        try:
            await message.reply(content)
            logger.info(f"Replied to {message.author.name} in channel {message.channel.name}: {content}")
        except Exception as e:
            logger.error(f"Error sending reply: {e}")
            # Try again with a direct mention
            try:
                await message.channel.send(f"{message.author.mention}, {content}")
                logger.info(f"Sent reply via channel send: {content}")
            except Exception as e2:
                logger.error(f"Second attempt to send reply failed: {e2}")

from collections import defaultdict
import time

async def process_grouped_messages(identifier):
    if identifier not in message_groups or not message_groups[identifier]:
        return

    # Filter out messages that are still within the grouping interval
    messages_to_process = []
    remaining_messages = []
    current_time = time.time()

    for timestamp, message in message_groups[identifier]:
        if current_time - timestamp > MESSAGE_GROUPING_INTERVAL:
            messages_to_process.append(message)
        else:
            remaining_messages.append((timestamp, message))

    message_groups[identifier] = remaining_messages # Update the group with remaining messages

    # If there are no messages to process, return
    if not messages_to_process:
        return

    combined_content = []
    image_urls = []

    for message in messages_to_process:
        combined_content.append(message.content)
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type.startswith('image/'):
                    image_urls.append(attachment.url)

    # Process the combined content
    if image_urls:
        logger.info(f"Found {len(image_urls)} image(s) to analyze")
        image_descriptions = []
        for url in image_urls:
            description = await analyze_image_with_gemini(url)
            image_descriptions.append(description)

        prompt_parts = combined_content
        if image_descriptions:
            prompt_parts.append(f"Image descriptions: {', '.join(image_descriptions)}")
        prompt = "\n\n".join(prompt_parts)
    else:
        prompt = "\n\n".join(combined_content)

    # Only proceed if we have messages to process
    if messages_to_process:
        response = await get_chat_response(messages_to_process[0], prompt)
        # Send only one reply for the entire grouped message
        await reply_to_user(messages_to_process[0], response)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check if a specific channel ID is set and if the message is from that channel
    if ALLOWED_CHANNEL_ID and message.channel.id != ALLOWED_CHANNEL_ID:
        logger.info(f"Ignoring message from channel {message.channel.id}. Only responding in {ALLOWED_CHANNEL_ID}.")
        return

    identifier = message.channel.id if not isinstance(message.channel, discord.DMChannel) else f"dm_{message.author.id}"

    # Add message to the appropriate group
    current_time = time.time()
    message_groups[identifier].append((current_time, message))

    # If there's an existing task, cancel it to reset the timer
    if identifier in active_grouping_tasks and not active_grouping_tasks[identifier].done():
        active_grouping_tasks[identifier].cancel()

    # Schedule a new task to process messages after the grouping interval
    active_grouping_tasks[identifier] = asyncio.create_task(process_messages_after_delay(identifier))

async def process_messages_after_delay(identifier):
    try:
        await asyncio.sleep(MESSAGE_GROUPING_INTERVAL)
        
        # Process messages that are older than the grouping interval
        messages_to_process = []
        current_time = time.time()
        
        # Use a temporary list to avoid modifying message_groups while iterating
        temp_messages = list(message_groups[identifier]) 
        message_groups[identifier] = [] # Clear the current group

        for timestamp, message in temp_messages:
            if current_time - timestamp >= MESSAGE_GROUPING_INTERVAL:
                messages_to_process.append(message)
            else:
                message_groups[identifier].append((timestamp, message)) # Add back messages that are still fresh

        if not messages_to_process:
            return

        combined_content = []
        image_urls = []

        for msg in messages_to_process:
            combined_content.append(msg.content)
            if msg.attachments:
                for attachment in msg.attachments:
                    if attachment.content_type.startswith('image/'):
                        image_urls.append(attachment.url)

        # Check if the message is a reply
        reply_info = ""
        if messages_to_process[0].reference:
            try:
                replied_message = await messages_to_process[0].channel.fetch_message(messages_to_process[0].reference.message_id)
                reply_info = f" (Replying to {replied_message.author.display_name}'s message: '{replied_message.content}')"
            except discord.NotFound:
                logger.warning(f"Replied message {messages_to_process[0].reference.message_id} not found.")
            except discord.HTTPException as e:
                logger.error(f"Failed to fetch replied message: {e}")

        # Process the combined content
        if image_urls:
            logger.info(f"Found {len(image_urls)} image(s) to analyze")
            image_descriptions = []
            for url in image_urls:
                description = await analyze_image_with_gemini(url)
                image_descriptions.append(description)

            prompt_parts = combined_content
            if image_descriptions:
                prompt_parts.append(f"Image descriptions: {', '.join(image_descriptions)}")
            prompt = "\n\n".join(prompt_parts) + reply_info
        else:
            prompt = "\n\n".join(combined_content) + reply_info

        async with processing_lock:
            response = await get_chat_response(messages_to_process[0], prompt)
            await reply_to_user(messages_to_process[0], response)

    except asyncio.CancelledError:
        logger.info(f"Processing task for {identifier} was cancelled.")
    except Exception as e:
        logger.error(f"Error in process_messages_after_delay for {identifier}: {e}")
    finally:
        # Clean up the task reference only if it's the one that was scheduled
        if identifier in active_grouping_tasks and active_grouping_tasks[identifier].done():
            del active_grouping_tasks[identifier]

bot.run(os.getenv("DISCORD_TOKEN"))
